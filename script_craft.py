"""Shared writing craft for every narrated script (owner, 22-oct-2026: "content humans love",
more views). Our Shorts kept viewers a median 7-19 s of 30-35 s.

Two pieces:
- ``short_rules()`` / ``long_rules()``: hook, re-hook, payoff and loop rules added to each
  script prompt (after ``.format``, so braces in them never matter).
- ``polish()``: a second "script doctor" call. It scores the hook against a rubric, writes
  five other hooks, and tightens the spoken lines. Code, not the model, decides what is
  kept: a rewritten line must keep every number of the original, add no number or name the
  research does not have, stay in Latin letters and about the same length, or the original
  line stays. ``POLISH=0`` turns it off.
"""
import os
import re
from typing import List

from pydantic import BaseModel

import short_kit as kit

# Openers viewers swipe on, and phrases that make a script sound machine-written.
# Matched case-insensitively anywhere in a spoken line.
# English: Wikipedia's "signs of AI writing" plus YouTube clichés. Roman Urdu / Hinglish: greetings
# and calques of the same (research notes 22-oct-2026; no study names these as stale, it is judgement
# from the anti-greeting evidence: most viewers leave in the first 3 s).
BANNED = [
    "dosto", "doston", "swagat", "welcome back", "hello friends", "hello guys", "namaste", "assalam o alaikum",
    "assalam-o-alaikum", "aaj hum baat karenge", "aaj ki video", "is video mein", "in this video",
    "kya aap jaante hain", "kya aap jante hain", "did you know", "let's dive", "lets dive", "dive into",
    "buckle up", "without further ado", "game changer", "game-changer", "in today's world", "it's important to note",
    "unleash", "unlock the secrets", "tapestry", "testament", "delve", "a journey", "ever wondered",
    "stay tuned", "like aur subscribe", "like and subscribe", "like share subscribe", "smash that", "smash the like",
    "mind-blowing", "you won't believe", "aap yakeen nahi karenge", "pivotal", "vibrant", "nestled",
    "groundbreaking", "meticulously", "multifaceted", "evolving landscape", "indelible mark", "imagine a world",
    "little did they know", "the rest is history", "let that sink in", "toh chaliye shuru karte hain",
    "chaliye shuru karte hain", "bina waqt zaya kiye", "video end tak dekhein", "video end tak dekhna",
    "milte hain agli video mein", "aaiye jaante hain", "aaiye jante hain", "hairan reh jayenge",
    "rongte khade ho jayenge", "hosh uda dene wala", "ek aisa raaz", "itihaas ke panno mein",
    "aaj ke is daur mein", "aham kirdar ada kiya", "gehri chhaap", "behad dilchasp", "muaziz nazreen",
    # Meta narration ("this video will show..."): an opening rewrite on 22-oct-2026 swapped a real
    # question for "Yeh video dikhayegi ke..." and scored itself 9/10.
    "yeh video", "is video", "video dikhayegi", "this video",
]


class Pick(BaseModel):
    better: int
    why: str


JUDGE_PROMPT = """Two versions of the {part} of a YouTube {what} for Pakistani and Indian viewers.
Which one makes more people keep watching? Judge only that: the first seconds grab (a specific number,
name, conflict or question that needs an answer), concrete words, no slow set-up, no "this video will
show", no greeting. Both say the same facts. Answer better = 1 or 2, and why in one short sentence.

VERSION 1:
{one}

VERSION 2:
{two}"""


def judge(client, what, part, original, rewrite, rnd=None):
    """True when a blind judge prefers ``rewrite``. The two go in shuffled order with no label, because
    a writer that scores its own work drifts up (research 22-oct-2026: judge in shuffled order); any
    failure keeps the original."""
    import random
    rnd = rnd or random
    swap = rnd.random() < 0.5
    one, two = (rewrite, original) if swap else (original, rewrite)
    try:
        got = kit.ask_json(client, Pick, JUDGE_PROMPT.format(part=part, what=what, one=one, two=two),
                           model=writer_model())
        return got.better == (1 if swap else 2)
    except Exception:  # noqa: BLE001
        return False

