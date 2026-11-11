"""The owner's other YouTube channels (self-host only; dashboard tab "Channels").

Punchline Bazaar stays the main channel: its Autopilot, Ready to post,
learning loop and files are exactly what they were. Each channel added here
is separate from it and from the others:
- its own Google connection and uploads log (output/channels/<id>/, used
  through youtube_account.use(), so one OAuth client serves every channel);
- its own kind of Short (KINDS), number a day and posting times;
- its jobs carry ``channel`` in .source.json, so they never show in the main
  channel's Ready to post and are never uploaded anywhere else.

loop_forever makes the Shorts (one generated job at a time on this laptop,
the channel furthest behind first) once a channel is connected, uploads each
finished one into the channel's next free posting time, pauses a channel 3 h
after YouTube's daily upload limit, checks for copyright blocks, and every
6 h reads the channel's own numbers: the best and worst titles steer the next
ideas, and for quiz and songs the format or style with the most views gets
picked more often (EXPLORE of the time something else, so a new winner can
still show up).
"""
import asyncio
import json
import os
import random
import re
import shutil
import statistics
import threading
import time
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "output", ".my_channels.json")
# Each channel's Google token, upload log and engagement state. Not under
# output/, which is scratch space for jobs: the 24 h job sweep deleted
# output/channels on 18-oct-2026 and all five channels had to reconnect.
CHANNELS_DIR = _REAL_CHANNELS_DIR = os.path.join(ROOT, "state", "channels")
OLD_CHANNELS_DIR = os.path.join(ROOT, "output", "channels")
TICK_SECONDS = 60
UPLOAD_EVERY = 600
UPLOAD_PAUSE_SECONDS = 3 * 3600
CLAIM_CHECK_EVERY = 1800
LEARN_EVERY = 6 * 3600
LOOKBACK_DAYS = 30
MATURE_HOURS = 48
# Views at a fixed age (research, 29-oct-2026): on lifetime views a Short counted at 30 days beat one counted
# at 3, which tilted the A/B tests, the format picks, the posting-hour tip and the best/worst lists toward
# old Shorts. The first learn pass between 48 and 72 h keeps the number as views_48h; decisions use it.
FAIR_AGE, FAIR_WINDOW = timedelta(hours=48), timedelta(hours=24)
JOB_TIMEOUT = 50 * 60
KEEP_DAYS = 7
# 8 since 5-nov-2026 (the horror and money channels): one job at a time on this laptop, and the six cards kept it
# busy about 4 h of 24 (measured that day), so two more fit.
MAX_CHANNELS = 8
MAX_PER_DAY = 10          # the channel's own daily upload limit is about 10 (14-oct-2026)
TRIES_PER_SHORT = 2       # a day of failures stops at twice the Shorts wanted
# Failures that say nothing about the idea: Gemini's quota, a network drop.
# Counted as tries, an hour of them used up the day and nothing was made
# after Gemini came back; instead they pause the channel for a while.
TRANSIENT = re.compile(r"\b429\b|RESOURCE_EXHAUSTED|quota|rate.?limit|too many requests|\b50[234]\b|UNAVAILABLE|"
                       r"overloaded|timed out|ConnectError|getaddrinfo|network|\bDNS\b|temporarily", re.I)
TRANSIENT_PAUSE = 1800
TRANSIENT_MAX = 6         # a day; past that they count like any other failure
# A job the server no longer knows, with nothing on disk: the server restarted
# (watchdog, laptop reboot) and the job could not be resumed. Waiting for the
# timeout held the one-job-at-a-time loop for up to 3 hours.
LOST_AFTER = 600
LOST = "the job was lost when the server restarted"
# A long video needs a few GB while it renders (shots, voices, the join); a
# full disk fails it at the last step, after all its AI calls were paid.
MIN_FREE_GB = 5
# A fresh connection makes and uploads nothing for 15 minutes: the cricket
# card was first connected to the music channel by mistake (18-oct-2026), and
# within a minute its waiting Short went up there and the next one was made
# with the music channel's handle on its end card. The card names the channel.
CONNECT_HOLD = 15 * 60
UPLOAD_TRIES = 3
IDEAS_RETRY = 1800
EXPLORE = 0.3
MIN_FOR_LEARNING = 3

KINDS = {
    # Shorts channels start at 2 a day at Pakistan's busy hours: every channel in these
    # niches with a median over 40k views posts 0.2-2.1 a day; ours posted 8 around the
    # clock, hit the daily limit 51 times and got a median of 0-5 views (22-oct-2026).
    "cricket": {"label": "Cricket facts and updates", "genre": "cricket", "color": "#0B3D2E",
                "times": ["14:00", "20:30"], "per_day": 2,
                "about": "Animated stats, records and match results with a voice-over and free-licence "
                         "player photos. Ideas come from Google Search every day."},
    "quiz": {"label": "Quiz and paheliyan", "genre": "quiz", "color": "#16206B",
             "times": ["16:00", "21:30"], "per_day": 2,
             "about": "General knowledge questions, paheliyan and quick maths puzzles with a countdown. "
                      "Viewers answer in the comments before the reveal."},
    "controversy": {"label": "Controversies, explained", "genre": "controversy", "color": "#2A0A0A",
                    "times": ["13:00", "19:30"], "per_day": 2,
                    "about": "What really happened in famous people's controversies: researched with sources, "
                             "allegations told as allegations, both sides, a fairness check before every video. "
                             "No religion, politics or army."},
    # Motion graphics (money_shorts.py, owner 29-oct-2026): money told as stories, every number researched.
    "money": {"label": "Money in numbers (motion graphics)", "genre": "money", "color": "#0A2A1F",
              "times": ["15:00", "21:00"], "per_day": 2,
              "about": "Animated charts that tell money stories in Roman Urdu: prices then and now, salaries at home "
                       "and abroad, companies' biggest mistakes. Every number researched with sources, checked "
                       "twice, never advice. About $0.05 of Gemini per Short."},
    # Cartoon comedy (toon_shorts.py, owner 5-nov-2026): talking animals and a talking baby, one cast, a series.
    "toons": {"label": "Talking animals cartoon comedy (Billo and Gang)", "genre": "toons", "color": "#3B1F5C",
              "times": ["17:30", "21:45"], "per_day": 2,
              "about": "An original cartoon series: Billo the cat, Sheru the dog, Mithu the parrot and baby Guddu who "
                       "talks like an old uncle, in one Lahore home. Every episode a new situation with a twist, two "
                       "drafts judged and punched up, the characters' mouths animated to their voices. About $0.4 "
                       "of Gemini per episode."},
    "music": {"label": "AI songs in English", "genre": "music", "color": "#2A0B2E",
              "times": ["18:00", "23:00"], "per_day": 2,
              "about": "Original songs under a minute: AI lyrics, sung by Google Lyria, with a cover "
                       "picture and the lyrics on screen. About $0.15 of Gemini per song."},
    # Long 16:9 videos (history_videos.py): 1-3 a day, a job takes 15-60 min on the laptop.
    # "story": the documentary channel's own settings and extras (minutes, language,
    # teaser Shorts, "Aaj ki tareekh"); the Quran channel is long but has none of them.
    "history": {"label": "History and stories (long videos)", "genre": "history", "color": "#1F1408",
                "times": ["18:00", "21:00"], "per_day": 2, "max_per_day": 3, "long": True, "story": True,
                "timeout": 3 * 3600,
                "notes": "Rome, Karbala, the Caliphs, the US government, the US economy",
                "about": "2 to 30 minute documentaries about empires, countries and famous events: researched "
                         "with sources, a narrator, free Wikipedia pictures and AI pictures, chapters and a "
                         "thumbnail. About $1 of Gemini per 10-minute video."},
    # Long 16:9 videos (quran_videos.py): 2-5 minutes, a real qari's recitation, no AI in the Quran itself.
    "quran": {"label": "Quran recitation with translation (long videos)", "genre": "quran", "color": "#0B2E22",
              "times": ["05:30", "20:30"], "per_day": 1, "max_per_day": 3, "long": True, "timeout": 2 * 3600,
              "about": "2 to 5 minute videos: a famous qari recites, the Arabic and the Urdu or English "
                       "translation on screen, the translation read out after each ayah, calm nature and "
                       "mosque footage, no music. Popular surahs first, then the whole Quran in order."},
}
# The planner module of each kind that works from a queue of researched ideas.
PLANNERS = {"cricket": "cricket_shorts", "controversy": "controversy_shorts", "history": "history_videos",
            "money": "money_shorts", "toons": "toon_shorts"}
MINUTES_RANGE, DEFAULT_MINUTES = (2, 30), 10
LANGS = ("urdu", "english")
# The long channel's subject: "history" documentaries, or "explainer", this
# week's hot topics explained (trend_explainer.py; owner, 21-oct-2026).
# "horror": original horror stories (horror_stories.py; owner, 5-nov-2026: the new channel).
LONG_MODES = ("history", "explainer", "horror")
FORMATS = {"quiz": ["mcq", "riddle", "math", "flags", "truefalse", "oddone", "stars", "islamic"]}
# Fast results on the cricket channel: a match Pakistan or India just
# finished is the most searched cricket topic of the day, worth more than
# any planned idea, so it jumps the queue and is published 20 minutes after
# it is made instead of at the next posting time.
MATCH_EVERY = 2 * 3600
URGENT_AFTER_MINUTES = 20
MATCH_PROMPT = """Today is {today}. Did the Pakistan or the India men's national cricket team
finish an international match (Test, ODI or T20I) in the last 12 hours? Use Google Search.
For each such match answer one line exactly: MATCH: <team> vs <team>, <series or tournament>, <date>
If none (or one is still being played), answer exactly: NONE"""
# engage.py switches. On for the new channels (nothing happens before the
# owner connects them); off on the main channel until the owner turns them
# on, because there they would start posting on a live channel at once.
# "podcasts": long-video playlists as YouTube podcast shows (engage.podcasts; long kinds only).
ENGAGE_DEFAULTS = {"first_comment": True, "auto_reply": True, "playlists": True, "cross_promo": True, "podcasts": True}
MAIN_ENGAGE_DEFAULTS = {k: False for k in ENGAGE_DEFAULTS}
ENGAGE_EVERY = 900
_lock = threading.Lock()
_ideas_failed = {}
failure_reason = None     # app.py sets it: job id -> the one-line reason the job failed
cancel_job = None         # app.py sets it: stops a job's process (one past its time still held a slot)


# ------------------------------------------------------------------ store

def _read(path, default):
    # A damaged file falls back to its hourly backup (safe_json): read as
    # empty, it lost every channel and the next write made that permanent.
    import safe_json
    return safe_json.read(path, default)


def _write(path, data):
    import safe_json
    safe_json.write(path, data)


def channels():
    return _read(STATE_FILE, {}).get("channels") or []


def get(cid):
    return next((c for c in channels() if c.get("id") == cid), None)


def _save_channel(ch):
    with _lock:
        data = _read(STATE_FILE, {})
        rows = data.get("channels") or []
        data["channels"] = [ch if c.get("id") == ch["id"] else c for c in rows]
        if not any(c.get("id") == ch["id"] for c in rows):
            data["channels"].append(ch)
        _write(STATE_FILE, data)


def _change(cid, fn):
    """Read-modify-write one channel under the lock; returns it."""
    with _lock:
        data = _read(STATE_FILE, {})
        rows = data.get("channels") or []
        ch = next((c for c in rows if c.get("id") == cid), None)
        if ch is None:
            return None
        fn(ch)
        _write(STATE_FILE, data)
        return ch


def folder(cid):
    return os.path.join(CHANNELS_DIR, cid)


def disk_free_gb():
    import shutil
    try:
        return shutil.disk_usage(os.path.dirname(STATE_FILE)).free / 1e9
    except OSError:
        return float("inf")


def account(cid):
    """What youtube_account.use() needs for this channel."""
    return {"id": cid, "token": os.path.join(folder(cid), "token.json"),
            "uploads": os.path.join(folder(cid), "uploads.json")}


def _clock(t):
    t = str(t or "").strip()
    try:
        h, m = (int(x) for x in t.split(":"))
        return f"{h:02d}:{m:02d}" if 0 <= h < 24 and 0 <= m < 60 else ""
    except ValueError:
        return ""


def add(kind, name=""):
    if kind not in KINDS:
        raise ValueError("Unknown channel type.")
    rows = channels()
    if len(rows) >= MAX_CHANNELS:
        raise ValueError(f"At most {MAX_CHANNELS} channels.")
    taken = {c["id"] for c in rows} | {"main"}
    cid, n = kind, 2
    while cid in taken:
        cid, n = f"{kind}{n}", n + 1
    k = KINDS[kind]
    ch = {"id": cid, "kind": kind, "name": " ".join(str(name or k["label"]).split())[:60],
          "enabled": True, "auto_upload": True, "per_day": k.get("per_day", 8), "post_times": list(k["times"]),
          "handle": "", "color": k["color"], "notes": k.get("notes", ""), "created": int(time.time()),
          **ENGAGE_DEFAULTS, **({"minutes": DEFAULT_MINUTES, "lang": "urdu"} if k.get("story") else {}),
          # No AI replies to religious comments, and no "More from us" line next to the other channels.
          **({"quran": dict(__import__("quran_videos").DEFAULTS), "auto_reply": False, "cross_promo": False}
             if kind == "quran" else {}),
          "last_upload": 0, "upload_paused_until": 0, "last_claim_check": 0, "last_learn": 0,
          "jobs": [], "ideas": [], "used": [], "stats": {}}
    _save_channel(ch)
    return ch


# How every generated video looks and sounds (all channels but the comedy one):
# the free Microsoft voices or Gemini's, and free stock footage behind the text.
LOOK_DEFAULTS = {"voice": "edge", "footage": True}


def look():
    return {**LOOK_DEFAULTS, **(_read(STATE_FILE, {}).get("look") or {})}


def update_look(patch):
    with _lock:
        data = _read(STATE_FILE, {})
        cur = {**LOOK_DEFAULTS, **(data.get("look") or {})}
        if patch.get("voice") in ("edge", "gemini"):
            cur["voice"] = patch["voice"]
        if "footage" in patch:
            cur["footage"] = bool(patch["footage"])
        data["look"] = cur
        _write(STATE_FILE, data)
    return cur


def look_env():
    """The job environment for the look (app.py sets it on every generated job)."""
    cur = look()
    return {"VOICE_ENGINE": cur["voice"], "STOCK_FOOTAGE": "1" if cur["footage"] else "0"}


def cap(ch):
    """Most videos a day for the channel's kind: Shorts up to YouTube's upload
    limit, long videos 3."""
    return KINDS.get(ch.get("kind"), {}).get("max_per_day", MAX_PER_DAY)


def main_settings():
    """The main channel's engagement switches (its other settings are Autopilot's)."""
    return {**MAIN_ENGAGE_DEFAULTS, **(_read(STATE_FILE, {}).get("main") or {})}


def update_main(patch):
    with _lock:
        data = _read(STATE_FILE, {})
        main = {**MAIN_ENGAGE_DEFAULTS, **(data.get("main") or {})}
        for key in ENGAGE_DEFAULTS:
            if key in patch:
                main[key] = bool(patch[key])
        data["main"] = main
        _write(STATE_FILE, data)
    return main


def engage_settings(ch):
    return {k: bool(ch.get(k, v)) for k, v in ENGAGE_DEFAULTS.items()}


def update(cid, patch):
    def fn(ch):
        for key in ("enabled", "auto_upload", "match_watch", *ENGAGE_DEFAULTS):
            if key in patch:
                ch[key] = bool(patch[key])
        if "per_day" in patch:
            try:
                ch["per_day"] = max(1, min(cap(ch), int(patch["per_day"])))
            except (TypeError, ValueError):
                pass
        if "post_times" in patch and isinstance(patch["post_times"], list):
            times = sorted({_clock(t) for t in patch["post_times"]} - {""})
            ch["post_times"] = times[:cap(ch)] or ch["post_times"]
        if "name" in patch:
            ch["name"] = " ".join(str(patch["name"] or "").split())[:60] or ch["name"]
        if "handle" in patch:
            h = re.sub(r"\s+", "", str(patch["handle"] or ""))[:40]
            ch["handle"] = ("@" + h.lstrip("@")) if h else ""
        if "color" in patch and re.fullmatch(r"#[0-9A-Fa-f]{6}", str(patch["color"] or "")):
            ch["color"] = patch["color"].upper()
        if "notes" in patch:
            ch["notes"] = " ".join(str(patch["notes"] or "").split())[:300]
        if "daily_short" in patch:
            ch["daily_short"] = bool(patch["daily_short"])
        if "toon_mix" in patch:
            ch["toon_mix"] = bool(patch["toon_mix"])      # the cartoon channel's weekly compilation (toon_mix.py)
        # Facebook / Instagram cross-posting (meta_publish.py): which Page, and which of the two.
        if "meta_page" in patch:
            ch["meta_page"] = re.sub(r"[^0-9]", "", str(patch["meta_page"] or ""))[:30]
        for key in ("meta_fb", "meta_ig"):
            if key in patch:
                ch[key] = bool(patch[key])
        if patch.get("meta_ig_mode") in META_IG_MODES:
            ch["meta_ig_mode"] = patch["meta_ig_mode"]
        if "meta_ig_page" in patch:
            ch["meta_ig_page"] = re.sub(r"[^0-9]", "", str(patch["meta_ig_page"] or ""))[:30]
        if patch.get("hide_old") and ch.get("took_over"):
            # hide_retired does it, a few per pass; asked again, a finished pass looks again (nothing done twice).
            ch["took_over"].setdefault("hide", int(time.time()))
            for k in ("hide_done", "hide_at"):
                ch["took_over"].pop(k, None)
        if "review_hours" in patch:
            try:
                ch["review_hours"] = max(0, min(REVIEW_MAX_HOURS, int(patch["review_hours"])))
            except (TypeError, ValueError):
                pass
        if ch["kind"] == "music" and isinstance(patch.get("moods"), dict):
            import music_moods                     # moods and their playlists (on/off, how often, the owner's own)
            ch["moods"] = music_moods.settings_of(patch["moods"])
        if ch["kind"] == "music" and "urdu_share" in patch:
            try:                                   # songs in Urdu: 0 (English only) to 1 (Urdu only)
                ch["urdu_share"] = round(max(0.0, min(1.0, float(patch["urdu_share"]))), 2)
            except (TypeError, ValueError):
                pass
        if ch["kind"] == "music" and "next_mood" in patch:
            ch["next_mood"] = re.sub(r"[^a-z0-9_]", "", str(patch["next_mood"] or ""))[:30]
        if ch["kind"] == "music" and "next_mix" in patch:
            ch["next_mix"] = re.sub(r"[^a-z0-9_]", "", str(patch["next_mix"] or ""))[:30]
        if ch["kind"] == "quran" and isinstance(patch.get("quran"), dict):
            import quran_videos
            ch["quran"] = quran_videos.settings_of({**(ch.get("quran") or {}), **patch["quran"]})
        if KINDS.get(ch["kind"], {}).get("story"):
            if "minutes" in patch:
                try:
                    ch["minutes"] = max(MINUTES_RANGE[0], min(MINUTES_RANGE[1], int(patch["minutes"])))
                except (TypeError, ValueError):
                    pass
            if patch.get("lang") in LANGS:
                ch["lang"] = patch["lang"]
            if patch.get("mode") in LONG_MODES and patch["mode"] != ch.get("mode", "history"):
                # The planned ideas belong to the old mode: plan again.
                ch["mode"] = patch["mode"]
                ch["ideas"] = []
    return _change(cid, fn)


