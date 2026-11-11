"""Chacha Judge: the channel's own host inside every Punchline Bazaar clip.

Owner, 11-nov-2026: Punchline Bazaar stays a clip channel, "bring more creativity in the videos".
YouTube cuts the Shorts reach of channels that re-post other creators' clips without "your own voice,
storytelling, or distinct point of view" (1-oct-2026). A voice-over that only describes the screen, or
one template stamped on every Short, does not count, and a pause or a voice over the comic kills the
joke (docs/research-2026-11-11/clip-creativity.md). So the host jokes, never describes, and never talks
over the comedian:

- BUBBLES: on 1-2 laughs of the clip the host's own one-liner pops up in the top band (the title steps
  aside) while the audience laughs; the clip's sound is never cut or covered.
- ON THE LAUGH: at the same moments a quick zoom on the comedian, an animated emoji and a quiet
  synthesised sound (never a song or film sound: those carry Content ID).
- VERDICT: after the clip, "PUNCHLINE ADALAT #n" and the host's short spoken verdict with a score out
  of 10 and a question for the comments, in place of the longer "Hamara Take" (ai_take.py).
Every clip gets its own colour, side, sound, zoom and emoji (LOOKS), so the Shorts are not one template.

One text call per job writes it all; the verdicts are read by the free voice (short_kit.voice_lines).
framed_layout draws it from the job file (takes[clip]["host"]). CLIP_HOST=0 turns it off (the plain
take then). The creator is never named (owner's rule, seo_copy.py).
"""
import json
import os
import random
import re
import time
from typing import List

from pydantic import BaseModel

ROOT = os.path.dirname(os.path.abspath(__file__))
SERIES_FILE = os.path.join(ROOT, "state", "punchline_adalat.json")   # framed_layout draws the names
VOICE = "Puck"
STYLE = "like a cheeky Pakistani uncle judging a comedy show, quick and playful, natural Urdu accent"
MAX_LAUGHS = 2
LAUGH_GAP = 4.0          # seconds between two laugh moments at least
EDGE_START = 1.5         # no laugh moment before this, nor in the clip's last EDGE_END seconds
EDGE_END = 1.0
SNAP = 1.5               # a moment is moved onto the nearest word end within this
BUBBLE_WORDS = (2, 9)
VERDICT_WORDS = (3, 12)
QUESTION_WORDS = (2, 6)
DEFAULT_QUESTION = "Aap kitne doge?"
MAX_VERDICT_SECONDS = 4.5
# The animated Noto emoji (stickers.py) the host may pick, and what each means to the model.
EMOJI_CHOICES = {"joy": "laughing out loud", "crying": "laughing so hard it hurts, or 'bechara'",
                 "shocked": "an outrageous line", "mind_blown": "a genius comeback",
                 "fire": "a savage roast", "eyes": "awkward or suspicious", "thinking": "a sly double meaning",
                 "hundred": "painfully true", "clap": "a perfect comeback"}
# Per-clip variety: bubble fill and text colours, the laugh sound, the zoom.
LOOKS = [("#FFD23F", "#1A1A1A"), ("#FFFFFF", "#1A1A1A"), ("#00E5FF", "#0B1020"), ("#FF5DA2", "#FFFFFF"),
         ("#7CFF6B", "#0B1020")]
SOUNDS = ("boom", "pop", "tss")
ZOOMS = (1.10, 1.12, 1.14, 1.16)
_NON_LATIN = re.compile("[؀-ۿऀ-ॿ]")
_EMOJI_CHARS = re.compile("[" + chr(0x1F000) + "-" + chr(0x1FAFF) + chr(0x2600) + "-" + chr(0x27BF)
                          + chr(0xFE0F) + chr(0x200D) + "]")


class Laugh(BaseModel):
    at: float
    bubble: str
    emoji: str


class HostClip(BaseModel):
    index: int
    laughs: List[Laugh]
    score: int
    verdict: str
    question: str


class HostResponse(BaseModel):
    clips: List[HostClip]


