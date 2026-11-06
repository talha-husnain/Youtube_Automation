"""Free stock footage and photos (Pexels, Pixabay) for the generated videos.

The search and download part follows MoneyPrinterTurbo (MIT licence,
Copyright (c) 2024 Harry, github.com/harry0703/MoneyPrinterTurbo,
app/services/material.py): orientation and size filters, a 24 h search
cache, downloads cached by URL and checked before use. Added here, because
they search once per video and use whatever comes back:
- a search per scene (every line of the script says what it wants to show);
- one vision call that looks at the candidates' thumbnails and picks the clip
  that fits each scene, or none;
- a memory of clips used lately (USED_DAYS), so a channel does not show the
  same shot every day.

Both libraries allow free use, also commercial, with no credit required
(pexels.com/license, pixabay.com/service/license-summary); descriptions still
name them. Keys are free: PEXELS_API_KEY, PIXABAY_API_KEY in .env. Openverse
(api.openverse.org) needs no key: public-domain and CC0 photos only (no
attribution or share-alike strings), 200 searches a day anonymously, so the
footage step has photos even before the owner signs up anywhere.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.abspath(__file__))
SEARCH_FILE = os.path.join(ROOT, "output", ".stock_search.json")
USED_FILE = os.path.join(ROOT, "output", ".stock_used.json")
CACHE_DIR = os.path.join(ROOT, "output", "stock_cache")
CACHE_MAX_MB = int(os.environ.get("STOCK_CACHE_MB") or 3000)
SEARCH_TTL = 24 * 3600
USED_DAYS = 14
MIN_SHORT_SIDE = 720            # 720p still fills a phone after a small upscale; 1080p is preferred
PER_SCENE = 6                   # candidates per scene shown to the picker
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Shortkaar/1.0"
_lock = threading.Lock()


def keys():
    """Each library's key; Openverse needs none ("anon"), OPENVERSE=0 turns it off."""
    return {"pexels": (os.environ.get("PEXELS_API_KEY") or "").strip(),
            "pixabay": (os.environ.get("PIXABAY_API_KEY") or "").strip(),
            "openverse": "" if os.environ.get("OPENVERSE", "1") == "0" else "anon",
            "wikipedia": "" if os.environ.get("WIKIPEDIA_PHOTOS", "1") == "0" else "anon"}


def available():
    return any(keys().values())


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


# ------------------------------------------------------------------ search

LIMITS_FILE = os.path.join(ROOT, "output", ".stock_limits.json")
REST_SECONDS = 3600     # a library that says "too many requests" rests an hour


class RateLimited(Exception):
    pass


def _get(url, headers=None, timeout=30):
    """httpx.get that turns a 429 into RateLimited (Pexels: 200 an hour and
    20,000 a month, docs 15-oct-2026; abuse ends the key)."""
    r = httpx.get(url, headers=headers, timeout=timeout)
    if r.status_code == 429:
        raise RateLimited(url.split("?")[0])
    return r


def _resting(provider):
    return _read(LIMITS_FILE, {}).get(provider, 0) > time.time()


def _rest(provider, seconds=REST_SECONDS, why="says too many requests"):
    with _lock:
        data = _read(LIMITS_FILE, {})
        data[provider] = int(time.time()) + seconds
        _write(LIMITS_FILE, data)
    print(f"   ⏸️ {provider} {why}: resting it for {seconds // 60} minutes.")


# A library that does not answer at all rests too: on 15-oct-2026 Openverse
# timed out on every search (curl too), and 10 searches at 30 s each held a
# quiz Short for 100 s before it went on without footage.
DOWN_AFTER = 2
DOWN_REST = 900
_misses, _down_at = {}, {}


def _missed(provider, error):
    if not isinstance(error, (httpx.TimeoutException, httpx.NetworkError)):
        return
    with _lock:
        _misses[provider] = _misses.get(provider, 0) + 1
        # Searches already in flight time out too: one rest per DOWN_REST.
        down = _misses[provider] >= DOWN_AFTER and time.time() - _down_at.get(provider, 0) > DOWN_REST
        if down:
            _misses[provider] = 0
            _down_at[provider] = time.time()
    if down:
        _rest(provider, DOWN_REST, "is not answering")

def _rendition(files, portrait, crop=False):
    """The smallest file whose short side is at least 1080, else the largest
    of at least MIN_SHORT_SIDE: [(w, h, url[, bytes])] -> (w, h, url) or None.
    ``crop`` (portrait only): a landscape file at least CROP_HEIGHT tall whose
    size is known and at most CROP_MAX_MB also counts, after the portrait ones:
    its 9:16 centre is still 1080 wide or more."""
    ok = [(w, h, u) for w, h, u, *_s in files if (h > w) == portrait and min(w, h) >= MIN_SHORT_SIDE]
    full = [f for f in ok if min(f[0], f[1]) >= 1080]
    if not full and crop and portrait:
        wide = [(w, h, u) for w, h, u, *s in files
                if w > h >= CROP_HEIGHT and s and 0 < s[0] <= CROP_MAX_MB * 1e6]
        if wide:
            return min(wide, key=lambda f: f[0] * f[1])
    if not ok:
        return None
    return min(full, key=lambda f: f[0] * f[1]) if full else max(ok, key=lambda f: f[0] * f[1])


