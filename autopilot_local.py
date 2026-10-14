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

With ``research`` on (default) it also finds the videos by itself: every
``research_queries`` search runs with YouTube's Creative Commons filter, and
the most-viewed long videos nobody clipped yet (``min_views`` and up, at most
``RESEARCH_PER_CHANNEL`` a day from one channel) join the source channels'
newest uploads. So an empty channel list still gives a full day of Shorts.
"""
import asyncio
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(ROOT, "output", ".autopilot.json")
LAST_SETTINGS_FILE = os.path.join(ROOT, "output", ".last_settings.json")
CLIPS_PER_VIDEO = 3
MAX_CHANNELS = 10
# Auto upload walks Ready to post this often; after the channel's daily
# upload limit it waits UPLOAD_PAUSE_SECONDS (one refused call per tick
# would be 1,440 a day).
AUTO_POST_EVERY = 600
UPLOAD_PAUSE_SECONDS = 3 * 3600
CLAIM_CHECK_EVERY = 1800
# Series and shows by title: "PATI PATNI AUR PADOSAN - Episode 14", marked
# Creative Commons, got two Shorts blocked worldwide by a Content ID claim
# (14-oct-2026). A podcast's "EP 29" is the creator's own and stays.
SERIES_TITLE = re.compile(r"\b(drama|serial|natak|film|movie|trailer|web ?series|season \d+)\b", re.I)
EPISODE_TITLE = re.compile(r"\b(episode|epi|ep\.? ?\d+)\b", re.I)
MAX_QUERIES = 8
RESEARCH_PER_CHANNEL = 2
RESEARCH_QUERIES = ["pakistani stand up comedy", "urdu stand up comedy", "pakistani comedy show",
                    "urdu funny poetry mushaira", "pakistani comedy podcast"]
TICK_SECONDS = 60
# Fields of a hand-made job that describe its look, kept for Autopilot.
LOOK_FIELDS = ("output_format", "target_clips", "clip_min_seconds", "clip_max_seconds", "auto_hook",
               "auto_hook_style", "layouts", "frame_bg_color", "frame_crop", "frame_zoom", "frame_title",
               "frame_outro", "frame_outro_seconds", "frame_handle", "caption_script", "ai_take", "bg_music",
               "take_voice")
BRAND = {"output_format": "framed", "frame_handle": "@PunchlineBazaar", "frame_bg_color": "#2B0F3D"}
DEFAULTS = {
    "enabled": False, "run_at": "03:00", "comedy_per_day": 3, "cricket_per_day": 1,
    "channels": [], "cc_only": True, "min_minutes": 5, "max_minutes": 120,
    "cricket_kinds": "both", "auto_upload": False, "post_times": ["13:00", "19:00"],
    # Weekly long video (long_video.py) on this weekday, 0 = Monday ... 6 = Sunday.
    "weekly_long": False, "weekly_day": 6, "last_weekly": None,
    # Send each finished Autopilot Short to the owner's Telegram (telegram_notify.py).
    "auto_phone": False,
    # Match watch: a result Short within hours of a followed team's match.
    "match_watch": False, "match_team": "Pakistan", "last_match_check": 0,
    # Research: find viral reuse-allowed videos by search, not only the channels.
    "research": True, "research_queries": RESEARCH_QUERIES, "min_views": 20000,
    "last_auto_post": 0, "upload_paused_until": 0,
    # Sources a Content ID claim blocked: research and channels never use them again.
    "blocked_sources": [], "last_claim_check": 0,
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
    for key in ("enabled", "cc_only", "auto_upload", "weekly_long", "auto_phone", "match_watch", "research"):
        if key in patch:
            cfg[key] = bool(patch[key])
    for key, hi in (("comedy_per_day", 10), ("cricket_per_day", 5), ("min_minutes", 600), ("max_minutes", 600),
                    ("min_views", 100_000_000)):
        if key in patch:
            try:
                cfg[key] = max(0, min(hi, int(patch[key])))
            except (TypeError, ValueError):
                pass
    if "research_queries" in patch and isinstance(patch["research_queries"], list):
        qs = [" ".join(str(q or "").split())[:80] for q in patch["research_queries"]]
        cfg["research_queries"] = list(dict.fromkeys(q for q in qs if q))[:MAX_QUERIES]
    if "match_team" in patch:
        team = " ".join(str(patch["match_team"] or "").split())[:40]
        cfg["match_team"] = team or cfg["match_team"]
    if "weekly_day" in patch:
        try:
            cfg["weekly_day"] = max(0, min(6, int(patch["weekly_day"])))
        except (TypeError, ValueError):
            pass
    if "run_at" in patch:
        cfg["run_at"] = _clock(patch["run_at"], cfg["run_at"])
    if "post_times" in patch and isinstance(patch["post_times"], list):
        times = sorted({_clock(t, "") for t in patch["post_times"]} - {""})
        # Up to 10 a day: 7 research Shorts + cricket need more than the old 6.
        cfg["post_times"] = times[:10] or cfg["post_times"]
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

def looks_like_a_series(title):
    t = title or ""
    return bool(SERIES_TITLE.search(t) or (EPISODE_TITLE.search(t) and "podcast" not in t.lower()))


def is_blocked(cfg, v):
    """A video or channel a claim already blocked a Short of."""
    import used_moments
    vid = used_moments.video_id(v.get("url") or "") or v.get("id")
    for b in cfg.get("blocked_sources") or []:
        if (vid and vid == b.get("video")) or (b.get("channel_url") and b.get("channel_url") == v.get("channel_url")):
            return True
    return False


def block_source(url, reason, log=print):
    """Never use this video's channel again (a claim blocked a Short of it)."""
    import channel_tools
    import used_moments
    vid = used_moments.video_id(url or "")
    cfg = settings()
    if not vid or any(b.get("video") == vid for b in cfg["blocked_sources"]):
        return False
    try:
        info = channel_tools.licence(url)
    except Exception:  # noqa: BLE001 — the video id alone still blocks it
        info = {}
    cfg["blocked_sources"] = (cfg["blocked_sources"] + [{
        "video": vid, "title": (info.get("title") or "")[:120], "channel": info.get("channel") or "",
        "channel_url": info.get("channel_url") or "", "reason": reason, "at": int(time.time())}])[-200:]
    # Its channel may also be a source channel: take it out.
    cfg["channels"] = [c for c in cfg["channels"] if not info.get("channel_url") or c.get("url") != info["channel_url"]]
    _write(SETTINGS_FILE, cfg)
    log(f"Blocked source: {info.get('channel') or vid} ({reason}). It is never used again.")
    return True


