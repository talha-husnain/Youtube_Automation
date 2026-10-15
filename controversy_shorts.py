"""Controversies about famous people, explained (CONTENT_GENRE=controversy).

Controversy channels lose videos (and get sued) in two ways: news footage,
which broadcasters claim through Content ID, and rumours told as facts. So
nothing here comes from a broadcast: the picture is animated (the cricket
fact cards, swiping in on a dark red canvas) with the person's free-licence
photo (player_photo, kind "person", credited in the description). And the
words go through three gates:
- research with Google Search grounding, every claim labelled REPORTED,
  ALLEGED, ADMITTED or RULED, at least MIN_SOURCES sources, else no video;
- the script says "ilzaam" (allegation) for what was only alleged, gives the
  person's own side and the outcome, and never mocks;
- a second model call checks the script against the facts for defamation
  risk; one rewrite with its notes, and if it still fails there is no video.
Topics in RULES (religion, politics, the army, minors, sexual allegations
no court ruled on...) are refused at every step. The description lists the
real source links (the grounding redirect links expire, so each one is
followed to the article it points at).

Env: CONTROVERSY_TOPIC (one line: the person and what it is about),
CONTROVERSY_VOICE, BG_MUSIC (a dark suspense bed from music_beds).
"""
import os
import re
import time
from types import SimpleNamespace
from typing import List

import httpx
from pydantic import BaseModel

import cricket_shorts as cs
import framed_layout as fl
import short_kit as kit

VOICE_STYLE = "like a calm, gripping documentary narrator, natural Urdu accent, serious, never mocking"
MIN_SOURCES = 3
RED = "#7F1D1D"
# Stock footage beside a real person's name must not suggest what no court
# said: handcuffs or prison bars next to "allegations" read as guilt.
FOOTAGE_RULE = ("Never footage that suggests a crime, arrest or guilt (handcuffs, prison bars, police "
                "arrests, mugshots), never a recognisable face, never religious or political symbols. ")
RULES = ("religion or blasphemy; politics or the army of any country; anyone under 18; sexual assault or "
         "harassment claims no court has ruled on; private people who are not famous; suicide or self-harm; "
         "a named person's health or mental illness; family members who are not public figures themselves")


class Beat(BaseModel):
    when: str
    headline: str
    detail: str
    line: str


class Story(BaseModel):
    found: bool
    allowed: bool
    reason: str
    person: str
    title: str
    hook_line: str
    beats: List[Beat]
    status_line: str
    question: str


class Check(BaseModel):
    ok: bool
    problems: List[str]


FACTS_PROMPT = """Today is {today}. Research this controversy about a famous person: {topic}
Use Google Search and only reliable news sources. Report: who; what happened and when (dates);
what was alleged and what was proven, admitted or ruled; how the person responded (their own
words when reported); what officials, courts, boards or companies decided; where it stands today.
Start every claim with REPORTED, ALLEGED, ADMITTED or RULED.
If the topic touches any of these, answer only "NOT ALLOWED: <why>": {rules}.
If fewer than three reliable sources cover it, answer only "NOT FOUND"."""

STORY_PROMPT = """You write a 40-55 second YouTube Short that explains a controversy about a famous
person, for Pakistani and Indian viewers, voiced by the channel {handle}. Topic: {topic}
Use ONLY the facts below; never add a claim, a date or a quote that is not in them.
{fixes}
Facts:
{facts}

Return:
- found: true when the facts describe the controversy.
- allowed: false if it touches any of: {rules}. reason: why, or "".
- person: the person's full name as their Wikipedia article is titled.
- title: max 45 characters, Roman Urdu, curious but true ("Shoaib Akhtar aur PCB: asal kahani kya thi?"),
  no emoji, no word that calls the person guilty of something only alleged.
- hook_line: Roman Urdu, 8-14 words, the question the video answers.
- beats: 4 to 6, in time order, covering what happened, the reaction, the person's own side,
  and the outcome. Each: when (max 12 characters: "2019", "MARCH 2023"), headline (max 30
  characters), detail (Roman Urdu, max 80 characters), line (Roman Urdu voice line, 10-20 words).
  Anything ALLEGED is said as an allegation ("un par ilzaam laga ke...", "reports ke mutabiq...");
  only ADMITTED, RULED or plainly REPORTED events are said as facts.
- status_line: Roman Urdu, 10-18 words: where it stands today.
- question: Roman Urdu, max 70 characters, asking viewers' opinion without attacking anyone,
  ending with "comment mein batao" or similar.
Neutral and fair: no insults, no mocking, no guessing at motives. Everyday Roman Urdu in Latin
letters, never Devanagari or Arabic script."""

