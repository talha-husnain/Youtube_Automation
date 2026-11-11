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

from ffmpeg_utils import (video_encode_args, escape_filter_value, QUALITY, METADATA_SCRUB,
                          LOUDNORM_FILTER)

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
# End card: the clip's last frame held, blurred and tinted, under an animated
# "follow for more" with the handle on a pulsing button. Holding the real
# frame avoids a cut to a blank screen. FRAME_OUTRO_SECONDS picks 1-3 s.
OUTRO_SECONDS = 3.0
GOLD = "#FFD23F"
# The channel's take (ai_take.py) sits between the clip and the end card on
# the same held frame: the voice starts after the text pops in and the words
# light up in gold as they are said. TAKE_LEAD + TAKE_TAIL must match
# ai_take.TAKE_PAD_SECONDS, which keeps the whole short under 3 minutes.
TAKE_LEAD = 0.35
TAKE_TAIL = 0.6
TEXT_ONLY_SECONDS = 3.5
TAKE_LABEL = "HAMARA TAKE"
# The host of comedy clips (clip_host.py) and his series.
HOST_LABEL = "CHACHA JUDGE"
SERIES_LABEL = "PUNCHLINE ADALAT"
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


def write_job(job_dir, cfg, caption_margin, titles, takes=None):
    data = {**cfg, "caption_margin": caption_margin, "titles": titles}
    if takes:
        # ai_take.py: {clip file: {text, audio, voice_seconds}}. Kept here so an
        # editor re-render (a trim) still ends with the channel's take.
        data["takes"] = takes
    with open(os.path.join(job_dir, JOB_FILE), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _by_clip_name(mapping, name):
    """An editor re-render names its output "<prefix>_<clip file>"."""
    for clip_name, value in (mapping or {}).items():
        if name == clip_name or name.endswith("_" + clip_name):
            return value
    return None


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
    try:
        outro_s = float(os.environ.get("FRAME_OUTRO_SECONDS") or job.get("outro_seconds")
                        or OUTRO_SECONDS)
    except ValueError:
        outro_s = OUTRO_SECONDS
    return {"bg": "#" + bg.lstrip("#").upper(), "crop": crop, "zoom": zoom, "title": title,
            "outro": outro, "handle": handle, "outro_seconds": min(max(outro_s, 1.0), 3.0)}


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


_K = 0.5523  # bezier handle length for a quarter circle


def _round_rect(w, h, r):
    """ASS drawing of a w x h rounded rectangle (origin top-left)."""
    c = r * _K
    return (f"m {r} 0 l {w - r} 0 b {w - r + c:.0f} 0 {w} {r - c:.0f} {w} {r} "
            f"l {w} {h - r} b {w} {h - r + c:.0f} {w - r + c:.0f} {h} {w - r} {h} "
            f"l {r} {h} b {r - c:.0f} {h} 0 {h - r + c:.0f} 0 {h - r} "
            f"l 0 {r} b 0 {r - c:.0f} {r - c:.0f} 0 {r} 0")


def _circle(rad):
    c = rad * _K
    d = 2 * rad
    return (f"m {rad} 0 b {rad + c:.0f} 0 {d} {rad - c:.0f} {d} {rad} "
            f"b {d} {rad + c:.0f} {rad + c:.0f} {d} {rad} {d} "
            f"b {rad - c:.0f} {d} 0 {rad + c:.0f} 0 {rad} "
            f"b 0 {rad - c:.0f} {rad - c:.0f} 0 {rad} 0")


END_CARD_STYLES = [
    "Style: OutroBig,Anton,200,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,"
    "0,0,0,0,100,100,4,0,1,9,6,5,40,40,0,1",
    "Style: OutroSub,Anton,130,{gold},{gold},&H00000000,&H96000000,"
    "0,0,0,0,100,100,3,0,1,7,5,5,40,40,0,1",
    "Style: Pill,Montserrat ExtraBold,62,{ink},{ink},&H00000000,&H00000000,"
    "1,0,0,0,100,100,0,0,1,0,0,5,40,40,0,1",
    "Style: Shape,Arial,20,{gold},{gold},{gold},&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
    "Style: OutroNote,Montserrat ExtraBold,44,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
    "1,0,0,0,100,100,1,0,1,0,3,5,40,40,0,1",
]


def end_card_events(t0, secs, handle, bg):
    """Dialogue lines of the animated end card starting at t0 for secs seconds.

    0.0 s "FOLLOW" slams in and shakes; 0.18 s "FOR MORE" slides in; 0.35 s
    the gold handle button rises, then pulses with ripple rings and a
    bouncing arrow until the end. Times inside tags are ms from each event.
    """
    t1 = t0 + secs
    cx = OUT_W // 2
    gold = _ass_colour(GOLD)
    pill_text = handle or "NEW CLIPS DAILY"
    pill_w = min(980, max(560, 40 * len(pill_text) + 160))
    pill_h, py = 150, 1090
    ev = []

    def add(layer, start, style, text, end=None):
        ev.append(f"Dialogue: {layer},{_ts(start)},{_ts(min(end or t1, t1))},{style},,0,0,0,,{text}")

    add(5, t0, "OutroBig",
        rf"{{\pos({cx},640)\fscx320\fscy320\alpha&HFF&\t(0,180,\fscx100\fscy100\alpha&H00&)"
        r"\t(180,240,\frz-5)\t(240,300,\frz4)\t(300,360,\frz0)}FOLLOW")
    add(5, t0 + 0.18, "OutroSub",
        rf"{{\move({OUT_W + 500},830,{cx},830,0,300)}}FOR MORE")
    # The button: shape and text share the same rise and pulses.
    pulse = "".join(rf"\t({a},{a + 200},\fscx108\fscy108)\t({a + 200},{a + 400},\fscx100\fscy100)"
                    for a in range(650, int(secs * 1000) - 350, 600))
    rise = rf"\move({cx},{OUT_H + 200},{cx},{py},0,350)"
    add(3, t0 + 0.35, "Shape",
        rf"{{\an5{rise}{pulse}\1c{gold}\bord0\shad0\p1}}{_round_rect(pill_w, pill_h, pill_h // 2)}{{\p0}}")
    add(4, t0 + 0.35, "Pill", rf"{{\an5{rise}{pulse}}}{pill_text}")
    # Ripple rings behind the button, one every 0.6 s after it lands.
    t = t0 + 0.75
    while t < t1 - 0.3:
        add(2, t, "Shape",
            rf"{{\an5\pos({cx},{py})\1a&HFF&\3c{gold}\bord6\shad0\fscx40\fscy40"
            rf"\t(0,700,\fscx120\fscy120\alpha&HFF&)\p1}}{_round_rect(pill_w, pill_h, pill_h // 2)}{{\p0}}",
            end=t + 0.7)
        t += 0.6
    # Arrow under the button, bouncing toward it.
    arrow = "m 0 40 l 36 0 l 72 40 l 58 40 l 36 16 l 14 40"
    t, up = t0 + 0.8, True
    while t < t1 - 0.05:
        y_from, y_to = (1250, 1220) if up else (1220, 1250)
        add(4, t, "Shape",
            rf"{{\an5\move({cx},{y_from},{cx},{y_to})\1c&HFFFFFF&\bord0\shad0\p1}}{arrow}{{\p0}}",
            end=t + 0.25)
        t, up = t + 0.25, not up
    if handle:
        add(4, t0 + 0.9, "OutroNote", rf"{{\pos({cx},1360)\fad(250,0)}}New clips every day")
    return ev


TAKE_STYLES = [
    # \kf fills each word from SecondaryColour (white) to PrimaryColour (gold).
    "Style: TakeText,Montserrat ExtraBold,{size},{gold},&H00FFFFFF,&H00000000,&H96000000,"
    "1,0,0,0,100,100,0,0,1,6,3,5,80,80,0,1",
    "Style: TakeLabel,Montserrat ExtraBold,46,{ink},{ink},&H00000000,&H00000000,"
    "1,0,0,0,100,100,2,0,1,0,0,5,40,40,0,1",
]


def _take_for(job_dir, job, name):
    """(take, voice path) for this clip from the job file, or (None, None)."""
    rec = _by_clip_name(job.get("takes"), name)
    text = clean_title((rec or {}).get("text") or "")
    if not text:
        return None, None
    voice = os.path.join(job_dir, rec["audio"]) if rec.get("audio") else None
    if voice and not os.path.exists(voice):
        voice = None
    voice_s = float(rec.get("voice_seconds") or 0) if voice else 0.0
    seconds = round(voice_s + TAKE_LEAD + TAKE_TAIL, 2) if voice_s else TEXT_ONLY_SECONDS
    take = {"text": text, "seconds": seconds, "voice_seconds": voice_s}
    if isinstance(rec.get("host"), dict):
        take["host"] = rec["host"]      # Chacha Judge (clip_host.py): bubbles, laugh edits, verdict
    return take, voice


def take_size(text):
    return 76 if len(text) <= 60 else 66 if len(text) <= 100 else 58


def take_events(t0, take):
    """Dialogue lines of the take: a gold "HAMARA TAKE" label drops in, then
    the line pops in and lights up word by word in time with the voice
    (spread by word length: the voice model gives no word timings)."""
    t1 = t0 + take["seconds"]
    cx = OUT_W // 2
    gold = _ass_colour(GOLD)
    words = take["text"].split()
    voice_s = take.get("voice_seconds") or 0.0
    if voice_s:
        weights = [len(w) + 2 for w in words]
        cs = [max(1, round(voice_s * 100 * wt / sum(weights))) for wt in weights]
        body = (rf"{{\k{round(TAKE_LEAD * 100)}}}"
                + " ".join(rf"{{\kf{c}}}{w}" for w, c in zip(words, cs)))
    else:
        body = " ".join(words)
    w, h = max(420, 30 * len(TAKE_LABEL) + 120), 96
    drop = rf"\move({cx},520,{cx},600,0,250)\fad(120,0)"
    return [
        f"Dialogue: 3,{_ts(t0)},{_ts(t1)},Shape,,0,0,0,,"
        rf"{{\an5{drop}\1c{gold}\bord0\shad0\p1}}{_round_rect(w, h, h // 2)}{{\p0}}",
        f"Dialogue: 4,{_ts(t0)},{_ts(t1)},TakeLabel,,0,0,0,,{{\\an5{drop}}}{TAKE_LABEL}",
        f"Dialogue: 5,{_ts(t0)},{_ts(t1)},TakeText,,0,0,0,,"
        rf"{{\pos({cx},960)\fad(150,0)\fscx85\fscy85\t(0,220,\fscx100\fscy100)}}{body}",
    ]


# ---------------------------------------------------------------- Chacha Judge (clip_host.py)
# On a laugh: the zoom holds ZOOM_HOLD s from the punchline's last word, the emoji pops a beat later,
# the host's bubble shows in the top band from BUBBLE_LEAD for BUBBLE_SECONDS (the title steps aside).
ZOOM_HOLD = 1.6
BUBBLE_LEAD = 0.45
BUBBLE_SECONDS = 2.6
BUBBLE_SIZE = 60
BUBBLE_LINE = 72
STICKER_SIZE = 150
HOST_STYLES = [
    "Style: Bubble,Montserrat ExtraBold,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
    "1,0,0,0,100,100,0,0,1,0,0,5,40,40,0,1",
    "Style: BubbleLabel,Montserrat ExtraBold,34,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
    "1,0,0,0,100,100,2,0,1,0,0,5,40,40,0,1",
    "Style: Verdict,Anton,170,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,"
    "0,0,0,0,100,100,3,0,1,8,5,5,40,40,0,1",
    "Style: Question,Montserrat ExtraBold,60,{gold},{gold},&H00000000,&H96000000,"
    "1,0,0,0,100,100,1,0,1,5,3,5,60,60,0,1",
]
# Synthesised laugh sounds (no file to license, never Content ID): aevalsrc expression, seconds,
# volume, extra filters. Quiet on purpose: the crowd's own laugh is the point and must stay on top.
LAUGH_SOUNDS = {
    "boom": ("0.9*sin(2*PI*(58*t-18*t*t))*exp(-5.5*t)+0.35*sin(2*PI*(116*t-36*t*t))*exp(-7*t)", 0.8, 0.45, ""),
    "pop": ("0.8*sin(2*PI*(700*t+2600*t*t))*exp(-22*t)", 0.25, 0.35, ""),
    "tss": ("(2*random(0)-1)*exp(-9*t)", 0.45, 0.3, ",highpass=f=4000"),
}


def laugh_moments(host, duration):
    """The host's laugh moments inside this clip: [{"at", "bubble", "emoji"}] (a trim may have cut some)."""
    out = []
    for lg in (host or {}).get("laughs") or []:
        try:
            at = float(lg["at"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0.5 <= at <= duration - 0.5 and clean_title(lg.get("bubble") or ""):
            out.append({**lg, "at": at})
    return out


def _bubble_lines(text):
    """One line, or two balanced ones for a longer bubble."""
    words = text.split()
    if len(text) <= 22 or len(words) < 3:
        return [text]
    best = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:]))))
    return [" ".join(words[:best]), " ".join(words[best:])]