def claims_due(cfg, now=None):
    return (now or time.time()) - cfg.get("last_claim_check", 0) >= CLAIM_CHECK_EVERY


def run_claim_check(check_claims, log=print):
    cfg = settings()
    cfg["last_claim_check"] = int(time.time())
    _write(SETTINGS_FILE, cfg)
    return check_claims(log)


def research_videos(cfg, log):
    """Most-viewed Creative Commons videos for the research searches, unused
    first, at most RESEARCH_PER_CHANNEL per channel. Search results carry
    the CC filter; pick_videos still checks each licence before a job."""
    import channel_tools
    import used_moments
    lo, hi = cfg["min_minutes"] * 60, cfg["max_minutes"] * 60
    queries = cfg.get("research_queries") or RESEARCH_QUERIES

    def _one(q):
        try:
            # "medium" is 4-20 min and "long" over 20: both, never <4 min clips.
            return channel_tools.search(q, cc=True, duration="medium", sort="views", limit=20) + \
                channel_tools.search(q, cc=True, duration="long", sort="views", limit=20)
        except Exception as e:  # noqa: BLE001 — one failed search must not stop the day
            log(f"Search failed for '{q}': {type(e).__name__}")
            return []

    with ThreadPoolExecutor(max_workers=4) as pool:
        found = [v for vs in pool.map(_one, queries) for v in vs]
    import learning
    learned = learning.load()

    def weight(v):
        # A source whose Shorts did well for this channel ranks up, a poor one
        # down, a resting one (factor 0) is left out (learning.py).
        return (v.get("views") or 0) * learning.source_factor(v.get("channel_url"), learned)
    seen, cands = set(), []
    for v in sorted(found, key=weight, reverse=True):
        if weight(v) <= 0:
            continue
        if v["id"] in seen or not v.get("seconds") or not lo <= v["seconds"] <= hi:
            continue
        seen.add(v["id"])
        if (v.get("views") or 0) < cfg.get("min_views", 0):
            continue
        if is_blocked(cfg, v) or looks_like_a_series(v.get("title")):
            continue
        used = used_moments.summary(v["url"])
        if used["count"] and used["seconds"] >= 0.4 * v["seconds"]:
            continue
        v["_partly"] = bool(used["count"])
        cands.append(v)
    cands = vet(cands[:VET_MAX], log)
    per_channel, fresh, partly = {}, [], []
    for v in cands:
        key = v.get("channel_url") or v.get("channel")
        if per_channel.get(key, 0) >= RESEARCH_PER_CHANNEL:
            continue
        per_channel[key] = per_channel.get(key, 0) + 1
        (partly if v.pop("_partly") else fresh).append(v)
    log(f"Research: {len(fresh)} new and {len(partly)} partly used videos from {len(queries)} searches.")
    return fresh, partly


