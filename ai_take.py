"""The channel's own spoken reaction ("take") after each clip.

Gemini writes one short Roman Urdu line per clip (an opinion or a relatable
joke about THIS clip, then a question that gets comments), a Gemini voice
reads it, and framed_layout shows it word by word over the clip's last frame
before the end card. It is the channel adding something of its own after the
source creator's moment, and the question at the end asks for comments.

Honest limit, said to the owner on 8-oct-2026: YouTube's creator liaison
named voice-over narration and template-based bulk changes as NOT making a
re-posted clip original (Shorts reach change, 1-oct-2026), so this helps
engagement more than it changes how YouTube classifies the clip.

Voices: measured on 8-oct-2026 by transcribing each model's output with
Whisper. gemini-2.5-flash-preview-tts and gemini-3.1-flash-tts-preview read
Roman Urdu cleanly; gemini-3.8-flash-tts read the instruction aloud too and
3.8-flash-lite garbled it, so neither is in the list.

Env: AI_TAKE (1 default, 0 off), AI_TAKE_VOICE (Gemini voice, default Puck),
TAKE_TTS_MODEL (tried first), CONTENT_GENRE (comedy for now).
Any failure leaves the clip without a take (a take without a voice falls back
to text only).
"""
import json
import os
import re
import subprocess
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from typing import List

from pydantic import BaseModel

TTS_MODELS = ["gemini-2.5-flash-preview-tts", "gemini-3.1-flash-tts-preview"]
DEFAULT_VOICE = "Puck"
# A take longer than this is sped up (at most MAX_TEMPO), else read as text only.
MAX_VOICE_SECONDS = 7.0
MAX_TEMPO = 1.25
# Shorts stop at 3 minutes: a clip that would pass it with the take and the
# end card keeps its length and goes without a take.
SHORTS_LIMIT_SECONDS = 179.5
# Mirrors framed_layout: voice lead/tail and the text-only hold.
TAKE_PAD_SECONDS = 0.95
TEXT_ONLY_SECONDS = 3.5

GENRES = {
    "comedy": ("a stand-up comedy clips", "a sarcastic roast or a cheeky double-meaning "
               "one-liner about THIS clip's situation, the way a stand-up does crowd work "
               "(never a summary, never the punchline repeated)"),
}

_NON_LATIN = re.compile("[؀-ۿऀ-ॿ]")


class Take(BaseModel):
    index: int
    take: str


class TakeResponse(BaseModel):
    takes: List[Take]


PROMPT = """You run the YouTube Shorts channel {handle}, {genre} channel for Pakistani
and Indian viewers. After each clip the channel's own voice says a short reaction: the
channel's "take".

For EACH clip below write `take`:
- Roman Urdu in Latin letters only (never Devanagari or Arabic script), everyday spoken
  words, like a friend reacting. English words people use daily are fine.
- 12 to 18 words in total, never more than 18: 2 or 3 short sentences, about 6 seconds
  when spoken. Count the words.
- First: {angle}.
- Then: a teasing, sarcastic question with a twist or a double meaning that viewers
  cannot resist answering, and tell them to answer in the comments ("comment mein
  batao", "neeche confess karo", "comments mein likho").
- The tone is naughty, not dirty. Double meaning and innuendo are welcome (YouTube
  keeps full ads for sexual jokes and innuendo without vulgar words). NEVER use a
  swear word, crude slang ("phat gayi", "g*nd") or an explicitly sexual word, never
  describe sex, and never joke about religion, caste, ethnicity or children.
  Examples of the tone only (other topics, never copy them):
  "Exam se pehle wali raat sab Einstein hote hain. Aapne raat ko kya kya 'padha' hai?
  Comment mein confess karo!"
  "Shaadi ke baad sab 'adjust' karna padta hai, samajh gaye na kya kya. Aapka sabse
  bada adjustment kya tha? Neeche likho!"
- NEVER name the comedian, creator, speaker, channel or show. No hashtags, no emoji.
- Every clip's take must be different: different opening words, different question.

Clips (JSON): {clips}

Return JSON: {{"takes": [{{"index": 0, "take": "..."}}, ...]}}"""


def enabled():
    return os.environ.get("AI_TAKE", "1").strip() != "0"


def _clip_text(transcript, clip, limit=1000):
    words = [w["word"] for s in (transcript or {}).get("segments") or []
             for w in s.get("words") or []
             if clip["start"] <= w["start"] <= clip["end"]]
    return "".join(words).strip()[:limit]


def write_takes(client, model, clips, transcript, handle, genre="comedy", source_title=""):
    """{clip index: take text} from one text call. Latin-only, creator-free.

    Only the clip's words and its (already name-free) SEO title go in, never
    the source title, so the model has no name to repeat; the source title's
    "BY <name>" still checks the answer."""
    from google.genai import types
    import seo_copy
    desc, angle = GENRES.get(genre, GENRES["comedy"])
    items = [{"index": i, "title": c.get("seo_title") or "",
              "what_is_said": _clip_text(transcript, c)} for i, c in enumerate(clips)]
    r = client.models.generate_content(
        model=model,
        contents=PROMPT.format(handle=handle, genre=desc, angle=angle,
                               clips=json.dumps(items, ensure_ascii=False)),
        config=types.GenerateContentConfig(response_mime_type="application/json",
                                           response_schema=TakeResponse))
    names = seo_copy.name_pattern(seo_copy._by_names(source_title), handle)
    out = {}
    for t in TakeResponse.model_validate_json(r.text).takes:
        text = re.sub(r"\s+", " ", t.take or "").strip()
        if not 0 <= t.index < len(clips) or not text or _NON_LATIN.search(text):
            continue
        if names:
            # The speaker says his own name in some clips and the model repeats it.
            text = names.sub("bhai", text)
        out[t.index] = text
    return out