# A different shape per video: one template read out again and again is what YouTube's
# "inauthentic content" rule (July 2025) calls mass production.
STRUCTURES = [
    "COUNTDOWN: build to the biggest fact last, say early that the last one is the craziest.",
    "RESULT FIRST: open on the ending or the final number, then show how it happened.",
    "MYTH THEN TRUTH: open on what most fans believe, then prove what really happened.",
    "MYSTERY: describe the record or the moment but hold back the name until the last line.",
    "CONTRAST: put two numbers or two people side by side and let the gap shock.",
]

SHORT_CRAFT = """WRITING RULES (most viewers decide in the first 3 seconds whether to stay):
- Line 1 is the hook, spoken in under 3 seconds (6-12 words), carrying a number, a name or a conflict: the most
  surprising number, a contradiction, the result first, or a precise question. Name exactly what is unknown
  ("kis bowler ne sirf 12 gend mein..."), never a vague "ek raaz". Never a greeting, the channel's name, "aaj hum",
  "is video mein", "kya aap jaante hain" or "dosto".
- The hook opens a loop: it promises something specific and the script pays it off in its last lines, not in
  line 2. Restate the promise once in the middle ("lekin asli record abhi baaki hai").
- Every line adds one new fact, a new one every 5-7 seconds. Sentences of 10 words or fewer, about 2.5-3 words a
  second when spoken. Cut warm-up words ("to", "basically", "dekhiye"), adjectives that carry no fact and any line
  that repeats an earlier one. Specific beats vague: a number, a name, a place, a date.
- Link the beats with turns ("lekin", "isliye", "phir", "asal twist yeh hai") so each line pulls into the next.
- Talk like a real Pakistani/Indian fan explaining it to a friend: everyday words, energy, no bookish words.
- The on-screen title carries the hook's promise in 3-7 words, so the Short works with the sound off.
- End on the payoff, no outro. The question for the comments takes a one-word answer people will argue about
  ("Babar ya Kohli? Ek naam likho"), never "like aur subscribe". The last line should make a replay feel natural.
- Shape for this video: {structure}
- Never use these stale phrases: {banned}."""

LONG_CRAFT = """WRITING RULES (YouTube measures the first 30 seconds as the intro; most viewers leave there):
- 0-15 s: open cold on the most dramatic TRUE moment of the story. By 30 s: what is at stake and the one question
  the video answers, with a promise of the payoff. No greeting, no channel intro, no "is video mein hum dekhenge".
- By about 60 s give a small payoff (one surprising answer), so the promise feels real.
- Plant two or three open questions early and answer them late; never answer the main one before the last chapter.
- Start each chapter with a re-hook (a new question, a turn, a number), about every 3 minutes something new
  happens, and end most chapters on an open turn. Put strong material in minutes 3-6, not only at the end.
- Every paragraph carries a specific: a date, a number, a name, a place, a detail you can see. No filler sentences,
  no "it is important to note", no repeating what was just said.
- Tell it as a story with people who want something and obstacles in their way, in plain spoken language.
- End on the payoff; the subscribe ask is one short sentence at the very end.
- Never use these stale phrases: {banned}."""


FIXED_ORDER = "the order given above (the first line is the hook)."


# When the new writing went live (22-oct-2026 22:00 local): the week report compares the Shorts
# uploaded after it with the month before (reminders.craft_line).
SINCE = 1792688400


def short_rules(structure=None, exclude=()):
    """``structure``: a fixed shape (a match or a controversy has its own order); else one of
    STRUCTURES at random, minus the ones whose name starts with a word in ``exclude``."""
    import random
    pool = [s for s in STRUCTURES if s.split(":")[0] not in exclude] or STRUCTURES
    return SHORT_CRAFT.format(banned=", ".join(f'"{b}"' for b in BANNED),
                              structure=structure or random.choice(pool)) + lessons()


def long_rules():
    return LONG_CRAFT.format(banned=", ".join(f'"{b}"' for b in BANNED)) + lessons()


def lessons():
    """This channel's own best and worst openings by viewers who stayed (my_channels.hook_lessons,
    sent as HOOK_LESSONS), as a last rule line; "" until the channel has the numbers."""
    text = (os.environ.get("HOOK_LESSONS") or "").strip()
    return ("- " + text) if text else ""