PROMPT = """You are "Chacha Judge", the host of {handle}, a Pakistani comedy Shorts channel. Each Short
is one moment from a stand-up or crowd-work set, and you are the channel's own voice in it: a cheeky
desi uncle who judges every joke in his "Punchline Adalat".

For EACH clip below (its words, each with the second it ends, counted from the clip's start):

1. laughs: the 1 or 2 moments the audience laughs hardest (a punchline, a comeback, a roast). For each:
   - at: the second the punchline's LAST word ends: copy one of the times in the words list.
   - bubble: YOUR OWN one-liner about it, shown on screen while the crowd laughs: 3 to 8 words of
     Roman Urdu. A joke, a roast, a sarcastic aside or a twist of your own, like a funny friend
     watching with you. NEVER describe or repeat what happened or was said ("comedian ne kaha...",
     "sab hans rahe hain", "uncle ne jawab diya" are wrong). Add something new. The kind of line meant
     (never reuse these): "Uncle ki izzat ka janaza nikal gaya", "HR ne resume wapas maang liya",
     "Is bande ko ghar mat jaane do".
   - emoji: one of {emoji}.
2. score: your verdict on the whole clip out of 10, from 4 to 10. Judge honestly: a great comeback
   earns 9 or 10, a mild one 6. Do not give every clip the same score.
3. verdict: what you say aloud right after the clip: 4 to 9 words of Roman Urdu, a punchy judgement
   about THIS clip's situation with your own twist, ending on the score in words. Generic praise is
   wrong ("Acha tha bhai", "Badiya tha", "Mazaa aa gaya" never). The kind meant (never reuse these):
   "Sheeshe ke saamne khana? Kapde pehno, aath number!", "Uncle ko seedha out kar diya, nau number!".
4. question: 2 to 5 words of Roman Urdu asking viewers for their score or their side
   ("Aap kitne doge?", "Aapka faisla kya hai?").

Rules for every line: Roman Urdu in Latin letters only (never Devanagari or Arabic script), everyday
spoken words, English words people use daily are fine. Never name the comedian, any person, channel
or show. No swear words, nothing sexual, never mock religion, caste, ethnicity, disability, children
or an audience member's looks: tease the situation, not the person. No emoji outside the emoji field.
Every clip's lines must differ from the other clips'.

Clips (JSON): {clips}

Return JSON: {{"clips": [{{"index": 0, "laughs": [{{"at": 12.4, "bubble": "...", "emoji": "joy"}}],
"score": 8, "verdict": "...", "question": "..."}}]}}"""


def enabled():
    """On for comedy unless CLIP_HOST=0, and off with the take (AI_TAKE=0: no channel voice at all)."""
    return (os.environ.get("CLIP_HOST", "1").strip() != "0" and os.environ.get("AI_TAKE", "1").strip() != "0"
            and (os.environ.get("CONTENT_GENRE") or "comedy").lower() == "comedy")


def clip_words(transcript, clip):
    """[(seconds from the clip start at which the word ends, word)] inside the clip."""
    start, end = float(clip["start"]), float(clip["end"])
    out = []
    for s in (transcript or {}).get("segments") or []:
        for w in s.get("words") or []:
            try:
                ws, we = float(w["start"]), float(w["end"])
            except (KeyError, TypeError, ValueError):
                continue
            word = str(w.get("word") or "").strip()
            if word and start <= ws and we <= end + 0.3:
                out.append((round(we - start, 1), word))
    return out


def _line(text, words, limit_words=None):
    """The line cleaned: Latin letters only, no emoji, one space; None when it breaks the word range."""
    text = _EMOJI_CHARS.sub("", str(text or ""))
    text = re.sub(r"\s+", " ", text.replace("\\", " ").replace("{", "(").replace("}", ")")).strip()
    lo, hi = limit_words or words
    if not text or _NON_LATIN.search(text) or not lo <= len(text.split()) <= hi:
        return None
    return text


def _snap(at, ends, clip_s):
    """``at`` moved onto the nearest word end within SNAP s, inside the clip's edges; None when none."""
    near = [e for e in ends if abs(e - at) <= SNAP and EDGE_START <= e <= clip_s - EDGE_END]
    return min(near, key=lambda e: abs(e - at)) if near else None


def clean(item, words, clip_s, names=None):
    """A validated host record from the model's answer, or None. ``names``: the creator's name pattern."""
    def scrub(text):
        return names.sub("bhai", text) if (text and names) else text
    ends = sorted({t for t, _w in words})
    laughs = []
    for lg in sorted(item.laughs, key=lambda x: x.at):
        at = _snap(float(lg.at), ends, clip_s)
        bubble = scrub(_line(lg.bubble, BUBBLE_WORDS))
        if at is None or not bubble or any(abs(at - x["at"]) < LAUGH_GAP for x in laughs):
            continue
        laughs.append({"at": at, "bubble": bubble,
                       "emoji": lg.emoji if lg.emoji in EMOJI_CHOICES else "joy"})
        if len(laughs) >= MAX_LAUGHS:
            break
    score = max(1, min(10, int(item.score or 0))) if item.score else 7
    verdict = scrub(_line(item.verdict, VERDICT_WORDS)) or f"Faisla {score} number"
    question = scrub(_line(item.question, QUESTION_WORDS)) or DEFAULT_QUESTION
    return {"laughs": laughs, "score": score, "verdict": verdict, "question": question}


def look(seed):
    """This clip's own colour, side, sound and zoom (the same for a re-render)."""
    rnd = random.Random(seed)
    fill, ink = rnd.choice(LOOKS)
    return {"fill": fill, "ink": ink, "side": rnd.choice(("left", "right")), "sound": rnd.choice(SOUNDS),
            "zoom": rnd.choice(ZOOMS)}


def next_series_numbers(count):
    """The next ``count`` "PUNCHLINE ADALAT #n" numbers (kept in SERIES_FILE)."""
    try:
        with open(SERIES_FILE, encoding="utf-8") as f:
            n = int(json.load(f).get("n") or 0)
    except (OSError, ValueError, AttributeError, TypeError):
        n = 0
    os.makedirs(os.path.dirname(SERIES_FILE), exist_ok=True)
    tmp = SERIES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"n": n + count, "at": int(time.time())}, f)
    os.replace(tmp, SERIES_FILE)
    return list(range(n + 1, n + count + 1))


