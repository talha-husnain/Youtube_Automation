"""Shared pieces of the generated Shorts: songs, movie dubs, cricket, quiz, AI music.

Comedy cuts and frames someone's footage (main.py, framed_layout.py). These
three video types make most or all of the picture themselves, so they share
what is here: a neutral job name, the Gemini client, AI voice lines, a
caption transcript built from timed lines, an animated 1080x1920 background
with a text layer, and the job's metadata in the shape the dashboard reads.

Everything a viewer sees or hears on the generated parts is ours: the
background is an ffmpeg gradient, the sounds are synthesised (aevalsrc) and
the voices are Gemini's. Only song_shorts' "I own this music" mode and the
movie scene's picture come from the source link.
"""
import glob
import json
import os
import random
import subprocess
import time
import wave
from concurrent.futures import ThreadPoolExecutor

import framed_layout as fl
from ffmpeg_utils import (video_encode_args, QUALITY, METADATA_SCRUB, LOUDNORM_FILTER,
                          escape_filter_value)

OUT_W, OUT_H = fl.OUT_W, fl.OUT_H
FPS = 30
# Captions of a generated short hang from here (PlayResY 288 units, the
# caption burner's), in the lower third above the platform UI.
CAPTION_TOP_PX = 1430
# Gemini voices (https://ai.google.dev/gemini-api/docs/speech-generation).
MALE_VOICES = ["Puck", "Charon", "Fenrir", "Orus", "Iapetus"]
FEMALE_VOICES = ["Kore", "Aoede", "Leda", "Zephyr", "Despina"]
WHOOSH = "if(lt(t,0.3),0.35*sin(2*PI*(300*t+1800*t*t))*(t/0.3)*(1-t/0.3)*4,0)"
# Real swooshes replace the synthesised chirp above wherever a card says WHOOSH: six Kenney
# interface sounds (CC0) that a Gemini listening pass scored 8-9/10 as a card's slide-in, out of
# 26 tried (22-oct-2026). All peak at -1 dBFS. At -11 dB a listening pass of a finished Short heard
# them "barely audible, swallowed by the music"; at -5 dB "a bit too loud, fighting the voice": -8 dB.
# Both passes heard the music too close to the voice: the ducked bed went from -24 to -28 LUFS.
SFX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sfx")
SFX_DB = float(os.environ.get("SFX_DB") or -8)


def whoosh_files():
    if os.environ.get("REAL_SFX", "1") == "0":
        return []
    return sorted(glob.glob(os.path.join(SFX_DIR, "*.ogg")))