def banned_hits(text):
    low = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "
    return [b for b in BANNED if re.search(r"(?<![a-z])" + re.escape(b) + r"(?![a-z])", low)]


def writer_model():
    """The model that writes scripts: the stronger flash, not GEMINI_MODEL's flash-lite."""
    return (os.environ.get("SCRIPT_MODEL") or os.environ.get("QUIZ_MODEL")
            or os.environ.get("GEMINI_MODEL_THUMBNAIL") or "gemini-3.7-flash")


# --- the spoken lines of a story ------------------------------------------------------------
SINGLES_FIRST = ("hook_line",)
LISTS = ("beats", "facts", "rows")
SINGLES_LAST = ("verdict_line", "status_line", "why_line", "outro_line", "question")


def spoken(story, fields=None):
    """[(path, text)] of the lines a voice reads, in order. ``fields`` limits it to those names
    (a quiz polishes only its hook and outro: its questions carry the answers)."""
    out = []

    def want(name):
        return fields is None or name in fields
    for name in SINGLES_FIRST:
        if want(name) and isinstance(getattr(story, name, None), str) and getattr(story, name).strip():
            out.append((name, getattr(story, name)))
    for name in LISTS:
        if not want(name):
            continue
        for i, item in enumerate(getattr(story, name, None) or []):
            line = getattr(item, "line", None)
            if isinstance(line, str) and line.strip():
                out.append((f"{name}.{i}", line))
    for name in SINGLES_LAST:
        if want(name) and isinstance(getattr(story, name, None), str) and getattr(story, name).strip():
            out.append((name, getattr(story, name)))
    return out


def _set(story, path, text):
    if "." in path:
        name, i = path.split(".")
        setattr(getattr(story, name)[int(i)], "line", text)
    else:
        setattr(story, path, text)


# --- guards -------------------------------------------------------------------------------
def numbers(text):
    return {n.replace(",", "") for n in re.findall(r"\d+(?:[.,:/]\d+)*", text or "")}


OPENERS = {"suno", "socho", "kaun", "kisne", "kitne", "kitna", "kitni", "sabse", "duniya", "kisi", "koi", "sach",
           "yaad", "zara", "dekho", "asal", "kahani", "ghalat", "sahi", "number", "record", "itihaas", "tareekh",
           "aakhir", "akhir", "achanak", "sochiye", "batao", "bataiye", "na", "nahi", "haan", "wah", "uff"}


# Honorifics the history prompts require ("Hazrat", "sallallahu alaihi wasallam"): never a new name.
HONORIFICS = {"hazrat", "imam", "sallallahu", "alaihi", "wasallam", "saw", "rahmatullah", "radiallahu", "anhu"}


def _names(text):
    """Capitalised words: names, places, teams. Each sentence's first word counts too ("Kohli bhi
    hairan" slipped through a check that skipped it) unless it is a common opener."""
    import subtitles
    out = set()
    for sentence in re.split(r"[.!?]+\s+", text or ""):
        words = re.findall(r"[A-Za-z][A-Za-z'-]*", sentence)
        out |= {w.lower().strip("'") for w in words[1:] if w[0].isupper() and len(w) > 2}
        if (words and len(words[0]) > 2 and words[0][0].isupper()
                and words[0].lower() not in subtitles.SENTENCE_STARTS | OPENERS):
            out.add(words[0].lower().strip("'"))
    return out - HONORIFICS


def _latin(text):
    return not re.search(r"[ऀ-ॿ؀-ۿ]", text or "")


def line_ok(new, old, facts, hook=False):
    """Code's verdict on one rewritten line."""
    new = (new or "").strip()
    if not new or not _latin(new) or banned_hits(new):
        return False
    n_new, n_old = len(new.split()), len(old.split())
    if n_new < 4 or n_new > (14 if hook else max(int(n_old * 1.25) + 1, n_old + 3)):
        return False
    have = numbers(old) | numbers(facts)
    if not numbers(old) <= numbers(new) and not hook:
        return False                        # the card shows that number: the voice must say it
    if not numbers(new) <= have:
        return False                        # a number the research does not have
    known = (old + " " + facts).lower()
    return all(n in known for n in _names(new))


class Hook(BaseModel):
    text: str
    score: int


