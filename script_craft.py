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
]

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


def short_rules(structure=None, exclude=()):
    """``structure``: a fixed shape (a match or a controversy has its own order); else one of
    STRUCTURES at random, minus the ones whose name starts with a word in ``exclude``."""
    import random
    pool = [s for s in STRUCTURES if s.split(":")[0] not in exclude] or STRUCTURES
    return SHORT_CRAFT.format(banned=", ".join(f'"{b}"' for b in BANNED),
                              structure=structure or random.choice(pool))


def long_rules():
    return LONG_CRAFT.format(banned=", ".join(f'"{b}"' for b in BANNED))


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


def _names(text):
    """Capitalised words: names, places, teams. The first word counts too ("Kohli bhi hairan"
    slipped through a check that skipped it) unless it is a common opener."""
    import subtitles
    words = re.findall(r"[A-Za-z][A-Za-z'.-]*", text or "")
    out = {w.lower().strip(".'") for w in words[1:] if w[0].isupper() and len(w) > 2}
    if words and len(words[0]) > 2 and words[0].lower() not in subtitles.SENTENCE_STARTS | OPENERS:
        out.add(words[0].lower().strip(".'"))
    return out


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
   about the same length or shorter. Return exactly {n} lines in the same order. The last line keeps its ending
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
            banned=", ".join(BANNED)), model=writer_model())
    except Exception as e:  # noqa: BLE001 — the writer's lines are fine on their own
        log(f"   ℹ️ Script polish skipped ({type(e).__name__}).")
        return story
    kept = 0
    if len(got.lines) == len(lines):
        for (path, old), new in zip(lines, got.lines):
            if new.strip() != old.strip() and line_ok(new, old, facts, hook=path == lines[0][0]):
                _set(story, path, new.strip())
                kept += 1
    hook_path, hook_old = lines[0]
    best = max((h for h in got.hooks if line_ok(h.text, hook_old, facts, hook=True)),
               key=lambda h: h.score, default=None)
    # A self-scored rubric drifts by a point or two: only a clear gain replaces the hook,
    # unless the writer's own hook is a stale opener.
    if best and (best.score >= got.hook_score + 2 or banned_hits(hook_old)):
        _set(story, hook_path, best.text.strip())
        log(f"   🪝 Hook {got.hook_score}/10 -> {best.score}/10: {best.text.strip()[:90]}")
    else:
        log(f"   🪝 Hook kept ({got.hook_score}/10).")
    log(f"   ✍️ Script polish: {kept} of {len(lines)} lines tightened.")
    _scrub(client, story, facts, fields, hook_path, language, log)
    return story


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