# A landscape clip this tall fills a 1080x1920 frame from its 9:16 centre without being enlarged (4K:
# a 1215x2160 slice). Pixabay had 1-3 portrait clips per cricket search and 19-28 landscape 4K ones
# (29-oct-2026); only the pool asks for them, and only files Pixabay says are small: its 4K files ran
# 1.7-148 MB (median 38) where a portrait full-HD clip was 4 MB, and downloads here ran at 50 KB/s that
# night. Pexels gives no sizes: portrait clips only.
CROP_HEIGHT = 1920
try:
    CROP_MAX_MB = float(os.environ.get("STOCK_CROP_MB") or 25)
except ValueError:
    CROP_MAX_MB = 25.0


def _pexels_videos(term, portrait, key, crop=False):
    # ``crop`` changes nothing here: Pexels gives no file sizes (see CROP_MAX_MB).
    r = _get("https://api.pexels.com/v1/videos/search?" + urlencode(
        {"query": term, "per_page": 20, "orientation": "portrait" if portrait else "landscape"}),
        headers={"Authorization": key, "User-Agent": UA}, timeout=30)
    out = []
    for v in (r.json() or {}).get("videos") or [] if r.status_code == 200 else []:
        files = [(int(f.get("width") or 0), int(f.get("height") or 0), f.get("link"))
                 for f in v.get("video_files") or [] if f.get("link")]
        best = _rendition(files, portrait, crop)
        if not best or not v.get("duration"):
            continue
        # Pexels gives no tags; its page address names the clip ("/video/boy-playing-cricket-123/").
        slug = re.sub(r"[-/]+", " ", re.sub(r"^.*/video/|-?\d+/?$", "", v.get("url") or "")).strip()
        out.append({"id": f"pexels:v{v['id']}", "provider": "Pexels", "kind": "video", "url": best[2],
                    "w": best[0], "h": best[1], "seconds": float(v["duration"]), "thumb": v.get("image") or "",
                    "page": v.get("url") or "", "author": ((v.get("user") or {}).get("name") or "")[:60],
                    "alt": slug[:120]})
    return out


def _pixabay_videos(term, portrait, key, crop=False):
    r = _get("https://pixabay.com/api/videos/?" + urlencode(
        {"key": key, "q": term[:100], "per_page": 50, "safesearch": "true"}), headers={"User-Agent": UA}, timeout=30)
    out = []
    for v in (r.json() or {}).get("hits") or [] if r.status_code == 200 else []:
        sizes = v.get("videos") or {}
        files = [(int(f.get("width") or 0), int(f.get("height") or 0), f.get("url"), int(f.get("size") or 0))
                 for f in sizes.values() if isinstance(f, dict) and f.get("url")]
        best = _rendition(files, portrait, crop)
        if not best or not v.get("duration"):
            continue
        thumb = next((f.get("thumbnail") for f in sizes.values() if isinstance(f, dict) and f.get("thumbnail")), "")
        out.append({"id": f"pixabay:v{v['id']}", "provider": "Pixabay", "kind": "video", "url": best[2],
                    "w": best[0], "h": best[1], "seconds": float(v["duration"]), "thumb": thumb,
                    "page": v.get("pageURL") or "", "author": (v.get("user") or "")[:60],
                    "alt": (v.get("tags") or "")[:120]})
    return out


def _pexels_photos(term, portrait, key):
    r = _get("https://api.pexels.com/v1/search?" + urlencode(
        {"query": term, "per_page": 20, "orientation": "portrait" if portrait else "landscape"}),
        headers={"Authorization": key, "User-Agent": UA}, timeout=30)
    out = []
    for p in (r.json() or {}).get("photos") or [] if r.status_code == 200 else []:
        w, h, src = int(p.get("width") or 0), int(p.get("height") or 0), p.get("src") or {}
        if not src.get("original") or min(w, h) < 1000 or (h > w) != portrait:
            continue
        # Pexels serves any width from the original: 2400 px is enough to pan over.
        out.append({"id": f"pexels:p{p['id']}", "provider": "Pexels", "kind": "photo",
                    "url": src["original"] + "?auto=compress&cs=tinysrgb&w=2400", "w": w, "h": h, "seconds": 0.0,
                    "thumb": src.get("medium") or src.get("small") or "", "page": p.get("url") or "",
                    "author": (p.get("photographer") or "")[:60], "alt": (p.get("alt") or "")[:120]})
    return out


