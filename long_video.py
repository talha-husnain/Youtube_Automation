"""Weekly long video: the week's best Shorts joined into one 16:9 YouTube video.

Each Short keeps its picture, captions and AI take; only its end card (the
last ``outro_seconds`` of the file, frame.json) is cut, since a FOLLOW card
every minute would wreck a long video. The Short sits in the middle of a
1920x1080 frame over a blurred copy of itself, with its number and hook on
the left and the channel handle on the right. A short intro card opens it
and one subscribe card closes it.

Segments are encoded with identical settings and joined with the concat
demuxer (no second encode). Chapter times come from the measured segment
lengths, in code; Gemini writes only the title, intro paragraph and
hashtags (Roman Urdu, never the creator's name).

Why bother: a long video earns from ads on its own views, where Shorts
share a pool, and a top-N compilation is a format Shorts channels already
use for their long-form tab.
"""
import json
import os
import re
import shutil
import subprocess
import textwrap
import time
from typing import List

from pydantic import BaseModel

ROOT = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1920, 1080, 30
INTRO_SECONDS, OUTRO_SECONDS = 3.5, 6.0
MIN_SHORTS, MAX_SHORTS = 3, 15
MAX_MINUTES = 15
NUM_FONT = os.path.join(ROOT, "fonts", "Anton-Regular.ttf")
TEXT_FONT = os.path.join(ROOT, "fonts", "Montserrat-ExtraBold.ttf")
GOLD = "#F2C14E"
VIDEO_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS),
              "-video_track_timescale", "30000", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]


class LongCopy(BaseModel):
    title: str
    intro: str
    hashtags: List[str]


COPY_PROMPT = """You write YouTube copy for a Pakistani comedy channel ({handle}). This long video
joins its {n} best Shorts of the week. Their hooks, in order:
{hooks}

Return, in everyday Roman Urdu (Latin letters only, no Devanagari or Arabic script):
- title: max 70 characters, with the number {n} and one emoji, curiosity first, e.g. a "Top {n}"
  or "{n} moments" angle built from the funniest hook. No clickbait lies.
- intro: 2 or 3 short sentences that make people watch to the end, then ask them to subscribe.
- hashtags: 5 hashtags, the first one #comedy.
Never name a comedian, creator or show. Naughty is fine, dirty is not."""


def clean_text(text, limit=80):
    """On-screen text the fonts can draw: no emoji, hashtags or dashes."""
    t = re.sub(r"#\S+", "", text or "")
    t = "".join(ch for ch in t if ord(ch) < 0x2000 or ch in "’‘“”")
    t = re.sub(r"[·•–—]", " ", t)
    return " ".join(t.split())[:limit].strip()


def clock(seconds):
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def chapters(starts):
    """[(seconds, label)] -> description lines; YouTube needs 0:00 first."""
    return "\n".join(f"{clock(t)} {label}" for t, label in starts)


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def _ff(args, cwd):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr.strip()[-400:]}")


