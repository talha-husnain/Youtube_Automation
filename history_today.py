"""Aaj ki tareekh: a daily "on this day in history" Short for the history
channel (history_videos.run hands over when HISTORY_TODAY=1).

The long videos are found slowly; a Short a day is how a new channel gets
seen. The story is one real event that happened on today's date in an
earlier year, for Pakistani and Indian viewers. The gates follow the long
videos': Google Search grounding with at least MIN_SOURCES sources, the
history channel's RULES and honorifics, one check of the script against the
research (one rewrite, then no video), and for sacred topics no people in the
pictures and no music. The picture is the cricket fact cards over free
footage and Wikipedia pictures (broll), never news footage.

Env: HISTORY_TODAY=1, HISTORY_LANG (urdu | english), HISTORY_TODAY_DATE
(YYYY-MM-DD, tests and back-fills; default today), HISTORY_AVOID (JSON list
of events already made), HISTORY_VOICE.
"""
import json
import os
import re
import time
from datetime import datetime
from types import SimpleNamespace
from typing import List

from pydantic import BaseModel

import cricket_shorts as cs
import framed_layout as fl
import history_videos as hv
import script_craft as craft
import short_kit as kit

MIN_SOURCES = 3
BROWN = "#5B3A1A"


class Beat(BaseModel):
    when: str
    headline: str
    detail: str
    line: str


class Story(BaseModel):
    found: bool
    allowed: bool
    reason: str
    sacred: bool
    event: str
    year: str
    title: str
    hook_line: str
    beats: List[Beat]
    why_line: str
    question: str


class Check(BaseModel):
    ok: bool
    problems: List[str]


FACTS_PROMPT = """Today is {today}. Find ONE real historical event that happened on {day_month} (this exact
day and month, in any earlier year) that Pakistani and Indian viewers would find gripping: a battle, a
discovery, a famous first, the founding or fall of an empire or city, a turning point in South Asian,
Islamic or world history. Use Google Search and reliable sources (encyclopedias, museums, universities,
major newspapers). Report: the event, the exact date and year, where, who was involved, what happened
step by step, and why it still matters. Quote nobody unless a documented original exists.
Never pick: {rules}. Never one of these, already made: {avoid}.
If fewer than three reliable sources confirm the date, answer only "NOT FOUND"."""

STORY_PROMPT = """You write a 40-55 second YouTube Short "Aaj ki tareekh" (on this day in history) for the
history channel {handle}, for Pakistani and Indian viewers. Today is {day_month}.
Use ONLY the facts below; never add a date, number, name or quote that is not in them.
{fixes}
Facts:
{facts}

Return:
- found: true when the facts describe one event on {day_month}.
- allowed: false if the story can only be told with {rules}. reason: why, or "".
- sacred: true if it involves {sacred}. {honour}
- event: the event's name as its Wikipedia article is titled.
- year: the year as digits ("1857", "711 CE").
- title: max 45 characters, {lang}, starts with the date ("{day_month}: ..."), curious but true, no emoji.
- hook_line: {lang}, 8-14 words, opens with "Aaj ke din" (or "On this day") and the year, makes them stay.
- beats: 4 to 5, in time order. Each: when (max 12 characters: a year, "SUBAH", "3 DIN BAAD"), headline
  (max 30 characters), detail ({lang}, max 80 characters), line ({lang} voice line, 10-20 words).
- why_line: {lang}, 10-18 words: why this day still matters.
- question: {lang}, max 70 characters, asking viewers something about it, ending with "comment mein batao"
  (or "tell us in the comments").
Spoken lines are read aloud by a voice: no Roman numerals, no brackets. Language: {lang_rule}."""

CHECK_PROMPT = """You check a short history video script before it is published. The research:
{facts}

The script (title, then the voice lines in order):
{script}

Problems to look for: a date, number, name or quote the research does not support; the event not on
{day_month}; mocking or judging any religion, sect or nation; a missing honorific for a revered religious
figure. Return ok=true only when there is no problem; otherwise ok=false and the problems, each short."""