def _pixabay_photos(term, portrait, key):
    r = _get("https://pixabay.com/api/?" + urlencode(
        {"key": key, "q": term[:100], "image_type": "photo", "per_page": 30, "safesearch": "true",
         "orientation": "vertical" if portrait else "horizontal"}), headers={"User-Agent": UA}, timeout=30)
    out = []
    for p in (r.json() or {}).get("hits") or [] if r.status_code == 200 else []:
        if not p.get("largeImageURL") or min(int(p.get("imageWidth") or 0), int(p.get("imageHeight") or 0)) < 1000:
            continue
        out.append({"id": f"pixabay:p{p['id']}", "provider": "Pixabay", "kind": "photo", "url": p["largeImageURL"],
                    "w": int(p["imageWidth"]), "h": int(p["imageHeight"]), "seconds": 0.0,
                    "thumb": p.get("webformatURL") or p.get("previewURL") or "", "page": p.get("pageURL") or "",
                    "author": (p.get("user") or "")[:60], "alt": (p.get("tags") or "")[:120]})
    return out


OPENVERSE_DAY_CAP = 180     # anonymous Openverse: 20 a minute, 200 a day (its rate-limit headers, 15-oct-2026)
OPENVERSE_FILE = os.path.join(ROOT, "output", ".openverse_calls.json")
WIKI_FILE = os.path.join(ROOT, "output", ".wikipedia_calls.json")


def _openverse_photos(term, portrait, key=None):
    """Public-domain and CC0 photos (Flickr, museums, Wikimedia...) through
    Openverse, which needs no key: works before the owner's sign-ups."""
    day = time.strftime("%Y-%m-%d")
    with _lock:
        calls = _read(OPENVERSE_FILE, {})
        if calls.get(day, 0) >= OPENVERSE_DAY_CAP:
            return []
        _write(OPENVERSE_FILE, {day: calls.get(day, 0) + 1})
    # Few public-domain photos are tall: for a phone frame any large photo will
    # do whose height fills it after the crop (a space quiz found 8 tall ones for 8 lines).
    query = {"q": term[:100], "license": "cc0,pdm", "size": "large", "mature": "false", "page_size": 20}
    if not portrait:
        query["aspect_ratio"] = "wide"
    # Openverse answers in 1-2 s when it is up; 30 s per search held a Short 68 s when it was down.
    r = _get("https://api.openverse.org/v1/images/?" + urlencode(query), headers={"User-Agent": UA}, timeout=12)
    out = []
    for p in (r.json() or {}).get("results") or [] if r.status_code == 200 else []:
        w, h = int(p.get("width") or 0), int(p.get("height") or 0)
        if not p.get("url") or (w and h and (h < 1400 if portrait else min(w, h) < 1000)):
            continue
        out.append({"id": f"openverse:{p['id']}", "provider": "Openverse", "kind": "photo", "url": p["url"],
                    "w": w, "h": h, "seconds": 0.0, "thumb": p.get("thumbnail") or p["url"],
                    "page": p.get("foreign_landing_url") or "", "author": (p.get("creator") or "")[:60],
                    "alt": (p.get("title") or "")[:120], "licence": p.get("license") or ""})
    return out


WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_DAY_CAP = 300          # searches a day (2 API calls each); Wikimedia asks for gentle use
WIKI_JUNK = re.compile(r"\.svg$|logo|icon|flag_of|coat_of_arms|emblem|seal_of|signature|wordmark|map_of|"
                       r"locator|blank|portrait_placeholder", re.I)
WIKI_PERSON = re.compile(r"\b(born|died|cricketer|footballer|player|athlete|actor|actress|singer|musician|rapper|"
                         r"politician|businessman|businesswoman|journalist|writer|author|poet|president|minister|"
                         r"coach|umpire|captain|model|youtuber|personality|presenter|king|queen|emperor|sultan|"
                         r"general|commander|scholar|saint|imam|caliph|prophet)\b|\(\d{4}", re.I)


