"""Talking-animal cartoon comedy Shorts (owner, 5-nov-2026: "make videos better like cartoons or baby talking or
animal talking ... we need strong and solid script as well").

Research that day:
- The AI pet "micro-drama" (cats and dogs in soap-opera roles) is the format of 2025-26: "Magic Cat Daddy" on YouTube
  started it with stitched AI pictures ("PPT-style", one video 200M views); a ginger-cat episode reached ~150M; the
  episodes are under a minute, serial, and end on a twist or a cliffhanger (Tech360 24-apr-2026, Baidu Baike).
  Talking-baby "podcasts" (a baby speaking like an adult) are the other one.
- YouTube's July 2026 clarification of "inauthentic content" (Tubefilter 13-jul-2026) makes three things
  non-monetizable: templated or repetitive videos ("the same situation over and over with the same outcome",
  "image slideshows and templated storylines"), "emotionally manipulative formulas" (named: "repetitive animals in
  exaggerated distress or peril", no narrative arc), and AI personas posing as experts on health, law or money.
  So: a fixed cast with real personalities (a series, not a template), a different comic engine every episode
  (SHAPES), a full arc ending on a twist, comedy and never animal suffering (RULES), and a writers' room that
  rejects a premise too close to an earlier one.
- "Made for kids" (FTC factors, YouTube answer/9528076): animated characters are one factor among many, and
  animation that appeals to everyone is allowed as general audience. The comedy is about grown-up home life (bills,
  guests, rishtas, cricket on TV), never a lesson for children; uploads stay selfDeclaredMadeForKids False.

How a character talks with no lip-sync model (this laptop has no CUDA): each shot is one AI picture with every
mouth closed; the image model then edits ONLY the speaker's mouth open (and the eyes shut, for blinks). The
difference between the two pictures is the mouth: that patch is laid over the closed picture whenever the voice is
loud (`flaps`, 15 changes a second at most), the classic cut-out cartoon technique. A spike on 5-nov-2026 changed
0.24% of the picture, all of it the cat's mouth. The camera pushes in slowly, leans to the speaker and punches in on
the punchline; pictures are upscaled with Real-ESRGAN's anime model when it is installed.

Cost: ~6 text calls and ~14-18 pictures an episode (about $0.3-0.5 of Gemini); voices are the free edge voices,
one per character (4 Urdu voices, each pitched differently), Gemini's as the fallback.
"""
import json
import os
import random
import re
import shutil
import subprocess
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from typing import List

from pydantic import BaseModel

import framed_layout as fl
import short_kit as kit

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get("TOON_STATE_DIR") or os.path.join(ROOT, "state", "toons")
W, H = kit.OUT_W, kit.OUT_H
FPS = kit.FPS
MARGIN = 1.16              # the picture canvas is this much larger than the frame: room to push in
PUSH = 0.06                # slow push-in over a shot
PUNCH = 0.08               # extra zoom on a punchline or a shock
LEAD = 0.15                # silence before the first line (kit: Shorts lose the first second to a slow start)
GAP, SAME_GAP, BEAT = 0.16, 0.08, 0.42   # between speakers, the same speaker, and before the punchline
MIN_LINES, MAX_LINES = 8, 13
MIN_WORDS, MAX_WORDS = 60, 115
# The episode-length A/B test (my_channels EXPERIMENTS["toonlen"], TOON_LENGTH): our Shorts lose half their
# viewers by 0:07-0:12 (channel doctor, 5-nov-2026), so a shorter episode is measured, not assumed.
LENGTHS = {"long": ((MIN_LINES, MAX_LINES), (MIN_WORDS, MAX_WORDS)), "short": ((6, 10), (42, 82))}


def limits():
    """((min lines, max lines), (min words, max words)) for this job's length side."""
    return LENGTHS.get((os.environ.get("TOON_LENGTH") or "long").lower(), LENGTHS["long"])
LINE_WORDS, HOOK_WORDS = 16, 12
MIN_SHOTS, MAX_SHOTS = 3, 8

STYLE = ("3D animated family-film style: soft global illumination, warm colours, rounded friendly shapes, expressive "
         "big eyes, rich textures, gentle depth of field, vertical 9:16 frame, characters large and clearly visible. "
         "A middle-class Pakistani home and neighbourhood. No text, letters, numbers, subtitles, logos or watermarks "
         "anywhere in the picture.")

# The series bible. "voice": the free edge voice, pitched per character; "gemini": the fallback voice (its gender
# also picks the local voice). "onscreen" False: heard from another room, never drawn (no human faces to keep
# consistent; the classic cartoon device).
CAST = {
    "billo": {"name": "Billo", "what": "cat",
              "look": "a chubby orange tabby cat with big green eyes, a white heart-shaped patch on her chest and a "
                      "thin gold collar with a tiny bell",
              "role": "the house's self-declared queen: vain, dramatic, sharp-tongued, always with a clever plan "
                      "that backfires; secretly soft on Guddu",
              "voice": {"edge": "ur-PK-UzmaNeural", "pitch": "+14Hz", "rate": "+8%"}, "gemini": "Leda",
              "style": "a sassy, dramatic diva", "colour": "#F28C28"},
    "sheru": {"name": "Sheru", "what": "dog",
              "look": "a big lazy fawn-coloured desi street dog with floppy ears, a sleepy face and a red cotton "
                      "scarf tied round his neck",
              "role": "loyal, slow and always hungry; takes every word literally, so his innocent lines turn into "
                      "the punchline",
              "voice": {"edge": "ur-PK-AsadNeural", "pitch": "-8Hz", "rate": "-6%"}, "gemini": "Charon",
              "style": "a slow, sleepy, simple-hearted guy", "colour": "#B07A45"},
    "mithu": {"name": "Mithu", "what": "parrot",
              "look": "a small bright green rose-ringed parakeet with a red beak and a thin black-and-pink ring "
                      "round his neck",
              "role": "the mohalla's gossip: hears everything, repeats secrets at the worst moment, talks fast",
              "voice": {"edge": "ur-IN-SalmanNeural", "pitch": "+30Hz", "rate": "+16%"}, "gemini": "Puck",
              "style": "a fast, cheeky gossip", "colour": "#2E9E44"},
    "guddu": {"name": "Guddu", "what": "baby",
              "look": "a chubby one-year-old South Asian baby boy with big round eyes, a tuft of black hair on top "
                      "and a tiny blue striped kurta",
              "role": "a baby who talks like a tired 50-year-old uncle (bills, cricket, relatives, 'aaj kal ke "
                      "bachay'); only the animals understand him, the grown-ups hear baby noises",
              "voice": {"edge": "ur-IN-GulNeural", "pitch": "+28Hz", "rate": "+2%"}, "gemini": "Kore",
              "style": "a cute baby voice saying a grumpy old uncle's words", "colour": "#3A7BD5"},
    "ammi": {"name": "Ammi", "what": "mother", "onscreen": False,
             "look": "", "role": "the mother of the house, heard from the kitchen or another room, never seen; her "
                                 "call or her footsteps can set off or end the chaos",
             "voice": {"edge": "ur-PK-UzmaNeural", "pitch": "-6Hz", "rate": "+0%"}, "gemini": "Aoede",
             "style": "a busy Pakistani mother calling from the kitchen", "colour": "#D6457A"},
}
PLACES = {
    "courtyard": "the sunny courtyard (sehan) of an old Lahore house: a woven charpai, potted plants, a steel water "
                 "cooler, brick arches and wooden doors, a clothesline",
    "kitchen": "a small Pakistani kitchen: steel pots, a pressure cooker on a gas stove, spice jars, a roti basket, "
               "green wall tiles",
    "lounge": "the TV lounge: a floral sofa set with lace covers, a big old TV, a cricket bat in the corner, a wall "
              "clock, a tea trolley",
    "rooftop": "the flat rooftop (chhat) in golden evening light: water tanks, colourful kites in the sky, "
               "neighbouring rooftops, a few pigeons",
    "street": "the mohalla street outside: a parked rickshaw, a small general store with chips packets, tangled "
              "power cables overhead",
    "bedroom": "the family bedroom: a big bed with a printed bedsheet, a baby cot, a ceiling fan, a steel almirah",
    "gate": "the house's iron main gate with a doorbell, a motorbike parked beside it, a neem tree",
}
FRAMINGS = {"close": "close-up: the speaking character's head and shoulders fill the frame",
            "medium": "medium shot: the characters from the waist up (a small animal whole), large in the frame",
            "wide": "wide shot: the whole place, the characters smaller but clearly visible"}
EMOTIONS = ("neutral", "happy", "excited", "angry", "shocked", "sly", "sad", "tired", "scared", "proud", "confused")
# The comic engine of an episode, rotated so no two in a row share one (YouTube: "the same situation over and over").
SHAPES = {
    "backfire": "PLAN BACKFIRES: a character announces a clever plan; it goes wrong in two steps, the second worse; "
                "the last line shows who it hit hardest.",
    "literal": "MISUNDERSTANDING: one character takes a word literally; the confusion grows each line until the "
               "reveal makes sense of everything.",
    "three": "RULE OF THREE: the same thing happens three times, each bigger; the third time breaks the pattern.",
    "secret": "SECRET OUT: someone hides something; it comes out at the worst possible moment (often Mithu "
              "repeating it).",
    "uncle": "UNCLE BABY: Guddu complains like a 50-year-old uncle about something tiny; the animals answer; the "
             "twist shows why he is upset.",
    "reversal": "ROLE REVERSAL: the animals copy the grown-ups of the house (Ammi's scolding, Abbu's TV remote rule); "
                "the button turns it back on them.",
    "fakeout": "FAKE-OUT: the hook makes it sound like a disaster; the reveal is something ordinary and funny.",
    "contest": "COMPETITION: two characters fight over one thing (the best cushion, the last samosa); a third wins "
               "it.",
}
# Where premises come from (the planner picks; each a different corner of home life).
LIFE = ("load-shedding and the UPS beeping", "the gas or electricity bill", "guests arriving without warning",
        "Eid shopping or Eid money (eidi)", "wedding season and the dholki", "a cricket match on TV",
        "exam results day", "the maid's day off", "the AC remote war", "the family WhatsApp group",
        "a rishta aunty's visit", "monsoon rain and a leaking roof", "mango season", "kite flying day",
        "the doodh wala and the sabzi wala", "a new phone in the house", "Abbu's diet", "Ramzan sehri alarms",
        "the neighbour's new car", "a power cut during a match", "summer holidays homework", "the washing machine",
        "Sunday breakfast of halwa puri", "a new pet in the mohalla", "the water motor and the empty tank",
        "the house being cleaned for guests", "a broken TV remote", "online shopping parcels")
