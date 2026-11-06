"""Money told as stories, in motion graphics (CONTENT_GENRE=money; owner, 29-oct-2026: "a channel with
motion graphics: research very detailed, find the most viral content about a specific niche, write the
script, make the motion graphics and voice it").

Research of 29-oct-2026 (channel numbers from vidIQ; sources in the session):
- The niche: money told as stories: prices then and now, salaries at home and in the Gulf, a company's
  biggest mistake, who earns what, money compared across countries. The most viewed narrated money Shorts
  put a number in the title and the first line ("Toyota's $2,300,000,000 Mistake", 10.6M views); finance
  has the highest ad rates of the niches looked at; no faceless Roman-Urdu motion-graphics channel was found.
- YouTube does not monetise "content that looks like it's made with a template" (answer/1311392, enforced
  harder from 16 Jul 2026): each video is its own researched story, the templates only draw it, in a colour
  set of its own (motion_scenes.palette_for) and a different writing shape (script_craft.STRUCTURES).
- 32-38 s, 85-100 words, 4-6 scenes, the hook's number on frame 0, the biggest number last, no footage.
The numbers are the product, so they pass gates, like controversy_shorts' claims:
- research with Google Search grounding: every fact with its number, unit, date and source, 3+ sources;
- code keeps a number on screen or in the voice only when the research has it (``figures``: "2.3 billion"
  is 2.3 and 2,300,000,000; a rounded "$2.3B" matches 2.27 billion), computes every ratio and change itself
  and never sets two currencies against each other (motion_scenes.comparable);
- a second model call checks the script against the research (a change in net worth told as income, an
  old price told as today's); one rewrite with its notes, then no video.
Never advice to buy, sell or invest (SEBI, Jan 2025: no share prices under 3 months old in education),
no expert persona (script_craft.PERSONA), no disputed borders on screen.

Env: MONEY_TOPIC (the story, one line), MONEY_VOICE, BG_MUSIC (a bed from music_beds, kind "money").
"""
import itertools
import os
import re
import time
from typing import List

from pydantic import BaseModel

import cricket_shorts as cs
import framed_layout as fl
import motion_scenes as ms
import script_craft as craft
import short_kit as kit
import viral_remix

VOICE_STYLE = "like a sharp, friendly money explainer, natural Urdu accent, clear on every number, confident"
MIN_SOURCES = 3
MIN_BEATS = 4
MAX_BEATS = 6
# The free voice reads Roman Urdu (as Urdu script) at about 2.2 words a second: the first live script, asked
# for 85-100 words, made a 59 s Short (29-oct-2026). 32-38 s is the target, so 65-80 words; past MAX_WORDS
# the writer gets one rewrite.
MAX_WORDS = 90
RULES = ("advice to buy, sell or invest in anything; share or crypto prices from the last 3 months; betting, "
         "gambling, lotteries or get-rich-quick schemes; politics, parties or the army of any country; religion; "
         "maps or borders of Kashmir or any disputed land; India and Pakistan as rivals (a calm comparison of "
         "prices or salaries is fine); private people who are not famous; anyone's health; dodging taxes")


class Item(BaseModel):
    name: str
    value: float
    shown: str
    country: str


class Beat(BaseModel):
    template: str
    headline: str
    unit: str
    better: str
    items: List[Item]
    note: str
    line: str


class Script(BaseModel):
    found: bool
    allowed: bool
    reason: str
    title: str
    kicker: str
    hook_line: str
    hook_number: str
    beats: List[Beat]
    payoff_label: str
    payoff_shown: str
    verdict_line: str
    question: str


class Check(BaseModel):
    ok: bool
    problems: List[str]


FACTS_PROMPT = """Today is {today}. Research this money story for a short video: {topic}
Use Google Search and reliable sources only: central banks, statistics bureaus, the World Bank or IMF,
regulators, company reports and filings, major newspapers. List 8 to 15 facts, one per line. Each line:
the claim with its exact number and unit, what the number measures (a price, a monthly or yearly salary,
revenue, profit, net worth, a loss, a share of people), its currency, the date or year it is for, and the
source's name in brackets. Give the latest numbers and, where the story needs them, the same measure in
earlier years from the same kind of source. For a comparison between countries, give each country's number
in one common currency when a source does (USD), never a conversion of your own.
No investment advice; no share or crypto prices from the last 3 months.
If the topic touches any of these, answer only "NOT ALLOWED: <why>": {rules}.
If reliable numbers cannot be found, answer only "NOT FOUND"."""