def _wav_seconds(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


DEFAULT_STYLE = "like a fun Pakistani YouTuber, natural Urdu accent"


def speak(client, text, path, voice=DEFAULT_VOICE, style=None):
    """Write ``text`` as a 24 kHz mono wav. Returns its length, or None.

    ``style`` says how to read it (song_shorts / movie_dub / cricket_shorts
    pass their own); the line itself is always Roman Urdu."""
    from google.genai import types
    models = [m for m in (os.environ.get("TAKE_TTS_MODEL") or "").split(",") if m.strip()]
    for model in models + [m for m in TTS_MODELS if m not in models]:
        for attempt in range(2):
            try:
                r = client.models.generate_content(
                    model=model.strip(),
                    contents=f"Read this Roman Urdu line aloud {style or DEFAULT_STYLE}: {text}",
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))))
                # Now and then a call comes back with no audio part at all
                # (1 in 8 back to back, 8-oct-2026): that is a retry, not a fail.
                data = r.candidates[0].content.parts[0].inline_data.data
                if not data:
                    raise ValueError("empty audio")
                with wave.open(path, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(24000)
                    w.writeframes(data)
                return _wav_seconds(path)
            except Exception as e:  # noqa: BLE001 — next attempt / model
                busy = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
                if attempt == 0:
                    time.sleep(15 if busy else 1)
                    continue
                print(f"   ⚠️ Voice {model} failed ({type(e).__name__}: {str(e)[:120]})")
    return None


def _fit(path, seconds):
    """Speed a long take up to MAX_TEMPO. Returns the new length or None."""
    if seconds <= MAX_VOICE_SECONDS:
        return seconds
    tempo = seconds / MAX_VOICE_SECONDS
    if tempo > MAX_TEMPO:
        return None
    tmp = path + ".fast.wav"
    try:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path, "-af", f"atempo={tempo:.3f}",
                        "-ar", "24000", "-ac", "1", tmp], check=True, timeout=60)
        os.replace(tmp, path)
        return _wav_seconds(path)
    except (subprocess.SubprocessError, OSError):
        return None


def apply(clips, transcript, job_dir, clip_names, outro_seconds=0.0, source_title=""):
    """Write and voice a take per clip. Returns {clip file name: take record}
    for framed_layout's job file; sets ``ai_take`` on each clip dict."""
    if not clips or not enabled():
        return {}
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("   ℹ️ AI take skipped (no Gemini key).")
        return {}
    genre = (os.environ.get("CONTENT_GENRE") or "comedy").lower()
    handle = (os.environ.get("FRAME_HANDLE") or "").strip() or "this channel"
    voice = (os.environ.get("AI_TAKE_VOICE") or DEFAULT_VOICE).strip()
    print(f"🎙️ Writing the channel's take for {len(clips)} clip(s)...")
    try:
        from google import genai
        client = genai.Client(api_key=key)
        model = os.environ.get("GEMINI_MODEL") or "gemini-3.1-flash-lite"
        texts = write_takes(client, model, clips, transcript, handle, genre, source_title)
    except Exception as e:  # noqa: BLE001 — clips go out without a take
        print(f"   ⚠️ AI take failed ({type(e).__name__}: {str(e)[:160]}) — no take this time.")
        return {}

    def one(i):
        text = texts[i]
        audio = os.path.join(job_dir, f"{os.path.splitext(clip_names[i])[0]}.take.wav")
        secs = speak(client, text, audio, voice)
        secs = _fit(audio, secs) if secs else None
        if not secs:
            if os.path.exists(audio):
                os.remove(audio)
            return i, {"text": text, "audio": None, "voice_seconds": 0.0}
        return i, {"text": text, "audio": os.path.basename(audio), "voice_seconds": round(secs, 2)}

    todo = []
    for i in sorted(texts):
        clip_s = float(clips[i]["end"]) - float(clips[i]["start"])
        if clip_s + MAX_VOICE_SECONDS + TAKE_PAD_SECONDS + outro_seconds > SHORTS_LIMIT_SECONDS:
            print(f"   ℹ️ Clip {i + 1} is {clip_s:.0f}s: no take, it would pass Shorts' 3 minutes.")
            continue
        todo.append(i)
    takes = {}
    # Three at a time: the preview voice models have low per-minute limits.
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i, rec in pool.map(one, todo):
            clips[i]["ai_take"] = rec["text"]
            takes[clip_names[i]] = rec
    voiced = sum(1 for r in takes.values() if r["audio"])
    print(f"   ✅ Take ready for {len(takes)}/{len(clips)} clips ({voiced} voiced)")
    return takes
