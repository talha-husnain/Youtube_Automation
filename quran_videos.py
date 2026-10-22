"""Quran recitation videos with translation for the Quran channel
(CONTENT_GENRE=quran; owner, 22-oct-2026: 2-5 minute videos, holy visuals,
Arabic with Urdu or English translation).

Nothing in the Quran itself comes from a model. The recitation is a real
qari's (per-ayah recordings from Quran.com), the Arabic is the published
Uthmani text, and the translations are published ones, all from the Quran
Foundation API (api.quran.com v4), whose developer terms allow use in social
videos with credit (api-docs.quran.foundation/legal/developer-terms,
11-oct-2026). Why not an AI recitation: Egypt's Dar al-Ifta (fatwa 8874,
18-jan-2026) accepts one only if it follows tajweed and is reviewed in full
by the Mushaf authority, which an automated channel cannot get, and a wrong
vowel changes the meaning. The AI voice reads only the TRANSLATION, after
each ayah (the free Microsoft Urdu voice, Gemini when it fails), and the
description says so. No music, ever (Dar al-Ifta and Al-Azhar: reciting with
music is forbidden by consensus, Sep 2024).

Translations: Urdu by Maulana Muhammad Junagarhi (died 1941: public domain
in Pakistan, life + 50 years) by default, or Fateh Muhammad Jalandhari (the
most used one; its copyright status was not confirmed, 22-oct-2026);
English by Marmaduke Pickthall (1930, public domain). Tanzil's own files say
"non-commercial only", which is why the text does not come from them.

One video: a passage of 2-5 minutes planned by plan_next() (whole ayat,
ending on a ruku where it can; short surahs share a video), a title card,
per ayah the recitation then its translation read out, the Arabic in Amiri
Quran and the translation in Noto Nastaliq Urdu / Noto Serif (OFL fonts in
fonts/), long ayat paged at their pause marks; free nature and mosque
footage with no people (one vision call picks it); the translations as
caption tracks; a thumbnail drawn by libass (the only shaper here that joins
Arabic letters). Env: QURAN_PLAN (JSON: segments, reciter, urdu, english,
screen, voice).
"""
import json
import math
import os
import random
import re
import subprocess
import threading
import time
import unicodedata
import wave
from concurrent.futures import ThreadPoolExecutor

import httpx

import framed_layout as fl
import short_kit as kit
from ffmpeg_utils import LOUDNORM_FILTER, METADATA_SCRUB, escape_filter_value

W, H, FPS = 1920, 1080, 30
RATE = 48000
API = os.environ.get("QURAN_API") or "https://api.quran.com/api/v4"
AUDIO_BASE = "https://verses.quran.com/"
ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(ROOT, "output", "quran_cache")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Shortkaar/1.0"

RECITERS = {7: "Mishary Rashid Alafasy", 2: "Abdul Basit Abdul Samad", 6: "Mahmoud Khalil Al-Husary",
            9: "Mohamed Siddiq Al-Minshawi", 3: "Abdur-Rahman As-Sudais", 4: "Abu Bakr Al-Shatri",
            5: "Hani Ar-Rifai", 10: "Saud Ash-Shuraim"}
RECITER_SHORT = {7: "Mishary Alafasy", 2: "Abdul Basit", 6: "Al-Husary", 9: "Al-Minshawi", 3: "As-Sudais",
                 4: "Al-Shatri", 5: "Ar-Rifai", 10: "Ash-Shuraim"}
URDU = {54: "Maulana Muhammad Junagarhi", 234: "Fateh Muhammad Jalandhari"}
ENGLISH = {19: "Marmaduke Pickthall"}
DEFAULTS = {"reciter": 7, "urdu": 54, "english": 19, "screen": "both", "voice": "urdu"}
SCREENS = ("both", "urdu", "english")
VOICES = ("urdu", "english", "off")
EDGE_VOICE = {"urdu": "ur-PK-AsadNeural", "english": "en-US-GuyNeural"}
VOICE_RATE = "-5%"
GEMINI_VOICE = "Charon"
VOICE_STYLE = "Read this translation of the Quran slowly, calmly and respectfully, like a gentle narrator."
WORDS_PER_SECOND = {"urdu": 2.3, "english": 2.6}     # the edge voices at -5%, for planning only
MIN_SECONDS, TARGET_SECONDS, MAX_SECONDS = 120, 225, 300
INTRO, OUTRO = 2.5, 3.5
AFTER_RECITE, AFTER_AYAH = 0.5, 0.8
SHOT_SECONDS = 12.0
BISMILLAH = (1, 1)

# Most searched first (the biggest Urdu Quran videos are Ya-Sin, Ar-Rahman,
# Al-Mulk, Al-Waqi'ah: channel research 22-oct-2026), then the whole Quran in order.
POPULAR = [(1,), (36,), (55,), (67,), (56,), (2, 255, 255), (2, 285, 286), (18,), (112,), (113,), (114,),
           (93,), (94,), (73,), (78,), (97,), (103,), (108,), (109,), (110,), (111,), (105,), (106,), (107,),
           (99,), (100,), (101,), (102,), (32,), (48,), (62,), (44,), (71,), (76,), (87,), (89,), (90,),
           (91,), (92,), (95,), (96,), (104,)]
SPECIAL = {(2, 255, 255): "Ayat ul Kursi", (2, 285, 286): "Surah Al-Baqarah ki Aakhri 2 Ayat"}
# Their own Arabic names on the title card and thumbnail, instead of the surah's.
SPECIAL_ARABIC = {(2, 255, 255): "آية الكرسي", (2, 285, 286): "خواتيم سورة البقرة"}
ALIASES = {"fatiha": 1, "fateha": 1, "baqara": 2, "baqarah": 2, "imran": 3, "nisa": 4, "maida": 5, "maidah": 5,
           "anam": 6, "kahf": 18, "kahaf": 18, "maryam": 19, "taha": 20, "noor": 24, "nur": 24, "yaseen": 36,
           "yasin": 36, "yaseeen": 36, "rahman": 55, "rehman": 55, "waqia": 56, "waqiah": 56, "waqiya": 56,
           "mulk": 67, "muzammil": 73, "muzzammil": 73, "naba": 78, "jumma": 62, "juma": 62, "jumuah": 62,
           "fath": 48, "hashr": 59, "sajda": 32, "sajdah": 32, "dukhan": 44, "insan": 76, "dahr": 76,
           "duha": 93, "zuha": 93, "inshirah": 94, "alamnashrah": 94, "qadr": 97, "qadar": 97, "kausar": 108,
           "kawthar": 108, "kafirun": 109, "kafiroon": 109, "asr": 103, "ikhlas": 112, "falaq": 113,
           "nas": 114, "naas": 114, "yusuf": 12, "ibrahim": 14, "luqman": 31, "hujurat": 49, "tin": 95,
           "teen": 95, "zilzal": 99, "zalzala": 99, "takasur": 102, "takathur": 102, "humaza": 104, "fil": 105,
           "feel": 105, "quraish": 106, "quraysh": 106, "maun": 107, "nasr": 110, "lahab": 111, "masad": 111}