class Doctored(BaseModel):
    hook_score: int
    hooks: List[Hook]
    lines: List[str]


POLISH_PROMPT = """You are the script editor of a {what} for Pakistani and Indian viewers. Our Shorts lose most
viewers in the first 2 seconds and the median viewer leaves before the end, so every word must earn its place.

THE FACTS (the only source of truth; add nothing that is not here):
{facts}

THE SCRIPT, one spoken line per number (line 0 is the hook):
{script}

1. Score line 0 from 1 to 10 as a hook: does it stop a thumb in under 3 seconds? 10 = a specific surprising number,
   contradiction or stake that makes the viewer need the answer; 5 = a plain topic statement; 1 = a greeting, the
   channel's name or "aaj hum baat karenge".
2. Write 5 better hooks, each a different pattern (the shocking number; the contradiction "sab samajhte hain X,
   lekin..."; the stake "agar yeh ek gend na hoti..."; the question that needs an answer; the bold true claim).
   Each 6-12 words, true to the facts, same language as the script. Score each honestly with the same rubric.
3. Rewrite every line (0 to {last}) to be punchier and sound like a real desi creator talking to a friend:
   cut warm-up and filler words, keep each line's meaning, keep EVERY number and name it has, never add a fact,
   never make a claim stronger than the line says it (an allegation stays an allegation), about the same
   length or shorter. Return exactly {n} lines in the same order. The last line keeps its ending
   (a question for the comments) if it has one.
{language}
Never use: {banned}."""


def polish(client, story, facts, what="cricket facts YouTube Short", fields=None, log=print,
           language="Roman Urdu in Latin letters, the way people speak; never Devanagari or Arabic script."):
    """Polish ``story``'s spoken lines in place and return it. Never raises: any failure
    keeps the writer's own lines."""
    if os.environ.get("POLISH", "1") == "0":
        return story
    lines = spoken(story, fields)
    if len(lines) < 2:
        return story
    facts = (facts or "")[:12000]
    script = "\n".join(f"{i}. {t}" for i, (_p, t) in enumerate(lines))
    try:
        got = kit.ask_json(client, Doctored, POLISH_PROMPT.format(
            what=what, facts=facts, script=script, last=len(lines) - 1, n=len(lines), language=language,
            banned=", ".join(BANNED)) + (chr(10) + lessons() if lessons() else ""), model=writer_model())
    except Exception as e:  # noqa: BLE001 — the writer's lines are fine on their own
        log(f"   ℹ️ Script polish skipped ({type(e).__name__}).")
        return story
    new_lines = dict(lines)
    kept = 0
    if len(got.lines) == len(lines):
        for (path, old), new in zip(lines, got.lines):
            if new.strip() != old.strip() and line_ok(new, old, facts, hook=path == lines[0][0]):
                new_lines[path] = new.strip()
                kept += 1
    hook_path, hook_old = lines[0]
    best = max((h for h in got.hooks if line_ok(h.text, hook_old, facts, hook=True)),
               key=lambda h: h.score, default=None)
    stale = bool(banned_hits(hook_old))
    # A self-scored rubric drifts by a point or two: only a clear gain is a candidate hook,
    # unless the writer's own hook is a stale opener.
    if best and (best.score >= got.hook_score + 2 or stale):
        new_lines[hook_path] = best.text.strip()
    changed = [p for p, t in lines if new_lines[p] != t]
    if changed:
        before = "\n".join(t for _p, t in lines)
        after = "\n".join(new_lines[p] for p, _t in lines)
        # The doctor scores its own work; a blind judge decides (a stale opener always goes).
        if stale or judge(client, what, "voice-over script (one line per row, the first is the hook)",
                          before, after):
            for p in changed:
                _set(story, p, new_lines[p])
            if new_lines[hook_path] != hook_old:
                log(f"   🪝 Hook {got.hook_score}/10 -> {new_lines[hook_path][:90]}")
            log(f"   ✍️ Script polish: {len(changed)} of {len(lines)} lines changed (a blind judge agreed).")
        else:
            log(f"   ⚖️ Script polish: a blind judge preferred the writer's own script ({got.hook_score}/10 hook);"
                " kept.")
    else:
        log(f"   🪝 Hook kept ({got.hook_score}/10); no line needed changing.")
    _scrub(client, story, facts, fields, hook_path, language, log)
    return story