VET_MAX = 40
VET_PROMPT = """You choose source videos for "Punchline Bazaar", a Pakistani comedy Shorts
channel: short funny clips with Roman Urdu titles for a Pakistani audience.

Every candidate below is marked Creative Commons on YouTube, but many of those
are re-uploads by channels that do not own them, and a re-upload gets the
channel copyright claims. Keep a video only when ALL of these are true:
- it is talking comedy: stand-up, a comedy or talk show, funny mushaira or
  poetry, a comedy podcast or interview with a comedian;
- it is in Urdu, Hindi or Punjabi;
- the channel looks like the original creator or the show's own channel (the
  comedian's or the show's own name), not a channel re-uploading a TV
  channel's programme, a film, a web series or another creator's video;
- it is not a reaction video, a drama serial or episode, a film or web series,
  a news clip, a song, or a compilation of other people's clips;
- it is not footage of a TV broadcast (award show, morning show, a TV
  channel's comedy programme): broadcasters claim their footage, and a
  claimed source got two Shorts blocked worldwide.
When unsure, do not keep it. Answer for every candidate: its id, keep, and a
reason of a few words."""


def vet(cands, log):
    """Keep the research finds that look like the creator's own talking comedy
    (one Gemini call for the day). A failed check keeps none: unattended, a
    day without research Shorts beats a day of re-uploads."""
    if not cands:
        return cands
    from pydantic import BaseModel
    import short_kit

    class Verdict(BaseModel):
        id: str
        keep: bool
        reason: str

    class Verdicts(BaseModel):
        videos: list[Verdict]

    lines = "\n".join(json.dumps({"id": v["id"], "title": v["title"][:150], "channel": v.get("channel", "")[:80],
                                   "minutes": round((v.get("seconds") or 0) / 60), "views": v.get("views")},
                                  ensure_ascii=False) for v in cands)
    try:
        got = short_kit.ask_json(short_kit.gemini(), Verdicts, f"{VET_PROMPT}\n\nCandidates:\n{lines}")
    except Exception as e:  # noqa: BLE001
        log(f"Could not check the research finds ({type(e).__name__}), so none were used today.")
        return []
    keep = {x.id for x in got.videos if x.keep}
    why = {x.id: x.reason for x in got.videos}
    dropped = [v for v in cands if v["id"] not in keep]
    log(f"Research check kept {len(cands) - len(dropped)} of {len(cands)} videos"
        + (f" (dropped e.g. {dropped[0]['title'][:40]!r}: {why.get(dropped[0]['id'], 'not kept')[:60]})" if dropped else "") + ".")
    return [v for v in cands if v["id"] in keep]


def pick_videos(cfg, clips_needed, log):
    """[(video, clips)] for today: newest unused videos first, round robin over
    the channels, then the research finds; licence checked when ``cc_only``."""
    import channel_tools
    import used_moments
    lo, hi = cfg["min_minutes"] * 60, cfg["max_minutes"] * 60

    def _list(ch):
        try:
            return channel_tools.channel_videos(ch["url"], 15)
        except Exception as e:  # noqa: BLE001 — one dead channel must not stop the day
            log(f"Could not read {ch.get('name') or ch['url']}: {channel_tools.why_not(e)}")
            return []

    with ThreadPoolExecutor(max_workers=4) as pool:
        lists = list(pool.map(_list, cfg["channels"]))
    fresh, partly = [], []
    for depth in range(15):                  # round robin: every channel's newest first
        for videos in lists:
            if depth >= len(videos):
                continue
            v = videos[depth]
            if not v.get("seconds") or not lo <= v["seconds"] <= hi or is_blocked(cfg, v):
                continue
            used = used_moments.summary(v["url"])
            if used["count"] == 0:
                fresh.append(v)
            elif used["seconds"] < 0.4 * v["seconds"]:
                partly.append(v)
    if cfg.get("research"):
        r_fresh, r_partly = research_videos(cfg, log)
        known = {v["url"] for v in fresh + partly}
        fresh += [v for v in r_fresh if v["url"] not in known]
        partly += [v for v in r_partly if v["url"] not in known]
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

    if cfg["comedy_per_day"] and (cfg["channels"] or cfg.get("research")):
        picked = await loop.run_in_executor(None, pick_videos, cfg, cfg["comedy_per_day"], log)
        if not picked:
            log("No new reuse-allowed comedy video found today.")
        import learning
        for video, n in picked:
            test = learning.next_arm()
            payload = {**look("comedy"), **test["overrides"], "url": video["url"], "genre": "comedy",
                       "acknowledged": True, "target_clips": n}
            try:
                job_id = await submit(payload)
                run["jobs"].append({"job_id": job_id, "kind": "comedy", "label": video["title"],
                                    "source": video["url"], "clips": n, "exp": test["exp"], "arm": test["arm"]})
            except Exception as e:  # noqa: BLE001
                log(f"Could not start a job for {video['title'][:60]}: {e}")
    elif cfg["comedy_per_day"]:
        log("Add a source channel or turn on research to make comedy Shorts.")

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