KURSI = re.compile(r"kurs[iy]", re.I)

# No night skies: under the darkening they read as black, and video_qa refused
# the first test video for 12 s of a starry sky (22-oct-2026).
FOOTAGE_TERMS = ["clouds timelapse", "sunset sky clouds", "blue sky clouds", "ocean waves", "calm sea sunset",
                 "mountains aerial", "green valley mountains", "forest sunlight", "waterfall", "desert dunes",
                 "sunrise landscape", "rain drops leaves", "river nature", "flowers garden", "lake reflection",
                 "snowy mountains", "mosque", "mosque dome", "minaret", "islamic architecture"]
FOOTAGE_RULE = ("This is the background of a Quran recitation video: calm, beautiful, respectful. Nature (sky, "
                "clouds, sea, mountains, forests, rivers, rain, desert, stars, sunrise) or mosques and Islamic "
                "architecture. Score 0 for: ANY person or face (even far away, a silhouette or a hand), animals, "
                "statues, churches, temples, crosses or symbols of other religions, text, logos, watermarks, "
                "cars, roads, phones, screens, city streets, parties, alcohol, fire, anything scary, and dark or "
                "night footage (it turns black under the text).")
# The biggest Urdu Quran videos say it in English ("Surah Yasin | Surat Yaseen with Urdu
# Translation | Quran Tilawat Beautiful Voice", 84M views; yt-dlp search, 22-oct-2026).
TITLE_WORDS = {"urdu": "with Urdu Translation", "english": "with English Translation"}
TITLE_TAIL = "Beautiful Tilawat"
# How those searches spell the surahs (Quran.com says "Ya-Sin", "Ar-Rahman", "Al-Mulk").
SEARCH_NAMES = {1: "Fatiha", 2: "Baqarah", 3: "Al-Imran", 12: "Yusuf", 18: "Kahf", 19: "Maryam", 20: "Taha",
                24: "Noor", 32: "Sajdah", 36: "Yaseen", 44: "Dukhan", 48: "Fatah", 55: "Rahman", 56: "Waqiah",
                62: "Jumma", 67: "Mulk", 71: "Nooh", 73: "Muzammil", 76: "Dahr", 78: "Naba", 87: "Aala",
                89: "Fajr", 90: "Balad", 91: "Shams", 92: "Lail", 93: "Duha", 94: "Alam Nashrah", 95: "Teen",
                96: "Alaq", 97: "Qadr", 99: "Zilzal", 100: "Adiyat", 101: "Qariah", 102: "Takasur", 103: "Asr",
                104: "Humazah", 105: "Feel", 106: "Quraish", 107: "Maun", 108: "Kausar", 109: "Kafiroon",
                110: "Nasr", 111: "Lahab", 112: "Ikhlas", 113: "Falaq", 114: "Naas"}
FOLLOW = {"urdu": "Roz nayi tilawat, Urdu tarjume ke saath: subscribe karein",
          "english": "A new recitation with translation every day: subscribe"}

_lock = threading.Lock()          # the durations file
_fetch = threading.RLock()        # one download of a surah's text or audio list at a time


# ------------------------------------------------------------------ data (cached for good: it never changes)

def _cache(name):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, name)


def _read(name):
    try:
        with open(_cache(name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write(name, data):
    path = _cache(name)
    tmp = f"{path}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    for attempt in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            # Windows: another thread is reading or replacing the same file (busy, not damage).
            time.sleep(0.1 * (attempt + 1))
    os.replace(tmp, path)


def _get(path, params=None, tries=3):
    last = None
    for attempt in range(tries):
        try:
            r = httpx.get(f"{API}{path}", params=params, headers={"User-Agent": UA}, timeout=30)
            if r.status_code == 200:
                return r.json()
            last = f"status {r.status_code}"
        except httpx.HTTPError as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(2 * (attempt + 1))
    # "network" is what my_channels.TRANSIENT reads: the channel waits, the try is not used.
    raise RuntimeError(f"Quran.com could not be reached (network: {str(last)[:120]}); made again later.")


def chapters():
    data = _read("chapters.json")
    if data:
        return data
    with _fetch:
        data = _read("chapters.json")
        if data:
            return data
        data = {str(c["id"]): {"n": c["id"], "name": c["name_simple"], "arabic": c["name_arabic"],
                               "meaning": (c.get("translated_name") or {}).get("name", ""),
                               "ayat": c["verses_count"], "bismillah": bool(c.get("bismillah_pre"))}
                for c in _get("/chapters", {"language": "en"})["chapters"]}
        _write("chapters.json", data)
    return data


# Quran.com's spellings that Pakistani searches write without the doubled vowel.
NAME_FIX = {"Ad-Duhaa": "Ad-Duha", "Ash-Shuraa": "Ash-Shura"}


def chapter(s):
    c = chapters()[str(int(s))]
    return {**c, "name": NAME_FIX.get(c["name"], c["name"])}


_TAGS = re.compile(r"<sup[^>]*>.*?</sup>|<[^>]+>", re.S)


def _plain_forms(text):
    """Arabic presentation forms as the plain letters: Junagarhi's text writes
    "والا" with the ready-joined U+FEFB, which Noto Nastaliq does not have (a
    fallback font drew a big "لا" in every line, 22-oct-2026)."""
    return "".join(unicodedata.normalize("NFKC", ch) if 0xFB50 <= ord(ch) <= 0xFDFF or 0xFE70 <= ord(ch) <= 0xFEFF
                   else ch for ch in text or "")


def clean_translation(text):
    """A translation without its footnote numbers and markup."""
    text = _plain_forms(_TAGS.sub("", text or "").replace("&nbsp;", " ").replace("\ufeff", ""))
    return re.sub(r"\s+", " ", text).strip()


def verses(s, urdu=DEFAULTS["urdu"], english=DEFAULTS["english"]):
    """[{"n", "key", "ar", "ur", "en", "ruku", "sajda"}] of surah ``s``."""
    name = f"text_{int(s)}_{int(urdu)}_{int(english)}.json"
    rows = _read(name)
    if not rows:
        with _fetch:
            rows = _read(name) or _fetch_verses(s, urdu, english, name)
    # Files cached before _plain_forms existed are cleaned as they are read.
    return [{**r, "ur": _plain_forms(r["ur"]), "en": _plain_forms(r["en"])} for r in rows]


def _fetch_verses(s, urdu, english, name):
    rows, page = [], 1
    while page:
        got = _get(f"/verses/by_chapter/{int(s)}", {"fields": "text_uthmani", "translations": f"{urdu},{english}",
                                                     "per_page": 50, "page": page, "words": "false"})
        for v in got["verses"]:
            tr = {t["resource_id"]: clean_translation(t["text"]) for t in v.get("translations") or []}
            rows.append({"n": v["verse_number"], "key": v["verse_key"],
                         "ar": (v.get("text_uthmani") or "").replace("\ufeff", "").strip(),
                         "ur": tr.get(int(urdu), ""), "en": tr.get(int(english), ""),
                         "ruku": v.get("ruku_number"), "sajda": bool(v.get("sajdah_number"))})
        page = (got.get("pagination") or {}).get("next_page")
    if len(rows) != chapter(s)["ayat"] or not all(r["ar"] for r in rows):
        raise RuntimeError(f"Quran.com sent {len(rows)} ayat of surah {s} (network: an incomplete answer); "
                           "made again later.")
    _write(name, rows)
    return rows


def audio_urls(reciter, s):
    name = f"audio_{int(reciter)}_{int(s)}.json"
    urls = _read(name)
    if urls:
        return urls
    with _fetch:
        return _read(name) or _fetch_audio_urls(reciter, s, name)


def _fetch_audio_urls(reciter, s, name):
    urls, page = {}, 1
    while page:
        got = _get(f"/recitations/{int(reciter)}/by_chapter/{int(s)}", {"per_page": 50, "page": page})
        for f in got["audio_files"]:
            u = f["url"]
            urls[f["verse_key"]] = ("https:" + u if u.startswith("//") else u if u.startswith("http")
                                    else AUDIO_BASE + u.lstrip("/"))
        page = (got.get("pagination") or {}).get("next_page")
    _write(name, urls)
    return urls


def audio_file(reciter, key):
    """The recitation of ayah ``key`` ("36:1") as a local mp3 (cached)."""
    s = int(key.split(":")[0])
    path = _cache(os.path.join("audio", str(int(reciter)), key.replace(":", "_") + ".mp3"))
    if os.path.isfile(path) and os.path.getsize(path) > 1000:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    url = audio_urls(reciter, s).get(key)
    if not url:
        raise RuntimeError(f"No recitation of {key} on Quran.com for this qari.")
    last = None
    for attempt in range(3):
        try:
            r = httpx.get(url, headers={"User-Agent": UA}, timeout=60, follow_redirects=True)
            if r.status_code == 200 and len(r.content) > 1000:
                with open(path + ".part", "wb") as f:
                    f.write(r.content)
                os.replace(path + ".part", path)
                return path
            last = f"status {r.status_code}"
        except httpx.HTTPError as e:
            last = type(e).__name__
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"The recitation of {key} could not be downloaded (network: {last}); made again later.")


def seconds_of(path):
    rel = os.path.relpath(path, CACHE_DIR)
    with _lock:
        known = _read("durations.json") or {}
    if rel in known:
        return known[rel]
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1",
                        path], capture_output=True, text=True, timeout=60)
    secs = round(float(r.stdout.strip() or 0), 3)
    with _lock:
        known = _read("durations.json") or {}
        known[rel] = secs
        _write("durations.json", known)
    return secs