CHECK_PROMPT = """You check a short video script about a real, named person for defamation risk
before it is published. The facts, each labelled REPORTED, ALLEGED, ADMITTED or RULED:
{facts}

The script (title, then the voice lines in order):
{script}

Problems to look for: a statement the facts do not support; something only ALLEGED said as a
fact; the person's own side missing when the facts have it; a topic among: {rules}; insults,
mockery, or guesses at motives. Return ok=true only when there is no problem; otherwise ok=false
and the problems, each one short."""

SEO_CONTEXT = ("IMPORTANT: this short is NOT comedy. It is a factual explainer of a controversy about "
               "{person}: {topic}. Ignore the comedy phrases and hashtags above; use the person's name, "
               "'controversy', 'explained', 'kya hua tha', 'asal kahani'. Never state an allegation as a "
               "fact, never insult the person, no claim that is not in the video. creator is \"\".")

IDEAS_PROMPT = """Today is {today}. Plan the next {count} YouTube Shorts of a channel that explains
controversies about famous people, fairly and with sources, for Pakistani and Indian viewers. Use
Google Search for what people are talking about now. About half recent (last 30 days) and well
reported; the rest famous older ones people still search: Bollywood, Pakistani showbiz and dramas,
cricketers, YouTubers and influencers, global celebrities, tech and business leaders.
Each idea is about ONE named famous person (never a team, board, company or country), names
them first and says what it is about ("Shoaib Akhtar vs PCB: the 2008 ban"), and is a real,
widely reported controversy, not a small disagreement or a debate about policy.
Never any of: {rules}.
{learn}Never repeat any of these, already made:
{avoid}
One per line, each starting with "topic: ". Nothing else."""


def channel_ideas(client, count=8, avoid=(), best=(), worst=()):
    import trends
    learn = trends.hint("controversy")
    if best:
        learn += "These did BEST on the channel, make more like them:\n" + "\n".join(best) + "\n"
    if worst:
        learn += "These did WORST, avoid their kind:\n" + "\n".join(worst) + "\n"
    text, _ = cs.grounded(client, IDEAS_PROMPT.format(
        today=time.strftime("%d %B %Y"), count=count, rules=RULES, learn=learn,
        avoid="\n".join(list(avoid)[-80:]) or "(nothing yet)"))
    seen = {a.lower() for a in avoid}
    return [i for i in cs._idea_lines(text) if i["kind"] == "topic" and i["text"].lower() not in seen][:count + 2]


def _real_url(url):
    """Where a grounding redirect link points (they expire), or the link itself."""
    if "grounding-api-redirect" not in (url or ""):
        return url
    try:
        r = httpx.head(url, follow_redirects=False, timeout=10)
        return r.headers.get("location") or url
    except httpx.HTTPError:
        return url


