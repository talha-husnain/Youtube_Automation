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
import time

import short_kit as kit

CLIP_MODEL = os.environ.get("LYRIA_CLIP_MODEL") or "lyria-3-clip-preview"
PER_KIND = 4
# A kind's pool grows to TARGET, one new bed a day at most (grow): cricket, controversy and quiz each
# had ONE bed under every Short (29-oct-2026), the spam policy's own example of mass production ("the
# exact same background music ... across many videos", support.google.com/youtube/answer/2801973).
TARGET = int(os.environ.get("MUSIC_BEDS_TARGET") or 12)
GROW_EVERY = 20 * 3600
# Mixed into the kind's prompts, so the 12 beds of a kind differ in tempo, key and lead instrument.
VARIANTS = ["at a slow 80 BPM", "at a lively 124 BPM", "in a minor key", "in a bright major key",
            "with piano as the lead", "with plucked guitar as the lead", "with flute as the lead",
            "sparse and minimal", "with layered hand percussion", "with warm analog synths"]
PROMPTS = {
    "cricket": [
        "Energetic stadium sports anthem: driving drums, handclaps, bright synth stabs, rising excitement",
        "Upbeat cricket highlights groove: punchy tabla and electronic drums, bold brass hits, confident",
        "Cinematic sports build-up: pulsing bass, taiko drums, heroic synth chords, tense and exciting",
        "Fun bouncy sports beat: dhol rhythm with modern trap drums and playful plucks",
    ],
    "controversy": [
        "Dark investigative documentary bed: low pulsing synth, soft ticking, tense strings, mysterious",
        "Suspenseful news explainer music: deep bass drone, sparse piano notes, slow heartbeat drum",
        "Moody true-story background: atmospheric pads, subtle glitch percussion, serious and steady",
        "Tense reveal music: muted cinematic drums, rising strings, restrained and dramatic",
    ],
    # Under the cartoon series (toon_shorts.py): light, bouncy comedy, quiet enough for dialogue.
    "toons": [
        "Playful cartoon comedy underscore: pizzicato strings, bassoon bounce, light xylophone, cheeky and mischievous",
        "Bouncy sitcom background music: ukulele, hand claps, whistling melody, sunny and silly",
        "Sneaky cartoon tiptoe music: muted plucks, soft woodblock, tuba steps, curious and funny",
        "Upbeat desi comedy groove: light dholak, playful flute, plucked synth, cheerful and quirky",
    ],
    # Under the money channel's charts (money_shorts.py): modern, light and curious, never news-dramatic.
    "money": [
        "Modern business explainer beat: clean electronic drums, plucked synth arpeggio, curious and upbeat",
        "Light corporate tech groove: soft kick, marimba motif, airy pads, confident and bright",
        "Lo-fi finance explainer music: dusty drums, mellow electric piano, steady and thoughtful",
        "Playful data story music: pizzicato strings, light claps, quirky bass line, clever mood",
    ],
    # Under long documentaries (history_videos.py), a different one per chapter.
    "history": [
        "Epic cinematic documentary underscore: soft strings, low choir pads, slow distant drums, majestic",
        "Middle Eastern ambient documentary bed: oud, soft frame drum, warm pads, reflective and calm",
        "Mysterious ancient history ambience: duduk melody, low drones, gentle percussion, timeless",
        "Gentle orchestral storytelling music: piano and strings, hopeful and reflective, steady",
    ],
    # Under the horror channel's stories (horror_stories.py): dread, never jump-scare noise.
    "horror": [
        "Dark ambient horror drone: low cello rumble, distant metallic scrapes, slow heartbeat pulse, dread",
        "Eerie suspense underscore: detuned music box, cold piano notes, soft wind, unsettling and quiet",
        "Haunted house ambience: deep drone, creaking textures, whispering pads, slow and tense",
        "Rising horror tension bed: low strings swelling, sparse taiko hits, dissonant choir pad, ominous",
        "South Asian folk horror ambience: low sarangi drone, distant tabla heartbeat, wind, haunting",
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
    n = len(beds(kind)) + 1
    while os.path.exists(os.path.join(folder, f"lyria_{kind}_{n:02d}.mp3")):
        n += 1
    path = os.path.join(folder, f"lyria_{kind}_{n:02d}.mp3")
    with open(path, "wb") as f:
        f.write(base64.b64decode(audio.data))
    return path


def grow(kind, client=None, now=None, target=None):
    """One new bed for ``kind`` when it has fewer than TARGET and none was made in the last GROW_EVERY;
    the path made, else None. Never raises. Called as a Short picks its bed, so the pool grows by
    itself, about a bed a day ($0.04 and ~15 s each)."""
    have = beds(kind)
    target = TARGET if target is None else target
    prompts = PROMPTS.get(kind) or []
    if len(have) >= target or not prompts:
        return None
    folder = os.path.join(kit.MUSIC_DIR, kind)
    newest = max((os.path.getmtime(os.path.join(folder, f)) for f in have), default=0)
    if (now or time.time()) - newest < GROW_EVERY:
        return None
    k = len(have)
    prompt = f"{prompts[k % len(prompts)]}, {VARIANTS[k % len(VARIANTS)]}"
    try:
        print(f"🎵 Adding background music for {kind} ({k + 1}/{target}): {prompt[:80]}...")
        return make(kind, client, prompt)
    except Exception as e:  # noqa: BLE001 — music is a bonus
        print(f"   ℹ️ No new background music ({type(e).__name__}: {str(e)[:120]}).")
        return None


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