def prefetch(reciter, keys):
    for s in sorted({int(k.split(":")[0]) for k in keys}):
        audio_urls(reciter, s)            # the list once, before six threads want it
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda k: seconds_of(audio_file(reciter, k)), keys))


# ------------------------------------------------------------------ what comes next

def settings_of(raw):
    raw = raw or {}
    out = dict(DEFAULTS)
    for k, allowed in (("reciter", RECITERS), ("urdu", URDU), ("english", ENGLISH)):
        try:
            if int(raw.get(k)) in allowed:
                out[k] = int(raw[k])
        except (TypeError, ValueError):
            pass
    if raw.get("screen") in SCREENS:
        out["screen"] = raw["screen"]
    if raw.get("voice") in VOICES:
        out["voice"] = raw["voice"]
    return out


def display_name(s):
    """"Surah Yaseen": the spelling people search for, else Quran.com's own."""
    return f"Surah {SEARCH_NAMES.get(int(s)) or chapter(s)['name']}"


def short_name(s):
    return SEARCH_NAMES.get(int(s)) or chapter(s)["name"]


def label(s, a, b):
    if (s, a, b) in SPECIAL:
        return SPECIAL[(s, a, b)]
    whole = a == 1 and b == chapter(s)["ayat"]
    return display_name(s) if whole else f"{display_name(s)}, Ayat {a}-{b}" if a != b else \
        f"{display_name(s)}, Ayat {a}"


def idea(s, a=None, b=None, owner=False):
    a, b = a or 1, b or chapter(s)["ayat"]
    return {"kind": "quran", "surah": int(s), "from": int(a), "to": int(b), "text": label(s, a, b),
            "id": f"{s}" if (a == 1 and b == chapter(s)["ayat"]) else f"{s}:{a}-{b}",
            **({"owner": True} if owner else {})}


def queue(done=()):
    """The default order as ideas, without the ones already made."""
    done = set(done)
    out, seen = [], set()
    for item in POPULAR + [(s,) for s in range(1, 115)]:
        i = idea(*item)
        if i["id"] not in done and i["id"] not in seen:
            seen.add(i["id"])
            out.append(i)
    return out


def _bare(text):
    return re.sub(r"[^a-z]", "", text.lower())


def _name_key(name):
    """"Ar-Rahman" -> "rahman": the article goes, so "Surah Rahman" finds it."""
    parts = name.lower().split("-")
    if len(parts) > 1 and re.fullmatch(r"a[lrnstdzh]{1,2}h?", parts[0]):
        parts = parts[1:]
    return _bare("".join(parts))


def parse_request(text):
    """The owner's "Surah Yaseen", "36", "2:255", "2:1-20" or "Ayat ul Kursi" as an idea, or None."""
    t = (text or "").strip()
    m = re.fullmatch(r"(\d{1,3})\s*[:.]\s*(\d{1,3})(?:\s*[-to]+\s*(\d{1,3}))?", t)
    if m:
        s, a = int(m.group(1)), int(m.group(2))
        b = int(m.group(3) or a)
        if 1 <= s <= 114 and 1 <= a <= b <= chapter(s)["ayat"]:
            return idea(s, a, b, owner=True)
        return None
    if re.fullmatch(r"\d{1,3}", t) and 1 <= int(t) <= 114:
        return idea(int(t), owner=True)
    if KURSI.search(t):
        return idea(2, 255, 255, owner=True)
    key = _bare(re.sub(r"\b(surah?|surat|soorah?|sura)\b", " ", t, flags=re.I))
    key = re.sub(r"^(al|ar|an|as|at|ad|az|ash)(?=[a-z]{3,})", "", key) if key not in ALIASES else key
    if key in ALIASES:
        return idea(ALIASES[key], owner=True)
    for c in chapters().values():
        if key and key in (_name_key(c["name"]), _bare(c["name"]), _bare(c["meaning"])):
            return idea(c["n"], owner=True)
    return None


def _speakable(text):
    return re.sub(r"\s+", " ", re.sub(r"[()\[\]{}«»\"]", " ", text or "")).strip()


