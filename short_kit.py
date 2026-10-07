"""Shared pieces of the generated Shorts: songs, movie dubs and cricket.

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
import json
import os
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


def ask_json(client, schema, contents, tools=None, model=None):
    """One Gemini call validated against a pydantic schema."""
    from google.genai import types
    r = client.models.generate_content(
        model=model or text_model(), contents=contents,
        config=types.GenerateContentConfig(response_mime_type="application/json",
                                           response_schema=schema, tools=tools))
    return schema.model_validate_json(r.text)


def caption_margin():
    return round(CAPTION_TOP_PX * 288 / OUT_H)


def timed_transcript(lines, language="ur"):
    """[(text, start, end)] -> the transcript shape the caption burner reads.

    Voice models give no word times, so each line's words share its time by
    length (the same spread the take's gold highlight uses)."""
    segs = []
    for text, start, end in lines:
        words = (text or "").split()
        if not words or end <= start:
            continue
        weights = [len(w) + 2 for w in words]
        t, out = start, []
        for w, wt in zip(words, weights):
            d = (end - start) * wt / sum(weights)
            out.append({"word": " " + w, "start": round(t, 3), "end": round(t + d, 3)})
            t += d
        segs.append({"start": start, "end": end, "text": text, "words": out})
    return {"language": language, "segments": segs}


def wav_seconds(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def speed_up(path, factor):
    """atempo a wav in place; returns its new length."""
    tmp = path + ".fast.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path, "-af", f"atempo={factor:.3f}",
                    "-ar", "24000", "-ac", "1", tmp], check=True, timeout=60)
    os.replace(tmp, path)
    return wav_seconds(path)


def voice_lines(client, items, job_dir, prefix):
    """items: [{"text", "voice", "style"}] -> [(wav path, seconds) | (None, 0.0)].

    Three at a time; 8 calls back to back met no rate limit (8-oct-2026)."""
    import ai_take

    def one(k):
        it = items[k]
        path = os.path.join(job_dir, f".{prefix}_{k + 1}.wav")
        secs = ai_take.speak(client, it["text"], path, it.get("voice") or ai_take.DEFAULT_VOICE,
                             it.get("style"))
        return (path, secs) if secs else (None, 0.0)

    with ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(one, range(len(items))))


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


def bg_source(colors, seconds):
    """Slowly moving gradient over the whole canvas (lavfi input)."""
    cs = [c.lstrip("#") for c in colors][:3] or ["2B0F3D", "8B5CF6"]
    while len(cs) < 2:
        cs.append(cs[0])
    stops = ":".join(f"c{i}=0x{c}" for i, c in enumerate(cs))
    return (f"gradients=s={OUT_W}x{OUT_H}:{stops}:nb_colors={len(cs)}:x0=0:y0=0:"
            f"x1={OUT_W}:y1={OUT_H}:speed=0.012:r={FPS}:d={seconds:.3f}")


def render(out_path, seconds, colors, events, extra_styles=(), voices=(), sfx=(),
           music=None, visualizer=False, silent=False, video=None, video_box=None, fades=None,
           music_seconds=None):
    """Make a 1080x1920 short: gradient (or ``video`` placed in ``video_box``),
    an optional audio-reactive bar layer from ``music``, then the text layer.

    voices: [(wav, at)]  sfx: [(aevalsrc expr, seconds, at)]
    music: (path, start in file, volume)  silent: no sound at all (a song
    added later in the YouTube app goes on a silent track).
    fades: (seconds, music length) fades the music in and out.
    music_seconds: how long the music (and its wave) run; the end card after
    it is quiet.
    """
    ass_path = os.path.join(os.path.dirname(os.path.abspath(out_path)),
                            f"gen_{os.getpid()}_{int(time.time() * 1000) % 10**8}.ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(ass_header(extra_styles) + list(events)) + "\n")
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", bg_source(colors, seconds),
           "-f", "lavfi", "-t", f"{seconds:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
    graph, v, mix, idx = [], "[0:v]", ["[1:a]"], 2
    if video:
        x, y, w, h = video_box
        cmd += ["-i", video]
        graph.append(f"[{idx}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                     f"crop={w}:{h},setsar=1,fps={FPS}[src]")
        graph.append(f"{v}[src]overlay={x}:{y}:eof_action=repeat[withsrc]")
        v, idx = "[withsrc]", idx + 1
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
    for k, (wav, at) in enumerate(voices):
        cmd += ["-i", wav]
        ms = int(at * 1000)
        graph.append(f"[{idx}:a]{LOUDNORM_FILTER},aresample=48000,aformat=channel_layouts=stereo,"
                     f"adelay={ms}|{ms}[vo{k}]")
        mix.append(f"[vo{k}]")
        idx += 1
    for k, (expr, secs, at) in enumerate(sfx):
        ms = int(at * 1000)
        graph.append(f"aevalsrc='{expr}':s=48000:d={secs:g},aformat=channel_layouts=stereo,"
                     f"adelay={ms}|{ms}[sx{k}]")
        mix.append(f"[sx{k}]")
    graph.append(f"{v}ass=filename='{escape_filter_value(ass_path)}'"
                 f":fontsdir='{escape_filter_value(fl.FONTS_DIR)}',format=yuv420p[v]")
    graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0[a]"
                 if len(mix) > 1 else "[1:a]anull[a]")
    try:
        r = subprocess.run(cmd + ["-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
                                  "-t", f"{seconds:.3f}", "-r", str(FPS),
                                  *video_encode_args(QUALITY), "-c:a", "aac", "-b:a", "192k",
                                  *METADATA_SCRUB, "-movflags", "+faststart", out_path],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                           errors="replace", timeout=1800)
        if r.returncode != 0:
            raise RuntimeError(f"render failed: {r.stderr.strip()[-400:]}")
    finally:
        if os.path.exists(ass_path):
            os.remove(ass_path)
    return out_path


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
