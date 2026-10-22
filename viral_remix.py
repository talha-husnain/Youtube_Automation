"""Ride what already works (owner, 22-oct-2026: "get the video, get the transcript, and based on
it we generate our own videos").

A viral video in our niche is STUDIED, never copied. Its captions go to one call that describes
its angle, hook pattern and beats in English, in its own words; the writer of our script never
sees the source's sentences. The topic then goes through our own grounded research like any
other idea, so every fact and word of our video is ours and the study only steers the angle and
the structure. ``guard`` still refuses a script that shares 8 words in a row with the source
(trend_explainer.copied_runs). Copying a script's wording is copying protected expression, and
YouTube's inauthentic-content rule (YPP, July 2025) demonetises re-uploaded and templated work.

Studies are stored by topic (state/remix/index.json), so a generator finds its study through the
idea text it already gets: no new job field. Kinds: cricket, controversy, history.
"""
import json
import os
import re
import time
from typing import List

from pydantic import BaseModel

import short_kit as kit

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(ROOT, "state", "remix")
KINDS = ("cricket", "controversy", "history")
MIN_VIEWS = int(os.environ.get("REMIX_MIN_VIEWS") or 20_000)   # auto picks only real hits
PER_DAY = int(os.environ.get("REMIX_PER_DAY") or 1)              # per channel, on top of the planner
KEEP_DAYS = 60

URL_RE = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})")

WHAT = {
    "cricket": ("a cricket facts YouTube Shorts channel for Pakistani and Indian fans (records, player stats, rules, "
                "match results, player-vs-player comparisons)"),
    "controversy": ("a YouTube Shorts channel that explains controversies about famous people fairly, with sources, "
                    "for Pakistani and Indian viewers"),
    "history": ("a long-video YouTube channel of Urdu documentaries and explainers (history, and trending stories "
                "explained) for Pakistani and Indian viewers"),
}
TOPIC_RULE = {
    "cricket": ('topic: our own video\'s topic in English, the way our planner writes it: a topic ("Babar Azam ODI '
                'records", "LBW rule explained"), a match ("India vs Pakistan, Asia Cup 2025 final") or two players '
                '("Babar Azam vs Virat Kohli"). kind: "topic", "match" or "versus".'),
    "controversy": 'topic: "<person>: <the controversy>" in English, as our planner writes it. kind: "topic".',
    "history": 'topic: our own documentary\'s topic in English, specific ("How the Mughal Empire lost Delhi"). kind: "topic".',
}


def _rules(kind):
    try:
        if kind == "controversy":
            import controversy_shorts
            return controversy_shorts.RULES
        if kind == "history":
            import history_videos
            return history_videos.RULES
    except Exception:  # noqa: BLE001
        pass
    return "anything hateful, sexual or about minors"


class Blueprint(BaseModel):
    fits: bool
    reason: str
    topic: str
    kind: str
    angle: str
    hook_pattern: str
    beats: List[str]
    devices: List[str]
    why: str


STUDY_PROMPT = """This YouTube video got {views:,} views: "{title}" by {channel} ({seconds} s).
Its captions are below. We run {what}. Study it for a writer who will make an ORIGINAL video for us.
Write in English, in your own words, and quote nothing from it.

Return:
- fits: true only if a video on this subject suits our channel and does not need {rules}.
  reason: why not, or "".
- {topic_rule}
- angle: the specific angle or question that made it work (one sentence).
- hook_pattern: HOW its first 3 seconds grab (the device, e.g. "opens on a shocking number and withholds who
  did it"), never its words.
- beats: 3 to 7 short descriptions of its structure in order ("stakes", "first surprise", "context",
  "twist", "payoff", "comment bait"), each with its function, not its content.
- devices: 2 to 5 retention devices it uses (open loop, countdown, re-hook, contrast, on-screen number).
- why: one sentence on why people watched and shared it.

CAPTIONS:
{text}"""


def video_id(text):
    m = URL_RE.search(text or "")
    return m.group(1) if m else None


def _norm(topic):
    return re.sub(r"[^a-z0-9]+", " ", (topic or "").lower()).strip()


def _index_path():
    return os.path.join(STATE_DIR, "index.json")


