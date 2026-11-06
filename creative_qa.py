"""A look at every finished video before it uploads with nobody watching (29-oct-2026).

video_qa catches what a signal can (no sound, black, a frozen picture). This catches what only eyes can:
the defects one evening's contact sheets found by hand, each already on YouTube when it was found:
words cut mid-word ("7 SEPT 201", "COMMENT MEIN BAT"), green and magenta streaks round a cut-out photo,
a first frame with nothing on it, photos dimmed under a text bar, boxes for letters a font lacks.

One vision call sees the first frame (what the feed shows) and twelve numbered frames across the video.
A video is held back only when a second, independent look reports the same broken defect: one look alone
is too eager. Every verdict goes to state/creative_qa.jsonl, so defects that repeat show up as a pattern
to fix in the code rather than one video at a time.

CREATIVE_QA=0 turns it off; CREATIVE_QA=report records the verdicts without holding anything back.
"""
import io
import json
import os
import subprocess
import time
from typing import List

from pydantic import BaseModel

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "creative_qa.jsonl")
FRAMES = 12
# Defects that hold a video back when both looks call them broken. "unreadable" and "other" are
# judgement calls: recorded, never blocking.
BLOCKING = {"cut_text", "overlap", "boxes", "garbage", "empty_open"}


class Issue(BaseModel):
    kind: str
    frame: int
    detail: str
    severity: str


class Verdict(BaseModel):
    first_frame: int
    polish: int
    issues: List[Issue]
    best_fix: str


PROMPT = """You check a finished {shape} video for the YouTube channel "{channel}" before it is uploaded
automatically, with nobody watching. Its title: "{title}".
Image 1 is its very first frame, what the feed shows. Image 2 shows {n} frames across the whole video in
order, left to right and top to bottom, numbered 1 to {n} in their corners.

Report only clear defects a viewer would notice, each with the frame it is in (0 for image 1):
- cut_text: words cut off in the middle of a word, or text running past the edge of the frame.
- overlap: two pieces of text drawn on top of each other so that either is hard to read.
- boxes: empty squares or broken glyphs in place of letters (a font missing characters).
- garbage: a corrupted picture: colour streaks, smears, blocky glitch bars, torn areas.
- empty_open: image 1 shows neither readable text nor a clear subject (a plain or blank background).
- unreadable: text that cannot be read against what is behind it.
- other: anything else clearly broken.
severity: "broken" only when you are sure and it would embarrass the channel; else "minor".
Deliberate design is not a defect: blurred or darkened backgrounds, dark veils, stylised or outlined
text, emoji stickers, "?" placeholders waiting to be revealed, a board or list still filling in,
a countdown, the end card asking viewers to follow. {scripts}
Also score first_frame (1-10: would it stop a thumb scrolling the feed?) and polish (1-10: does it look
professionally made?), and give best_fix: the one change that would most improve this video, one sentence.
Return no issues when you see none."""

SCRIPTS = {"quran": "Arabic script (the verses) and Urdu Nastaliq script (the translation) are expected here.",
           "history": "Urdu or English text is expected; Urdu may be in Latin letters."}


def enabled():
    return os.environ.get("CREATIVE_QA", "1").strip().lower() not in ("0", "off", "false")


def blocks():
    """False in report mode (CREATIVE_QA=report): verdicts are recorded, nothing is held back."""
    return os.environ.get("CREATIVE_QA", "1").strip().lower() != "report"


def _duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, timeout=60).stdout.strip()
    return float(out or 0)


def _frame(path, t, width):
    """One frame at ``t`` seconds as a PIL image ``width`` px wide."""
    from PIL import Image
    png = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", path,
                          "-frames:v", "1", "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                         capture_output=True, timeout=120).stdout
    if not png:
        raise RuntimeError(f"no frame at {t:.1f}s")
    return Image.open(io.BytesIO(png)).convert("RGB")


