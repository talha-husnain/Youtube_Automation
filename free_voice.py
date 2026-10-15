"""Free narration with Microsoft's neural voices (edge-tts), the voice
MoneyPrinterTurbo uses by default, for the generated videos.

Why the Urdu script step: read as written, Roman Urdu came out garbled (the
Urdu voice skipped half the words of a test line; Whisper heard nonsense,
15-oct-2026). The same line converted to Urdu script first was heard back
almost word for word, by both ur-PK voices. So the lines of one video are
converted in a single cheap Gemini text call, then read for free. The voice
also reports when each word is spoken (WordBoundary), saved next to the wav
(<wav>.words.json) for exact captions (short_kit.line_word_times).

edge-tts talks to the read-aloud service of Microsoft Edge, which is not an
official API: it can hang or change. Every line has a timeout and retries,
and a line that still fails is voiced by Gemini (ai_take.speak), so a video is
never lost to it. VOICE_ENGINE=gemini switches back to Gemini for everything.
"""
import asyncio
import json
import os
import re
import subprocess
from typing import List

from pydantic import BaseModel

import short_kit as kit

URDU = {"male": "ur-PK-AsadNeural", "female": "ur-PK-UzmaNeural"}
ENGLISH = {"male": "en-US-GuyNeural", "female": "en-US-JennyNeural"}
TIMEOUT = 60
TRIES = 3


def engine():
    return (os.environ.get("VOICE_ENGINE") or "edge").lower()


def gender(voice):
    return "female" if voice in kit.FEMALE_VOICES else "male"


def rate_for(style):
    """edge voices have no acting styles; pace is what we can set."""
    s = (style or "").lower()
    if any(w in s for w in ("excited", "energetic", "fast", "commentator", "fun")):
        return "+12%"
    if any(w in s for w in ("calm", "documentary", "steady", "serious")):
        return "-4%"
    return "+4%"


class Converted(BaseModel):
    lines: List[str]


CONVERT_PROMPT = """Convert each numbered line of Roman Urdu (Urdu written in Latin letters) to proper Urdu script,
word for word, the same words in the same order. Write numbers and years as Urdu words, and English words in
Urdu letters the way Pakistanis say them. Keep the punctuation as Urdu punctuation (۔ ، ؟). Return exactly {n}
lines, in order.

{lines}"""


def to_urdu_script(client, lines):
    """[Urdu script] for [Roman Urdu], one call; raises when the count is off."""
    got = kit.ask_json(client, Converted, CONVERT_PROMPT.format(
        n=len(lines), lines="\n".join(f"{k}: {t}" for k, t in enumerate(lines))))
    out = [re.sub(r"^\s*\d+\s*[:.)-]\s*", "", t).strip() for t in got.lines]
    if len(out) != len(lines) or not all(out):
        raise ValueError(f"converted {len(out)} lines for {len(lines)}")
    return out


async def _say(text, voice, rate, mp3):
    import edge_tts
    words = []
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    with open(mp3, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append((chunk["text"], chunk["offset"] / 1e7, (chunk["offset"] + chunk["duration"]) / 1e7))
    return words


def speak(text, path, voice, rate="+0%"):
    """``text`` read by an edge voice into a 24 kHz mono wav at ``path``, the
    word times saved beside it. Returns the length, or None."""
    mp3 = path + ".mp3"
    for _attempt in range(TRIES):
        try:
            words = asyncio.run(asyncio.wait_for(_say(text, voice, rate, mp3), TIMEOUT))
            if not os.path.isfile(mp3) or os.path.getsize(mp3) < 2000:
                raise ValueError("no audio")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", mp3, "-ar", "24000", "-ac", "1",
                            "-sample_fmt", "s16", path], check=True, timeout=120)
            tokens = text.split()
            if len(tokens) == len(words):
                # The voice reports bare words; the text's own tokens carry the
                # punctuation that clause-by-clause caption timing lines up on.
                words = [(tok, s, e) for tok, (_w, s, e) in zip(tokens, words)]
            with open(path + ".words.json", "w", encoding="utf-8") as f:
                json.dump(words, f, ensure_ascii=False)
            return kit.wav_seconds(path)
        except Exception as e:  # noqa: BLE001 — retried, then Gemini takes the line
            last = e
        finally:
            if os.path.exists(mp3):
                os.remove(mp3)
    print(f"   ⚠️ Free voice failed ({type(last).__name__}: {str(last)[:100]}).")
    return None


def heard_words(wav):
    """The word times the voice reported for ``wav`` [(text, start, end)], or []."""
    try:
        with open(wav + ".words.json", encoding="utf-8") as f:
            return [tuple(w) for w in json.load(f)]
    except (OSError, ValueError, TypeError):
        return []


def voice_items(client, items):
    """The texts each item is read from, and its edge voice: Roman Urdu lines
    go through one conversion call. [(text, voice, rate) | None]."""
    urdu = [k for k, it in enumerate(items) if (it.get("language") or "Roman Urdu") == "Roman Urdu"]
    converted = {}
    if urdu:
        try:
            for k, t in zip(urdu, to_urdu_script(client, [items[k]["text"] for k in urdu])):
                converted[k] = t
        except Exception as e:  # noqa: BLE001 — those lines go to Gemini
            print(f"   ⚠️ Urdu script conversion failed ({type(e).__name__}); Gemini voices these lines.")
    out = []
    for k, it in enumerate(items):
        g = gender(it.get("voice"))
        if k in converted:
            out.append((converted[k], URDU[g], rate_for(it.get("style"))))
        elif (it.get("language") or "") == "English":
            out.append((it["text"], ENGLISH[g], rate_for(it.get("style"))))
        else:
            out.append(None)
    return out