STORY_PROMPT = """You write a 32-38 second motion-graphics YouTube Short that tells a money story with
numbers, for viewers in Pakistan, India and the Gulf, voiced by the channel {handle}. Topic: {topic}
Use ONLY the facts below: every number on screen and in the voice must be in them. Never add a number, a
date or a claim that is not in them, and never work out a number yourself: code computes every ratio,
difference and percentage change and shows it on screen.
{fixes}
Facts:
{facts}

Return:
- found: true when the facts answer the topic with real numbers. allowed: false if it touches any of:
  {rules}. reason: why not, or "".
- title: max 50 characters, Roman Urdu, a specific promise with the key number or comparison, no emoji, no "#".
- kicker: 1-3 English words in capitals for the label at the top ("PRICE CHECK", "SALARY", "BIG MISTAKE").
- hook_line: Roman Urdu, 6-12 words, spoken in under 3 seconds: the most surprising number or contrast of
  the story; never a greeting.
- hook_number: the number shown huge on the first frame (the one the hook says), max 10 characters, written
  as on the screen ("$2.3B", "Rs 272", "64%").
- beats: 4 to 6 scenes in story order, each one picture of the story; use at least 3 different templates and
  never the same one twice in a row (a new kind of picture keeps the eye):
  - template: one of
    "big_number": one number; items[0] = the number, items[1] (optional) = the same measure to compare with
      (an earlier year, another place);
    "versus": exactly 2 items compared on one measure; better = which value wins: "higher" or "lower";
    "bars": 3-6 items on one measure (the same price in different countries);
    "timeline": 3-8 items in time order, name = the year or date, value = the number then;
    "list": 3-5 items ranked on one measure; better says whether higher or lower ranks first;
    "grid": 1-4 groups out of 100: name = the group, value = how many in 100 (a percentage);
    "fact": one striking fact in words; items[0] (optional) = the one number it states.
  - headline: max 30 characters, what the picture shows ("Petrol, per litre").
  - unit: the unit of the values ("PKR", "USD", "%", "per litre"). Every item of a scene is the same measure
    in the same currency: never set rupees against dirhams, or Pakistani rupees against Indian rupees.
  - better: "higher" or "lower" (only versus and list use it; else "higher").
  - items: name (max 18 characters), value (the plain number as the fact gives it, no unit: 2300000000 or
    2.3), shown (how the screen writes it, max 12 characters: "$2.3B", "Rs 272", "₹1.2 lakh", "64%"),
    country (the country's English name when the item is a country, else "").
  - note: the publisher's name and the year, max 36 characters ("OGRA, 2026", "World Bank, 2024"), never
    only a date.
  - line: the voice line while the scene is on screen, Roman Urdu, 8-12 words, at most two numbers, each
    also on screen in this scene.
- payoff_label (max 30 characters) and payoff_shown (max 12 characters): the biggest or most surprising
  number of the story, shown last, exactly as a fact gives it.
- verdict_line: Roman Urdu, 8-14 words, lands the payoff with that number.
- question: Roman Urdu, max 70 characters, a question people answer in one word, ending with "comment mein
  batao" or similar.
Write every amount in the voice lines in digits with its scale word, the way people say it: "2.3 arab
dollar", "1.2 lakh rupay", "45 crore", "272 rupay"; round it the way people speak ("40 rupay" for Rs 40.39,
"378 rupay" for Rs 377.91), while the screen shows the exact number. The whole voice-over is 65-80 words (about 35 seconds:
every extra word loses viewers), scene lines 8-12 words. Never tell anyone
to buy, sell or invest: say what the numbers show. Everyday spoken Roman Urdu in Latin letters, never
Devanagari or Arabic script."""