def want_samples(cids=None):
    """Queue one sample video per channel (all by default); the loop makes them
    one after another, connected or not, so the owner can watch each first."""
    now = time.time()
    picked = []
    for k, ch in enumerate(channels()):
        if cids is None or ch["id"] in cids:
            _change(ch["id"], lambda c, at=now + k: c.update(sample_wanted=at))
            picked.append(ch["id"])
    return picked


def move_old_folder(old=None, new=None, log=print):
    """Move output/channels/<id> to CHANNELS_DIR once (the server calls it at
    startup). A file already in the new place wins; the old folder goes when
    it is empty."""
    if old is None and new is None and CHANNELS_DIR != _REAL_CHANNELS_DIR:
        # Redirected by a test: test_a_second_copy_of_the_app enters the real
        # startup, and the move carried the real output/channels into its
        # temporary folder (18-oct-2026).
        return 0
    old, new = old or OLD_CHANNELS_DIR, new or CHANNELS_DIR
    if not os.path.isdir(old):
        return 0
    moved = 0
    for root, _dirs, files in os.walk(old):
        for name in files:
            src = os.path.join(root, name)
            dst = os.path.join(new, os.path.relpath(src, old))
            if os.path.exists(dst):
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            moved += 1
    for root, _dirs, _files in os.walk(old, topdown=False):       # deepest first
        if not os.listdir(root):
            os.rmdir(root)
    if moved:
        log(f"📦 Moved {moved} channel file(s) from output/channels to {new}.")
    return moved


def remember_channel(cid, me):
    """The YouTube channel this card belongs to, kept in the channels file
    (outside the token, which can be lost): a later connect must pick it."""
    _change(cid, lambda c: c.update(yt_channel=me.get("id"), yt_title=(me.get("title") or "").strip()))


def forget_channel(cid):
    """Disconnect on purpose: the card may then go to another channel."""
    _change(cid, lambda c: [c.pop(k, None) for k in ("yt_channel", "yt_title")])


def wrong_pick(cid, me):
    """Why a sign-in for this card picked the wrong channel, or None."""
    ch = get(cid) or {}
    if ch.get("yt_channel") and me.get("id") and ch["yt_channel"] != me["id"]:
        want = ch.get("yt_title") or "its own channel"
        return (f"This card belongs to {want}, but {(me.get('title') or 'another channel').strip()} was picked. "
                f"Press connect again and pick {want}. To move the card to a different channel, "
                "press disconnect first.")
    return None


def remove(cid):
    """Forget a channel here: its record, Google token and uploads log. Its
    videos on YouTube stay; Google access can be removed in the Google account."""
    with _lock:
        data = _read(STATE_FILE, {})
        data["channels"] = [c for c in data.get("channels") or [] if c.get("id") != cid]
        _write(STATE_FILE, data)
    if re.fullmatch(r"[a-z]+\d*", cid or ""):
        shutil.rmtree(folder(cid), ignore_errors=True)


def retired_dir():
    """Where a retired card's files go: state/retired, beside CHANNELS_DIR (so a test's redirect covers it)."""
    return os.path.join(os.path.dirname(CHANNELS_DIR), "retired")


def hand_over(old_cid, new_cid, now=None):
    """Give one card's YouTube channel to another card (owner, 5-nov-2026: no Google accounts left for new
    channels, so the two weakest ones were reused for the horror and money cards).

    The new card takes the Google token, so its videos go up on that channel from now on. The old card goes
    away, but nothing is deleted: its record, uploads log, engagement state and kit move to
    state/retired/<old>-<time>/, and its videos stay on YouTube. The new card keeps its own empty uploads log,
    so its numbers, A/B tests, playlists and replies start from its own videos, and its next learn pass puts
    its own About text on the channel (about_credit, the old text backed up). The channel's name, handle and
    picture have no API: the owner changes them in YouTube Studio.
    Refused for the main channel, while either card is making a video, when the old card has no channel or
    the new one already has one."""
    now = now or time.time()
    with _lock:
        data = _read(STATE_FILE, {})
        rows = data.get("channels") or []
        old = next((c for c in rows if c.get("id") == old_cid), None)
        new = next((c for c in rows if c.get("id") == new_cid), None)
        if not old or not new or old_cid == new_cid:
            raise ValueError("Pick two different channel cards.")
        token = os.path.join(folder(old_cid), "token.json")
        if not os.path.isfile(token):
            raise ValueError(f"{old['name']} is not connected to a YouTube channel.")
        if os.path.isfile(os.path.join(folder(new_cid), "token.json")):
            raise ValueError(f"{new['name']} already has its own YouTube channel. Disconnect it first.")
        busy = [c["name"] for c in (old, new) if running(c)]
        if busy:
            raise ValueError(f"{busy[0]} is making a video now. Try again when it is done.")
        try:
            with open(token, encoding="utf-8") as f:
                yt = (json.load(f) or {}).get("channel") or {}
        except (OSError, ValueError):
            yt = {}
        dest = os.path.join(retired_dir(), f"{old_cid}-{datetime.fromtimestamp(now).strftime('%Y%m%d-%H%M%S')}")
        os.makedirs(folder(new_cid), exist_ok=True)
        os.makedirs(retired_dir(), exist_ok=True)
        shutil.move(token, os.path.join(folder(new_cid), "token.json"))
        shutil.move(folder(old_cid), dest)
        with open(os.path.join(dest, "card.json"), "w", encoding="utf-8") as f:
            json.dump(old, f, ensure_ascii=False, indent=1)
        title = (old.get("yt_title") or yt.get("title") or "").strip()
        new.update(yt_channel=old.get("yt_channel") or yt.get("id") or "", yt_title=title,
                   took_over={"from": old["name"], "kind": old["kind"], "yt_title": title,
                              "handle": yt.get("handle") or "", "at": int(now),
                              "archive": os.path.relpath(dest, os.path.dirname(os.path.dirname(CHANNELS_DIR)))})
        for key in ("about_credit", "long_uploads", "last_learn", "placement_checked"):
            new.pop(key, None)          # asked again of the channel it has now
        data["channels"] = [c for c in rows if c.get("id") != old_cid]
        _write(STATE_FILE, data)
    dropped = len(waiting(old))
    return {"ok": True, "to": new_cid, "from": old_cid, "channel": title, "archive": dest, "dropped": dropped}


HIDE_PER_PASS = 15             # old videos set private per pass (51 units each)
HIDE_EVERY = 10 * 60
HIDE_CEILING = 6000            # the day's quota units in use before hiding waits for tomorrow (uploads come first)


def _archive_of(ch):
    t = ch.get("took_over") or {}
    if not t.get("archive"):
        return None
    root = os.path.dirname(os.path.dirname(CHANNELS_DIR))
    return os.path.join(root, t["archive"])