# Never, in any line, picture or premise (YouTube's distress/peril rule, advertisers, Pakistan's PECA law, the owner's
# rules for every channel).
RULES = ("an animal or the baby hurt, sick, starving, abandoned, beaten, crying in pain or in real danger; a sad "
         "tear-jerker built to make viewers cry; real people, celebrities, politicians, cricketers or brands named "
         "or made fun of; religion, sects, prayers or holy things as a joke; politics, the army, India-Pakistan "
         "fights; jokes about any ethnic group, region, caste, skin colour, weight or disability; swearing, adult "
         "or romantic content; violence beyond slapstick (a slip, a pillow, a splash); teaching children a lesson "
         "or school material (this is comedy for grown-ups and families, not a kids' show); copying any known "
         "cartoon's characters, names or catchphrases")
NON_LATIN = re.compile("[" + chr(0x0600) + "-" + chr(0x06FF) + chr(0x0900) + "-" + chr(0x097F) + "]")


def _tag_line(key):
    c = CAST[key]
    return f"- {key} = {c['name']} ({c['what']}): {c['role']}." + (f" Looks: {c['look']}." if c.get("look") else
                                                                   " Never on screen.")


def bible():
    return ("CAST (use these keys):\n" + "\n".join(_tag_line(k) for k in CAST)
            + "\nThe humans of the house (Ammi, Abbu, Dadi) are never on screen; only Ammi may speak, from off "
              "screen. Guddu can only be understood by the animals.\n"
            + "PLACES (use these keys): " + "; ".join(f"{k} = {v}" for k, v in PLACES.items()))


# ------------------------------------------------------------------ the series record

def _series_file():
    return os.path.join(STATE_DIR, "series.json")