# Background music the user adds (royalty-free tracks, e.g. YouTube Audio
# Library or Pixabay): nothing is downloaded or shipped with the app.
MUSIC_DIR = os.environ.get("MUSIC_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "music")
MUSIC_EXT = (".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac")
# Far under the voices (LOUDNORM_FILTER, -14): a bed, not a song.
BED_LOUDNORM = "loudnorm=I=-30:TP=-8:LRA=11"
# A render whose captions are burned in a second pass: veryfast at CRF 16 took
# 29 s where the default medium CRF 18 took 57 s on a 61 s Short (15-oct-2026),
# and the caption pass re-encodes at full quality anyway.
FAST_PASS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p"]


def neutral_stem(prefix):
    """File stem without the source title, which may carry a creator's name."""
    return time.strftime(f"{prefix}_%Y-%m-%d_%H%M%S")


def gemini():
    from google import genai
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("This video type needs GEMINI_API_KEY in .env.")
    return genai.Client(api_key=key)


def text_model():
    return os.environ.get("GEMINI_MODEL") or "gemini-3.1-flash-lite"


TRANSIENT = ("getaddrinfo", "ConnectError", "ConnectTimeout", "ReadTimeout", "RemoteProtocolError",
             "503", "500", "502", "504", "UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED", "Server disconnected")


def ask_json(client, schema, contents, tools=None, model=None, tries=3):
    """One Gemini call validated against a pydantic schema. A network or server
    blip is retried (this laptop's DNS dropped for minutes on 15-oct-2026 and a
    10-minute video died at its picture step, its voices already made)."""
    from google.genai import types
    for attempt in range(tries):
        try:
            r = client.models.generate_content(
                model=model or text_model(), contents=contents,
                config=types.GenerateContentConfig(response_mime_type="application/json",
                                                   response_schema=schema, tools=tools))
            return schema.model_validate_json(r.text)
        except Exception as e:  # noqa: BLE001 — only blips are retried
            if attempt == tries - 1 or not any(m in f"{type(e).__name__} {e}" for m in TRANSIENT):
                raise
            print(f"   🔁 Gemini call failed ({type(e).__name__}); trying again in {10 * (attempt + 1)} s.")
            time.sleep(10 * (attempt + 1))


def caption_margin():
    return round(CAPTION_TOP_PX * 288 / OUT_H)


def speech_spans(wav, gap=0.12, floor_db=-32.0):
    """[(start, end)] where the voice in a clean TTS wav is speaking: 20 ms
    frames louder than ``floor_db`` below the peak, pauses shorter than ``gap``
    bridged. [] when the file cannot be read."""
    try:
        import numpy as np
        with wave.open(wav, "rb") as w:
            rate, n = w.getframerate(), w.getnframes()
            if w.getsampwidth() != 2 or not n:
                return []
            data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32)
            if w.getnchannels() > 1:
                data = data.reshape(-1, w.getnchannels()).mean(axis=1)
    except (OSError, wave.Error, EOFError, ImportError, ValueError):
        return []
    hop = max(1, rate // 50)
    frames = len(data) // hop
    if not frames:
        return []
    rms = np.sqrt((data[:frames * hop].reshape(frames, hop) ** 2).mean(axis=1)) + 1e-6
    loud = 20 * np.log10(rms / rms.max()) > floor_db
    spans, start = [], None
    for k, on in enumerate(loud):
        t = k * hop / rate
        if on and start is None:
            start = t
        elif not on and start is not None:
            spans.append([start, t])
            start = None
    if start is not None:
        spans.append([start, frames * hop / rate])
    merged = []
    for s in spans:
        if merged and s[0] - merged[-1][1] < gap:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    return [(a, b) for a, b in merged if b - a >= 0.06]


def _spread(words, weights, spans, a, b):
    """Words over the speech between a and b, by length."""
    inside = [(max(s, a), min(e, b)) for s, e in spans if min(e, b) > max(s, a)] or [(a, b)]
    total = sum(e - s for s, e in inside) or 1e-3
    mass = float(sum(weights)) or 1.0

    def at(fraction):
        left = fraction * total
        for s, e in inside:
            if left <= e - s + 1e-9:
                return s + left
            left -= e - s
        return inside[-1][1]
    out, acc = [], 0.0
    for wt in weights:
        s, acc = at(acc / mass), acc + wt
        out.append((s, at(acc / mass)))
    return out


def spoken_weight(word):
    """How long a word takes to say, roughly: numbers are short to write and
    long to say ("680" = "chhe sau assi"), abbreviations go letter by letter."""
    core = word.strip(".,?!;:'\"()")
    if any(ch.isdigit() for ch in core):
        return 3 + 3 * sum(ch.isdigit() for ch in core)
    if 2 <= len(core) <= 4 and core.isupper():
        return 3 * len(core)
    return len(core) + 2


def word_times(words, spans, length):
    """[(start, end)] in wav time for ``words`` spoken in ``spans``.

    A plain spread by length put a sentence end 3 s early on a real narration
    line (15-oct-2026, checked against Whisper's word times): TTS voices pause
    longest at full stops, and numbers take long to say. So the sentence ends
    (. ? !) take the longest pauses of the line, in order; each comma then
    takes the clear pause nearest where it is expected inside its sentence;
    the words between two anchors share only the speech between them."""
    spans = spans or [(0.0, length)]
    weights = [spoken_weight(w) for w in words]
    pauses = [(spans[i][1], spans[i + 1][0]) for i in range(len(spans) - 1)]
    strong = [k for k, w in enumerate(words[:-1]) if w[-1:] in ".?!"]
    anchors = {}                                  # word index -> (pause start, pause end)
    if strong and len(pauses) >= len(strong):
        longest = sorted(sorted(pauses, key=lambda p: p[1] - p[0], reverse=True)[:len(strong)])
        anchors.update(zip(strong, longest))

    def expect(k, lo_k, lo_t, hi_k, hi_t):
        mass = sum(weights[lo_k + 1:hi_k + 1]) or 1
        return lo_t + (hi_t - lo_t) * sum(weights[lo_k + 1:k + 1]) / mass
    soft = [k for k, w in enumerate(words[:-1]) if w[-1:] in ",;:" and k not in anchors]
    for k in soft:
        lo = max([j for j in anchors if j < k], default=-1)
        hi = min([j for j in anchors if j > k], default=len(words) - 1)
        lo_t = anchors[lo][1] if lo >= 0 else spans[0][0]
        hi_t = anchors[hi][0] if hi in anchors else spans[-1][1]
        e = expect(k, lo, lo_t, hi, hi_t)
        taken = set(anchors.values())
        options = [p for p in pauses if p not in taken and p[1] - p[0] >= 0.15 and lo_t < p[0] < hi_t
                   and abs(p[0] - e) <= 0.9]
        if options:
            anchors[k] = min(options, key=lambda p: abs(p[0] - e) - (p[1] - p[0]))
    # Anchors must run forward in time; drop any that would not.
    ordered, last = [], spans[0][0]
    for k in sorted(anchors):
        if anchors[k][0] > last:
            ordered.append((k, anchors[k][0]))
            ordered.append((k, anchors[k][1]))     # the next words start after the pause
            last = anchors[k][1]
    anchors = [(-1, spans[0][0])] + ordered
    out = [None] * len(words)
    bounds = [anchors[0]] + anchors[1:] + [(len(words) - 1, spans[-1][1])]
    k0, t0 = -1, spans[0][0]
    for k1, t1 in bounds[1:]:
        if k1 > k0 and t1 > t0:
            for j, ts in zip(range(k0 + 1, k1 + 1), _spread(words[k0 + 1:k1 + 1], weights[k0 + 1:k1 + 1],
                                                             spans, t0, t1)):
                out[j] = ts
            k0 = k1
        t0 = max(t0, t1)
    # Anything left (no speech found for it) shares the tail.
    if None in out:
        k = out.index(None)
        for j, ts in zip(range(k, len(words)), _spread(words[k:], weights[k:], spans, t0, max(t0 + 0.1, length))):
            out[j] = ts
    return [(s, max(e, s + 0.05)) for s, e in out]


_whisper = {}
_whisper_lock = __import__("threading").Lock()


def whisper_words(wav, language="ur"):
    """[(start, end)] of each word Whisper hears in our own voice line, or [].

    Roman Urdu is the Urdu sentence letter for letter, so Whisper (writing Urdu
    script) usually finds exactly as many words as the script has: 22 of 22 and
    27 of 27 on a real narration line, 15-oct-2026. Model loaded once."""
    try:
        from faster_whisper import WhisperModel
        with _whisper_lock:
            if "m" not in _whisper:
                _whisper["m"] = WhisperModel(os.environ.get("CAPTION_WHISPER") or "small", device="cpu",
                                             compute_type="int8", cpu_threads=4)
            model = _whisper["m"]
            segs, _info = model.transcribe(wav, language=language, word_timestamps=True, vad_filter=False,
                                           condition_on_previous_text=False, beam_size=1)
            return [(w.word.strip(), float(w.start), float(w.end))
                    for s in segs for w in (s.words or []) if w.word.strip()]
    except Exception:  # noqa: BLE001 — the pause method takes over
        return []


CLAUSE_END = tuple(".,?!;:۔،؟")


def _units(word):
    """How many words Whisper writes for one Roman word: "maidan-e-Karbala"
    is two in Urdu script (the izafat -e- joins the first), "ahl-o-ayal" three."""
    parts = [p for p in word.split("-") if p]
    return max(1, len([p for p in parts if p.lower() != "e"]))


def _grid(heard, n_units, weights):
    """Times for n units spread over Whisper's words by length, using its real
    word starts and ends as the clock (a word count that differs a little
    still lands each unit near the right sound)."""
    m = len(heard)
    total = float(sum(weights)) or 1.0

    def at(x):
        k = min(int(x), m - 1)
        s, e = heard[k][1], heard[k][2]
        return s + (min(x, m) - k) * (e - s)
    out, acc = [], 0.0
    for wt in weights:
        a = at(acc / total * m)
        acc += wt
        out.append((a, at(acc / total * m)))
    return out


def align_heard(words, heard):
    """[(start, end)] per word from Whisper's (text, start, end) words: exact
    when the counts match, else clause by clause (both sides end clauses at
    punctuation), else over the whole line. None when nothing was heard."""
    if not heard or not words:
        return None
    units, owner = [], []
    for k, w in enumerate(words):
        n = _units(w)
        for j in range(n):
            units.append(w if j == n - 1 else w.split("-")[0])
            owner.append(k)
    weights = [spoken_weight(u) for u in units]

    def clauses(seq, text_of, ends):
        out, cur = [], []
        for i, item in enumerate(seq):
            cur.append(i)
            if text_of(item).endswith(ends):
                out.append(cur)
                cur = []
        return out + ([cur] if cur else [])
    # Whisper marks clauses its own way (on 8 real lines: the same commas, only
    # the full stops, or nothing), so try commas, then sentences, then the line.
    times = None
    for ends in (CLAUSE_END, tuple(".?!۔؟")):
        ours, theirs = clauses(units, lambda u: u, ends), clauses(heard, lambda h: h[0], ends)
        if len(ours) == len(theirs) and len(ours) > 1:
            times = []
            for oc, tc in zip(ours, theirs):
                hs = [heard[i] for i in tc]
                if len(oc) == len(hs):
                    times += [(h[1], h[2]) for h in hs]
                else:
                    times += _grid(hs, len(oc), [weights[i] for i in oc])
            break
    if times is None:
        times = ([(h[1], h[2]) for h in heard] if len(units) == len(heard)
                 else _grid(heard, len(units), weights))
    out = []
    for k in range(len(words)):
        mine = [t for t, o in zip(times, owner) if o == k]
        out.append((mine[0][0], max(mine[-1][1], mine[0][0] + 0.05)))
    for k in range(1, len(out)):           # never run backwards
        if out[k][0] < out[k - 1][0]:
            out[k] = (out[k - 1][0], max(out[k][1], out[k - 1][0] + 0.05))
    return out


def line_word_times(text, wav, length, language="ur"):
    """[(start, end)] per word of ``text`` in its own voice wav: Whisper's word
    times when it heard the same number of words, else spread over the real
    speech (speech_spans + word_times), else by length. EXACT_CAPTIONS=pauses
    skips Whisper, =0 uses length only."""
    words = (text or "").split()
    mode = os.environ.get("EXACT_CAPTIONS", "whisper")
    if not words or not wav or mode == "0":
        return None
    import free_voice
    told = free_voice.heard_words(wav)        # the free voice says when each word is spoken
    if told:
        got = align_heard(words, told)
        if got:
            return got
    if mode == "whisper":
        got = align_heard(words, whisper_words(wav, language))
        if got:
            return got
    spans = speech_spans(wav)
    return word_times(words, spans, length) if spans else None


def timed_transcript(lines, language="ur"):
    """[(text, start, end[, wav])] -> the transcript shape the caption burner reads.

    Voice models give no word times. With the line's wav, its words are spread
    over the moments the voice is actually speaking (speech_spans), so the
    highlight waits through pauses; without it, over the line's whole time by
    length (the same spread the take's gold highlight uses)."""
    segs = []
    for line in lines:
        text, start, end = line[:3]
        wav = line[3] if len(line) > 3 else None
        words = (text or "").split()
        if not words or end <= start:
            continue
        exact = line_word_times(text, wav, end - start, "en" if language == "en" else "ur") if wav else None
        if exact:
            times = [(start + a, start + b) for a, b in exact]
        else:
            weights = [len(w) + 2 for w in words]
            t, times = start, []
            for wt in weights:
                d = (end - start) * wt / sum(weights)
                times.append((t, t + d))
                t += d
        out = [{"word": " " + w, "start": round(a, 3), "end": round(min(b, end), 3)} for w, (a, b) in zip(words, times)]
        segs.append({"start": start, "end": end, "text": text, "words": out})
    return {"language": language, "segments": segs}


def wav_seconds(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def speed_up(path, factor):
    """atempo a wav in place; returns its new length."""
    tmp = path + ".fast.wav"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", path, "-af", f"atempo={factor:.3f}",
                    "-ar", "24000", "-ac", "1", tmp], check=True, timeout=60)
    os.replace(tmp, path)
    return wav_seconds(path)


