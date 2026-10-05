"""FRAMED output: the clip on a solid-colour 9:16 canvas, title above, captions below.

The look clip channels use instead of a face-tracked crop: the source is
cropped (which also trims corner logos), scaled to the full width and placed
in the upper middle of the frame. The colour band above carries the clip's
title, the band below carries the captions, burned afterwards by the normal
caption pass so the clip editor can still restyle them.

One ffmpeg pass per clip and no face detection or scene analysis, so on a
CPU-only machine it renders a 60 s clip in ~17 s (libx264 medium, i7-1360P,
5-oct-2026) where the tracked reframe needs minutes.

Env (per job, set by app.py from the request):
  FRAME_BG_COLOR  background, hex (default #14142B)
  FRAME_CROP      wide (16:9) | classic (4:3, default) | square (1:1)
  FRAME_ZOOM      extra zoom on top of the crop (default 1.12)
  FRAME_TITLE     1 (default) burns the clip title in the top band, 0 off
"""
import json
import os
import re
import subprocess
import uuid

from ffmpeg_utils import video_encode_args, escape_filter_value, QUALITY, METADATA_SCRUB

OUT_W, OUT_H = 1080, 1920
# Top of the video, as a fraction of the height. 20% leaves ~380 px for a
# two-line title and puts the captions in the band below the picture, above
# the strip the TikTok / Shorts UI covers at the bottom.
VIDEO_TOP_RATIO = 0.20
CAPTION_GAP_PX = 45
# Share of the vertical trim taken from the top (the rest comes off the bottom).
CROP_TOP_SHARE = 0.25
CROP_ASPECTS = {"wide": 16 / 9, "classic": 4 / 3, "square": 1.0}
DEFAULT_BG = "#14142B"
FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


# Per-job record of the look, written by main.py into the job directory. The
# job's FRAME_* env only exists in the job process; the clip editor re-renders
# and re-captions from the API process, and without this file a trimmed clip
# came back on the default colour, with no title, captions at the bottom.
JOB_FILE = "frame.json"