def series():
    try:
        with open(_series_file(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def episodes():
    return [e for e in series().get("episodes") or [] if isinstance(e, dict)]


def record(ep, n, now=None, series_name="", part=1):
    data = series()
    rows = [e for e in data.get("episodes") or [] if isinstance(e, dict)]
    rows.append({"n": n, "premise": ep.premise[:200], "title": ep.title[:100], "twist": ep.twist[:200],
                 "shape": ep.shape, "cast": sorted({l.speaker for l in ep.lines}), "at": int(now or time.time()),
                 **({"series": series_name[:60], "part": part} if series_name else {}),
                 # The last lines: a part 2 opens on them (the cliffhanger).
                 "ending": [f"{CAST[l.speaker]['name']}: {l.text}" for l in ep.lines[-3:] if l.speaker in CAST]})
    data["episodes"] = rows[-200:]
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = _series_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _series_file())


def next_number():
    return max([int(e.get("n") or 0) for e in episodes()] + [0]) + 1


def _words(text):
    return {w for w in re.findall(r"[a-z]+", (text or "").lower()) if len(w) > 3}


def too_close(premise, others, limit=0.5):
    """The earlier premise this one repeats (word overlap), or None."""
    mine = _words(premise)
    for o in others:
        theirs = _words(o)
        if mine and theirs and len(mine & theirs) / len(mine | theirs) >= limit:
            return o
    return None


# ------------------------------------------------------------------ the writers' room

class Shot(BaseModel):
    place: str
    who: List[str]
    framing: str
    picture: str


class Line(BaseModel):
    shot: int
    speaker: str
    text: str
    emotion: str


class Episode(BaseModel):
    title: str
    hook_caption: str
    premise: str
    shape: str
    shots: List[Shot]
    lines: List[Line]
    twist: str
    question: str


class Pick(BaseModel):
    better: int
    notes: List[str]


class Check(BaseModel):
    ok: bool
    problems: List[str]


class Idea(BaseModel):
    premise: str
    lead: str
    shape: str
    parts: int = 1
    series: str = ""


class Ideas(BaseModel):
    ideas: List[Idea]


CRAFT = """HOW TO WRITE IT (viewers decide in 3 seconds; comedy lives in surprise and specifics):
- Line 1 is the hook, under {hook} words (3 seconds): we drop into the middle of the trouble, a conflict or an absurd
  claim ("Kisi ne meri machhli chura li hai!"), never a greeting, never introducing the characters, never "aaj".
- Pure dialogue between the characters, no narrator. {lo}-{hi} lines, {wlo}-{whi} words in all (30-42 seconds),
  each line {lw} words or fewer, short spoken sentences.
- Every line moves the story or lands a joke. Each character sounds like the bible says (Billo dramatic, Sheru
  literal and hungry, Mithu fast gossip, Guddu a grumpy uncle in a baby's body).
- Escalate: each beat bigger than the last; a line that only repeats an earlier one is cut.
- Specific beats generic: name the dish, the object, the price, the relative, the time ("raat ke 2 baje",
  "Phupho ka biryani wala dabba"), real Pakistani/Indian home life.
- The twist comes in the last two lines and changes how we see the start. The LAST line is the punchline: short (a
  reaction or 3-8 words), so the Short ends on the laugh and a replay feels natural. No moral, no outro, no "like
  aur subscribe".
- Everyday Roman Urdu / Hinglish in Latin letters, as said at home in Lahore, Karachi or Delhi; simple words Indians
  understand too. Laugh words sparingly.
- Comedy shape for this episode: {shape}
- Never use these stale phrases: {banned}."""

SHOT_RULES = """SHOTS (each picture is drawn by an image model, then the speaker's mouth is animated):
- {slo}-{shi} shots; every line names its shot by number (0-based); consecutive lines may share a shot.
- A speaker must be in the "who" of their line's shot, except ammi (never on screen: her line's shot shows who
  reacts). 1-2 characters per shot (3 only in a wide shot); "who" in left-to-right order.
- framing: close (punchlines and big reactions), medium (most lines) or wide (the opening or a reveal).
- picture: one English sentence of what we see: pose, action, props, expression, where they look. The characters
  only; no humans. Do not describe mouths (they are drawn closed and animated later)."""

WRITE_PROMPT = """You are the head writer of an original animated comedy series of YouTube Shorts and Instagram Reels for
Pakistani and Indian viewers: talking animals and a talking baby in one middle-class Lahore home. Episode {n}.

{bible}

Earlier episodes (for continuity; you may call back to one, never retell one):
{earlier}

THIS EPISODE'S PREMISE: {premise}
{part_note}
{craft}

{shots}

NEVER: {rules}.

Return: title (Roman Urdu, 4-9 words, the situation that makes people click, may end with one emoji), hook_caption
(2-6 words on screen at the start so it works with the sound off), premise (one sentence), shape (the key: {shape_key}),
shots, lines (speaker key, text, emotion from {emotions}), twist (one sentence: what the twist reveals), question (a
comment question with a one-word answer people will argue about, Roman Urdu).
{fixes}"""

JUDGE_PROMPT = """Two drafts of the same episode of an animated comedy Short for Pakistani and Indian viewers.
Which one gets more people to watch to the end, laugh and replay? Judge: the hook in the first 3 seconds, a real
escalation, a twist nobody saw coming that still makes sense, the last line being the laugh, specific desi details,
each character sounding like themselves. Answer better = 1 or 2, then up to 5 notes: concrete fixes for the better
draft (a sharper hook, a funnier last line, a line to cut, a missed callback).

DRAFT 1:
{one}

DRAFT 2:
{two}"""

PUNCH_PROMPT = """You punch up an episode of an animated comedy Short before it is drawn. Keep the premise, the cast,
the shots and their numbering, and the twist. Make the hook grab harder in 3 seconds, make the last line the
biggest laugh (short), cut or tighten any line that is not a joke or a turn, keep each character's voice, keep
everything in Roman Urdu. Apply these notes from the story editor:
{notes}

{craft}

Return the whole episode in the same shape.

THE EPISODE:
{episode}"""

CHECK_PROMPT = """You check an episode of an animated comedy Short (talking animals and a talking baby in a Pakistani
home) before it is published on YouTube and Instagram. Report a problem only for something in the script below.

Problems:
- anything in this list: {rules};
- an animal or the baby in exaggerated distress or peril, or a plot built to make viewers cry (YouTube refuses to
  monetize "repetitive animals in exaggerated distress or peril");
- no story arc: no clear set-up, escalation and twist, or the last line is not a payoff;
- a line a Pakistani family would find offensive.
ok = true when there is nothing.

THE EPISODE:
{episode}"""

IDEAS_PROMPT = """Today is {today}. Plan the next {count} episodes of an original animated comedy series of YouTube
Shorts and Instagram Reels for Pakistani and Indian viewers: talking animals and a talking baby in one middle-class
Lahore home.

{bible}

Each idea is ONE premise sentence: who wants what, what stands in the way, and the comic engine (it may hint at the
twist). Comedy from everyday desi home life, for example: {life}. A same-day event everyone talks about (a big
match, a holiday, the weather) can be the setting, never a real person.
- Every idea uses a different shape from: {shapes}; and a different lead character; spread the cast.
- About one idea in four is a TWO-PART story (parts = 2, with a series name of 2-4 words): part 1 ends on a
  cliffhanger, part 2 pays it off. The others have parts = 1 and no series name.
- Never repeat or closely resemble these earlier premises: {avoid}
{best}{worst}{requests}{notes}{trends}
NEVER: {rules}.
Return ideas: premise (English or Roman Urdu), lead (a cast key), shape (a shape key)."""


def script_text(ep):
    out = [f"TITLE: {ep.title}", f"HOOK CAPTION: {ep.hook_caption}", f"PREMISE: {ep.premise}", f"SHAPE: {ep.shape}"]
    out += [f"SHOT {k}: [{s.framing}] {s.place}; {', '.join(s.who)}: {s.picture}" for k, s in enumerate(ep.shots)]
    out += [f"{k + 1}. (shot {l.shot}) {l.speaker} [{l.emotion}]: {l.text}" for k, l in enumerate(ep.lines)]
    out += [f"TWIST: {ep.twist}", f"QUESTION: {ep.question}"]
    return "\n".join(out)


def tidy(ep):
    """Keys lower-cased, unknown emotions/framings set to the default, empty lines dropped."""
    for s in ep.shots:
        s.place = (s.place or "").strip().lower()
        s.framing = (s.framing or "").strip().lower()
        if s.framing not in FRAMINGS:
            s.framing = "medium"
        s.who = [w.strip().lower() for w in s.who if (w or "").strip()]
    lines = []
    for l in ep.lines:
        l.speaker = (l.speaker or "").strip().lower()
        l.text = re.sub(r"\s+", " ", (l.text or "")).strip()
        l.emotion = (l.emotion or "").strip().lower()
        if l.emotion not in EMOTIONS:
            l.emotion = "neutral"
        if l.text:
            lines.append(l)
    ep.lines = lines
    ep.shape = (ep.shape or "").strip().lower()
    if ep.shape not in SHAPES:
        # The writer sometimes returns the shape's description ("secret out: someone hides...", episode 3).
        ep.shape = next((k for k, v in SHAPES.items()
                         if ep.shape.startswith(k) or ep.shape.startswith(v.split(":")[0].lower())), ep.shape[:20])
    return ep


def problems(ep):
    """What the code finds wrong with a script: [] means it can be drawn and voiced."""
    import script_craft as craft
    out = []
    n = len(ep.lines)
    (lo, hi), (wlo, whi) = limits()
    if not lo <= n <= hi:
        out.append(f"it has {n} lines: write {lo}-{hi}")
    if not MIN_SHOTS <= len(ep.shots) <= MAX_SHOTS:
        out.append(f"it has {len(ep.shots)} shots: use {MIN_SHOTS}-{MAX_SHOTS}")
    words = sum(len(l.text.split()) for l in ep.lines)
    if not wlo <= words <= whi:
        out.append(f"the dialogue has {words} words: write {wlo + 8}-{whi - 10}")
    if ep.lines and len(ep.lines[0].text.split()) > HOOK_WORDS:
        out.append(f"the hook (line 1) has {len(ep.lines[0].text.split())} words: {HOOK_WORDS} or fewer")
    used = set()
    for k, s in enumerate(ep.shots):
        if s.place not in PLACES:
            out.append(f"shot {k} place '{s.place}' is not one of {', '.join(PLACES)}")
        bad = [w for w in s.who if w not in CAST or CAST[w].get("onscreen") is False]
        if bad:
            out.append(f"shot {k} shows {', '.join(bad)}: only on-screen cast keys")
        if not 1 <= len(s.who) <= (3 if s.framing == "wide" else 2):
            out.append(f"shot {k} has {len(s.who)} characters: 1-2 (3 only in a wide shot)")
        if len(set(s.who)) != len(s.who):
            out.append(f"shot {k} lists a character twice")
    for k, l in enumerate(ep.lines):
        tag = f"line {k + 1}"
        if l.speaker not in CAST:
            out.append(f"{tag}: speaker '{l.speaker}' is not a cast key")
            continue
        if not 0 <= l.shot < len(ep.shots):
            out.append(f"{tag}: shot {l.shot} does not exist")
            continue
        used.add(l.shot)
        if CAST[l.speaker].get("onscreen") is not False and l.speaker not in ep.shots[l.shot].who:
            out.append(f"{tag}: {l.speaker} speaks but is not in shot {l.shot}")
        if len(l.text.split()) > LINE_WORDS:
            out.append(f"{tag} has {len(l.text.split())} words: {LINE_WORDS} or fewer")
        if NON_LATIN.search(l.text):
            out.append(f"{tag} is not in Latin letters")
        hits = craft.banned_hits(l.text)
        if hits:
            out.append(f"{tag} uses stale phrases: {', '.join(hits)}")
    unused = [k for k in range(len(ep.shots)) if k not in used]
    if unused:
        out.append(f"shots {unused} have no line: drop them or give them a line")
    if len({l.speaker for l in ep.lines}) < 2:
        out.append("only one character speaks: it is a dialogue between two or more")
    if NON_LATIN.search(ep.title + " " + ep.hook_caption + " " + ep.question):
        out.append("the title, hook caption or question is not in Latin letters")
    return out


def _model():
    import script_craft as craft
    return craft.writer_model()


def _craft(shape):
    import script_craft as craft
    (lo, hi), (wlo, whi) = limits()
    return CRAFT.format(hook=HOOK_WORDS, lo=lo, hi=hi - 1, wlo=wlo + 10, whi=whi - 15,
                        lw=LINE_WORDS - 2, shape=SHAPES.get(shape, shape),
                        banned=", ".join(craft.BANNED[:40])).replace("(30-42 seconds)", "(25-32 seconds)"
                                                                      if (lo, hi) != (MIN_LINES, MAX_LINES) else
                                                                      "(30-42 seconds)")


def _earlier(rows, limit=6):
    rows = rows[-limit:]
    return "\n".join(f"- Ep {e.get('n')}: {e.get('premise')} (twist: {e.get('twist')})" for e in rows) or "- none yet"


def pick_shapes(rows, wanted=None, rnd=None):
    """Two shapes for the two drafts: the planner's first, none of the last three episodes' if avoidable."""
    rnd = rnd or random.Random()
    recent = [e.get("shape") for e in rows[-3:]]
    pool = [s for s in SHAPES if s not in recent and s != wanted] or [s for s in SHAPES if s != wanted]
    rnd.shuffle(pool)
    first = wanted if wanted in SHAPES else pool.pop(0)
    return [first, pool[0] if pool else first]


def part_note(part=None):
    """The writer's note for a two-part story: ``part`` = (k, of, the earlier part's last lines)."""
    if not part or part[1] < 2:
        return ""
    k, of, before = part
    if k == 1:
        return (f"\nTHIS IS PART 1 OF {of}. Do NOT resolve it: the last line is a CLIFFHANGER (a shock, a reveal "
                "half seen, a door opening), so viewers come back for part 2. Every other rule holds; the cliffhanger "
                "takes the punchline's place. The title ends with \"(Part 1)\".\n")
    return (f"\nTHIS IS PART {k} OF {of}. Part {k - 1} ended like this:\n" + "\n".join(f"  {x}" for x in before)
            + "\nLine 1 replays that cliffhanger as the hook in under 10 words (a new viewer must get it at once), "
              f"then the story pays it off with the twist. The title ends with \"(Part {k})\".\n")


def series_part(name, k, of, rows=None):
    """(k, of, ending lines of part k-1) for the writer, or None for a one-part episode."""
    if not name or of < 2:
        return None
    rows = episodes() if rows is None else rows
    before = next((e.get("ending") or [] for e in reversed(rows)
                   if e.get("series") == name and int(e.get("part") or 0) == k - 1), [])
    return (k, of, before)


def draft(client, premise, shape, n, rows, fixes="", part=None):
    ep = kit.ask_json(client, Episode, WRITE_PROMPT.format(
        n=n, bible=bible(), earlier=_earlier(rows), premise=premise, craft=_craft(shape), part_note=part_note(part),
        shots=SHOT_RULES.format(slo=MIN_SHOTS + 1, shi=MAX_SHOTS - 1), rules=RULES, shape_key=shape,
        emotions=", ".join(EMOTIONS), fixes=fixes), model=_model())
    return tidy(ep)


def write(client, premise, shape=None, rows=None, n=None, log=print, rnd=None, part=None):
    """The episode that passed the code gates and the safety check, or raises. ``part``: (k, of, ending lines) of a
    two-part story (series_part)."""
    rows = episodes() if rows is None else rows
    n = n or next_number()
    shapes = pick_shapes(rows, shape, rnd)
    with ThreadPoolExecutor(max_workers=2) as pool:
        drafts = list(pool.map(lambda s: _safe(lambda: draft(client, premise, s, n, rows, part=part)), shapes))
    drafts = [d for d in drafts if d is not None]
    if not drafts:
        raise RuntimeError("The writers' room returned no script (the network or Gemini is down); made again later.")
    good = [d for d in drafts if not problems(d)]
    if not good:
        first = drafts[0]
        log(f"   ⚠️ Both drafts failed the script checks ({len(problems(first))} problem(s)); rewriting once.")
        fixed = draft(client, premise, first.shape or shapes[0], n, rows, part=part,
                      fixes="\nFix these problems of the last version:\n- " + "\n- ".join(problems(first)[:12]))
        if problems(fixed):
            raise RuntimeError("The script failed the checks twice: " + "; ".join(problems(fixed)[:4]))
        good = [fixed]
    chosen, notes = good[0], []
    if len(good) == 2:
        try:
            pick = kit.ask_json(client, Pick, JUDGE_PROMPT.format(one=script_text(good[0]), two=script_text(good[1])),
                                model=_model())
            chosen = good[1] if pick.better == 2 else good[0]
            notes = [x for x in pick.notes if x][:5]
        except Exception as e:  # noqa: BLE001 — the first good draft goes on
            log(f"   ⚠️ The draft judge failed ({type(e).__name__}); keeping draft 1.")
    log(f"   ✍️ Draft chosen: {chosen.shape} ({len(chosen.lines)} lines, {len(chosen.shots)} shots).")
    if os.environ.get("TOON_PUNCH", "1") != "0":
        try:
            punched = tidy(kit.ask_json(client, Episode, PUNCH_PROMPT.format(
                notes="\n".join(f"- {x}" for x in notes) or "- (none: use your judgement)",
                craft=_craft(chosen.shape) + part_note(part) + "\n" + SHOT_RULES.format(
                    slo=MIN_SHOTS + 1, shi=MAX_SHOTS - 1)
                + f"\nLine 1 stays at {HOOK_WORDS} words or fewer, and every speaker stays in the shot their line "
                  "names (the first episode's punch-up broke both, 5-nov-2026).",
                episode=script_text(chosen)), model=_model()))
            left = problems(punched)
            if left or len(punched.shots) != len(chosen.shots):
                log(f"   ✂️ Punch-up dropped ({'; '.join(left[:2]) or 'it changed the shots'}).")
            else:
                chosen = punched
        except Exception as e:  # noqa: BLE001
            log(f"   ⚠️ Punch-up failed ({type(e).__name__}); the chosen draft goes on.")
    for attempt in range(2):
        cliff = ("\nThis is part 1 of a two-part story: its cliffhanger ending IS its payoff."
                 if part and part[0] == 1 and part[1] > 1 else "")
        check = kit.ask_json(client, Check, CHECK_PROMPT.format(rules=RULES, episode=script_text(chosen)) + cliff,
                             model=_model())
        if check.ok:
            return chosen
        log(f"   ⚠️ The script check found {len(check.problems)} problem(s): {'; '.join(check.problems[:2])[:200]}")
        if attempt:
            break
        fixed = draft(client, premise, chosen.shape, n, rows, part=part, fixes="\nFix these problems found by the editor:\n- "
                      + "\n- ".join(check.problems[:10]))
        if problems(fixed):
            break
        chosen = fixed
    raise RuntimeError("The episode did not pass the script check twice; skipped to be safe.")


def _safe(fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — the other draft still counts
        print(f"   ⚠️ A draft failed ({type(e).__name__}: {str(e)[:120]}).")
        return None


def channel_ideas(client, count=4, avoid=(), best=(), worst=(), requests=(), notes=""):
    """The next ``count`` premises: [{"text", "lead", "shape", "kind": "toons"}]."""
    from datetime import datetime
    rows = episodes()
    past = [str(a) for a in avoid][-60:] + [e.get("premise", "") for e in rows][-60:]
    hint = ""
    try:
        import trends
        hint = trends.searches_hint(12)
    except Exception:  # noqa: BLE001 — the planner works without it
        pass
    life = random.sample(LIFE, min(12, len(LIFE)))
    got = kit.ask_json(client, Ideas, IDEAS_PROMPT.format(
        today=f"{datetime.now():%A %d %B %Y}", count=count + 2, bible=bible(), life="; ".join(life),
        shapes="; ".join(f"{k} = {v.split(':')[0]}" for k, v in SHAPES.items()),
        avoid="; ".join(p[:120] for p in past[-40:]) or "none",
        best=("Viewers liked these: " + "; ".join(map(str, best[:6])) + "\n") if best else "",
        worst=("These flopped (different angles): " + "; ".join(map(str, worst[:6])) + "\n") if worst else "",
        requests=("Viewers asked for (use only what fits the rules): " + "; ".join(map(str, requests[:6])) + "\n")
        if requests else "",
        notes=f"The owner's wishes: {notes}\n" if notes else "",
        trends=(hint + "\n") if hint else "", rules=RULES), model=_model())
    out, seen = [], list(past)
    for it in got.ideas:
        text = re.sub(r"\s+", " ", it.premise or "").strip()[:220]
        if len(text) < 15 or too_close(text, seen):
            continue
        seen.append(text)
        row = {"text": text, "lead": (it.lead or "").strip().lower(), "shape": (it.shape or "").strip().lower(),
               "kind": "toons"}
        name = re.sub(r"[^A-Za-z0-9 ]", "", it.series or "").strip()[:40]
        if it.parts == 2 and name and os.environ.get("TOON_TWO_PARTS", "1") != "0":
            # Part 2 follows straight after in the queue; the upload links part 1 to it (series / series_part).
            out.append({**row, "series": name, "part": 1, "parts": 2})
            out.append({**row, "text": f"{text} (part 2)", "series": name, "part": 2, "parts": 2})
        else:
            out.append(row)
    # A two-part story is never cut in half by the count.
    keep = out[:count]
    if keep and keep[-1].get("part") == 1 and len(out) > count:
        keep.append(out[count])
    return keep


# ------------------------------------------------------------------ pictures

def _image(client, contents, out, size="1K", aspect="9:16"):
    """One picture (9:16 unless ``aspect``) from the image model, saved as PNG; raises when none comes back."""
    import io
    from google.genai import types
    from PIL import Image
    model = os.environ.get("GEMINI_IMAGE_MODEL") or "gemini-3.1-flash-image"
    last = None
    for attempt in range(3):
        try:
            import ai_fallback
            with ai_fallback.allow_images():        # the one channel the paid backup draws for (7-nov-2026)
                r = client.models.generate_content(
                    model=model, contents=contents,
                    config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"],
                                                       image_config=types.ImageConfig(aspect_ratio=aspect,
                                                                                      image_size=size)))
            for part in r.parts or []:
                if part.inline_data is not None and part.inline_data.data:
                    Image.open(io.BytesIO(part.inline_data.data)).convert("RGB").save(out)
                    return out
            try:
                said = (r.text or "").strip()
            except Exception:  # noqa: BLE001 — no text part either
                said = ""
            last = RuntimeError("the image model returned no picture" + (f": {said[:160]}" if said else ""))
        except Exception as e:  # noqa: BLE001 — a transient error gets another try
            last = e
            if "credits are depleted" in str(e) or not any(
                    m in f"{type(e).__name__} {e}" for m in kit.TRANSIENT + ("429", "500", "503")):
                break
        time.sleep(4 * (attempt + 1))
    raise last


def cast_dir():
    return os.path.join(STATE_DIR, "cast")


def cast_ref(client, key):
    """The character's reference picture, drawn once and kept (the owner may replace the file)."""
    path = os.path.join(cast_dir(), f"{key}.png")
    if os.path.isfile(path):
        return path
    os.makedirs(cast_dir(), exist_ok=True)
    c = CAST[key]
    tmp = path + ".new.png"
    _image(client, [f"{STYLE}\nCharacter reference sheet for an animated series: {c['name']}, {c['look']}. One "
                    f"character alone, full body, standing in a relaxed three-quarter pose, facing the camera, mouth "
                    f"closed, eyes open, on a plain light grey studio background."], tmp)
    os.replace(tmp, path)
    return path


def _side(k, n):
    return ("" if n == 1 else ["on the left", "on the right"][k] if n == 2 else
            ["on the left", "in the middle", "on the right"][min(k, 2)])


SIMPLE_PICTURE = "the characters together in this place, friendly lively expressions, looking at each other"


def shot_prompt(ep, k, simple=False):
    """The picture prompt of shot k; ``simple``: the shot's own action left out (the fallback when the image model
    returned nothing for it, episode 4's first shot, 5-nov-2026)."""
    s = ep.shots[k]
    who = "; ".join(f"{CAST[w]['name']} the {CAST[w]['what']} {_side(i, len(s.who))} (reference picture {i + 1}: "
                    f"{CAST[w]['look']})" for i, w in enumerate(s.who))
    return (f"{STYLE}\nPlace: {PLACES.get(s.place, s.place)}.\nFraming: {FRAMINGS[s.framing]}.\n"
            f"Characters, left to right: {who}.\nWhat we see: {SIMPLE_PICTURE if simple else s.picture}\n"
            "Keep every character exactly like their reference picture: same species, colours, markings, collar, "
            "scarf and clothes, same proportions. Every character's MOUTH IS CLOSED and the eyes are open. Only these "
            "characters; no humans, no other animals.")


def draw_shot(client, ep, k, refs, out):
    from PIL import Image
    pics = []
    for w in ep.shots[k].who:
        with Image.open(refs[w]) as im:
            pics.append(im.convert("RGB").copy())
    try:
        return _image(client, pics + [shot_prompt(ep, k)], out)
    except RuntimeError as e:
        if "no picture" not in str(e):
            raise
        # One shot the model will not draw must not cost the episode: the same characters and place, plainer.
        print(f"   ⚠️ Shot {k} came back without a picture ({str(e)[:140]}); drawing a simpler version.")
        return _image(client, pics + [shot_prompt(ep, k, simple=True)], out)


def variant_prompt(ep, k, who, kind):
    s = ep.shots[k]
    c = CAST[who]
    where = _side(s.who.index(who), len(s.who)) if who in s.who else ""
    part = ("beak open wide, as if squawking a word" if c["what"] == "parrot" else
            "mouth open wide in the middle of a word, as if saying 'aah', teeth and tongue visible")
    change = (f"Change ONLY {c['name']} the {c['what']}{' ' + where if where else ''}: {part}." if kind == "mouth" else
              f"Change ONLY {c['name']} the {c['what']}{' ' + where if where else ''}: eyes fully closed, as in the "
              "middle of a blink.")
    return (f"Edit this exact image. {change} Keep everything else exactly identical: the same pose, the same "
            "framing, the same lighting and colours, the same background, every other character unchanged. Do not "
            "move the camera, do not redraw the picture.")


def only_mouths(problem):
    """True when the picture check's problem is only about an open mouth (fixed by an edit, not a redraw)."""
    p = (problem or "").lower()
    return "mouth" in p and not any(w in p for w in ("missing", "human", "person", "text", "letter", "extra",
                                                     "different", "species", "wrong", "not the"))


CLOSE_PROMPT = ("Edit this exact image. Change ONLY the mouths: every character's mouth (or beak) is CLOSED, lips "
                "together, a closed mouth that keeps their expression (a closed frown, a closed smile). Keep everything "
                "else exactly identical: the same pose, eyes, framing, lighting, colours and background. Do not move "
                "the camera, do not redraw the picture.")


def close_mouths(client, ep, k, path):
    """The shot's picture with every mouth closed, in place, when the edit changed only a small patch."""
    from PIL import Image
    with Image.open(path) as im:
        ref = im.convert("RGB").copy()
    tmp = path + ".closed.png"
    _image(client, [ref, CLOSE_PROMPT], tmp)
    mask, _c = mask_of(_load(path), _load(tmp))
    if mask is None:
        os.remove(tmp)
        return None
    os.replace(tmp, path)
    return path


def draw_variant(client, ep, k, base, who, kind, out):
    from PIL import Image
    with Image.open(base) as im:
        ref = im.convert("RGB").copy()
    return _image(client, [ref, variant_prompt(ep, k, who, kind)], out)


def mask_of(base, other, expect=None):
    """The changed patch between two pictures of one shot, as a soft mask (float32 0..1 at the base's size), with
    its centre (x, y); or (None, None) when the edit redrew the picture, changed nothing, or changed the wrong
    place. ``expect``: (lo, hi) share of the width the patch's centre must fall in (which character it is)."""
    import cv2
    import numpy as np
    a = base.astype(np.int16)
    b = other.astype(np.int16)
    if a.shape != b.shape:
        return None, None
    d = np.abs(a - b).max(axis=2)
    if float(np.median(d)) > 12:
        return None, None                  # the whole picture moved or was redrawn
    m = (d > 38).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    n, labels, stats, cents = cv2.connectedComponentsWithStats(m, 8)
    if n < 2:
        return None, None
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    hgt, wid = m.shape
    reach = 0.22 * wid
    keep = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= 0.15 * stats[big, cv2.CC_STAT_AREA]
            and np.hypot(*(cents[i] - cents[big])) <= reach]
    patch = np.isin(labels, keep)
    share = float(patch.mean())
    if not 0.0002 <= share <= 0.06 or stats[big, cv2.CC_STAT_WIDTH] > 0.5 * wid:
        return None, None
    ys, xs = np.nonzero(patch)
    cx, cy = float(xs.mean()), float(ys.mean())
    if expect and not expect[0] <= cx / wid <= expect[1]:
        return None, None
    grow = max(5, round(wid * 0.012))
    soft = cv2.dilate(patch.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1,) * 2))
    soft = cv2.GaussianBlur(soft, (0, 0), grow * 0.8)
    return soft.astype(np.float32) / 255.0, (cx, cy)