class Opening(BaseModel):
    score_before: int
    score_after: int
    paragraphs: List[str]


OPENING_PROMPT = """You edit the opening of a YouTube {what} for Pakistani and Indian viewers. YouTube measures
the first 30 seconds as the intro, and most viewers leave there: this opening decides the video.

THE FACTS (the only source of truth; add nothing that is not here):
{facts}

THE OPENING, one spoken paragraph per number (about the first {seconds} seconds):
{paragraphs}

Score the opening 1 to 10: 10 = opens cold on the most dramatic true moment, says within 30 s what is at stake
and the one question the video answers, promises the payoff, every sentence specific; 1 = a greeting, a slow
background lecture, or "is video mein hum dekhenge".
Then rewrite it to score higher: same number of paragraphs, each about the same length, keeping EVERY number and
name each paragraph has, adding no fact that is not in the facts. Never make a claim stronger than the original
says it: a hope stays a hope, a dream never becomes a duty, "reports say" stays "reports say". Sharpen by
reordering, cutting and choosing concrete words. Plain spoken {language}. Score your version honestly with the
same rubric. Never use: {banned}."""


def polish_opening(client, script, facts, what="history documentary", language="Roman Urdu in Latin letters",
                   log=print):
    """Rewrite a long video's hook scenes for the first 30 seconds, in place; code keeps a paragraph
    only if it passes ``line_ok`` and the whole rewrite scores 2+ higher. Never raises."""
    if os.environ.get("POLISH", "1") == "0" or getattr(script, "sacred", False):
        # A sacred story keeps the writer's careful wording: on the first live run (Constantinople,
        # 22-oct-2026) the polish turned rulers who "dreamed" of the city into a "sacred duty".
        return script
    scenes = list(getattr(script, "hook", None) or [])
    if not scenes:
        return script
    old = [s.line for s in scenes]
    seconds = round(sum(len(p.split()) for p in old) / 2.5)
    try:
        got = kit.ask_json(client, Opening, OPENING_PROMPT.format(
            what=what, facts=facts[:16000], seconds=seconds, language=language, banned=", ".join(BANNED),
            paragraphs="\n".join(f"{i}. {p}" for i, p in enumerate(old))), model=writer_model())
    except Exception as e:  # noqa: BLE001
        log(f"   ℹ️ Opening polish skipped ({type(e).__name__}).")
        return script
    if len(got.paragraphs) != len(old) or got.score_after < got.score_before + 2:
        log(f"   🎬 Opening kept ({got.score_before}/10).")
        return script
    cand = list(old)
    for k, (new, before) in enumerate(zip(got.paragraphs, old)):
        if re.search(r"\b(hazrat|sallallahu|allah|imam|prophet|nabi|rasool)\b", before, re.I):
            continue      # a paragraph about faith keeps the writer's checked wording
        if line_ok(new, before, facts):
            cand[k] = new.strip()
    kept = sum(1 for a, b in zip(cand, old) if a != b)
    if not kept:
        log(f"   🎬 Opening kept ({got.score_before}/10): no rewrite passed the checks.")
        return script
    # The rewriter's own 6 -> 9 meant little: on 22-oct-2026 it swapped a real question for
    # "Yeh video dikhayegi ke...". A blind judge, shown both in shuffled order, decides.
    if not judge(client, what, "opening (about the first 30 seconds)", "\n\n".join(old), "\n\n".join(cand)):
        log(f"   ⚖️ Opening: a blind judge preferred the writer's own; kept ({got.score_before}/10).")
        return script
    for scene, text in zip(scenes, cand):
        scene.line = text
    log(f"   🎬 Opening {got.score_before}/10 -> {got.score_after}/10: {kept} of {len(old)} paragraph(s) rewritten "
        "(a blind judge agreed).")
    return script


class Lines(BaseModel):
    lines: List[str]


SCRUB_PROMPT = """Rewrite each numbered line of a YouTube Short's voice-over without the phrases named after it.
Keep its meaning, every number and name in it, about the same length, the same language ({language}).
Use only these facts: {facts}

{rows}

Return exactly {n} lines in the same order."""