def load_job(job_dir):
    try:
        with open(os.path.join(job_dir, JOB_FILE), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return None


def write_job(job_dir, cfg, caption_margin, titles):
    with open(os.path.join(job_dir, JOB_FILE), "w", encoding="utf-8") as f:
        json.dump({**cfg, "caption_margin": caption_margin, "titles": titles}, f,
                  ensure_ascii=False, indent=1)


def job_caption_margin(job_dir):
    """Caption MarginV for a clip in a FRAMED job, or None for any other job."""
    job = load_job(job_dir)
    return job.get("caption_margin") if job else None


def settings(job_dir=None):
    """The look: defaults, then the job file, then this process's FRAME_* env."""
    job = (load_job(job_dir) if job_dir else None) or {}
    bg = (os.environ.get("FRAME_BG_COLOR") or job.get("bg") or DEFAULT_BG).strip()
    if not re.fullmatch(r"#?[0-9A-Fa-f]{6}", bg):
        bg = DEFAULT_BG
    crop = (os.environ.get("FRAME_CROP") or job.get("crop") or "classic").strip().lower()
    if crop not in CROP_ASPECTS:
        crop = "classic"
    try:
        zoom = min(max(float(os.environ.get("FRAME_ZOOM") or job.get("zoom") or 1.12), 1.0), 1.5)
    except ValueError:
        zoom = 1.12
    title = os.environ.get("FRAME_TITLE", "0" if job.get("title") is False else "1").strip() != "0"
    return {"bg": "#" + bg.lstrip("#").upper(), "crop": crop, "zoom": zoom, "title": title}


def geometry(src_w, src_h, crop="classic", zoom=1.12):
    """Crop box in the source and the placed size/position on the canvas."""
    aspect = min(CROP_ASPECTS.get(crop, 4 / 3), src_w / src_h)  # never widen
    cw = min(src_w, src_h * aspect) / zoom
    ch = cw / aspect
    cw, ch = int(cw) // 2 * 2, int(ch) // 2 * 2
    # Most of the vertical trim comes off the bottom: that is where a source's
    # own burned-in subtitles and lower thirds sit, and a centred crop sliced
    # them in half (stand-up source with Hinglish subs, 5-oct-2026). Heads are
    # near the top, so the top keeps most of its margin.
    cy = int((src_h - ch) * CROP_TOP_SHARE) // 2 * 2
    vw = OUT_W
    vh = int(round(OUT_W / aspect)) // 2 * 2
    max_h = int(OUT_H * 0.62) // 2 * 2
    if vh > max_h:  # portrait / square-ish sources: fit the height instead
        vh = max_h
        vw = int(round(vh * aspect)) // 2 * 2
    top = int(OUT_H * VIDEO_TOP_RATIO) // 2 * 2
    return {"crop_w": cw, "crop_h": ch, "crop_x": (src_w - cw) // 2 // 2 * 2, "crop_y": cy,
            "w": vw, "h": vh,
            "x": (OUT_W - vw) // 2, "y": top}


def caption_margin_units(geo):
    """MarginV (top-aligned) for subtitles.generate_ass, in its PlayResY 288 units."""
    return round((geo["y"] + geo["h"] + CAPTION_GAP_PX) * 288 / OUT_H)


def _luminance(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ass_colour(hex_color):
    h = hex_color.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def clean_title(text):
    """Drop hashtags/emoji-free noise and ASS control characters."""
    text = re.sub(r"#\S+", "", text or "")
    # libass draws emoji as grey outlines (no colour fonts), so the burned
    # title drops them; the metadata title keeps them for posting.
    text = re.sub("[\U0001F000-\U0001FAFF☀-➿️‍]", "", text)
    text = text.replace("\\", "").replace("{", "(").replace("}", ")")
    return re.sub(r"\s+", " ", text).strip()


def title_ass(title, geo, bg, path, duration):
    """A one-event ASS file with the title centred in the top band."""
    colour = "#000000" if _luminance(bg) > 0.6 else "#FFFFFF"
    # 64 px reads as a headline on a phone; long titles shrink so two lines fit.
    size = 76 if len(title) <= 36 else 64 if len(title) <= 60 else 52
    band_mid = geo["y"] // 2
    end = f"{int(duration // 3600)}:{int(duration % 3600 // 60):02d}:{duration % 60:05.2f}"
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "[Script Info]\nScriptType: v4.00+\n"
            f"PlayResX: {OUT_W}\nPlayResY: {OUT_H}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Title,Montserrat ExtraBold,{size},{_ass_colour(colour)},{_ass_colour(colour)},"
            "&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,0,3,5,70,70,0,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            f"Dialogue: 0,0:00:00.00,{end},Title,,0,0,0,,{{\\pos({OUT_W // 2},{band_mid})}}{title}\n")


def _probe(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration", "-of", "csv=p=0:s=x", path],
        timeout=60).decode().split()
    w, h = (int(v) for v in out[0].split("x")[:2])
    duration = float(out[-1]) if len(out) > 1 else 60.0
    return w, h, duration


def render(input_video, output_video, title=None):
    """Render one cut clip as a FRAMED 9:16 video. Returns the geometry used."""
    job_dir = os.path.dirname(os.path.abspath(output_video))
    cfg = settings(job_dir)
    if title is None:
        # An editor re-render names its output "<prefix>_<clip file>"; the
        # clip's title was recorded under the clip file name.
        name = os.path.basename(output_video)
        for clip_name, clip_title in ((load_job(job_dir) or {}).get("titles") or {}).items():
            if name == clip_name or name.endswith("_" + clip_name):
                title = clip_title
                break
    src_w, src_h, duration = _probe(input_video)
    geo = geometry(src_w, src_h, cfg["crop"], cfg["zoom"])
    vf = (f"crop={geo['crop_w']}:{geo['crop_h']}:{geo['crop_x']}:{geo['crop_y']},scale={geo['w']}:{geo['h']}:flags=lanczos,"
          f"pad={OUT_W}:{OUT_H}:{geo['x']}:{geo['y']}:color=0x{cfg['bg'].lstrip('#')},setsar=1")
    ass_path = None
    title = clean_title(title) if cfg["title"] else ""
    if title:
        ass_path = os.path.join(os.path.dirname(os.path.abspath(output_video)),
                                f"frametitle_{uuid.uuid4().hex[:8]}.ass")
        title_ass(title, geo, cfg["bg"], ass_path, duration + 1)
        vf += (f",ass=filename='{escape_filter_value(ass_path)}'"
               f":fontsdir='{escape_filter_value(FONTS_DIR)}'")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_video, "-vf", vf,
             *video_encode_args(QUALITY), "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", *METADATA_SCRUB,
             "-movflags", "+faststart", output_video],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1800)
    finally:
        if ass_path and os.path.exists(ass_path):
            os.remove(ass_path)
    print(f"🖼️ Framed {geo['w']}x{geo['h']} on {cfg['bg']} ({cfg['crop']}, zoom {cfg['zoom']:g})"
          + (f", title: {title}" if title else ""))
    return geo