def _txt(job_dir, name, text):
    # ffmpeg runs inside job_dir, so drawtext reads textfile= by its bare name
    # (no drive colon to escape); the text never passes through the graph.
    # newline="\n": Windows text mode writes \r\n, which drawtext draws as an
    # extra empty line between every two lines of the hook.
    with open(os.path.join(job_dir, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return name


def _draw(textfile, font, size, color, x, y, border=5, spacing=12):
    from ffmpeg_utils import escape_filter_value
    font = escape_filter_value(font.replace("\\", "/"))
    return (f"drawtext=fontfile='{font}':textfile={textfile}:fontsize={size}:fontcolor={color}"
            f":x={x}:y={y}:borderw={border}:bordercolor=black@0.85:line_spacing={spacing}")


def card(job_dir, out, seconds, bg, lines):
    """A plain brand card: [(text, font, size, color, y)] centred."""
    draws = []
    for k, (text, font, size, color, y) in enumerate(lines):
        draws.append(_draw(_txt(job_dir, f".card_{os.path.basename(out)}_{k}.txt", text), font, size, color,
                           "(w-text_w)/2", y))
    _ff(["-f", "lavfi", "-i", f"color=c={bg}:s={W}x{H}:d={seconds}:r={FPS}",
         "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo",
         "-filter_complex", f"[0:v]{','.join(draws)},format=yuv420p[v]", "-map", "[v]", "-map", "1:a",
         "-t", f"{seconds}", *VIDEO_ARGS, os.path.basename(out)], job_dir)


def segment(job_dir, src, out, keep_seconds, number, hook, handle):
    """One Short in the 16:9 frame: blurred self behind, number + hook left."""
    hook_lines = "\n".join(textwrap.wrap(clean_text(hook, 70), 16)[:4]) or " "
    num = _txt(job_dir, f".num_{number}.txt", f"#{number}")
    hk = _txt(job_dir, f".hook_{number}.txt", hook_lines)
    hd = _txt(job_dir, ".handle.txt", handle or " ")
    sub = _txt(job_dir, ".sub.txt", "SUBSCRIBE")
    left = 90
    right = f"{W - 610}+(610-text_w)/2"
    graph = (
        f"[0:v]scale=480:270:force_original_aspect_ratio=increase,crop=480:270,gblur=sigma=10,"
        f"scale={W}:{H},eq=brightness=-0.22:saturation=0.8[bg];"
        f"[0:v]scale=-2:{H}[fg];"
        f"[bg][fg]overlay=(W-w)/2:0,"
        f"{_draw(num, NUM_FONT, 170, GOLD, left, 250, 7)},"
        f"{_draw(hk, TEXT_FONT, 50, 'white', left, 470, 5, 16)},"
        f"{_draw(hd, TEXT_FONT, 44, 'white', right, 470, 5)},"
        f"{_draw(sub, NUM_FONT, 60, GOLD, right, 540, 6)},format=yuv420p[v]")
    _ff(["-i", os.path.abspath(src), "-t", f"{keep_seconds:.3f}", "-filter_complex", graph, "-map", "[v]",
         "-map", "0:a?", *VIDEO_ARGS, os.path.basename(out)], job_dir)


def write_copy(client, model, hooks, handle):
    from google.genai import types
    r = client.models.generate_content(
        model=model, contents=COPY_PROMPT.format(handle=handle or "this channel", n=len(hooks),
                                                 hooks="\n".join(f"{k + 1}. {h}" for k, h in enumerate(hooks))),
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=LongCopy,
                                           temperature=0.8))
    return LongCopy.model_validate_json(r.text)


def build(job_dir, shorts, handle, bg="#2B0F3D", client=None, model=None, progress=print):
    """shorts: [{path, hook, title, keep_seconds}] in order. Returns the metadata dict."""
    if not MIN_SHORTS <= len(shorts) <= MAX_SHORTS:
        raise ValueError(f"Pick {MIN_SHORTS} to {MAX_SHORTS} Shorts.")
    os.makedirs(job_dir, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d")
    parts = []
    n = len(shorts)
    progress(f"intro (1/{n + 2})")
    intro = os.path.join(job_dir, ".part_00.mp4")
    card(job_dir, intro, INTRO_SECONDS, bg, [
        (f"TOP {n}", NUM_FONT, 230, GOLD, 300),
        ("is hafte ke sabse funny moments", TEXT_FONT, 64, "white", 600),
        (handle or " ", TEXT_FONT, 46, "white", 720)])
    parts.append((intro, "Intro"))
    for k, s in enumerate(shorts, 1):
        progress(f"short {k} of {n} ({k + 1}/{n + 2})")
        out = os.path.join(job_dir, f".part_{k:02d}.mp4")
        # Countdown order on screen: the last one shown is #1.
        segment(job_dir, s["path"], out, s["keep_seconds"], n - k + 1, s["hook"], handle)
        parts.append((out, f"#{n - k + 1} {clean_text(s['hook'], 60)}"))
    progress(f"outro ({n + 2}/{n + 2})")
    outro = os.path.join(job_dir, ".part_99.mp4")
    card(job_dir, outro, OUTRO_SECONDS, bg, [
        ("SHUKRIYA!", NUM_FONT, 200, GOLD, 300),
        ("Roz naye funny Shorts ke liye subscribe karo", TEXT_FONT, 56, "white", 580),
        (handle or " ", TEXT_FONT, 60, GOLD, 690)])
    parts.append((outro, None))

    progress("joining")
    listing = os.path.join(job_dir, ".parts.txt")
    with open(listing, "w", encoding="utf-8") as f:
        f.writelines(f"file '{os.path.basename(p)}'\n" for p, _ in parts)
    name = f"Weekly_{stamp}_clip_1.mp4"
    _ff(["-f", "concat", "-safe", "0", "-i", ".parts.txt", "-c", "copy", "-movflags", "+faststart", name], job_dir)
    starts, t = [], 0.0
    for path, label in parts:
        if label:
            starts.append((t, label))
        t += _probe(path)
    total = _probe(os.path.join(job_dir, name))

    hooks = [clean_text(s["hook"] or s["title"], 80) for s in shorts]
    copy = None
    if client is not None:
        try:
            copy = write_copy(client, model, hooks, handle)
        except Exception as e:  # noqa: BLE001 — a plain title still ships the video
            progress(f"copy fallback ({type(e).__name__})")
    title = (copy.title if copy else f"Top {n} funny moments is hafte ke 😂")[:100]
    tags = [h if h.startswith("#") else f"#{h}" for h in (copy.hashtags if copy else ["#comedy", "#funny"])][:5]
    description = "\n\n".join(x for x in [
        copy.intro if copy else "Is hafte ke sabse funny moments, ek hi video mein.",
        "Chapters:\n" + chapters(starts),
        f"Subscribe karo {handle} for daily funny Shorts." if handle else "",
        " ".join(tags)] if x)
    for p, _ in parts:
        os.remove(p)
    for leftover in os.listdir(job_dir):
        if leftover.startswith((".card_", ".num_", ".hook_", ".handle", ".sub", ".parts")):
            os.remove(os.path.join(job_dir, leftover))
    meta = {"shorts": [{"start": 0.0, "end": round(total, 2), "seo_title": title, "seo_description": description,
                        "seo_tags": [h.lstrip("#") for h in tags], "hashtags": tags,
                        "video_title_for_youtube_short": title, "chapters": [[round(a, 1), b] for a, b in starts]}],
            "genre": "long", "output_format": "long", "source_video": None,
            "transcript": {"language": "none", "segments": []}}
    with open(os.path.join(job_dir, f"Weekly_{stamp}_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    with open(os.path.join(job_dir, ".source.json"), "w", encoding="utf-8") as f:
        json.dump({"url": None, "genre": "long", "shorts": [s.get("id") for s in shorts]}, f)
    return meta


def keep_seconds(path, frame_cfg):
    """How much of a served Short to keep: all of it minus its end card."""
    dur = _probe(path)
    outro = float(frame_cfg.get("outro_seconds") or 0) if frame_cfg.get("outro", True) else 0.0
    return max(1.0, dur - outro)


def ffmpeg_ready():
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