def _wikipedia_photos(term, portrait, key=None):
    """Lead pictures of the Wikipedia articles a search for ``term`` finds,
    free licences only (Wikimedia Commons, credited by name and licence).
    Keyless and reachable from this laptop when Openverse's search was down
    for hours (15-oct-2026); the vision pick still decides whether one fits."""
    from player_photo import FREE, UA as WIKI_UA, _strip
    day = time.strftime("%Y-%m-%d")
    with _lock:
        calls = _read(WIKI_FILE, {})
        if calls.get(day, 0) >= WIKI_DAY_CAP:
            return []
        _write(WIKI_FILE, {day: calls.get(day, 0) + 1})
    head = {"User-Agent": WIKI_UA}
    r = _get(WIKI_API + "?" + urlencode({"action": "query", "format": "json", "generator": "search",
                                         "gsrsearch": term[:100], "gsrnamespace": 0, "gsrlimit": 12,
                                         "prop": "pageimages|description", "piprop": "name"}), headers=head, timeout=15)
    pages = ((r.json() if r.status_code == 200 else {}).get("query") or {}).get("pages") or {}
    # An article about a person leads with their portrait: "Babar Azam's
    # century" got a photo of Cameron Green (15-oct-2026). Named people get
    # their own photo elsewhere (player_photo); stock shows no one by name.
    files = [p["pageimage"] for p in sorted(pages.values(), key=lambda p: p.get("index", 99))
             if p.get("pageimage") and not WIKI_JUNK.search(p["pageimage"])
             and not WIKI_PERSON.search(p.get("description") or "") and not WIKI_PERSON.search(p.get("title") or "")][:10]
    if not files:
        return []
    size = {"iiurlheight": 2000} if portrait else {"iiurlwidth": 1920}
    r = _get(WIKI_API + "?" + urlencode({"action": "query", "format": "json", "prop": "imageinfo",
                                         "titles": "|".join("File:" + f for f in files),
                                         "iiprop": "url|size|extmetadata", **size}), headers=head, timeout=15)
    out = []
    for p in ((r.json() if r.status_code == 200 else {}).get("query") or {}).get("pages", {}).values():
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        licence = _strip((meta.get("LicenseShortName") or {}).get("value"))
        w, h = int(info.get("width") or 0), int(info.get("height") or 0)
        if not info.get("thumburl") or not FREE.match(licence or ""):
            continue
        if h < 1400 if portrait else min(w, h) < 1000:
            continue
        name = p.get("title", "").removeprefix("File:")
        out.append({"id": f"wikipedia:{name}", "provider": "Wikimedia Commons", "kind": "photo",
                    "url": info["thumburl"], "w": int(info.get("thumbwidth") or w), "h": int(info.get("thumbheight") or h),
                    "seconds": 0.0, "thumb": _commons_thumb(info["thumburl"]), "page": info.get("descriptionurl") or "",
                    "author": _strip((meta.get("Artist") or {}).get("value"))[:60], "alt": name[:120],
                    "licence": licence[:40]})
    return out


SEARCHERS = {("pexels", "video"): _pexels_videos, ("pixabay", "video"): _pixabay_videos,
             ("pexels", "photo"): _pexels_photos, ("pixabay", "photo"): _pixabay_photos,
             ("openverse", "photo"): _openverse_photos, ("wikipedia", "photo"): _wikipedia_photos}


def search(term, portrait=True, kind="video", crop=False):
    """Candidates for ``term`` from every library with a key, cached 24 h
    (an empty answer too, but only for an hour: it may be a hiccup). ``crop``:
    videos may be landscape 4K, cropped to the portrait frame (_rendition)."""
    term = re.sub(r"\s+", " ", str(term or "")).strip()[:80]
    if not term:
        return []
    crop = bool(crop and portrait and kind == "video")
    out = []
    for provider, key in keys().items():
        if not key or (provider, kind) not in SEARCHERS or _resting(provider):
            continue
        cache_key = f"{provider}|{kind}|{'p' if portrait else 'l'}{f'c{CROP_MAX_MB:g}' if crop else ''}|{term.lower()}"
        with _lock:
            hit = _read(SEARCH_FILE, {}).get(cache_key)
        if hit and time.time() - hit["at"] < (SEARCH_TTL if hit["items"] else 3600):
            out += hit["items"]
            continue
        try:
            items = SEARCHERS[(provider, kind)](term, portrait, key, **({"crop": True} if crop else {}))
        except RateLimited:
            _rest(provider)
            continue
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            print(f"   ℹ️ {provider} search failed for '{term}' ({type(e).__name__}).")
            _missed(provider, e)
            continue
        _misses.pop(provider, None)
        with _lock:
            data = _read(SEARCH_FILE, {})
            data[cache_key] = {"at": int(time.time()), "items": items}
            # Keep the file small: drop entries past their day.
            data = {k: v for k, v in data.items() if time.time() - v.get("at", 0) < SEARCH_TTL}
            _write(SEARCH_FILE, data)
        out += items
    return out


# ------------------------------------------------------------------ memory

def recently_used(days=USED_DAYS):
    cut = time.time() - days * 86400
    return {k for k, t in _read(USED_FILE, {}).items() if t >= cut}


def mark_used(ids):
    with _lock:
        data = _read(USED_FILE, {})
        cut = time.time() - 60 * 86400
        data = {k: t for k, t in data.items() if t >= cut}
        for i in ids:
            data[i] = int(time.time())
        _write(USED_FILE, data)


# ------------------------------------------------------------------ picking

class Choice(BaseModel):
    scene: int
    clip: int
    fit: int


# Picks the picker itself scores under this are dropped: with only Openverse to
# choose from, a cricket Short got old leather book covers for "records"
# (15-oct-2026), worse than the plain gradient.
MIN_FIT = 6