def pictures(path, n=FRAMES):
    """(first frame, contact sheet) as JPEG bytes. Portrait cells 270 px wide, landscape 400."""
    from PIL import Image, ImageDraw
    seconds = _duration(path)
    if seconds <= 0:
        raise RuntimeError("the video has no length")
    first = _frame(path, 0.0, 540)
    portrait = first.height > first.width
    cell = 270 if portrait else 400
    # A Short's last 1.6 s is its end card, whose words slide in: caught mid-slide they read as cut off
    # (calibration on real Shorts, 29-oct-2026).
    body = seconds - 1.6 if portrait and seconds > 8 else seconds
    times = [body * (k + 0.5) / n for k in range(n)]
    cells = [_frame(path, t, cell) for t in times]
    cols = 4 if portrait else 3
    rows = (n + cols - 1) // cols
    h = cells[0].height
    sheet = Image.new("RGB", (cols * (cell + 6) + 6, rows * (h + 6) + 6), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    for k, im in enumerate(cells):
        x, y = 6 + (k % cols) * (cell + 6), 6 + (k // cols) * (h + 6)
        sheet.paste(im, (x, y))
        draw.rectangle((x, y, x + 34, y + 24), fill=(255, 255, 255))
        draw.text((x + 6, y + 5), str(k + 1), fill=(200, 0, 0))

    def jpeg(im):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
        return buf.getvalue()
    return jpeg(first), jpeg(sheet)


def _shape(first):
    from PIL import Image
    im = Image.open(io.BytesIO(first))
    return "vertical Short" if im.height > im.width else "long 16:9"


def _look(client, model, first, sheet, prompt):
    import short_kit as kit
    from google.genai import types
    parts = [types.Part.from_bytes(data=first, mime_type="image/jpeg"),
             types.Part.from_bytes(data=sheet, mime_type="image/jpeg"), prompt]
    return kit.ask_json(client, Verdict, parts, model=model)


def _broken(verdict):
    return {i.kind for i in verdict.issues if i.severity == "broken" and i.kind in BLOCKING}


def review(path, title, channel_kind, channel_name="", client=None, model=None, look=None):
    """{"first_frame", "polish", "issues", "best_fix", "blocked": [kinds], "reason"} or None when the
    check could not run (the upload then goes ahead: this is an extra layer, not the only one).
    ``look``: a test seam replacing the vision call (first, sheet, prompt) -> Verdict."""
    try:
        first, sheet = pictures(path)
    except Exception as e:  # noqa: BLE001
        _record({"title": title, "kind": channel_kind, "error": f"frames: {type(e).__name__}: {str(e)[:120]}"})
        return None
    prompt = PROMPT.format(shape=_shape(first), channel=channel_name or channel_kind, title=(title or "")[:120], n=FRAMES,
                           scripts=SCRIPTS.get(channel_kind, "Text is expected in Latin letters (English or "
                                                             "Roman Urdu / Hinglish)."))
    if look is None:
        import script_craft
        import short_kit as kit
        client = client or kit.gemini()
        model = model or os.environ.get("CREATIVE_QA_MODEL") or script_craft.writer_model()

        def look(f, s, p):
            return _look(client, model, f, s, p)
    try:
        verdict = look(first, sheet, prompt)
        broken = _broken(verdict)
        if broken:
            # A second, independent look: only a defect both looks call broken holds the video back.
            broken &= _broken(look(first, sheet, prompt))
    except Exception as e:  # noqa: BLE001
        _record({"title": title, "kind": channel_kind, "error": f"look: {type(e).__name__}: {str(e)[:120]}"})
        return None
    reason = "; ".join(f"{i.kind} (frame {i.frame}): {i.detail}" for i in verdict.issues
                       if i.kind in broken and i.severity == "broken")[:300]
    out = {"first_frame": verdict.first_frame, "polish": verdict.polish, "best_fix": verdict.best_fix[:300],
           "issues": [i.model_dump() for i in verdict.issues][:12], "blocked": sorted(broken), "reason": reason}
    _record({"title": title, "kind": channel_kind, "path": path, **out})
    return out


def _record(row):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": int(time.time()), **row}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def digest(days=7):
    """{channel kind: {"videos", "first_frame", "polish", "issues": {kind: count}}} over the last days:
    the defects that repeat, for the owner's report and for fixing their cause."""
    since, out = time.time() - days * 86400, {}
    try:
        with open(LOG, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError):
        return {}
    for r in rows:
        if r.get("at", 0) < since or "polish" not in r:
            continue
        d = out.setdefault(r.get("kind") or "?", {"videos": 0, "first_frame": 0, "polish": 0, "issues": {}})
        d["videos"] += 1
        d["first_frame"] += r.get("first_frame") or 0
        d["polish"] += r.get("polish") or 0
        for i in r.get("issues") or []:
            d["issues"][i.get("kind")] = d["issues"].get(i.get("kind"), 0) + 1
    for d in out.values():
        d["first_frame"] = round(d["first_frame"] / d["videos"], 1)
        d["polish"] = round(d["polish"] / d["videos"], 1)
    return out