def research(client, topic):
    """(facts text, [(source name, real url)])."""
    from google.genai import types
    r = client.models.generate_content(
        model=kit.text_model(), contents=FACTS_PROMPT.format(topic=topic, rules=RULES, today=time.strftime("%d %B %Y")),
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
    gm = r.candidates[0].grounding_metadata if r.candidates else None
    seen, sources = set(), []
    for c in getattr(gm, "grounding_chunks", None) or []:
        web = getattr(c, "web", None)
        if not web or not web.uri:
            continue
        name = (web.title or "").strip()
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        sources.append((name, web.uri))
    return (r.text or "").strip(), sources


def _script(story):
    return "\n".join([f"TITLE: {story.title}", story.hook_line, *(b.line for b in story.beats),
                      story.status_line, story.question])


def write(client, topic, handle):
    """(Story, facts, sources) that passed every gate, or raises."""
    from quiz_shorts import quiz_model
    facts, sources = research(client, topic)
    head = facts[:200].upper()
    if "NOT ALLOWED" in head:
        raise RuntimeError(f"Not covered on this channel: {facts[:160]}")
    if not facts or "NOT FOUND" in head or len(sources) < MIN_SOURCES:
        raise RuntimeError(f"Not enough reliable sources for this one ({len(sources)}).")
    fixes = ""
    for attempt in range(2):
        story = kit.ask_json(client, Story, STORY_PROMPT.format(handle=handle, topic=topic, facts=facts,
                                                                rules=RULES, fixes=fixes), model=quiz_model())
        if not story.found or not story.allowed or len(story.beats) < 3:
            raise RuntimeError(f"Not made: {story.reason or 'the facts were too thin'}.")
        story.beats = story.beats[:6]
        check = kit.ask_json(client, Check, CHECK_PROMPT.format(facts=facts, script=_script(story), rules=RULES),
                             model=quiz_model())
        if check.ok:
            return story, facts, sources
        print(f"   ⚠️ The fairness check found {len(check.problems)} problem(s); rewriting once.")
        fixes = "Fix these problems found by a fact check of the last version:\n- " + "\n- ".join(check.problems)
    raise RuntimeError("The script did not pass the fairness check twice; skipped to be safe.")


def run(output_dir, pipeline):
    import credits
    topic = re.sub(r"\s+", " ", os.environ.get("CONTROVERSY_TOPIC") or "").strip()[:200]
    if len(topic) < 5:
        raise RuntimeError("Name the person and the controversy.")
    cfg = fl.settings()
    client = kit.gemini()
    print(f"🔥 Controversy short: researching \"{topic}\"...")
    story, facts, sources = write(client, topic, cfg["handle"] or "this channel")
    print(f"   ✅ {story.person}: {len(story.beats)} beats, {len(sources)} sources, passed the fairness check.")
    stem = kit.neutral_stem("Story")
    photo = cs._photo(story.person, output_dir, kind="person")
    lines = [story.hook_line] + [b.line for b in story.beats] + [story.status_line, story.question]
    print(f"🎙️ Voicing {len(lines)} lines...")
    windows, voices, caps, body_end = cs._voice_timeline(
        client, lines, output_dir, stem, voice=os.environ.get("CONTROVERSY_VOICE") or "Charon", style=VOICE_STYLE,
        broll_rule=FOOTAGE_RULE)
    frame = SimpleNamespace(kicker="CONTROVERSY", title=story.title)
    events, sfx, images, n = cs.topic_frame_events(frame, body_end, cfg["handle"]), [], [], len(story.beats)
    for k, a, b in windows:
        sfx.append((kit.WHOOSH, 0.3, max(0.0, a - 0.15)))
        if k == 0:
            if photo:
                images.append({"path": photo["card"], "t0": a, "t1": b, "y": 850, "zoom": 0.06})
                events += cs._pill(a + 0.3, b, 1290, cs._txt(photo["info"]["player"], 26).upper())
                images.append({"path": photo["badge"], "t0": b, "t1": body_end, "y": 200, "zoom": 0.0,
                               "x": kit.OUT_W - 150})
            else:
                events.append(kit.dialogue(4, a, b, "CkText", rf"{{\an5\pos({cs.CX},900)\fad(200,200)}}"
                                                              rf"{cs._txt(story.hook_line, 90)}"))
        elif k <= n:
            beat = story.beats[k - 1]
            fact = cs.Fact(headline=beat.headline, stat=beat.when.upper(), detail=beat.detail, line=beat.line)
            events += cs.fact_events(k, n, fact, a, b, count=False)
        elif k == n + 1:
            events += cs._pill(a, b, 700, "AB KYA HAAL HAI?")
            events.append(kit.dialogue(4, a + 0.2, b, "CkText", rf"{{\an5\pos({cs.CX},930)\fad(200,200)}}"
                                                                 rf"{cs._txt(story.status_line, 110)}"))
        else:
            events.append(kit.dialogue(4, a, b, "CkText", rf"{{\an5\pos({cs.CX},900)\1c{cs._c(fl.GOLD)}"
                                                          rf"\fad(200,200)}}{cs._txt(story.question, 72)}"))
    clip = {"start": 0.0, "video_title_for_youtube_short": story.title, "viral_hook_text": story.hook_line,
            "why": f"Controversy explained: {topic}", "predicted_score": 88, "captions": kit.timed_transcript(caps),
            "genre": "controversy", "ai_voice": "AI voice", "comment_question": story.question,
            "sources": [u for _n, u in sources[:8]], "controversy": story.model_dump()}

    def add_sources(c):
        real = [(name, _real_url(url)) for name, url in sources[:4]]
        block = ("Sources:\n" + "\n".join(f"- {name}: {url}" if name else f"- {url}" for name, url in real)
                 + "\nThis video reports what these sources published; allegations are told as allegations.")
        c["source_links"] = real
        for field in ("seo_description", "video_description_for_instagram"):
            if c.get(field):
                c[field] = credits.insert(c[field], block)

    cs._finish(output_dir, stem, pipeline, cfg, events, [cfg["bg"], kit.blend(RED, cfg["bg"], 0.35)],
               voices, sfx, body_end, clip,
               {"source_title": topic, "context": SEO_CONTEXT.format(person=story.person, topic=topic),
                "text_limit": 4000},
               images=images, photos=[photo["info"]] if photo else [], genre="controversy", after_seo=add_sources,
               broll_rule=FOOTAGE_RULE)
