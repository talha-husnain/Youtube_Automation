"""Daily Autopilot for a local install (the cloud one is cloud/autopilot.py).

Every day at ``run_at`` (local time) it makes the planned Shorts by itself:
comedy from the source channels (their newest videos first, never a moment
twice, used_moments.py) and cricket from this week's ideas
(cricket_shorts.ideas, never the same idea twice). The jobs go through the
normal /api/process, so they show up in History like any other. With
``auto_upload`` each finished Short is uploaded into the next free posting
time (youtube_account.next_slots).

The look of each Short is the look of the last job made by hand for that
type (``output/.last_settings.json``, written by /api/process), so the plan is
the only thing Autopilot asks for. A day the laptop was off at ``run_at`` is
made as soon as the server runs again that day.
"""
import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(ROOT, "output", ".autopilot.json")
LAST_SETTINGS_FILE = os.path.join(ROOT, "output", ".last_settings.json")
CLIPS_PER_VIDEO = 3
MAX_CHANNELS = 10
TICK_SECONDS = 60
# Fields of a hand-made job that describe its look, kept for Autopilot.
LOOK_FIELDS = ("output_format", "target_clips", "clip_min_seconds", "clip_max_seconds", "auto_hook",
               "auto_hook_style", "layouts", "frame_bg_color", "frame_crop", "frame_zoom", "frame_title",
               "frame_outro", "frame_outro_seconds", "frame_handle", "caption_script", "ai_take", "bg_music")
BRAND = {"output_format": "framed", "frame_handle": "@PunchlineBazaar", "frame_bg_color": "#2B0F3D"}
DEFAULTS = {
    "enabled": False, "run_at": "03:00", "comedy_per_day": 3, "cricket_per_day": 1,
    "channels": [], "cc_only": True, "min_minutes": 5, "max_minutes": 120,
    "cricket_kinds": "both", "auto_upload": False, "post_times": ["13:00", "19:00"],
    "last_run": None, "runs": [],
}


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


def settings():
    return {**DEFAULTS, **_read(SETTINGS_FILE, {})}


def _clock(t, default):
    t = str(t or "").strip()
    try:
        h, m = (int(x) for x in t.split(":"))
        return f"{h:02d}:{m:02d}" if 0 <= h < 24 and 0 <= m < 60 else default
    except ValueError:
        return default


def save(patch):
    """Merge the user's changes, keeping every value in range."""
    cfg = settings()
    for key in ("enabled", "cc_only", "auto_upload"):
        if key in patch:
            cfg[key] = bool(patch[key])
    for key, hi in (("comedy_per_day", 10), ("cricket_per_day", 5), ("min_minutes", 600), ("max_minutes", 600)):
        if key in patch:
            try:
                cfg[key] = max(0, min(hi, int(patch[key])))
            except (TypeError, ValueError):
                pass
    if "run_at" in patch:
        cfg["run_at"] = _clock(patch["run_at"], cfg["run_at"])
    if "post_times" in patch and isinstance(patch["post_times"], list):
        times = sorted({_clock(t, "") for t in patch["post_times"]} - {""})
        cfg["post_times"] = times[:6] or cfg["post_times"]
    if patch.get("cricket_kinds") in ("both", "match", "topic"):
        cfg["cricket_kinds"] = patch["cricket_kinds"]
    if "channels" in patch and isinstance(patch["channels"], list):
        cfg["channels"] = [c for c in patch["channels"] if isinstance(c, dict) and c.get("url")][:MAX_CHANNELS]
    _write(SETTINGS_FILE, cfg)
    return cfg


def remember_look(body):
    """Keep the look of a job made by hand, per video type (app.py calls this)."""
    genre = (body.get("genre") or "comedy").lower()
    look = {k: body[k] for k in LOOK_FIELDS if body.get(k) not in (None, "")}
    if not look:
        return   # a raw API call with no look of its own: keep the saved one
    data = _read(LAST_SETTINGS_FILE, {})
    data[genre] = {**look, "saved": int(time.time())}
    _write(LAST_SETTINGS_FILE, data)


def look(genre):
    saved = dict(_read(LAST_SETTINGS_FILE, {}).get(genre) or {})
    saved.pop("saved", None)
    return {**BRAND, **saved}


def looks_saved():
    return {g: v.get("saved") for g, v in _read(LAST_SETTINGS_FILE, {}).items()}


# ------------------------------------------------------------------ picking

def pick_videos(cfg, clips_needed, log):
    """[(video, clips)] for today: newest unused videos first, round robin over
    the channels, licence checked when ``cc_only``."""
    import channel_tools
    import used_moments
    lo, hi = cfg["min_minutes"] * 60, cfg["max_minutes"] * 60

    def _list(ch):
        try:
            return channel_tools.channel_videos(ch["url"], 15)
        except Exception as e:  # noqa: BLE001 — one dead channel must not stop the day
            log(f"Could not read {ch.get('name') or ch['url']}: {type(e).__name__}")
            return []

    with ThreadPoolExecutor(max_workers=4) as pool:
        lists = list(pool.map(_list, cfg["channels"]))
    fresh, partly = [], []
    for depth in range(15):                  # round robin: every channel's newest first
        for videos in lists:
            if depth >= len(videos):
                continue
            v = videos[depth]
            if not v.get("seconds") or not lo <= v["seconds"] <= hi:
                continue
            used = used_moments.summary(v["url"])
            if used["count"] == 0:
                fresh.append(v)
            elif used["seconds"] < 0.4 * v["seconds"]:
                partly.append(v)
    picked, left = [], clips_needed
    for v in fresh + partly:
        if left <= 0:
            break
        if cfg["cc_only"]:
            lic = channel_tools.licence(v["url"])
            if lic["licence"] != "creative_commons":
                log(f"Skipped (not Creative Commons): {v['title'][:60]}")
                continue
        n = min(CLIPS_PER_VIDEO, left)
        picked.append((v, n))
        left -= n
    return picked