def expect_for(n, k):
    """Where character k of n (left to right) should be: a share of the width."""
    if n <= 1:
        return None
    return [(0.0, 0.62), (0.38, 1.0)][k] if n == 2 else [(0.0, 0.45), (0.25, 0.75), (0.55, 1.0)][min(k, 2)]


class LookItem(BaseModel):
    n: int
    ok: bool
    problem: str


class Look(BaseModel):
    shots: List[LookItem]


LOOK_PROMPT = """The first pictures are the reference pictures of an animated series' characters, in this order:
{refs}. Then come {count} numbered scene pictures. For each scene say ok = false, with the problem in a few words,
if: a character it must show is missing or clearly not the one in the reference (another species, colour, markings
or clothes), it shows a human or an extra animal, it has any text or letters, or any character's mouth is open.
Scenes and who must be in each:
{scenes}"""


def look_check(client, ep, refs, files):
    """{shot: problem} for the pictures to draw again (one vision call); {} when all pass or the call fails."""
    from PIL import Image
    keys = [w for w in CAST if w in refs]
    parts = []
    for w in keys:
        with Image.open(refs[w]) as im:
            parts.append(im.convert("RGB").resize((256, 456)))
    for k in range(len(ep.shots)):
        with Image.open(files[k]) as im:
            parts.append(im.convert("RGB").resize((384, 684)))
    scenes = "\n".join(f"{k + 1}: {', '.join(CAST[w]['name'] for w in s.who)}" for k, s in enumerate(ep.shots))
    try:
        got = kit.ask_json(client, Look, parts + [LOOK_PROMPT.format(
            refs=", ".join(CAST[w]["name"] for w in keys), count=len(ep.shots), scenes=scenes)])
    except Exception as e:  # noqa: BLE001 — the pictures go on unchecked
        print(f"   ⚠️ Picture check failed ({type(e).__name__}); the pictures go on unchecked.")
        return {}
    return {it.n - 1: it.problem for it in got.shots if not it.ok and 1 <= it.n <= len(ep.shots)}