MATCH_CHECK_SECONDS = 3 * 3600
MATCH_PROMPT = """Today is {today}. Did the {team} men's national cricket team finish an
international match (Test, ODI or T20I) in the last 24 hours? Use Google Search.
If yes, answer one line exactly: MATCH: <team> vs <team>, <series or tournament>, <date>
If not, or if it is still being played, answer exactly: NONE"""


def match_due(cfg, now=None):
    now = now or time.time()
    return bool(cfg.get("match_watch")) and now - float(cfg.get("last_match_check") or 0) >= MATCH_CHECK_SECONDS


def find_finished_match(client, team, today=None):
    """"Pakistan vs Sri Lanka, Asia Cup, 7 Oct 2026" when the team just played, else None."""
    import re
    import cricket_shorts
    text, _sources = cricket_shorts.grounded(client, MATCH_PROMPT.format(
        team=team, today=today or datetime.now().strftime("%d %B %Y")))
    m = re.search(r"MATCH:\s*(.+)", text or "")
    return " ".join(m.group(1).split())[:200] if m else None


async def run_match_watch(submit, client_fn):
    """Every 3 hours: if the followed team just finished a match, make its Short now."""
    import used_moments
    cfg = settings()
    cfg["last_match_check"] = int(time.time())
    _write(SETTINGS_FILE, cfg)
    loop = asyncio.get_event_loop()
    try:
        line = await loop.run_in_executor(None, find_finished_match, client_fn(), cfg["match_team"])
    except Exception as e:  # noqa: BLE001 — try again at the next check
        print(f"⚠️ Match watch: {type(e).__name__}: {e}")
        return None
    if not line or used_moments.topic_used(line):
        return None
    run = {"at": int(time.time()), "date": datetime.now().strftime("%Y-%m-%d"), "reason": "match watch",
           "jobs": [], "notes": []}
    payload = {**look("cricket"), "genre": "cricket", "cricket_mode": "match", "cricket_match": line,
               "acknowledged": True}
    payload.pop("output_format", None)
    try:
        job_id = await submit(payload)
        used_moments.record_topic(line, job_id)
        run["jobs"].append({"job_id": job_id, "kind": "cricket", "label": line, "source": None, "clips": 1})
    except Exception as e:  # noqa: BLE001
        run["notes"].append(f"Could not start the match Short '{line[:60]}': {e}")
    cfg = settings()
    cfg["runs"] = ([run] + cfg.get("runs", []))[:30]
    _write(SETTINGS_FILE, cfg)
    return run


def weekly_due(cfg, now=None):
    now = now or datetime.now()
    return (cfg.get("weekly_long") and now.weekday() == cfg.get("weekly_day", 6)
            and cfg.get("last_weekly") != now.strftime("%Y-%m-%d") and now.strftime("%H:%M") >= cfg["run_at"])


def run_weekly(build_weekly):
    """Start this week's long video; the note lands in the runs list."""
    cfg = settings()
    cfg["last_weekly"] = datetime.now().strftime("%Y-%m-%d")
    _write(SETTINGS_FILE, cfg)
    run = {"at": int(time.time()), "date": cfg["last_weekly"], "reason": "weekly", "jobs": [], "notes": []}
    try:
        job_id = build_weekly()
        if job_id:
            run["jobs"].append({"job_id": job_id, "kind": "long video", "label": "Weekly top Shorts", "source": None,
                                "clips": 1})
        else:
            run["notes"].append("Weekly long video skipped: fewer than 3 Shorts this week.")
    except Exception as e:  # noqa: BLE001
        run["notes"].append(f"Weekly long video failed to start: {e}")
    cfg = settings()
    cfg["runs"] = ([run] + cfg.get("runs", []))[:30]
    _write(SETTINGS_FILE, cfg)
    return run