class Choices(BaseModel):
    picks: List[Choice]


PICK_PROMPT = """You choose background footage for the scenes of a short video. Topic: {topic}
SCENES (number: what the narrator says / what should be seen):
{scenes}

The {n} pictures above are thumbnails of candidate clips, numbered from 0 in the order given:
{clips}

For each scene choose the clip whose picture fits it best: the same kind of place, object, action or mood, and
say how well it fits: fit 0-10, where 8+ shows the line's subject, 6-7 its setting or mood, under 6 only loosely
related or generic (a texture, an unrelated object). Prefer moving footage (video) when it fits as well, and a
full-HD clip over one marked 720p. "General" clips were searched for the whole channel, not one scene: use them
for any scene they fit. The
mood must match: never celebration (fireworks, parties) under a serious or sad line. Never choose one that shows
something unrelated, a logo, a watermark, readable text, a famous building or person that the scene is not
about, or anything sexual, violent or religious that the scene does not ask for. Never a portrait or close
photo of a recognisable real person (a named player, a painted noble) unless the line names exactly that
person: a viewer takes them for the person spoken about. Crowds and far-off players are fine. {rule}Use each clip at most
once. Use clip -1 when nothing fits. Return one pick per scene."""


def _agent(url):
    """upload.wikimedia.org answers 429 to a browser-like agent and 200 to one
    that says who is calling, as its policy asks (checked 15-oct-2026)."""
    if "wikimedia.org" in (url or ""):
        from player_photo import UA as wiki_ua
        return wiki_ua
    return UA


def _commons_thumb(url):
    """A 500 px Commons thumbnail of ``url`` (500 is one of the sizes
    Wikimedia serves; 400 was refused with a 400), or the URL itself."""
    m = re.match(r"(https://upload\.wikimedia\.org/wikipedia/commons)/(?:thumb/)?([0-9a-f]/[0-9a-f]{2}/([^/?]+))", url or "")
    return f"{m.group(1)}/thumb/{m.group(2)}/500px-{m.group(3)}" if m else url


def _thumb_part(url):
    from google.genai import types
    from PIL import Image
    r = httpx.get(url, headers={"User-Agent": _agent(url)}, timeout=20, follow_redirects=True)
    if r.status_code != 200 or len(r.content) < 500:
        return None
    im = Image.open(io.BytesIO(r.content)).convert("RGB")
    im.thumbnail((320, 320))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=75)
    return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")


def full_hd(c):
    """True for a clip or photo whose short side is at least 1080 px."""
    return min(int(c.get("w") or 0), int(c.get("h") or 0)) >= 1080


def choose(client, topic, scenes, pools, model=None, rule="", general=()):
    """``scenes``: [text] ``pools``: [[candidate]] per scene -> [candidate | None]
    per scene, decided by one vision call over all the thumbnails. ``general``:
    candidates for any scene (the channel's pool)."""
    import short_kit as kit
    flat, owner = [], []
    for k, pool in [*enumerate(pools), *((-1, [c]) for c in general)]:
        for c in pool:
            if c["id"] not in {f["id"] for f in flat} and c.get("thumb"):
                flat.append(c)
                owner.append(k)
    if not flat:
        return [None] * len(scenes)
    with ThreadPoolExecutor(max_workers=6) as ex:
        parts = list(ex.map(lambda c: _safe(_thumb_part, c["thumb"]), flat))
    keep = [k for k, p in enumerate(parts) if p is not None]
    flat, owner, parts = [flat[k] for k in keep], [owner[k] for k in keep], [parts[k] for k in keep]
    if not flat:
        return [None] * len(scenes)
    listing = "\n".join(f"{k}: {s[:200]}" for k, s in enumerate(scenes))
    clips = "\n".join(f"{k}: {'general' if owner[k] < 0 else f'searched for scene {owner[k]}'} ({c['kind']}"
                      f"{'' if c['kind'] != 'video' or full_hd(c) else ' 720p'}"
                      f"{', ' + c['alt'] if c.get('alt') else ''})"
                      for k, c in enumerate(flat))
    got = kit.ask_json(client, Choices, parts + [PICK_PROMPT.format(topic=topic, scenes=listing, n=len(flat),
                                                                    clips=clips, rule=rule)], model=model)
    out, used = [None] * len(scenes), set()
    for p in got.picks:
        if (0 <= p.scene < len(scenes) and 0 <= p.clip < len(flat) and p.clip not in used
                and out[p.scene] is None and p.fit >= MIN_FIT):
            out[p.scene] = flat[p.clip]
            used.add(p.clip)
    return out


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:  # noqa: BLE001 — one thumbnail less
        return None


# ------------------------------------------------------------------ download