# ------------------------------------------------------------------ timing: mouths and blinks

def envelope(wav, fps=FPS):
    """Loudness per video frame of a voice file (RMS over 1.5 frames)."""
    import numpy as np
    with wave.open(wav, "rb") as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    hop = sr / fps
    win = max(1, int(hop * 1.5))
    frames = int(np.ceil(len(data) / hop))
    out = np.zeros(frames, dtype=np.float32)
    for i in range(frames):
        a = max(0, int(i * hop - win / 4))
        seg = data[a:a + win]
        out[i] = float(np.sqrt(np.mean(seg * seg))) if len(seg) else 0.0
    return out


def flaps(env, open_at=0.5, close_at=0.28, hold=2):
    """Mouth open (True) per frame: open when the voice is loud, closed in its dips, each state held for at least
    ``hold`` frames (so 15 changes a second at most at 30 fps)."""
    import numpy as np
    env = np.asarray(env, dtype=np.float32)
    loud = env[env > 1e-3]
    ref = float(np.percentile(loud, 85)) if len(loud) else 1.0
    state, run, out = False, hold, []
    for v in env / max(ref, 1e-6):
        want = True if v >= open_at else False if v <= close_at else state
        if want != state and run >= hold:
            state, run = want, 0
        run += 1
        out.append(state)
    return out


def blinks(t0, t1, rnd, every=(2.4, 4.6), first=(0.6, 1.8), length=4 / FPS):
    """[(start, end)] blink windows inside a shot."""
    out, t = [], t0 + rnd.uniform(*first)
    while t + length < t1:
        out.append((t, t + length))
        t += rnd.uniform(*every)
    return out


def timeline(lines, said):
    """Line windows [(k, start, end, wav)] and the body's end: speech gaps by who speaks next, a beat before the
    punchline."""
    t, rows = LEAD, []
    for k, (line, (path, secs)) in enumerate(zip(lines, said)):
        secs = secs or max(1.5, len(line.text.split()) / 2.8)
        rows.append((k, t, t + secs, path))
        nxt = lines[k + 1] if k + 1 < len(lines) else None
        if nxt is None:
            t += secs
        elif k + 1 == len(lines) - 1:
            t += secs + BEAT
        else:
            t += secs + (SAME_GAP if nxt.speaker == line.speaker else GAP)
    return rows, t + 0.5


def shot_windows(ep, rows, total):
    """[(shot index, start, end)] in play order; a shot starts at its first line (the first at 0) and runs until
    the next shot's line; a shot that comes back later gets a new window."""
    out = []
    for k, a, _b, _p in rows:
        s = ep.lines[k].shot
        if out and out[-1][0] == s:
            continue
        start = 0.0 if not out else a - 0.05
        if out:
            out[-1] = (out[-1][0], out[-1][1], start)
        out.append((s, start, total))
    return out


# ------------------------------------------------------------------ render

def _ease(u):
    import math
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