def bubbles(host, geo, duration):
    """The host's bubbles that fit this clip: [{"t0", "t1", "lines", "cx", "cy", "w", "h", "emoji"}],
    in the top band, so neither a bubble nor its emoji ever covers a face (an emoji on the picture's
    corner sat on the comedian's face, 11-nov-2026)."""
    right = ((host or {}).get("look") or {}).get("side") == "right"
    band = max(geo["y"], 300)
    out = []
    for lg in laugh_moments(host, duration):
        t0 = lg["at"] + BUBBLE_LEAD
        t1 = min(t0 + BUBBLE_SECONDS, duration)
        if t1 - t0 < 1.0:
            continue
        lines = _bubble_lines(clean_title(lg["bubble"]))
        w = min(960, max(420, int(max(len(x) for x in lines) * BUBBLE_SIZE * 0.6) + 100))
        h = 78 + BUBBLE_LINE * len(lines)
        out.append({"t0": t0, "t1": t1, "lines": lines, "w": w, "h": h, "emoji": lg.get("emoji"),
                    "cx": OUT_W // 2 + (40 if right else -40), "cy": band // 2 + 10, "right": right})
    return out


def bubble_events(host, geo, duration):
    """Dialogue lines of the host's bubbles: a speech bubble in the top band with his name on it,
    popping in BUBBLE_LEAD after the punchline, its tail toward the picture on the clip's side."""
    look = (host or {}).get("look") or {}
    fill = _ass_colour(look.get("fill") or GOLD)
    ink = _ass_colour(look.get("ink") or "#1A1A1A")
    ev = []
    for b in bubbles(host, geo, duration):
        t0, t1, lines, w, h, cx, cy, right = (b["t0"], b["t1"], b["lines"], b["w"], b["h"], b["cx"], b["cy"],
                                              b["right"])
        top = cy - h // 2
        pop = r"\fscx60\fscy60\t(0,160,\fscx106\fscy106)\t(160,280,\fscx100\fscy100)\fad(0,180)"
        ev.append(f"Dialogue: 6,{_ts(t0)},{_ts(t1)},Shape,,0,0,0,,"
                  rf"{{\an5\pos({cx},{cy}){pop}\1c{fill}\bord0\shad4\4a&H80&\p1}}{_round_rect(w, h, 34)}{{\p0}}")
        tail_x = cx + (w // 4 if right else -w // 4)
        ev.append(f"Dialogue: 6,{_ts(t0)},{_ts(t1)},Shape,,0,0,0,,"
                  rf"{{\an8\pos({tail_x},{top + h - 2}){pop}\1c{fill}\bord0\shad0\p1}}m 0 0 l 56 0 l 18 44{{\p0}}")
        ev.append(f"Dialogue: 7,{_ts(t0 + 0.08)},{_ts(t1)},BubbleLabel,,0,0,0,,"
                  rf"{{\pos({cx},{top + 36})\1c{ink}\alpha&H30&\fad(120,180)}}{HOST_LABEL}")
        ev.append(f"Dialogue: 7,{_ts(t0 + 0.08)},{_ts(t1)},Bubble,,0,0,0,,"
                  rf"{{\pos({cx},{top + 60 + BUBBLE_LINE * len(lines) // 2})\1c{ink}\fad(120,180)}}"
                  + r"\N".join(lines))
    return ev


def title_spans(host, duration):
    """When the title shows: the whole clip, less the host's bubbles."""
    spans, t = [], 0.0
    for b in bubbles(host, {"y": 0}, duration):
        b0, b1 = b["t0"], b["t1"]
        if b0 - t > 0.3:
            spans.append((t, b0))
        t = b1
    if duration - t > 0.3:
        spans.append((t, duration))
    return spans


def verdict_events(t0, take):
    """The host's verdict after the clip: "PUNCHLINE ADALAT #n" drops in, "FAISLA 8/10" slams down,
    the spoken line lights up word by word, then the question for the comments."""
    host = take["host"]
    t1 = t0 + take["seconds"]
    cx = OUT_W // 2
    gold = _ass_colour(GOLD)
    label = f"{SERIES_LABEL} #{int(host.get('series') or 1)}"
    w, h = max(520, 30 * len(label) + 120), 96
    drop = rf"\move({cx},440,{cx},520,0,250)\fad(120,0)"
    ev = [f"Dialogue: 3,{_ts(t0)},{_ts(t1)},Shape,,0,0,0,,"
          rf"{{\an5{drop}\1c{gold}\bord0\shad0\p1}}{_round_rect(w, h, h // 2)}{{\p0}}",
          f"Dialogue: 4,{_ts(t0)},{_ts(t1)},TakeLabel,,0,0,0,,{{\\an5{drop}}}{label}",
          f"Dialogue: 5,{_ts(t0 + 0.15)},{_ts(t1)},Verdict,,0,0,0,,"
          rf"{{\pos({cx},720)\fscx260\fscy260\alpha&HFF&\t(0,170,\fscx100\fscy100\alpha&H00&)"
          rf"\t(170,230,\frz-4)\t(230,290,\frz3)\t(290,350,\frz0)}}FAISLA {{\1c{gold}}}"
          rf"{int(host.get('score') or 0)}/10"]
    ev += [e for e in take_events(t0, take) if ",TakeText," in e]
    question = clean_title(host.get("question") or "").upper()
    if question:
        ev.append(f"Dialogue: 5,{_ts(t0 + 0.6)},{_ts(t1)},Question,,0,0,0,,"
                  rf"{{\pos({cx},1190)\fad(200,0)}}{question}")
    return ev


def laugh_sound(kind, at, k):
    """Filtergraph piece of one quiet laugh sound at ``at`` seconds, labelled [fx<k>]."""
    expr, secs, gain, extra = LAUGH_SOUNDS.get(kind) or LAUGH_SOUNDS["boom"]
    ms = max(0, int(at * 1000))
    return (f";aevalsrc='{expr}':s=48000:d={secs:g}{extra},volume={gain:g},"
            f"aformat=channel_layouts=stereo,adelay={ms}|{ms}[fx{k}]")


def zoom_filters(geo, zoom, windows):
    """Filters after the scale that punch in on the comedian (upper middle of the picture) during
    ``windows`` [(t0, t1)]; "" without windows."""
    if not windows:
        return ""
    zw, zh = int(geo["w"] / zoom) // 2 * 2, int(geo["h"] / zoom) // 2 * 2
    zx, zy = (geo["w"] - zw) // 2, int((geo["h"] - zh) * 0.35)
    on = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in windows)
    return (f",split=2[pb][pz];[pz]crop={zw}:{zh}:{zx}:{zy},scale={geo['w']}:{geo['h']}:flags=lanczos[pzz];"
            f"[pb][pzz]overlay=0:0:enable='{on}'")


def end_card_audio(secs):
    """aevalsrc expression: a rising swoosh into a soft two-tone ding.

    Synthesised, so there is no sound file to license or ship.
    """
    swoosh = "if(lt(t,0.35),0.45*sin(2*PI*(260*t+1500*t*t))*(t/0.35)*(1-t/0.35)*4,0)"
    ding = ("if(gte(t,0.62),0.55*sin(2*PI*1318*(t-0.62))*exp(-5*(t-0.62))"
            "+0.25*sin(2*PI*1975*(t-0.62))*exp(-7*(t-0.62)),0)")
    return f"aevalsrc='{swoosh}+{ding}':s=48000:d={secs:g}"


def overlay_ass(path, geo, bg, duration, title="", handle="", outro=False,
                outro_seconds=OUTRO_SECONDS, take=None):
    """The frame's text layer: title, handle tag and end card, all animated.

    The title pops in over the first ~0.4 s instead of a separate intro card:
    on Shorts a card before the clip spends the first second, which is when
    viewers decide to swipe.
    """
    colour = _ass_colour("#000000" if _luminance(bg) > 0.6 else "#FFFFFF")
    # 76 px reads as a headline on a phone; long titles shrink so two lines fit.
    size = 76 if len(title) <= 36 else 64 if len(title) <= 60 else 52
    band_mid = geo["y"] // 2
    host = (take or {}).get("host")
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
        *(s.format(gold=_ass_colour(GOLD),
                   ink=_ass_colour(bg if _luminance(bg) < 0.4 else "#000000"))
          for s in END_CARD_STYLES),
        *(s.format(gold=_ass_colour(GOLD), size=take_size(take["text"]),
                   ink=_ass_colour(bg if _luminance(bg) < 0.4 else "#000000"))
          for s in (TAKE_STYLES if take else [])),
        *(s.format(gold=_ass_colour(GOLD), size=BUBBLE_SIZE) for s in (HOST_STYLES if host else [])),
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if title:
        pop = (r"\fad(150,0)\fscx70\fscy70\t(0,260,\fscx106\fscy106)"
               r"\t(260,400,\fscx100\fscy100)")
        back = r"\fad(200,0)"
        # The host's bubbles take the band for a moment; the title steps aside and comes back.
        for k, (a, b) in enumerate(title_spans(host, duration) if host else [(0.0, duration)]):
            lines.append(f"Dialogue: 1,{_ts(a)},{_ts(b)},Title,,0,0,0,,"
                         f"{{\\pos({OUT_W // 2},{band_mid}){pop if k == 0 else back}}}{title}")
    if host:
        lines += bubble_events(host, geo, duration)
    if handle:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(duration)},Handle,,0,0,0,,"
                     f"{{\\pos({OUT_W // 2},44)\\alpha&H40&}}{handle}")
    take_s = 0.0
    if take:
        lines += verdict_events(duration, take) if host else take_events(duration, take)
        take_s = take["seconds"]
    if outro:
        lines += end_card_events(duration + take_s, outro_seconds, handle, bg)
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