CHECK_PROMPT = """You check a money explainer Short before it is published. The research, each fact with
its source and date:
{facts}

The script: the title, then each scene's on-screen numbers and voice line:
{script}

Problems to look for: a number on screen or in the voice that the research does not have; a number used
as something it does not measure (a change in net worth told as income, a yearly figure as a monthly one, a
price of one year told as today's, an amount in one currency shown as another); two things set against
each other that the research measures differently; advice to buy, sell or invest; a topic among: {rules}.
Return ok=true only when there is no problem; otherwise ok=false and each problem, short."""

SEO_CONTEXT = ("IMPORTANT: this short is NOT comedy. It is a motion-graphics money explainer: {topic}. Ignore the "
               "comedy phrases and hashtags above; use the words people search for it (price, salary, kitna, "
               "kitne ka, mehngai, the country, company or thing it names) and its key number. Never advise "
               "anyone to buy, sell or invest. creator is \"\".")

IDEAS_PROMPT = """Today is {today}. Plan the next {count} YouTube Shorts of a motion-graphics channel that
tells money stories with numbers, in Roman Urdu, for viewers in Pakistan, India and the Gulf. Use Google
Search for what people talk about now (prices, salaries, budgets, companies, deals) and for famous money
stories people still search. Mix: prices then and now (petrol, gold, a plate of biryani, a car, a flat);
salaries and what they buy at home and in the Gulf, the UK or the US; a company's biggest mistake or
comeback in numbers; who earns what (public companies, publicly reported pay of famous people); the
rupee and inflation; what famous things cost (a stadium, a mega project, a satellite); money compared
across countries. Leave cricketers' pay and scandals to our other channels.
Each idea is ONE specific question a number answers, in English ("How much costlier has petrol got in
Pakistan since 2005?", "What a driver earns in Dubai vs Karachi"), and must be answerable with published
numbers (central banks, statistics bureaus, World Bank, IMF, company reports, major news).
Never any of: {rules}.
{learn}Never repeat any of these, already made:
{avoid}
One per line, each starting with "topic: ". Nothing else."""


def channel_ideas(client, count=8, avoid=(), best=(), worst=(), requests=(), notes=""):
    import engage
    import trends
    learn = trends.searches_hint() + trends.wiki_hint() + trends.hint("money") + engage.request_hint(requests)
    if (notes or "").strip():
        # The owner's topic wishes (Channels tab); the rules above still win.
        learn += f"The channel's owner wants these topics most; at least half the ideas come from them: {notes.strip()}\n"
    if best:
        learn += "These did BEST on the channel, make more like them:\n" + "\n".join(best) + "\n"
    if worst:
        learn += "These did WORST, avoid their kind:\n" + "\n".join(worst) + "\n"
    text, _ = cs.grounded(client, IDEAS_PROMPT.format(
        today=time.strftime("%d %B %Y"), count=count, rules=RULES, learn=learn,
        avoid="\n".join(list(avoid)[-80:]) or "(nothing yet)"))
    seen = {a.lower() for a in avoid}
    return [i for i in cs._idea_lines(text) if i["kind"] == "topic" and i["text"].lower() not in seen][:count + 2]


# A video or a social post is not a source for a number: the first live run listed a YouTube video among its
# sources (29-oct-2026). Grounding links are redirects, so the site is read from the chunk's title.
NOT_A_SOURCE = re.compile(r"youtube\.|youtu\.be|facebook\.|instagram\.|tiktok\.|twitter\.|(^|\.)x\.com|reddit\.|"
                          r"quora\.|pinterest\.|linkedin\.", re.I)


def research(client, topic):
    """(facts text, [(source name, url)]) from one grounded call; videos and social posts do not count."""
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
        if name.lower() in seen or NOT_A_SOURCE.search(name):
            continue
        seen.add(name.lower())
        sources.append((name, web.uri))
    return (r.text or "").strip(), sources


# ---------------------------------------------------------------- the number gate

SCALE = {"thousand": 1e3, "hazar": 1e3, "hazaar": 1e3, "k": 1e3, "lakh": 1e5, "lac": 1e5, "lakhs": 1e5,
         "million": 1e6, "mn": 1e6, "m": 1e6, "crore": 1e7, "cr": 1e7, "crores": 1e7, "billion": 1e9, "bn": 1e9,
         "b": 1e9, "arab": 1e9, "kharab": 1e11, "trillion": 1e12, "tn": 1e12, "t": 1e12}