def _valid(path, kind):
    if kind == "photo":
        try:
            from PIL import Image
            with Image.open(path) as im:
                im.verify()
            return True
        except Exception:  # noqa: BLE001
            return False
    # Decode the first two seconds: a truncated file fails here, not mid-render.
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-t", "2", "-i", path, "-f", "null", "-"],
                       capture_output=True, text=True, timeout=120)
    return r.returncode == 0 and not r.stderr.strip()


def _trim_cache():
    try:
        files = [os.path.join(CACHE_DIR, f) for f in os.listdir(CACHE_DIR) if not f.endswith(".part")]
    except OSError:
        return
    files.sort(key=os.path.getmtime)
    total = sum(os.path.getsize(f) for f in files)
    while files and total > CACHE_MAX_MB * 1024 * 1024:
        f = files.pop(0)
        total -= os.path.getsize(f)
        try:
            os.remove(f)
        except OSError:
            pass


def _flatten(path):
    """A see-through picture (a PNG cut-out saved under .jpg) rewritten as an opaque JPEG on a
    dark ground (short_kit.opaque); anything else is left alone. Never raises."""
    try:
        from PIL import Image
        import short_kit as kit
        with Image.open(path) as im:
            if not (im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info):
                return
            flat = kit.opaque(im)
        flat.save(path + ".tmp", "JPEG", quality=92)
        os.replace(path + ".tmp", path)
    except Exception:  # noqa: BLE001
        pass


def download(item):
    """Local path of a candidate (cached by URL), or None."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    ext = ".mp4" if item["kind"] == "video" else ".jpg"
    path = os.path.join(CACHE_DIR, hashlib.md5(item["url"].encode()).hexdigest() + ext)
    if os.path.isfile(path):
        os.utime(path)
        if item["kind"] == "photo":
            _flatten(path)    # cached before see-through pictures were flattened
        return path
    part = path + ".part"
    agent = _agent(item["url"])
    for attempt in range(3):
        try:
            with httpx.stream("GET", item["url"], headers={"User-Agent": agent}, timeout=60,
                              follow_redirects=True) as r:
                if r.status_code != 200:
                    raise httpx.HTTPError(f"status {r.status_code}")
                with open(part, "wb") as f:
                    for block in r.iter_bytes(1 << 20):
                        f.write(block)
            if _valid(part, item["kind"]):
                os.replace(part, path)
                if item["kind"] == "photo":
                    _flatten(path)
                _trim_cache()
                return path
        except (httpx.HTTPError, OSError, subprocess.SubprocessError):
            pass
        time.sleep(2 * (attempt + 1))
    if os.path.exists(part):
        os.remove(part)
    return None


# ------------------------------------------------------------------ the whole step

POOL_OFFER = 10      # pool clips shown to the picker beside each scene's own candidates


def for_scenes(client, topic, scenes, terms, portrait=True, photos=True, log=print, rule="", pool=None):
    """One footage clip (or photo) per scene: [{"path", "kind", ...candidate} | None].

    ``scenes``: what each scene says/shows; ``terms``: the stock search words
    for each (from the script). Videos first, full HD before 720p (a 720p clip
    only when too few full-HD ones came back); a scene with too few clips also
    gets photos. Clips used by any channel in the last USED_DAYS are skipped
    while there are others. ``pool``: the channel's checked footage (``pool()``):
    the picker sees the best of it for every scene, and a scene still without a
    clip gets one of it nobody used lately, before the Short falls back to its
    gradient."""
    if not available() or not scenes:
        return [None] * len(scenes)
    fresh = recently_used()
    def pool_for(term):
        found = search(term, portrait, "video")
        if photos and len(found) < 4:
            found += search(term, portrait, "photo")
        unused = [c for c in found if c["id"] not in fresh]
        return sorted(unused or found, key=lambda c: (c["kind"] != "video", not full_hd(c)))[:PER_SCENE]
    # Four searches at a time: one after another took 33 s for 7 lines.
    with ThreadPoolExecutor(max_workers=4) as ex:
        pools = list(ex.map(pool_for, terms))
    total = sum(len(p) for p in pools)
    spare = pool_order(pool or [])
    own = {c["id"] for p in pools for c in p}
    offer = [c for c in spare if c["id"] not in own][:POOL_OFFER]
    log(f"   🎞️ {total} free stock clips and photos found for {len(scenes)} scenes"
        + (f", {len(spare)} in the channel's pool." if spare else "."))
    try:
        chosen = (choose(client, topic, scenes, pools, rule=rule, general=offer) if offer
                  else choose(client, topic, scenes, pools, rule=rule))
    except Exception as e:  # noqa: BLE001 — unsure: take each scene's first result
        log(f"   ℹ️ Footage check failed ({type(e).__name__}); using the first result per scene.")
        chosen = [p[0] if p else None for p in pools]
    out = [None] * len(scenes)
    for attempt in range(2):         # a clip that will not download is replaced from the pool once
        taken = {c["id"] for c in chosen if c} | {c["id"] for c in out if c}
        spare = [c for c in spare if c["id"] not in taken]
        for k in range(len(scenes)):
            if out[k] is None and chosen[k] is None and spare:
                chosen[k] = spare.pop(0)
        with ThreadPoolExecutor(max_workers=4) as ex:
            paths = list(ex.map(lambda kc: download(kc[1]) if kc[1] and out[kc[0]] is None else None,
                                enumerate(chosen)))
        for k, (c, path) in enumerate(zip(chosen, paths)):
            if out[k] is None and c and path:
                out[k] = {**c, "path": path}
        chosen = [None] * len(scenes)
        if all(out) or not spare:
            break
    mark_used([c["id"] for c in out if c])
    in_pool = {c["id"] for c in pool or []}
    from_pool = sum(1 for c in out if c and c["id"] in in_pool)
    log(f"   ✅ {sum(1 for c in out if c)} of {len(scenes)} scenes have stock footage"
        + (f" ({from_pool} from the channel's pool)." if from_pool else "."))
    return out


# ------------------------------------------------------------------ the channel's pool

# Cricket stock is thin and the per-line searches are narrow ("bowler run up night"): on 29-oct-2026 a
# cricket Short found 43 candidates for 8 lines and none passed, and 40 of 46 cricket renders kept the
# plain gradient. So each kind with broad terms keeps a pool: the terms searched once a day (each search
# still goes through search(): its cache, the libraries' rests and daily caps), what they found kept
# POOL_DAYS, and every new clip tagged once by one vision call as the kind itself, neutral "atmosphere"
# that fits behind any of its stories, or "reject" (another sport, text, a face...).
POOL_FILE = os.path.join(ROOT, "output", ".stock_pool.json")
POOL_DAYS = 7
POOL_TERMS = {"cricket": ("cricket", "cricket match", "cricket ball", "cricket stadium", "cricket fans",
                          "street cricket", "cricket bat")}
POOL_WORDS = {"cricket": {
    "shows": "a cricket ground or pitch, players batting, bowling or fielding, a cricket bat, ball or stumps, "
             "a cricket crowd",
    "neutral": "stadium floodlights at night, a cheering crowd, a green grass field, a trophy, a scoreboard "
               "without readable text, a sunset over a ground",
    "never": "another sport's ground, game or gear (football, baseball, ice hockey, American football, basketball, "
             "tennis, golf, rugby; goal posts, a court, a diamond, yard lines); the insect called a cricket"}}
# Rejected before the vision check, by the library's own tags or file name: on the first real pool two
# "atmosphere" stadiums were tagged "football stadium, bundesliga" by Pixabay, and "cricket" finds the
# insect (29-oct-2026).
POOL_NEVER = {"cricket": re.compile(r"\b(football|soccer|bundesliga|fifa|uefa|baseball|softball|hockey|basketball|"
                                    r"nba|nfl|mlb|tennis|rugby|golf|volleyball|handball|badminton|insects?|bugs?|"
                                    r"grasshoppers?|locusts?|chirp\w*|cartoon|stickman|animation|illustration)\b",
                                    re.I)}
TAG_BATCH = 40


class PoolTag(BaseModel):
    clip: int
    tag: str


class PoolTags(BaseModel):
    tags: List[PoolTag]


TAG_PROMPT = """The {n} pictures above are thumbnails of free stock clips and photos found by searching for
"{kind}", numbered from 0 in that order, with the library's tags or file name:
{listing}

