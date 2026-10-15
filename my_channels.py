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
CHANNELS_DIR = os.path.join(ROOT, "output", "channels")
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
FORMATS = {"quiz": ["mcq", "riddle", "math", "flags"]}
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


# ------------------------------------------------------------------ store

def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


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
        if KINDS.get(ch["kind"], {}).get("long"):
            if "minutes" in patch:
                try:
                    ch["minutes"] = max(MINUTES_RANGE[0], min(MINUTES_RANGE[1], int(patch["minutes"])))
                except (TypeError, ValueError):
                    pass
            if patch.get("lang") in LANGS:
                ch["lang"] = patch["lang"]
    return _change(cid, fn)


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
    return [j for j in ch.get("jobs") or [] if j.get("day") == day and j.get("status") in statuses]


def waiting(ch):
    return [j for j in ch.get("jobs") or [] if j.get("status") == "done"]


def running(ch):
    return [j for j in ch.get("jobs") or [] if j.get("status") == "running"]


def keeps(job_id, cid, age_seconds):
    """Keep a job folder past the retention sweep while its Short waits to upload."""
    if age_seconds > KEEP_DAYS * 86400:
        return False
    ch = get(cid)
    return bool(ch) and any(j.get("job_id") == job_id and j.get("status") in ("running", "done")
                            for j in ch.get("jobs") or [])


def connected(ch):
    import youtube_account
    with youtube_account.use(account(ch["id"])):
        return youtube_account.status()


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
    })
    return out


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
                and r.get("created", 0) >= since]
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
    by_format = {}
    for r in mature:
        by_format.setdefault(r.get("format") or "other", []).append(r["views"])
    ranked = sorted(mature, key=lambda r: r["views"], reverse=True)
    stats = {"at": int(time.time()), "tracked": len(rows), "counted": len(mature),
             "views": sum((numbers.get(r["video_id"]) or {}).get("views", 0) for r in rows),
             "median": _median([r["views"] for r in mature]),
             "formats": {f: {"shorts": len(v), "median": _median(v)} for f, v in by_format.items()},
             "best": [f"{r['title'][:80]} ({r['views']} views)" for r in ranked[:5]],
             "worst": [f"{r['title'][:80]} ({r['views']} views)" for r in ranked[-5:][::-1]]
             if len(ranked) >= 8 else []}

    def fn(c):
        c["stats"] = stats
        c["last_learn"] = int(time.time())
    log(f"📈 {ch['name']}: {stats['counted']} Shorts counted, median {stats['median']} views.")
    return _change(ch["id"], fn)


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
    return max(scored, key=lambda o: seen[o]["median"])


# ------------------------------------------------------------------ making

def _look(ch):
    yt = connected(ch).get("channel") or {}
    handle = ch.get("handle") or (yt.get("handle") or "")
    if handle and not handle.startswith("@"):
        handle = "@" + handle
    return {"output_format": "framed", "frame_handle": handle, "frame_bg_color": ch.get("color") or "#14142B",
            "frame_outro": True, "acknowledged": True, "channel": ch["id"]}


def next_payload(ch, client_fn, log=print):
    """(payload, meta) for the channel's next Short, or (None, None)."""
    kind = ch["kind"]
    look = _look(ch)
    stats = ch.get("stats") or {}
    if kind in PLANNERS:
        if not ch.get("ideas"):
            if time.time() - _ideas_failed.get(ch["id"], 0) < IDEAS_RETRY:
                return None, None
            import importlib
            planner = importlib.import_module(PLANNERS[kind])
            # The history channel also hears the owner's topic wishes, its language and length.
            extra = ({"notes": ch.get("notes") or "", "lang": ch.get("lang", "urdu"),
                      "minutes": ch.get("minutes", DEFAULT_MINUTES)} if kind == "history" else {})
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
            return ({**look, "genre": "history", "history_topic": idea["text"], "bg_music": True,
                     "history_minutes": ch.get("minutes", DEFAULT_MINUTES), "history_lang": ch.get("lang", "urdu"),
                     "frame_outro": False},
                    {"label": idea["text"], "format": "history", "topic": idea["text"]})
        return ({**look, "genre": "cricket", "cricket_mode": idea["kind"], "cricket_match": idea["text"],
                 "bg_music": True},
                {"label": idea["text"], "format": idea["kind"], "topic": idea["text"],
                 **({"urgent": True} if idea.get("urgent") else {})})
    if kind == "quiz":
        import quiz_shorts
        fmt = pick_format(ch, FORMATS["quiz"])
        topic = random.choice(quiz_shorts.TOPICS) if fmt == "mcq" else ""
        if ch.get("notes") and fmt == "mcq" and random.random() < 0.5:
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
    if not ch.get("enabled") or running(ch):
        return False
    made = len(_jobs_on(ch, day))
    tries = len(_jobs_on(ch, day, ("running", "done", "uploaded", "failed")))
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
    recent += [_teams(i["text"]) for i in ch.get("ideas") or [] if i.get("kind") == "match"]
    new = []
    for line in found:
        teams = _teams(line)
        if not teams or teams in recent:
            continue
        recent.append(teams)
        new.append({"kind": "match", "text": line, "urgent": True})
    if new:
        _change(ch["id"], lambda c: c.update(ideas=new + (c.get("ideas") or [])))
        log(f"⚡ {ch['name']}: just finished: {', '.join(x['text'][:60] for x in new)}. Making it next.")
    return new