def write(client, model, clips, transcript, handle, source_title=""):
    """{clip index: host record} from one text call; clips the model skipped or got wrong are left out."""
    from google.genai import types
    import seo_copy
    items, words_of = [], {}
    for i, c in enumerate(clips):
        words = clip_words(transcript, c)
        words_of[i] = words
        items.append({"index": i, "title": c.get("seo_title") or "",
                      "words": " ".join(f"{w}@{t:g}" for t, w in words)[:6000]})
    r = client.models.generate_content(
        model=model,
        contents=PROMPT.format(handle=handle, clips=json.dumps(items, ensure_ascii=False),
                               emoji=", ".join(f"{k} ({v})" for k, v in EMOJI_CHOICES.items())),
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=HostResponse))
    names = seo_copy.name_pattern(seo_copy._by_names(source_title), handle)
    out = {}
    for item in HostResponse.model_validate_json(r.text).clips:
        if not 0 <= item.index < len(clips) or item.index in out:
            continue
        clip_s = float(clips[item.index]["end"]) - float(clips[item.index]["start"])
        rec = clean(item, words_of[item.index], clip_s, names)
        if rec:
            out[item.index] = rec
    return out


def apply(clips, transcript, job_dir, clip_names, outro_seconds=0.0, source_title=""):
    """Write and voice the host for each clip. Returns {clip file name: take record with "host"} for
    framed_layout's job file (the verdict is the record's text and voice), or {} when it failed, so the
    caller can fall back to the plain take."""
    import ai_take
    if not clips or not enabled():
        return {}
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return {}
    handle = (os.environ.get("FRAME_HANDLE") or "").strip() or "this channel"
    voice = (os.environ.get("AI_TAKE_VOICE") or VOICE).strip()
    print(f"🧑‍⚖️ Chacha Judge watches {len(clips)} clip(s)...")
    try:
        from google import genai
        import ai_fallback
        import short_kit
        client = ai_fallback.wrap(genai.Client(api_key=key, http_options=short_kit.http_options()))
        model = os.environ.get("GEMINI_MODEL") or "gemini-3.1-flash-lite"
        # The jokes are the channel's own voice: the full backup model writes them while Gemini is
        # out of credit (one call a job), as for the songs.
        with ai_fallback.best_writer():
            hosts = write(client, model, clips, transcript, handle, source_title)
    except Exception as e:  # noqa: BLE001 — the plain take instead
        print(f"   ⚠️ Host failed ({type(e).__name__}: {str(e)[:160]}) — plain take instead.")
        return {}
    todo = []
    for i in sorted(h for h in hosts if 0 <= h < len(clips)):
        clip_s = float(clips[i]["end"]) - float(clips[i]["start"])
        longest = MAX_VERDICT_SECONDS * ai_take.MAX_TEMPO + ai_take.TAKE_PAD_SECONDS
        if clip_s + longest + outro_seconds > ai_take.SHORTS_LIMIT_SECONDS:
            print(f"   ℹ️ Clip {i + 1} is {clip_s:.0f}s: no host, it would pass Shorts' 3 minutes.")
            continue
        todo.append(i)
    if not todo:
        return {}
    try:
        voiced = short_kit.voice_lines(client, [{"text": hosts[i]["verdict"], "voice": voice, "style": STYLE}
                                                for i in todo], job_dir, "verdict")
    except Exception as e:  # noqa: BLE001 — the verdict still shows as text
        print(f"   ⚠️ Verdict voices failed ({type(e).__name__}: {str(e)[:120]}) — text only.")
        voiced = [None] * len(todo)
    numbers = next_series_numbers(len(todo))
    takes = {}
    for i, got, n in zip(todo, voiced, numbers):
        name = clip_names[i]
        audio = os.path.join(job_dir, f"{os.path.splitext(name)[0]}.take.wav")
        path, secs = got if got else (None, 0.0)
        if path and secs:
            if os.path.abspath(path) != os.path.abspath(audio):
                os.replace(path, audio)
            if os.path.exists(path + ".words.json"):
                os.remove(path + ".words.json")
            secs = ai_take._fit(audio, secs) if secs <= MAX_VERDICT_SECONDS * ai_take.MAX_TEMPO else None
        if not (path and secs):
            if os.path.exists(audio):
                os.remove(audio)
            secs = 0.0
        host = {**hosts[i], "series": n, "look": look(f"{name}|{n}")}
        takes[name] = {"text": host["verdict"], "audio": os.path.basename(audio) if secs else None,
                       "voice_seconds": round(secs, 2), "host": host}
        clips[i]["ai_take"] = host["verdict"]
        clips[i]["host"] = {"score": host["score"], "laughs": [x["bubble"] for x in host["laughs"]],
                            "series": n}
    voiced_n = sum(1 for r in takes.values() if r["audio"])
    laughs = sum(len(r["host"]["laughs"]) for r in takes.values())
    print(f"   ✅ Host ready for {len(takes)}/{len(clips)} clips ({laughs} laugh moments, {voiced_n} verdicts voiced)")
    return takes