def upload_finished(job_clips, log=print):
    """With auto_upload on: put every finished, not yet uploaded Short of
    recent runs into the next free posting time. ``job_clips(job_id)`` gives
    (status, [clip dicts]) for a job."""
    import youtube_account
    cfg = settings()
    if not cfg["auto_upload"] or not youtube_account.status()["connected"]:
        return 0
    # A refused upload (daily limit, network) is tried again on a later tick.
    done = {(u.get("job_id"), u.get("clip_index")) for u in youtube_account.uploads() if u.get("status") != "failed"}
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
                row = youtube_account.upload_and_mark(
                    clip["path"], clip["title"], clip["description"], clip["tags"], job["kind"],
                    publish_at=slot, ai_made=clip.get("ai_made", False),
                    meta={"job_id": job["job_id"], "clip_index": clip["index"], "auto": True,
                          "source": job.get("source")})
                log(f"Autopilot upload {row['status']}: {row['title'][:60]}")
                count += 1
                if row.get("status") != "done" and youtube_account.upload_limit_hit(row.get("error")):
                    log("YouTube's daily upload limit is reached; the rest go up on a later tick.")
                    return count
    return count


def auto_post_due(cfg, now=None):
    now = now or time.time()
    return (cfg["auto_upload"] and now >= cfg.get("upload_paused_until", 0)
            and now - cfg.get("last_auto_post", 0) >= AUTO_POST_EVERY)


def run_auto_post(post_ready, log=print):
    """Upload every Short waiting in Ready to post (``post_ready()`` -> {done,
    limit} or None when nothing waits); pause after the daily limit."""
    import youtube_account
    cfg = settings()
    cfg["last_auto_post"] = int(time.time())
    _write(SETTINGS_FILE, cfg)
    if not youtube_account.status()["connected"]:
        return None
    got = post_ready()
    if got and got.get("limit"):
        cfg = settings()
        cfg["upload_paused_until"] = int(time.time()) + UPLOAD_PAUSE_SECONDS
        _write(SETTINGS_FILE, cfg)
        log(f"Auto upload: {got.get('done', 0)} up, then YouTube's daily limit. Trying again in 3 hours.")
    elif got and got.get("done"):
        log(f"Auto upload: {got['done']} Short(s) uploaded and scheduled.")
    return got


def phone_finished(plan_items, send, log=print):
    """With auto_phone on: every finished Short of recent Autopilot runs that
    has not gone to Telegram yet goes now, in posting order."""
    import post_queue
    import telegram_notify
    cfg = settings()
    if not cfg.get("auto_phone") or not telegram_notify.status()["connected"]:
        return 0
    jobs = {j["job_id"] for run in cfg.get("runs", [])[:3] for j in run["jobs"]}
    state = post_queue._load()
    todo = [x for x in plan_items() if x["status"] == "ready" and x["job_id"] in jobs
            and not (state.get(x["id"]) or {}).get("telegram_sent")]
    sent = 0
    for x in sorted(todo, key=lambda i: i.get("slot") or ""):
        try:
            send(x)
            sent += 1
        except Exception as e:  # noqa: BLE001 — one failed send must not stop the rest
            log(f"Telegram send failed: {e}")
    return sent


async def loop_forever(submit, job_clips, is_active=lambda: True, build_weekly=None, to_phone=None,
                       post_ready=None, check_claims=None):
    while True:
        await asyncio.sleep(TICK_SECONDS)
        if not is_active():
            continue
        try:
            if due(settings()):
                print("🤖 Autopilot: making today's Shorts.")
                await run_now(submit)
            if match_due(settings()):
                import short_kit
                await run_match_watch(submit, short_kit.gemini)
            if build_weekly and weekly_due(settings()):
                print("🤖 Autopilot: building this week's long video.")
                await asyncio.get_event_loop().run_in_executor(None, run_weekly, build_weekly)
            if check_claims and claims_due(settings()):
                await asyncio.get_event_loop().run_in_executor(None, run_claim_check, check_claims)
            import learning
            if learning.due():
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: learning.run(print, look("comedy").get("frame_handle") or ""))
            if post_ready:
                # Everything in Ready to post, hand-made Shorts too.
                if auto_post_due(settings()):
                    await asyncio.get_event_loop().run_in_executor(None, run_auto_post, post_ready)
            else:
                await asyncio.get_event_loop().run_in_executor(None, upload_finished, job_clips)
            if to_phone:
                await asyncio.get_event_loop().run_in_executor(None, phone_finished, *to_phone)
        except Exception as e:  # noqa: BLE001 — the loop must survive a bad day
            print(f"⚠️ Autopilot error: {type(e).__name__}: {e}")