They may become backgrounds behind the text cards of a {kind} channel's Shorts, one clip behind any line,
whoever the line is about. Tag every picture:
- "{kind}": it plainly shows {kind}: {shows}.
- "atmosphere": no {kind} in it, but a neutral scene that fits behind any {kind} story: {neutral}.
- "reject": anything else. Always reject {never}; a painting, drawing, engraving or old print; readable
  text anywhere, a name or number on a shirt included (a fan's "TENDULKAR 10" passed once), a logo or a
  watermark; a national flag; a real person you could recognise: a named player in the tags or file
  name, or a face close enough to know (players far off and crowds are fine); anything sexual, violent
  or religious; a blurry or broken picture.
A stadium or crowd whose sport you cannot tell is atmosphere only when nothing in it, its tags or its
name belongs to another sport. When unsure, reject. Return one tag per picture."""


def tag_pool(client, kind, items, model=None):
    """{id: tag} for ``items`` from one vision call per TAG_BATCH thumbnails; a thumbnail that cannot
    be fetched is "reject" (nothing to check it by). Raises when the call fails: untagged clips wait
    for the next job."""
    import short_kit as kit
    words = POOL_WORDS[kind]
    out = {}
    for i in range(0, len(items), TAG_BATCH):
        batch = items[i:i + TAG_BATCH]
        with ThreadPoolExecutor(max_workers=6) as ex:
            parts = list(ex.map(lambda c: _safe(_thumb_part, c.get("thumb")) if c.get("thumb") else None, batch))
        keep = [(c, p) for c, p in zip(batch, parts) if p is not None]
        out.update({c["id"]: "reject" for c, p in zip(batch, parts) if p is None})
        if not keep:
            continue
        listing = "\n".join(f"{k}: {c['kind']}, {(c.get('alt') or '-')[:100]}" for k, (c, _p) in enumerate(keep))
        got = kit.ask_json(client, PoolTags, [p for _c, p in keep]
                           + [TAG_PROMPT.format(n=len(keep), kind=kind, listing=listing, **words)], model=model)
        for t in got.tags:
            if 0 <= t.clip < len(keep):
                tag = t.tag.strip().lower()
                out[keep[t.clip][0]["id"]] = tag if tag in (kind, "atmosphere") else "reject"
    return out


def pool(kind, client=None, log=print, portrait=True):
    """The checked footage of ``kind`` (POOL_TERMS): [candidate] tagged as the kind or "atmosphere",
    never a rejected one. Searches once a day, keeps what it found POOL_DAYS, tags new clips when a
    Gemini ``client`` is given. [] for a kind without terms, without keys, or on any failure."""
    terms = POOL_TERMS.get(kind or "")
    if not terms or not available():
        return []
    try:
        now, day = time.time(), time.strftime("%Y-%m-%d")
        with _lock:
            entry = _read(POOL_FILE, {}).get(kind) or {}
        items = {i: c for i, c in (entry.get("items") or {}).items() if now - c.get("at", 0) < POOL_DAYS * 86400}
        searched = entry.get("day") == day
        if not searched:
            never = POOL_NEVER.get(kind)
            for term in terms:
                # Photos for every term too: the first strict check kept 8 of 94 cricket videos (the
                # rest were insects, other sports or unrelated), and pool_order still puts videos first.
                got = search(term, portrait, "video", crop=True) + search(term, portrait, "photo")
                for c in got:
                    old = items.get(c["id"]) or {}
                    tag = old.get("tag") or ("reject" if never and never.search(c.get("alt") or "") else None)
                    items[c["id"]] = {**c, "at": now, "term": term, **({"tag": tag} if tag else {})}
        todo = [c for c in items.values() if not c.get("tag")]
        if todo and client is not None:
            try:
                for cid, tag in tag_pool(client, kind, todo).items():
                    items[cid]["tag"] = tag
                log(f"   🏷️ {len(todo)} new {kind} pool clips checked: "
                    f"{sum(1 for c in todo if items[c['id']].get('tag') == kind)} {kind}, "
                    f"{sum(1 for c in todo if items[c['id']].get('tag') == 'atmosphere')} atmosphere.")
            except Exception as e:  # noqa: BLE001 — checked next time
                log(f"   ℹ️ The {kind} pool check failed ({type(e).__name__}); trying again next job.")
        with _lock:
            data = _read(POOL_FILE, {})
            data[kind] = {"day": day, "items": items}
            _write(POOL_FILE, data)
        return [c for c in items.values() if c.get("tag") in (kind, "atmosphere")]
    except Exception as e:  # noqa: BLE001 — a pool is a bonus, never a failed Short
        log(f"   ℹ️ No {kind} pool this time ({type(e).__name__}).")
        return []


def pool_order(items, used=None):
    """Pool clips in the order to use them: used longest ago (never first), then the kind over
    atmosphere, video over photo, full HD over 720p. ``used``: {id: when} (USED_FILE)."""
    used = _read(USED_FILE, {}) if used is None else used
    return sorted(items, key=lambda c: (used.get(c["id"], 0), c.get("tag") == "atmosphere",
                                        c.get("kind") != "video", not full_hd(c)))


def credit_line(items):
    """The footage credit for the description: each library with the people
    who filmed or photographed it (Pexels asks for the name when possible), or ''."""
    by = {}
    for c in items:
        if c:
            names = by.setdefault(c["provider"], [])
            if c.get("author") and c["author"] not in names:
                names.append(c["author"])
    if not by:
        return ""
    parts = [f"{p} ({', '.join(n[:6])}{' and others' if len(n) > 6 else ''})" if n else p
             for p, n in sorted(by.items())]
    line = "Stock footage and photos (free licence): " + "; ".join(parts) + "."
    # CC BY / BY-SA pictures from Commons ask for the work, its author, the
    # licence and a link: one line each (public domain and CC0 need none).
    seen, files = set(), []
    for c in items:
        if (c and c.get("provider") == "Wikimedia Commons" and c.get("page") and c["page"] not in seen
                and not re.match(r"\s*(cc0|public domain|pd)", c.get("licence") or "", re.I)):
            seen.add(c["page"])
            files.append(f"- {c.get('alt') or 'picture'}: {c.get('author') or 'unknown'}, {c.get('licence')} ({c['page']})")
    return "\n".join([line] + files[:8])