class ShotArt:
    """One shot's pictures on the push-in canvas: the closed picture, then each speaker's open mouth and the blink
    as masks over it."""

    def __init__(self, base, mouths=None, blink=None, scale=1.0):
        import cv2
        import numpy as np
        self.cv2, self.np = cv2, np
        cw, ch = round(W * MARGIN), round(H * MARGIN)
        self.size = (cw, ch)
        s = max(cw / base.shape[1], ch / base.shape[0])
        self.fit = s
        self.offset = ((base.shape[1] * s - cw) / 2, (base.shape[0] * s - ch) / 2)
        self.base = self._fit(base)
        self.mouths = {}
        for who, (pic, mask, centre) in (mouths or {}).items():
            self.mouths[who] = (self._fit(pic), self._fit_mask(mask), self._point(centre, scale))
        self.blink = None
        if blink:
            who, pic, mask = blink
            self.blink = (who, self._fit(pic), self._fit_mask(mask))
        self.cache = {}
        self.depth = None              # parallax depth on the canvas, made on first use (False: none)

    def _fit(self, im):
        cv2 = self.cv2
        big = cv2.resize(im, (round(im.shape[1] * self.fit), round(im.shape[0] * self.fit)), interpolation=cv2.INTER_AREA)
        x, y = round(self.offset[0]), round(self.offset[1])
        return big[y:y + self.size[1], x:x + self.size[0]].copy()

    def _fit_mask(self, m):
        cv2 = self.cv2
        big = cv2.resize(m, (round(m.shape[1] * self.fit), round(m.shape[0] * self.fit)), interpolation=cv2.INTER_LINEAR)
        x, y = round(self.offset[0]), round(self.offset[1])
        return big[y:y + self.size[1], x:x + self.size[0]][..., None]

    def _point(self, p, scale):
        return (p[0] * scale * self.fit - self.offset[0], p[1] * scale * self.fit - self.offset[1])

    def focus(self, who):
        return self.mouths[who][2] if who in self.mouths else None

    def picture(self, talking=None, blinking=False):
        key = (talking if talking in self.mouths else None, bool(blinking and self.blink))
        if key in self.cache:
            return self.cache[key]
        np = self.np
        im = self.base.astype(np.float32)
        if key[1]:
            _w, pic, m = self.blink
            im = im * (1 - m) + pic.astype(np.float32) * m
        if key[0]:
            pic, m, _c = self.mouths[key[0]]
            im = im * (1 - m) + pic.astype(np.float32) * m
        out = np.clip(im + 0.5, 0, 255).astype(np.uint8)
        if len(self.cache) < 8:
            self.cache[key] = out
        return out


def camera(t, a, b, punch_at=None, shake_at=None, focus=None, canvas=None):
    """The canvas-to-frame transform at time t of a shot shown from a to b: (zoom, centre x, centre y)."""
    import math
    cw, ch = canvas or (round(W * MARGIN), round(H * MARGIN))
    z = 1.0 + PUSH * _ease((t - a) / max(0.5, b - a))
    if punch_at is not None and t >= punch_at:
        z += PUNCH * _ease((t - punch_at) / 0.12)
    cx, cy = cw / 2, ch / 2
    if focus:
        lean = 0.35 * _ease((t - a) / 1.2)
        cx += lean * (focus[0] - cx)
        cy += lean * (focus[1] - cy)
    if shake_at is not None and 0 <= t - shake_at < 0.3:
        k = 1 - (t - shake_at) / 0.3
        cx += 7 * k * math.sin(83 * t)
        cy += 5 * k * math.cos(71 * t)
    s = z / MARGIN                       # canvas pixels to frame pixels
    hw, hh = W / 2 / s, H / 2 / s        # half the view, in canvas pixels
    # No room to move (the whole canvas in view, give or take the rounding of its size): centred.
    cx = cw / 2 if 2 * hw >= cw - 1 else min(max(cx, hw), cw - hw)
    cy = ch / 2 if 2 * hh >= ch - 1 else min(max(cy, hh), ch - hh)
    return z, cx, cy


DEPTH_AMP = 0.010            # the nearest pixels drift this share of the canvas width more than the farthest


def _depth_fn():
    """parallax.depth_of when the depth model is installed (TOON_PARALLAX=0 / PARALLAX=0 off), else None."""
    if os.environ.get("TOON_PARALLAX", "1") == "0":
        return None
    try:
        import parallax
        return parallax.depth_of if parallax.available() else None
    except Exception:  # noqa: BLE001
        return None


def render_track(plan, total, out, fps=FPS, log=print, depth_fn=None):
    """The picture track (no sound, no text) as an mp4: ``plan`` is [{"art": ShotArt, "a", "b", "talk": [(start,
    end, who, [bool per frame])], "blinks": [(s, e)], "punch": t|None, "shake": t|None, "focus": who|None}]."""
    import cv2
    import numpy as np
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", out]
    depth_fn = _depth_fn() if depth_fn is None else depth_fn
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    frames = int(round(total * fps))
    k = 0
    smooth = None
    grid = None
    try:
        for f in range(frames):
            t = f / fps
            while k + 1 < len(plan) and t >= plan[k + 1]["a"]:
                k += 1
                smooth = None
            p = plan[k]
            art = p["art"]
            who, open_ = None, False
            for (s, e, speaker, track) in p["talk"]:
                if s <= t < e:
                    who = speaker
                    i = int((t - s) * fps)
                    open_ = bool(track[i]) if 0 <= i < len(track) else False
                    break
            blink = any(s <= t < e for s, e in p["blinks"])
            pic = art.picture(who if open_ else None, blink)
            focus_who = who if who in art.mouths else p.get("focus")
            z, cx, cy = camera(t, p["a"], p["b"], p.get("punch"), p.get("shake"), art.focus(focus_who), art.size)
            if smooth is None:
                smooth = [cx, cy]
            smooth[0] += 0.08 * (cx - smooth[0])
            smooth[1] += 0.08 * (cy - smooth[1])
            s = z / MARGIN
            if depth_fn and art.depth is None:
                try:
                    art.depth = depth_fn(cv2.cvtColor(art.base, cv2.COLOR_RGB2BGR)).astype(np.float32)
                except Exception as e:  # noqa: BLE001 — this shot moves without depth
                    log(f"   ℹ️ No parallax on a shot ({type(e).__name__}).")
                    art.depth = False
            if depth_fn and art.depth is not False:
                # 2.5D: near pixels (the characters) drift a little more than the wall behind them, one way per
                # shot, as the camera pushes in (parallax.py's technique; the history channel's pictures use it).
                if grid is None:
                    grid = np.meshgrid(np.arange(W, dtype=np.float32) - W / 2, np.arange(H, dtype=np.float32) - H / 2)
                sx = grid[0] / s + smooth[0]
                sy = grid[1] / s + smooth[1]
                d = cv2.remap(art.depth, sx, sy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                lean = DEPTH_AMP * art.size[0] * (2 * _ease((t - p["a"]) / max(0.5, p["b"] - p["a"])) - 1)
                way = 1 if k % 2 == 0 else -1
                frame = cv2.remap(pic, sx - d * lean * way, sy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            else:
                m = np.float32([[s, 0, W / 2 - s * smooth[0]], [0, s, H / 2 - s * smooth[1]]])
                frame = cv2.warpAffine(pic, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            proc.stdin.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR).tobytes())
        proc.stdin.close()
        if proc.wait(timeout=600):
            raise RuntimeError("ffmpeg could not write the cartoon picture track")
    finally:
        if proc.poll() is None:
            proc.kill()
    return out


# ------------------------------------------------------------------ sound and text

BOING = "if(lt(t,0.5),0.4*sin(2*PI*190*t+2.2*sin(2*PI*11*t)*exp(-4*t))*exp(-5*t),0)"
POP = "if(lt(t,0.09),0.55*sin(2*PI*(1100*t-5200*t*t))*(1-t/0.09),0)"
DING = "if(lt(t,0.9),(0.3*sin(2*PI*1318*t)+0.18*sin(2*PI*1760*t))*exp(-5*t),0)"


def sounds(ep, rows, windows):
    """[(aevalsrc expr, seconds, at)]: a whoosh on some cuts, a pop on shocks, a ding on the twist, a boing after the
    punchline."""
    out = []
    for i, (_s, a, _b) in enumerate(windows[1:], 1):
        if i % 2:
            out.append((kit.WHOOSH, 0.3, max(0.0, a - 0.12)))
    for k, a, b, _p in rows:
        emo = ep.lines[k].emotion
        if emo in ("shocked", "scared") and k:
            out.append((POP, 0.09, max(0.0, a - 0.05)))
    if len(rows) >= 3:
        out.append((DING, 0.9, max(0.0, rows[-2][1] - 0.06)))
        out.append((BOING, 0.5, rows[-1][2] + 0.05))
    return out


def _ass(hex_colour):
    h = hex_colour.lstrip("#")
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


STYLES = [
    # Name tags 64 px (creative_qa on the first two-part episode: "make the name tags bigger"; it scored 8/10).
    kit.style("TnHook", "Montserrat ExtraBold", 72, "#FFFFFF", outline=5, shadow=3),
    kit.style("TnEp", "Montserrat ExtraBold", 40, "#FFFFFF", outline=3, shadow=2),
    "Style: TnName,Montserrat ExtraBold,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,2,0,3,18,0,5,"
    "60,60,0,1",
]


NAME_Y = kit.CAPTION_TOP_PX - 70      # the name tag's centre: right above the caption line


def text_events(ep, rows, n, body_end, more=False):
    """The hook caption (sound-off viewers), the episode tag, each speaker's name the first time they talk, and on
    part 1 of a two-part story ``more``: "PART 2 JALD!" over the cliffhanger."""
    ev = []
    if more and rows:
        ev.append(kit.dialogue(7, rows[-1][1], body_end, "TnHook",
                               rf"{{\an5\pos({W // 2},330)\1c&H3FD2FF&\fscx60\fscy60\t(0,200,\fscx100\fscy100)"
                               rf"\fad(120,0)}}TO BE CONTINUED... PART 2 JALD!"))
    hook = re.sub(r"[{}\\]", "", ep.hook_caption or "").strip()[:48].upper()
    if hook:
        end = min(body_end, max(2.6, rows[0][2] + 0.6) if rows else 2.8)
        ev.append(kit.dialogue(5, 0.0, end, "TnHook", rf"{{\an5\pos({W // 2},330)\fscx92\fscy92"
                                                     rf"\t(0,180,\fscx100\fscy100)\fad(0,200)}}{hook}"))
    ev.append(kit.dialogue(4, 0.0, body_end, "TnEp", rf"{{\an5\pos({W // 2},170)\alpha&H30&}}EP {n}"))
    seen = set()
    for k, a, b, _p in rows:
        who = ep.lines[k].speaker
        if who in seen or who not in CAST:
            continue
        seen.add(who)
        name = CAST[who]["name"].upper() + (" (AWAAZ)" if CAST[who].get("onscreen") is False else "")
        t0, t1 = a, min(b + 0.4, a + 2.0)
        # Just above the captions, as the line's speaker label: at 470 it sat on faces in close-ups (creative_qa on
        # episode 4: "the MITHU tag is over the parrot's eyes").
        ev.append(kit.dialogue(6, t0, t1, "TnName", rf"{{\an5\pos({W // 2},{NAME_Y})\3c{_ass(CAST[who]['colour'])}"
                                                   rf"\fscx70\fscy70\t(0,140,\fscx100\fscy100)\fad(60,160)}}{name}"))
    return ev


SEO_CONTEXT = ("IMPORTANT: this Short is an ORIGINAL animated comedy episode (episode {n} of our own series), not a "
               "clip from a show and not a kids' video. The characters are fictional: {cast}. The episode: {premise} "
               "The twist: {twist}. Write the title about the situation and its funny turn (what happened, who got "
               "caught), not only the names; keep it Roman Urdu; never call it a kids' cartoon, a nursery rhyme or "
               "a moral story, and never use the words 'kids' or 'bachon ke liye'.")
SERIES_NOTE = ("An original animated comedy series: Billo the cat, Sheru the dog, Mithu the parrot and baby Guddu in "
               "one Lahore home. All characters are fictional; pictures and voices are made with AI.")


def voice_items(ep):
    items = []
    for l in ep.lines:
        c = CAST[l.speaker]
        rate = c["voice"]["rate"]
        if l.emotion in ("angry", "excited", "shocked", "scared"):
            rate = f"{int(rate.rstrip('%')) + 6:+d}%"
        elif l.emotion in ("tired", "sad"):
            rate = f"{int(rate.rstrip('%')) - 6:+d}%"
        items.append({"text": l.text, "voice": c["gemini"], "style": f"{c['style']}, {l.emotion}",
                      "edge_voice": c["voice"]["edge"], "pitch": c["voice"]["pitch"], "rate": rate})
    return items


# ------------------------------------------------------------------ the job

def thumb_shot(ep, art):
    """The shot whose picture stands for the episode in the compilation's thumbnail: the first close-up of a
    character who talks (a face), else any shot with a talking character, else the first (episode 2's first shot
    was Billo from behind)."""
    talking = [k for k in range(len(ep.shots)) if (art.get(k) or {}).get("mouths")]
    close = [k for k in talking if ep.shots[k].framing == "close"]
    return (close or talking or [0])[0]


def with_part(title, k, limit=100):
    """``title`` ending in "(Part k)" once, hashtags after it, inside YouTube's 100 characters."""
    title = re.sub(r"\s*\(?\bpart\s*\d\)?", "", title or "", flags=re.I).strip()
    tags = " ".join(re.findall(r"#\w+", title))
    core = re.sub(r"\s*#\w+", "", title).strip()
    tail = f" (Part {k})" + (f" {tags}" if tags else "")
    return core[:max(10, limit - len(tail))].rstrip() + tail


def same_voices(client, items, said, log=print, wait=8):
    """A line the free edge voice failed went to the local or Gemini voice: in a cartoon that is another
    character's voice (Sheru's line came out in the narrator's on the first episode, 5-nov-2026; the same line
    read fine a minute later). Those lines get the character's own edge voice again after a pause; the other
    voice stays when it fails again. An edge line has its word times beside it; the others do not."""
    import free_voice
    off = [k for k, (p, _s) in enumerate(said) if p and not os.path.isfile(p + ".words.json")]
    if not off or free_voice.engine() != "edge":
        return said
    log(f"   🔁 {len(off)} line(s) came out in another voice; asking the character's own voice again.")
    time.sleep(wait)
    try:
        rows = free_voice.voice_items(client, [items[k] for k in off])
    except Exception:  # noqa: BLE001 — the other voice stays
        return said
    for k, row in zip(off, rows):
        if not row:
            continue
        path = said[k][0]
        tmp = path + ".edge.wav"
        secs = free_voice.speak(row[0], tmp, *row[1:])
        if secs:
            os.replace(tmp, path)
            if os.path.isfile(tmp + ".words.json"):
                os.replace(tmp + ".words.json", path + ".words.json")
            said[k] = (path, secs)
    return said


def _upscaled(paths, work, log=print):
    """{path: 2x path} through Real-ESRGAN's anime model when it is installed (TOON_UPSCALE=0 off); {} otherwise."""
    if os.environ.get("TOON_UPSCALE", "1") == "0":
        return {}
    try:
        import upscale
        if not upscale.available():
            return {}
        src, dst = os.path.join(work, "up_in"), os.path.join(work, "up_out")
        for d in (src, dst):
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d)
        names = {}
        for i, p in enumerate(paths):
            name = f"p{i:03d}.png"
            shutil.copyfile(p, os.path.join(src, name))
            names[p] = os.path.join(dst, name)
        upscale._run(src, dst, "realesr-animevideov3", 2)
        return {p: q for p, q in names.items() if os.path.isfile(q)}
    except Exception as e:  # noqa: BLE001 — the pictures go on at their own size
        log(f"   ⚠️ Upscaling skipped ({type(e).__name__}: {str(e)[:100]}).")
        return {}