def voice_lines(client, items, job_dir, prefix):
    """items: [{"text", "voice", "style", "language"?}] -> [(wav path, seconds) | (None, 0.0)].

    The free Microsoft voices (free_voice.py) read every line they can unless
    VOICE_ENGINE=gemini; a line they fail, or one in a language they do not
    take, is read by Gemini. The free voice goes one line at a time with a
    pause (Microsoft refuses bursts); Gemini three at a time, 8 calls back to
    back met no rate limit (8-oct-2026)."""
    import ai_take
    import free_voice
    import local_voice
    eng = free_voice.engine()
    use_free = eng == "edge" and not free_voice.resting()
    use_local = eng in ("edge", "omni") and local_voice.available()
    free = free_voice.voice_items(client, items) if use_free or use_local else [None] * len(items)
    path_of = [os.path.join(job_dir, f".{prefix}_{k + 1}.wav") for k in range(len(items))]
    out = [None] * len(items)
    for k in range(len(items)):
        if use_free and free[k]:
            secs = free_voice.speak(free[k][0], path_of[k], free[k][1], free[k][2])
            if secs:
                out[k] = (path_of[k], secs)
            time.sleep(free_voice.PAUSE)
    # What the edge voice could not read (all of it with VOICE_ENGINE=omni) goes to the free local
    # voice before the paid one: when edge rested, every line used to cost a Gemini call.
    todo = [k for k in range(len(items)) if out[k] is None and free[k]] if use_local else []
    for k in todo:
        if os.path.exists(path_of[k] + ".words.json"):
            os.remove(path_of[k] + ".words.json")
    if todo:
        print(f"   🗣️ Local voice reads {len(todo)} line(s)...")
    for k, secs in zip(todo, local_voice.speak_many([(free[k][0], path_of[k], free_voice.gender(items[k].get("voice")),
                                                       free[k][2]) for k in todo])):
        if secs:
            out[k] = (path_of[k], secs)

    def gemini_line(k):
        it = items[k]
        if os.path.exists(path_of[k] + ".words.json"):
            os.remove(path_of[k] + ".words.json")
        secs = ai_take.speak(client, it["text"], path_of[k], it.get("voice") or ai_take.DEFAULT_VOICE,
                             it.get("style"), **({"language": it["language"]} if it.get("language") else {}))
        return (path_of[k], secs) if secs else (None, 0.0)
    rest = [k for k in range(len(items)) if out[k] is None]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for k, got in zip(rest, pool.map(gemini_line, rest)):
            out[k] = got
    return out