SEO_CONTEXT = ("IMPORTANT: this short is NOT comedy. It is a factual 'on this day in history' short about "
               "{event} ({year}), told on {day_month}. Ignore the comedy phrases and hashtags above; use the "
               "event's name, 'aaj ki tareekh', 'on this day', 'history', the year. creator is \"\".")


def _day(date=None):
    raw = os.environ.get("HISTORY_TODAY_DATE") or ""
    try:
        return datetime.strptime(raw, "%Y-%m-%d") if raw else (date or datetime.now())
    except ValueError:
        return date or datetime.now()


def day_month(d):
    return f"{d.day} {d.strftime('%B')}"


def _script(story):
    return "\n".join([f"TITLE: {story.title}", story.hook_line, *(b.line for b in story.beats),
                      story.why_line, story.question])


def research(client, d, avoid):
    """(facts, [(name, url)]) from one grounded call."""
    from google.genai import types
    r = client.models.generate_content(
        model=kit.text_model(),
        contents=FACTS_PROMPT.format(today=d.strftime("%d %B %Y"), day_month=day_month(d), rules=hv.RULES,
                                     avoid="; ".join(avoid[-40:]) or "(nothing yet)"),
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
    gm = r.candidates[0].grounding_metadata if r.candidates else None
    seen, sources = set(), []
    for c in getattr(gm, "grounding_chunks", None) or []:
        web = getattr(c, "web", None)
        if web and web.uri and (web.title or "").lower() not in seen:
            seen.add((web.title or "").lower())
            sources.append(((web.title or "").strip(), web.uri))
    return (r.text or "").strip(), hv.rank_sources(sources)


def write(client, d, handle, lang="urdu", avoid=(), research_fn=None):
    """(Story, facts, sources) that passed the check, or raises."""
    from quiz_shorts import quiz_model
    facts, sources = (research_fn or research)(client, d, list(avoid))
    if not facts or "NOT FOUND" in facts[:200].upper() or len(sources) < MIN_SOURCES:
        raise RuntimeError(f"No well-sourced event for {day_month(d)} ({len(sources)} sources).")
    fixes = ""
    for attempt in range(2):
        story = kit.ask_json(client, Story, STORY_PROMPT.format(
            handle=handle, day_month=day_month(d), facts=facts, fixes=fixes, rules=hv.RULES, sacred=hv.SACRED,
            honour=hv.HONOUR.get(lang, hv.HONOUR["urdu"]), lang=hv.LANG_NAME.get(lang, "Roman Urdu"),
            lang_rule=hv.LANG_RULE.get(lang, hv.LANG_RULE["urdu"])) + "\n\n" + craft.short_rules(),
            model=quiz_model())
        if not story.found or not story.allowed or len(story.beats) < 3:
            raise RuntimeError(f"Not made: {story.reason or 'the facts were too thin'}.")
        story.beats = story.beats[:5]
        if lang == "urdu":   # the polish speaks Roman Urdu; an English channel keeps the writer's lines
            craft.polish(client, story, facts, what="\"on this day in history\" YouTube Short")
        check = kit.ask_json(client, Check, CHECK_PROMPT.format(facts=facts, script=_script(story),
                                                                day_month=day_month(d)), model=quiz_model())
        if check.ok:
            return story, facts, sources
        print(f"   ⚠️ The fact check found {len(check.problems)} problem(s); rewriting once.")
        fixes = "Fix these problems found by a fact check of the last version:\n- " + "\n- ".join(check.problems)
    raise RuntimeError("The script did not pass the fact check twice; skipped to be safe.")


def run(output_dir, pipeline):
    import credits
    from controversy_shorts import _real_url
    d = _day()
    lang = (os.environ.get("HISTORY_LANG") or "urdu").lower()
    lang = lang if lang in hv.LANGS else "urdu"
    try:
        avoid = [str(a)[:120] for a in json.loads(os.environ.get("HISTORY_AVOID") or "[]")]
    except ValueError:
        avoid = []
    cfg = fl.settings()
    client = kit.gemini()
    print(f"📅 Aaj ki tareekh ({day_month(d)}): researching...")
    story, facts, sources = write(client, d, cfg["handle"] or "this channel", lang, avoid)
    print(f"   ✅ {story.event} ({story.year}): {len(story.beats)} beats, {len(sources)} sources.")
    stem = kit.neutral_stem("Today")
    lines = [story.hook_line] + [b.line for b in story.beats] + [story.why_line, story.question]
    rule = hv.FOOTAGE_RULE + ((hv.NO_PEOPLE + " ") if story.sacred else "")
    print(f"🎙️ Voicing {len(lines)} lines...")
    windows, voices, caps, body_end = cs._voice_timeline(
        client, lines, output_dir, stem, voice=os.environ.get("HISTORY_VOICE") or "Charon",
        style=hv.VOICE_STYLE[lang], broll_rule=rule)
    frame = SimpleNamespace(kicker="AAJ KI TAREEKH" if lang == "urdu" else "ON THIS DAY", title=story.title)
    events, sfx, n = cs.topic_frame_events(frame, body_end, cfg["handle"]), [], len(story.beats)
    for k, a, b in windows:
        sfx.append((kit.WHOOSH, 0.3, max(0.0, a - 0.15)))
        if k == 0:
            events += cs._pill(a + 0.3, b, 1290, cs._txt(f"{day_month(d).upper()} {story.year}", 26))
            events.append(kit.dialogue(4, a, b, "CkText", rf"{{\an5\pos({cs.CX},900)\fad(200,200)}}"
                                                          rf"{cs._txt(story.hook_line, 90)}"))
        elif k <= n:
            beat = story.beats[k - 1]
            fact = cs.Fact(headline=beat.headline, stat=beat.when.upper(), detail=beat.detail, line=beat.line)
            events += cs.fact_events(k, n, fact, a, b, count=False)
        elif k == n + 1:
            events += cs._pill(a, b, 700, "AAJ BHI KYUN ZAROORI?" if lang == "urdu" else "WHY IT MATTERS")
            events.append(kit.dialogue(4, a + 0.2, b, "CkText", rf"{{\an5\pos({cs.CX},930)\fad(200,200)}}"
                                                                 rf"{cs._txt(story.why_line, 110)}"))
        else:
            events.append(kit.dialogue(4, a, b, "CkText", rf"{{\an5\pos({cs.CX},900)\1c{cs._c(fl.GOLD)}"
                                                          rf"\fad(200,200)}}{cs._txt(story.question, 72)}"))
    clip = {"start": 0.0, "video_title_for_youtube_short": story.title, "viral_hook_text": story.hook_line,
            "why": f"On this day: {story.event} ({story.year})", "predicted_score": 85,
            "captions": kit.timed_transcript(caps), "genre": "history", "ai_voice": "AI voice",
            "comment_question": story.question, "sources": [u for _n, u in sources[:8]],
            "history": {"today": True, "event": story.event, "year": story.year, "date": d.strftime("%Y-%m-%d"),
                        "sacred": story.sacred, "lang": lang}}

    def add_sources(c):
        real = [(name, _real_url(url)) for name, url in sources[:4]]
        block = "Sources:\n" + "\n".join(f"- {name}: {url}" if name else f"- {url}" for name, url in real)
        c["source_links"] = real
        for field in ("seo_description", "video_description_for_instagram"):
            if c.get(field):
                c[field] = credits.insert(c[field], block)

    if story.sacred:
        os.environ["BG_MUSIC"] = "0"          # no music under a sacred story, as in the long videos
    cs._finish(output_dir, stem, pipeline, cfg, events, [cfg["bg"], kit.blend(BROWN, cfg["bg"], 0.35)],
               voices, sfx, body_end, clip,
               {"source_title": story.event,
                "context": SEO_CONTEXT.format(event=story.event, year=story.year, day_month=day_month(d)),
                "text_limit": 4000},
               genre="history", after_seo=add_sources, broll_rule=rule)