def _load(path):
    import numpy as np
    from PIL import Image
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))


def make_art(client, ep, work, log=print):
    """Every shot's pictures: {shot: {"base", "mouths": {who: path}, "blink": (who, path) | None}}."""
    refs = {w: cast_ref(client, w) for w in sorted({w for s in ep.shots for w in s.who})}
    files = [os.path.join(work, f"shot{k}.png") for k in range(len(ep.shots))]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda k: draw_shot(client, ep, k, refs, files[k]), range(len(ep.shots))))
    if os.environ.get("TOON_LOOK_CHECK", "1") != "0":
        redo = look_check(client, ep, refs, files)
        # An open mouth is the usual finding (4 of 5 shots on the first episode, 5-nov-2026; a redraw came back
        # open again): the mouths are closed by an edit, which keeps the picture. Anything else is drawn again.
        shut = {k: p for k, p in redo.items() if only_mouths(p)}
        again = {k: p for k, p in redo.items() if k not in shut}
        if shut:
            log(f"   👄 Closing the mouths in {len(shut)} shot(s).")
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda k: _safe(lambda: close_mouths(client, ep, k, files[k])), list(shut)))
        if again:
            log(f"   🔁 Drawing {len(again)} shot(s) again: " + "; ".join(f"{k}: {p}" for k, p in again.items())[:200])
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda k: _safe(lambda: draw_shot(client, ep, k, refs, files[k])), list(again)))
    jobs = []
    for k, s in enumerate(ep.shots):
        talkers = [w for w in s.who if any(l.shot == k and l.speaker == w for l in ep.lines)]
        for w in talkers:
            jobs.append((k, w, "mouth"))
        if s.framing != "wide" and os.environ.get("TOON_BLINK", "1") != "0":
            lead = max(s.who, key=lambda w: sum(1 for l in ep.lines if l.shot == k and l.speaker == w))
            jobs.append((k, lead, "blink"))

    def one(job):
        k, w, kind = job
        out = os.path.join(work, f"shot{k}_{w}_{kind}.png")
        return job, _safe(lambda: draw_variant(client, ep, k, files[k], w, kind, out))
    with ThreadPoolExecutor(max_workers=4) as pool:
        made = list(pool.map(one, jobs))
    art = {k: {"base": files[k], "mouths": {}, "blink": None} for k in range(len(ep.shots))}
    for (k, w, kind), path in made:
        if path and kind == "mouth":
            art[k]["mouths"][w] = path
        elif path:
            art[k]["blink"] = (w, path)
    return art


def build_plan(ep, art, rows, windows, total, work, log=print, rnd=None):
    """ShotArt per window, the mouth tracks and blinks: the plan render_track draws."""
    rnd = rnd or random.Random(7)
    allpaths = []
    for k, a in art.items():
        allpaths += [a["base"]] + list(a["mouths"].values()) + ([a["blink"][1]] if a["blink"] else [])
    big = _upscaled(allpaths, work, log)
    built, plan = {}, []
    def track_of(p):
        try:
            return flaps(envelope(p)) if p and os.path.isfile(p) else []
        except Exception as e:  # noqa: BLE001 — an unreadable voice file: that line's mouth stays closed
            log(f"   ℹ️ No mouth timing for {os.path.basename(p)} ({type(e).__name__}).")
            return []
    tracks = {k: track_of(p) for k, _a, _b, p in rows}
    for s, a, b in windows:
        if s not in built:
            base = _load(art[s]["base"])
            mouths, ok = {}, 0
            n = len(ep.shots[s].who)
            for who, path in art[s]["mouths"].items():
                mask, centre = mask_of(base, _load(path), expect_for(n, ep.shots[s].who.index(who)))
                if mask is not None:
                    mouths[who] = (path, mask, centre)
                    ok += 1
                else:
                    log(f"   ⚠️ Shot {s}: {who}'s mouth edit was not clean; that character does not talk here.")
            blink = None
            if art[s]["blink"]:
                who, path = art[s]["blink"]
                mask, _c = mask_of(base, _load(path), expect_for(n, ep.shots[s].who.index(who)))
                if mask is not None:
                    blink = (who, path, mask)
            scale = 1.0
            if big.get(art[s]["base"]):
                pic = _load(big[art[s]["base"]])
                scale = pic.shape[1] / base.shape[1]
                import cv2
                up = (lambda m: cv2.resize(m, (pic.shape[1], pic.shape[0]), interpolation=cv2.INTER_LINEAR))
                mouths = {w: (_load(big.get(p, p)), up(m), c) for w, (p, m, c) in mouths.items()}
                if any(x.shape != pic.shape for x, _m, _c in mouths.values()):
                    mouths = {}
                blink = (blink[0], _load(big.get(blink[1], blink[1])), up(blink[2])) if blink else None
                if blink and blink[1].shape != pic.shape:
                    blink = None
                base = pic
            else:
                mouths = {w: (_load(p), m, c) for w, (p, m, c) in mouths.items()}
                blink = (blink[0], _load(blink[1]), blink[2]) if blink else None
            built[s] = ShotArt(base, mouths, blink, scale)
        talk, punch, shake, focus = [], None, None, None
        for k, la, lb, _p in rows:
            if ep.lines[k].shot != s or not (a - 0.06 <= la < b):
                continue
            who = ep.lines[k].speaker
            talk.append((la, lb, who, tracks.get(k) or []))
            focus = focus or (who if who in built[s].mouths else None)
            if k == len(ep.lines) - 1 and punch is None:
                punch = la
            if ep.lines[k].emotion in ("shocked", "scared") and shake is None and k:
                shake = la
        plan.append({"art": built[s], "a": a, "b": b, "talk": talk, "punch": punch, "shake": shake, "focus": focus,
                     "blinks": blinks(a, b, rnd) if built[s].blink else []})
    return plan