# A scale word only counts as one ("2.3 bn", "45-crore"), never as the start of a word ("2005 mein").
_FIGURE = re.compile(r"(?<![\w.])(\d+(?:,\d{2,3})*(?:\.\d+)?)(?:[\s-]*("
                     + "|".join(sorted(SCALE, key=len, reverse=True)) + r")(?![a-z]))?", re.I)
SMALL = 10           # a bare count in words ("5 mulk", "3 saal") needs no source; an amount or a share does


def figures(text):
    """[(value, scaled value or None, decimals, start, end)] of every number in ``text``: "2.3 billion"
    is (2.3, 2.3e9, 1, ...), "1,20,000" is (120000, None, 0, ...), "4.7x" is (4.7, None, 1, ...)."""
    out = []
    for m in _FIGURE.finditer(text or ""):
        raw = m.group(1)
        v = float(raw.replace(",", ""))
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        word = (m.group(2) or "").lower()
        out.append((v, v * SCALE[word] if word else None, decimals, m.start(), m.end()))
    return out


def _known(facts):
    """Every value the research states, plain and scaled."""
    have = set()
    for v, scaled, _d, _a, _b in figures(facts):
        have.add(v)
        if scaled is not None:
            have.add(scaled)
    return have


def _half_step(value, decimals):
    """Half of the last digit written: a number written "2.3" stands for 2.25-2.35, "2300000000" for
    2.25-2.35 billion (its trailing zeros are not precision)."""
    if decimals:
        return 0.5 * 10 ** -decimals
    digits = str(int(abs(value)))
    zeros = len(digits) - len(digits.rstrip("0")) if value else 0
    return 0.5 * 10 ** min(zeros, max(0, len(digits) - 2))


def close(value, decimals, have, scale=1.0):
    """True when ``value`` (written with ``decimals``) is one of ``have``, as written or rounded."""
    tol = max(_half_step(value, decimals) * scale, abs(value * scale) * 1e-6)
    return any(abs(value * scale - h) <= tol + 1e-9 for h in have)


def unsupported(text, have, derived=(), small=SMALL):
    """The numbers in ``text`` that neither the research (``have``) nor code (``derived``) gives. A scaled
    number must match as scaled: "23 crore" is not supported by some other fact's 23."""
    bad = []
    for v, scaled, decimals, a, b in figures(text):
        around = (text[max(0, a - 3):a] + text[b:b + 2]).lower()
        money = bool(re.search(r"[$₹£€¥%]|rs|aed|sar", around))
        if scaled is None and not money and decimals == 0 and v <= small:
            continue
        if scaled is not None:
            ok = close(v, decimals, have, scale=scaled / v) if v else 0.0 in have
        else:
            ok = close(v, decimals, have) or close(v, decimals, set(derived))
        if not ok:
            bad.append(text[a:b].strip())
    return bad


def derived(values, years=()):
    """What code may say about these values: ratios, changes in percent and differences, rounded the ways a
    voice line says them ("teen guna", "4.7 guna", "370 percent"), and the gaps between the research's
    years ("20 saal mein")."""
    out = set()
    for x, y in itertools.permutations([v for v in values if v and v > 0], 2):
        r = x / y
        for d in (r, (r - 1) * 100, abs(x - y)):
            out |= {round(d), round(d, 1), round(abs(d)), round(abs(d), 1)}
    out |= {abs(a - b) for a, b in itertools.combinations(sorted(set(years)), 2)}
    return out


def _item_ok(item, have):
    """The item's number is in the research: as the screen writes it, else its plain value."""
    if re.search(r"\d", item.shown or "") and not unsupported(item.shown, have, small=-1):
        return True
    raw = f"{abs(float(item.value or 0)):f}".rstrip("0").rstrip(".")
    return close(abs(float(item.value or 0)), len(raw.split(".")[1]) if "." in raw else 0, have)


