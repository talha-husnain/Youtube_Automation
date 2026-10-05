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
  FRAME_OUTRO     1 (default) adds a 2 s "follow for more" end card, 0 off
  FRAME_HANDLE    channel handle shown small at the top and on the end card
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
# End card: the clip's last frame held and dimmed, with "follow for more" and
# the handle. Holding the real frame avoids a cut to a blank screen; 2 s is
# long enough to read two lines.
OUTRO_SECONDS = 2.0
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
    outro = os.environ.get("FRAME_OUTRO", "0" if job.get("outro") is False else "1").strip() != "0"
    handle = clean_handle(os.environ.get("FRAME_HANDLE") or job.get("handle") or "")
    return {"bg": "#" + bg.lstrip("#").upper(), "crop": crop, "zoom": zoom, "title": title,
            "outro": outro, "handle": handle}


def clean_handle(text):
    """A channel handle safe to burn: letters, digits, _ . - @ and spaces, 30 chars."""
    text = re.sub(r"[^\w .@-]", "", str(text or "")).strip()[:30]
    if text and " " not in text and not text.startswith("@"):
        text = "@" + text
    return text


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


# libass draws emoji as grey outlines (no colour fonts), so burned text drops
# them; the metadata title keeps them for posting.
_EMOJI = re.compile("[" + chr(0x1F000) + "-" + chr(0x1FAFF) + chr(0x2600) + "-"
                    + chr(0x27BF) + chr(0xFE0F) + chr(0x200D) + "]")


def clean_title(text):
    """Drop hashtags, emoji and ASS control characters."""
    text = re.sub(r"#\S+", "", text or "")
    text = _EMOJI.sub("", text)
    text = text.replace("\\", "").replace("{", "(").replace("}", ")")
    return re.sub(r"\s+", " ", text).strip()


def _ts(seconds):
    seconds = max(0.0, seconds)
    return f"{int(seconds // 3600)}:{int(seconds % 3600 // 60):02d}:{seconds % 60:05.2f}"


def overlay_ass(path, geo, bg, duration, title="", handle="", outro=False):
    """The frame's text layer: title, handle tag and end card, all animated.

    The title pops in over the first ~0.4 s instead of a separate intro card:
    on Shorts a card before the clip spends the first second, which is when
    viewers decide to swipe.
    """
    colour = _ass_colour("#000000" if _luminance(bg) > 0.6 else "#FFFFFF")
    # 76 px reads as a headline on a phone; long titles shrink so two lines fit.
    size = 76 if len(title) <= 36 else 64 if len(title) <= 60 else 52
    band_mid = geo["y"] // 2
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {OUT_W}", f"PlayResY: {OUT_H}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Title,Montserrat ExtraBold,{size},{colour},{colour},&H00000000,&H64000000,"
        "1,0,0,0,100,100,0,0,1,0,3,5,70,70,0,1",
        f"Style: Handle,Montserrat ExtraBold,34,{colour},{colour},&H00000000,&H00000000,"
        "1,0,0,0,100,100,1,0,1,0,0,5,40,40,0,1",
        "Style: Outro,Anton,118,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,2,0,1,7,0,5,60,60,0,1",
        "Style: OutroHandle,Montserrat ExtraBold,64,&H0000E5FF,&H0000E5FF,&H00000000,"
        "&H00000000,1,0,0,0,100,100,0,0,1,5,0,5,60,60,0,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if title:
        pop = (r"\fad(150,0)\fscx70\fscy70\t(0,260,\fscx106\fscy106)"
               r"\t(260,400,\fscx100\fscy100)")
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(duration)},Title,,0,0,0,,"
                     f"{{\\pos({OUT_W // 2},{band_mid}){pop}}}{title}")
    if handle:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(duration)},Handle,,0,0,0,,"
                     f"{{\\pos({OUT_W // 2},44)\\alpha&H40&}}{handle}")
    if outro:
        t0, t1 = duration, duration + OUTRO_SECONDS
        y = int(OUT_H * 0.44)
        lines.append(f"Dialogue: 2,{_ts(t0)},{_ts(t1)},Outro,,0,0,0,,"
                     f"{{\\pos({OUT_W // 2},{y})"
                     r"\fscx40\fscy40\t(0,220,\fscx110\fscy110)\t(220,340,\fscx100\fscy100)}"
                     r"FOLLOW\NFOR MORE")
        if handle:
            lines.append(f"Dialogue: 2,{_ts(t0 + 0.25)},{_ts(t1)},OutroHandle,,0,0,0,,"
                         f"{{\\pos({OUT_W // 2},{y + 230})\\fad(200,0)}}{handle}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


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
    audio = []
    if cfg["outro"]:
        # Hold the last frame, dimmed, under the end card; silence pads the audio.
        vf += (f",tpad=stop_mode=clone:stop_duration={OUTRO_SECONDS:g}"
               f",drawbox=x=0:y=0:w=iw:h=ih:color=0x{cfg['bg'].lstrip('#')}@0.72:t=fill"
               f":enable='gte(t,{duration:.3f})'")
        audio = ["-af", f"apad=pad_dur={OUTRO_SECONDS:g}"]
    if title or cfg["handle"] or cfg["outro"]:
        ass_path = os.path.join(os.path.dirname(os.path.abspath(output_video)),
                                f"frametitle_{uuid.uuid4().hex[:8]}.ass")
        overlay_ass(ass_path, geo, cfg["bg"], duration, title=title,
                    handle=cfg["handle"], outro=cfg["outro"])
        vf += (f",ass=filename='{escape_filter_value(ass_path)}'"
               f":fontsdir='{escape_filter_value(FONTS_DIR)}'")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_video, "-vf", vf, *audio,
             *video_encode_args(QUALITY), "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", *METADATA_SCRUB,
             "-movflags", "+faststart", output_video],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1800)
    finally:
        if ass_path and os.path.exists(ass_path):
            os.remove(ass_path)
    print(f"🖼️ Framed {geo['w']}x{geo['h']} on {cfg['bg']} ({cfg['crop']}, zoom {cfg['zoom']:g})"
          + (f", title: {title}" if title else "")
          + (", end card" if cfg["outro"] else ""))
    return geo