def run(output_dir, pipeline):
    import credits
    import toon_mix
    if os.environ.get("TOON_MIX_JOB") == "1":
        return toon_mix.run(output_dir, pipeline)       # the weekly compilation of kept episodes
    if os.environ.get("TOON_MOTION", "1") != "0":
        # Real animated scenes with lip-sync (owner, 9-nov-2026): toon_motion.py. TOON_MOTION=0: the pictures below.
        import toon_motion
        return toon_motion.run(output_dir, pipeline)
    premise = re.sub(r"\s+", " ", os.environ.get("TOON_PREMISE") or "").strip()[:240]
    shape = (os.environ.get("TOON_SHAPE") or "").strip().lower() or None
    os.environ["STOCK_FOOTAGE"] = "0"          # our own pictures only (broll reads this in this job's process)
    # No local (OmniVoice) fallback: it is another voice for the character anyway, and on episode 3 it loaded for
    # minutes and timed out; a failed line goes to Gemini, then same_voices asks the character's own voice again.
    os.environ["LOCAL_VOICE"] = "0"
    cfg = fl.settings()
    client = kit.gemini()
    rows_before = episodes()
    if len(premise) < 10:
        ideas = channel_ideas(client, 1)
        if not ideas:
            raise RuntimeError("No new episode idea came back; made again later.")
        premise, shape = ideas[0]["text"], ideas[0].get("shape")
    n = next_number()
    name = re.sub(r"[^A-Za-z0-9 ]", "", os.environ.get("TOON_SERIES") or "").strip()[:40]
    try:
        k, of = int(os.environ.get("TOON_PART") or 1), int(os.environ.get("TOON_PARTS") or 1)
    except ValueError:
        k, of = 1, 1
    part = series_part(name, k, of, rows_before) if name and 1 <= k <= of <= 3 else None
    print(f"🐱 Cartoon episode {n}{f' ({name}, part {k} of {of})' if part else ''}: \"{premise}\"")
    ep = write(client, premise, shape, rows_before, n, part=part)
    if part and f"part {k}" not in ep.title.lower():
        ep.title = f"{ep.title[:85].rstrip()} (Part {k})"
    print(f"   ✅ {ep.title} | {len(ep.lines)} lines, {len(ep.shots)} shots ({ep.shape}); twist: {ep.twist[:120]}")
    stem = kit.neutral_stem("Toon")
    work = os.path.join(output_dir, f".{stem}_art")
    os.makedirs(work, exist_ok=True)
    print(f"🎨 Drawing {len(ep.shots)} shots while {len(ep.lines)} lines are voiced...")
    items = voice_items(ep)
    with ThreadPoolExecutor(max_workers=1) as pool:
        art_job = pool.submit(make_art, client, ep, work)
        said = same_voices(client, items, kit.voice_all(client, items, output_dir, stem))
        art = art_job.result()
    rows, body_end = timeline(ep.lines, said)
    outro_s = kit.outro_seconds(cfg)
    card_ev, card_sfx = kit.end_card(body_end, outro_s)
    total = body_end + (outro_s if card_ev else 0.0)
    windows = shot_windows(ep, rows, total)
    talking = sum(1 for a in art.values() for _ in a["mouths"])
    print(f"🎬 Animating {len(windows)} shot windows ({talking} talking mouths, {total:.1f}s)...")
    plan = build_plan(ep, art, rows, windows, total, work)
    track = render_track(plan, total, os.path.join(work, "track.mp4"))
    bed = None
    if os.environ.get("BG_MUSIC", "0") == "1":
        import cricket_shorts as cs
        song = cs._bed("toons")
        bed = (song, body_end) if song else None
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    voices = [(p, a) for _k, a, _b, p in rows if p]
    caps = [(ep.lines[k].text, a, b, p) for k, a, b, p in rows]
    events = text_events(ep, rows, n, body_end, more=bool(part and k < of))
    kit.render(final, total, [cfg["bg"], cfg["bg"]], events + card_ev, STYLES, voices=voices,
               sfx=sounds(ep, rows, windows) + card_sfx, bed=bed, bg_video=track, fast=True)
    cast = sorted({l.speaker for l in ep.lines})
    clip = {"start": 0.0, "end": round(total, 3), "seconds": round(total, 3), "file": final,
            "video_title_for_youtube_short": ep.title, "viral_hook_text": ep.lines[0].text,
            "why": f"Cartoon episode {n}: {ep.premise}", "predicted_score": 90,
            "captions": kit.timed_transcript(caps), "genre": "toons", "ai_voice": "AI voice",
            "comment_question": ep.question, "toon": ep.model_dump(), "episode": n,
            "background_music": os.path.basename(bed[0]) if bed else None}
    kit.seo_or_fail([clip], clip["captions"], source_title=ep.title,
                    context=SEO_CONTEXT.format(n=n, cast=", ".join(f"{CAST[c]['name']} the {CAST[c]['what']}"
                                                                    for c in cast),
                                               premise=ep.premise, twist=ep.twist), text_limit=3000)
    for field in ("seo_description", "video_description_for_instagram"):
        if clip.get(field):
            clip[field] = credits.insert(clip[field], SERIES_NOTE)
    if part:
        # The title contest rewrote "...(Part 1)" without its part on the first two-part episode (5-nov-2026).
        clip["seo_title"] = with_part(clip.get("seo_title") or ep.title, k)
    kit.finish(output_dir, stem, [clip], clip["captions"], pipeline, extra={"genre": "toons"})
    record(ep, n, series_name=name if part else "", part=k)
    toon_mix.keep(clip.get("served") or final, body_end, n, clip.get("seo_title") or ep.title,
                  art[thumb_shot(ep, art)]["base"])
    if os.environ.get("TOON_KEEP_ART", "0") != "1":
        shutil.rmtree(work, ignore_errors=True)


# ------------------------------------------------------------------ channel art (the owner uploads it in Studio)

BANNER_PROMPT = ("{style}\nA wide banner picture for the series' YouTube channel: the four friends together, left to "
                 "right Mithu the parrot on Sheru's head, Sheru the dog, Billo the cat and baby Guddu, sitting on a woven "
                 "charpai in the sunny courtyard, all smiling at the camera, mouths closed. They sit in ONE horizontal "
                 "row across the exact middle of the picture, filling its middle third; plenty of plain sky and wall "
                 "above and floor below (the top and bottom are cropped on phones). Keep each exactly like their "
                 "reference picture. No text.")
AVATAR_PROMPT = ("{style}\nA round channel icon: a close-up of Billo the cat's face from her reference picture, big "
                 "green eyes, a cheeky closed-mouth smile, her gold collar bell visible, centred, on a plain deep "
                 "purple background. No text.")


def channel_art(client, out_dir):
    """banner.png (2560x1440, YouTube's size; the cast in the centre band every device shows) and avatar.png
    (800x800) for the channel, Facebook Page and Instagram: [paths]."""
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    refs = [cast_ref(client, w) for w in ("mithu", "sheru", "billo", "guddu")]
    pics = []
    for r in refs:
        with Image.open(r) as im:
            pics.append(im.convert("RGB").copy())
    style = STYLE.replace(", vertical 9:16 frame", "")
    raw = _image(client, pics + [BANNER_PROMPT.format(style=style)], os.path.join(out_dir, ".banner_raw.png"),
                 aspect="16:9")
    with Image.open(raw) as im:
        im = im.convert("RGB")
        s = max(2560 / im.width, 1440 / im.height)
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        x, y = (im.width - 2560) // 2, (im.height - 1440) // 2
        im.crop((x, y, x + 2560, y + 1440)).save(os.path.join(out_dir, "banner.png"))
    raw = _image(client, [pics[2], AVATAR_PROMPT.format(style=style)], os.path.join(out_dir, ".avatar_raw.png"),
                 aspect="1:1")
    with Image.open(raw) as im:
        im.convert("RGB").resize((800, 800), Image.LANCZOS).save(os.path.join(out_dir, "avatar.png"))
    return [os.path.join(out_dir, "banner.png"), os.path.join(out_dir, "avatar.png")]


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "art":
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
        for path in channel_art(kit.gemini(), sys.argv[2] if len(sys.argv) > 2 else os.path.join(STATE_DIR, "art")):
            print(path)
    else:
        print("python toon_shorts.py art [folder]   # the channel's banner and icon from the cast pictures")
