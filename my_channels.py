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
JOB_TIMEOUT = 50 * 60
KEEP_DAYS = 7
MAX_CHANNELS = 6
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
    "cricket": {"label": "Cricket facts and updates", "genre": "cricket", "color": "#0B3D2E",
                "times": ["11:30", "13:30", "15:30", "17:30", "19:30", "21:30", "23:30", "00:30"],
                "about": "Animated stats, records and match results with a voice-over and free-licence "
                         "player photos. Ideas come from Google Search every day."},
    "quiz": {"label": "Quiz and paheliyan", "genre": "quiz", "color": "#16206B",
             "times": ["10:00", "12:00", "14:00", "16:00", "18:00", "20:00", "22:00", "00:00"],
             "about": "General knowledge questions, paheliyan and quick maths puzzles with a countdown. "
                      "Viewers answer in the comments before the reveal."},
    "controversy": {"label": "Controversies, explained", "genre": "controversy", "color": "#2A0A0A",
                    "times": ["11:15", "13:15", "15:15", "17:15", "19:15", "21:15", "23:15", "00:45"],
                    "about": "What really happened in famous people's controversies: researched with sources, "
                             "allegations told as allegations, both sides, a fairness check before every video. "
                             "No religion, politics or army."},
    "music": {"label": "AI songs in English", "genre": "music", "color": "#2A0B2E",
              "times": ["01:00", "04:00", "07:00", "10:00", "13:00", "16:00", "19:00", "22:00"],
              "about": "Original songs under a minute: AI lyrics, sung by Google Lyria, with a cover "
                       "picture and the lyrics on screen. About $0.15 of Gemini per song."},
    # Long 16:9 videos (history_videos.py): 1-3 a day, a job takes 15-60 min on the laptop.
    "history": {"label": "History and stories (long videos)", "genre": "history", "color": "#1F1408",
                "times": ["18:00", "21:00"], "per_day": 2, "max_per_day": 3, "long": True, "timeout": 3 * 3600,
                "notes": "Rome, Karbala, the Caliphs, the US government, the US economy",
                "about": "2 to 30 minute documentaries about empires, countries and famous events: researched "
                         "with sources, a narrator, free Wikipedia pictures and AI pictures, chapters and a "
                         "thumbnail. About $1 of Gemini per 10-minute video."},
}
# The planner module of each kind that works from a queue of researched ideas.
PLANNERS = {"cricket": "cricket_shorts", "controversy": "controversy_shorts", "history": "history_videos"}
MINUTES_RANGE, DEFAULT_MINUTES = (2, 30), 10
LANGS = ("urdu", "english")
FORMATS = {"quiz": ["mcq", "riddle", "math", "flags", "truefalse", "oddone"]}
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
ENGAGE_DEFAULTS = {"first_comment": True, "auto_reply": True, "playlists": True, "cross_promo": True}
MAIN_ENGAGE_DEFAULTS = {k: False for k in ENGAGE_DEFAULTS}
ENGAGE_EVERY = 900
_lock = threading.Lock()
_ideas_failed = {}
failure_reason = None     # app.py sets it: job id -> the one-line reason the job failed


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
          **ENGAGE_DEFAULTS, **({"minutes": DEFAULT_MINUTES, "lang": "urdu"} if k.get("long") else {}),
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
        if "review_hours" in patch:
            try:
                ch["review_hours"] = max(0, min(REVIEW_MAX_HOURS, int(patch["review_hours"])))
            except (TypeError, ValueError):
                pass
        if KINDS.get(ch["kind"], {}).get("long"):
            if "minutes" in patch:
                try:
                    ch["minutes"] = max(MINUTES_RANGE[0], min(MINUTES_RANGE[1], int(patch["minutes"])))
                except (TypeError, ValueError):
                    pass
            if patch.get("lang") in LANGS:
                ch["lang"] = patch["lang"]
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


# ------------------------------------------------------------------ status