def validate(script, facts):
    """Keep what the research supports. Returns (kept beats, problems): a scene goes when a number on it or in
    its line is not in the research, when its items are not one measure in one currency, or when its
    template has too few items; the comparison of a big number goes alone."""
    have = _known(facts)
    kept, problems = [], []
    # Code may state ratios of the numbers that are in the research, never of the ones that are not.
    every = [abs(float(i.value)) for b in script.beats for i in b.items if _item_ok(i, have)]
    extra = derived(every, years=[v for v in have if 1900 <= v <= 2100 and float(v).is_integer()])
    for b in script.beats[:MAX_BEATS + 2]:
        name = (b.template or "").strip().lower().replace(" ", "_")
        b.template = {"number": "big_number", "ranking": "list", "line": "timeline", "bar": "bars"}.get(name, name)
        if b.template not in ms.TEMPLATES:
            problems.append(f"scene '{b.headline}': unknown template {b.template!r}")
            continue
        items = [i for i in b.items if _item_ok(i, have)]
        dropped = [i.shown for i in b.items if i not in items]
        if dropped:
            problems.append(f"scene '{b.headline}': numbers not in the research: {', '.join(dropped)}")
        if b.template == "big_number" and len(items) > 1 and not ms.comparable(items[:2]):
            items = items[:1]                  # the number stands; the comparison in another currency goes
        items = items[:ms.MAX_ITEMS[b.template]]
        if b.template in ("versus", "bars", "list", "timeline") and not ms.comparable(items):
            problems.append(f"scene '{b.headline}': its items are not one measure in one currency")
            continue
        if b.template == "grid" and sum(max(0.0, i.value) for i in items) > 100.5:
            problems.append(f"scene '{b.headline}': its groups add up to more than 100")
            continue
        if len(items) < ms.MIN_ITEMS[b.template]:
            problems.append(f"scene '{b.headline}': too few supported items for a {b.template}")
            continue
        bad = unsupported(b.line, have, extra) + unsupported(b.headline, have, extra) + unsupported(b.note, have)
        if bad:
            problems.append(f"scene '{b.headline}': numbers not in the research: {', '.join(bad)}")
            continue
        b.items = items
        kept.append(b)
    for field in ("hook_line", "verdict_line", "title", "question"):
        bad = unsupported(getattr(script, field), have, extra)
        if bad:
            problems.append(f"{field}: numbers not in the research: {', '.join(bad)}")
    for field in ("hook_number", "payoff_shown"):
        if unsupported(getattr(script, field), have):
            setattr(script, field, "")
    return kept[:MAX_BEATS], problems


def _script_text(script):
    rows = [f"TITLE: {script.title}", f"HOOK ({script.hook_number}): {script.hook_line}"]
    for b in script.beats:
        nums = "; ".join(f"{i.name} = {i.shown}" for i in b.items)
        rows.append(f"[{b.template}] {b.headline} ({b.unit}) {nums} | source: {b.note} | voice: {b.line}")
    rows += [f"PAYOFF ({script.payoff_label}: {script.payoff_shown}): {script.verdict_line}", script.question]
    return "\n".join(rows)


