"""A research agent per channel niche (owner, 28-oct-2026: "find the most viral content created in that
niche, see their videos, get ideas from it and recreate the videos ourselves").

Once a day per niche (my_channels runs one niche per loop tick, ~30-60 s each):

1. find: the most viewed videos of the niche's recent searches (2 of its queries a day, in turn) through
   the Data API (yt_api: a real view-count sort and no bot check), plus the breakout videos of the
   creators behind them (>= OUTLIER_X their own median: views / channel median is the fair bar, research
   22-oct-2026). Creators are remembered, so the watchlist grows day by day.
2. study: Gemini watches the best ones we have not studied (viral_remix.study): angle, hook, first
   frame, beats, visuals, on-screen text, sound, ending. Studied, never copied: the writer never sees
   the source's words and viral_remix.guard refuses a script that shares 8 words in a row with it.
3. playbook: after a few new studies one call turns the niche's last studies into rules (winning
   topics, hooks, shape, length, on-screen and sound, endings, titles, what to avoid). It reaches every
   script prompt of the niche (NICHE_PLAYBOOK -> script_craft.playbook()) and the SEO writer.
4. ideas: each fitting study is an idea the channel makes (my_channels takes REMIX_PER_DAY a day).

State: state/research/<niche>.json. RESEARCH=0 turns the agent off (tests).
"""
import json
import os
import re
import time
from typing import List

from pydantic import BaseModel

import short_kit as kit
import viral_remix

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(ROOT, "state", "research")
RUN_EVERY = 20 * 3600          # a niche's pass, about once a day
QUERIES_PER_RUN = 2
CREATORS_PER_RUN = 2           # creators' upload lists read per pass (2 units each)
CREATOR_REST = 7 * 86400       # a creator's list is read again after a week
STUDIES_PER_RUN = int(os.environ.get("RESEARCH_STUDIES") or 2)
TRIES_PER_RUN = 4              # watch calls a pass may spend, unfit videos included
PLAYBOOK_AFTER = 3             # new studies before the playbook is rebuilt
PLAYBOOK_MAX_AGE = 7 * 86400
PLAYBOOK_STUDIES = 15
IDEA_DAYS = 21                 # a study older than this is no longer a fresh idea
OUTLIER_X = 3.0
# Fan edits, song syncs and status clips hold the top of cricket search: no story to study.
NOT_A_STORY = re.compile(r"\b(edit|edits|status|beat ?sync|whatsapp|ft\.?|x)\b", re.I)