RETRY_WAIT = 30


def voice_all(client, items, job_dir, prefix, wait=None):
    """voice_lines, then once more after a pause for the lines that failed;
    raises when a line still has no voice. A quiz went up with 8 of its 10
    lines silent on 18-oct-2026 (a DNS outage, free voice and Gemini both
    down): only an every-line-failed check guarded it."""
    said = voice_lines(client, items, job_dir, prefix)
    missing = [k for k, (p, _s) in enumerate(said) if not p]
    if missing:
        print(f"   🔁 {len(missing)} voice line(s) failed; trying them again in {RETRY_WAIT if wait is None else wait} s...")
        time.sleep(RETRY_WAIT if wait is None else wait)
        for k, got in zip(missing, voice_lines(client, [items[k] for k in missing], job_dir, prefix + "r")):
            if got[0]:
                said[k] = got
        missing = [k for k, (p, _s) in enumerate(said) if not p]
    if missing:
        # "network" is what my_channels.TRANSIENT reads: the channel waits, the try is not used.
        raise RuntimeError(f"{len(missing)} of {len(items)} voice lines could not be made (the network or the "
                           "voice service is down); made again later.")
    return said


def seo_or_fail(clips, *args, wait=None, **kwargs):
    """seo_copy.apply for a generated Short, which has no copy of its own: once
    more after a pause, then the job fails. The same quiz went up with an
    empty description and no tags when the SEO call hit the outage."""
    import seo_copy
    if os.environ.get("SEO_COPY", "1").strip() == "0" or not os.getenv("GEMINI_API_KEY"):
        return seo_copy.apply(clips, *args, **kwargs)
    done = seo_copy.apply(clips, *args, **kwargs)
    if not done:
        time.sleep(RETRY_WAIT if wait is None else wait)
        done = seo_copy.apply(clips, *args, **kwargs)
    if not done:
        raise RuntimeError("The title and description could not be written (the network or Gemini is down); "
                           "made again later.")
    import script_craft as craft
    client = gemini()
    for c in clips:
        if c.get("seo_title"):
            facts = " ".join(filter(None, [seo_copy._clip_text(args[0] if args else None, c, 3000),
                                           kwargs.get("source_title", ""), kwargs.get("context", "")]))
            c["seo_title"] = craft.pick_title(client, c["seo_title"], facts)
    return done