def write(client, topic, handle, log=print):
    """(Script, facts, sources) that passed every gate, or raises."""
    facts, sources = research(client, topic)
    head = facts[:200].upper()
    if "NOT ALLOWED" in head:
        raise RuntimeError(f"Not covered on this channel: {facts[:160]}")
    if not facts or "NOT FOUND" in head or len(sources) < MIN_SOURCES:
        raise RuntimeError(f"Not enough reliable sources for this one ({len(sources)}).")
    fixes = ""
    for attempt in range(2):
        script = kit.ask_json(client, Script, STORY_PROMPT.format(handle=handle, topic=topic, facts=facts, rules=RULES,
                                                                  fixes=fixes)
                              + viral_remix.note_for(topic) + "\n\n" + craft.short_rules(exclude=("MYSTERY",)),
                              model=craft.writer_model())
        if not script.found or not script.allowed:
            raise RuntimeError(f"Not made: {script.reason or 'the research had no usable numbers'}.")
        script.beats, problems = validate(script, facts)
        line_problems = [p for p in problems if not p.startswith("scene")]
        words = sum(len(t.split()) for _p, t in craft.spoken(script))
        if words > MAX_WORDS and not attempt:
            line_problems.append(f"the voice-over has {words} words: cut it to 65-80")
            problems.append(line_problems[-1])
        if len(script.beats) < MIN_BEATS or line_problems:
            log(f"   ⚠️ The number check left {len(script.beats)} scenes ({len(problems)} problem(s)); rewriting once.")
            fixes = "Fix these problems found by a number check of the last version:\n- " + "\n- ".join(problems[:12])
            continue
        for p in problems:
            log(f"   ✂️ {p}")
        # Polished before the fact check, so the check reads what will be voiced. line_ok keeps every number
        # of a line and adds none the research lacks.
        craft.polish(client, script, facts, what="money explainer YouTube Short in motion graphics", log=log)
        script.beats, after = validate(script, facts)
        viral_remix.guard(topic, " ".join(t for _p, t in craft.spoken(script)))
        check = kit.ask_json(client, Check, CHECK_PROMPT.format(facts=facts, script=_script_text(script), rules=RULES),
                             model=craft.writer_model())
        if check.ok and len(script.beats) >= MIN_BEATS:
            return script, facts, sources
        problems = check.problems or after
        log(f"   ⚠️ The fact check found {len(problems)} problem(s); rewriting once.")
        fixes = "Fix these problems found by a fact check of the last version:\n- " + "\n- ".join(problems[:12])
    raise RuntimeError("The numbers did not pass the checks twice; skipped to be safe.")


def run(output_dir, pipeline):
    import credits
    import controversy_shorts
    topic = re.sub(r"\s+", " ", os.environ.get("MONEY_TOPIC") or "").strip()[:200]
    if len(topic) < 5:
        raise RuntimeError("Name the money story to tell.")
    # Motion graphics only: stock footage would sit under the charts (broll reads this in this job's process).
    os.environ["STOCK_FOOTAGE"] = "0"
    cfg = fl.settings()
    client = kit.gemini()
    print(f"💰 Money short: researching \"{topic}\"...")
    script, facts, sources = write(client, topic, cfg["handle"] or "this channel")
    print(f"   ✅ {len(script.beats)} scenes ({', '.join(b.template for b in script.beats)}), "
          f"{len(sources)} sources, passed the number and fact checks.")
    stem = kit.neutral_stem("Money")
    pal = ms.palette_for(topic)
    flags = ms.flag_badges(script.beats, output_dir)
    lines = [script.hook_line] + [b.line for b in script.beats] + [script.verdict_line, script.question]
    print(f"🎙️ Voicing {len(lines)} lines...")
    windows, voices, caps, body_end = cs._voice_timeline(
        client, lines, output_dir, stem, voice=os.environ.get("MONEY_VOICE") or "Charon", style=VOICE_STYLE,
        broll_rule="")
    events, images, sfx = ms.events(script, windows, body_end, cfg["handle"], pal, flags)
    clip = {"start": 0.0, "video_title_for_youtube_short": script.title, "viral_hook_text": script.hook_line,
            "why": f"Money story: {topic}", "predicted_score": 90, "captions": kit.timed_transcript(caps),
            "genre": "money", "ai_voice": "AI voice", "comment_question": script.question,
            "sources": [u for _n, u in sources[:8]], "money": script.model_dump(), "palette": pal["name"]}

    def add_sources(c):
        real = [(name, controversy_shorts._real_url(url)) for name, url in sources[:5]]
        block = ("Sources:\n" + "\n".join(f"- {name}: {url}" if name else f"- {url}" for name, url in real)
                 + "\nNumbers as these sources published them, for the dates shown. Not financial advice.")
        c["source_links"] = real
        for field in ("seo_description", "video_description_for_instagram"):
            if c.get(field):
                c[field] = credits.insert(c[field], block)

    cs._finish(output_dir, stem, pipeline, cfg, events, [cfg["bg"], kit.blend(pal["glow"], cfg["bg"], 0.35)],
               voices, sfx, body_end, clip,
               {"source_title": topic, "context": SEO_CONTEXT.format(topic=topic), "text_limit": 4000},
               images=images, genre="money", after_seo=add_sources, broll_rule="", stickers=False)