NICHES = {
    "cricket": {"queries": ["cricket facts shorts", "cricket records shorts", "pakistan cricket shorts",
                            "cricket unknown facts hindi", "cricket rules explained shorts",
                            "cricket player comparison shorts", "babar azam shorts", "virat kohli records shorts"],
                "days": 30, "durations": ["short"], "max_seconds": 180, "floor": 100_000, "story": True},
    # The motion-graphics money channel (money_shorts.py): searches from the research of 29-oct-2026.
    "money": {"queries": ["salary comparison shorts", "price then and now shorts", "business mistake shorts hindi",
                          "pakistan economy shorts", "company biggest mistake shorts", "money facts shorts hindi",
                          "how much does it cost shorts", "gold price history shorts"],
              "days": 30, "durations": ["short"], "max_seconds": 180, "floor": 100_000, "story": True},
    # The cartoon series (toon_shorts.py): talking animal and talking baby comedy (research of 5-nov-2026).
    "toons": {"queries": ["talking cat cartoon shorts hindi", "billi ki kahani shorts", "funny cartoon shorts urdu",
                          "talking baby funny shorts hindi", "ai cat story shorts", "talking animals comedy shorts",
                          "desi family cartoon comedy shorts", "cat drama shorts"],
              "days": 30, "durations": ["short"], "max_seconds": 180, "floor": 100_000, "story": True},
    "controversy": {"queries": ["controversy explained shorts", "pakistani celebrity controversy",
                                "bollywood controversy explained shorts", "cricketer controversy shorts",
                                "pakistani actress controversy shorts", "celebrity scandal explained hindi"],
                    "days": 30, "durations": ["short"], "max_seconds": 180, "floor": 50_000, "story": True},
    # "gk quiz shorts" with Hindi relevance found health clickbait and "ai song shorts" nursery rhymes
    # (first pass, 28-oct-2026): the searches say what the video IS, and screen() drops the rest.
    "quiz": {"queries": ["gk quiz questions and answers", "quiz challenge can you answer", "guess the flag quiz",
                         "islamic quiz questions urdu", "general knowledge quiz hindi", "true or false quiz challenge",
                         "riddles with answers hindi", "guess the actress quiz"],
             "days": 60, "durations": ["short"], "max_seconds": 180, "floor": 50_000},
    "music": {"queries": ["sad song lyrics", "love song lyrics english", "ai generated song", "heartbreak song lyrics",
                          "suno ai song", "aesthetic lyrics video song"],
              "days": 30, "durations": ["short"], "max_seconds": 180, "floor": 100_000,
              "region": "US", "language": "en",
              # The first screen kept 0 of 31: it read real artists' lyric Shorts as "not our kind".
              "screen": ("Any song Short with lyrics or aesthetic visuals over a song counts, whoever sings it: "
                         "we take its theme, hook and look, never the song. Drop kids' songs, film clips, dance "
                         "challenges and covers of a person singing on camera.")},
    "quran": {"queries": ["quran recitation shorts", "quran urdu translation shorts", "beautiful tilawat shorts",
                          "surah rahman shorts", "quran recitation with translation"],
              "days": 60, "durations": ["short"], "max_seconds": 180, "floor": 100_000, "language": "ur",
              "ideas": False,
              "screen": ("Only recitation of the Quran with its text or translation on screen. Political or news "
                         "clips that put surah names in their titles for search are not.")},
    "history": {"queries": ["history documentary urdu", "islamic history urdu documentary",
                            "mughal history documentary hindi", "history of pakistan documentary",
                            "ancient history documentary hindi", "world war history hindi"],
                "days": 120, "durations": ["medium", "long"], "min_seconds": 240, "floor": 100_000},
    "explainer": {"queries": ["explained in hindi", "explained in urdu", "pakistan economy explained",
                              "world news explained hindi", "geopolitics explained hindi",
                              "why is it happening explained hindi"],
                  "days": 14, "durations": ["medium", "long"], "min_seconds": 240, "floor": 100_000},
    # The long channel in horror mode (horror_stories.py): what the top Urdu/Hindi horror stories do.
    "horror": {"queries": ["horror story urdu", "horror story hindi", "bhoot ki kahani", "darawni kahani",
                           "jinn ki kahani urdu", "haunted haveli story hindi"],
               "days": 60, "durations": ["medium", "long"], "min_seconds": 240, "floor": 100_000,
               "screen": ("Only narrated horror stories (fiction told by a narrator over pictures or footage). Drop "
                          "films, film reviews, pranks, 'real ghost caught on camera' clips and exorcism videos.")},
    "comedy": {"queries": ["pakistani comedy shorts", "urdu funny shorts", "stand up comedy hindi shorts",
                           "funny mushaira shorts", "pakistani stand up comedy shorts"],
               "days": 30, "durations": ["short"], "max_seconds": 180, "floor": 200_000, "ideas": False},
}


def enabled():
    return os.environ.get("RESEARCH", "1") != "0"


# ------------------------------------------------------------------ state

def _path(niche):
    return os.path.join(STATE_DIR, f"{niche}.json")


def load(niche):
    try:
        with open(_path(niche), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(niche, data):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = _path(niche) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path(niche))


def due(niche, now=None):
    return niche in NICHES and (now or time.time()) - load(niche).get("last_run", 0) >= RUN_EVERY


# ------------------------------------------------------------------ 1. find