def today(now=None):
    return (now or datetime.now()).strftime("%Y-%m-%d")


def _jobs_on(ch, day, statuses=("running", "done", "uploaded")):
    """The day's jobs; a long video's teaser Short is extra, not one of the day's videos."""
    return [j for j in ch.get("jobs") or [] if j.get("day") == day and j.get("status") in statuses
            and j.get("format") not in EXTRA_FORMATS]


# Shorts of the history channel that come on top of its long videos.
EXTRA_FORMATS = ("teaser", "today")


def today_short_due(ch, now=None):
    """True while the history channel still owes today's "Aaj ki tareekh"
    Short (history_today.py): on by default (daily_short), two tries a day."""
    if not KINDS.get(ch.get("kind"), {}).get("long") or not ch.get("daily_short", True):
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
    if not KINDS.get(ch.get("kind"), {}).get("long"):
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
        or (j.get("status") == "uploaded" and KINDS.get(ch.get("kind"), {}).get("long")
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
    if long:
        out.update(minutes=ch.get("minutes", DEFAULT_MINUTES), lang=ch.get("lang", "urdu"))
    out.update({
        "max_per_day": cap(ch), "long": long,
        **engage_settings(ch), "match_watch": bool(ch.get("match_watch", True)),
        "kind_label": KINDS.get(ch["kind"], {}).get("label", ch["kind"]),
        "youtube": yt, "made_today": len(_jobs_on(ch, day)),
        "uploaded_today": sum(1 for r in rows if r.get("status") == "done"
                              and today(datetime.fromtimestamp(r.get("created", 0))) == day),
        "waiting": len(waiting(ch)), "running": [j.get("label") for j in running(ch)],
        "jobs": sorted(ch.get("jobs") or [], key=lambda j: j.get("at", 0), reverse=True)[:12],
        "uploads": rows[:12], "ideas_left": len(ch.get("ideas") or []),
        "plans_ideas": ch["kind"] in PLANNERS,
        "up_next": [i.get("text", "") for i in (ch.get("ideas") or [])[:UP_NEXT_SHOWN]],
        "up_next_series": [f"{i['series']}, part {i['part']} of {i['parts']}" if i.get("series") else ""
                           for i in (ch.get("ideas") or [])[:UP_NEXT_SHOWN]],
    })
    return out


UP_NEXT_SHOWN = 8


def _owner_idea(kind, text):
    """An idea the owner typed, in the planner's shape. Cricket needs its
    kind: "India vs Pakistan, Asia Cup final" is a match, "Babar vs Kohli" a
    player fight, anything else a topic."""
    if kind == "cricket" and re.search(r"\bvs\.?\b|\bversus\b", text, re.I):
        return {"kind": "match" if re.search(r",|\b(final|semi|cup|trophy|series|test|odi|t20|league|psl|ipl)\b",
                                             text, re.I) else "versus", "text": text, "owner": True}
    return {"kind": "topic", "text": text, "owner": True}


def add_idea(cid, text):
    """The owner's own topic, made next."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:140]
    ch = get(cid)
    if not ch or ch["kind"] not in PLANNERS:
        raise ValueError("This channel picks its own topics.")
    if not text:
        raise ValueError("Write a topic first.")
    idea = _owner_idea(ch["kind"], text)

    def fn(c):
        rest = [i for i in c.get("ideas") or [] if i.get("text", "").lower() != text.lower()]
        # A just-finished match (urgent) still goes first: it is news for a few hours only.
        urgent = [i for i in rest if i.get("urgent")]
        c["ideas"] = urgent + [idea] + [i for i in rest if not i.get("urgent")]
    return _change(cid, fn)


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
        c["used"] = ((c.get("used") or []) + [t[:140] for t in gone or [text]])[-300:]
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
            youtube_account._save_upload(r)
            try:
                age = now - datetime.fromisoformat((n["published"] or "").replace("Z", "+00:00"))
            except ValueError:
                continue
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
                youtube_account._save_upload(r)
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
             "median": _median([r["views"] for r in mature]),
             "formats": {f: {"shorts": len(v), "median": _median(v),
                             **({"watched": _median(kept[f])} if kept.get(f) else {})}
                         for f, v in by_format.items()},
             "watched": _median([x for v in kept.values() for x in v]) if kept else None,
             "best": [f"{r['title'][:80]} ({r['views']} views)" for r in ranked[:5]],
             "worst": [f"{r['title'][:80]} ({r['views']} views)" for r in ranked[-5:][::-1]]
             if len(ranked) >= 8 else []}
    # The end card A/B test (ab_choice): median views with and without it.
    arms = {}
    for r in mature:
        if r.get("outro") is not None and r.get("format") != "teaser":
            arms.setdefault(str(bool(r["outro"])).lower(), []).append(r["views"])
    stats["ab"] = {"outro": {k: {"shorts": len(v), "median": _median(v)} for k, v in arms.items()}}
    stats["hours"] = _by_hour(mature)

    def fn(c):
        c["stats"] = stats
        c["last_learn"] = int(time.time())
    log(f"📈 {ch['name']}: {stats['counted']} Shorts counted, median {stats['median']} views.")
    return _change(ch["id"], fn)


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
    if not KINDS.get(ch.get("kind"), {}).get("long"):
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


AB_MIN = 6            # Shorts counted per side before a side can win
AB_LEAD = 1.2         # the winner's median must beat the other's by this much
AB_EXPLORE = 0.2


def ab_choice(ch, rnd=random):
    """With or without the FOLLOW end card for the next Short: the end card
    asks for a follow but stops a Short from looping, and replays count as
    views, so each channel tests it on its own Shorts. Alternate until both
    sides have AB_MIN counted, then the clear winner (AB_LEAD) most of the
    time; no clear winner keeps alternating."""
    seen = ((ch.get("stats") or {}).get("ab") or {}).get("outro") or {}
    on, off = seen.get("true") or {}, seen.get("false") or {}
    if on.get("shorts", 0) >= AB_MIN and off.get("shorts", 0) >= AB_MIN and rnd.random() >= AB_EXPLORE:
        if on["median"] >= off["median"] * AB_LEAD:
            return True
        if off["median"] >= on["median"] * AB_LEAD:
            return False
    made = [j.get("outro") for j in ch.get("jobs") or [] if j.get("outro") is not None
            and j.get("status") in ("running", "done", "uploaded")]
    return made.count(True) <= made.count(False)


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


AB_KINDS = ("cricket", "controversy", "quiz")     # songs and long videos have no end card


def next_payload(ch, client_fn, log=print):
    """(payload, meta) for the channel's next Short, or (None, None); the
    Shorts channels also get the end card A/B side (ab_choice)."""
    payload, meta = _next_payload(ch, client_fn, log)
    if payload and ch["kind"] in AB_KINDS and meta.get("format") != "teaser":
        payload["frame_outro"] = meta["outro"] = ab_choice(ch)
    return payload, meta


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
                 "history_teaser_part": part, "bg_music": True},
                {"label": f"{'Moment ' + str(part) if part else 'Teaser'}: {long_video.get('label', '')}"[:120],
                 "format": "teaser", "part": part, "topic": long_video.get("topic"),
                 "teaser_of": long_video["job_id"], "publish_after": long_video.get("slot")})
    if today_short_due(ch):
        made = [u[6:] for u in ch.get("used") or [] if str(u).startswith("today:")]
        return ({**look, "genre": "history", "history_today": True, "history_lang": ch.get("lang", "urdu"),
                 "history_avoid": made[-40:], "bg_music": True},
                {"label": f"Aaj ki tareekh: {datetime.now():%d %B}", "format": "today", "topic": ""})
    if kind in PLANNERS:
        if not ch.get("ideas"):
            if time.time() - _ideas_failed.get(ch["id"], 0) < IDEAS_RETRY:
                return None, None
            import importlib
            planner = importlib.import_module(PLANNERS[kind])
            # The history channel also hears the owner's topic wishes, its language and length.
            extra = ({"notes": ch.get("notes") or "", "lang": ch.get("lang", "urdu"),
                      "minutes": ch.get("minutes", DEFAULT_MINUTES)} if kind == "history" else {})
            # Topics viewers asked for in comments (engage.auto_replies); the
            # planner's own rules still decide whether any of them is made.
            import engage
            import inspect
            asked = engage.requests(account(ch["id"]))
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
        idea = ch["ideas"][0]
        _change(ch["id"], lambda c: c.update(ideas=(c.get("ideas") or [])[1:]))
        if kind == "controversy":
            return ({**look, "genre": "controversy", "controversy_topic": idea["text"], "bg_music": True},
                    {"label": idea["text"], "format": "controversy", "topic": idea["text"]})
        if kind == "history":
            series = ({"history_series": idea["series"], "history_part": idea["part"],
                       "history_parts": idea["parts"], "history_before": idea.get("before") or []}
                      if idea.get("series") else {})
            return ({**look, "genre": "history", "history_topic": idea["text"], "bg_music": True,
                     "history_minutes": long_minutes(ch), "history_lang": ch.get("lang", "urdu"),
                     "frame_outro": False, **series},
                    {"label": (f"Part {idea['part']}: " if series else "") + idea["text"], "format": "history",
                     "topic": idea["text"],
                     **({"series": idea["series"], "series_part": idea["part"]} if series else {})})
        return ({**look, "genre": "cricket", "cricket_mode": idea["kind"], "cricket_match": idea["text"],
                 "bg_music": True},
                {"label": idea["text"], "format": idea["kind"], "topic": idea["text"],
                 **({"urgent": True} if idea.get("urgent") else {})})
    if kind == "quiz":
        import quiz_shorts
        fmt = pick_format(ch, FORMATS["quiz"])
        topic = random.choice(quiz_shorts.TOPICS) if fmt in quiz_shorts.FACT_FORMATS else ""
        if ch.get("notes") and fmt in quiz_shorts.FACT_FORMATS and random.random() < 0.5:
            topic = ch["notes"][:80]
        # The channel's running number: "QUIZ #12" makes a daily series to come back for.
        number = 1 + sum(1 for j in ch.get("jobs") or [] if j.get("status") in ("done", "uploaded"))
        return ({**look, "genre": "quiz", "quiz_format": fmt, "quiz_topic": topic, "bg_music": True,
                 "quiz_avoid": (ch.get("used") or [])[-80:], "quiz_number": number},
                {"label": f"{fmt}{': ' + topic if topic else ''}", "format": fmt, "topic": topic})
    if kind == "music":
        import music_shorts
        style = pick_format(ch, music_shorts.STYLES)
        theme = random.choice(music_shorts.THEMES)
        # No end card on songs: a Short that ends on the music loops straight
        # back into the first line, and replays count as views.
        return ({**look, "genre": "music", "music_style": style, "music_theme": theme, "frame_outro": False,
                 "music_avoid": (ch.get("used") or [])[-60:]},
                {"label": f"{style} song about {theme}", "format": style, "topic": theme})
    return None, None


def wants_more(ch, now=None):
    day = today(now)
    if not ch.get("enabled") or running(ch) or ch.get("paused_until", 0) > (now.timestamp() if now else time.time()):
        return False
    if teaser_due(ch) or today_short_due(ch, now):
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
    _change(ch["id"], lambda c: c.update(jobs=((c.get("jobs") or []) + [row])[-200:]))
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
        elif now - j.get("at", now) > KINDS.get(ch["kind"], {}).get("timeout", JOB_TIMEOUT):
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
                    f"{ch['review_hours']} h unless you skip it here or in Shortkaar (Channels tab).",
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
    prev = history_videos.series_rows(youtube_account.uploads(), j["series"]).get(part - 1)
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


def _remake(cid, j):
    """A planned topic goes back to the front of the ideas (after urgent
    results), for a video that cannot be posted as it was made."""
    if not j.get("topic") or j.get("format") in EXTRA_FORMATS or j.get("series"):
        return
    kind = j["format"] if j.get("format") in ("match", "versus", "topic") else "topic"

    def fn(c):
        if c["kind"] not in PLANNERS:
            return
        rest = [i for i in c.get("ideas") or [] if i.get("text") != j["topic"]]
        urgent = [i for i in rest if i.get("urgent")]
        c["ideas"] = urgent + [{"kind": kind, "text": j["topic"]}] + [i for i in rest if not i.get("urgent")]
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
                long = bool(KINDS.get(ch["kind"], {}).get("long")) and j.get("format") not in EXTRA_FORMATS
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
            if KINDS[ch["kind"]].get("long") and j.get("format") not in EXTRA_FORMATS:
                import history_videos
                ups = youtube_account.uploads()
                if j.get("series"):
                    desc = history_videos.series_links(desc, ups, j["series"], j.get("series_part") or 1,
                                                       ch.get("lang", "urdu"))
                desc = history_videos.watch_next(desc, ups, ch.get("lang", "urdu"))
            row = youtube_account.upload(
                clip["path"], clip["title"], desc, clip["tags"],
                "history_teaser" if j.get("format") in EXTRA_FORMATS else KINDS[ch["kind"]]["genre"],
                publish_at=slot, ai_made=clip.get("ai_made", False),
                meta={"job_id": j["job_id"], "clip_index": clip["index"], "channel": ch["id"],
                      "format": j.get("format"), "topic": j.get("topic"), "seconds": clip.get("seconds"),
                      "question": clip.get("question") or "", "answers": clip.get("answers") or [],
                      **({"series": j["series"], "series_part": j.get("series_part")} if j.get("series") else {}),
                      **({"outro": j["outro"]} if j.get("outro") is not None else {})})
            if row.get("status") == "done":
                done += 1
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


def telegram_press(data):
    """A button pressed in Telegram (telegram_notify.poll): the answer text."""
    kind, _, rest = data.partition(":")
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
        if c["id"] == exclude:
            continue
        with ya.use(account(c["id"])):
            yt = ya.status()
        handle = c.get("handle") or (yt.get("channel") or {}).get("handle") or ""
        if yt.get("connected") and handle:
            out.append((handle if handle.startswith("@") else "@" + handle, c["kind"]))
    return out


def promote(description, cid):
    """The description with a "More from us" line, when that channel's
    cross_promo switch is on and there is another connected channel."""
    import engage
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
    if cid == "main":
        sw, kind = main_settings(), "comedy"
    else:
        ch = get(cid)
        if not ch:
            return
        sw, kind = engage_settings(ch), ch["kind"]
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
                         ("playlists", lambda: engage.add_to_playlists(acct, kind, log)),
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
    if any(c.get("review_hours") for c in rows):
        try:
            import telegram_notify
            await loop.run_in_executor(None, telegram_notify.poll, telegram_press)
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
            try:
                await loop.run_in_executor(None, check_placement, ch["id"], log)
            except Exception as e:  # noqa: BLE001 — next learn pass
                log(f"⚠️ {ch['name']}: placement check failed ({type(e).__name__}).")
        if ch.get("kind") == "cricket":
            await loop.run_in_executor(None, match_watch, ch, client_fn, log, t)
    # Engagement on every connected channel, the main one included.
    for cid in ["main"] + [c["id"] for c in live]:
        await loop.run_in_executor(None, engage_pass, cid, client_fn, log)


async def loop_forever(submit, job_clips, output_dir, client_fn, is_active=lambda: True, today_fn=None):
    while True:
        await asyncio.sleep(TICK_SECONDS)
        if not is_active():
            continue
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
