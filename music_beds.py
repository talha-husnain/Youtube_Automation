"""Background music made for us: 30-second instrumental beds from Google's
Lyria (lyria-3-clip-preview, $0.04 each on the Gemini API, ~15 s to make,
14-oct-2026), kept in music/<kind>/ and looped under the voice.

Nothing is downloaded from a music library, so there is no track for
Content ID to match; every Lyria file carries Google's SynthID watermark.
A few per kind are enough: short_kit.render loops and fades the bed far
under the voice, and a random one is picked per Short.
"""
import base64
import os
import random

import short_kit as kit

CLIP_MODEL = os.environ.get("LYRIA_CLIP_MODEL") or "lyria-3-clip-preview"
PER_KIND = 4
PROMPTS = {
    "cricket": [
        "Energetic stadium sports anthem: driving drums, handclaps, bright synth stabs, rising excitement",
        "Upbeat cricket highlights groove: punchy tabla and electronic drums, bold brass hits, confident",
        "Cinematic sports build-up: pulsing bass, taiko drums, heroic synth chords, tense and exciting",
        "Fun bouncy sports beat: dhol rhythm with modern trap drums and playful plucks",
    ],
    "quiz": [
        "Playful game show background loop: ticking clock percussion, light plucked strings, curious mood",
        "Suspenseful quiz countdown music: soft pulsing synth, ticking hi-hats, thinking mood, steady",
        "Bright quirky puzzle music: marimba, pizzicato strings, light claps, cheerful and clever",
        "Light tension bed for a trivia show: low synth pad, gentle ticking, subtle heartbeat drum",
    ],
}


def beds(kind):
    folder = os.path.join(kit.MUSIC_DIR, kind)
    try:
        return sorted(f for f in os.listdir(folder) if f.lower().endswith(kit.MUSIC_EXT))
    except OSError:
        return []


def make(kind, client=None, prompt=None):
    """One new bed for ``kind``; returns its path."""
    client = client or kit.gemini()
    prompt = prompt or random.choice(PROMPTS.get(kind) or PROMPTS["quiz"])
    it = client.interactions.create(model=CLIP_MODEL,
                                    input=prompt + ". Instrumental only, no vocals. Loopable, even energy.")
    audio = it.output_audio
    if not audio or not audio.data:
        raise RuntimeError("Lyria returned no audio.")
    folder = os.path.join(kit.MUSIC_DIR, kind)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"lyria_{kind}_{len(beds(kind)) + 1:02d}.mp3")
    with open(path, "wb") as f:
        f.write(base64.b64decode(audio.data))
    return path


def ensure(kind, want=PER_KIND, client=None):
    """Make missing beds for ``kind`` (one call each); never raises."""
    have = beds(kind)
    prompts = PROMPTS.get(kind) or []
    for k in range(len(have), want):
        try:
            print(f"🎵 Making background music for {kind} ({k + 1}/{want})...")
            make(kind, client, prompts[k % len(prompts)] if prompts else None)
        except Exception as e:  # noqa: BLE001 — music is a bonus
            print(f"   ℹ️ No new background music ({type(e).__name__}: {str(e)[:120]}).")
            break
    return beds(kind)