def pick_ideas(cfg, count, log):
    import cricket_shorts
    import short_kit
    import used_moments
    try:
        ideas = cricket_shorts.ideas(short_kit.gemini())
    except Exception as e:  # noqa: BLE001
        log(f"Could not fetch cricket ideas: {type(e).__name__}")
        return []
    kinds = cfg["cricket_kinds"]
    ideas = [i for i in ideas if (kinds == "both" or i["kind"] == kinds) and not used_moments.topic_used(i["text"])]
    # Alternate a match and a topic when both are allowed.
    matches = [i for i in ideas if i["kind"] == "match"]
    topics = [i for i in ideas if i["kind"] == "topic"]
    mixed = [x for pair in zip(topics, matches) for x in pair] + topics[len(matches):] + matches[len(topics):]
    return mixed[:count]


# ------------------------------------------------------------------ running

async def run_now(submit, reason="schedule"):
    """Make today's Shorts. ``submit(payload) -> job_id`` posts one job."""
    import used_moments
    cfg = settings()
    today = datetime.now().strftime("%Y-%m-%d")
    run = {"at": int(time.time()), "date": today, "reason": reason, "jobs": [], "notes": []}
    cfg["last_run"] = today
    _write(SETTINGS_FILE, cfg)
    log = run["notes"].append
    loop = asyncio.get_event_loop()

    if cfg["comedy_per_day"] and cfg["channels"]:
        picked = await loop.run_in_executor(None, pick_videos, cfg, cfg["comedy_per_day"], log)
        if not picked:
            log("No new comedy video found on your source channels today.")
        for video, n in picked:
            payload = {**look("comedy"), "url": video["url"], "genre": "comedy", "acknowledged": True,
                       "target_clips": n}
            try:
                job_id = await submit(payload)
                run["jobs"].append({"job_id": job_id, "kind": "comedy", "label": video["title"],
                                    "source": video["url"], "clips": n})
            except Exception as e:  # noqa: BLE001
                log(f"Could not start a job for {video['title'][:60]}: {e}")
    elif cfg["comedy_per_day"]:
        log("Add a source channel to make comedy Shorts.")

    if cfg["cricket_per_day"]:
        ideas = await loop.run_in_executor(None, pick_ideas, cfg, cfg["cricket_per_day"], log)
        for idea in ideas:
            payload = {**look("cricket"), "genre": "cricket", "cricket_mode": idea["kind"],
                       "cricket_match": idea["text"], "acknowledged": True}
            payload.pop("output_format", None)
            try:
                job_id = await submit(payload)
                used_moments.record_topic(idea["text"], job_id)
                run["jobs"].append({"job_id": job_id, "kind": "cricket", "label": idea["text"],
                                    "source": None, "clips": 1})
            except Exception as e:  # noqa: BLE001
                log(f"Could not start the cricket Short '{idea['text'][:60]}': {e}")

    cfg = settings()
    cfg["runs"] = ([run] + cfg.get("runs", []))[:30]
    _write(SETTINGS_FILE, cfg)
    return run


def due(cfg, now=None):
    now = now or datetime.now()
    return (cfg["enabled"] and cfg.get("last_run") != now.strftime("%Y-%m-%d")
            and now.strftime("%H:%M") >= cfg["run_at"])


def upload_finished(job_clips, log=print):
    """With auto_upload on: put every finished, not yet uploaded Short of
    recent runs into the next free posting time. ``job_clips(job_id)`` gives
    (status, [clip dicts]) for a job."""
    import youtube_account
    cfg = settings()
    if not cfg["auto_upload"] or not youtube_account.status()["connected"]:
        return 0
    done = {(u.get("job_id"), u.get("clip_index")) for u in youtube_account.uploads()}
    count = 0
    for run in cfg.get("runs", [])[:3]:
        for job in run["jobs"]:
            state, clips = job_clips(job["job_id"])
            if state != "completed":
                continue
            for clip in clips:
                if (job["job_id"], clip["index"]) in done:
                    continue
                slot = youtube_account.next_slots(cfg["post_times"], 1)[0]
                row = youtube_account.upload(
                    clip["path"], clip["title"], clip["description"], clip["tags"], job["kind"],
                    publish_at=slot, ai_made=clip.get("ai_made", False),
                    meta={"job_id": job["job_id"], "clip_index": clip["index"], "auto": True})
                log(f"Autopilot upload {row['status']}: {row['title'][:60]}")
                count += 1
    return count


async def loop_forever(submit, job_clips, is_active=lambda: True):
    while True:
        await asyncio.sleep(TICK_SECONDS)
        if not is_active():
            continue
        try:
            if due(settings()):
                print("🤖 Autopilot: making today's Shorts.")
                await run_now(submit)
            await asyncio.get_event_loop().run_in_executor(None, upload_finished, job_clips)
        except Exception as e:  # noqa: BLE001 — the loop must survive a bad day
            print(f"⚠️ Autopilot error: {type(e).__name__}: {e}")