def todays_queries(niche, now=None):
    qs = NICHES[niche]["queries"]
    day = int((time.time() if now is None else now) // 86400)     # now=0 is a real time (day 0), not "unset"
    return [qs[(day * QUERIES_PER_RUN + i) % len(qs)] for i in range(min(QUERIES_PER_RUN, len(qs)))]


def _keep(niche, v):
    cfg = NICHES[niche]
    secs = v.get("seconds") or 0
    if cfg.get("max_seconds") and secs > cfg["max_seconds"]:
        return False
    if cfg.get("min_seconds") and secs < cfg["min_seconds"]:
        return False
    if cfg.get("story") and NOT_A_STORY.search(v.get("title") or ""):
        return False
    return (v.get("views") or 0) >= cfg["floor"]


def find(niche, now=None, api=None, log=print, queries=None):
    """[row] worth studying, most viewed first, and the updated creators watchlist."""
    import yt_api
    api = api or yt_api
    cfg, now = NICHES[niche], now or time.time()
    data = load(niche)
    creators = data.get("creators") or {}
    rows, seen = [], set()
    for n, q in enumerate(queries or todays_queries(niche, now)):
        duration = cfg["durations"][n % len(cfg["durations"])]
        try:
            got = api.search(q, days=cfg["days"], duration=duration, region=cfg.get("region", "PK"),
                             language=cfg.get("language", "hi"))
        except Exception as e:  # noqa: BLE001 — out of quota or YouTube said no: the next search may work
            log(f"   ℹ️ Research search '{q}' failed ({type(e).__name__}: {str(e)[:100]}).")
            continue
        for v in got:
            if v["id"] in seen or not _keep(niche, v):
                continue
            seen.add(v["id"])
            rows.append({**v, "found": q})
            c = creators.setdefault(v["channel_id"], {"name": v["channel"], "read": 0, "hits": 0, "best": 0})
            c["hits"] += 1
            c["best"] = max(c["best"], v["views"])
            c["name"] = v["channel"]
    fresh = sorted((cid for cid in creators if now - creators[cid].get("read", 0) >= CREATOR_REST),
                   key=lambda cid: creators[cid]["best"], reverse=True)
    for cid in fresh[:CREATORS_PER_RUN]:
        creators[cid]["read"] = int(now)
        try:
            tab = api.channel_uploads(cid, 30)
        except Exception as e:  # noqa: BLE001
            log(f"   ℹ️ Could not read {creators[cid]['name']}'s uploads ({type(e).__name__}).")
            continue
        for v in viral_remix.outliers(tab, min_views=cfg["floor"], x=OUTLIER_X):
            if v["id"] not in seen and _keep(niche, v):
                seen.add(v["id"])
                rows.append({**v, "found": f"breakout of {creators[cid]['name']}"})
    rows.sort(key=lambda v: v["views"], reverse=True)
    # The watchlist keeps the 60 creators with the biggest hits.
    creators = dict(sorted(creators.items(), key=lambda kv: kv[1]["best"], reverse=True)[:60])
    return rows, creators


# ------------------------------------------------------------------ 2. study

class Pick(BaseModel):
    id: str
    keep: bool


class Picks(BaseModel):
    videos: List[Pick]


SCREEN_PROMPT = """We run {what}. Below are the most viewed recent YouTube videos for our searches. Search
results are noisy (first pass, 28-oct-2026: "gk quiz" found health clickbait, "ai song" found nursery rhymes).
Keep a video only if it is the KIND of video our channel makes or could make on its own (same format and
audience), and it is not about {rules}. {hint}Answer for every id: keep true or false.

{lines}"""


def screen(niche, rows, client, log=print):
    """The rows a title-only call keeps (one text call for the whole list), in their order; all of
    them when the call fails, since each watch still checks the fit itself."""
    if not rows:
        return rows
    lines = "\n".join(json.dumps({"id": v["id"], "title": (v.get("title") or "")[:120],
                                  "channel": (v.get("channel") or "")[:60], "views": v.get("views"),
                                  "seconds": v.get("seconds")}, ensure_ascii=False) for v in rows[:40])
    try:
        hint = NICHES[niche].get("screen", "")
        got = kit.ask_json(client, Picks, SCREEN_PROMPT.format(what=viral_remix.WHAT[niche],
                                                               rules=viral_remix._rules(niche),
                                                               hint=f"{hint} " if hint else "", lines=lines))
    except Exception as e:  # noqa: BLE001
        log(f"   ℹ️ Could not screen the {niche} finds ({type(e).__name__}); watching them unscreened.")
        return rows
    keep = {p.id for p in got.videos if p.keep}
    kept = [v for v in rows if v["id"] in keep]
    log(f"   🔎 {len(kept)} of {len(rows[:40])} {niche} finds look like our kind of video.")
    return kept


def study_some(niche, rows, client, log=print, study_fn=None):
    """Study up to STUDIES_PER_RUN of ``rows`` we have not studied; [record]."""
    study_fn = study_fn or viral_remix.study
    done, tries = [], 0
    seen = viral_remix.studied_ids()
    skip = viral_remix.recent_channels()
    for v in rows:
        if len(done) >= STUDIES_PER_RUN or tries >= TRIES_PER_RUN:
            break
        if v["id"] in seen or v.get("channel") in skip:
            continue
        tries += 1
        try:
            rec = study_fn(client, v["id"], niche, log=log, skip_channels=skip, meta=v)
        except ValueError as e:
            log(f"   ℹ️ Skipped \"{(v.get('title') or '')[:50]}\": {e}")
            continue
        except Exception as e:  # noqa: BLE001 — Gemini down: the rest of the pass waits for tomorrow
            log(f"   ℹ️ Could not study a {niche} video ({type(e).__name__}: {str(e)[:100]}).")
            break
        done.append(rec)
        skip = set(skip) | {rec.get("channel")}
    return done


# ------------------------------------------------------------------ 3. playbook

class Playbook(BaseModel):
    topics: List[str]
    hooks: List[str]
    structure: str
    length: str
    on_screen: List[str]
    audio: str
    endings: List[str]
    titles: List[str]
    avoid: List[str]


PLAYBOOK_PROMPT = """You are the head of content for {what}.
Below are studies of the {n} most viewed recent videos in our niche: views, title and what each one did.
Turn them into the playbook our writers and editors follow for every video. Keep only patterns that
several of these videos share or that the biggest hits use, concrete enough to apply. English, and
quote no video's words: describe shapes and devices.
Leave out every tactic that misleads or pressures viewers, even when hits use it: comment demands tied to
religion, luck or guilt ("type X or ..."), fake urgency, false or shock claims, misleading thumbnails or
health scares. Our channel must stay trusted and inside YouTube's spam and misinformation rules.
{ours}
Return:
- topics: 5-8 topic families that win in this niche now, specific ("records only one player holds").
- hooks: 4-6 hook patterns for the first 3 seconds, each as a device with its shape.
- structure: the shape that wins, in one paragraph (beats in order, where the payoff sits).
- length: the winning length ("25-35 s").
- on_screen: 3-6 rules for the first frame, the text on screen and the pictures.
- audio: one sentence on voice, music and sound effects.
- endings: 2-4 ways the best ones end (comment questions, loops).
- titles: 3-5 title patterns (shapes, not titles).
- avoid: 3-5 things the weaker videos here do.

STUDIES:
{studies}"""


def studies_of(niche, limit=PLAYBOOK_STUDIES):
    """This niche's stored studies, the most viewed first."""
    recs = [r for k, r in viral_remix._read().items()
            if not k.startswith("_") and r.get("niche") == niche and r.get("blueprint")]
    return sorted(recs, key=lambda r: (r.get("views") or 0), reverse=True)[:limit]


def _study_line(r):
    bp = r["blueprint"]
    parts = [f"{r.get('views', 0):,} views, {r.get('seconds') or bp.get('length_seconds') or '?'} s: "
             f"\"{(r.get('title') or '')[:90]}\"",
             f"angle: {bp.get('angle', '')}", f"hook: {bp.get('hook_pattern', '')}",
             f"beats: {'; '.join(bp.get('beats') or [])}", f"devices: {'; '.join(bp.get('devices') or [])}"]
    for key in ("first_frame", "visuals", "text_style", "audio", "cta"):
        if bp.get(key):
            parts.append(f"{key.replace('_', ' ')}: {bp[key]}")
    if bp.get("timeline"):
        parts.append(f"timeline: {'; '.join(bp['timeline'][:8])}")
    if bp.get("audience"):
        parts.append(f"commenters: {bp['audience']}")
    parts.append(f"why: {bp.get('why', '')}")
    return "- " + " | ".join(parts)


def build_playbook(niche, client, ours=""):
    recs = studies_of(niche)
    if len(recs) < PLAYBOOK_AFTER:
        return None
    prompt = PLAYBOOK_PROMPT.format(
        what=viral_remix.WHAT[niche], n=len(recs), studies="\n".join(_study_line(r) for r in recs)[:30000],
        ours=f"\nOur own channel so far: {ours}\n" if ours else "")
    pb = kit.ask_json(client, Playbook, prompt, model=viral_remix._writer())
    return {**pb.model_dump(), "at": int(time.time()), "from": [r["id"] for r in recs]}


def playbook_due(data, new, now=None):
    pb = data.get("playbook") or {}
    if not pb:
        return True
    return data.get("new_since_playbook", 0) + new >= PLAYBOOK_AFTER or \
        (now or time.time()) - pb.get("at", 0) >= PLAYBOOK_MAX_AGE


def playbook_text(niche, limit=2600):
    """The niche's playbook as a block for a prompt, or "": what the winners' files measure against ours
    (teardown.py) first, then the playbook from Gemini's studies."""
    data = load(niche) if niche in NICHES else {}
    import teardown
    measured = teardown.measured_text(data)
    pb = data.get("playbook")
    if not pb:
        return measured[:limit]

    def join(xs, n):
        return "; ".join(str(x).strip().rstrip(".") for x in (xs or [])[:n] if str(x).strip())
    lines = ["WHAT WINS IN THIS NICHE NOW (patterns from this month's most viewed videos in it; shapes to "
             "use with our own facts and words, never their words):",
             f"- Topics that win: {join(pb.get('topics'), 6)}",
             f"- Hooks that hold: {join(pb.get('hooks'), 5)}",
             f"- Shape: {pb.get('structure', '').strip()}",
             f"- Length: {pb.get('length', '').strip()}",
             f"- On screen: {join(pb.get('on_screen'), 4)}",
             f"- Endings: {join(pb.get('endings'), 3)}",
             f"- Titles: {join(pb.get('titles'), 4)}",
             f"- Avoid: {join(pb.get('avoid'), 4)}"]
    text = "\n".join(line for line in lines if not line.endswith(": "))
    return ((measured + "\n\n" if measured else "") + text)[:limit]


# ------------------------------------------------------------------ 4. ideas

def next_idea(niche, used=(), take=True, now=None):
    """The best fresh study of this niche as an idea for the channel, or None. ``take`` marks it
    made, so it is never offered twice."""
    if niche not in NICHES or NICHES[niche].get("ideas") is False:
        return None
    now = now or time.time()
    data = load(niche)
    taken = set(data.get("taken") or [])
    used = {str(u).lower() for u in used}
    for rec in studies_of(niche, limit=100):
        if rec["id"] in taken or rec["topic"].lower() in used or now - rec.get("at", 0) > IDEA_DAYS * 86400:
            continue
        if take:
            data["taken"] = (data.get("taken") or [])[-300:] + [rec["id"]]
            _save(niche, data)
        return viral_remix.as_idea(rec)
    return None


# ------------------------------------------------------------------ the daily pass

def _measure(niche, ours_files, log, now, **fns):
    """teardown.measure_some on a copy of the niche's measurements (minutes of downloads and listening, so
    the file is read again before the pass saves); ({"anatomy", "ours"}, how many) or (None, 0)."""
    import teardown
    data = load(niche)
    got = {"anatomy": dict(data.get("anatomy") or {}), "ours": dict(data.get("ours") or {})}
    try:
        n = teardown.measure_some(got, studies_of(niche, 40), ours_files or [], log=log, now=now, **fns)
    except Exception as e:  # noqa: BLE001 — measuring is a bonus too
        log(f"   ℹ️ Could not measure the {niche} videos ({type(e).__name__}).")
        return None, 0
    return got, n


def run(niche, client, log=print, now=None, api=None, study_fn=None, ours="", queries=None, ours_files=None,
        measure=True, **fns):
    """One research pass for ``niche``; a summary dict. Never raises. ``queries``: search these
    instead of today's two (a first pass that should look wider). ``ours_files``: our videos of the niche
    still on disk, measured against the studied winners (teardown.py); ``measure=False`` skips that."""
    now = now or time.time()
    data = load(niche)
    data["last_run"] = int(now)            # set first: a crash must not retry every minute
    _save(niche, data)
    out = {"at": int(now), "found": 0, "studied": [], "playbook": False}
    try:
        rows, creators = find(niche, now, api=api, log=log, queries=queries)
        out["found"] = len(rows)
        seen = viral_remix.studied_ids()
        todo = screen(niche, [v for v in rows if v["id"] not in seen], client, log=log)
        recs = study_some(niche, todo, client, log=log, study_fn=study_fn)
        out["studied"] = [r["id"] for r in recs]
        measured, out["measured"] = _measure(niche, ours_files, log, now, **fns) if measure else (None, 0)
        data = load(niche)
        if measured:
            data.update(measured)
        data["creators"] = creators
        data["candidates"] = [{k: v.get(k) for k in ("id", "title", "channel", "views", "seconds", "found")}
                              for v in rows[:30]]
        if playbook_due(data, len(recs), now):
            try:
                pb = build_playbook(niche, client, ours)
            except Exception as e:  # noqa: BLE001 — the old playbook stays
                log(f"   ℹ️ Could not build the {niche} playbook ({type(e).__name__}).")
                pb = None
            if pb:
                data["playbook"], data["new_since_playbook"] = pb, 0
                out["playbook"] = True
            else:
                data["new_since_playbook"] = data.get("new_since_playbook", 0) + len(recs)
        else:
            data["new_since_playbook"] = data.get("new_since_playbook", 0) + len(recs)
        data["runs"] = ((data.get("runs") or []) + [out])[-14:]
        _save(niche, data)
    except Exception as e:  # noqa: BLE001 — research is a bonus, never a blocker
        log(f"⚠️ Research for {niche} failed ({type(e).__name__}: {str(e)[:120]}).")
        out["error"] = f"{type(e).__name__}"
    log(f"🔎 Research {niche}: {out['found']} viral videos found, {len(out['studied'])} studied"
        + (f", {out['measured']} measured" if out.get("measured") else "")
        + (", playbook rebuilt" if out["playbook"] else "") + ".")
    return out


ASK_DAYS = 14


def asks(niche, days=ASK_DAYS, limit=4):
    """Topics the viewers of this niche's viral videos asked for in their comments (newest studies
    first, one per topic): demand seen under someone else's hit, for the channel's planner."""
    since, seen, out = time.time() - days * 86400, set(), []
    recs = sorted((r for r in studies_of(niche, 60) if r.get("at", 0) >= since), key=lambda r: -r.get("at", 0))
    for r in recs:
        for a in r["blueprint"].get("asks") or []:
            key = re.sub(r"[^a-z0-9]+", " ", str(a).lower()).strip()
            if key and key not in seen and len(key) > 3:
                seen.add(key)
                out.append(str(a).strip()[:80])
    return out[:limit]


def summary(niche):
    """What the dashboard shows: the playbook, today's finds, the studies and the top creators."""
    data = load(niche)
    studies = [{"id": r["id"], "title": r.get("title"), "views": r.get("views"), "channel": r.get("channel"),
                "topic": r.get("topic"), "angle": r["blueprint"].get("angle"),
                "hook": r["blueprint"].get("hook_pattern"), "audience": r["blueprint"].get("audience") or "",
                "asks": r["blueprint"].get("asks") or [], "at": r.get("at"),
                "taken": r["id"] in set(data.get("taken") or [])} for r in studies_of(niche, 20)]
    creators = [{"id": cid, **c} for cid, c in list((data.get("creators") or {}).items())[:12]]
    import teardown
    measured = {"lines": teardown.lines(data),
                "theirs": sum(1 for r in (data.get("anatomy") or {}).values() if r.get("m")),
                "ours": sum(1 for r in (data.get("ours") or {}).values() if r.get("m")),
                "need": [teardown.MIN_THEIRS, teardown.MIN_OURS]}
    return {"niche": niche, "last_run": data.get("last_run"), "playbook": data.get("playbook"), "measured": measured,
            "candidates": (data.get("candidates") or [])[:12], "studies": studies, "creators": creators,
            "runs": (data.get("runs") or [])[-5:]}
