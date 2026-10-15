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

def _rendition(files, portrait):
    """The smallest file whose short side is at least 1080, else the largest
    of at least MIN_SHORT_SIDE: [(w, h, url)] -> (w, h, url) or None."""
    ok = [(w, h, u) for w, h, u in files if (h > w) == portrait and min(w, h) >= MIN_SHORT_SIDE]
    if not ok:
        return None
    full = [f for f in ok if min(f[0], f[1]) >= 1080]
    return min(full, key=lambda f: f[0] * f[1]) if full else max(ok, key=lambda f: f[0] * f[1])


def _pexels_videos(term, portrait, key):
    r = _get("https://api.pexels.com/v1/videos/search?" + urlencode(
        {"query": term, "per_page": 20, "orientation": "portrait" if portrait else "landscape"}),
        headers={"Authorization": key, "User-Agent": UA}, timeout=30)
    out = []
    for v in (r.json() or {}).get("videos") or [] if r.status_code == 200 else []:
        files = [(int(f.get("width") or 0), int(f.get("height") or 0), f.get("link"))
                 for f in v.get("video_files") or [] if f.get("link")]
        best = _rendition(files, portrait)
        if not best or not v.get("duration"):
            continue
        out.append({"id": f"pexels:v{v['id']}", "provider": "Pexels", "kind": "video", "url": best[2],
                    "w": best[0], "h": best[1], "seconds": float(v["duration"]), "thumb": v.get("image") or "",
                    "page": v.get("url") or "", "author": ((v.get("user") or {}).get("name") or "")[:60]})
    return out


def _pixabay_videos(term, portrait, key):
    r = _get("https://pixabay.com/api/videos/?" + urlencode(
        {"key": key, "q": term[:100], "per_page": 50, "safesearch": "true"}), headers={"User-Agent": UA}, timeout=30)
    out = []
    for v in (r.json() or {}).get("hits") or [] if r.status_code == 200 else []:
        sizes = v.get("videos") or {}
        files = [(int(f.get("width") or 0), int(f.get("height") or 0), f.get("url"))
                 for f in sizes.values() if isinstance(f, dict) and f.get("url")]
        best = _rendition(files, portrait)
        if not best or not v.get("duration"):
            continue
        thumb = next((f.get("thumbnail") for f in sizes.values() if isinstance(f, dict) and f.get("thumbnail")), "")
        out.append({"id": f"pixabay:v{v['id']}", "provider": "Pixabay", "kind": "video", "url": best[2],
                    "w": best[0], "h": best[1], "seconds": float(v["duration"]), "thumb": thumb,
                    "page": v.get("pageURL") or "", "author": (v.get("user") or "")[:60]})
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


def search(term, portrait=True, kind="video"):
    """Candidates for ``term`` from every library with a key, cached 24 h
    (an empty answer too, but only for an hour: it may be a hiccup)."""
    term = re.sub(r"\s+", " ", str(term or "")).strip()[:80]
    if not term:
        return []
    out = []
    for provider, key in keys().items():
        if not key or (provider, kind) not in SEARCHERS or _resting(provider):
            continue
        cache_key = f"{provider}|{kind}|{'p' if portrait else 'l'}|{term.lower()}"
        with _lock:
            hit = _read(SEARCH_FILE, {}).get(cache_key)
        if hit and time.time() - hit["at"] < (SEARCH_TTL if hit["items"] else 3600):
            out += hit["items"]
            continue
        try:
            items = SEARCHERS[(provider, kind)](term, portrait, key)
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
related or generic (a texture, an unrelated object). Prefer moving footage (video) when it fits as well. The
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


def choose(client, topic, scenes, pools, model=None, rule=""):
    """``scenes``: [text] ``pools``: [[candidate]] per scene -> [candidate | None]
    per scene, decided by one vision call over all the thumbnails."""
    import short_kit as kit
    flat, owner = [], []
    for k, pool in enumerate(pools):
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
    clips = "\n".join(f"{k}: searched for scene {owner[k]} ({c['kind']}{', ' + c['alt'] if c.get('alt') else ''})"
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


def download(item):
    """Local path of a candidate (cached by URL), or None."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    ext = ".mp4" if item["kind"] == "video" else ".jpg"
    path = os.path.join(CACHE_DIR, hashlib.md5(item["url"].encode()).hexdigest() + ext)
    if os.path.isfile(path):
        os.utime(path)
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
                _trim_cache()
                return path
        except (httpx.HTTPError, OSError, subprocess.SubprocessError):
            pass
        time.sleep(2 * (attempt + 1))
    if os.path.exists(part):
        os.remove(part)
    return None


# ------------------------------------------------------------------ the whole step

def for_scenes(client, topic, scenes, terms, portrait=True, photos=True, log=print, rule=""):
    """One footage clip (or photo) per scene: [{"path", "kind", ...candidate} | None].

    ``scenes``: what each scene says/shows; ``terms``: the stock search words
    for each (from the script). Videos first; a scene with too few clips also
    gets photos. Clips used by any channel in the last USED_DAYS are skipped
    while there are others."""
    if not available() or not scenes:
        return [None] * len(scenes)
    fresh = recently_used()
    def pool_for(term):
        found = search(term, portrait, "video")
        if photos and len(found) < 4:
            found += search(term, portrait, "photo")
        unused = [c for c in found if c["id"] not in fresh]
        return (unused or found)[:PER_SCENE]
    # Four searches at a time: one after another took 33 s for 7 lines.
    with ThreadPoolExecutor(max_workers=4) as ex:
        pools = list(ex.map(pool_for, terms))
    total = sum(len(p) for p in pools)
    log(f"   🎞️ {total} free stock clips and photos found for {len(scenes)} scenes.")
    try:
        chosen = choose(client, topic, scenes, pools, rule=rule)
    except Exception as e:  # noqa: BLE001 — unsure: take each scene's first result
        log(f"   ℹ️ Footage check failed ({type(e).__name__}); using the first result per scene.")
        chosen = [p[0] if p else None for p in pools]
    out = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        paths = list(ex.map(lambda c: download(c) if c else None, chosen))
    for c, path in zip(chosen, paths):
        out.append({**c, "path": path} if c and path else None)
    mark_used([c["id"] for c in out if c])
    log(f"   ✅ {sum(1 for c in out if c)} of {len(scenes)} scenes have stock footage.")
    return out


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