def _read():
    try:
        with open(_index_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write(data):
    os.makedirs(STATE_DIR, exist_ok=True)
    cutoff = time.time() - KEEP_DAYS * 86400
    data = {k: v for k, v in data.items() if v.get("at", 0) >= cutoff}
    tmp = _index_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _index_path())


def studied_ids():
    data = _read()
    return {v.get("id") for k, v in data.items() if not k.startswith("_")} | set(data.get("_seen", {}).get("ids", []))


def recent_channels(days=7):
    cutoff = time.time() - days * 86400
    return {v.get("channel") for k, v in _read().items() if not k.startswith("_") and v.get("at", 0) >= cutoff}


def study(client, url_or_id, kind, log=print, fetch=None, skip_channels=()):
    """The stored record {"id", "title", "views", "topic", "kind", "blueprint"...} or raises
    ValueError with a reason the owner can read. ``skip_channels``: creators studied this week
    (one rival leaned on again and again makes a channel look templated)."""
    import youtube_captions
    if kind not in KINDS:
        raise ValueError("This channel cannot make videos from another video.")
    vid = video_id(url_or_id) or (url_or_id if re.fullmatch(r"[A-Za-z0-9_-]{11}", url_or_id or "") else None)
    if not vid:
        raise ValueError("That is not a YouTube video link.")
    info = {}
    tr = (fetch or youtube_captions.fetch)(f"https://www.youtube.com/watch?v={vid}", max_seconds=1800,
                                           info_out=info)
    text = ((tr or {}).get("text") or "").strip()
    if len(text.split()) < 25:
        _mark_seen(vid)
        raise ValueError("That video has no captions to study (YouTube gives none for it).")
    if info.get("channel") and info["channel"] in set(skip_channels):
        _mark_seen(vid)
        raise ValueError(f"{info['channel']} was already studied this week.")
    bp = kit.ask_json(client, Blueprint, STUDY_PROMPT.format(
        views=int(info.get("views") or 0), title=info.get("title") or "?", channel=info.get("channel") or "?",
        seconds=int(info.get("seconds") or 0), what=WHAT[kind], rules=_rules(kind), topic_rule=TOPIC_RULE[kind],
        text=text[:20000]), model=_writer())
    if not bp.fits or len(bp.topic.strip()) < 5:
        _mark_seen(vid)
        raise ValueError(f"Not a fit for this channel: {bp.reason or 'off topic'}.")
    topic = re.sub(r"\s+", " ", bp.topic).strip()[:140]
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(os.path.join(STATE_DIR, f"{vid}.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    rec = {"id": vid, "title": info.get("title") or "", "views": int(info.get("views") or 0),
           "channel": info.get("channel") or "", "topic": topic,
           "kind": bp.kind if bp.kind in ("topic", "match", "versus") else "topic",
           "blueprint": bp.model_dump(), "at": int(time.time())}
    data = _read()
    data[_norm(topic)] = rec
    _write(data)
    log(f"   🧪 Studied \"{rec['title'][:70]}\" ({rec['views']:,} views) -> {topic}")
    return rec


def _writer():
    import script_craft
    return script_craft.writer_model()


def _mark_seen(vid):
    data = _read()
    seen = data.get("_seen") or {"ids": [], "at": int(time.time())}
    seen["ids"] = (seen.get("ids") or [])[-300:] + [vid]
    seen["at"] = int(time.time())
    data["_seen"] = seen
    _write(data)


def record_for(topic):
    rec = _read().get(_norm(topic))
    return rec if rec and rec.get("blueprint") else None


def note_for(topic):
    """The study as a block for a script prompt, or ""."""
    rec = record_for(topic)
    if not rec:
        return ""
    bp = rec["blueprint"]
    return ("\n\nINSPIRATION (a study of a video on this subject that got "
            f"{rec['views']:,} views; study only, its words are not given and must not be guessed):\n"
            f"- angle that worked: {bp['angle']}\n- how its hook grabbed: {bp['hook_pattern']}\n"
            f"- its structure: {'; '.join(bp['beats'])}\n- what kept people watching: {'; '.join(bp['devices'])}\n"
            f"- why people watched: {bp['why']}\n"
            "Use the angle, the hook pattern and the structure where OUR facts support them. Every fact comes from "
            "the facts given above and every sentence is our own; if our facts tell a different story, follow our "
            "facts. Put the facts in your own order and include at least one that video does not have: the same "
            "facts in the same order reads as a copy.")


def source_text(topic):
    rec = record_for(topic)
    if not rec:
        return ""
    try:
        with open(os.path.join(STATE_DIR, f"{rec['id']}.txt"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def guard(topic, script_text):
    """Raise when our script repeats 8 words in a row of the studied video."""
    src = source_text(topic)
    if not src:
        return
    import trend_explainer
    runs = trend_explainer.copied_runs(script_text, [src])
    if runs:
        raise RuntimeError(f"The script repeats the studied video's words ({' '.join(runs[0])}); not made.")


def as_idea(rec):
    return {"kind": rec["kind"], "text": rec["topic"], "remix": rec["id"], "at": int(time.time())}


def made_today(ch, now=None):
    """How many remix ideas this channel planned today (kept on the card as remix_days)."""
    day = time.strftime("%Y-%m-%d", time.localtime(now or time.time()))
    return int((ch.get("remix_days") or {}).get(day, 0))


QUERIES = {
    "cricket": ["cricket facts shorts", "cricket records hindi urdu shorts"],
    "controversy": ["controversy explained shorts hindi", "cricketer controversy shorts"],
}
# Fan edits and song syncs hold the top of cricket search (22-oct-2026: 4 of the week's top 5 were
# "Virat Kohli x <song>" edits). They have no story to study, so they cost a captions call for nothing.
NOT_A_STORY = re.compile(r"\b(edit|edits|status|song|beat ?sync|lyrics|whatsapp|ft\.?|x)\b", re.I)
CANDIDATES_SECONDS = 24 * 3600


def candidates(kind, search=None, now=None):
    """[{"id", "title", "views"}] of this month's most viewed Shorts for ``kind``. trends.top looks at
    one week and found nothing over 1,600 views on 22-oct-2026; a Short worth studying keeps working
    for weeks. Two searches in a row, never in parallel, cached a day."""
    now = now or time.time()
    data = _read()
    hit = (data.get("_candidates") or {}).get(kind)
    if hit and now - hit.get("at", 0) < CANDIDATES_SECONDS:
        return hit["rows"]
    if search is None:
        import channel_tools

        def search(q):
            return channel_tools.search(q, cc=False, duration="short", date="year", sort="views", limit=10)
    rows, seen = [], set()
    for q in QUERIES.get(kind, []):
        try:
            got = search(q)
        except Exception:  # noqa: BLE001 — a bonus, never needed
            got = []
        for v in got:
            if v.get("id") in seen or NOT_A_STORY.search(v.get("title") or ""):
                continue
            seen.add(v["id"])
            rows.append({"id": v["id"], "title": (v.get("title") or "")[:100], "views": int(v.get("views") or 0)})
    rows.sort(key=lambda v: v["views"], reverse=True)
    data = _read()
    data.setdefault("_candidates", {"at": int(now)})[kind] = {"at": int(now), "rows": rows[:20]}
    data["_candidates"]["at"] = int(now)
    _write(data)
    return rows[:20]


def auto_idea(client, kind, log=print, videos=None, study_fn=None):
    """An idea from this week's most viewed Short in the niche that we have not studied, or None.
    A few yt-dlp calls in a row at most (a burst got this laptop bot-checked on 22-oct-2026)."""
    if kind not in ("cricket", "controversy") or os.environ.get("VIRAL_REMIX", "1") == "0":
        return None
    rows = videos if videos is not None else candidates(kind)
    seen = studied_ids()
    for v in rows[:3]:
        if v["id"] in seen or (v.get("views") or 0) < MIN_VIEWS:
            continue
        try:
            rec = (study_fn or study)(client, v["id"], kind, log=log, skip_channels=recent_channels())
        except ValueError as e:
            log(f"   ℹ️ Skipped a viral video to study: {e}")
            continue
        except Exception as e:  # noqa: BLE001 — a bonus idea, never needed
            log(f"   ℹ️ Could not study a viral video ({type(e).__name__}).")
            return None
        return as_idea(rec)
    return None