def ayah_cost(s, n, settings, rows=None):
    """Seconds one ayah takes in the video: its recitation, then its translation read out."""
    r = seconds_of(audio_file(settings["reciter"], f"{s}:{n}"))
    if settings["voice"] == "off":
        return r + AFTER_AYAH
    rows = rows or verses(s, settings["urdu"], settings["english"])
    words = len(_speakable(rows[n - 1]["ur" if settings["voice"] == "urdu" else "en"]).split())
    return r + AFTER_RECITE + words / WORDS_PER_SECOND[settings["voice"]] + AFTER_AYAH


def opening_cost(s, a, settings):
    if a != 1 or not chapter(s)["bismillah"]:
        return 0.0
    return ayah_cost(*BISMILLAH, settings, verses(1, settings["urdu"], settings["english"]))


def plan_next(ideas, settings, cost_fn=None, open_fn=None, rukus_fn=None):
    """(passage, ideas left) for the next video. passage: {"segments": [[surah,
    from, to], ...], "seconds", "part"} or None. Whole ayat, about
    TARGET_SECONDS, at most MAX_SECONDS, ending on a ruku when one ends after
    the target; a short whole surah takes the next whole surahs along until
    MIN_SECONDS. ``part`` numbers the videos of a surah that takes several."""
    settings = settings_of(settings)
    real = cost_fn is None
    cost_fn = cost_fn or (lambda s, n: ayah_cost(s, n, settings))
    open_fn = open_fn or (lambda s, a: opening_cost(s, a, settings))
    rukus_fn = rukus_fn or (lambda s: [r["ruku"] for r in verses(s, settings["urdu"], settings["english"])])
    ideas = [dict(i) for i in ideas or []]
    segs, total, part = [], 0.0, None
    while ideas:
        it = ideas[0]
        s, a, b = int(it["surah"]), int(it["from"]), int(it["to"])
        whole = a == 1 and b == chapter(s)["ayat"]
        if segs and not whole:
            break                      # only whole surahs share a video
        if real and not segs:
            # About a video's worth of recitations at once (each file is ~100 KB).
            prefetch(settings["reciter"], [f"{s}:{n}" for n in range(a, min(b, a + 40) + 1)])
        rukus = rukus_fn(s)
        t, n = open_fn(s, a), a
        while n <= b:
            c = cost_fn(s, n)
            if (segs or n > a) and total + t + c > MAX_SECONDS:
                break
            t += c
            n += 1
            if total + t >= MAX_SECONDS:
                break
            if total + t >= TARGET_SECONDS and n <= b and rukus and rukus[n - 1] != rukus[n - 2]:
                break                  # a ruku (a passage of the surah) ends here
        if n == a or (segs and n <= b):
            break                      # a whole surah that does not fit waits for the next video
        segs.append([s, a, n - 1])
        total += t
        if len(segs) == 1 and (s, a, b) not in SPECIAL and not (a == 1 and n - 1 == chapter(s)["ayat"]):
            part = int(it.get("part") or 1)          # this video is one part of a longer surah
        if n > b:
            ideas.pop(0)
        else:
            ideas[0] = {**it, "from": n, "text": label(s, n, b), "part": int(it.get("part") or 1) + 1}
            break
        if total >= MIN_SECONDS:
            break
    return ({"segments": segs, "seconds": round(total, 1), "part": part} if segs else None), ideas


# ------------------------------------------------------------------ text on screen

_ARABIC_LETTER = re.compile(r"[\u0621-\u064A\u0671-\u06D3\u06FA-\u06FF]")
_WAQF = re.compile(r"[\u06D6-\u06DC]")
AR_PAGE = 80                 # Arabic letters on one screen (2-3 lines at 94-124 px)
TR_PAGE = {"ur": 150, "en": 150}


def letters(text):
    return len(_ARABIC_LETTER.findall(text or ""))


def arabic_digits(n):
    return "".join(chr(0x660 + int(c)) for c in str(n))


def arabic_pages(text, limit=AR_PAGE):
    """The ayah in screens of at most ``limit`` letters, cut after a pause mark
    (waqf) where there is one, else between words."""
    tokens = text.split()
    pages, cur, last_waqf = [], [], -1
    for tok in tokens:
        cur.append(tok)
        if _WAQF.search(tok):
            last_waqf = len(cur)
        if letters(" ".join(cur)) > limit and len(cur) > 1:
            cut = last_waqf if 0 < last_waqf < len(cur) else len(cur) - 1
            pages.append(" ".join(cur[:cut]))
            cur, last_waqf = cur[cut:], -1
            for k, t in enumerate(cur):
                if _WAQF.search(t):
                    last_waqf = k + 1
    if cur:
        if pages and letters(" ".join(cur)) < 12 and all(_WAQF.search(t) or not letters(t) for t in cur):
            pages[-1] += " " + " ".join(cur)          # a lone pause mark joins the page before
        else:
            pages.append(" ".join(cur))
    return pages or [text]


def split_words(text, shares):
    """``text`` in len(shares) parts of about those shares of its words, cut
    after punctuation when one is within two words. Too few words to share:
    all of it with the first part."""
    words = text.split()
    if len(shares) == 1:
        return [text]
    if len(words) < 2 * len(shares):
        return [text] + [""] * (len(shares) - 1)
    out, start, acc = [], 0, 0.0
    total = sum(shares)
    for k, sh in enumerate(shares[:-1]):
        acc += sh / total
        cut = max(start + 1, min(len(words) - (len(shares) - k - 1), round(acc * len(words))))
        for d in (0, 1, -1, 2, -2):
            c = cut + d
            if start < c < len(words) and re.search(r"[,.;:!?،۔؛]$", words[c - 1]):
                cut = c
                break
        out.append(" ".join(words[start:cut]))
        start = cut
    out.append(" ".join(words[start:]))
    return out


def pages_of(unit, screen):
    """[(arabic, urdu, english)] screens for one ayah."""
    ar = arabic_pages(unit["ar"])
    need = len(ar)
    ur = unit["ur"] if screen in ("both", "urdu") else ""
    en = unit["en"] if screen in ("both", "english") else ""
    need = max(need, math.ceil(len(ur) / TR_PAGE["ur"]) if ur else 1, math.ceil(len(en) / TR_PAGE["en"]) if en else 1)
    if need > len(ar):
        ar = arabic_pages(unit["ar"], max(20, math.ceil(letters(unit["ar"]) / need) + 4))
    shares = [max(1, letters(p)) for p in ar]
    urs = split_words(ur, shares) if ur else [""] * len(ar)
    ens = split_words(en, shares) if en else [""] * len(ar)
    return list(zip(ar, urs, ens))


def _esc(text):
    return (text or "").replace("\\", " ").replace("{", "(").replace("}", ")").replace("\n", " ")