def _scrub(client, story, facts, fields, hook_path, language, log=print):
    """Lines still carrying a banned phrase get one rewrite that names only their hits (a regex
    check plus a targeted fix beats asking the writer to avoid a long list)."""
    left = [(p, t, banned_hits(t)) for p, t in spoken(story, fields) if banned_hits(t)]
    if not left:
        return
    rows = "\n".join(f"{i}. {t}   (remove: {', '.join(h)})" for i, (_p, t, h) in enumerate(left))
    try:
        got = kit.ask_json(client, Lines, SCRUB_PROMPT.format(language=language, facts=facts[:6000], rows=rows,
                                                              n=len(left)), model=writer_model())
    except Exception:  # noqa: BLE001
        return
    fixed = 0
    for (path, old, _h), new in zip(left, got.lines if len(got.lines) == len(left) else []):
        if line_ok(new, old, facts, hook=path == hook_path):
            _set(story, path, new.strip())
            fixed += 1
    log(f"   🧹 Stale phrases: {fixed} of {len(left)} line(s) fixed.")


# --- titles ---------------------------------------------------------------------------------
class Titles(BaseModel):
    titles: List[str]


TITLES_PROMPT = """The title of a {what} for Pakistani and Indian viewers is: "{title}"
Write 5 DIFFERENT titles for the same video, each a different angle: the most surprising number, a
contradiction, a precise question, the result first, a two-sided "A ya B?". Rules for every title:
- 35-65 characters, {language}, sentence case, no hashtags, no "|", no emoji.
- The subject people search for (the player, team, country, person or quiz type) in the first 4 words.
- Promise something specific the video really delivers; never give the payoff away, never invent.
- Use only numbers and names from the title or these facts: {facts}"""

TITLE_CAP = 70


def _title_tail(title):
    """Split "Babar ka record #shorts" / "... | Quiz #12" into the part to rewrite and the tail kept."""
    m = re.search(r"\s*(\|\s*Quiz\s*#\d+)?(\s*#\w+)*\s*$", title or "")
    return title[:m.start()].strip(), title[m.start():].strip()


def title_ok(new, old, facts):
    new = (new or "").strip()
    if not new or not _latin(new) or banned_hits(new) or "#" in new or "|" in new:
        return False
    if not 25 <= len(new) <= TITLE_CAP or new.lower() == (old or "").lower():
        return False
    if any(len(w) > 4 and w.isupper() for w in re.findall(r"[A-Za-z]+", new)):
        return False                        # shouting words; "ODI", "T20", "IPL" pass
    if not numbers(new) <= numbers(old) | numbers(facts):
        return False
    known = (old + " " + facts).lower()
    return all(n in known for n in _names(new))


ROMAN = "Roman Urdu / Hinglish in Latin letters"


def pick_title(client, title, facts, what="YouTube Short", language=ROMAN, rnd=None, log=print):
    """A title tournament: 5 other angles, code drops those that break the rules or bring a number or
    name the Short does not have, then the blind judge (shuffled, unlabelled) must prefer a survivor to
    the first title, twice at most. The title is the one line every viewer reads before the hook."""
    if os.environ.get("POLISH", "1") == "0" or not title:
        return title
    head, tail = _title_tail(title)
    if not head:
        return title
    try:
        got = kit.ask_json(client, Titles, TITLES_PROMPT.format(what=what, title=head, language=language,
                                                                facts=(facts or "")[:4000]),
                           model=writer_model())
    except Exception:  # noqa: BLE001 — keep the first title
        return title
    room = 100 - len(tail) - 1
    seen, alive = set(), []
    for t in got.titles:
        t = re.sub(r"\s+", " ", (t or "").strip().strip('"'))
        if title_ok(t, head, facts or "") and len(t) <= room and t.lower() not in seen:
            seen.add(t.lower())
            alive.append(t)
    best = head
    for t in alive[:2]:
        if judge(client, what, "title", best, t, rnd):
            best = t
    log(f"   🏆 Title: {len(alive)} of {len(got.titles)} other angles passed the checks; "
        + (f'"{head}" -> "{best}"' if best != head else "the first title kept."))
    return f"{best} {tail}".strip()