def ass_header(extra_styles=()):
    """Script header at the canvas size with the end card's styles."""
    return [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {OUT_W}", f"PlayResY: {OUT_H}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        *(s.format(gold=fl._ass_colour(fl.GOLD), ink=fl._ass_colour("#000000"))
          for s in fl.END_CARD_STYLES),
        *extra_styles,
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]


def dialogue(layer, start, end, style, text):
    return f"Dialogue: {layer},{fl._ts(start)},{fl._ts(end)},{style},,0,0,0,,{text}"


def style(name, font, size, colour="#FFFFFF", outline=0, shadow=0, align=5, bold=1,
          secondary=None, spacing=0):
    c = fl._ass_colour(colour)
    s2 = fl._ass_colour(secondary) if secondary else c
    return (f"Style: {name},{font},{size},{c},{s2},&H00000000,&H96000000,{bold},0,0,0,100,100,"
            f"{spacing},0,1,{outline},{shadow},{align},60,60,0,1")


def blend(hex_color, base, share):
    """``share`` of hex_color mixed into base. Raw team or mood colours at full
    strength made garish, muddy backgrounds (first renders, 8-oct-2026)."""
    try:
        a = [int(hex_color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
        b = [int(base.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    except (ValueError, AttributeError):
        return base
    return "#" + "".join(f"{round(x * share + y * (1 - share)):02X}" for x, y in zip(a, b))


def music_tracks():
    try:
        return sorted(f for f in os.listdir(MUSIC_DIR) if f.lower().endswith(MUSIC_EXT))
    except OSError:
        return []


def music_track(kind=None):
    """A random track from music/<kind>/ (the beds music_beds.py makes for a
    channel kind), else from the music folder, or None when both are empty."""
    if kind:
        sub = os.path.join(MUSIC_DIR, kind)
        try:
            own = sorted(f for f in os.listdir(sub) if f.lower().endswith(MUSIC_EXT))
        except OSError:
            own = []
        if own:
            return os.path.join(sub, random.choice(own))
    tracks = music_tracks()
    return os.path.join(MUSIC_DIR, random.choice(tracks)) if tracks else None


def ambient_events(total, seed=7):
    """Soft light dots drifting up behind everything: depth on a flat gradient."""
    rnd = random.Random(seed)
    ev = []
    for _ in range(12):
        r = rnd.randint(18, 70)
        x, y0 = rnd.randint(40, OUT_W - 40), rnd.randint(300, OUT_H + 200)
        x1, y1 = x + rnd.randint(-80, 80), y0 - rnd.randint(250, 700)
        alpha = rnd.choice(["D0", "DC", "E6"])
        ev.append(dialogue(0, 0, total, "Shape",
                           rf"{{\an5\move({x},{y0},{x1},{y1})\1c&HFFFFFF&\1a&H{alpha}&\bord0\shad0"
                           rf"\blur8\p1}}{fl._circle(r)}{{\p0}}"))
    return ev


def bg_source(colors, seconds):
    """Slowly moving gradient over the whole canvas (lavfi input)."""
    cs = [c.lstrip("#") for c in colors][:3] or ["2B0F3D", "8B5CF6"]
    while len(cs) < 2:
        cs.append(cs[0])
    stops = ":".join(f"c{i}=0x{c}" for i, c in enumerate(cs))
    return (f"gradients=s={OUT_W}x{OUT_H}:{stops}:nb_colors={len(cs)}:x0=0:y0=0:"
            f"x1={OUT_W}:y1={OUT_H}:speed=0.012:r={FPS}:d={seconds:.3f}")


def render(out_path, seconds, colors, events, extra_styles=(), voices=(), sfx=(),
           music=None, visualizer=False, silent=False, fades=None, music_seconds=None, bed=None,
           images=(), bg_image=None, bg_video=None, fast=False, stickers=()):
    """Make a 1080x1920 short: gradient (or ``bg_image``), an optional wave
    line from ``music``, pictures, then the text layer.

    voices: [(wav, at)]  sfx: [(aevalsrc expr, seconds, at)]
    music: (path, start in file, volume)  silent: no sound at all (a song
    added later in the YouTube app goes on a silent track).
    fades: (seconds, music length) fades the music in and out.
    music_seconds: how long the music (and its wave) run; the end card after
    it is quiet.
    bed: (track, seconds) background music under the voices, looped, faded.
    images: [{"path", "t0", "t1", "x", "y", "zoom"}] RGBA pictures centred at (x, y)
    between t0 and t1, fading in and out and growing by ``zoom`` (0.05 = 5%).
    bg_image: a picture for the whole background instead of the gradient,
    panning slowly (the AI songs' cover art).
    bg_video: a finished background (broll.py's stock footage at the canvas
    size, at least ``seconds`` long) instead of either.
    stickers: stickers.place() output, animated emoji over the picture and under the text.
    """
    ass_path = os.path.join(os.path.dirname(os.path.abspath(out_path)),
                            f"gen_{os.getpid()}_{int(time.time() * 1000) % 10**8}.ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(ass_header(extra_styles) + list(events)) + "\n")
    mixed = None
    if bg_video and not music:
        # Over footage, audio filtered in the same graph as the video stalled
        # the render for good (the music bed at 47.6 s every time, bisected
        # input by input, 15-oct-2026; never on the gradient). So the sound is
        # mixed first on its own, as the long videos' renderer does, and the
        # picture pass only maps the finished track.
        mixed = mix_audio(ass_path[:-4] + "_audio.wav", seconds, voices, sfx, bed)
        voices, sfx, bed = [], [], None
    if bg_video:
        cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", bg_video]
        bg_image = None
    elif bg_image:
        cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-loop", "1", "-framerate", str(FPS),
               "-t", f"{seconds:.3f}", "-i", bg_image]
    else:
        cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", bg_source(colors, seconds)]
    cmd += ["-f", "lavfi", "-t", f"{seconds:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
    graph, v, mix, idx = [], "[0:v]", ["[1:a]"], 2
    if bg_video and os.environ.get("BROLL_SHADE", "1") != "0":
        # Footage gets a dark fade top and bottom so the title and captions read.
        import broll
        cmd += ["-i", broll.shade(OUT_W, OUT_H)]
        graph.append(f"[0:v][{idx}:v]overlay=0:0:format=auto[shaded]")
        v, idx = "[shaded]", idx + 1
    if bg_image:
        # 10% larger than the canvas, then a slow drift of the crop window:
        # movement for the price of a crop (zoompan per frame is far slower).
        graph.append(f"[0:v]scale={round(OUT_W * 1.1)}:{round(OUT_H * 1.1)}:force_original_aspect_ratio=increase,"
                     f"crop={OUT_W}:{OUT_H}:x='(iw-ow)/2+(iw-ow)/2*sin(t/9)':y='(ih-oh)/2+(ih-oh)/2*sin(t/13)',"
                     f"setsar=1,eq=brightness=-0.05:saturation=1.08,fps={FPS}[bgv]")
        v = "[bgv]"
    if music:
        path, start, vol = music
        cmd += ["-ss", f"{start:.3f}", "-t", f"{music_seconds or seconds:.3f}", "-i", path]
        m, idx = idx, idx + 1
        split = f"[{m}:a]asplit=2[mv][ma]" if visualizer else f"[{m}:a]anull[ma]"
        graph.append(split)
        if visualizer:
            # A gold wave line that moves with the music. Bars from showfreqs
            # read as a grey block on a phone (first render, 8-oct-2026).
            graph.append(f"[mv]showwaves=s=1080x220:mode=cline:rate={FPS}:scale=sqrt:"
                         f"colors=0xFFD23F,format=rgba,colorchannelmixer=aa=0.8[viz]")
            graph.append(f"{v}[viz]overlay=0:1420:eof_action=pass[withviz]")
            v = "[withviz]"
        if silent:
            graph.append("[ma]anullsink")
        else:
            fade = (f"afade=t=in:d={fades[0]:g},afade=t=out:st={max(0.0, fades[1] - fades[0]):.3f}"
                    f":d={fades[0]:g}," if fades else "")
            graph.append(f"[ma]{fade}volume={vol},aresample=48000,aformat=channel_layouts=stereo[mus]")
            mix.append("[mus]")
    if bed:
        idx = _bed_input(cmd, graph, mix, idx, bed)
    for k, im in enumerate(images):
        t0, t1 = float(im["t0"]), float(im["t1"])
        d, z = max(0.5, t1 - t0), float(im.get("zoom", 0.05))
        # Over footage a picture input that ended early (a photo card gone at
        # 6 s) stalled the render for good about 170 frames later; on the
        # gradient it never did (15-oct-2026, reproduced and bisected). There
        # each picture runs to the end, hidden after t1 by enable= and the fade.
        length = max(d, seconds - t0 + 0.5) if bg_video else d
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{length:.3f}", "-i", im["path"]]
        graph.append(f"[{idx}:v]format=rgba,setpts=PTS-STARTPTS+{t0:.3f}/TB,"
                     f"scale=w='trunc(iw*(1+{z:g}*(t-{t0:.3f})/{d:.3f})/2)*2':h=-2:eval=frame,"
                     f"fade=t=in:st={t0:.3f}:d=0.3:alpha=1,fade=t=out:st={max(t0, t1 - 0.3):.3f}:d=0.3:alpha=1"
                     f"[im{k}]")
        graph.append(f"{v}[im{k}]overlay=x='{float(im.get('x', OUT_W / 2)):.0f}-w/2':"
                     f"y='{float(im.get('y', OUT_H / 2)):.0f}-h/2':"
                     f"eof_action=pass:enable='between(t,{t0:.3f},{t1:.3f})'[v_im{k}]")
        v = f"[v_im{k}]"
        idx += 1
    if stickers:
        import stickers as stk
        for k, st in enumerate(stickers):
            # Over footage the input runs to the end like the pictures above (the ffmpeg 9 stall).
            inputs, filters, v = stk.overlay_args(st["path"], idx, st["t0"], st["t1"], st["x"], st["y"],
                                                  st.get("size", stk.SIZE), src=v, label=f"stk{k}",
                                                  alive_until=seconds if bg_video else None)
            cmd += inputs
            graph += filters
            idx += 1
    idx = _voice_sfx_inputs(cmd, graph, mix, idx, voices, sfx)
    graph.append(f"{v}ass=filename='{escape_filter_value(ass_path)}'"
                 f":fontsdir='{escape_filter_value(fl.FONTS_DIR)}',format=yuv420p[v]")
    picture = ass_path[:-4] + "_picture.mp4" if mixed else None
    if mixed:
        # The picture alone (no sound in this pass at all), then a join that
        # copies it: an audio stream in the picture pass, even a finished
        # track mapped as is, still stalled it.
        outputs = ["-map", "[v]", "-an", "-t", f"{seconds:.3f}", "-r", str(FPS),
                   *(FAST_PASS if fast else video_encode_args(QUALITY)), picture]
    else:
        _final_mix(graph, mix)
        outputs = ["-map", "[v]", "-map", "[a]", "-t", f"{seconds:.3f}", "-r", str(FPS),
                   *(FAST_PASS if fast else video_encode_args(QUALITY)), "-c:a", "aac", "-b:a", "192k",
                   *METADATA_SCRUB, "-movflags", "+faststart", out_path]
    try:
        r = subprocess.run(cmd + ["-filter_complex", ";".join(graph), *outputs],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                           # A render that stalls (one did, 15-oct-2026: 41 s of CPU in 15 min)
                           # fails in minutes, not after half an hour.
                           errors="replace", timeout=max(600, seconds * 12))
        if r.returncode != 0:
            raise RuntimeError(f"render failed: {r.stderr.strip()[-400:]}")
        if mixed:
            r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", picture, "-i", mixed,
                                "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                                "-t", f"{seconds:.3f}", *METADATA_SCRUB, "-movflags", "+faststart", out_path],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               errors="replace", timeout=300)
            if r.returncode != 0:
                raise RuntimeError(f"join failed: {r.stderr.strip()[-400:]}")
    finally:
        for temp in (ass_path, mixed, picture):
            if temp and os.path.exists(temp):
                os.remove(temp)
    return out_path


# Ducking (quality pass 2, 22-oct-2026): the bed sat at a fixed -30 LUFS, 16 dB under the voice, so it was
# either buried between lines or muddy under them. Ducked, it can sit at -24 and dip ~10 dB while anyone
# speaks (sidechain keyed by the voices); a limiter stops the summed peaks from clipping. MUSIC_DUCK=0: old mix.
def ducking():
    return os.environ.get("MUSIC_DUCK", "1").strip() != "0"


BED_DUCKED_LOUDNORM = "loudnorm=I=-28:TP=-6:LRA=11"
DUCK = "sidechaincompress=threshold=0.02:ratio=8:attack=15:release=400:makeup=1"
LIMIT = "alimiter=limit=0.95:level=0"


def _final_mix(graph, mix):
    """Every sound in ``mix`` summed into [a]; with a bed and voices, the bed ducked under the voices."""
    voices = [m for m in mix if m.startswith("[vo")]
    if len(mix) == 1:
        graph.append(f"{mix[0]}anull[a]")
        return
    parts = mix
    if ducking() and "[bed]" in mix and voices:
        graph.append(f"{''.join(voices)}amix=inputs={len(voices)}:normalize=0,asplit=2[vox][vkey]")
        graph.append(f"[bed][vkey]{DUCK}[bedd]")
        parts = [m for m in mix if m != "[bed]" and m not in voices] + ["[vox]", "[bedd]"]
    graph.append(f"{''.join(parts)}amix=inputs={len(parts)}:duration=first:normalize=0,{LIMIT}[a]")


def _bed_input(cmd, graph, mix, idx, bed):
    """The background bed: looped, cut to its length, quiet, faded in and out."""
    track, length = bed
    cmd += ["-stream_loop", "-1", "-i", track]
    graph.append(f"[{idx}:a]atrim=0:{length:.3f},asetpts=PTS-STARTPTS,"
                 f"{BED_DUCKED_LOUDNORM if ducking() else BED_LOUDNORM},"
                 f"afade=t=in:d=1,afade=t=out:st={max(0.0, length - 1.5):.3f}:d=1.5,"
                 f"aresample=48000,aformat=channel_layouts=stereo[bed]")
    mix.append("[bed]")
    return idx + 1


def _voice_sfx_inputs(cmd, graph, mix, idx, voices, sfx):
    for k, (wav, at) in enumerate(voices):
        cmd += ["-i", wav]
        ms = int(at * 1000)
        graph.append(f"[{idx}:a]{LOUDNORM_FILTER},aresample=48000,aformat=channel_layouts=stereo,"
                     f"adelay={ms}|{ms}[vo{k}]")
        mix.append(f"[vo{k}]")
        idx += 1
    files = whoosh_files() if any(s[0] == WHOOSH for s in sfx) else []
    for k, (expr, secs, at) in enumerate(sfx):
        ms = int(at * 1000)
        if expr == WHOOSH and files:
            # A real swoosh, a different one per card (sfx/: Kenney, CC0).
            cmd += ["-i", files[k % len(files)]]
            graph.append(f"[{idx}:a]volume={SFX_DB}dB,aresample=48000,aformat=channel_layouts=stereo,"
                         f"adelay={ms}|{ms}[sx{k}]")
            idx += 1
        else:
            graph.append(f"aevalsrc='{expr}':s=48000:d={secs:g},aformat=channel_layouts=stereo,"
                         f"adelay={ms}|{ms}[sx{k}]")
        mix.append(f"[sx{k}]")
    return idx


def mix_audio(path, seconds, voices=(), sfx=(), bed=None):
    """The voices, sound effects and bed of a Short mixed into one 48 kHz stereo
    wav of ``seconds``, the same filters render() uses, in an audio-only pass."""
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-t", f"{seconds:.3f}",
           "-i", "anullsrc=r=48000:cl=stereo"]
    graph, mix, idx = [], ["[0:a]"], 1
    if bed:
        idx = _bed_input(cmd, graph, mix, idx, bed)
    _voice_sfx_inputs(cmd, graph, mix, idx, voices, sfx)
    _final_mix(graph, mix)
    r = subprocess.run(cmd + ["-filter_complex", ";".join(graph), "-map", "[a]", "-t", f"{seconds:.3f}",
                              "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", path],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                       errors="replace", timeout=max(300, seconds * 6))
    if r.returncode != 0:
        raise RuntimeError(f"audio mix failed: {r.stderr.strip()[-400:]}")
    return path


def outro_seconds(cfg):
    """The end card's length on a generated Short: the brand setting, at most SHORT_OUTRO_SECONDS (1.5).
    A 3 s card is a swipe-away point and stops the Short from looping into itself (replays count as
    views); the comedy clips keep the brand setting."""
    try:
        cap = float(os.environ.get("SHORT_OUTRO_SECONDS") or 1.5)
    except ValueError:
        cap = 1.5
    return min(float(cfg["outro_seconds"]), max(1.0, cap))


def end_card(t0, secs):
    """Events + sound of the brand end card at t0 (the comedy one)."""
    cfg = fl.settings()
    if not cfg["outro"]:
        return [], []
    return (fl.end_card_events(t0, secs, cfg["handle"], cfg["bg"]),
            [(fl.end_card_audio(secs).split("'")[1], secs, t0)])


def finish(output_dir, stem, clips, transcript, pipeline, extra=None, margin=None):
    """Write metadata the dashboard reads, burn captions, announce each file.

    ``clips`` carry ``file`` (their rendered path) and ``captions`` (a
    transcript in clip time, or None for no captions). ``margin``: caption
    MarginV when the picture is a framed source (movie_dub), else the
    generated layout's."""
    margin = caption_margin() if margin is None else margin
    data = {"shorts": [{k: v for k, v in c.items() if k not in ("file", "captions")} for c in clips],
            "transcript": transcript or {"language": "none", "segments": []},
            "source_video": None, "output_format": "framed", **(extra or {})}
    with open(os.path.join(output_dir, f"{stem}_metadata.json"), "w") as f:
        json.dump(data, f, indent=2)
    cfg = fl.settings()
    fl.write_job(output_dir, cfg, margin,
                 {os.path.basename(c["file"]): c.get("video_title_for_youtube_short") or ""
                  for c in clips})
    # Numbers and names in a second colour (subtitles.EMPHASIS_COLOR); only generated Shorts come here.
    os.environ.setdefault("CAPTION_EMPHASIS", "1")
    for i, c in enumerate(clips):
        served = c["file"]
        if c.get("captions"):
            served = pipeline.auto_caption_clip(c["file"], c["captions"], 0.0, c["seconds"],
                                                margin_v=margin) or c["file"]
        if c.get("ai_voice"):
            from ffmpeg_utils import mark_ai_generated
            mark_ai_generated(served, c["ai_voice"])
        print(f"   ✅ Clip {i + 1} ready: {c['file']}")
        print(f"CLIP_READY {i} {os.path.basename(served)}")