def _style(name, font, size, colour, outline=2, shadow=2, margin=140, bold=0, align=5, box=None):
    """An ASS style; ``box``: a filled box of that colour behind the text (BorderStyle 3)."""
    c = fl._ass_colour(colour)
    edge = fl._ass_colour(box) if box else "&H00000000"
    return (f"Style: {name},{font},{size},{c},{c},{edge},&H96000000,{bold},0,0,0,100,100,0,0,{3 if box else 1},"
            f"{outline},{shadow},{align},{margin},{margin},0,1")


def styles():
    # Sizes from the first renders (22-oct-2026): both fonts draw small for their size
    # (libass sizes a line by the font's height, and Noto Nastaliq's is huge): Nastaliq at
    # 120 looks like Arial at 45, so 128 is the Urdu that reads like the 40 px English.
    return [_style("QAr", "Amiri Quran", 128, "#F6E7B0", outline=2, shadow=3),
            _style("QArBig", "Amiri Quran", 190, fl.GOLD, outline=2, shadow=4),
            _style("QOrn", "Amiri Quran", 140, fl.GOLD, outline=1, shadow=2),
            # Noto Serif has no Arabic-Indic digits; Amiri does.
            _style("QNum", "Amiri Quran", 46, fl.GOLD, outline=1, shadow=1),
            _style("QUr", "Noto Nastaliq Urdu", 128, "#FFFFFF", outline=2, shadow=2, margin=170),
            _style("QUrOnly", "Noto Nastaliq Urdu", 150, "#FFFFFF", outline=2, shadow=2, margin=170),
            _style("QEn", "Noto Serif Bold", 40, "#E8E8E8", outline=2, shadow=2, margin=200, bold=1),
            _style("QEnOnly", "Noto Serif Bold", 50, "#FFFFFF", outline=2, shadow=2, margin=180, bold=1),
            _style("QHead", "Montserrat ExtraBold", 34, fl.GOLD, outline=0, shadow=2, margin=70, bold=1),
            _style("QSmall", "Montserrat ExtraBold", 26, "#FFFFFF", outline=0, shadow=2, margin=70, bold=1),
            _style("QTitle", "Montserrat ExtraBold", 64, "#FFFFFF", outline=0, shadow=3, bold=1),
            _style("QPill", "Montserrat ExtraBold", 34, fl.GOLD, outline=0, shadow=2, bold=1)]


def _ass(events, w=W, h=H, style_lines=None):
    head = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 0",
            "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding", *(style_lines or styles()), "", "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    return "\n".join(head + list(events)) + "\n"


def _at(layer, t0, t1, style, x, y, text, an=5, fade=(220, 220), extra=""):
    return kit.dialogue(layer, t0, t1, style, rf"{{\an{an}\pos({x},{y})\fad({fade[0]},{fade[1]}){extra}}}{_esc(text)}")