async def make_one(submit, ch, client_fn, log=print, now=None):
    """Start the channel's next Short; returns the job id or None."""
    loop = asyncio.get_event_loop()
    payload, meta = await loop.run_in_executor(None, next_payload, ch, client_fn, log)
    if not payload:
        return None
    row = {"at": int(time.time()), "day": today(now), "status": "running", **meta}
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
            changed.append((j["job_id"], "failed", "the job failed", []))
        elif now - j.get("at", now) > KINDS.get(ch["kind"], {}).get("timeout", JOB_TIMEOUT):
            changed.append((j["job_id"], "failed", "took too long", []))
    if not changed:
        return ch

    def fn(c):
        for job_id, status, err, used in changed:
            for j in c.get("jobs") or []:
                if j.get("job_id") == job_id:
                    j["status"] = status
                    if err:
                        j["error"] = err
            topic = next((j.get("topic") for j in c["jobs"] if j.get("job_id") == job_id), None)
            if status == "done":
                adds = used or ([topic] if c["kind"] in PLANNERS and topic else [])
                c["used"] = ((c.get("used") or []) + [str(u)[:140] for u in adds if u])[-300:]
    return _change(ch["id"], fn)


# ------------------------------------------------------------------ uploading

def upload_due(ch, now=None):
    now = now or time.time()
    return (ch.get("enabled") and ch.get("auto_upload") and waiting(ch)
            and now >= ch.get("upload_paused_until", 0) and now - ch.get("last_upload", 0) >= UPLOAD_EVERY)


def upload_waiting(ch, job_clips, log=print):
    """Upload the channel's finished Shorts, each into its next free posting
    time. Stops at YouTube's daily limit and pauses the channel 3 h."""
    import youtube_account
    _change(ch["id"], lambda c: c.update(last_upload=int(time.time())))
    done, limit = 0, False
    with youtube_account.use(account(ch["id"])):
        if not youtube_account.status()["connected"]:
            return {"done": 0, "limit": False}
        for j in sorted(waiting(ch), key=lambda j: j.get("at", 0)):
            _state, clips = job_clips(j["job_id"])
            if not clips:
                _set_job(ch["id"], j["job_id"], status="failed", error="no longer on this computer")
                continue
            clip = clips[0]
            if j.get("urgent"):
                slot = datetime.now().astimezone() + timedelta(minutes=URGENT_AFTER_MINUTES)
            else:
                slot = youtube_account.next_slots(ch["post_times"], 1)[0]
            row = youtube_account.upload(
                clip["path"], clip["title"], promote(clip["description"], ch["id"]), clip["tags"],
                KINDS[ch["kind"]]["genre"], publish_at=slot, ai_made=clip.get("ai_made", False),
                meta={"job_id": j["job_id"], "clip_index": clip["index"], "channel": ch["id"],
                      "format": j.get("format"), "topic": j.get("topic"), "seconds": clip.get("seconds"),
                      "question": clip.get("question") or "", "answers": clip.get("answers") or []})
            if row.get("status") == "done":
                done += 1
                if clip.get("thumbnail"):
                    youtube_account.add_thumbnail(row, clip["thumbnail"])
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

async def tick(submit, job_clips, output_dir, client_fn, log=print, now=None):
    """One pass over every channel (the loop calls this each minute)."""
    loop = asyncio.get_event_loop()
    t = now or time.time()
    rows = channels()
    for ch in rows:
        refresh_jobs(ch, job_clips, output_dir, t)
    rows = channels()
    live = []
    for ch in rows:
        if not ch.get("enabled"):
            continue
        st = await loop.run_in_executor(None, connected, ch)
        if st.get("connected"):
            live.append(ch)
    # One generated job at a time on this laptop: the channel furthest behind.
    if not any(running(c) for c in rows):
        behind = [c for c in live if wants_more(c)]
        if behind:
            ch = min(behind, key=lambda c: (len(_jobs_on(c, today())) / max(1, c["per_day"]), c.get("created", 0)))
            await make_one(submit, ch, client_fn, log)
    for ch in live:
        ch = get(ch["id"]) or ch
        if upload_due(ch, t):
            await loop.run_in_executor(None, upload_waiting, ch, job_clips, log)
        if t - ch.get("last_claim_check", 0) >= CLAIM_CHECK_EVERY:
            await loop.run_in_executor(None, claim_check, ch, log)
        if t - ch.get("last_learn", 0) >= LEARN_EVERY:
            await loop.run_in_executor(None, learn, ch, log)
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