def hide_retired(ch, log=print, now=None):
    """Set the retired card's videos and playlists on this channel to private, a few per pass, oldest first
    (owner, 5-nov-2026: the old quiz and history videos off the new money and horror channels). Only the ids
    in the retired card's own logs, so nothing this card made is touched; reversible in YouTube Studio.
    Asked with update(hide_old=True); the done ids are kept in the archive's hidden.json. Returns how many."""
    import youtube_account as ya
    t = ch.get("took_over") or {}
    now = now or time.time()
    folder_ = _archive_of(ch)
    if not t.get("hide") or t.get("hide_done") or not folder_ or now - t.get("hide_at", 0) < HIDE_EVERY:
        return 0
    path = os.path.join(folder_, "hidden.json")
    try:
        with open(path, encoding="utf-8") as f:
            done = json.load(f)
    except (OSError, ValueError):
        done = {}
    # Only YouTube's 11-character ids count as done: the first pass kept our own row ids, which hid nothing.
    done["videos"] = {k: v for k, v in (done.get("videos") or {}).items() if len(k) == 11}
    done.setdefault("playlists", {})

    def rows(name, default):
        try:
            with open(os.path.join(folder_, name), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default
    mine = ch.get("yt_channel") or ""
    # A row uploaded while the old card pointed at another of our channels (check_placement's "elsewhere") is
    # not on this channel: never touched from here.
    # YouTube's id is "video_id" ("id" is our own 12-character row id: the first pass on 5-nov-2026 asked YouTube
    # for 30 row ids, found nothing and marked them gone; nothing was changed on YouTube).
    vids = [r["video_id"] for r in sorted(rows("uploads.json", []), key=lambda r: r.get("created", 0))
            if r.get("video_id") and r.get("status") == "done" and r["video_id"] not in done["videos"]
            and not r.get("elsewhere") and (not mine or not r.get("yt_channel") or r["yt_channel"] == mine)]
    lists = [p for p in ((rows("engage.json", {}) or {}).get("playlists") or {}).values()
             if p and p not in done["playlists"]]
    n = 0
    with ya.use(account(ch["id"])):
        if not ya.status()["connected"]:
            return 0
        for kind, ids, fn in (("videos", vids, ya.unschedule), ("playlists", lists, ya.playlist_private)):
            for vid in ids:
                if n >= HIDE_PER_PASS or ya.quota_used() + ya.UPDATE_UNITS > HIDE_CEILING:
                    break
                try:
                    done[kind][vid] = "private" if fn(vid) else "gone"
                except Exception as e:  # noqa: BLE001 — the next pass tries it again
                    if re.search(r"\b403\b|forbidden|insufficientPermissions", str(e), re.I):
                        done[kind][vid] = "not this channel's"         # never tried again
                        n += 1
                        continue
                    log(f"⚠️ {ch['name']}: could not hide an old {kind[:-1]} ({str(e)[:80]}).")
                    break
                n += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(done, f, indent=1)
    left = len(vids) + len(lists) - n
    _change(ch["id"], lambda c: c.setdefault("took_over", {}).update(
        hide_at=int(now), hidden=len(done["videos"]) + len(done["playlists"]), hide_left=max(0, left),
        **({"hide_done": int(now)} if left <= 0 else {})))
    if n:
        log(f"🙈 {ch['name']}: {n} old {t.get('kind', '')} video(s)/playlist(s) set to private, {max(0, left)} to go.")
    return n


# ------------------------------------------------------------------ status

def today(now=None):
    return (now or datetime.now()).strftime("%Y-%m-%d")


def _jobs_on(ch, day, statuses=("running", "done", "uploaded")):
    """The day's jobs; a long video's teaser Short is extra, not one of the day's videos."""
    return [j for j in ch.get("jobs") or [] if j.get("day") == day and j.get("status") in statuses
            and j.get("format") not in EXTRA_FORMATS]


# Shorts of the history channel that come on top of its long videos.
# "mix": the song channel's weekly long mood mix (mood_mix.py): on top of the day's Shorts, never in their stats.
EXTRA_FORMATS = ("teaser", "today", "mix")
MIX_TIMEOUT = 150 * 60          # Lyria makes an instrumental mix's tracks one by one, then 30+ min of video


def today_short_due(ch, now=None):
    """True while the history channel still owes today's "Aaj ki tareekh"
    Short (history_today.py): on by default (daily_short), two tries a day."""
    if not KINDS.get(ch.get("kind"), {}).get("story") or not ch.get("daily_short", True):
        return False
    if ch.get("mode", "history") != "history":      # "on this day" is a history Short
        return False
    day = today(now)
    mine = [j for j in ch.get("jobs") or [] if j.get("format") == "today" and j.get("day") == day]
    return not any(j.get("status") in ("running", "done", "uploaded") for j in mine) and len(mine) < 2


TEASER_WINDOW = 20 * 3600     # a long video's files are kept this long for its Shorts
MOMENT_SHORTS = 2             # Shorts of a long video's best moments, after its opening teaser


def shorts_per_long(ch):
    """The teaser plus moment Shorts each long video gets. Fewer at 3 long
    videos a day: Shorts count toward the channel's daily upload limit (the
    main channel refused its 11th upload on 14-oct-2026)."""
    per_day = max(1, int(ch.get("per_day") or 1))
    return max(1, min(1 + MOMENT_SHORTS, 8 // per_day - 1))


def _parts(j):
    """Shorts started from this long video (a job from before moment Shorts says only 'teaser')."""
    return int(j.get("parts", 1 if j.get("teaser") else 0))


def teaser_due(ch, now=None):
    """The history channel's uploaded long video still owed a Short (its
    teaser, then its best moments), or None."""
    if not KINDS.get(ch.get("kind"), {}).get("story"):
        return None
    now = now or time.time()
    for j in sorted(ch.get("jobs") or [], key=lambda j: j.get("at", 0)):
        if (j.get("status") == "uploaded" and j.get("format") not in EXTRA_FORMATS and j.get("video_id")
                and _parts(j) < shorts_per_long(ch) and now - j.get("at", 0) < TEASER_WINDOW):
            return j
    return None


def waiting(ch):
    return [j for j in ch.get("jobs") or [] if j.get("status") == "done"]


def running(ch):
    return [j for j in ch.get("jobs") or [] if j.get("status") == "running"]


def keeps(job_id, cid, age_seconds):
    """Keep a job folder past the retention sweep while its Short waits to upload."""
    if age_seconds > KEEP_DAYS * 86400:
        return False
    ch = get(cid)
    return bool(ch) and any(j.get("job_id") == job_id and (
        j.get("status") in ("running", "done")
        # An uploaded long video stays until its Shorts are made from it, and
        # no longer than teaser_due would still offer it (its folder is GBs).
        or (j.get("status") == "uploaded" and KINDS.get(ch.get("kind"), {}).get("story")
            and j.get("format") not in EXTRA_FORMATS
            and _parts(j) < shorts_per_long(ch) and time.time() - j.get("at", 0) < TEASER_WINDOW))
        for j in ch.get("jobs") or [])


def connected(ch):
    import youtube_account
    with youtube_account.use(account(ch["id"])):
        return youtube_account.status()


def settling(st, now=None):
    """Until when a just-made connection waits (CONNECT_HOLD), or 0."""
    until = int(st.get("granted_at") or 0) + CONNECT_HOLD
    return until if st.get("connected") and (now or time.time()) < until else 0


PLACEMENT_DAYS = 14


def check_placement(cid, log=print, now=None):
    """This card's uploads that are not on the channel it is connected to
    now: they went up while the card pointed at another channel. One found
    public or scheduled on another of our channels is marked with that
    channel's name, so Today asks the owner to set it to private or delete
    it; the mark goes once it is private or gone. Read-only on YouTube (1
    unit per 50 videos per channel). Run after a connect and each learn."""
    import youtube_account
    now = now or time.time()
    with youtube_account.use(account(cid)):
        me = (youtube_account.status().get("channel") or {}).get("id")
        rows = [r for r in youtube_account.uploads() if r.get("status") == "done" and r.get("video_id")
                and now - r.get("created", 0) < PLACEMENT_DAYS * 86400]
        if not me or not rows:
            return []
        owners = _owners([r["video_id"] for r in rows])
    away = [r for r in rows if (owners.get(r["video_id"]) or {}).get("channel") != me]
    if not away and not any(r.get("elsewhere") for r in rows):
        return []
    # Which of our other channels holds them: a private video is visible only
    # to its own channel's token. One the owner deleted is found nowhere and
    # is left alone (it may as well have been deleted from this channel).
    found = {}
    for oid, acct in [("main", None)] + [(c["id"], account(c["id"])) for c in channels() if c["id"] != cid]:
        with youtube_account.use(acct):
            st = youtube_account.status()
            yid = (st.get("channel") or {}).get("id")
            if not (st.get("connected") and yid and away):
                continue
            try:
                seen = _owners([r["video_id"] for r in away])
            except Exception:  # noqa: BLE001 — that channel is not checked this time
                continue
        found.update({v: {**o, "title": (st["channel"].get("title") or "").strip()}
                      for v, o in seen.items() if o["channel"] == yid})
    marks, marked = {}, []
    for r in rows:
        o = found.get(r["video_id"])
        # Public or still scheduled there: the owner should act. Kept private
        # (set by the owner) it harms nothing and leaves the to-do list.
        if o and (o["privacy"] != "private" or o["publish_at"]):
            marked.append({**r, "elsewhere": o["title"]})
            if r.get("elsewhere") != o["title"]:
                marks[r["id"]] = {"elsewhere": o["title"]}
        elif r.get("elsewhere"):
            marks[r["id"]] = {"elsewhere": None}
    if marks:
        with youtube_account.use(account(cid)):
            youtube_account._mark_uploads(marks)
    for r in marked:
        if r["id"] in marks:
            log(f"⚠️ {cid}: '{r.get('title', '')[:60]}' went up on {r['elsewhere']}, not on this channel.")
    return marked


def _owners(video_ids):
    """video id -> {channel, privacy, publish_at} as YouTube says, for the
    videos this token can see (private ones only on their own channel)."""
    import youtube_account
    out = {}
    for i in range(0, len(video_ids), 50):
        items = youtube_account._get(f"{youtube_account.API}/videos",
                                     {"part": "snippet,status", "id": ",".join(video_ids[i:i + 50])}).get("items") or []
        out.update({v["id"]: {"channel": v["snippet"]["channelId"], "privacy": v["status"].get("privacyStatus"),
                              "publish_at": v["status"].get("publishAt")} for v in items})
    return out


def elsewhere(cid, now=None):
    """Uploads of this card found on another channel, for Today: still
    scheduled or public within PLACEMENT_DAYS."""
    import youtube_account
    now = now or time.time()
    with youtube_account.use(account(cid)):
        return [{"title": r.get("title", ""), "video_id": r["video_id"], "on": r["elsewhere"],
                 "publish_at": r.get("publish_at")}
                for r in youtube_account.uploads()
                if r.get("elsewhere") and now - r.get("created", 0) < PLACEMENT_DAYS * 86400]


UNVERIFIED_MINUTES = 14    # YouTube refuses videos over 15 min from an unverified channel
LONG_CHECK_EVERY = 6 * 3600


def long_minutes(ch, now=None):
    """The history channel's video length, capped at UNVERIFIED_MINUTES while
    YouTube says long uploads are not allowed (asked every 6 h, 1 unit);
    unknown (not connected, an error) keeps the owner's length."""
    import youtube_account
    minutes = int(ch.get("minutes", DEFAULT_MINUTES))
    if minutes <= UNVERIFIED_MINUTES:
        return minutes
    now = now or time.time()
    state = ch.get("long_uploads") or {}
    if now - state.get("at", 0) > LONG_CHECK_EVERY:
        try:
            with youtube_account.use(account(ch["id"])):
                answer = youtube_account.long_uploads() if youtube_account.status()["connected"] else "unknown"
        except Exception:  # noqa: BLE001 — unknown: keep the owner's length
            answer = "unknown"
        state = {"status": answer, "at": int(now)}
        _change(ch["id"], lambda c: c.update(long_uploads=state))
    return UNVERIFIED_MINUTES if state.get("status") in ("eligible", "disallowed") else minutes


def summary(ch):
    import youtube_account
    with youtube_account.use(account(ch["id"])):
        yt = youtube_account.status()
        rows = sorted(youtube_account.uploads(), key=lambda r: r.get("created", 0), reverse=True)
    day = today()
    out = {k: v for k, v in ch.items() if k not in ("jobs", "ideas", "used")}
    long = bool(KINDS.get(ch["kind"], {}).get("long"))
    if KINDS.get(ch["kind"], {}).get("story"):
        out.update(minutes=ch.get("minutes", DEFAULT_MINUTES), lang=ch.get("lang", "urdu"),
                   mode=ch.get("mode", "history"))
    if ch["kind"] == "quran":
        import quran_videos as qv
        out.update(quran=qv.settings_of(ch.get("quran")),
                   quran_options={"reciters": [[k, v] for k, v in qv.RECITERS.items()],
                                  "urdu": [[k, v] for k, v in qv.URDU.items()],
                                  "english": [[k, v] for k, v in qv.ENGLISH.items()]})
    if ch["kind"] == "music":
        import engage
        import music_moods
        settings = music_moods.settings_of(ch.get("moods"))
        try:
            lists = (engage.load(account(ch["id"])) or {}).get("playlists") or {}
        except Exception:  # noqa: BLE001 — the card shows the moods without links
            lists = {}
        out.update(moods=music_moods.summary(settings, ch.get("jobs"), lists), mood_settings=settings,
                   next_mood=ch.get("next_mood") or "", next_mix=ch.get("next_mix") or "",
                   urdu_share=music_moods.urdu_share(ch),
                   mix_status=music_moods.mix_summary(settings, ch.get("jobs")),
                   mix_settings={k: music_moods.mix_setting(settings, k)
                                 for k in ("mixes", "mix_minutes", "mix_budget")})
    out.update({
        "max_per_day": cap(ch), "long": long,
        **engage_settings(ch), "match_watch": bool(ch.get("match_watch", True)),
        "meta_page": ch.get("meta_page") or "", "meta_fb": bool(ch.get("meta_fb", True)),
        "meta_ig": bool(ch.get("meta_ig", True)),
        "meta_ig_mode": ch.get("meta_ig_mode") or "auto", "meta_ig_now": meta_ig_mode(ch),
        "kind_label": ("Horror stories (long videos)" if ch["kind"] == "history" and ch.get("mode") == "horror"
                       else KINDS.get(ch["kind"], {}).get("label", ch["kind"])),
        "youtube": yt, "made_today": len(_jobs_on(ch, day)),
        "uploaded_today": sum(1 for r in rows if r.get("status") == "done"
                              and today(datetime.fromtimestamp(r.get("created", 0))) == day),
        "waiting": len(waiting(ch)), "running": [j.get("label") for j in running(ch)],
        "jobs": sorted(ch.get("jobs") or [], key=lambda j: j.get("at", 0), reverse=True)[:12],
        "uploads": rows[:12], "ideas_left": len(ch.get("ideas") or []),
        "plans_ideas": ch["kind"] in PLANNERS or ch["kind"] == "quran",
        "up_next": [i.get("text", "") for i in (ch.get("ideas") or [])[:UP_NEXT_SHOWN]],
        "up_next_series": [f"{i['series']}, part {i['part']} of {i['parts']}" if i.get("series") else ""
                           for i in (ch.get("ideas") or [])[:UP_NEXT_SHOWN]],
    })
    try:
        import channel_doctor
        import niche_research
        out["doctor"] = channel_doctor.run(ch, rows, niche_research.load(niche_of(ch)), yt)
    except Exception as e:  # noqa: BLE001 — the card shows without its checks
        out["doctor"] = [{"key": "error", "question": "Channel checks", "status": "unknown",
                          "finding": f"Could not run the checks ({type(e).__name__}).", "evidence": [], "next": ""}]
    return out


UP_NEXT_SHOWN = 8


def _owner_idea(kind, text):
    """An idea the owner typed, in the planner's shape. Cricket needs its
    kind: "India vs Pakistan, Asia Cup final" is a match, "Babar vs Kohli" a
    player fight, "Top 5 ..." a ranking, anything else a topic."""
    if kind == "cricket" and re.match(r"\s*top\s*(5|five|10|ten)\b", text, re.I):
        return {"kind": "ranking", "text": text, "owner": True}
    if kind == "cricket" and re.search(r"\bvs\.?\b|\bversus\b", text, re.I):
        return {"kind": "match" if re.search(r",|\b(final|semi|cup|trophy|series|test|odi|t20|league|psl|ipl)\b",
                                             text, re.I) else "versus", "text": text, "owner": True}
    return {"kind": "topic", "text": text, "owner": True}


def _remix_link(text):
    import viral_remix
    return bool(viral_remix.video_id(text))


def add_idea(cid, text):
    """The owner's own topic, made next. A YouTube link is studied first (~20 s): blocking."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:140]
    ch = get(cid)
    if not ch or (ch["kind"] not in PLANNERS and ch["kind"] != "quran"):
        raise ValueError("This channel picks its own topics.")
    if not text:
        raise ValueError("Write a topic first.")
    if ch["kind"] == "quran":
        import quran_videos
        idea = quran_videos.parse_request(text)
        if not idea:
            raise ValueError("Write a surah's name or number (Surah Yaseen, 36), or ayat like 2:255 or 2:1-20.")
        text = idea["text"]
    elif _remix_link(text):
        # A YouTube link: study that video and make our own on its angle (viral_remix).
        import short_kit
        import viral_remix
        idea = {**viral_remix.as_idea(viral_remix.study(short_kit.gemini(), text, ch["kind"])), "owner": True}
        text = idea["text"]
    else:
        idea = _owner_idea(ch["kind"], text)

    def fn(c):
        rest = [i for i in c.get("ideas") or [] if i.get("text", "").lower() != text.lower()]
        # A just-finished match (urgent) still goes first: it is news for a few hours only.
        urgent = [i for i in rest if i.get("urgent")]
        c["ideas"] = urgent + [idea] + [i for i in rest if not i.get("urgent")]
    return _change(cid, fn)


def niche_of(ch):
    """The research niche of a card (niche_research.NICHES): its kind, or "explainer" for the
    long channel in explainer mode; the main channel is "comedy"."""
    if not ch or ch.get("id") == "main":
        return "comedy"
    if ch.get("kind") == "history" and ch.get("mode") in ("explainer", "horror"):
        return ch["mode"]
    return ch.get("kind")


def remix_idea(ch, log=print):
    """Today's idea from the niche's studied viral videos (niche_research), at most
    viral_remix.PER_DAY a day per channel, or None. ``remix_days`` counts what was taken."""
    import niche_research
    import viral_remix
    if not niche_research.enabled() or os.environ.get("VIRAL_REMIX", "1") == "0" \
            or viral_remix.made_today(ch) >= viral_remix.PER_DAY:
        return None
    idea = niche_research.next_idea(niche_of(ch), used=ch.get("used") or [])
    if idea:
        day = time.strftime("%Y-%m-%d")
        _change(ch["id"], lambda c: c.update(remix_days={day: viral_remix.made_today(c) + 1}))
        log(f"🧪 {ch['name']}: next video rides a viral one: {idea['text']}")
    return idea


def _remix_first(ch, client_fn, log=print):
    """Once a day a planned channel (cricket, controversy, history) makes its own video on the angle
    of a viral one its research agent studied (niche_research), before the planner's ideas. Urgent
    match results and the owner's own ideas still go first. The study happened in the research pass,
    so this takes no network call."""
    if ch["kind"] not in PLANNERS:
        return ch
    head = (ch.get("ideas") or [{}])[0]
    if head.get("urgent") or head.get("owner") or head.get("remix"):
        return ch
    idea = remix_idea(ch, log)
    if not idea:
        return get(ch["id"])
    if ch["kind"] == "cricket" and idea["kind"] not in ("topic", "match", "versus", "ranking"):
        idea["kind"] = "topic"
    if ch["kind"] != "cricket":
        idea["kind"] = "topic"

    def fn(c):
        rest = [i for i in c.get("ideas") or [] if i.get("text", "").lower() != idea["text"].lower()]
        urgent = [i for i in rest if i.get("urgent")]
        c["ideas"] = urgent + [idea] + [i for i in rest if not i.get("urgent")]
    _change(ch["id"], fn)
    return get(ch["id"])


def drop_idea(cid, text):
    """Take an idea out of the queue; it goes on the avoid list, so the planner
    does not bring it back."""
    text = str(text or "")

    def fn(c):
        ideas = c.get("ideas") or []
        # A series without one of its parts no longer tells one story: the rest goes too.
        series = next((i.get("series") for i in ideas if i.get("text") == text and i.get("series")), None)
        gone = [i.get("text", "") for i in ideas if i.get("text") == text or (series and i.get("series") == series)]
        c["ideas"] = [i for i in ideas if i.get("text", "") not in gone]
        c["used"] = ((c.get("used") or []) + [t[:140] for t in gone or [text]]
                     + [f"quran:{i['id']}" for i in ideas if i.get("kind") == "quran" and i.get("id")
                        and i.get("text") in gone])[-300:]
    return _change(cid, fn)


# ------------------------------------------------------------------ learning

def _median(xs):
    return round(statistics.median(xs)) if xs else 0


def learn(ch, log=print):
    """Read this channel's own numbers and keep what they say in ch["stats"]."""
    import youtube_account
    # Stamped first: a failing read (an expired token) waits for the next turn
    # instead of being retried every minute.
    _change(ch["id"], lambda c: c.update(last_learn=int(time.time())))
    acct = account(ch["id"])
    with youtube_account.use(acct):
        if not youtube_account.status()["connected"]:
            return ch
        since = time.time() - LOOKBACK_DAYS * 86400
        rows = [r for r in youtube_account.uploads() if r.get("video_id") and r.get("status") == "done"
                and r.get("created", 0) >= since and not r.get("elsewhere")]   # another channel's numbers
        numbers = {}
        for k in range(0, len(rows), 50):
            part = rows[k:k + 50]
            res = youtube_account._get(f"{youtube_account.API}/videos", {
                "part": "statistics,status,snippet", "id": ",".join(r["video_id"] for r in part)})
            for v in res.get("items") or []:
                st = v.get("statistics") or {}
                numbers[v["id"]] = {"views": int(st.get("viewCount") or 0), "likes": int(st.get("likeCount") or 0),
                                    "comments": int(st.get("commentCount") or 0),
                                    "public": (v.get("status") or {}).get("privacyStatus") == "public",
                                    "published": (v.get("snippet") or {}).get("publishedAt")}
        now = datetime.now(timezone.utc)
        mature = []
        for r in rows:
            n = numbers.get(r["video_id"])
            if not n:
                continue
            r.update(views=n["views"], likes=n["likes"], comments=n["comments"], public=n["public"])
            try:
                age = now - datetime.fromisoformat((n["published"] or "").replace("Z", "+00:00"))
            except ValueError:
                youtube_account._save_upload(r)
                continue
            if "views_48h" not in r and FAIR_AGE <= age < FAIR_AGE + FAIR_WINDOW:
                r["views_48h"] = n["views"]
            youtube_account._save_upload(r)
            if n["public"] and age >= timedelta(hours=MATURE_HOURS):
                mature.append(r)
        # How much of each video people watch: on a small channel it moves
        # long before the views do, and it is what Shorts are ranked by.
        try:
            watched = youtube_account.video_analytics(LOOKBACK_DAYS) if mature else {}
        except Exception:  # noqa: BLE001 — retention is a bonus over the views
            watched = {}
        for r in mature:
            a = watched.get(r["video_id"])
            if a:
                r.update(retention=a["avg_percent"], watch_seconds=a["avg_seconds"])
                if a.get("engaged") is not None and a.get("a_views"):
                    r.update(stayed=round(100 * a["engaged"] / a["a_views"], 1), a_views=a["a_views"])
                youtube_account._save_upload(r)
        insights = _insights(ch, mature, log)
    lifetime = [r["views"] for r in mature]
    # Decisions compare views at the same age (views_48h) where a Short has that number.
    mature = [{**r, "views": r.get("views_48h", r["views"])} for r in mature]
    by_format, kept = {}, {}
    for r in mature:
        by_format.setdefault(r.get("format") or "other", []).append(r["views"])
        if r.get("retention") is not None:
            kept.setdefault(r.get("format") or "other", []).append(r["retention"])
    # Teaser Shorts get Shorts-sized views: the best and worst lists that steer
    # the next long videos compare long videos only.
    ranked = sorted([r for r in mature if r.get("format") not in EXTRA_FORMATS], key=lambda r: r["views"],
                    reverse=True)
    stats = {"at": int(time.time()), "tracked": len(rows), "counted": len(mature),
             "views": sum((numbers.get(r["video_id"]) or {}).get("views", 0) for r in rows),
             "median": _median(lifetime),
             "formats": {f: {"shorts": len(v), "median": _median(v),
                             **({"watched": _median(kept[f])} if kept.get(f) else {})}
                         for f, v in by_format.items()},
             "watched": _median([x for v in kept.values() for x in v]) if kept else None,
             "best": [f"{r['title'][:80]} ({r['views']} views)" for r in ranked[:5]],
             "worst": [f"{r['title'][:80]} ({r['views']} views)" for r in ranked[-5:][::-1]]
             if len(ranked) >= 8 else []}
    # The A/B tests (ab_choice): views and % watched per side, Shorts since AB_SINCE only.
    stats["ab"] = ab_stats(mature)
    stats["hooks"] = hook_lessons(mature)
    stats["hours"] = _by_hour(mature)
    stats.update(insights)

    def fn(c):
        c["stats"] = stats
        c["last_learn"] = int(time.time())
    log(f"📈 {ch['name']}: {stats['counted']} Shorts counted, median {stats['median']} views.")
    return _change(ch["id"], fn)


CURVE_MIN_VIEWS = 50        # the retention curve comes back empty for a video with very few views
CURVE_PER_PASS = 6          # curves read per learn pass (one Analytics call each)
CURVE_REFRESH = 7 * 86400   # a video's curve is read again weekly in its first month
DAILY = 20 * 3600


def _insights(ch, mature, log=print):
    """yt_insights for a learn pass (inside the channel's youtube_account.use): retention curves on the upload
    rows, and once a day the channel's search terms and (long videos) thumbnail reach. Returns the stats keys;
    a failing read keeps the last ones, never stops the pass."""
    import youtube_account
    import yt_insights
    old = ch.get("stats") or {}
    now = time.time()
    out = {k: old[k] for k in ("search", "search_at", "reach_at", "reach_error") if k in old}
    due = [r for r in mature if (r.get("a_views") or r.get("views") or 0) >= CURVE_MIN_VIEWS and r.get("seconds")
           and (not r.get("curve_at") or (now - r["curve_at"] > CURVE_REFRESH
                                          and now - r.get("created", now) < 30 * 86400))]
    for r in sorted(due, key=lambda r: r.get("curve_at") or 0)[:CURVE_PER_PASS]:
        try:
            summary = yt_insights.curve_summary(yt_insights.retention(r["video_id"]), float(r["seconds"]))
        except Exception as e:  # noqa: BLE001 — curves are a bonus over the views
            log(f"   ℹ️ {ch['name']}: no retention curve ({str(e)[:80]}).")
            break
        r["curve_at"] = int(now)
        if summary:
            r["curve"] = summary
        youtube_account._save_upload(r)
    long = bool(KINDS.get(ch["kind"], {}).get("long"))
    out["retention_lesson"] = yt_insights.retention_lesson(mature, long=long)
    # A channel handed over from another card (hand_over) reads only the searches since then: the 90 days
    # before were the old videos' (the money card heard "mushkil paheliyan", 5-nov-2026), and those words
    # would steer its new titles.
    took = (ch.get("took_over") or {}).get("at") or 0
    days = min(90, int((now - took) // 86400)) if took else 90
    if took and days < 2:
        out["search"], out["search_at"] = [], int(now)
    elif now - old.get("search_at", 0) > DAILY:
        try:
            out["search"] = yt_insights.search_terms(days=days)
        except Exception as e:  # noqa: BLE001
            log(f"   ℹ️ {ch['name']}: no search terms ({str(e)[:80]}).")
        out["search_at"] = int(now)
    if long and now - old.get("reach_at", 0) > DAILY:
        out["reach_at"] = int(now)
        try:
            totals = yt_insights.reach(ch["id"])
            out.pop("reach_error", None)
            for r in mature:
                t = totals.get(r["video_id"])
                if t and t["impressions"]:
                    r.update(impressions=t["impressions"], ctr=t["ctr"])
                    youtube_account._save_upload(r)
        except Exception as e:  # noqa: BLE001 — most often the Reporting API is not switched on yet
            out["reach_error"] = str(e)[:200]
    return out


TIP_MIN = 4           # Shorts counted at an hour before that hour is compared
TIP_LEAD = 1.5        # the best hour's median must beat the worst's by this much...
TIP_GAP = 10          # ...and by this many views, so 3 against 1 is not "3x better"


def _by_hour(rows):
    """{"HH": {"shorts", "median"}} of counted Shorts by the local hour they went
    public. Long videos are left out: their views are not comparable."""
    import youtube_account
    out = {}
    for r in rows:
        if r.get("genre") in youtube_account.LONG_GENRES or not r.get("publish_at"):
            continue
        try:
            hour = datetime.fromisoformat(r["publish_at"]).astimezone().hour
        except ValueError:
            continue
        out.setdefault(f"{hour:02d}", []).append(r["views"])
    return {h: {"shorts": len(v), "median": _median(v)} for h, v in sorted(out.items())}


def time_tip(ch):
    """A posting-time suggestion from the channel's own numbers, or None:
    the weakest posting hour moves next to the strongest one. Only says
    something once both hours have TIP_MIN Shorts and a clear gap."""
    hours = {int(h): v for h, v in ((ch.get("stats") or {}).get("hours") or {}).items()
             if v.get("shorts", 0) >= TIP_MIN}
    if len(hours) < 2:
        return None
    best = max(hours, key=lambda h: hours[h]["median"])
    worst = min(hours, key=lambda h: hours[h]["median"])
    hi, lo = hours[best]["median"], hours[worst]["median"]
    if hi < max(lo, 1) * TIP_LEAD or hi - lo < TIP_GAP:
        return None
    taken = {int(t.split(":")[0]) for t in ch.get("post_times") or []}
    new = next((h % 24 for h in (best + 1, best - 1, best + 2, best - 2) if h % 24 not in taken), None)
    if new is None:
        return None
    old = next((t for t in ch.get("post_times") or [] if int(t.split(":")[0]) == worst), f"{worst:02d}:00")
    times = sorted({t for t in ch.get("post_times") or [] if t != old} | {f"{new:02d}:00"})
    return {"best": f"{best:02d}:00", "best_median": hi, "worst": old, "worst_median": lo,
            "new": f"{new:02d}:00", "post_times": times,
            "text": (f"Shorts posted at {best:02d}:00 get a median of {hi} views, at {old} only {lo}. "
                     f"Move the {old} time to {new:02d}:00?")}


# The long-video length tip: how much of each video people watch
# (YouTube Analytics averageViewPercentage, median over the counted videos).
LENGTH_MIN_VIDEOS = 4
LENGTH_LOW, LENGTH_HIGH = 30, 50       # % watched
LENGTH_SHORTEST = 5


def length_tip(ch):
    """A length suggestion for a long-video channel, or None: shorter when
    people leave early, longer when they watch most of each video."""
    if not KINDS.get(ch.get("kind"), {}).get("story"):
        return None
    f = ((ch.get("stats") or {}).get("formats") or {}).get(KINDS[ch["kind"]].get("format", "history")) or {}
    watched = f.get("watched")
    if watched is None or f.get("shorts", 0) < LENGTH_MIN_VIDEOS:
        return None
    minutes = int(ch.get("minutes", DEFAULT_MINUTES))
    status = (ch.get("long_uploads") or {}).get("status")
    top = UNVERIFIED_MINUTES if status in ("eligible", "disallowed") else MINUTES_RANGE[1]
    minutes = min(minutes, top)
    w = round(watched)
    if watched < LENGTH_LOW and minutes > LENGTH_SHORTEST + 1:
        new = max(LENGTH_SHORTEST, round(minutes * 0.7))
        return {"minutes": new, "watched": w,
                "text": f"People watch {w}% of your long videos. Shorter ones usually keep more of them: "
                        f"make them {new} minutes instead of {minutes}?"}
    if watched > LENGTH_HIGH and minutes + 3 <= top:
        new = minutes + 3
        return {"minutes": new, "watched": w,
                "text": f"People watch {w}% of your long videos, which is a lot. Longer ones earn more watch "
                        f"time from the same viewers: make them {new} minutes instead of {minutes}?"}
    return None


AB_MIN = 10           # Shorts counted per side before a side can win (was 6)
AB_LEAD = 1.2         # the winner's median must beat the other's by this much
AB_P = 0.1            # and a permutation test on log views must say it is not luck
AB_EXPLORE = 0.2
# The tests restart when the treatment changes. From 22-oct-2026 22:00 the end card is 1.5 s (was 3 s)
# and every script is new; the first run of the end card test (8-20 Shorts a side, medians 0-12 views)
# showed nothing (permutation p 0.55-0.95 on all three channels).
AB_SINCE = 1792688400
# Each test: the channel kinds it runs on and its two sides (the first is today's default).
EXPERIMENTS = {
    "outro": {"kinds": ("cricket", "controversy", "quiz", "money"), "arms": (True, False),
              "label": "FOLLOW end card", "names": ("with", "without")},
    # Quiz countdowns were cut by a second on 22-oct-2026 (the median viewer left at 7 s, about when
    # the first one starts): "long" puts the second back, so the cut is measured, not assumed.
    "timer": {"kinds": ("quiz",), "arms": ("short", "long"), "label": "quiz countdown",
              "names": ("1 s shorter", "as before")},
    # Long videos' thumbnails (5-nov-2026): the text on the left (as always) or on the right, judged by the
    # click-through rate of the Reporting API's reach reports (yt_insights.reach), not by views.
    "thumb": {"kinds": ("history",), "arms": ("left", "right"), "label": "thumbnail text side",
              "names": ("text left", "text right"), "metric": "ctr"},
    # Footage cut pace (5-nov-2026): our usual cut every broll.CUT seconds, or the length that gives our
    # Shorts the median shot of the niche's winners as teardown.py measures their files (pace_now). Runs
    # only once both sides are measured and differ by 15% or more.
    "pace": {"kinds": ("cricket", "controversy", "music"), "arms": ("ours", "rivals"), "label": "cut pace",
             "names": ("our usual cuts", "the winners' pace")},
    # Cartoon episode length (toon_shorts.LENGTHS, 5-nov-2026): our Shorts lose half their viewers by 0:07-0:12,
    # so a 25-32 s episode is measured against the 35-45 s one, not assumed better.
    "toonlen": {"kinds": ("toons",), "arms": ("long", "short"), "label": "episode length",
                "names": ("35-45 seconds", "25-32 seconds")},
}
AB_KINDS = EXPERIMENTS["outro"]["kinds"]


def _arm(v):
    return str(v).lower()


def perm_p(a, b, n=2000, seed=7):
    """Two-sided permutation p-value of the difference in mean log(1+views): how often a random
    split of the same Shorts differs as much. Views are heavy-tailed, hence the log; no scipy here."""
    import math
    la, lb = [math.log1p(x) for x in a], [math.log1p(x) for x in b]
    if not la or not lb:
        return 1.0
    obs = abs(sum(la) / len(la) - sum(lb) / len(lb))
    pool, k, hits = la + lb, len(la), 0
    rnd = random.Random(seed)
    for _ in range(n):
        rnd.shuffle(pool)
        if abs(sum(pool[:k]) / k - sum(pool[k:]) / (len(pool) - k)) >= obs - 1e-12:
            hits += 1
    return hits / n


HOOK_MIN_VIEWS = 10   # fewer starts than this and one viewer moves "stayed" by 10+ points
HOOK_GAP = 10         # the best must beat the worst by this many points, or it is noise


def hook_lessons(rows, n=3):
    """{"best": [...], "worst": [...]} openings of this channel's own Shorts ranked by how many viewers
    stayed past the first seconds (engagedViews / views), for the writer prompts (HOOK_LESSONS). Shorts
    from before the opening line was stored teach with their title. {} until there is a clear gap."""
    seen = [r for r in rows if r.get("stayed") is not None and (r.get("a_views") or 0) >= HOOK_MIN_VIEWS
            and r.get("format") not in EXTRA_FORMATS and (r.get("opening") or r.get("title"))]
    if len(seen) < 2 * n:
        return {}
    seen.sort(key=lambda r: r["stayed"], reverse=True)
    best, worst = seen[:n], seen[-n:][::-1]
    if best[0]["stayed"] - worst[0]["stayed"] < HOOK_GAP:
        return {}

    def line(r):
        said = (r.get("opening") or r.get("title") or "").strip()[:110]
        return f"\"{said}\" ({r['stayed']:.0f}% stayed)"
    return {"best": [line(r) for r in best], "worst": [line(r) for r in worst]}


def hook_text(stats):
    """The lessons as one prompt line ("" without them): the openings that kept viewers, where the channel's
    viewers leave (retention curves) and what they searched (yt_insights)."""
    import yt_insights
    stats = stats or {}
    h = stats.get("hooks") or {}
    parts = []
    if h.get("best"):
        parts.append(("THIS CHANNEL'S OWN VIEWERS (share who stayed past the first seconds): openings that kept them: "
                      + "; ".join(h["best"]) + ". Openings they swiped away from: " + "; ".join(h["worst"])
                      + ". Learn what the first kind does differently; never copy their words.")[:1500])
    if stats.get("retention_lesson"):
        parts.append(stats["retention_lesson"][:400])
    hint = yt_insights.search_hint([tuple(t) for t in stats.get("search") or []])
    if hint:
        parts.append(hint[:500])
    return "\n".join(parts)


def ab_stats(rows, since=AB_SINCE):
    """{test: {side: {"shorts", "median", "watched"?}, "p": p}} over counted Shorts since ``since``."""
    out = {}
    for key, exp in EXPERIMENTS.items():
        metric = exp.get("metric", "views")
        arms = {}
        for r in rows:
            if r.get(key) is None or r.get("format") == "teaser" or r.get("created", 0) < since:
                continue
            if r.get(metric) is None:
                continue                   # a thumbnail without reach numbers yet counts for nothing
            arms.setdefault(_arm(r[key]), []).append(r)
        if not arms:
            continue
        res = {}
        mid = _median if metric == "views" else (lambda xs: round(statistics.median(xs), 2) if xs else 0)
        for a, rs in arms.items():
            kept = [r["retention"] for r in rs if r.get("retention") is not None]
            res[a] = {"shorts": len(rs), "median": mid([r[metric] for r in rs]),
                      **({"watched": _median(kept)} if kept else {})}
        if len(arms) == 2:
            (_a, ra), (_b, rb) = arms.items()
            res["p"] = round(perm_p([r[metric] for r in ra], [r[metric] for r in rb]), 3)
        out[key] = res
    return out


def ab_winner(seen, key):
    """The winning side of a test, or None: both sides AB_MIN counted, a clear lead in median views,
    a permutation p under AB_P, and the winner not watched less."""
    a, b = EXPERIMENTS[key]["arms"]
    sa, sb = seen.get(_arm(a)) or {}, seen.get(_arm(b)) or {}
    if min(sa.get("shorts", 0), sb.get("shorts", 0)) < AB_MIN or seen.get("p", 1.0) > AB_P:
        return None
    for win, lose, side in ((sa, sb, a), (sb, sa, b)):
        if win["median"] > lose["median"] and win["median"] >= lose["median"] * AB_LEAD \
                and win.get("watched", 0) >= lose.get("watched", 0) - 5:
            return side
    return None


def ab_choice(ch, key="outro", rnd=random):
    """The side of test ``key`` for the next Short. The end card asks for a follow but stops a Short
    from looping (replays count as views), so each channel tests it on its own Shorts. Alternate until
    a side wins (ab_winner), then the winner most of the time; no winner keeps alternating."""
    exp = EXPERIMENTS[key]
    seen = ((ch.get("stats") or {}).get("ab") or {}).get(key) or {}
    win = ab_winner(seen, key)
    if win is not None and rnd.random() >= AB_EXPLORE:
        return win
    a, b = exp["arms"]
    made = [j.get(key) for j in ch.get("jobs") or [] if j.get(key) is not None
            and j.get("status") in ("running", "done", "uploaded") and j.get("at", AB_SINCE) >= AB_SINCE]
    return a if made.count(a) <= made.count(b) else b


def ab_line(ch):
    """One line per running test for the week report, or []."""
    out = []
    for key, res in (((ch.get("stats") or {}).get("ab")) or {}).items():
        exp = EXPERIMENTS.get(key)
        if not exp or ch.get("kind") not in exp["kinds"]:
            continue
        parts = []
        ctr = exp.get("metric") == "ctr"
        for side, name in zip(exp["arms"], exp["names"]):
            s = res.get(_arm(side)) or {}
            parts.append(f"{name}: {s.get('shorts', 0)} {'videos' if ctr else 'Shorts'}, median {s.get('median', 0)}"
                         + ("% click rate" if ctr else " views")
                         + (f", {s['watched']:.0f}% watched" if s.get("watched") is not None else ""))
        win = ab_winner(res, key)
        verdict = (f"winner: {exp['names'][exp['arms'].index(win)]}" if win is not None else
                   f"no winner yet (needs {AB_MIN} a side and a clear gap)")
        out.append(f"  Test, {exp['label']}: " + "; ".join(parts) + f". {verdict}.")
    return out


def pick_format(ch, options, rnd=random):
    """The next format or style: each tried MIN_FOR_LEARNING times first, then
    the best median views most of the time, something else EXPLORE of it."""
    made = {}
    for j in ch.get("jobs") or []:
        if j.get("status") in ("running", "done", "uploaded"):
            made[j.get("format")] = made.get(j.get("format"), 0) + 1
    fresh = [o for o in options if made.get(o, 0) < MIN_FOR_LEARNING]
    if fresh:
        return min(fresh, key=lambda o: (made.get(o, 0), rnd.random()))
    seen = (ch.get("stats") or {}).get("formats") or {}
    scored = [o for o in options if (seen.get(o) or {}).get("shorts", 0) >= MIN_FOR_LEARNING]
    if not scored or rnd.random() < EXPLORE:
        return rnd.choice(options)
    return max(scored, key=lambda o: format_score(seen[o]))


def format_score(v):
    """Median views weighted by how much of it people watch (50% is neutral):
    100 views watched to 90% beat 120 views swiped away at 40%."""
    return v.get("median", 0) * (0.5 + (v.get("watched") if v.get("watched") is not None else 50) / 100)


# ------------------------------------------------------------------ making

def _look(ch):
    yt = connected(ch).get("channel") or {}
    handle = ch.get("handle") or (yt.get("handle") or "")
    if handle and not handle.startswith("@"):
        handle = "@" + handle
    return {"output_format": "framed", "frame_handle": handle, "frame_bg_color": ch.get("color") or "#14142B",
            "frame_outro": True, "acknowledged": True, "channel": ch["id"]}


def next_payload(ch, client_fn, log=print):
    """(payload, meta) for the channel's next Short, or (None, None); the
    Shorts channels also get their A/B sides (ab_choice): the end card on every
    Shorts channel (songs and long videos have none), the countdown on quizzes."""
    payload, meta = _next_payload(ch, client_fn, log)
    if payload and meta.get("format") != "teaser":
        if ch["kind"] in EXPERIMENTS["outro"]["kinds"]:
            payload["frame_outro"] = meta["outro"] = ab_choice(ch, "outro")
        if ch["kind"] in EXPERIMENTS["thumb"]["kinds"] and meta.get("format") == "history":
            payload["history_thumb"] = meta["thumb"] = ab_choice(ch, "thumb")
        if ch["kind"] in EXPERIMENTS["timer"]["kinds"]:
            meta["timer"] = ab_choice(ch, "timer")
            payload["quiz_timer_add"] = 0 if meta["timer"] == "short" else 1
        if ch["kind"] in EXPERIMENTS["toonlen"]["kinds"] and meta.get("format") == "toons":
            payload["toon_length"] = meta["toonlen"] = ab_choice(ch, "toonlen")
        cut = pace_now(ch) if ch["kind"] in EXPERIMENTS["pace"]["kinds"] else None
        if cut:
            meta["pace"] = ab_choice(ch, "pace")
            if meta["pace"] == "rivals":
                payload["broll_cut"] = cut
    if payload and hook_text(ch.get("stats")):
        payload["hook_lessons"] = hook_text(ch.get("stats"))
    if payload:
        import niche_research
        book = niche_research.playbook_text(niche_of(ch))
        if book:
            payload["niche_playbook"] = book
    return payload, meta


def pace_now(ch):
    """The winners' footage cut length for this card's niche (teardown.pace_cut), or None."""
    try:
        import niche_research
        import teardown
        return teardown.pace_cut(niche_research.load(niche_of(ch)), teardown.BASE_CUT)
    except Exception:  # noqa: BLE001 — no test this time
        return None


def _next_payload(ch, client_fn, log=print):
    kind = ch["kind"]
    look = _look(ch)
    stats = ch.get("stats") or {}
    long_video = teaser_due(ch)
    if long_video:
        # The uploaded long video's Shorts come before the next long video:
        # part 0 is its opening, parts 1-2 its best moments (history_videos.moments_for).
        part = _parts(long_video)
        _set_job(ch["id"], long_video["job_id"], teaser="started", parts=part + 1)
        return ({**look, "genre": "history", "history_teaser_of": long_video["job_id"],
                 "history_video_id": long_video["video_id"], "history_lang": ch.get("lang", "urdu"),
                 "history_teaser_part": part, "bg_music": True, "history_mode": ch.get("mode", "history")},
                {"label": f"{'Moment ' + str(part) if part else 'Teaser'}: {long_video.get('label', '')}"[:120],
                 "format": "teaser", "part": part, "topic": long_video.get("topic"),
                 "teaser_of": long_video["job_id"], "publish_after": long_video.get("slot")})
    if today_short_due(ch):
        made = [u[6:] for u in ch.get("used") or [] if str(u).startswith("today:")]
        return ({**look, "genre": "history", "history_today": True, "history_lang": ch.get("lang", "urdu"),
                 "history_avoid": made[-40:], "bg_music": True},
                {"label": f"Aaj ki tareekh: {datetime.now():%d %B}", "format": "today", "topic": ""})
    if kind == "quran":
        return _quran_payload(ch, look, log)
    if kind == "toons" and mix_due(ch):
        # The week's episodes as one long video (toon_mix.py): watch hours, on top of the day's Shorts.
        import toon_mix
        vol = len(toon_mix.mixes()) + 1
        count = len(toon_mix.pending()[:toon_mix.MAX_EPISODES])
        return ({**look, "genre": "toons", "toon_mix": True, "frame_outro": False},
                {"label": f"Compilation vol. {vol}: {count} episodes", "format": "mix", "topic": "compilation"})
    if kind in PLANNERS:
        if ch.get("mode") == "explainer" and ch.get("ideas"):
            # News goes stale: ideas planned more than a day and a half ago are dropped.
            import trend_explainer
            keep = trend_explainer.fresh(ch["ideas"])
            if len(keep) < len(ch["ideas"]):
                _change(ch["id"], lambda c: c.update(ideas=trend_explainer.fresh(c.get("ideas"))))
                ch = get(ch["id"])
        if not ch.get("ideas"):
            if time.time() - _ideas_failed.get(ch["id"], 0) < IDEAS_RETRY:
                return None, None
            import importlib
            planner = importlib.import_module(PLANNERS[kind])
            # The history channel also hears the owner's topic wishes, its language and length.
            extra = ({"notes": ch.get("notes") or "", "lang": ch.get("lang", "urdu"),
                      "minutes": ch.get("minutes", DEFAULT_MINUTES),
                      **({"mode": ch["mode"]} if ch.get("mode") in ("explainer", "horror") else {})}
                     if kind == "history" else {"notes": ch.get("notes") or ""} if kind in ("money", "toons")
                     else {})
            # Topics viewers asked for in comments (engage.auto_replies); the
            # planner's own rules still decide whether any of them is made.
            import engage
            import inspect
            asked = engage.requests(account(ch["id"]))
            # ...and what viewers of this niche's viral videos asked for under them (niche_research).
            try:
                import niche_research
                asked = asked + [f"{a} (asked under a viral video in this niche)"
                                 for a in niche_research.asks(niche_of(ch))][:max(0, 7 - len(asked))]
            except Exception:  # noqa: BLE001 — the planner works without them
                pass
            if asked and "requests" in inspect.signature(planner.channel_ideas).parameters:
                extra["requests"] = asked
            try:
                got = planner.channel_ideas(client_fn(), ch["per_day"], avoid=ch.get("used") or [],
                                            best=stats.get("best") or [], worst=stats.get("worst") or [], **extra)
            except Exception as e:  # noqa: BLE001
                _ideas_failed[ch["id"]] = time.time()
                log(f"⚠️ {ch['name']}: could not plan ideas ({type(e).__name__}).")
                return None, None
            if not got:
                _ideas_failed[ch["id"]] = time.time()
                return None, None
            _change(ch["id"], lambda c: c.update(ideas=got))
            ch = get(ch["id"])
        ch = _remix_first(ch, client_fn, log)
        idea = ch["ideas"][0]
        _change(ch["id"], lambda c: c.update(ideas=(c.get("ideas") or [])[1:]))
        if idea.get("notes"):
            look = {**look, "owner_notes": idea["notes"]}      # a remake with the owner's notes (_remake)
        if kind == "controversy":
            return ({**look, "genre": "controversy", "controversy_topic": idea["text"], "bg_music": True},
                    {"label": idea["text"], "format": "controversy", "topic": idea["text"], "idea": idea})
        if kind == "money":
            return ({**look, "genre": "money", "money_topic": idea["text"], "bg_music": True},
                    {"label": idea["text"], "format": "money", "topic": idea["text"], "idea": idea})
        if kind == "toons":
            series = ({"toon_series": idea["series"], "toon_part": idea.get("part") or 1,
                       "toon_parts": idea.get("parts") or 2} if idea.get("series") else {})
            return ({**look, "genre": "toons", "toon_premise": idea["text"], "toon_shape": idea.get("shape") or "",
                     "bg_music": True, **series},
                    {"label": (f"Part {idea.get('part') or 1}: " if series else "") + idea["text"], "format": "toons",
                     "topic": idea["text"], "idea": idea,
                     **({"series": idea["series"], "series_part": idea.get("part") or 1} if series else {})})
        if kind == "history":
            series = ({"history_series": idea["series"], "history_part": idea["part"],
                       "history_parts": idea["parts"], "history_before": idea.get("before") or []}
                      if idea.get("series") else {})
            return ({**look, "genre": "history", "history_topic": idea["text"], "bg_music": True,
                     "history_minutes": long_minutes(ch), "history_lang": ch.get("lang", "urdu"),
                     "history_mode": ch.get("mode", "history"),
                     "frame_outro": False, **series},
                    {"label": (f"Part {idea['part']}: " if series else "") + idea["text"], "format": "history",
                     "topic": idea["text"], "idea": idea,
                     **({"series": idea["series"], "series_part": idea["part"]} if series else {})})
        return ({**look, "genre": "cricket", "cricket_mode": idea["kind"], "cricket_match": idea["text"],
                 "bg_music": True},
                {"label": idea["text"], "format": idea["kind"], "topic": idea["text"], "idea": idea,
                 **({"urgent": True} if idea.get("urgent") else {})})
    if kind == "quiz":
        import quiz_shorts
        fmt = pick_format(ch, FORMATS["quiz"])
        topics = quiz_shorts.ISLAMIC_TOPICS if fmt == "islamic" else quiz_shorts.TOPICS
        topic = random.choice(topics) if fmt in quiz_shorts.FACT_FORMATS else ""
        if ch.get("notes") and fmt in quiz_shorts.FACT_FORMATS and fmt != "islamic" and random.random() < 0.5:
            topic = ch["notes"][:80]
        # Once a day the subject of a viral quiz the research agent studied (niche_research).
        idea = remix_idea(ch, log)
        if idea:
            fmt = idea["kind"] if idea["kind"] in quiz_shorts.FACT_FORMATS else "mcq"
            topic = idea["text"][:80]
        # The channel's running number: "QUIZ #12" makes a daily series to come back for.
        number = 1 + sum(1 for j in ch.get("jobs") or [] if j.get("status") in ("done", "uploaded"))
        return ({**look, "genre": "quiz", "quiz_format": fmt, "quiz_topic": topic, "bg_music": True,
                 "quiz_avoid": (ch.get("used") or [])[-80:], "quiz_number": number},
                {"label": f"{fmt}{': ' + topic if topic else ''}", "format": fmt, "topic": topic})
    if kind == "music":
        mix = _mix_payload(ch, look)
        if mix:
            return mix
        import music_shorts
        import ai_influencer
        import music_moods
        # Every song is made for a mood and its playlist (owner, 5-nov-2026): the mood furthest behind its
        # share of the last songs, then the best of that mood's styles and one of its themes.
        moods = music_moods.settings_of(ch.get("moods"))
        recent = [j.get("mood") or music_moods.infer(j.get("format"), j.get("topic"))
                  for j in sorted(ch.get("jobs") or [], key=lambda j: j.get("at", 0))
                  if j.get("status") in ("running", "done", "uploaded")]
        wanted = (ch.get("next_mood") or "")
        mood_key = wanted if wanted in music_moods.song_moods(moods) else music_moods.pick(moods, recent)
        # English or Urdu (owner, 10-nov-2026): the language behind its share of the last few songs.
        lang = music_moods.pick_lang(music_moods.urdu_share(ch), [
            j.get("lang") for j in sorted(ch.get("jobs") or [], key=lambda j: j.get("at", 0))
            if j.get("status") in ("running", "done", "uploaded") and j.get("format") != "mix"])
        brief = ""
        if mood_key:
            mood = music_moods.song_moods(moods)[mood_key]
            style, theme, brief = music_moods.song_choice(mood, music_shorts.STYLES,
                                                          lambda opts: pick_format(ch, opts), lang=lang)
        else:
            style = pick_format(ch, music_shorts.STYLES)
            theme = music_shorts.pick_theme()
        # Once a day the theme and style of a viral song Short the research agent studied (within the mood:
        # its theme, and its style only when that style is one of the mood's).
        idea = remix_idea(ch, log) if not wanted and lang == "english" else None
        if idea:
            theme = idea["text"][:60]
            mood_styles = music_moods.song_moods(moods)[mood_key].get("styles") if mood_key else music_shorts.STYLES
            style = idea["kind"] if idea["kind"] in (mood_styles or []) else style
        # The channel's AI singer dances in the first songs of the day, up to
        # ai_influencer.DAILY_MAX (she costs about $0.70 a Short); the rest are
        # the usual songs. Off until there is a fal.ai key and a chosen character.
        dance = ai_influencer.available()
        # No end card on songs: a Short that ends on the music loops straight
        # back into the first line, and replays count as views.
        mood_name = music_moods.all_moods(moods)[mood_key]["name"] if mood_key else ""
        return ({**look, "genre": "music", "music_style": style, "music_theme": theme, "frame_outro": False,
                 "music_avoid": (ch.get("used") or [])[-60:], **({"music_dance": True} if dance else {}),
                 "music_lang": lang, **({"music_mood": mood_key, "music_brief": brief} if mood_key else {})},
                {"label": f"{'Dance: ' if dance else ''}{'Urdu · ' if lang == 'urdu' else ''}"
                          f"{mood_name + ': ' if mood_name else ''}{style} song about {theme}",
                 "format": "dance" if dance else style, "topic": theme, "lang": lang,
                 **({"mood": mood_key} if mood_key else {})})
    return None, None


def mix_due(ch, now=None):
    """True when the song channel owes its weekly mood mix (music_moods.next_mix), or the cartoon channel its
    weekly compilation (toon_mix.due)."""
    if ch.get("kind") == "toons":
        if not ch.get("toon_mix", True):
            return False
        import toon_mix
        try:
            return toon_mix.due(ch.get("jobs"), now.timestamp() if hasattr(now, "timestamp") else now)
        except Exception:  # noqa: BLE001 — episodes go on without the compilation
            return False
    if ch.get("kind") != "music":
        return False
    import music_moods
    try:
        return music_moods.next_mix(music_moods.settings_of(ch.get("moods")), ch.get("jobs"),
                                    now=now.timestamp() if hasattr(now, "timestamp") else now,
                                    wanted=ch.get("next_mix") or "") is not None
    except Exception:  # noqa: BLE001 — songs go on without the mix
        return False


def _mix_payload(ch, look):
    """(payload, meta) of the song channel's due mood mix, or None."""
    import music_moods
    settings = music_moods.settings_of(ch.get("moods"))
    got = music_moods.next_mix(settings, ch.get("jobs"), wanted=ch.get("next_mix") or "")
    if not got:
        return None
    key, dirs = got
    mood = music_moods.all_moods(settings)[key]
    vol = 1 + sum(1 for j in ch.get("jobs") or [] if j.get("format") == "mix" and j.get("mood") == key
                  and j.get("status") in ("done", "uploaded"))
    return ({**look, "genre": "music", "music_mix": key, "music_mix_mood": mood, "music_mix_songs": dirs,
             "music_mix_minutes": music_moods.mix_setting(settings, "mix_minutes"),
             "music_mix_budget": music_moods.mix_setting(settings, "mix_budget"), "music_mix_vol": vol,
             "frame_outro": False},
            {"label": f"{mood['name']} mix, vol. {vol}" + (f" ({len(dirs)} songs)" if dirs else ""),
             "format": "mix", "topic": mood["name"], "mood": key})


QURAN_TRIES = 3


def _quran_job(look, settings, passage, label, tries):
    import quran_videos as qv
    s = passage["segments"][0][0]
    part = passage.get("part")
    return ({**look, "genre": "quran", "quran_plan": {**settings, **passage}, "frame_outro": False},
            {"label": label, "format": "quran", "topic": label, "passage": passage, "passage_try": tries,
             # The parts of a long surah share a playlist (engage.py names it after the series).
             **({"series": f"{qv.display_name(s)}, {qv.TITLE_WORDS['english' if settings['screen'] == 'english' else 'urdu']}",
                 "series_part": part} if part else {})})


def _quran_payload(ch, look, log=print):
    """The next passage of the Quran channel: a passage whose video failed
    first (the order matters here), then the queue of surahs (popular ones,
    then the whole Quran in order; the owner's own requests go first)."""
    import quran_videos as qv
    settings = qv.settings_of(ch.get("quran"))
    for j in sorted(ch.get("jobs") or [], key=lambda j: j.get("at", 0), reverse=True):
        if j.get("format") == "quran" and j.get("status") == "failed" and j.get("passage") and not j.get("redone"):
            _set_job(ch["id"], j["job_id"], redone=True)
            tries = int(j.get("passage_try") or 1)
            if tries < QURAN_TRIES:
                return _quran_job(look, settings, j["passage"], j.get("label", ""), tries + 1)
            log(f"⚠️ {ch['name']}: '{j.get('label', '')[:60]}' failed {tries} times; going on to the next passage.")
            break
    if time.time() - _ideas_failed.get(ch["id"], 0) < IDEAS_RETRY:
        return None, None
    ideas = ch.get("ideas") or qv.queue([u[6:] for u in ch.get("used") or [] if str(u).startswith("quran:")])
    try:
        passage, left = qv.plan_next(ideas, settings)
    except Exception as e:  # noqa: BLE001 — Quran.com unreachable: try again later
        _ideas_failed[ch["id"]] = time.time()
        log(f"⚠️ {ch['name']}: could not plan the next passage ({type(e).__name__}: {str(e)[:120]}).")
        return None, None
    if not passage:
        return None, None
    still = {i.get("id") for i in left}
    finished = [i["id"] for i in ideas if i.get("id") and i["id"] not in still]
    _change(ch["id"], lambda c: c.update(ideas=left, used=((c.get("used") or [])
                                                           + [f"quran:{x}" for x in finished])[-300:]))
    label = qv.title_of(passage["segments"], settings, passage.get("part")).split(" | ")[0]
    return _quran_job(look, settings, passage, label, 1)


def wants_more(ch, now=None):
    day = today(now)
    if not ch.get("enabled") or running(ch) or ch.get("paused_until", 0) > (now.timestamp() if now else time.time()):
        return False
    if teaser_due(ch) or today_short_due(ch, now) or mix_due(ch, now):
        return True
    made = len(_jobs_on(ch, day))
    passing = sum(1 for j in _jobs_on(ch, day, ("failed",)) if j.get("transient"))
    tries = len(_jobs_on(ch, day, ("running", "done", "uploaded", "failed"))) - min(passing, TRANSIENT_MAX)
    if (ch.get("ideas") or [{}])[0].get("urgent"):
        return tries < (ch["per_day"] + 2) * TRIES_PER_SHORT   # a fresh result goes even past today's count
    return made < ch["per_day"] and tries < ch["per_day"] * TRIES_PER_SHORT and len(waiting(ch)) < ch["per_day"]


def _teams(line):
    m = re.match(r"\s*([^,]+?)\s+vs\.?\s+([^,]+)", line or "", re.I)
    return frozenset(x.strip().lower() for x in m.groups()) if m else frozenset()


def match_watch(ch, client_fn, log=print, now=None):
    """Every MATCH_EVERY: a match Pakistan or India just finished goes to the
    front of the cricket channel's ideas, marked urgent."""
    now = now or time.time()
    if ch.get("kind") != "cricket" or not ch.get("match_watch", True) or now - ch.get("last_match_check", 0) < MATCH_EVERY:
        return []
    _change(ch["id"], lambda c: c.update(last_match_check=int(now)))
    import cricket_shorts
    try:
        text, _src = cricket_shorts.grounded(client_fn(), MATCH_PROMPT.format(today=datetime.now().strftime("%d %B %Y")))
    except Exception as e:  # noqa: BLE001 — next check in 2 hours
        log(f"⚠️ {ch['name']}: match check failed ({type(e).__name__}).")
        return []
    found = [" ".join(m.group(1).split())[:200] for m in re.finditer(r"MATCH:\s*(.+)", text or "")]
    # Already covered: a match Short of the same two teams in the last 20 hours
    # (dates come back written differently each time), or one waiting in ideas.
    recent = [_teams(j.get("topic") or "") for j in ch.get("jobs") or []
              if j.get("format") == "match" and j.get("status") in ("running", "done", "uploaded")
              and now - j.get("at", 0) < 20 * 3600]
    # An owner's typed "A vs B" may be any match: the real result replaces it.
    recent += [_teams(i["text"]) for i in ch.get("ideas") or [] if i.get("kind") == "match" and not i.get("owner")]
    new = []
    for line in found:
        teams = _teams(line)
        if not teams or teams in recent:
            continue
        recent.append(teams)
        new.append({"kind": "match", "text": line, "urgent": True})
    if new:
        done = {_teams(x["text"]) for x in new}
        _change(ch["id"], lambda c: c.update(ideas=new + [
            i for i in c.get("ideas") or [] if not (i.get("owner") and i.get("kind") == "match"
                                                    and _teams(i["text"]) in done)]))
        log(f"⚡ {ch['name']}: just finished: {', '.join(x['text'][:60] for x in new)}. Making it next.")
    return new


async def make_one(submit, ch, client_fn, log=print, now=None):
    """Start the channel's next Short; returns the job id or None."""
    loop = asyncio.get_event_loop()
    payload, meta = await loop.run_in_executor(None, next_payload, ch, client_fn, log)
    if not payload:
        return None
    row = {"at": int(time.time()), "day": today(now), "status": "running", **meta}
    # The channel it is made for (its end card names it): upload_waiting
    # refuses it if the card is connected to another channel by then.
    yid = (connected(ch).get("channel") or {}).get("id")
    if yid:
        row["yt_channel"] = yid
    try:
        row["job_id"] = await submit(payload)
    except Exception as e:  # noqa: BLE001
        row.update(status="failed", error=str(e)[:200])
        log(f"⚠️ {ch['name']}: could not start '{meta['label'][:60]}': {e}")

    def fn(c):
        c["jobs"] = ((c.get("jobs") or []) + [row])[-200:]
        if (c.get("next_mix") and row.get("format") == "mix" and row.get("mood") == c["next_mix"]
                and row["status"] != "failed"):
            c.pop("next_mix")                      # the owner's "make a mix now" is on its way
        if c.get("next_mood") and row.get("mood") == c["next_mood"] and row["status"] != "failed":
            c.pop("next_mood")                     # the owner's "make a <mood> song" is on its way
        if row["status"] == "failed" and c["kind"] in PLANNERS and _requeue(c, row.get("idea")):
            row["requeued"] = True                 # never started: the idea itself was never tried
    _change(ch["id"], fn)
    if row.get("job_id"):
        log(f"🎬 {ch['name']}: making '{meta['label'][:70]}'.")
    return row.get("job_id")


def _used_items(job_path):
    """What a finished job used (questions, song title, topic) for the avoid list."""
    import glob
    metas = glob.glob(os.path.join(job_path, "*_metadata.json"))
    if not metas:
        return []
    try:
        with open(metas[0], encoding="utf-8") as f:
            short = (json.load(f).get("shorts") or [{}])[0]
    except (OSError, ValueError):
        return []
    if short.get("quiz"):
        return short["quiz"].get("questions") or []
    if short.get("song"):
        return [short["song"].get("title")]
    if (short.get("history") or {}).get("today"):
        return [f"today:{short['history'].get('event')}"]
    return []


def refresh_jobs(ch, job_clips, output_dir, now=None):
    """Running jobs that ended: done (waits for upload) or failed."""
    now = now or time.time()
    changed = []
    for j in running(ch):
        state, clips = job_clips(j["job_id"])
        if state == "completed" and clips:
            changed.append((j["job_id"], "done", None, _used_items(os.path.join(output_dir, j["job_id"]))))
        elif state in ("failed", "error", "cancelled") or (state == "completed" and not clips):
            reason = failure_reason(j["job_id"]) if failure_reason else None
            changed.append((j["job_id"], "failed", reason or "the job failed", []))
        elif state == "missing" and now - j.get("at", now) > LOST_AFTER:
            changed.append((j["job_id"], "failed", LOST, []))
        elif now - j.get("at", now) > (MIX_TIMEOUT if j.get("format") == "mix"
                                       else KINDS.get(ch["kind"], {}).get("timeout", JOB_TIMEOUT)):
            if cancel_job:
                try:
                    cancel_job(j["job_id"], "stopped: it took too long")
                except Exception:  # noqa: BLE001 — the job is still marked failed
                    pass
            changed.append((j["job_id"], "failed", "took too long", []))
    if not changed:
        return ch
    if ch.get("review_hours"):
        _tell_review(ch, [job_id for job_id, status, _e, _u in changed if status == "done"], job_clips)

    def fn(c):
        for job_id, status, err, used in changed:
            for j in c.get("jobs") or []:
                if j.get("job_id") == job_id:
                    j["status"] = status
                    if status == "done":
                        j["done_at"] = int(now)
                    if err:
                        j["error"] = err
                    if status == "failed" and err == LOST:
                        j["transient"] = True             # not the idea's fault, and no outage to wait out
                    elif status == "failed" and err and TRANSIENT.search(err):
                        j["transient"] = True
                        c["paused_until"] = int(now) + TRANSIENT_PAUSE
                    if j.get("transient") and c["kind"] in PLANNERS and _requeue(c, j.get("idea")):
                        j["requeued"] = True
            job = next((j for j in c["jobs"] if j.get("job_id") == job_id), {})
            topic = job.get("topic")
            if status == "done" and job.get("format") != "teaser":   # a teaser's topic is already used
                adds = used or ([topic] if c["kind"] in PLANNERS and topic else [])
                c["used"] = ((c.get("used") or []) + [str(u)[:140] for u in adds if u])[-300:]
    return _change(ch["id"], fn)


# ------------------------------------------------------------------ uploading

REVIEW_MAX_HOURS = 24


def held_for_review(ch, j, now=None):
    """True while a finished video waits the channel's review_hours, so the
    owner can watch it (Channels tab or Telegram) and skip it first."""
    hours = int(ch.get("review_hours") or 0)
    # Studio's AI editor is changing the file (ai_editor.py): never upload the half-edited video.
    if (j.get("editing_until") or 0) > (now or time.time()):
        return True
    if j.get("approved"):            # approved in the Studio (studio.act): no need to wait out the hold
        return False
    return bool(hours) and (now or time.time()) < (j.get("done_at") or j.get("at", 0)) + hours * 3600


def _tell_review(ch, job_ids, job_clips):
    """A Telegram message per video held for review, when Telegram is set up."""
    if not job_ids:
        return
    try:
        import telegram_notify
        if not telegram_notify.status().get("connected"):
            return
        for job_id in job_ids:
            _state, clips = job_clips(job_id)
            if clips:
                telegram_notify.send_text(
                    f"{ch['name']}: \"{clips[0]['title'][:90]}\" is ready and goes up in "
                    f"{ch['review_hours']} h unless you skip it here or in Shortkaar (Channels tab).\n"
                    f"{PHONE_EDIT_HINT}\nref {job_id}",
                    buttons=[("Skip this video", f"skip:{ch['id']}:{job_id}")])
    except Exception:  # noqa: BLE001 — a message never stops the channel
        pass


SLOT_GAP = timedelta(minutes=40)
QA_TRIES = 3


def _clear_of(slot, uploads):
    """``slot``, moved on by SLOT_GAP until no scheduled upload of the channel is that close."""
    busy = []
    for r in uploads:
        try:
            if r.get("status") == "done" and r.get("publish_at"):
                busy.append(datetime.fromisoformat(r["publish_at"]))
        except ValueError:
            pass
    for _ in range(24):
        if all(abs(slot - b) >= SLOT_GAP for b in busy):
            break
        slot += SLOT_GAP
    return slot


def _link_previous_part(row, j, ch, log=print):
    """The series' previous part gets a "next part" link to the one just
    uploaded (inside youtube_account.use for this channel). Never fails the upload."""
    import history_videos
    import youtube_account
    part = int(j.get("series_part") or 1)
    genres = ("toons",) if ch.get("kind") == "toons" else history_videos.LONG_GENRES
    prev = history_videos.series_rows(youtube_account.uploads(), j["series"], genres).get(part - 1)
    if not prev or prev.get("next_linked"):
        return
    try:
        youtube_account.add_to_description(prev["video_id"], history_videos.next_part_line(
            row["video_id"], part, ch.get("lang", "urdu")))
        prev["next_linked"] = row["video_id"]
    except Exception as e:  # noqa: BLE001 — the new part is up either way
        prev["next_link_error"] = str(e)[:200]
        log(f"   ℹ️ {ch['name']}: could not link part {part - 1} to part {part} ({str(e)[:100]}).")
    youtube_account._save_upload(prev)


def upload_due(ch, now=None):
    now = now or time.time()
    return (ch.get("enabled") and ch.get("auto_upload") and waiting(ch)
            and now >= ch.get("upload_paused_until", 0) and now - ch.get("last_upload", 0) >= UPLOAD_EVERY)


# News goes stale while it waits (a channel connected days later, the upload
# limit, a review hold): a match result is skipped after two days, and an
# "Aaj ki tareekh" Short ("on this day") goes up on its own date or never.
# Everything else (quizzes, facts, history, songs) keeps.
STALE_HOURS = {"match": 48}


def stale(j, now=None):
    now = now or time.time()
    if j.get("format") == "today":
        return bool(j.get("day")) and j["day"] != today(datetime.fromtimestamp(now))
    hours = STALE_HOURS.get(j.get("format"))
    return bool(hours) and now - j.get("at", now) > hours * 3600


REQUEUE_MAX = 2


def _requeue(c, idea):
    """A planned idea whose job died of something outside the idea (network, quota, a server restart)
    goes back in the queue: after any urgent match results, before the rest. A planned idea leaves the
    queue when its job starts, so an outage used to lose it: an urgent result, the owner's own topic,
    one part of a history series. At most REQUEUE_MAX times; an idea already queued is left alone."""
    if not isinstance(idea, dict) or not idea.get("text") or int(idea.get("requeued") or 0) >= REQUEUE_MAX:
        return False
    ideas = c.get("ideas") or []
    if any(str(i.get("text") or "").lower() == idea["text"].lower() for i in ideas):
        return False
    lead = 0 if idea.get("urgent") else next((k for k, i in enumerate(ideas) if not i.get("urgent")), len(ideas))
    c["ideas"] = ideas[:lead] + [{**idea, "requeued": int(idea.get("requeued") or 0) + 1}] + ideas[lead:]
    return True


def _remake(cid, j, notes=""):
    """A planned topic goes back to the front of the ideas (after urgent
    results), for a video that cannot be posted as it was made. ``notes``: what
    the owner wants different (Studio's AI editor), sent to the writer as OWNER_NOTES."""
    if not j.get("topic") or j.get("format") in EXTRA_FORMATS or j.get("series"):
        return
    kind = j["format"] if j.get("format") in ("match", "versus", "topic", "ranking") else "topic"
    notes = " ".join(str(notes or "").split())[:500]

    def fn(c):
        if c["kind"] not in PLANNERS:
            return
        rest = [i for i in c.get("ideas") or [] if i.get("text") != j["topic"]]
        urgent = [i for i in rest if i.get("urgent")]
        c["ideas"] = (urgent + [{"kind": kind, "text": j["topic"], **({"notes": notes} if notes else {})}]
                      + [i for i in rest if not i.get("urgent")])
        c["used"] = [u for u in c.get("used") or [] if u != j["topic"][:140]]
    _change(cid, fn)


def upload_waiting(ch, job_clips, log=print):
    """Upload the channel's finished Shorts, each into its next free posting
    time. Stops at YouTube's daily limit and pauses the channel 3 h."""
    import youtube_account
    _change(ch["id"], lambda c: c.update(last_upload=int(time.time())))
    done, limit = 0, False
    with youtube_account.use(account(ch["id"])):
        st = youtube_account.status()
        if not st["connected"]:
            return {"done": 0, "limit": False}
        me = (st.get("channel") or {}).get("id")
        for j in sorted(waiting(ch), key=lambda j: j.get("at", 0)):
            if j.get("yt_channel") and me and j["yt_channel"] != me:
                # Made while the card pointed at another channel: its end card
                # and description name that channel. Made again instead.
                _set_job(ch["id"], j["job_id"], status="skipped",
                         error="made for another channel (this card was reconnected); made again")
                _remake(ch["id"], j)
                log(f"⏭️ {ch['name']}: not uploading '{(j.get('label') or '')[:60]}': made for another channel.")
                continue
            if stale(j):
                _set_job(ch["id"], j["job_id"], status="skipped", error="too old to post now (news of an earlier day)")
                log(f"⏭️ {ch['name']}: not uploading '{(j.get('label') or j.get('topic') or '')[:60]}': too old now.")
                continue
            if (j.get("editing_until") or 0) > time.time():     # the AI editor is changing it, even if urgent
                continue
            if held_for_review(ch, j) and not j.get("urgent"):   # a match result is news for hours only
                continue
            _state, clips = job_clips(j["job_id"])
            if not clips:
                _set_job(ch["id"], j["job_id"], status="failed", error="no longer on this computer")
                continue
            clip = clips[0]
            if not j.get("qa") and os.environ.get("VIDEO_QA", "1") != "0":
                # Nobody watches these go up: a silent, black or frozen render stops here.
                import video_qa
                long = ((bool(KINDS.get(ch["kind"], {}).get("long")) and j.get("format") not in EXTRA_FORMATS)
                        or j.get("format") == "mix")
                try:
                    problems = video_qa.check(clip["path"], long=long)
                except video_qa.Unchecked as e:
                    # The checker, not the video: try again on the next pass, three times.
                    tries = j.get("qa_tries", 0) + 1
                    _set_job(ch["id"], j["job_id"], qa_tries=tries)
                    if tries < QA_TRIES:
                        log(f"   ℹ️ {ch['name']}: could not check '{clip['title'][:50]}' yet ({e}); next pass.")
                        continue
                    problems = [f"the check could not run {QA_TRIES} times ({e})"]
                if problems:
                    _set_job(ch["id"], j["job_id"], status="failed", error="quality check: " + "; ".join(problems))
                    log(f"🚫 {ch['name']}: not uploading '{clip['title'][:60]}': {'; '.join(problems)}.")
                    continue
                _set_job(ch["id"], j["job_id"], qa="ok")
            if not j.get("look"):
                import creative_qa
                if creative_qa.enabled():
                    # Eyes on it before it goes up (creative_qa.py): words cut mid-word, a corrupted
                    # picture, an empty first frame. Once per job; a check that cannot run lets it go up.
                    seen = creative_qa.review(clip["path"], clip.get("title") or "", ch["kind"], ch.get("name") or "")
                    if seen and seen["blocked"] and creative_qa.blocks():
                        _set_job(ch["id"], j["job_id"], status="failed", look="blocked",
                                 error="visual check: " + seen["reason"])
                        log(f"🚫 {ch['name']}: not uploading '{clip['title'][:60]}': visual check: {seen['reason'][:150]}.")
                        continue
                    _set_job(ch["id"], j["job_id"],
                             look=f"first frame {seen['first_frame']}/10, polish {seen['polish']}/10" if seen else "unchecked")
            if j.get("urgent"):
                slot = datetime.now().astimezone() + timedelta(minutes=URGENT_AFTER_MINUTES)
            elif j.get("format") == "teaser":
                # 15 minutes after its long video goes public, so the link in it works;
                # a moment Short a day later per part, so the long video gets new viewers for days.
                soon = datetime.now().astimezone() + timedelta(minutes=URGENT_AFTER_MINUTES)
                try:
                    after = (datetime.fromisoformat(j.get("publish_after") or "")
                             + timedelta(minutes=15, days=int(j.get("part") or 0)))
                except ValueError:
                    after = soon
                # Today's teaser and the moments of earlier long videos would all
                # land 15 minutes after the same posting time: one per gap.
                slot = _clear_of(max(after, soon), youtube_account.uploads())
            elif j.get("format") == "today":
                # On its own date, from noon: the story is "aaj ke din".
                soon = datetime.now().astimezone() + timedelta(minutes=URGENT_AFTER_MINUTES)
                noon = soon.replace(hour=12, minute=0, second=0, microsecond=0)
                slot = _clear_of(max(soon, noon), youtube_account.uploads())
                if j.get("day") and slot.strftime("%Y-%m-%d") != j["day"]:
                    # Uploaded late in the evening, it would go public tomorrow: "aaj" would be wrong.
                    _set_job(ch["id"], j["job_id"], status="skipped", error="too late in the day to post")
                    log(f"⏭️ {ch['name']}: not uploading '{clip['title'][:60]}': its day is over.")
                    continue
            else:
                slot = youtube_account.next_slots(ch["post_times"], 1)[0]
            if not (clip.get("description") or "").strip():
                # Its writing step failed (a network drop, 18-oct-2026); such a
                # job was usually voiced in the same outage too.
                _set_job(ch["id"], j["job_id"], status="failed", error="no description (its writing step failed)")
                log(f"🚫 {ch['name']}: not uploading '{clip.get('title', '')[:60]}': it has no description.")
                continue
            desc = promote(clip["description"], ch["id"])
            if KINDS[ch["kind"]].get("story") and j.get("format") not in EXTRA_FORMATS:
                import history_videos
                ups = youtube_account.uploads()
                if j.get("series"):
                    desc = history_videos.series_links(desc, ups, j["series"], j.get("series_part") or 1,
                                                       ch.get("lang", "urdu"))
                desc = history_videos.watch_next(desc, ups, ch.get("lang", "urdu"))
            elif ch["kind"] == "toons" and j.get("series"):
                # Part 2 of a two-part cartoon links its part 1 (and part 1 gets the link to it after this upload).
                import history_videos
                desc = history_videos.series_links(desc, youtube_account.uploads(), j["series"],
                                                   j.get("series_part") or 1, "urdu", genres=("toons",))
            # Hindi and Urdu-script titles for viewers searching in those scripts (localize.py).
            import localize
            translated = {}
            if localize.available(ch["kind"]):
                try:
                    import short_kit
                    translated = localize.build(short_kit.gemini(), clip["title"], desc, ch["kind"], log=log)
                except Exception:  # noqa: BLE001 — never holds an upload back
                    translated = {}
            # The same song never goes up twice (audio_dedupe.py, Chromaprint); a mix reuses songs on purpose.
            fp = None
            if ch["kind"] == "music" and j.get("format") != "mix":
                import audio_dedupe
                fp = audio_dedupe.fingerprint(clip["path"]) if audio_dedupe.available() else None
                dup = audio_dedupe.duplicate(ch["id"], fp, exclude=j["job_id"])
                if dup:
                    _set_job(ch["id"], j["job_id"], status="skipped",
                             error=f"the same song as '{dup['title'][:60]}', already uploaded")
                    log(f"⏭️ {ch['name']}: not uploading '{clip['title'][:60]}': the same song as "
                        f"'{dup['title'][:60]}' ({dup['score']:.0%} of its fingerprint).")
                    continue
            row = youtube_account.upload(
                clip["path"], clip["title"], desc, clip["tags"],
                upload_genre(ch, j),
                publish_at=slot, ai_made=clip.get("ai_made", False),
                **({"localizations": translated} if translated else {}),
                meta={"job_id": j["job_id"], "clip_index": clip["index"], "channel": ch["id"],
                      "format": j.get("format"), "topic": j.get("topic"), "seconds": clip.get("seconds"),
                      "question": clip.get("question") or "", "answers": clip.get("answers") or [],
                      # What the first seconds say and show, for hook_lessons.
                      "opening": clip.get("opening") or "", "screen": clip.get("hook") or "",
                      **({"series": j["series"], "series_part": j.get("series_part")} if j.get("series") else {}),
                      **({"mood": j["mood"]} if j.get("mood") else {}),
                      **({"lang": j["lang"]} if j.get("lang") else {}),
                      **({"thumb": j["thumb"]} if j.get("thumb") else {}),
                      **({"outro": j["outro"]} if j.get("outro") is not None else {}),
                      **({"timer": j["timer"]} if j.get("timer") is not None else {}),
                      **({"pace": j["pace"]} if j.get("pace") else {}),
                      **({"toonlen": j["toonlen"]} if j.get("toonlen") else {})})
            if row.get("status") == "done":
                done += 1
                if fp:
                    import audio_dedupe
                    audio_dedupe.remember(ch["id"], j["job_id"], clip["title"], fp)
                if clip.get("thumbnail"):
                    youtube_account.add_thumbnail(row, clip["thumbnail"])
                    _keep_for_retry(ch, row, "thumbnail", clip["thumbnail"])
                if clip.get("captions"):
                    lang = clip.get("captions_language") or "ur"
                    youtube_account.add_captions(row, clip["captions"], lang)
                    _keep_for_retry(ch, row, "captions", clip["captions"], lang)
                    for path, lang in clip.get("captions_extra") or []:
                        youtube_account.add_captions(row, path, lang, key=f"captions_{lang}")
                        _keep_for_retry(ch, row, f"captions_{lang}", path, lang)
                if j.get("series") and (j.get("series_part") or 1) > 1:
                    _link_previous_part(row, j, ch, log)
                _set_job(ch["id"], j["job_id"], status="uploaded", video_id=row.get("video_id"),
                         slot=slot.isoformat())
                log(f"⬆️ {ch['name']}: uploaded '{row['title'][:60]}' for {slot:%d %b %H:%M}.")
                try:
                    import meta_publish
                    # The same Short on the channel's Facebook Page and Instagram at its YouTube time.
                    if meta_publish.enqueue(ch, {**row, "description": desc}, clip["path"], slot,
                                            ig_wait=meta_ig_mode(ch) == "winners"):
                        log(f"   📋 {ch['name']}: queued for Facebook / Instagram.")
                except Exception as e:  # noqa: BLE001 — YouTube is what matters
                    log(f"   ⚠️ {ch['name']}: not queued for Facebook / Instagram ({type(e).__name__}).")
                continue
            if youtube_account.upload_limit_hit(row.get("error")):
                limit = True
                break
            tries = j.get("upload_tries", 0) + 1
            _set_job(ch["id"], j["job_id"], upload_tries=tries, error=(row.get("error") or "")[:200],
                     **({"status": "failed"} if tries >= UPLOAD_TRIES else {}))
    if limit:
        _change(ch["id"], lambda c: c.update(upload_paused_until=int(time.time()) + UPLOAD_PAUSE_SECONDS))
        log(f"⏸️ {ch['name']}: YouTube's daily upload limit after {done}; trying again in 3 hours.")
    return {"done": done, "limit": limit}


# A thumbnail refused before the owner phone-verifies the channel, or a
# caption track skipped for the day's quota, is tried again: the job folder
# is gone by then, so the file is kept in the channel's folder until it
# works (RETRY_DAYS at most, RETRY_TRIES passes, one every LEARN_EVERY).
RETRY_DAYS = 7
RETRY_TRIES = 4


def _keep_for_retry(ch, row, key, path, lang=None):
    import shutil
    import youtube_account
    if row.get(key) not in ("failed", "skipped") or not os.path.isfile(path):
        return
    keep = os.path.join(folder(ch["id"]), "retry")
    os.makedirs(keep, exist_ok=True)
    dst = os.path.join(keep, f"{row['id']}.{key}{os.path.splitext(path)[1]}")
    try:
        shutil.copyfile(path, dst)
    except OSError:
        return
    row.setdefault("retry", {})[key] = {"file": dst, "lang": lang, "tries": 0}
    youtube_account._save_upload(row)


# OmniVoice's audio tokenizer (local_voice.py) is under Boson AI's Higgs Audio 2 community licence, which
# asks for this line on a related about page; the owner said to add it (22-oct-2026). Kinds with narration only.
VOICE_CREDIT = ("Some narration is made with OmniVoice. Built with Higgs Materials licensed from Boson AI USA, Inc., "
                "Copyright Boson AI USA, Inc., All Rights Reserved and Meta Llama 3 licensed under the Meta Llama 3 "
                "Community License, Copyright Meta Platforms, Inc., All Rights Reserved.")
VOICE_KINDS = ("cricket", "quiz", "controversy", "history", "quran", "money", "toons")
# Every channel's About text was empty on 22-oct-2026, which also wastes YouTube's channel search: an
# empty one gets this before the credit. Plain facts only; the owner can rewrite it in Studio any time.
ABOUT = {
    "cricket": "Cricket facts, records and match stories in Urdu and Hindi, made fresh every day. Pakistan, "
               "India and world cricket: player records, results, head-to-head numbers and the moments fans "
               "talk about. New Shorts every afternoon and evening.",
    "quiz": "Daily quiz Shorts in Urdu: general knowledge, Islamic quiz, flags, true or false and paheliyan. "
            "Answer in the comments and challenge your friends. A new quiz every day.",
    "controversy": "Viral stories and controversies explained simply in Urdu and Hindi: what was reported, what "
                   "is alleged and what each side says, with the sources in every description. New explainers "
                   "every day.",
    "money": "Money stories told with animated charts, in Urdu and Hindi: what things cost then and now, what "
             "people earn at home and abroad, and the biggest money mistakes of famous companies. Every number "
             "comes from published sources, listed in each description. Information only, never financial "
             "advice. New Shorts every day.",
    "history": "Urdu documentaries on history and the big stories of today: empires, battles, scholars, "
               "turning points and the news everyone is talking about, explained with sources. New videos "
               "every day, plus short clips from each one.",
    "quran": "Tilawat of the Holy Quran by Qari Mishary Rashid Alafasy, ayah by ayah, with the Arabic text "
             "and the Urdu translation of Maulana Muhammad Junagarhi on screen. Recitation and texts from the "
             "Quran Foundation (quran.com). A new surah or part every day.",
    # The long channel in horror mode (ABOUT key = engage_kind).
    "horror": "Original horror stories in Urdu and Hindi, told late at night: haunted havelis, highways, hostels "
              "and the things that wait in the dark. Every story is fiction, written for this channel, with "
              "painted pictures and a narrator. New stories every week, plus short clips from each one.",
    "toons": "Billo the cat, Sheru the dog, Mithu the parrot and baby Guddu, who talks like a tired old uncle: an "
             "original animated comedy series about one Lahore home. Bills, guests, cricket on TV, rishta aunties "
             "and Ammi's kitchen rules, a new episode with a twist every day. All characters are fictional; the "
             "pictures and voices are made with AI.",
}


def about_credit(ch, log=print):
    """Add VOICE_CREDIT to the channel's About text once (``about_credit`` on the card). A channel handed over
    from a card of another kind (hand_over) gets its own kind's About in place of the old one, which is kept in
    the card's folder."""
    import youtube_account
    if ch.get("kind") not in VOICE_KINDS or ch.get("about_credit"):
        return False
    about = ABOUT.get(engage_kind(ch)) or ABOUT.get(ch["kind"])
    swap = bool(ch.get("took_over")) and bool(about)
    with youtube_account.use(account(ch["id"])):
        if not youtube_account.status()["connected"]:
            return False
        try:
            more = ({"replace": about, "backup": os.path.join(folder(ch["id"]), f"about_backup_{today()}.txt")}
                    if swap else {})
            added = youtube_account.add_to_channel_about(VOICE_CREDIT, if_empty=about, **more)
        except Exception as e:  # noqa: BLE001 — tried again on the next learn pass
            log(f"⚠️ {ch.get('name')}: voice credit not added ({str(e)[:80]}).")
            return False
    _change(ch["id"], lambda c: c.update(about_credit=int(time.time())))
    if swap:
        log(f"📝 {ch.get('name')}: the channel's About text now describes this card (the old one is backed up).")
    else:
        log(f"📝 {ch.get('name')}: voice credit {'added to' if added else 'already in'} the channel's About text.")
    return added


def retry_extras(ch, log=print, now=None):
    """Try failed thumbnails and caption tracks of the last week again.
    Returns how many went up this time."""
    import youtube_account
    now = now or time.time()
    fixed = 0
    # Custom thumbnails need a phone-verified channel; long_minutes() keeps
    # YouTube's answer (eligible = not verified yet).
    unverified = (ch.get("long_uploads") or {}).get("status") in ("eligible", "disallowed")
    with youtube_account.use(account(ch["id"])):
        for row in youtube_account.uploads():
            if not row.get("retry"):
                continue
            for key, r in list(row["retry"].items()):
                usable = (now - row.get("created", now) <= RETRY_DAYS * 86400 and r["tries"] < RETRY_TRIES
                          and os.path.isfile(r["file"]))
                if usable and key == "thumbnail" and unverified:
                    continue                  # refused until the phone check; no try used
                if usable:
                    r["tries"] += 1
                    if key == "thumbnail":
                        youtube_account.add_thumbnail(row, r["file"])
                    else:
                        youtube_account.add_captions(row, r["file"], r.get("lang") or "ur", key=key)
                    if row.get(key) != "set":
                        youtube_account._save_upload(row)
                        continue
                    fixed += 1
                    log(f"🔁 {ch['name']}: {key.replace('_', ' ')} added to '{(row.get('title') or '')[:50]}'.")
                try:                          # done, or given up: the copy goes
                    os.remove(r["file"])
                except OSError:
                    pass
                row["retry"].pop(key)
                youtube_account._save_upload(row)
            if row.get("retry") is not None and not row["retry"]:
                row.pop("retry")
                youtube_account._save_upload(row)
    return fixed


# Editing from the phone (4-nov-2026): a text reply to a review note, or to an edited video the bot sent
# back, is an AI-editor request for that video. app.py sets ``start_ai_edit(job_id, prompt)`` (the same
# subprocess as Studio's box; it raises with a reason the owner can read).
PHONE_EDIT_HINT = ("Reply to this message with a change (e.g. \"captions peele karo\", \"pehle 2 second kaato\"), "
                   "or \"suggest\" for the AI's own ideas.")
start_ai_edit = None
# "<job id>" or "<job id>.<n>": clip n of a job cut into several Shorts (studio.REF).
_REF = re.compile(r"\bref ([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(?:\.[1-9][0-9]?)?)\b")


SUGGEST_WORDS = {"suggest", "suggestions", "ideas", "idea", "kya behtar ho sakta hai", "behtar karo", "mashwara",
                 "tips"}


def _phone_suggestions(job_id):
    """The AI editor's own suggestions as Telegram buttons ("ed:<job>:<n>": a press applies that one)."""
    import ai_editor
    import telegram_notify
    try:
        items = (ai_editor.suggest(job_id) or {}).get("items") or []
    except Exception as e:  # noqa: BLE001 — the reason goes back to the phone
        return f"No suggestions right now ({getattr(e, 'args', [''])[0] or type(e).__name__})."
    if not items:
        return "The AI has nothing to suggest: this one looks ready."
    lines = [f"{k + 1}. {s['text']}" + (f" ({s['why']})" if s.get("why") else "") for k, s in enumerate(items)]
    telegram_notify.send_text("Suggested edits (tap one to make it):\n" + "\n".join(lines) + f"\nref {job_id}",
                              buttons=[(f"{k + 1}. {s['text']}", f"ed:{job_id}:{k}") for k, s in enumerate(items)],
                              rows=True)
    return ""


def _press_suggestion(rest):
    """A tap on a suggestion button: that suggestion becomes the edit request."""
    import ai_editor
    import studio
    job_id, _, k = rest.rpartition(":")
    try:
        path = studio.job_dir(job_id)
        folder = ai_editor.edits_name(studio.split_ref(job_id)[1])
        items = (ai_editor._read_json(os.path.join(path, folder, "suggest.json"), {}) or {}).get("items") or []
        text = items[int(k)]["text"]
    except (studio.StudioError, ValueError, IndexError, KeyError):
        return "That suggestion is gone; reply \"suggest\" for new ones."
    if not start_ai_edit:
        return "The editor is not running; open Shortkaar's Studio."
    try:
        start_ai_edit(job_id, text)
    except Exception as e:  # noqa: BLE001
        return f"Could not start the edit: {getattr(e, 'detail', None) or e}"
    return f"Working on it: \"{text[:120]}\". The new version comes here in about a minute."


def telegram_reply(text, replied):
    """The owner replied ``text`` to the bot's message ``replied``: start that video's AI edit."""
    m = _REF.search(replied or "")
    if not m:
        return ""                                     # a reply to some other note: nothing to do
    import studio
    job_id = m.group(1)
    jid, index = studio.split_ref(job_id)
    found = next(((c, j) for c in channels() for j in c.get("jobs") or [] if j.get("job_id") == jid), None)
    if found and not index:
        status = found[1].get("status")
    else:
        # The main channel's clips and the owner's uploads are Studio videos too.
        try:
            path = studio.job_dir(job_id)
            studio.clip_of(studio._read(path), index)
        except studio.StudioError:
            return "That video is no longer in Shortkaar."
        main = studio.main_clip(jid, index, path)
        status = {"posted": "uploaded", "skipped": "skipped"}.get((main or {}).get("status"), "done")
    if status in ("skipped", "failed"):
        return f"That video was {status}, so there is nothing to edit."
    if not start_ai_edit:
        return "The editor is not running; open Shortkaar's Studio."
    if text.strip().lower().strip("?!. ") in SUGGEST_WORDS:
        return _phone_suggestions(job_id)
    try:
        start_ai_edit(job_id, text)
    except Exception as e:  # noqa: BLE001 — the reason goes back to the phone
        return f"Could not start the edit: {getattr(e, 'detail', None) or e}"
    if status == "uploaded":
        return "Working on it. It is already on YouTube, so only the title, description and tags can change."
    return f"Working on it: \"{text[:120]}\". The new version comes here in about a minute."


def telegram_press(data):
    """A button pressed in Telegram (telegram_notify.poll): the answer text."""
    kind, _, rest = data.partition(":")
    if kind == "ed":
        return _press_suggestion(rest)
    cid, _, job_id = rest.partition(":")
    if kind != "skip" or not cid or not job_id:
        return ""
    ch = get(cid)
    job = next((j for j in (ch or {}).get("jobs") or [] if j.get("job_id") == job_id), None)
    if not job:
        return "That video is no longer in Shortkaar."
    if skip(cid, job_id):
        return f"Skipped. {ch['name']} makes another one in its place."
    status = job.get("status")
    if status == "skipped":
        return "Already skipped."
    if status == "uploaded":
        return "Too late: it has already been uploaded. Remove it in YouTube Studio if you want it gone."
    if status == "failed":
        return "Nothing to skip: that video failed and was never uploaded."
    return "That video is not finished yet, so there is nothing to skip."


def skip(cid, job_id):
    """Never upload this waiting Short; it no longer counts as made today, so
    the loop makes another in its place. Returns False when it is not waiting."""
    ch = get(cid)
    job = next((j for j in (ch or {}).get("jobs") or [] if j.get("job_id") == job_id), None)
    if not job or job.get("status") != "done":
        return False
    _set_job(cid, job_id, status="skipped")
    return True


def promo_targets(exclude):
    """[(handle, kind)] of the owner's other connected channels."""
    import youtube_account as ya
    out = []
    if exclude != "main":
        with ya.use(None):
            yt = ya.status()
        if yt.get("connected") and (yt.get("channel") or {}).get("handle"):
            out.append((yt["channel"]["handle"], "comedy"))
    for c in channels():
        if c["id"] == exclude or c.get("kind") == "quran":
            continue
        with ya.use(account(c["id"])):
            yt = ya.status()
        handle = c.get("handle") or (yt.get("channel") or {}).get("handle") or ""
        if yt.get("connected") and handle:
            out.append((handle if handle.startswith("@") else "@" + handle, engage_kind(c)))
    return out


def engage_kind(ch):
    """The kind engage.py words comments, playlists and replies for: a long
    channel in explainer mode is not a history channel any more."""
    if ch.get("kind") == "history" and ch.get("mode") in ("explainer", "horror"):
        return ch["mode"]
    return ch["kind"]


def upload_genre(ch, j):
    """The genre an upload goes up as (youtube_account.CATEGORY): a horror story is Entertainment, its Shorts
    too; the history channel's Shorts are "history_teaser"."""
    if j.get("format") == "mix":
        # A long video: the songs' mood mix (Music) or the cartoon series' compilation (Comedy).
        return "toons_mix" if ch.get("kind") == "toons" else "music_mix"
    horror = ch.get("kind") == "history" and ch.get("mode") == "horror"
    if j.get("format") in EXTRA_FORMATS:
        return "horror_teaser" if horror else "history_teaser"
    return "horror" if horror else KINDS[ch["kind"]]["genre"]


def promote(description, cid):
    """The description with a "More from us" line, when that channel's
    cross_promo switch is on and there is another connected channel."""
    import engage
    if (get(cid) or {}).get("kind") == "quran":
        return description             # never a comedy or dance channel under a recitation
    on = main_settings()["cross_promo"] if cid == "main" else engage_settings(get(cid) or {})["cross_promo"]
    try:
        return engage.with_promo(description, promo_targets(cid)) if on else description
    except Exception:  # noqa: BLE001 — a promo line never stops an upload
        return description


def engage_pass(cid, client_fn, log=print):
    """First comments, playlists and replies for one channel ("main" too)."""
    import engage
    import youtube_account as ya
    acct = None if cid == "main" else account(cid)
    moods, ch = None, None
    if cid == "main":
        sw, kind = main_settings(), "comedy"
    else:
        ch = get(cid)
        if not ch:
            return
        sw, kind = engage_settings(ch), engage_kind(ch)
        if ch["kind"] == "music":
            import music_moods                     # songs also go into their mood's playlist
            moods = music_moods.settings_of(ch.get("moods"))
    st = engage.load(acct)
    if time.time() - st.get("last_pass", 0) < ENGAGE_EVERY:
        return
    engage._update(acct, lambda s: s.update(last_pass=int(time.time())))
    with ya.use(acct):
        yt = ya.status()
        if not yt.get("connected"):
            return
        me = yt.get("channel") or {}
        for key, job in (("first_comment", lambda: engage.first_comments(acct, kind, log)),
                         ("playlists", lambda: engage.add_to_playlists(acct, kind, log, moods=moods)),
                         ("podcasts", lambda: engage.podcasts(acct, kind, me.get("title") or "",
                                                              (ch or {}).get("color") or "#1F1408", log)),
                         ("auto_reply", lambda: engage.reply_due(acct) and engage.auto_replies(
                             acct, kind, me.get("handle") or "", me.get("id"), client_fn, log))):
            if not sw.get(key):
                continue
            try:
                job()
            except Exception as e:  # noqa: BLE001 — one failing step never stops the others
                log(f"⚠️ {cid}: {key} failed ({type(e).__name__}: {str(e)[:120]}).")


def _set_job(cid, job_id, **fields):
    def fn(c):
        for j in c.get("jobs") or []:
            if j.get("job_id") == job_id:
                j.update(fields)
    _change(cid, fn)


def claim_check(ch, log=print):
    import youtube_account
    _change(ch["id"], lambda c: c.update(last_claim_check=int(time.time())))
    with youtube_account.use(account(ch["id"])):
        if not youtube_account.status()["connected"]:
            return []
        found = youtube_account.claim_check()
    for row in found:
        log(f"🚫 {ch['name']}: '{row.get('title', '')[:60]}' is blocked ({row.get('block_reason')}).")
    return found


# ------------------------------------------------------------------ loop

_disk_said = [0.0]


async def tick(submit, job_clips, output_dir, client_fn, log=print, now=None):
    """One pass over every channel (the loop calls this each minute)."""
    loop = asyncio.get_event_loop()
    t = now or time.time()
    rows = channels()
    for ch in rows:
        refresh_jobs(ch, job_clips, output_dir, t)
    rows = channels()
    live, settled = [], []
    for ch in rows:
        if not ch.get("enabled"):
            continue
        st = await loop.run_in_executor(None, connected, ch)
        if st.get("connected"):
            live.append(ch)
            if not settling(st, t):
                settled.append(ch)
            elif not ch.get("placement_checked") or ch["placement_checked"] < st.get("granted_at", 0):
                # Just connected: did an earlier connection of this card put videos elsewhere?
                _change(ch["id"], lambda c: c.update(placement_checked=int(t)))
                try:
                    await loop.run_in_executor(None, check_placement, ch["id"], log)
                except Exception as e:  # noqa: BLE001 — the learn pass checks again
                    log(f"⚠️ {ch['name']}: placement check failed ({type(e).__name__}).")
    # One generated job at a time on this laptop: a sample the owner asked for
    # first (connected or not), else the channel furthest behind.
    room = disk_free_gb() >= MIN_FREE_GB
    if not room and t - _disk_said[0] >= 3600:
        _disk_said[0] = t
        log(f"⚠️ Only {disk_free_gb():.1f} GB free on the disk: no new videos until {MIN_FREE_GB} GB are free.")
    if room and not any(running(c) for c in rows):
        samples = [c for c in rows if c.get("sample_wanted")]
        behind = [c for c in settled if wants_more(c)]
        if samples:
            ch = min(samples, key=lambda c: c.get("sample_wanted", 0))
            _change(ch["id"], lambda c: c.pop("sample_wanted", None))
            await make_one(submit, ch, client_fn, log)
        elif behind:
            ch = min(behind, key=lambda c: (len(_jobs_on(c, today())) / max(1, c["per_day"]), c.get("created", 0)))
            await make_one(submit, ch, client_fn, log)
    # Skip presses on the review messages (Telegram) before any upload, so a
    # press just before the hold ends still stops it.
    # Text replies there are AI edits from the phone (telegram_reply), so it polls whenever the editor is
    # wired up too (poll returns at once when Telegram is not connected).
    if any(c.get("review_hours") for c in rows) or start_ai_edit:
        try:
            import telegram_notify
            await loop.run_in_executor(None, lambda: telegram_notify.poll(telegram_press, on_text=telegram_reply))
        except Exception as e:  # noqa: BLE001
            log(f"⚠️ Telegram poll: {type(e).__name__}")
    for ch in live:
        ch = get(ch["id"]) or ch
        if ch["id"] in {c["id"] for c in settled} and upload_due(ch, t):
            import keep_awake
            with keep_awake.task():
                await loop.run_in_executor(None, upload_waiting, ch, job_clips, log)
        if t - ch.get("last_claim_check", 0) >= CLAIM_CHECK_EVERY:
            await loop.run_in_executor(None, claim_check, ch, log)
        if t - ch.get("last_learn", 0) >= LEARN_EVERY:
            await loop.run_in_executor(None, learn, ch, log)
            await loop.run_in_executor(None, retry_extras, ch, log)
            await loop.run_in_executor(None, about_credit, get(ch["id"]) or ch, log)
            try:
                await loop.run_in_executor(None, check_placement, ch["id"], log)
            except Exception as e:  # noqa: BLE001 — next learn pass
                log(f"⚠️ {ch['name']}: placement check failed ({type(e).__name__}).")
        if (ch.get("took_over") or {}).get("hide") and not ch["took_over"].get("hide_done"):
            try:
                await loop.run_in_executor(None, hide_retired, ch, log, t)
            except Exception as e:  # noqa: BLE001 — the next pass
                log(f"⚠️ {ch['name']}: hiding the old videos failed ({type(e).__name__}).")
        if ch.get("kind") == "cricket":
            await loop.run_in_executor(None, match_watch, ch, client_fn, log, t)
    # Engagement on every connected channel, the main one included.
    for cid in ["main"] + [c["id"] for c in live]:
        await loop.run_in_executor(None, engage_pass, cid, client_fn, log)
    await loop.run_in_executor(None, meta_pass, log, t)
    await loop.run_in_executor(None, research_pass, [niche_of(c) for c in live], client_fn, log, t)


def research_pass(niches, client_fn, log=print, now=None):
    """The research agent of ONE niche that is due (niche_research.run), the main channel's comedy
    included: one per loop tick keeps each tick short (a pass is ~30-60 s of searches and Gemini
    watching). Returns the niche researched, or None."""
    import niche_research
    if not niche_research.enabled():
        return None
    for niche in dict.fromkeys(["comedy"] + list(niches)):
        if niche in niche_research.NICHES and niche_research.due(niche, now):
            ch = next((c for c in channels() if niche_of(c) == niche), None)
            stats = (ch or {}).get("stats") or {}
            ours = (f"{stats.get('counted')} videos counted, median {stats.get('median')} views, "
                    f"{stats.get('watched')}% watched" if stats.get("counted") else "")
            try:
                niche_research.run(niche, client_fn(), log, now, ours=ours, ours_files=recent_files(niche))
            except Exception as e:  # noqa: BLE001 — run() already never raises; the client might
                log(f"⚠️ Research for {niche} failed ({type(e).__name__}).")
            return niche
    return None


def recent_files(niche, rows=None, output_dir=None):
    """Our uploaded videos of ``niche`` whose file is still in its job folder (about a day), newest first:
    [{"id", "path", "title", "views", "channel"}], for teardown.py to measure against the niche's winners.
    A long channel's Shorts (teasers, "Aaj ki tareekh") and the song mixes are not its main videos."""
    import youtube_account
    output_dir = output_dir or os.path.join(ROOT, "output")
    out = []
    for ch in (channels() if rows is None else rows):
        if niche_of(ch) != niche:
            continue
        with youtube_account.use(account(ch["id"])):
            ups = youtube_account.uploads()
        for r in sorted(ups, key=lambda r: r.get("created", 0), reverse=True):
            vid = r.get("video_id")          # YouTube's id ("id" is our own row id)
            if r.get("status") != "done" or not vid or r.get("format") in EXTRA_FORMATS:
                continue
            path = os.path.join(output_dir, str(r.get("job_id") or ""), str(r.get("file") or ""))
            if r.get("job_id") and r.get("file") and os.path.isfile(path):
                out.append({"id": vid, "path": path, "title": r.get("title"), "views": r.get("views"),
                            "channel": ch["id"]})
    return out


META_EVERY = 10 * 60
_last_meta = [0.0]


def meta_pass(log=print, now=None):
    """Post the Shorts queued for Facebook / Instagram whose time has come (meta_publish.post_pass)."""
    now = now or time.time()
    if now - _last_meta[0] < META_EVERY:
        return 0
    _last_meta[0] = now
    try:
        import meta_publish
        if not meta_publish.status()["connected"] or not meta_publish.queue():
            return 0
        import keep_awake
        with keep_awake.task():
            return meta_publish.post_pass(log, now, score=meta_score)
    except Exception as e:  # noqa: BLE001 — next pass
        log(f"⚠️ Facebook / Instagram pass failed ({type(e).__name__}).")
        return 0


META_IG_MODES = ("auto", "all", "winners")
# Few Instagram accounts (owner, 5-nov-2026, "I will go with your suggestions"): cricket has its own; the
# Roman-Urdu story channels share one; songs (an English audience) and the Quran stay on Facebook only.
IG_GROUPS = {"cricket": "cricket", "controversy": "stories", "money": "stories", "history": "stories",
             "quiz": "stories", "music": None, "quran": None,
             "toons": "toons"}            # cartoon animals are Reels' best fit: their own account, not a hub
_STOP = {"the", "and", "of", "in", "a", "an", "ki", "ka", "ke", "official", "page", "tv"}


def _words(text):
    return set(re.findall(r"[a-z0-9]+", str(text or "").lower())) - _STOP


def page_for(ch, pages, taken=()):
    """The Facebook Page named like this card (its name or its YouTube channel's), or None."""
    best, score = None, 0.0
    names = [ch.get("name"), ch.get("yt_title"), (ch.get("took_over") or {}).get("yt_title")]
    for p in pages:
        pw = _words(p.get("name"))
        if p["id"] in taken or not pw:
            continue
        for n in names:
            nw = _words(n)
            s = len(pw & nw) / len(pw | nw) if nw else 0.0
            if s > score:
                best, score = p, s
    return best if score >= 0.5 else None


def auto_link(rows=None, pages=None, log=print):
    """After Facebook is connected (or its Pages read again): each card without a Page gets the one named like
    it, and its Instagram: its own Page's when it has one, else the account its IG_GROUPS group shares; songs
    and the Quran Facebook only. Choices the owner made stay. [{"card", "name", "page", "instagram"}]."""
    import meta_publish
    rows = [c for c in (channels() if rows is None else rows) if c.get("id") != "main"]
    pages = (meta_publish._token() or {}).get("pages") or [] if pages is None else pages
    by_id = {p["id"]: p for p in pages}
    taken = {c["meta_page"] for c in rows if c.get("meta_page") in by_id}
    fresh = set()
    for ch in rows:
        if ch.get("meta_page") in by_id:
            continue
        p = page_for(ch, pages, taken)
        if p:
            taken.add(p["id"])
            ch["meta_page"] = p["id"]
            fresh.add(ch["id"])
            _change(ch["id"], lambda c, pid=p["id"]: c.update(meta_page=pid))
    hubs = {}
    for ch in rows:                      # a group's shared account: the Instagram of one of its own Pages
        p = by_id.get(ch.get("meta_page"))
        g = IG_GROUPS.get(ch.get("kind"))
        if g and p and p.get("ig_id"):
            hubs.setdefault(g, p["id"])
    out = []
    for ch in rows:
        own = by_id.get(ch.get("meta_page")) or {}
        g = IG_GROUPS.get(ch.get("kind"), "stories")
        if ch["id"] in fresh and not ch.get("meta_ig_page"):
            if g is None:
                patch = {"meta_ig": False}
            elif own.get("ig_id"):
                patch = {"meta_ig": True, "meta_ig_page": ""}
            elif hubs.get(g):
                patch = {"meta_ig": True, "meta_ig_page": hubs[g]}
            else:
                patch = {}
            if patch:
                ch.update(patch)
                _change(ch["id"], lambda c, x=patch: c.update(x))
        ig = by_id.get(ch.get("meta_ig_page") or ch.get("meta_page")) if ch.get("meta_ig", True) else None
        out.append({"card": ch["id"], "name": ch.get("name"), "page": own.get("name") or "",
                    "instagram": (ig or {}).get("ig_username") or ""})
    if fresh:
        log(f"🔗 Facebook: {len(fresh)} channel(s) linked to their Pages by name.")
    return out


def meta_ig_mode(ch, rows=None):
    """"all" or "winners": which of the card's Shorts go to its Instagram. "auto" (the default) is
    "winners" when another running card posts to the same Instagram (owner, 5-nov-2026: one or two
    Instagram accounts for all the channels), so a shared account gets only what already won on YouTube."""
    mode = ch.get("meta_ig_mode") or "auto"
    if mode != "auto":
        return mode
    mine = ch.get("meta_ig_page") or ch.get("meta_page")
    if not mine or not ch.get("meta_ig", True):
        return "all"
    rows = channels() if rows is None else rows
    shared = any(c.get("id") != ch.get("id") and c.get("enabled") and c.get("meta_ig", True)
                 and (c.get("meta_ig_page") or c.get("meta_page")) == mine for c in rows)
    return "winners" if shared else "all"


def meta_score(item):
    """(views, the channel's median views) of a queued Short's YouTube upload, for meta_publish's
    winners-only Instagram; None when the card or its numbers are not known yet."""
    ch = get(item.get("channel"))
    vid = item.get("video_id") or str(item.get("id", "")).split("_", 1)[-1]
    if not ch or not vid:
        return None
    import youtube_account
    with youtube_account.use(account(ch["id"])):
        row = next((r for r in youtube_account.uploads() if (r.get("video_id") or r.get("id")) == vid), None)
    if not row or row.get("views") is None:
        return None
    return row["views"], (ch.get("stats") or {}).get("median") or 0


last_tick = None     # time.time() at the start of the loop's latest tick (heartbeat.py)


async def loop_forever(submit, job_clips, output_dir, client_fn, is_active=lambda: True, today_fn=None):
    global last_tick
    while True:
        await asyncio.sleep(TICK_SECONDS)
        if not is_active():
            continue
        last_tick = time.time()
        try:
            await tick(submit, job_clips, output_dir, client_fn)
        except Exception as e:  # noqa: BLE001 — the loop must survive a bad day
            print(f"⚠️ Channels error: {type(e).__name__}: {e}")
        if today_fn:
            try:
                import notify
                import reminders
                await asyncio.get_event_loop().run_in_executor(None, reminders.tick, today_fn, notify.toast)
            except Exception as e:  # noqa: BLE001
                print(f"⚠️ Reminder error: {type(e).__name__}: {e}")