def page_events(t0, t1, page, number, screen):
    """One screen: the Arabic (growing up from y=560), the ayah's number in
    its ornament, then the translation(s) under it."""
    ar, ur, en = page
    size = 150 if letters(ar) <= 40 else 128 if letters(ar) <= 65 else 112
    ev = [_at(3, t0, t1, "QAr", W // 2, 545 if screen == "both" else 590, ar, an=2, extra=rf"\fs{size}")]
    if number:
        y = 610 if screen == "both" else 655
        ev += [_at(2, t0, t1, "QOrn", W // 2, y, "\u06DD"), _at(4, t0, t1, "QNum", W // 2, y + 6, arabic_digits(number))]
    if screen == "both":
        if ur:
            ev.append(_at(3, t0, t1, "QUr", W // 2, 668, ur, an=8))
        if en:
            ev.append(_at(3, t0, t1, "QEn", W // 2, 1048, en, an=2))
    elif screen == "urdu" and ur:
        ev.append(_at(3, t0, t1, "QUrOnly", W // 2, 710, ur, an=8))
    elif screen == "english" and en:
        ev.append(_at(3, t0, t1, "QEnOnly", W // 2, 710, en, an=8))
    return ev


def spans(t0, length, weights):
    """Back-to-back (start, end) windows over [t0, t0+length] by ``weights``."""
    total = sum(weights) or 1
    out, t = [], t0
    for w in weights:
        d = length * w / total
        out.append((t, t + d))
        t += d
    return out


def voice_spans(t0, length, pages_words, words_file):
    """Windows of each page while its translation is read: the voice's own
    word times when it reported one per word, else by word count."""
    counts = [max(1, n) for n in pages_words]
    try:
        with open(words_file, encoding="utf-8") as f:
            times = json.load(f)
    except (OSError, ValueError):
        times = []
    if len(times) == sum(pages_words) and len(counts) > 1:
        out, k = [], 0
        for j, n in enumerate(pages_words):
            start = t0 + (times[k][1] if j else 0.0)
            k += n
            end = t0 + (times[k][1] if k < len(times) else length)
            out.append((start, end))
        return out
    return spans(t0, length, counts)


# ------------------------------------------------------------------ sound

def pcm(path):
    """The file as 48 kHz mono 16-bit samples (bytes)."""
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", str(RATE),
                        "pipe:1"], capture_output=True, timeout=300)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"could not read {os.path.basename(path)}")
    return r.stdout


def write_narration(path, pieces, total):
    """``pieces``: [(start seconds, pcm bytes)] laid on silence ``total`` long."""
    buf = bytearray(int(total * RATE) * 2)
    for start, data in pieces:
        k = int(start * RATE) * 2
        end = min(len(buf), k + len(data))
        buf[k:end] = data[:end - k]
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(buf))
    return path


def voice_translations(client, texts, job_dir, lang, log=print, wait=30):
    """[(wav, seconds)] per text: the free Microsoft voice, Gemini for a line it
    fails, once more after a pause; raises when a line still has no voice."""
    import ai_take
    import free_voice
    import local_voice
    out = [None] * len(texts)
    path_of = [os.path.join(job_dir, f".qv_{k + 1}.wav") for k in range(len(texts))]
    for attempt in range(2):
        if attempt:
            log(f"   🔁 {sum(1 for o in out if not o)} translation line(s) failed; trying again in {wait} s...")
            time.sleep(wait)
        for k, text in enumerate(texts):
            if out[k] or not text:
                continue
            if free_voice.engine() == "edge" and not free_voice.resting():
                secs = free_voice.speak(text, path_of[k], EDGE_VOICE[lang], VOICE_RATE)
                time.sleep(free_voice.PAUSE)
                if secs:
                    out[k] = (path_of[k], secs)
        # The edge voice's misses go to the free local voice (local_voice.py), then to Gemini.
        todo = [k for k, t in enumerate(texts) if t and not out[k]]
        if todo and free_voice.engine() in ("edge", "omni") and local_voice.available():
            for k in todo:
                if os.path.exists(path_of[k] + ".words.json"):
                    os.remove(path_of[k] + ".words.json")
            for k, secs in zip(todo, local_voice.speak_many([(texts[k], path_of[k], "male", VOICE_RATE) for k in todo])):
                if secs:
                    out[k] = (path_of[k], secs)
        for k, text in enumerate(texts):
            if out[k] or not text or client is None:
                continue
            if os.path.exists(path_of[k] + ".words.json"):
                os.remove(path_of[k] + ".words.json")
            secs = ai_take.speak(client, text, path_of[k], GEMINI_VOICE, VOICE_STYLE,
                                 language="Urdu" if lang == "urdu" else "English")
            if secs:
                out[k] = (path_of[k], secs)
        if all(o or not t for o, t in zip(out, texts)):
            return out
    raise RuntimeError(f"{sum(1 for o, t in zip(out, texts) if t and not o)} translation lines could not be "
                       "voiced (the network or the voice service is down); made again later.")


# ------------------------------------------------------------------ pictures

def footage(client, total, log=print):
    """Stock clips for the background, one per ~SHOT_SECONDS: [candidate with "path"]."""
    import stock_media
    n = max(2, math.ceil(total / SHOT_SECONDS))
    terms = random.sample(FOOTAGE_TERMS, min(n, len(FOOTAGE_TERMS)))
    terms = (terms * (n // len(terms) + 1))[:n]
    scenes = [f"calm background for a Quran recitation: {t}" for t in terms]
    found = [c for c in stock_media.for_scenes(client, "a Quran recitation with translation", scenes, terms,
                                               portrait=False, photos=False, log=log, rule=FOOTAGE_RULE) if c]
    if not found:
        raise RuntimeError("No footage could be found (the network or the footage libraries are down); "
                           "made again later.")
    return found


def shot(src, seconds, offset, out):
    """One background shot: the clip filling 16:9, a little darker, fading in and out."""
    fade = min(0.6, seconds / 4)
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,"
          f"eq=brightness=-0.03:saturation=0.9,drawbox=x=0:y=0:w=iw:h=ih:color=black@0.32:t=fill,"
          f"fade=t=in:st=0:d={fade:.2f},fade=t=out:st={seconds - fade:.2f}:d={fade:.2f},format=yuv420p")
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{offset:.2f}", "-stream_loop", "-1",
                        "-i", src, "-vf", vf, "-frames:v", str(int(round(seconds * FPS))), "-r", str(FPS),
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
                        "-video_track_timescale", "30000", "-an", out],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"footage shot failed: {r.stderr.strip()[-300:]}")
    return out


def too_dark(path):
    """True when the shot holds 1.5 s+ that video_qa would call black (its own detector)."""
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "info", "-i", path, "-vf",
                        "fps=5,scale=320:-2,blackdetect=d=1.5:pix_th=0.10", "-an", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace", timeout=300)
    return "black_start" in r.stderr


def background(job_dir, clips, total, log=print):
    """The joined background video, ``total`` seconds of shots. A shot that
    comes out too dark is made again from the next clip (twice at most)."""
    n = max(2, math.ceil(total / SHOT_SECONDS))
    lengths = [total / n] * n
    os.makedirs(os.path.join(job_dir, ".q_seg"), exist_ok=True)
    dark = set()

    def one(k):
        out = os.path.join(job_dir, ".q_seg", f"s{k:03d}.mp4")
        for attempt in range(3):
            c = clips[(k + attempt) % len(clips)]
            if c["id"] in dark and attempt < 2:
                continue
            room = max(0.0, float(c.get("seconds") or 0) - lengths[k] - 0.5)
            # A clip used twice starts at another moment the second time.
            offset = random.uniform(0, room) if room > 1 else 0.0
            shot(c["path"], lengths[k], offset, out)
            if not too_dark(out):
                break
            dark.add(c["id"])
            log(f"   ℹ️ Shot {k + 1} came out too dark; another clip.")
        return out
    with ThreadPoolExecutor(max_workers=3) as pool:
        names = list(pool.map(one, range(n)))
    log(f"   🎞️ {n} background shots from {len(clips)} clips.")
    lst = os.path.join(job_dir, ".q_parts.txt")
    with open(lst, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(f"file '{os.path.relpath(p, job_dir).replace(os.sep, '/')}'\n" for p in names))
    out = os.path.join(job_dir, ".q_bg.mp4")
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", ".q_parts.txt",
                        "-c", "copy", ".q_bg.mp4"], cwd=job_dir, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"join failed: {r.stderr.strip()[-300:]}")
    return out


def burn(job_dir, video, events, out_name):
    """The text over the background (video only: audio in the same graph as
    footage stalled ffmpeg 9 for good, see CLAUDE.md)."""
    with open(os.path.join(job_dir, ".q_text.ass"), "w", encoding="utf-8") as f:
        f.write(_ass(events))
    vf = f"ass=filename='.q_text.ass':fontsdir='{escape_filter_value(fl.FONTS_DIR)}'"
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", os.path.basename(video), "-vf", vf,
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-an",
                        out_name], cwd=job_dir, capture_output=True, text=True, errors="replace", timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(f"text pass failed: {r.stderr.strip()[-300:]}")
    return os.path.join(job_dir, out_name)


def mix(job_dir, video, narration, out, total):
    # ffmpeg runs inside job_dir, so it gets bare names: the server passes a relative job_dir
    # ("output/<id>") and the joined paths then pointed at output/<id>/output/<id>/... (23-oct-2026,
    # "Error opening input: No such file or directory" on every Quran video).
    video, narration, out_name = (os.path.basename(p) for p in (video, narration, out))
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", video, "-i", narration,
                        "-filter_complex", f"[1:a]{LOUDNORM_FILTER},aresample=48000,aformat=channel_layouts=stereo[a]",
                        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                        "-t", f"{total:.3f}", *METADATA_SCRUB, "-movflags", "+faststart", out_name],
                       cwd=job_dir, capture_output=True, text=True, errors="replace", timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"mix failed: {r.stderr.strip()[-400:]}")
    return out


def thumbnail(job_dir, clip, segs, screen, out):
    """1280x720: a darkened frame, the surah's Arabic name, its name and "Urdu Tarjuma"."""
    s, a, b = segs[0]
    tw, th = 1280, 720
    name = SPECIAL.get(tuple(segs[0])) or display_name(s)
    words = TITLE_WORDS["english" if screen == "english" else "urdu"]
    if len(segs) > 1:
        sub = " + ".join(short_name(x[0]) for x in segs[1:])
    elif tuple(segs[0]) in SPECIAL:
        sub = f"{display_name(s)} {a}" if a == b else f"{display_name(s)} {a}-{b}"
    elif a == 1 and b == chapter(s)["ayat"]:
        sub = ""
    else:
        sub = f"Ayat {a}" if a == b else f"Ayat {a}-{b}"
    st = [_style("TAr", "Amiri Quran", 240, fl.GOLD, outline=3, shadow=5),
          _style("TName", "Anton", 96, "#FFFFFF", outline=4, shadow=4),
          _style("TSub", "Montserrat ExtraBold", 40, "#FFFFFF", outline=2, shadow=2, bold=1),
          _style("TPill", "Montserrat ExtraBold", 40, "#1A1405", outline=14, shadow=0, bold=1, box=fl.GOLD)]
    ev = [_at(1, 0, 5, "TAr", tw // 2, 250, SPECIAL_ARABIC.get(tuple(segs[0])) or chapter(s)["arabic"],
              fade=(0, 0)),
          _at(1, 0, 5, "TName", tw // 2, 450, name.upper(), fade=(0, 0)),
          _at(1, 0, 5, "TPill", tw // 2, 575, words.upper(), fade=(0, 0))]
    if sub:
        ev.append(_at(1, 0, 5, "TSub", tw // 2, 650, sub, fade=(0, 0)))
    with open(os.path.join(job_dir, ".q_thumb.ass"), "w", encoding="utf-8") as f:
        f.write(_ass(ev, tw, th, st))
    vf = (f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},eq=brightness=-0.12:saturation=1.1,"
          f"ass=filename='.q_thumb.ass':fontsdir='{escape_filter_value(fl.FONTS_DIR)}'")
    # Inside job_dir: an absolute source and a bare output name (job_dir may be relative, see mix).
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", "1.5", "-i", os.path.abspath(clip["path"]),
                        "-vf", vf, "-frames:v", "1", "-q:v", "3", os.path.basename(out)],
                       cwd=job_dir, capture_output=True, text=True, timeout=120)
    return out if r.returncode == 0 and os.path.isfile(out) else None


# ------------------------------------------------------------------ words around the video

def title_of(segs, settings, part=None):
    """"Surah Yaseen Part 2 (Ayat 13-27) with Urdu Translation | Beautiful Tilawat | Mishary Alafasy"."""
    words = TITLE_WORDS["english" if settings["screen"] == "english" else "urdu"]
    qari = RECITER_SHORT[settings["reciter"]]
    if len(segs) == 1:
        s, a, b = segs[0]
        head = SPECIAL.get((s, a, b)) or (display_name(s) if a == 1 and b == chapter(s)["ayat"]
                                          else f"{display_name(s)}{f' Part {part}' if part else ''} "
                                               f"(Ayat {a}-{b})" if a != b else f"{display_name(s)} (Ayat {a})")
    else:
        head = display_name(segs[0][0]) + ", " + ", ".join(short_name(x[0]) for x in segs[1:])
    for title in (f"{head} {words} | {TITLE_TAIL} | {qari}", f"{head} {words} | {qari}", f"{head} {words}"):
        if len(title) <= 100:
            return title
    return title[:100]


def _tag(text):
    return re.sub(r"[^A-Za-z0-9]", "", text)


def describe(segs, settings, handle, credit, voiced):
    screen = settings["screen"]
    lines = []
    for s, a, b in segs:
        c = chapter(s)
        span = f"poori surah, {c['ayat']} ayat" if a == 1 and b == c["ayat"] else \
            f"ayat {a}-{b}" if a != b else f"ayat {a}"
        lines.append(f"{display_name(s)} ({c['meaning']}), surah number {s}, {span}  {c['arabic']}")
    tr = []
    if screen in ("both", "urdu") or settings["voice"] == "urdu":
        tr.append(f"Urdu tarjuma: {URDU[settings['urdu']]}")
    if screen in ("both", "english") or settings["voice"] == "english":
        tr.append(f"English translation: {ENGLISH[settings['english']]}")
    which = "English tarjume" if screen == "english" else "Urdu tarjume"
    opening = f"{label(*segs[0])}{' aur aage' if len(segs) > 1 else ''} ki tilawat, {which} ke saath."
    if voiced:
        opening += " Har ayat ke baad us ka tarjuma suniye aur screen par parhiye."
    tags = ["#Quran", *[f"#{_tag(display_name(s))}" for s, _a, _b in segs[:2]],
            "#QuranWithEnglishTranslation" if screen == "english" else "#QuranWithUrduTranslation",
            "#Tilawat", "#QuranRecitation"]
    body = [opening, "", *lines, "",
            f"Tilawat: Qari {RECITERS[settings['reciter']]}", *tr,
            *([f"Tarjume ki awaaz AI ki hai ({'Urdu' if settings['voice'] == 'urdu' else 'English'}); tilawat qari "
               "sahab ki apni awaaz mein hai."] if voiced else []),
            "Quran text, translations and recitation audio: Quran.com (Quran Foundation).",
            *([credit] if credit else []),
            "No music.", "",
            f"{FOLLOW['english' if screen == 'english' else 'urdu']}{(' ' + handle) if handle else ''}",
            "", " ".join(tags)]
    return "\n".join(body)


def tags_of(segs, settings):
    out = ["quran", "quran recitation", "tilawat", "quran with urdu translation", "urdu tarjuma",
           "quran tilawat urdu tarjuma", RECITERS[settings["reciter"]].lower()]
    for s, a, b in segs:
        n = short_name(s).lower()
        out += [f"surah {n}", f"surah {n} urdu translation", f"surah {chapter(s)['name'].lower()}",
                f"surah {_name_key(chapter(s)['name'])}"]
        if (s, a, b) in SPECIAL:
            out.append(SPECIAL[(s, a, b)].lower())
    if settings["screen"] == "english":
        out = [t.replace("urdu translation", "english translation") for t in out if "urdu tarjuma" not in t]
    seen, keep = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            keep.append(t[:40])
    return keep[:15]


def _srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(path, cues):
    """``cues``: [(start, end, text)] -> an SRT file, or None when there is no text."""
    merged = []
    for a, b, text in cues:
        if not text.strip():
            continue
        if merged and merged[-1][2] == text and a - merged[-1][1] < 0.2:
            merged[-1] = (merged[-1][0], b, text)      # the same page while recited and while read out
        else:
            merged.append((a, b, text))
    cues = merged
    if not cues:
        return None
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for k, (a, b, text) in enumerate(cues, 1):
            f.write(f"{k}\n{_srt_time(a)} --> {_srt_time(b)}\n{text.strip()}\n\n")
    return path


# ------------------------------------------------------------------ the job

def units(segs, settings):
    """What is said, in order: the Bismillah where a surah opens (not At-Tawbah,
    and Al-Fatiha's first ayah is the Bismillah), then each ayah."""
    out = []
    for s, a, b in segs:
        rows = verses(s, settings["urdu"], settings["english"])
        if a == 1 and chapter(s)["bismillah"]:
            first = verses(1, settings["urdu"], settings["english"])[0]
            out.append({**first, "s": 1, "number": None, "bismillah": True})
        for n in range(a, b + 1):
            out.append({**rows[n - 1], "s": s, "number": n, "surah_of": s})
    return out


def run(output_dir, pipeline):
    plan = json.loads(os.environ.get("QURAN_PLAN") or "{}")
    settings = settings_of(plan)
    segs = [[int(x) for x in seg] for seg in plan.get("segments") or []]
    if not segs or any(not (1 <= s <= 114 and 1 <= a <= b <= chapter(s)["ayat"]) for s, a, b in segs):
        raise RuntimeError("No Quran passage was given (QURAN_PLAN segments).")
    cfg = fl.settings()
    handle = cfg["handle"] or ""
    started = time.time()
    screen, voice = settings["screen"], settings["voice"]
    title = title_of(segs, settings, plan.get("part"))
    print(f"📖 Quran video: {title} ({RECITERS[settings['reciter']]}, screen {screen}, voice {voice})")
    us = units(segs, settings)
    keys = [u["key"] for u in us]
    prefetch(settings["reciter"], keys)
    recite = [audio_file(settings["reciter"], k) for k in keys]
    rec_secs = [seconds_of(p) for p in recite]
    try:
        client = kit.gemini()
    except RuntimeError:
        client = None                      # footage then takes each scene's first result
    said = [None] * len(us)
    if voice != "off":
        lang_key = "ur" if voice == "urdu" else "en"
        print(f"🎙️ Reading {len(us)} translations ({voice})...")
        said = voice_translations(client, [_speakable(u[lang_key]) for u in us], output_dir, voice)

    # The timeline: title card, then per ayah its recitation and its translation read out.
    events, pieces, ur_cues, en_cues = [], [], [], []
    s0 = segs[0][0]
    events += [_at(5, 0.2, INTRO, "QArBig", W // 2, 400, SPECIAL_ARABIC.get(tuple(segs[0])) or chapter(s0)["arabic"],
                   fade=(400, 300)),
               _at(5, 0.4, INTRO, "QTitle", W // 2, 560, SPECIAL.get(tuple(segs[0])) or display_name(s0),
                   fade=(400, 300)),
               _at(5, 0.6, INTRO, "QPill", W // 2, 650, f"Qari {RECITERS[settings['reciter']]}", fade=(400, 300))]
    t = INTRO
    for k, u in enumerate(us):
        ayah_start = t
        pages = pages_of(u, screen)
        pieces.append((t, pcm(recite[k])))
        rec_end = t + rec_secs[k]
        voice_win = None
        if said[k]:
            v0 = rec_end + AFTER_RECITE
            pieces.append((v0, pcm(said[k][0])))
            voice_win = (v0, said[k][1])
            t = v0 + said[k][1] + AFTER_AYAH
        else:
            t = rec_end + AFTER_AYAH
        shares = [max(1, letters(p[0])) for p in pages]
        windows = spans(ayah_start, rec_secs[k], shares)
        if voice_win:
            spoken = _speakable(u["ur" if voice == "urdu" else "en"])
            per_page = [len(_speakable(p[1 if voice == "urdu" else 2]).split()) for p in pages]
            if sum(per_page) != len(spoken.split()):
                per_page = [len(spoken.split()) * sh // sum(shares) for sh in shares]
            vw = voice_spans(voice_win[0], voice_win[1], per_page, said[k][0] + ".words.json")
            # The last page of the recitation stays up through the pause before the voice.
            windows[-1] = (windows[-1][0], vw[0][0])
            windows += vw
            pages = pages + pages
        windows[-1] = (windows[-1][0], t - 0.05)
        for (a, b), page in zip(windows, pages):
            events += page_events(a, b, page, u["number"], screen)
        if u.get("sajda"):
            events.append(_at(5, ayah_start, t, "QPill", W // 2, 160, "AYAT-E-SAJDA", fade=(300, 300)))
        ur_cues += [(a, b, p[1]) for (a, b), p in zip(windows, pages)]
        en_cues += [(a, b, p[2]) for (a, b), p in zip(windows, pages)]
        # Always on: the surah and ayah at the top left.
        head = "Bismillah" if u.get("bismillah") else f"{display_name(u['surah_of'])}  Ayat {u['number']}"
        events.append(_at(5, ayah_start, t, "QHead", 70, 60, head, an=7, fade=(0, 0)))
    end_text = t
    total = t + OUTRO
    if handle:
        events.append(_at(5, 0, total, "QSmall", W - 70, 62, handle, an=9, fade=(0, 0)))
    events.append(_at(5, INTRO, end_text, "QSmall", 70, 104, f"Qari {RECITERS[settings['reciter']]}", an=7,
                      fade=(300, 0)))
    events += [_at(5, end_text, total, "QTitle", W // 2, 470, FOLLOW["english" if screen == "english" else "urdu"],
                   fade=(300, 300), extra=r"\fs52"),
               *([_at(5, end_text + 0.2, total, "QPill", W // 2, 580, handle, fade=(300, 300))] if handle else [])]

    stem = kit.neutral_stem("Quran")
    print(f"🎞️ Finding calm footage for {total / 60:.1f} min...")
    clips = footage(client, total)
    print(f"🎬 Rendering {total / 60:.1f} min...")
    bg = background(output_dir, clips, total)
    video = burn(output_dir, bg, events, ".q_video.mp4")
    narration = write_narration(os.path.join(output_dir, ".q_voice.wav"), pieces, total)
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    mix(output_dir, video, narration, final, total)
    thumb = thumbnail(output_dir, clips[0], segs, screen, os.path.join(output_dir, f"{stem}_thumb.jpg"))
    ur_srt = write_srt(os.path.join(output_dir, "captions.srt"), ur_cues) if screen != "english" else None
    en_srt = write_srt(os.path.join(output_dir, "captions.en.srt"), en_cues) if screen != "urdu" else None
    import stock_media
    desc = describe(segs, settings, handle, stock_media.credit_line(clips), voice != "off")
    main_srt, main_lang = (ur_srt, "ur") if ur_srt else (en_srt, "en")
    clip = {"start": 0.0, "end": round(total, 3), "seconds": round(total, 3), "file": final,
            "video_title_for_youtube_short": title, "seo_title": title[:100], "seo_description": desc,
            "seo_tags": tags_of(segs, settings), "viral_hook_text": label(*segs[0]),
            "why": f"Quran: {', '.join(label(*x) for x in segs)}", "predicted_score": 80, "genre": "quran",
            "comment_question": "", "ai_made": False,
            **({"ai_voice": "AI voice (translation only)"} if voice != "off" else {}),
            "thumbnail_file": os.path.basename(thumb) if thumb else None,
            "captions_file": os.path.basename(main_srt) if main_srt else None, "captions_language": main_lang,
            "captions_extra": ([{"file": os.path.basename(en_srt), "language": "en"}]
                               if ur_srt and en_srt else []),
            "footage": [{"provider": f["provider"], "page": f["page"], "author": f["author"]} for f in clips],
            "quran": {"segments": segs, **settings, "ayat": sum(b - a + 1 for _s, a, b in segs)}}
    kit.finish(output_dir, stem, [clip], None, pipeline, extra={"genre": "quran", "format": "16:9"})
    print(f"   ⏱️ Made in {(time.time() - started) / 60:.1f} min.")