def render(input_video, output_video, title=None, plain=False):
    """Render one cut clip as a FRAMED 9:16 video. Returns the geometry used.

    A render with the host's layer (clip_host.py) that fails is done again ``plain``: the clip is
    never lost to a bubble, a zoom or a sticker."""
    if not plain:
        try:
            return _render(input_video, output_video, title, plain=False)
        except subprocess.CalledProcessError as e:
            job = load_job(os.path.dirname(os.path.abspath(output_video))) or {}
            rec = _by_clip_name(job.get("takes"), os.path.basename(output_video)) or {}
            if not rec.get("host"):
                raise
            err = (e.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
            print(f"   ⚠️ Host layer failed in ffmpeg ({err[0][:160]}) — rendering the plain frame.")
    return _render(input_video, output_video, title, plain=True)


def _render(input_video, output_video, title=None, plain=False):
    job_dir = os.path.dirname(os.path.abspath(output_video))
    cfg = settings(job_dir)
    job = load_job(job_dir) or {}
    if title is None:
        # The clip's title was recorded under the clip file name.
        title = _by_clip_name(job.get("titles"), os.path.basename(output_video))
    src_w, src_h, duration = _probe(input_video)
    take, voice = _take_for(job_dir, job, os.path.basename(output_video))
    if plain and take:
        take.pop("host", None)       # the verdict line stays, as a plain take
    geo = geometry(src_w, src_h, cfg["crop"], cfg["zoom"])
    host = (take or {}).get("host")
    laughs = laugh_moments(host, duration) if host else []
    look = (host or {}).get("look") or {}
    zoom_windows = [(lg["at"], min(lg["at"] + ZOOM_HOLD, duration)) for lg in laughs]
    vf = (f"[0:v]crop={geo['crop_w']}:{geo['crop_h']}:{geo['crop_x']}:{geo['crop_y']},"
          f"scale={geo['w']}:{geo['h']}:flags=lanczos"
          + zoom_filters(geo, float(look.get("zoom") or 1.12), zoom_windows)
          + f",pad={OUT_W}:{OUT_H}:{geo['x']}:{geo['y']}:color=0x{cfg['bg'].lstrip('#')},setsar=1")
    ass_path = None
    title = clean_title(title) if cfg["title"] else ""
    secs = cfg["outro_seconds"]
    take_s = take["seconds"] if take else 0.0
    hold = take_s + (secs if cfg["outro"] else 0.0)
    if hold:
        # Hold the last frame, blurred and tinted, under the take and end card.
        vf += (f",tpad=stop_mode=clone:stop_duration={hold:g}"
               f",gblur=sigma=14:enable='gte(t,{duration:.3f})'"
               f",drawbox=x=0:y=0:w=iw:h=ih:color=0x{cfg['bg'].lstrip('#')}@0.68:t=fill"
               f":enable='gte(t,{duration:.3f})'")
    if title or cfg["handle"] or cfg["outro"] or take:
        ass_path = os.path.join(os.path.dirname(os.path.abspath(output_video)),
                                f"frametitle_{uuid.uuid4().hex[:8]}.ass")
        overlay_ass(ass_path, geo, cfg["bg"], duration, title=title,
                    handle=cfg["handle"], outro=cfg["outro"], outro_seconds=secs, take=take)
        vf += (f",ass=filename='{escape_filter_value(ass_path)}'"
               f":fontsdir='{escape_filter_value(FONTS_DIR)}'")
    graph = f"{vf}[v]"
    inputs = ["-i", input_video] + (["-i", voice] if voice else [])
    vout = "[v]"
    stickers_on = []
    if laughs:
        # The host's emoji pops on his bubble's outer top corner, in the band: never over a face.
        try:
            import stickers
            idx = 2 if voice else 1
            for k, b in enumerate(bubbles(host, geo, duration) if stickers.available() else []):
                path = stickers.path(b["emoji"] if b["emoji"] in stickers.EMOJI else "joy")
                if not path:
                    continue
                sx = b["cx"] + (b["w"] // 2 - 20 if b["right"] else 20 - b["w"] // 2)
                sy = b["cy"] - b["h"] // 2 + 10
                t0, t1 = b["t0"] + 0.1, b["t1"]
                more, filters, vout = stickers.overlay_args(path, idx, t0, t1, sx, sy, size=STICKER_SIZE,
                                                            src=vout, label=f"hst{k}",
                                                            alive_until=duration + hold)
                inputs += more
                graph += ";" + ";".join(filters)
                stickers_on.append(b["emoji"])
                idx += 1
        except Exception as e:  # noqa: BLE001 — the Short goes out without the emoji
            print(f"   ⚠️ Host emoji skipped ({type(e).__name__}: {e})")
    if hold or laughs:
        # Silence pads the clip's audio; the take's voice and the end card's
        # sound mix in on top, and the host's quiet laugh sounds.
        graph += f";[0:a]apad=pad_dur={hold:g}[a0]" if hold else ";[0:a]anull[a0]"
        mix = ["[a0]"]
        for k, lg in enumerate(laughs):
            graph += laugh_sound(look.get("sound"), lg["at"] + 0.02, k)
            mix.append(f"[fx{k}]")
        if voice:
            at = int((duration + TAKE_LEAD) * 1000)
            graph += (f";[1:a]{LOUDNORM_FILTER},aresample=48000,aformat=channel_layouts=stereo,"
                      f"adelay={at}|{at}[tk]")
            mix.append("[tk]")
        if cfg["outro"]:
            delay = int((duration + take_s) * 1000)
            graph += (f";{end_card_audio(secs)},aformat=channel_layouts=stereo,"
                      f"adelay={delay}|{delay}[sfx]")
            mix.append("[sfx]")
        graph += (f";{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0[a]"
                  if len(mix) > 1 else ";[a0]anull[a]")
        maps = ["-map", vout, "-map", "[a]"]
    else:
        maps = ["-map", vout, "-map", "0:a?"]
    try:
        subprocess.run(
            ["ffmpeg", "-y", *inputs, "-filter_complex", graph, *maps,
             *video_encode_args(QUALITY), "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", *METADATA_SCRUB,
             "-movflags", "+faststart", output_video],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1800)
    finally:
        if ass_path and os.path.exists(ass_path):
            os.remove(ass_path)
    print(f"🖼️ Framed {geo['w']}x{geo['h']} on {cfg['bg']} ({cfg['crop']}, zoom {cfg['zoom']:g})"
          + (f", title: {title}" if title else "")
          + (f", take {take_s:.1f}s" + ("" if voice else " (text only)") if take else "")
          + (f", host: {len(laughs)} laugh(s) {look.get('sound')}/{look.get('zoom')}/{'+'.join(stickers_on) or 'no emoji'}"
             if host else "")
          + (", end card" if cfg["outro"] else ""))
    return geo
