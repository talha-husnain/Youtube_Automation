"""AI editor: change a finished video by saying what to change (owner, 29-oct-2026: "I don't want a generic
video editor ... I just give it a prompt or tell it what I want to change, and it does it").

Studio's AI box (StudioTab.jsx) sends the owner's words here. One Gemini call turns them into operations
from a closed list (OPS) and, for videos up to 10 minutes, watches the video itself so "the part where he
laughs" can be found. Code then finds the moments: a quoted line becomes its word times, and cuts are
moved into the gaps between words. ffmpeg renders the result from the ORIGINAL clean cut in one pass, so
quality never drops over many edits. Captions are burned last, the sound is levelled, and a look at
before/after frames checks that the change really happened. Every edit is a revision in the job's edits/
folder. The current one is published as ``subtitled_<ts>_ai_<clip>.mp4`` (the newest derived file is
what Studio plays and what the upload sends), and undo publishes an older one.

Ideas taken from the research (29-oct-2026); no code was copied:
- browser-use/video-use (MIT): an edit list kept apart from the file, never a cut inside a word, 30 ms
  fades at every cut, captions burned last, and a checker that looks at frames.
- MartinDelophy/ai-video-editor (MIT): revisions that never overwrite the input, all or nothing.
- video-db/Director: the model quotes the words and code finds their times.
- Descript, Kapwing, Captions and OpusClip: cheap edits are applied at once with a one-line plan, a
  question is asked only when nothing in the video matches, and every version is kept.

Edits of our own generated Shorts reuse what made them. A Short with a music bed keeps its voices apart
(short_kit.stem_path), so "change the music" swaps the bed instead of stacking a second one, and "make
the hook stronger" can send the topic back to the channel with the owner's notes (OWNER_NOTES).

CLI (run by the server in a subprocess): ``python ai_editor.py apply <job_id>`` reads edits/request.json
and writes edits/result.json; ``python ai_editor.py transcribe <job_id>`` transcribes an uploaded video.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import List

from pydantic import BaseModel

import studio

ROOT = os.path.dirname(os.path.abspath(__file__))
EDITS = "edits"
UPLOADS_FILE = os.path.join(ROOT, "state", "studio_uploads.json")
UPLOAD_GENRE = "studio_upload"
PLAN_VIDEO_SECONDS = 180          # the planner watches Shorts; longer videos it knows by their words
INLINE_VIDEO_BYTES = 18 * 1024 * 1024
FADE = 0.03                       # an audio fade at every cut: no clicks (video-use)
CUT_PAD = 0.06                    # a cut lands this far into the gap from the word it keeps
MIN_SECONDS = 3.0
SHORTS_MAX = 179.5
MAX_PASSES = 2                    # a plan, and one fix when the check says the change did not happen
PLAN_TOKENS = 8192                # output cap of a plan / suggestion call (a real plan is ~1-2 KB)

OPS = {
    "cut": "remove a stretch. quote = the exact words to remove (copied from SPOKEN WORDS), or start/end",
    "keep": "keep only this stretch and drop the rest. quote or start/end",
    "tighten": "remove the pauses between words longer than amount seconds (default 0.3): for 'faster', "
               "'remove the silences', 'tighter'",
    "speed": "play faster or slower: amount = factor 0.5-2 (1.1 = 10% faster, 0.5 = slow motion). With quote "
             "or start/end only that stretch changes (slow motion on a moment, a boring part faster); "
             "without, the whole video",
    "zoom": "punch in on a moment: quote or start/end; amount = zoom 1.1-1.6 (default 1.25)",
    "text": "words on screen: text; quote or start/end (default: the first 3 seconds); value = position "
            "top|middle|bottom, optionally followed by '; color=yellow; size=1.3' (size 0.6-2)",
    "bleep": "hide words (a swear word, a name): quote = the exact words; value = beep (default) or mute",
    "blur": "blur part of the PICTURE (a logo, a watermark, another channel's name, a face, a number plate): "
            "value = 'box=x0,y0,x1,y1' with 0-1000 coordinates of the frame, read from the attached video, or "
            "top-left|top-right|bottom-left|bottom-right|top|bottom|left|right|center; text = pixelate for "
            "blocks instead of blur; quote or start/end, default the whole video; value = off removes all",
    "sfx": "a sound effect that starts at a moment: value = whoosh|pop|ding|boom|click|rise|scratch; quote or "
           "start; amount = dB louder (+) or quieter (-), 0 = normal",
    "sticker": "an animated emoji on screen for ~2 s: value = one of " + ", ".join(
        ["fire", "shocked", "mind_blown", "joy", "heartbreak", "eyes", "check", "cross", "hundred", "trophy",
         "cricket", "thinking", "point_down", "clap", "crying", "angry", "rocket", "crown"])
               + "; quote or start/end; text = top-left|top-right|middle|bottom-left|bottom-right",
    "clean_audio": "clean up the speech: background noise, hum and hiss out, the level evened: amount = "
                   "strength 0.2-1 (default 0.6); value = off to undo",
    "fade": "fade from and/or to black, the sound with it: value = in|out|both|off; amount = seconds (default 0.6)",
    "undo": "take back AI edits: value = last (the latest edit, default) or all (back to the video before "
            "any AI edit). Use it alone",
    "caption_fix": "correct a word everywhere in the captions: text = 'wrong => right'",
    "caption_style": "caption look: value like 'color=yellow; size=1.3; position=middle; case=normal'. "
                     "Keys: color, highlight (the spoken word's colour), size (0.6-2), position "
                     "(top|middle|bottom), case (upper|normal)",
    "captions": "value = off or on",
    "translate_captions": "value = the language: english, roman urdu, hindi, urdu...",
    "music": "background music: value = a mood in a few words ('sad piano', 'energetic', 'calm') or 'off' "
             "or 'different'; amount = dB louder (+) or quieter (-), 0 = normal",
    "volume": "value = music|voice|all; amount = dB (+3 louder, -6 quieter)",
    "look": "picture look: value = darker|brighter|contrast|vivid|warm|cool|black and white|cinematic|normal; "
            "amount = strength 0.2-1 (default 0.5)",
    "broll": "cover a stretch with free stock footage, the sound stays: text = what to show, in English; "
             "quote or start/end",
    "title": "new title: text, or value = 'better' for a stronger one written for the owner",
    "description": "new description: text",
    "tags": "new tags: text, comma separated",
    "remake": "make this video again from its topic with these notes in text (a channel video not yet on "
              "YouTube; about 10 minutes): for 'stronger hook', 'new script', 'other voice'",
    "reframe": "change the shape: value = vertical|square|horizontal (the picture fits over a blurred copy)",
}
DETAIL_OPS = {"title", "description", "tags"}
FILE_OPS = set(OPS) - DETAIL_OPS - {"remake", "undo"}
SFX_KINDS = ("whoosh", "pop", "ding", "boom", "click", "rise", "scratch")
# Ops a still frame can show: only these send an edit to the before/after frame check.
VISIBLE_OPS = {"zoom", "text", "broll", "look", "reframe", "caption_style", "translate_captions", "caption_fix",
               "captions", "blur", "sticker"}
# Synthesised sound effects (aevalsrc expressions: no file, no licence): (expression, seconds). A whoosh
# uses short_kit's real Kenney (CC0) swooshes when they are there.
SFX_EXPR = {
    "pop": ("0.8*sin(2*PI*(900-700*t/0.09)*t)*exp(-38*t)", 0.14),
    "ding": ("0.38*sin(2*PI*1568*t)*exp(-3.5*t)+0.22*sin(2*PI*2352*t)*exp(-5*t)+0.1*sin(2*PI*3136*t)*exp(-7*t)", 1.4),
    "boom": ("0.9*sin(2*PI*(95-55*t)*t)*exp(-2.8*t)+0.25*(random(1)*2-1)*exp(-30*t)", 1.2),
    "click": ("0.7*(random(2)*2-1)*exp(-260*t)", 0.04),
    "rise": ("0.3*sin(2*PI*(180*t+380*t*t))*(t/1.3)*(1-exp(-(1.3-t)*30))", 1.3),
    "scratch": ("0.5*sin(2*PI*(1100-900*t/0.35)*t)*exp(-4*t)*(0.6+0.4*sin(2*PI*28*t))", 0.35),
}
# Where a region preset sits, as fractions of the frame (x0, y0, x1, y1).
REGIONS = {"top-left": (0.0, 0.0, 0.34, 0.16), "top-right": (0.66, 0.0, 1.0, 0.16),
           "bottom-left": (0.0, 0.84, 0.34, 1.0), "bottom-right": (0.66, 0.84, 1.0, 1.0),
           "top": (0.0, 0.0, 1.0, 0.16), "bottom": (0.0, 0.84, 1.0, 1.0), "left": (0.0, 0.0, 0.3, 1.0),
           "right": (0.7, 0.0, 1.0, 1.0), "center": (0.3, 0.35, 0.7, 0.65), "full": (0.0, 0.0, 1.0, 1.0)}
STICKER_SPOTS = {"top-left": (0.22, 0.2), "top-right": (0.78, 0.2), "middle": (0.5, 0.45),
                 "bottom-left": (0.22, 0.62), "bottom-right": (0.78, 0.62)}
COLOURS = {"yellow": "#FFE500", "white": "#FFFFFF", "red": "#FF3B3B", "green": "#35E07A", "blue": "#3BA4FF",
           "orange": "#FF9F1C", "pink": "#FF5FA2", "purple": "#B57BFF", "black": "#000000", "gold": "#FFD23F",
           "cyan": "#33E1FF"}
LOOKS = ("darker", "brighter", "contrast", "vivid", "warm", "cool", "black and white", "cinematic")
OPPOSITE = {"darker": "brighter", "brighter": "darker", "warm": "cool", "cool": "warm"}
URDU_LETTERS = re.compile("[" + chr(0x600) + "-" + chr(0x6FF) + "]")  # Urdu script on screen gets the Nastaliq font


class Op(BaseModel):
    op: str
    quote: str = ""
    start: float = -1.0
    end: float = -1.0
    text: str = ""
    value: str = ""
    amount: float = 0.0


class Plan(BaseModel):
    summary: str
    ops: List[Op]
    assumptions: List[str] = []
    question: str = ""
    why_not: str = ""


class Check(BaseModel):
    done: bool
    problems: List[str]


class Lines(BaseModel):
    lines: List[str]


class EditError(studio.StudioError):
    """An edit that cannot be made, with a reason the owner can read."""


PROMPT = """You are the video editor inside the owner's YouTube studio. The owner wrote what to change in
this video, in their own words (Roman Urdu, Urdu, Hindi or English):

  "{request}"

{sheet}

Turn the request into operations from this closed list, and nothing else:
{ops}

Rules:
- Do exactly what was asked and nothing more. Never "improve" anything that was not mentioned.
- A follow-up ("thoda aur", "a bit more", "remove the zoom") refers to EDITS SO FAR; to undo one, use
  the opposite operation (look normal, captions on, music off...).
- Point at moments with `quote`, copying the exact words from SPOKEN WORDS. Use start/end seconds only
  when the owner gives times or the moment has no words. {video_note}
- Times are seconds of the video AS IT IS NOW (the SPOKEN WORDS list), never of an older version.
- Leave the fields an operation does not use empty (start/end -1, amount 0, text and value "").
- If part of the request cannot be done with these operations, say why in why_not and name the nearest
  thing you can do. Do that if it is close.
- Ask a question only when the request names nothing you can find in this video. Otherwise take the most
  obvious reading, do it, and put your guess in assumptions.
- "A logo", "a watermark", "another channel's name" never means OUR OWN BRANDING (in the sheet). If the
  only branding you see is ours, do nothing to it and say so in why_not.
- A sound effect or a sticker happens AT a moment: give the quote of the words it goes with, or start
  (end may stay -1).
- summary: one short line in the owner's language and script saying what you are doing, like
  "Shuru ke 2 second kaate, captions peele aur bade" or "Cut the first 2 s, yellow captions at 1.3x".
{limits}{note}"""

CHECK_PROMPT = """The owner of a YouTube channel asked their video editor: "{request}"
The editor's plan: "{summary}"
The image shows the same moments of the video: row 1 BEFORE the edit, row 2 AFTER it.
Did the requested VISIBLE change happen, and did the edit break anything: text cut off, text overlapping,
empty boxes in place of letters, a corrupted picture? done = true only when the change the owner asked
for can be seen in row 2 and nothing broke. List each problem in plain words (none when fine). Changes to
sound, timing or cuts cannot be seen in still frames: judge only what a picture can show."""

TRANSLATE_PROMPT = """Translate each numbered caption line of a YouTube video into {language}. Keep the
meaning and the tone, short and spoken, one line out for each line in. Roman Urdu or Hinglish means Latin
letters. Return exactly {n} lines in the same order, without the numbers.

{lines}"""


# ---------------------------------------------------------------- small helpers

def _now():
    return int(time.time())


def edits_name(index=0):
    """The edit chain's folder inside the job: edits/ for the first clip, edits_clip<n>/ for clip n of a job
    cut into several Shorts (each clip is its own video with its own versions)."""
    return EDITS if not index else f"{EDITS}_clip{int(index) + 1}"


def _edits(path, index=0):
    d = os.path.join(path, edits_name(index))
    os.makedirs(d, exist_ok=True)
    return d


def edits_dir(ref):
    """The edit folder of a Studio id (made when missing)."""
    return _edits(studio.job_dir(ref), studio.split_ref(ref)[1])


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)


def load(path, index=0):
    return _read_json(os.path.join(path, edits_name(index), "state.json"), None)


def save(path, state):
    """The chain's state, into the folder of the clip it belongs to (its base says which)."""
    _write_json(os.path.join(_edits(path, (state.get("base") or {}).get("clip") or 0), "state.json"), state)


def stage(path, text, index=0):
    """What the edit is doing now, for the Studio's progress line (and, timed, in edits/edit.log)."""
    _write_json(os.path.join(_edits(path, index), "task.json"), {"stage": text, "at": time.time()})
    print(f"{time.strftime('%H:%M:%S')} {text}", flush=True)


def _probe(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate:"
                        "format=duration", "-of", "json", video], capture_output=True, text=True, timeout=60)
    info = json.loads(r.stdout or "{}")
    v = next((s for s in info.get("streams") or [] if s.get("codec_type") == "video"), {})
    num, _, den = (v.get("r_frame_rate") or "30/1").partition("/")
    try:
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        fps = 30.0
    return {"w": int(v.get("width") or 1080), "h": int(v.get("height") or 1920),
            "fps": round(fps, 3) if 10 <= fps <= 61 else 30.0,
            "audio": any(s.get("codec_type") == "audio" for s in info.get("streams") or []),
            "seconds": float((info.get("format") or {}).get("duration") or 0)}


def _rel(p, start):
    """``p`` relative to ``start`` with forward slashes; absolute when they are on different drives."""
    try:
        return os.path.relpath(p, start).replace("\\", "/")
    except ValueError:
        return os.path.abspath(p)


def _merge(ranges):
    out = []
    for a, b in sorted((float(a), float(b)) for a, b in ranges if b > a):
        if out and a <= out[-1][1] + 1e-6:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _subtract(keep, a, b):
    out = []
    for ka, kb in keep:
        if b <= ka or a >= kb:
            out.append((ka, kb))
            continue
        if a > ka:
            out.append((ka, a))
        if b < kb:
            out.append((b, kb))
    return [(x, y) for x, y in out if y - x > 0.04]


def _intersect(keep, ranges):
    out = []
    for ka, kb in keep:
        for a, b in ranges:
            lo, hi = max(ka, a), min(kb, b)
            if hi - lo > 0.04:
                out.append((lo, hi))
    return _merge(out)


SPEED_MIN, SPEED_MAX = 0.25, 4.0  # a stretch's own speed times the whole video's


class Timeline:
    """The kept stretches of the base video (base seconds) played at ``speed``, with ``segments``
    [(a, b, factor)] of base time played at their own factor on top (slow motion on one moment, a boring
    stretch faster; 4-nov-2026): maps base <-> output time. ``pieces`` = [(a, b, factor)]: every kept
    stretch split where a segment starts or ends, each with the factor it plays at."""

    def __init__(self, keep, speed=1.0, segments=()):
        self.keep = [(float(a), float(b)) for a, b in keep if b - a > 0.04]
        self.speed = float(speed or 1.0)
        segs = [(float(a), float(b), float(f)) for a, b, f in segments or () if b - a > 0.04 and f > 0]
        cuts = sorted({x for a, b, _ in segs for x in (a, b)})
        self.pieces = []
        for a, b in self.keep:
            bounds = [a] + [c for c in cuts if a + 1e-6 < c < b - 1e-6] + [b]
            for lo, hi in zip(bounds, bounds[1:]):
                f = 1.0
                for sa, sb, sf in segs:                     # the last segment over a stretch wins
                    if sa - 1e-6 <= (lo + hi) / 2 <= sb + 1e-6:
                        f = sf
                f = _clamp(f * self.speed, SPEED_MIN, SPEED_MAX)
                if self.pieces and abs(self.pieces[-1][2] - f) < 1e-9 and abs(self.pieces[-1][1] - lo) < 1e-9:
                    self.pieces[-1] = (self.pieces[-1][0], hi, f)     # same speed, no cut: one piece
                else:
                    self.pieces.append((lo, hi, f))
        self.starts, t = [], 0.0
        for a, b, f in self.pieces:
            self.starts.append(t)
            t += (b - a) / f
        self._duration = t
        self.raw = sum(b - a for a, b in self.keep)

    @property
    def duration(self):
        return self._duration

    @property
    def uniform(self):
        """True when every piece plays at the same speed (no stretch of its own)."""
        return len({round(f, 6) for _a, _b, f in self.pieces}) <= 1

    def out(self, t):
        """Output time of base time ``t``, or None when that moment was cut."""
        for (a, b, f), s in zip(self.pieces, self.starts):
            if a - 1e-6 <= t <= b + 1e-6:
                return s + (min(max(t, a), b) - a) / f
        return None

    def out_ranges(self, a, b):
        res = []
        for (ka, kb, f), s in zip(self.pieces, self.starts):
            lo, hi = max(a, ka), min(b, kb)
            if hi - lo > 0.02:
                res.append((s + (lo - ka) / f, s + (hi - ka) / f))
        return _merge(res)

    def base(self, t):
        t = max(0.0, t)
        for (a, b, f), s in zip(self.pieces, self.starts):
            if t <= s + (b - a) / f + 1e-6:
                return a + max(0.0, t - s) * f
        return self.pieces[-1][1] if self.pieces else 0.0

    def base_ranges(self, a, b):
        """The base stretches an output stretch shows (what earlier edits cut is skipped)."""
        res = []
        for (ka, kb, f), s in zip(self.pieces, self.starts):
            lo, hi = max(a, s), min(b, s + (kb - ka) / f)
            if hi - lo > 0.02:
                res.append((ka + (lo - s) * f, ka + (hi - s) * f))
        return _merge(res)


# ---------------------------------------------------------------- the job, its base and its words

def _main_name():
    try:
        import youtube_account
        return ((youtube_account.status().get("channel") or {}).get("title") or "").strip() or "the main channel"
    except Exception:  # noqa: BLE001 — a name for the sheet only
        return "the main channel"


def context(job_id, channels=None):
    """What the editor knows about the video before any request. ``job_id`` is a Studio id: a job id, or
    "<job id>.<n>" for clip n of a job cut into several Shorts (the main comedy channel's)."""
    path = studio.job_dir(job_id)
    jid, index = studio.split_ref(job_id)
    data = studio._read(path)
    short = studio.clip_of(data, index)
    if channels is None:
        try:
            import my_channels
            channels = my_channels.channels()
        except Exception:  # noqa: BLE001 — an upload needs no channel
            channels = []
    ch, j = studio._find_job(job_id, channels)
    upload = (data.get("genre") == UPLOAD_GENRE)
    # The comedy pipeline keeps its genre in .source.json, not in the metadata: read as "" the editor drew
    # its captions in the generated Shorts' emphasis style instead of the comedy look.
    genre = data.get("genre") or studio._source(path).get("genre") or ""
    main = None if ch or upload else studio.main_clip(jid, index, path)
    # Our own branding on screen (4-nov-2026): asked to blur "another channel's logo", the planner blurred
    # the channel's OWN handle in the top band. The sheet now names what is ours.
    frame = _read_json(os.path.join(path, "frame.json"), {}) or {}
    main_name = _main_name() if main is not None else None
    own = [x for x in dict.fromkeys([frame.get("handle"), (ch or {}).get("handle"), (ch or {}).get("yt_title"),
                                     (ch or {}).get("name"), main_name if main_name != "the main channel" else None])
           if x]
    if main is not None:
        state = studio.main_state(main)
    else:
        state = studio.state_of(ch, j) if ch else ("your upload" if upload else "not on a channel")
    return {"job_id": studio.ref_of(jid, index), "path": path, "index": index,
            "channel": ch["id"] if ch else ("main" if main is not None else None),
            "channel_name": (ch or {}).get("name") or ("Your uploads" if upload else (main_name or "")),
            "kind": (ch or {}).get("kind") or ("upload" if upload else genre),
            "genre": genre, "upload": upload, "main": main is not None,
            "on_youtube": bool(j and j.get("status") == "uploaded") or (main or {}).get("status") == "posted",
            "video_id": (j or {}).get("video_id") or (main or {}).get("youtube_id"),
            "state": state,
            "topic": (j or {}).get("topic") or short.get("seo_title") or "",
            "remakable": bool(ch and j and j.get("topic") and j.get("status") == "done"),
            "framed": data.get("output_format") == "framed", "own": own,
            "lesson": ((ch or {}).get("stats") or {}).get("retention_lesson") or "",
            "search": [str(t[0]) for t in ((ch or {}).get("stats") or {}).get("search") or [] if t]}


def _meta_snapshot(data, index=0):
    short = studio.clip_of(data, index)
    return {"transcript": studio.clip_transcript(data, index),
            "short": {k: short.get(k) for k in ("seo_title", "seo_description", "seo_tags",
                                                "video_title_for_youtube_short", "start", "end", "seconds")}}


def ensure_base(path, index=0):
    """The edit chain's starting point: the clean cut (no captions) and the details as they were. A new
    chain starts at the first edit, and again when the video was changed outside the AI editor (a manual
    trim or caption edit in Studio), so revisions always build on what the owner last saw.

    A clip cut from a longer show (the comedy pipeline's jobs hold 3) shares the WHOLE source's transcript, in
    source seconds; its base words are the slice its captions were made from (``studio.clip_transcript``),
    and that shared transcript is never rewritten (``_publish``): it also serves the other clips."""
    state = load(path, index)
    served = os.path.basename(studio.served(path, index))
    if state and served in [state["base"]["served"]] + [p["name"] for p in state.get("published") or []]:
        return state
    data = studio._read(path)
    clean = studio.clean_source(path, index)
    shared = studio.shares_transcript(data, index)
    meta = _meta_snapshot(data, index)
    original = os.path.basename(clean) == f"{studio._base(path)}_clip_{index + 1}.mp4"
    stem = None
    if original:
        import short_kit as kit
        s = kit.stem_path(clean)
        stem = os.path.basename(s) if os.path.isfile(s) else None
    info = _probe(clean)
    captions = bool(_words(meta["transcript"])) and data.get("output_format") == "framed" \
        and served.startswith("subtitled_")
    state = {"base": {"video": os.path.basename(clean), "served": served, "stem": stem,
                      "seconds": info["seconds"] or studio.duration(clean), "w": info["w"], "h": info["h"],
                      "fps": info["fps"], "audio": info["audio"], "captions": captions,
                      "bed": bool(stem), "meta": meta, "at": _now(), "clip": index, "shared": shared},
             "revisions": [], "current": 0, "published": [], "translations": {},
             "older": (state or {}).get("revisions", [])[-20:]}
    save(path, state)
    return state


def _words(transcript):
    return [w for s in (transcript or {}).get("segments") or [] for w in s.get("words") or []
            if (w.get("word") or "").strip()]


def _current_ops(state):
    n = state.get("current") or 0
    return list(state["revisions"][n - 1]["all_ops"]) if n else []


def _current_meta(state):
    n = state.get("current") or 0
    return state["revisions"][n - 1]["meta"] if n else state["base"]["meta"]


def words_now(base_words, tl):
    """The base words that survive the cuts, in output time."""
    out = []
    for w in base_words:
        a, b = tl.out(float(w["start"])), tl.out(float(w["end"]))
        if a is None or b is None or b < a:
            continue
        out.append({"word": w["word"].strip(), "start": round(a, 3), "end": round(b, 3)})
    return out


def _phrases(words, most=12):
    """Words grouped into short lines (a pause, a sentence end or ``most`` words end one)."""
    lines, cur = [], []
    for k, w in enumerate(words):
        cur.append(w)
        gap = (words[k + 1]["start"] - w["end"]) if k + 1 < len(words) else 9
        if len(cur) >= most or gap > 0.6 or w["word"][-1:] in ".?!":
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return lines


def edit_sheet(ctx, state, tl, words):
    base = state["base"]
    meta = _current_meta(state)
    short = meta["short"]
    spec = compile_ops(_current_ops(state), base["seconds"], _words(base["meta"]["transcript"]), base)
    what = ("the owner's own uploaded video" if ctx["upload"]
            else f"a {ctx['kind']} video of the channel \"{ctx['channel_name']}\"")
    status = ("ALREADY ON YOUTUBE: only title, description and tags can change; YouTube keeps the file it was "
              "sent" if ctx["on_youtube"] else ctx["state"])
    captions = ("on, burned by us from SPOKEN WORDS (style and words can change)" if spec["captions"]
                else ("off" if base["captions"] or _words(base["meta"]["transcript"])
                      else "none of ours (the video may show its own; those cannot be restyled)"))
    music = ("a background bed under the voices: it can be swapped or turned off" if base.get("stem")
             else ("mixed into the sound: new music can be added under it, the old one cannot be removed"
                   if ctx["genre"] not in ("", UPLOAD_GENRE) else
                   "whatever the uploaded sound has: new music can be added under it"))
    if spec["music"]:
        music += f"; now: {spec['music']['value']}"
    revs = state["revisions"][:state.get("current") or 0]
    lines = [f"VIDEO: {tl.duration:.1f} s, {'vertical' if base['h'] > base['w'] else 'horizontal'} "
             f"{base['w']}x{base['h']}, {what}.",
             f"STATUS: {status}.",
             f"TITLE: {short.get('seo_title') or ''}",
             f"DESCRIPTION: {(short.get('seo_description') or '')[:500]}",
             "CREDITS in the description (always kept by code; never write them yourself): "
             + ("; ".join(b.splitlines()[0][:60] for b in studio.credit_blocks(short.get("seo_description")))
                or "none"),
             f"TAGS: {', '.join(short.get('seo_tags') or [])[:300]}",
             f"CAPTIONS: {captions}.", f"MUSIC: {music}.",
             "OUR OWN BRANDING on screen (this channel's; keep it unless the owner names it): "
             + ("; ".join(ctx.get("own") or []) or "none") + ", and the end card with the follow button",
             "EDITS SO FAR: " + ("; ".join(f'{r["n"]}) "{r["prompt"][:90]}" -> {r["summary"][:90]}'
                                           for r in revs) or "none")]
    # What YouTube says about this channel's viewers (my_channels._insights): where they leave, what they searched.
    if ctx.get("lesson"):
        lines.append("VIEWERS OF THIS CHANNEL: " + ctx["lesson"][:500])
    if ctx.get("search"):
        lines.append("THEY FOUND THIS CHANNEL BY SEARCHING: " + ", ".join(ctx["search"][:10]))
    lines.append("SPOKEN WORDS (seconds, as the video is now):")
    budget = 14000
    for ph in _phrases(words):
        line = f"{ph[0]['start']:.2f}-{ph[-1]['end']:.2f} " + " ".join(w["word"] for w in ph)
        budget -= len(line)
        if budget < 0:
            lines.append("... (more words follow)")
            break
        lines.append(line)
    if not words:
        lines.append("(no words: the video has no speech we know of)")
    return "\n".join(lines)


# ---------------------------------------------------------------- the plan

def proxy(path, video, index=0):
    """A small copy of the video for the planner to watch, kept until the video changes: Gemini samples
    about a frame a second, and the full file (10-18 MB inline) had its connection reset mid-send on the
    first live run (29-oct-2026). 360 px on the short side, 10 fps, mono sound: ~2 MB for a Short."""
    out = os.path.join(_edits(path, index), "proxy.mp4")
    if os.path.isfile(out) and os.path.getmtime(out) >= os.path.getmtime(video):
        return out
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", video, "-vf",
                        "scale='if(gt(iw,ih),-2,360)':'if(gt(iw,ih),360,-2)',fps=10", "-c:v", "libx264",
                        # ultrafast: a 360 px, 10 fps look for the planner; veryfast took most of the 10-17 s
                        # "Reading the video" on a busy CPU (live run, 4-nov-2026).
                        "-preset", "ultrafast", "-crf", "30", "-c:a", "aac", "-b:a", "48k", "-ac", "1",
                        "-movflags", "+faststart", out], capture_output=True, text=True, timeout=600)
    return out if r.returncode == 0 and os.path.isfile(out) else None


def plan(client, request, sheet, ctx, video=None, note=""):
    import script_craft
    import short_kit as kit
    from google.genai import types
    ops = "\n".join(f"- {k}: {v}" for k, v in OPS.items())
    limits = ""
    if ctx["on_youtube"]:
        limits = "\n- This video is ALREADY ON YOUTUBE: use only title, description and tags."
    elif ctx["upload"]:
        limits = "\n- This is the owner's own uploaded file: remake is not available."
    elif not ctx["remakable"]:
        limits = "\n- remake is not available for this video."
    prompt = PROMPT.format(request=request, sheet=sheet, ops=ops, limits=limits,
                           video_note=("The video is attached: use what you see and hear to find moments "
                                       "that have no words." if video else ""),
                           note=f"\n\n{note}" if note else "")
    parts = [prompt]
    if video:
        size = os.path.getsize(video)
        if size <= INLINE_VIDEO_BYTES:
            with open(video, "rb") as f:
                parts = [types.Part.from_bytes(data=f.read(), mime_type="video/mp4"), prompt]
        else:
            up = client.files.upload(file=video)
            for _ in range(60):
                if getattr(up.state, "name", str(up.state)) != "PROCESSING":
                    break
                time.sleep(2)
                up = client.files.get(name=up.name)
            parts = [up, prompt]
    # A plan is ~1-2 KB: the cap ends a runaway answer in seconds, and a broken one is asked once more.
    return kit.ask_json(client, Plan, parts, model=os.environ.get("AI_EDIT_MODEL") or script_craft.writer_model(),
                        max_tokens=PLAN_TOKENS, invalid_tries=2)


def _norm(word):
    return re.sub(r"[^\w]", "", (word or "").lower())


def find_quote(words, quote):
    """(first, last) word indexes of the stretch of ``words`` that best matches ``quote``, or None. One word
    more or fewer is tolerated; at least 60% of the quote's words must match in order."""
    q = [t for t in (_norm(x) for x in (quote or "").split()) if t]
    toks = [_norm(w["word"]) for w in words]
    if not q or not toks:
        return None
    n = len(q)
    for i in range(len(toks) - n + 1):            # an exact run first
        if toks[i:i + n] == q:
            return i, i + n - 1
    best, score = None, 0.0
    for i in range(len(toks)):
        if not any(_same(toks[i], x) for x in q):
            continue
        for length in (n - 1, n, n + 1):
            if length < 1 or i + length > len(toks):
                continue
            s = _lcs(q, toks[i:i + length]) / max(n, length)
            if s > score:
                best, score = (i, i + length - 1), s
    return best if score >= 0.6 else None


def _same(a, b):
    """Two normalised words that are the same word as spoken and as quoted: equal, one a longer form of the
    other ("record" / "records", "kohli" / "kohlis"), or one or two letters apart in a long word (Roman Urdu
    has no fixed spelling: "zabardast" / "zabardust")."""
    if a == b:
        return True
    if min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)) and abs(len(a) - len(b)) <= 2:
        return True
    if min(len(a), len(b)) >= 6:
        import difflib
        return difflib.SequenceMatcher(None, a, b).ratio() >= 0.84
    return False


def _lcs(a, b):
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for k, y in enumerate(b):
            cur.append(prev[k] + 1 if _same(x, y) else max(prev[k + 1], cur[k]))
        prev = cur
    return prev[-1]


def _snap(t, words, side):
    """A cut boundary moved out of any word it falls inside, into the gap: ``side`` "start" keeps the
    word when less than half of it would be cut (and cuts all of it otherwise); "end" likewise."""
    for k, w in enumerate(words):
        a, b = w["start"], w["end"]
        if a < t < b:
            prev_end = words[k - 1]["end"] if k else 0.0
            next_start = words[k + 1]["start"] if k + 1 < len(words) else b + 1
            cut_it = (b - t) > (t - a) if side == "start" else (t - a) > (b - t)
            if side == "start":
                return max(prev_end, a - CUT_PAD) if cut_it else min(next_start, b + CUT_PAD)
            return min(next_start, b + CUT_PAD) if cut_it else max(prev_end, a - CUT_PAD)
    return t


def _span(op, words, duration):
    """(start, end) in output seconds for an op, from its quote or its times, or None."""
    if op.quote.strip():
        hit = find_quote(words, op.quote)
        if hit:
            i, j = hit
            prev_end = words[i - 1]["end"] if i else 0.0
            next_start = words[j + 1]["start"] if j + 1 < len(words) else duration
            return max(prev_end, words[i]["start"] - CUT_PAD), min(next_start, words[j]["end"] + CUT_PAD)
    if op.start >= 0 or op.end >= 0:
        a = max(0.0, op.start if op.start >= 0 else 0.0)
        b = min(duration, op.end if op.end >= 0 else duration)
        if b - a > 0.15:
            return a, b
    return None


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def resolve(p, ctx, state, tl, words):
    """The plan's operations checked and turned into base-time records. Returns (ops, details, remake,
    notes): ``details`` the title/description/tags changes, ``remake`` the notes when the video goes back
    to the channel, ``notes`` what could not be done, in plain words."""
    duration = tl.duration
    ops, details, remake, notes = [], {}, None, []
    last_span = None          # the moment of the plan's previous located op (output seconds)
    for op in p.ops:
        kind = (op.op or "").strip().lower()
        if kind not in OPS:
            notes.append(f"'{op.op}' is not something this editor can do.")
            continue
        if ctx["on_youtube"] and kind not in DETAIL_OPS:
            notes.append("The video is already on YouTube, which keeps the file it was sent: only its title, "
                         "description and tags can change.")
            continue
        if kind in DETAIL_OPS:
            details[kind] = {"text": op.text.strip(), "value": op.value.strip().lower()}
            continue
        if kind == "remake":
            if ctx["remakable"]:
                remake = op.text.strip() or p.summary
            else:
                notes.append("This video cannot be sent back to be made again (only a channel video that is "
                             "not on YouTube yet can).")
            continue
        if kind == "undo":
            continue                                    # apply() takes undo before anything else
        rec = {"op": kind}
        pointed = bool(op.quote.strip()) or op.start >= 0 or op.end >= 0
        value = op.value.strip().lower()
        if kind == "blur" and value == "off":
            rec.update(value="off", ranges=[])
            ops.append(rec)
            continue
        if kind == "bleep" and not pointed:
            notes.append("Say which words to bleep.")
            continue
        if kind in ("cut", "keep", "zoom", "text", "broll", "bleep", "blur", "sfx", "sticker") \
                or (kind == "speed" and pointed):
            span = _span(op, words, duration)
            if span is None and not pointed and last_span and kind in ("sticker", "sfx", "zoom", "text"):
                # "...wahan slow motion karo aur fire emoji lagao": the planner sent the sticker with no
                # moment of its own (live run, 4-nov-2026). It goes where the op before it went.
                span = last_span
            if span is None and kind in ("sfx", "sticker") and op.start >= 0:
                # A moment, not a stretch: the planner sends start=0, end=0 for "a whoosh at the start"
                # (live run, 4-nov-2026: both sounds of a request were dropped as "not found").
                span = (min(op.start, duration), min(duration, op.start + 0.3))
            if span is None and kind == "text":
                span = (0.0, min(3.0, duration))
            if span is None and kind == "blur" and not pointed:
                span = (0.0, duration)                  # a logo is there the whole video
            if span is None:
                what = f'"{op.quote}"' if op.quote else "that moment"
                notes.append(f"Could not find {what} in the video.")
                continue
            a, b = span
            if kind not in ("cut", "keep", "blur"):
                last_span = (a, b)
            if kind in ("cut", "keep") and not op.quote.strip():
                a, b = _snap(a, words, "start"), _snap(b, words, "end")
            if kind == "sticker":
                b = min(duration, max(b, a + 2.2) if b - a < 1.2 else min(b, a + 3.0))
            rec["ranges"] = [list(r) for r in tl.base_ranges(a, b)]
            if kind == "sfx":
                rec["ranges"] = rec["ranges"][:1]          # one sound, where the moment starts
            if not rec["ranges"]:
                continue
            if kind == "zoom":
                rec["amount"] = _clamp(op.amount or 1.25, 1.05, 1.8)
            if kind == "text":
                if not op.text.strip():
                    continue
                rec["text"] = op.text.strip()[:140]
                first = value.split(";")[0].strip()
                rec["value"] = first if first in ("top", "middle", "bottom") else "top"
                style = _style(value)
                if style:
                    rec["style"] = {k: v for k, v in style.items() if k in ("color", "size")}
            if kind == "broll":
                if not (op.text or op.quote).strip():
                    continue
                rec["text"] = (op.text or op.quote).strip()[:80]
            if kind == "speed":
                if not op.amount:
                    continue
                rec["amount"] = _clamp(op.amount, SPEED_MIN, SPEED_MAX)
            if kind == "bleep":
                rec["value"] = "mute" if value.startswith("mute") or value == "silence" else "beep"
            if kind == "blur":
                box = _region(value)
                if box is None:
                    notes.append(f"Could not tell where '{op.value}' is; say a corner or a side.")
                    continue
                rec["box"] = list(box)
                rec["text"] = "pixelate" if "pixel" in op.text.lower() or "pixel" in value else "blur"
            if kind == "sfx":
                kind_sfx = next((s for s in SFX_KINDS if s in value), None)
                if not kind_sfx:
                    notes.append(f"No '{op.value}' sound; the sounds are: {', '.join(SFX_KINDS)}.")
                    continue
                rec["value"], rec["amount"] = kind_sfx, _clamp(op.amount or 0.0, -12, 8)
            if kind == "sticker":
                import stickers
                name = re.sub(r"[^a-z_]", "", value.replace(" ", "_"))
                if not stickers.path(name):
                    notes.append(f"No '{op.value}' sticker here.")
                    continue
                spot = op.text.strip().lower()
                rec["value"], rec["text"] = name, spot if spot in STICKER_SPOTS else "top-right"
        elif kind == "tighten":
            rec["amount"] = _clamp(op.amount or 0.3, 0.12, 1.5)
        elif kind == "speed":
            if not op.amount:
                continue
            rec["amount"] = _clamp(op.amount, 0.5, 2.0)
        elif kind == "clean_audio":
            if not state["base"].get("audio"):
                notes.append("This video has no sound to clean.")
                continue
            rec["value"] = "off" if value == "off" else "on"
            rec["amount"] = _clamp(op.amount or 0.6, 0.2, 1.0)
        elif kind == "fade":
            rec["value"] = value if value in ("in", "out", "both", "off") else "both"
            rec["amount"] = _clamp(op.amount or 0.6, 0.2, 3.0)
        elif kind == "caption_fix":
            wrong, _, right = op.text.replace("->", "=>").partition("=>")
            if not wrong.strip():
                continue
            rec["text"] = f"{wrong.strip()} => {right.strip()}"
        elif kind in ("caption_style", "captions", "translate_captions", "reframe"):
            if not op.value.strip():
                continue
            rec["value"] = op.value.strip()
        elif kind == "music":
            rec["value"] = (op.value or op.text or "different").strip()[:60]
            rec["amount"] = _clamp(op.amount or 0.0, -15, 10)
            if rec["value"].lower() in ("off", "none", "no music") and not state["base"].get("stem") \
                    and ctx["genre"] not in ("", UPLOAD_GENRE):
                notes.append("This video's music is mixed into its sound (it was made before voices were kept "
                             "apart), so it cannot be taken out; new videos can.")
                continue
        elif kind == "volume":
            target = op.value.strip().lower() if op.value.strip().lower() in ("music", "voice", "all") else "all"
            rec["value"], rec["amount"] = target, _clamp(op.amount or 0.0, -20, 12)
            if target == "music" and not state["base"].get("stem") and not _has_music_op(_current_ops(state)):
                notes.append("The music is mixed into this video's sound, so only the whole sound can be made "
                             "louder or quieter.")
                rec["value"] = "all"
        elif kind == "look":
            value = op.value.strip().lower()
            if value not in LOOKS + ("normal",):
                notes.append(f"No '{op.value}' look; the looks are: {', '.join(LOOKS)}.")
                continue
            rec["value"], rec["amount"] = value, _clamp(op.amount or 0.5, 0.15, 1.0)
        ops.append(rec)
    return ops, details, remake, notes


def _has_music_op(ops):
    return any(o["op"] == "music" for o in ops)


# ---------------------------------------------------------------- everything at once, in base time

def _style(value, style=None):
    style = dict(style or {})
    for part in re.split(r"[;,]", value or ""):
        k, _, v = part.partition("=")
        k, v = k.strip().lower(), v.strip().lower()
        if not k or not v:
            continue
        if k in ("color", "colour", "highlight"):
            v = COLOURS.get(v, v if re.fullmatch(r"#[0-9a-f]{6}", v) else "")
            if v:
                style["highlight" if k == "highlight" else "color"] = v.upper()
        elif k == "size":
            try:
                style["size"] = _clamp(float(v.rstrip("x")), 0.6, 2.0)
            except ValueError:
                pass
        elif k == "position" and v in ("top", "middle", "bottom"):
            style["position"] = v
        elif k == "case" and v in ("upper", "normal"):
            style["case"] = v
    return style


def _region(value):
    """(x0, y0, x1, y1) as fractions of the frame from 'box=x0,y0,x1,y1' (0-1000, Gemini's own box scale;
    0-1 fractions are taken too) or a named spot; None when it names nothing. A box is padded by 2% of the
    frame (a watermark's guessed edge), and never smaller than 4% a side."""
    v = (value or "").lower().strip()
    nums = re.findall(r"-?\d+(?:\.\d+)?", v)
    if "box" in v or (len(nums) == 4 and not any(name in v for name in REGIONS)):
        if len(nums) < 4:
            return None
        x0, y0, x1, y1 = (float(n) for n in nums[:4])
        scale = 1.0 if max(x0, y0, x1, y1) <= 1.0 else 1000.0
        x0, x1 = sorted((x0 / scale, x1 / scale))
        y0, y1 = sorted((y0 / scale, y1 / scale))
        x0, y0, x1, y1 = max(0.0, x0 - 0.02), max(0.0, y0 - 0.02), min(1.0, x1 + 0.02), min(1.0, y1 + 0.02)
        if x1 - x0 < 0.04 or y1 - y0 < 0.04:
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            x0, x1 = max(0.0, cx - 0.02), min(1.0, cx + 0.02)
            y0, y1 = max(0.0, cy - 0.02), min(1.0, cy + 0.02)
        return round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)
    for name in sorted(REGIONS, key=len, reverse=True):       # "top-right" before "top"
        if name in v.replace(" ", "-") or name.replace("-", " ") in v:
            return REGIONS[name]
    if "corner" in v or "logo" in v or "watermark" in v:
        return REGIONS["top-right"]
    if re.search(r"\b(whole|all|everything)\b", v):
        return REGIONS["full"]
    return None


def compile_ops(ops, length, base_words, base=None):
    """Every operation of the chain folded into one render spec (base seconds)."""
    base = base or {}
    keep = [(0.0, float(length))]
    spec = {"speed": 1.0, "speeds": [], "zooms": [], "texts": [], "brolls": [], "look": {}, "music": None,
            "volume": {"music": 0.0, "voice": 0.0, "all": 0.0}, "captions": bool(base.get("captions")),
            "style": {}, "fixes": [], "language": None, "reframe": None, "tighten": None,
            "bleeps": [], "blurs": [], "sfx": [], "stickers": [], "clean": None, "fade": None}
    for o in ops:
        k = o["op"]
        if k == "cut":
            for a, b in o["ranges"]:
                keep = _subtract(keep, a, b)
        elif k == "keep":
            keep = _intersect(keep, o["ranges"])
        elif k == "tighten":
            spec["tighten"] = o["amount"]
        elif k == "speed":
            if o.get("ranges"):
                spec["speeds"] += [(a, b, o["amount"]) for a, b in o["ranges"]]
            else:
                spec["speed"] = o["amount"]
        elif k == "bleep":
            spec["bleeps"] += [(a, b, o.get("value") or "beep") for a, b in o["ranges"]]
        elif k == "blur":
            if o.get("value") == "off":
                spec["blurs"] = []
            else:
                spec["blurs"] += [{"range": r, "box": o["box"], "mode": o.get("text") or "blur"}
                                  for r in o["ranges"]]
        elif k == "sfx":
            spec["sfx"] += [(a, o["value"], o.get("amount", 0.0)) for a, _b in o["ranges"]]
        elif k == "sticker":
            spec["stickers"] += [(a, b, o["value"], o.get("text") or "top-right") for a, b in o["ranges"]]
        elif k == "clean_audio":
            spec["clean"] = None if o.get("value") == "off" else o["amount"]
        elif k == "fade":
            spec["fade"] = None if o.get("value") == "off" else (o["value"], o["amount"])
        elif k == "zoom":
            spec["zooms"] += [(a, b, o["amount"]) for a, b in o["ranges"]]
        elif k == "text":
            spec["texts"] += [(a, b, o["text"], o["value"], o.get("style") or {}) for a, b in o["ranges"]]
        elif k == "broll":
            spec["brolls"] += [{"range": r, "text": o["text"], "file": o.get("file")} for r in o["ranges"]]
        elif k == "look":
            if o["value"] == "normal":
                spec["look"] = {}
            else:
                spec["look"].pop(OPPOSITE.get(o["value"], ""), None)
                spec["look"][o["value"]] = o["amount"]
        elif k == "music":
            spec["music"] = {"value": o["value"], "amount": o.get("amount", 0.0), "file": o.get("file")}
        elif k == "volume":
            spec["volume"][o["value"]] = _clamp(spec["volume"][o["value"]] + o["amount"], -25, 15)
        elif k == "captions":
            spec["captions"] = o["value"].lower() not in ("off", "no", "none", "hide")
        elif k == "caption_style":
            spec["style"] = _style(o["value"], spec["style"])
            spec["captions"] = True
        elif k == "caption_fix":
            spec["fixes"].append(o["text"])
        elif k == "translate_captions":
            spec["language"] = o["value"]
            spec["captions"] = True
        elif k == "reframe":
            spec["reframe"] = o["value"].lower()
    if spec["tighten"] is not None:
        for w0, w1 in zip(base_words, base_words[1:]):
            a, b = float(w0["end"]), float(w1["start"])
            if b - a > spec["tighten"]:
                keep = _subtract(keep, a + spec["tighten"] / 2, b - spec["tighten"] / 2)
    spec["keep"] = keep
    return spec


def timeline(spec):
    """The Timeline of a compiled spec: its kept stretches, the whole video's speed, each stretch's own."""
    return Timeline(spec["keep"], spec["speed"], spec.get("speeds") or ())


# ---------------------------------------------------------------- music, footage, captions

def _mood_track(value, ctx, client, log=print):
    """A bed for a mood: the channel's own beds for "different", else one made for the mood (Lyria, ~15 s,
    $0.04, kept in music/mood_<words>/ for next time)."""
    import music_beds
    import short_kit as kit
    v = value.lower().strip()
    if v in ("different", "another", "other", "new", "change"):
        kind = ctx["kind"] if ctx["kind"] in music_beds.PROMPTS else "quiz"
        music_beds.ensure(kind, 2, client)
        return kit.music_track(kind)
    slug = re.sub(r"[^a-z0-9]+", "_", v).strip("_")[:40] or "calm"
    kind = f"mood_{slug}"
    if not music_beds.beds(kind):
        log(f"🎵 Making {value} music...")
        music_beds.make(kind, client, prompt=f"{value} background music for a short video, warm and polished, "
                                             f"steady energy")
    return kit.music_track(kind)


def _broll_clip(path, ctx, query, seconds, size, name, client, log=print):
    """A stock footage shot of ``seconds`` at ``size`` for ``query`` (stock_media + broll), or None."""
    import broll
    import stock_media
    if not stock_media.available():
        return None
    items = stock_media.for_scenes(client, ctx["topic"] or query, [query], [query], portrait=size[1] > size[0],
                                   photos=True, log=log)
    if not items or not items[0]:
        return None
    shots = broll.plan_shots([(0.0, seconds + 0.5, query)], items)
    return broll.build(path, shots, out_name=f"{edits_name(ctx.get('index') or 0)}/{name}", size=size)


def _translated(state, path, client, language, segments):
    """Base segment texts in ``language`` (cached per language in the chain's state)."""
    import short_kit as kit
    cache = state.setdefault("translations", {}).setdefault(language.lower(), {})
    todo = [k for k, s in enumerate(segments) if str(k) not in cache and (s.get("text") or "").strip()]
    for i in range(0, len(todo), 40):
        part = todo[i:i + 40]
        got = kit.ask_json(client, Lines, TRANSLATE_PROMPT.format(
            language=language, n=len(part), lines="\n".join(f"{n + 1}. {segments[k]['text'].strip()}"
                                                            for n, k in enumerate(part))))
        if len(got.lines) == len(part):
            for k, text in zip(part, got.lines):
                cache[str(k)] = re.sub(r"^\s*\d+[.)]\s*", "", text).strip()
    save(path, state)
    return {int(k): v for k, v in cache.items()}


def caption_transcript(state, spec, tl, path=None, client=None):
    """The base transcript with the caption fixes and translation applied, moved onto the output timeline."""
    base_tr = state["base"]["meta"]["transcript"] or {}
    segments = [dict(s) for s in base_tr.get("segments") or []]
    texts = None
    if spec["language"]:
        texts = _translated(state, path, client, spec["language"], segments)
    out = []
    for k, seg in enumerate(segments):
        words = [dict(w) for w in seg.get("words") or [] if (w.get("word") or "").strip()]
        if not words:
            continue
        text = texts.get(k) if texts else None
        if text:
            words = studio._respread({"words": words, "start": seg.get("start"), "end": seg.get("end")}, text)
        for fix in spec["fixes"]:
            wrong, _, right = fix.partition("=>")
            pat = re.compile(r"(?<![\w])" + re.escape(wrong.strip()) + r"(?![\w])", re.IGNORECASE)
            joined = " ".join(w["word"].strip() for w in words)
            fixed = pat.sub(right.strip(), joined)
            if fixed != joined:
                words = studio._respread({"words": words}, fixed)
        kept = []
        for w in words:
            a, b = tl.out(float(w["start"])), tl.out(float(w["end"]))
            if a is not None and b is not None and b >= a:
                kept.append({"word": " " + w["word"].strip(), "start": round(a, 3), "end": round(b, 3)})
        if kept:
            out.append({"start": kept[0]["start"], "end": kept[-1]["end"],
                        "text": " ".join(w["word"].strip() for w in kept), "words": kept})
    return {**{k: v for k, v in base_tr.items() if k != "segments"}, "segments": out}


# ---------------------------------------------------------------- rendering

def _atempo(f):
    """The atempo chain (with a trailing comma) for ``f``x, or "" at normal speed. One atempo takes
    0.5-100, so slower than half speed is two in a row."""
    if abs(f - 1.0) < 0.005:
        return ""
    if f < 0.5:
        return f"atempo=0.5,atempo={f / 0.5:.4f},"
    return f"atempo={f:.4f},"


def _between(ranges):
    """An ffmpeg expression that is 1 inside any (a, b) of ``ranges`` (output seconds), else 0."""
    return "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in ranges) or "0"


def _zoom_expr(zooms):
    terms = []
    for t0, t1, f in zooms:
        r = max(0.08, min(0.35, (t1 - t0) / 3))
        x = f"clip(min((t-{t0:.3f})/{r:.3f},({t1:.3f}-t)/{r:.3f}),0,1)"
        terms.append(f"{f - 1:.3f}*between(t,{t0:.3f},{t1:.3f})*(0.5-0.5*cos(PI*{x}))")
    return "1+" + "+".join(terms)


def _look_filters(look):
    out = []
    for value, s in look.items():
        if value == "darker":
            out.append(f"eq=brightness={-0.16 * s:.3f}:contrast={1 + 0.04 * s:.3f}")
        elif value == "brighter":
            out.append(f"eq=brightness={0.12 * s:.3f}")
        elif value == "contrast":
            out.append(f"eq=contrast={1 + 0.35 * s:.3f}")
        elif value == "vivid":
            out.append(f"eq=saturation={1 + 0.6 * s:.3f}")
        elif value == "warm":
            out.append(f"colorbalance=rs={0.12 * s:.3f}:gs={0.03 * s:.3f}:bs={-0.12 * s:.3f}:rm={0.08 * s:.3f}"
                       f":bm={-0.08 * s:.3f}")
        elif value == "cool":
            out.append(f"colorbalance=rs={-0.10 * s:.3f}:bs={0.12 * s:.3f}:rm={-0.06 * s:.3f}:bm={0.08 * s:.3f}")
        elif value == "black and white":
            out.append("hue=s=0")
        elif value == "cinematic":
            out.append(f"eq=contrast={1 + 0.15 * s:.3f}:saturation={1 - 0.12 * s:.3f},"
                       f"colorbalance=rs={0.05 * s:.3f}:bs={-0.04 * s:.3f}:rh={0.05 * s:.3f}:bh={-0.05 * s:.3f}"
                       f":rl={-0.04 * s:.3f}:bl={0.05 * s:.3f},vignette=PI/6")
    return out


def _wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return r"\N".join(lines[:4])


def _text_ass(texts, size, path):
    """An ASS file with the owner's on-screen words: bold, outlined, popping in and out."""
    w, h = size
    vertical = h > w
    px = round(h * (0.042 if vertical else 0.07))
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 2", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
             "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
             "Alignment, MarginL, MarginR, MarginV, Encoding",
             f"Style: Edit,Montserrat ExtraBold,{px},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,"
             f"0,1,{max(4, px // 12)},2,8,40,40,40,1",
             f"Style: EditUrdu,Noto Nastaliq Urdu,{px},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,"
             f"0,1,{max(4, px // 12)},2,8,40,40,40,1", "",
             "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    ys = {"top": (8, round(h * (0.2 if vertical else 0.08))), "middle": (5, round(h * 0.5)),
          "bottom": (2, round(h * (0.64 if vertical else 0.86)))}

    def ts(t):
        t = max(0.0, t)
        return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"
    for t0, t1, text, pos, *rest in texts:
        look = rest[0] if rest else {}
        an, y = ys.get(pos, ys["top"])
        clean = text.replace("\\", "/").replace("{", "(").replace("}", ")")
        style = "EditUrdu" if URDU_LETTERS.search(clean) else "Edit"
        size = float(look.get("size") or 1.0)
        body = _wrap(clean, max(8, round((20 if vertical else 36) / size)))
        colour = ""
        hexc = str(look.get("color") or "")
        if re.fullmatch(r"#[0-9A-Fa-f]{6}", hexc):
            colour = r"\1c&H" + (hexc[5:7] + hexc[3:5] + hexc[1:3]).upper() + "&"     # ASS is BGR
        scale = round(100 * size)
        lines.append(f"Dialogue: 0,{ts(t0)},{ts(t1)},{style},,0,0,0,,"
                     + r"{\an" + str(an) + r"\pos(" + f"{w // 2},{y}" + r")\fad(120,160)" + colour
                     + rf"\fscx{round(scale * 0.85)}\fscy{round(scale * 0.85)}"
                     + rf"\t(0,140,\fscx{round(scale * 1.04)}\fscy{round(scale * 1.04)})"
                     + rf"\t(140,240,\fscx{scale}\fscy{scale})}}" + body)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return path


def _target_size(spec, base):
    w, h = base["w"], base["h"]
    shape = (spec.get("reframe") or "").lower()
    if shape.startswith("vert"):
        return (1080, 1920) if (w, h) != (1080, 1920) else (w, h)
    if shape.startswith("squ"):
        return (1080, 1080)
    if shape.startswith("hor") or shape.startswith("land"):
        return (1920, 1080)
    return (w + w % 2, h + h % 2)


def render(path, state, spec, ctx, out, client=None, log=print, captions=None):
    """The edited video: base clean cut, cuts with fades, speed, shape, zooms, look, footage and on-screen
    text, the sound with new music under the voices, and ``captions`` (an .ass file, caption_ass) drawn
    last in the same pass. One encode: the burn used to be a second one at preset medium, about half of
    every edit's time, and a second generation on the picture. Returns ``out``."""
    import short_kit as kit
    from ffmpeg_utils import escape_filter_value
    import framed_layout as fl
    from ffmpeg_utils import INTERMEDIATE, video_encode_args
    base = state["base"]
    src = os.path.join(path, base["video"])
    tl = timeline(spec)
    D = tl.duration
    W, H = _target_size(spec, base)
    fps = base["fps"]
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", src]
    idx = 1
    replace = spec["music"] is not None and base.get("stem") and os.path.isfile(os.path.join(path, base["stem"]))
    if replace:
        cmd += ["-i", os.path.join(path, base["stem"])]
        asrc, idx = f"{idx}:a", idx + 1
    elif base.get("audio"):
        asrc = "0:a"
    else:
        cmd += ["-f", "lavfi", "-t", f"{base['seconds']:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        asrc, idx = f"{idx}:a", idx + 1
    graph = []
    pieces = tl.pieces
    whole = (len(pieces) == 1 and pieces[0][0] < 0.02 and pieces[0][1] > base["seconds"] - 0.02
             and abs(pieces[0][2] - 1.0) < 0.01)
    if whole:
        graph.append(f"[0:v]null[vc]")
        graph.append(f"[{asrc}]aresample=48000,aformat=channel_layouts=stereo[ac]")
    else:
        # Each kept piece at its own speed (setpts / atempo), joined: a cut, a whole-video speed and a
        # stretch in slow motion are all the same thing here. A fade at every join that is a real cut.
        for k, (a, b, f) in enumerate(pieces):
            length = (b - a) / f
            cut_before = k == 0 or abs(pieces[k - 1][1] - a) > 1e-6
            cut_after = k + 1 == len(pieces) or abs(pieces[k + 1][0] - b) > 1e-6
            fades = ((f"afade=t=in:d={FADE}," if cut_before else "")
                     + (f"afade=t=out:st={max(0.0, length - FADE):.3f}:d={FADE}," if cut_after else ""))
            graph.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=(PTS-STARTPTS)/{f:.4f}[v{k}]")
            graph.append(f"[{asrc}]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,{_atempo(f)}"
                         f"aresample=48000,aformat=channel_layouts=stereo,{fades}anull[a{k}]")
        graph.append("".join(f"[v{k}][a{k}]" for k in range(len(pieces)))
                     + f"concat=n={len(pieces)}:v=1:a=1[vc][ac]")
    v, a = "[vc]", "[ac]"
    if (W, H) != (base["w"], base["h"]):
        graph.append(f"{v}split=2[r1][r2];[r1]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                     f"gblur=sigma=30,eq=brightness=-0.08[rb];[r2]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                     f"setsar=1[rf];[rb][rf]overlay=(W-w)/2:(H-h)/2[vr]")
        v = "[vr]"
    zooms = [(o0, o1, f) for b0, b1, f in spec["zooms"] for o0, o1 in tl.out_ranges(b0, b1)]
    if zooms:
        graph.append(f"{v}scale=w='trunc(iw*({_zoom_expr(zooms)})/2)*2':h=-2:eval=frame,crop={W}:{H},setsar=1[vz]")
        v = "[vz]"
    looks = _look_filters(spec["look"])
    if looks:
        graph.append(f"{v}{','.join(looks)}[vl]")
        v = "[vl]"
    # Blur / pixelate a region (a logo, a watermark, a face) of the picture as it is now, before any
    # footage covers it: the stock clips are ours and stay sharp.
    for k, bl in enumerate(spec.get("blurs") or []):
        ranges = tl.out_ranges(*bl["range"])
        if not ranges:
            continue
        x0, y0, x1, y1 = bl["box"]
        bx, by = int(x0 * W) // 2 * 2, int(y0 * H) // 2 * 2
        bw, bh = max(8, int((x1 - x0) * W) // 2 * 2), max(8, int((y1 - y0) * H) // 2 * 2)
        bw, bh = min(bw, W - bx), min(bh, H - by)
        if bl.get("mode") == "pixelate":
            soften = (f"scale=max(2\\,iw/{max(4, bw // 24)}):max(2\\,ih/{max(4, bw // 24)}):flags=area,"
                      f"scale={bw}:{bh}:flags=neighbor")
        else:
            radius = max(4, min(bw, bh) // 6)
            soften = f"boxblur=luma_radius={radius}:luma_power=3:chroma_radius={max(2, radius // 2)}:chroma_power=2"
        graph.append(f"{v}split=2[bm{k}][bs{k}];[bs{k}]crop={bw}:{bh}:{bx}:{by},{soften}[bb{k}];"
                     f"[bm{k}][bb{k}]overlay={bx}:{by}:enable='{_between(ranges)}'[vbl{k}]")
        v = f"[vbl{k}]"
    j = 0
    for k, br in enumerate(spec["brolls"]):
        clip = br.get("file") and os.path.join(path, br["file"])
        if not clip or not os.path.isfile(clip):
            continue
        # Every stretch the footage covers (one stretch can come out in pieces when cut in between):
        # the clip plays on from where the last piece left it.
        played = 0.0
        for o0, o1 in tl.out_ranges(*br["range"]):
            cmd += ["-ss", f"{played:.3f}", "-i", clip]
            graph.append(f"[{idx}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
                         f"fps={fps},setpts=PTS-STARTPTS,tpad=start_duration={o0:.3f}:start_mode=clone:"
                         f"stop_mode=clone:stop_duration={max(1.0, D - o0 + 1):.3f}[bk{j}]")
            graph.append(f"{v}[bk{j}]overlay=0:0:enable='between(t,{o0:.3f},{o1:.3f})'[vb{j}]")
            v, idx, j = f"[vb{j}]", idx + 1, j + 1
            played += o1 - o0
    texts = [(o0, o1, text, pos, style) for b0, b1, text, pos, *rest in spec["texts"]
             for style in [rest[0] if rest else {}] for o0, o1 in tl.out_ranges(b0, b1)]
    if texts:
        ass = _text_ass(texts, (W, H), os.path.join(os.path.dirname(out), "text.ass"))
        graph.append(f"{v}ass=filename='{escape_filter_value(ass)}':fontsdir='{escape_filter_value(fl.FONTS_DIR)}'[vt]")
        v = "[vt]"
    if spec.get("stickers"):
        import stickers
        size = round(min(W, H) * 0.2)
        for k, (b0, b1, name, spot) in enumerate(spec["stickers"]):
            file = stickers.path(name)
            got = tl.out_ranges(b0, b1)
            if not file or not got:
                continue
            fx, fy = STICKER_SPOTS.get(spot, STICKER_SPOTS["top-right"])
            # alive_until: the input runs to the end (an input ending early stalled ffmpeg over footage).
            inputs, filters, v = stickers.overlay_args(file, idx, got[0][0], got[-1][1], fx * W, fy * H, size=size,
                                                       src=v, label=f"est{k}", alive_until=D, fps=round(fps))
            cmd += inputs
            graph += filters
            idx += 1
    if captions:
        graph.append(f"{v}ass=filename='{escape_filter_value(captions)}':fontsdir='{escape_filter_value(fl.FONTS_DIR)}'[vcap]")
        v = "[vcap]"
    fade = spec.get("fade")
    if fade:
        kind, secs = fade
        secs = min(secs, D / 3)
        parts = ([f"fade=t=in:st=0:d={secs:.3f}"] if kind in ("in", "both") else []) \
            + ([f"fade=t=out:st={max(0.0, D - secs):.3f}:d={secs:.3f}"] if kind in ("out", "both") else [])
        if parts:
            graph.append(f"{v}{','.join(parts)}[vfd]")
            v = "[vfd]"
    graph.append(f"{v}{kit.TO_BT709}[vout]")
    vol = spec["volume"]
    if spec.get("clean") and base.get("audio"):
        # Speech cleanup: rumble and hum under 80 Hz out, FFT denoise that learns the noise as it goes
        # (afftdn tn=1), a gentle compressor to even the level; kit.level sets the loudness after.
        s = float(spec["clean"])
        graph.append(f"{a}highpass=f=80,afftdn=nr={8 + 16 * s:.1f}:nf=-40:tn=1,"
                     f"acompressor=threshold=-22dB:ratio={1.5 + 2 * s:.2f}:attack=8:release=180:makeup=2[acl]")
        a = "[acl]"
    bleeps = [(o0, o1, how) for b0, b1, how in spec.get("bleeps") or [] for o0, o1 in tl.out_ranges(b0, b1)]
    if bleeps:
        hide = _between([(o0, o1) for o0, o1, _ in bleeps])
        graph.append(f"{a}volume=0:enable='{hide}'[amu]")
        a = "[amu]"
        beeps = [(o0, o1) for o0, o1, how in bleeps if how != "mute"]
        if beeps:
            # sine= is made at amplitude 1/8: x2.4 = 0.3 (-13.5 dBFS RMS), as loud as the speech it hides
            # (0.22 without the x8 came out 13 dB under it, measured).
            graph.append(f"sine=frequency=1000:sample_rate=48000:duration={D:.3f},"
                         f"volume='2.4*({_between(beeps)})':eval=frame,aformat=channel_layouts=stereo[beep]")
            graph.append(f"{a}[beep]amix=inputs=2:duration=first:normalize=0[abp]")
            a = "[abp]"
    if vol["voice"]:
        graph.append(f"{a}volume={vol['voice']:.1f}dB[avv]")
        a = "[avv]"
    music = spec["music"]
    track = music and music.get("file") and os.path.join(ROOT, music["file"]) if music else None
    if music and music["value"].lower() not in ("off", "none", "no music") and track and os.path.isfile(track):
        cmd += ["-stream_loop", "-1", "-i", track]
        bed_db = (music.get("amount") or 0.0) + vol["music"]
        graph.append(f"[{idx}:a]atrim=0:{D:.3f},asetpts=PTS-STARTPTS,{kit.BED_DUCKED_LOUDNORM},volume={bed_db:.1f}dB,"
                     f"afade=t=in:d=1,afade=t=out:st={max(0.0, D - 1.5):.3f}:d=1.5,aresample=48000,"
                     f"aformat=channel_layouts=stereo[bed]")
        graph.append(f"{a}asplit=2[vx][vkey]")
        graph.append(f"[bed][vkey]{kit.DUCK}[bedd]")
        graph.append(f"[vx][bedd]amix=inputs=2:duration=first:normalize=0,{kit.LIMIT}[am]")
        a, idx = "[am]", idx + 1
    sfx = [(o, kind, db) for b0, kind, db in spec.get("sfx") or [] for o in [tl.out(b0)] if o is not None]
    if sfx:
        files = kit.whoosh_files()
        labels = []
        for k, (at, kind, db) in enumerate(sfx):
            ms = int(at * 1000)
            gain = kit.SFX_DB + float(db or 0.0)
            if kind == "whoosh" and files:
                cmd += ["-i", files[k % len(files)]]
                graph.append(f"[{idx}:a]volume={gain:.1f}dB,aresample=48000,aformat=channel_layouts=stereo,"
                             f"adelay={ms}|{ms}[fx{k}]")
                idx += 1
            else:
                expr, secs = SFX_EXPR.get(kind, (kit.WHOOSH, 0.3))
                graph.append(f"aevalsrc='{expr}':s=48000:d={secs:g},aformat=channel_layouts=stereo,"
                             f"volume={gain + 6:.1f}dB,adelay={ms}|{ms}[fx{k}]")
            labels.append(f"[fx{k}]")
        graph.append(f"{a}{''.join(labels)}amix=inputs={1 + len(labels)}:duration=first:normalize=0,{kit.LIMIT}[asx]")
        a = "[asx]"
    if vol["all"]:
        graph.append(f"{a}volume={vol['all']:.1f}dB[aall]")
        a = "[aall]"
    if fade:
        kind, secs = fade
        secs = min(secs, D / 3)
        parts = ([f"afade=t=in:st=0:d={secs:.3f}"] if kind in ("in", "both") else []) \
            + ([f"afade=t=out:st={max(0.0, D - secs):.3f}:d={secs:.3f}"] if kind in ("out", "both") else [])
        if parts:
            graph.append(f"{a}{','.join(parts)}[afd]")
            a = "[afd]"
    graph.append(f"{a}anull[aout]")
    # The shared encoder (ffmpeg_utils): Intel Quick Sync where FFMPEG_ENCODER=qsv, else x264 veryfast
    # CRF 16 (was a fixed veryfast CRF 17). An edit is rendered once from the clean cut, so it keeps quality.
    r = subprocess.run(cmd + ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]",
                              "-t", f"{D:.3f}", "-r", f"{fps:g}", *video_encode_args(INTERMEDIATE),
                              "-pix_fmt", "yuv420p", *kit.BT709_TAGS, "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                              "-movflags", "+faststart", out],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace",
                       timeout=max(900, int(D * 15)))
    if r.returncode != 0 or not os.path.isfile(out):
        raise EditError("The video could not be made: " + (r.stderr.strip().splitlines() or ["ffmpeg failed"])[-1][-300:])
    if base.get("audio") or music:
        kit.level(out)
    return out


def burn(path, ctx, state, spec, transcript, src, out):
    """Our captions on an already edited video (a second encode; apply draws them inside render)."""
    import subtitles
    ass = caption_ass(path, ctx, state, spec, transcript, _probe(src)["seconds"] or 1e9,
                      os.path.join(os.path.dirname(out), "captions.ass"))
    if not ass:
        return None
    subtitles.burn_subtitles(src, ass, out)
    return out


def caption_ass(path, ctx, state, spec, transcript, seconds, ass):
    """Our captions as an .ass file for the edited video's size, in the job's own look with the owner's
    style changes, or None when there is nothing to show."""
    import subtitles
    st = dict(subtitles.AUTO_CAPTION_STYLE)
    style = spec["style"]
    st["font_size"] = round(st["font_size"] * float(style.get("size") or 1.0))
    if style.get("color"):
        st["font_color"] = style["color"]
        if style["color"].upper() == str(st["highlight_color"]).upper():
            st["highlight_color"] = "#FFFFFF"
    if style.get("highlight"):
        st["highlight_color"] = style["highlight"]
    if style.get("case"):
        st["uppercase"] = style["case"] == "upper"
    w, h = _target_size(spec, state["base"])
    vertical = h > w
    position = style.get("position")
    if position:
        placement = {"alignment": "top", "margin_v": round({"top": 0.2, "middle": 0.46, "bottom": 0.64}[position] * 288)}
    elif ctx["framed"] and (w, h) == (state["base"]["w"], state["base"]["h"]):
        import framed_layout
        margin = framed_layout.job_caption_margin(path)
        placement = {"alignment": "top", "margin_v": margin} if margin is not None else {"alignment": "bottom"}
    else:
        # Clear of YouTube's own title and buttons at the bottom of a vertical video.
        placement = {"alignment": "top", "margin_v": round(0.62 * 288)} if vertical else {"alignment": "bottom"}
    if ctx["genre"] not in ("comedy", UPLOAD_GENRE):
        os.environ.setdefault("CAPTION_EMPHASIS", "1")
    if not subtitles.generate_ass(transcript, 0.0, seconds, ass,
                                  max_chars=st["max_chars"], max_duration=st["max_duration"], fontsize=st["font_size"],
                                  font_name=st["font_name"], font_color=st["font_color"],
                                  border_color=st["border_color"], border_width=st["border_width"],
                                  highlight_color=st["highlight_color"], effect=st["effect"],
                                  base_opacity=st["base_opacity"], uppercase=st["uppercase"], **placement):
        return None
    return ass


# ---------------------------------------------------------------- checking the result

def _changed_times(spec, tl, D):
    """Up to four output times where the edit shows (zooms, text, footage), else spread over the video."""
    marks = []
    for b0, b1, *_ in (spec["zooms"] + [(t[0], t[1]) for t in spec["texts"]]
                       + [(s[0], s[1]) for s in spec.get("stickers") or []]):
        for o0, o1 in tl.out_ranges(b0, b1):
            marks.append((o0 + o1) / 2)
    for br in spec["brolls"] + list(spec.get("blurs") or []):
        for o0, o1 in tl.out_ranges(*br["range"]):
            marks.append((o0 + o1) / 2)
    if len(marks) < 4:
        marks += [D * f for f in (0.12, 0.38, 0.62, 0.86)][:4 - len(marks)]
    return sorted(set(round(min(max(0.2, m), max(0.2, D - 0.3)), 2) for m in marks))[:4]


def _sheet(before, after, times_before, times_after):
    import io
    from PIL import Image
    import creative_qa
    cells = []
    for video, times in ((before, times_before), (after, times_after)):
        row = []
        for t in times:
            try:
                row.append(creative_qa._frame(video, t, 270))
            except Exception:  # noqa: BLE001 — a missing frame is a gap in the sheet
                row.append(None)
        cells.append(row)
    sample = next((c for row in cells for c in row if c is not None), None)
    if sample is None:
        return None
    cw, ch = sample.size
    sheet = Image.new("RGB", (len(times_after) * (cw + 6) + 6, 2 * (ch + 6) + 6), (255, 255, 255))
    for r, row in enumerate(cells):
        for c, im in enumerate(row):
            if im is not None:
                sheet.paste(im.resize((cw, ch)), (6 + c * (cw + 6), 6 + r * (ch + 6)))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=86)
    return buf.getvalue()


def check(client, request, summary, before, after, spec, tl, base_tl):
    """(done, problems) from one look at before/after frames, or (None, []) when nothing visible changed
    or the look could not run."""
    import script_craft
    import short_kit as kit
    from google.genai import types
    visible = (spec["zooms"] or spec["texts"] or spec["brolls"] or spec["look"] or spec["reframe"]
               or spec["style"] or spec["language"] or spec["fixes"] or spec.get("blurs") or spec.get("stickers"))
    if not visible:
        return None, []
    D = tl.duration
    after_times = _changed_times(spec, tl, D)
    before_times = [base_tl.out(tl.base(t)) or tl.base(t) for t in after_times]
    try:
        jpeg = _sheet(before, after, before_times, after_times)
        if not jpeg:
            return None, []
        got = kit.ask_json(client, Check, [types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                                           CHECK_PROMPT.format(request=request, summary=summary)],
                           model=os.environ.get("AI_EDIT_MODEL") or script_craft.writer_model())
        return bool(got.done), [p for p in got.problems if p.strip()][:5]
    except Exception:  # noqa: BLE001 — the check is extra; the edit stands
        return None, []


# ---------------------------------------------------------------- one request, start to end

def _publish(path, state, n):
    """Make revision ``n`` (0 = the original) the file Studio plays and the upload sends."""
    for p in state.get("published") or []:
        try:
            os.remove(os.path.join(path, p["name"]))
        except OSError:
            pass
    state["published"] = []
    index = state["base"].get("clip") or 0
    if n:
        final = os.path.join(path, state["revisions"][n - 1]["final"])
        name = f"subtitled_{_now()}_ai{n}_{studio._base(path)}_clip_{index + 1}.mp4"
        shutil.copyfile(final, os.path.join(path, name))
        state["published"] = [{"n": n, "name": name}]
    else:
        # The base file is newest again once the edited copies are gone; touch it to be sure.
        base = os.path.join(path, state["base"]["served"])
        if os.path.isfile(base):
            os.utime(base, None)
    meta = state["revisions"][n - 1]["meta"] if n else state["base"]["meta"]
    data = studio._read(path)
    shared = state["base"].get("shared")
    if not shared:
        data["transcript"] = meta["transcript"]
    short = studio.clip_of(data, index)
    for k, v in meta["short"].items():
        if shared and k in ("start", "end"):
            continue        # the clip's place in the source show stays as it was cut
        if v is None:
            short.pop(k, None)
        else:
            short[k] = v
    studio._write(path, data)
    state["current"] = n
    save(path, state)


def restore(job_id, n):
    """Go back to revision ``n`` (0 = the video before any AI edit)."""
    path = studio.job_dir(job_id)
    state = load(path, studio.split_ref(job_id)[1])
    if not state:
        raise EditError("This video has no AI edits.")
    n = int(n)
    if not 0 <= n <= len(state["revisions"]):
        raise EditError("No such version.")
    if not os.path.isfile(os.path.join(path, state["revisions"][n - 1]["final"])) if n else False:
        raise EditError("That version's file is gone.")
    _publish(path, state, n)
    return status(job_id)


def _undo(job_id, state, p, op, ctx=None):
    """'undo' / 'wapas karo' typed into the box: the version before the latest edit, or the original with
    value 'all'. The later revisions stay (Studio's version list can redo them)."""
    cur = state.get("current") or 0
    if not cur:
        return {"ok": False, "message": "There is no AI edit to undo yet.", "summary": p.summary, "notes": []}
    target = 0 if (op.value or "").strip().lower() in ("all", "everything", "original") else cur - 1
    st = restore(job_id, target)
    said = "Back to the video before any AI edit." if target == 0 else f"Back to version {target}."
    return {"ok": True, "n": target, "summary": p.summary or said, "assumptions": [], "why_not": "",
            "notes": [said], "check": {"done": None, "problems": []}, "undone": True,
            "seconds": round(float((st.get("revisions") or [{}])[target - 1].get("seconds") or 0) if target
                             else float((state.get("base") or {}).get("seconds") or 0), 2),
            "details": [], "remake": None, "file_changed": not (ctx or {}).get("on_youtube"),
            # On YouTube only the details ever changed: the restored ones go back up.
            "push": bool((ctx or {}).get("on_youtube"))}


def _details(client, ctx, meta, details, transcript, log=print):
    """Title, description and tags changes into the metadata snapshot. Returns what changed, in words."""
    import script_craft
    short = meta["short"]
    said = []
    if "title" in details:
        d = details["title"]
        if d["text"] and d["value"] != "better":
            short["seo_title"] = re.sub(r"\s+", " ", d["text"])[:studio.TITLE_MAX]
            said.append("title")
        else:
            facts = " ".join(s.get("text") or "" for s in (transcript or {}).get("segments") or [])
            facts += "\n" + (short.get("seo_description") or "")
            old = short.get("seo_title") or ""
            os.environ.setdefault("POLISH", "1")
            new = script_craft.pick_title(client, old, facts[:6000], log=log)
            if new and new != old:
                short["seo_title"] = new[:studio.TITLE_MAX]
                said.append("title")
    if "description" in details and details["description"]["text"]:
        # The credits of the old description stay (licences require them), whatever the new text says.
        text = studio.keep_credits(short.get("seo_description"), details["description"]["text"])
        if len(text.encode("utf-8")) <= studio.DESCRIPTION_MAX:
            short["seo_description"] = text.strip()
            said.append("description")
    if "tags" in details and details["tags"]["text"]:
        short["seo_tags"] = [t.strip().lstrip("#") for t in re.split(r"[,\n]", details["tags"]["text"]) if t.strip()][:40]
        said.append("tags")
    return said


def apply(job_id, request, client=None, log=print):
    """Do what the owner asked. Returns a result for the Studio (and for the server's follow-up actions)."""
    import short_kit as kit
    ctx = context(job_id)
    path, ix = ctx["path"], ctx["index"]
    stage(path, "Reading the video", ix)
    state = ensure_base(path, ix)
    base = state["base"]
    base_words = _words(base["meta"]["transcript"])
    ops_now = _current_ops(state)
    spec_now = compile_ops(ops_now, base["seconds"], base_words, base)
    tl_now = timeline(spec_now)
    words = words_now(base_words, tl_now)
    client = client or kit.gemini()
    served = studio.served(path, ix)
    watch = proxy(path, served, ix) if tl_now.duration <= PLAN_VIDEO_SECONDS and os.path.isfile(served) else None
    note, problems, last = "", [], None
    for attempt in range(MAX_PASSES):
        stage(path, "Understanding what to change" if not attempt else "Fixing what the check found", ix)
        try:
            p = plan(client, request, edit_sheet(ctx, state, tl_now, words), ctx, video=watch, note=note)
        except Exception as e:  # noqa: BLE001 — a failed fix-up keeps the first pass, which is already made
            if last is None:
                raise
            log(f"   ℹ️ the second plan failed ({type(e).__name__}); keeping the first version")
            last["problems"] = list(last["problems"]) + ["A second try could not be planned; this is the first one."]
            break
        undo = [o for o in p.ops if (o.op or "").strip().lower() == "undo"]
        if undo:
            return _undo(job_id, state, p, undo[0], ctx)
        ops, details, remake, notes = resolve(p, ctx, state, tl_now, words)
        if not ops and not details and not remake:
            question = p.question.strip()
            msg = question or p.why_not.strip() or (notes[0] if notes else "") \
                or "I could not find anything to change for that. Try saying it another way."
            return {"ok": False, "question": bool(question), "message": msg, "summary": p.summary,
                    "notes": notes + ([p.why_not] if p.why_not and p.why_not != msg else [])}
        all_ops = ops_now + ops
        spec = compile_ops(all_ops, base["seconds"], base_words, base)
        tl = timeline(spec)
        if tl.duration < MIN_SECONDS:
            return {"ok": False, "message": f"That would leave {tl.duration:.1f} s; a video needs at least "
                                            f"{MIN_SECONDS:.0f} s.", "summary": p.summary, "notes": notes}
        n = len(state["revisions"][:state.get("current") or 0]) + 1
        rdir = os.path.join(_edits(path, ix), f"r{n}")
        shutil.rmtree(rdir, ignore_errors=True)
        os.makedirs(rdir)
        meta = json.loads(json.dumps(_current_meta(state)))
        file_changes = any(o["op"] in FILE_OPS for o in ops)
        final = None
        if file_changes:
            # Assets first: music for a mood, footage for a stretch.
            for o in ops:
                if o["op"] == "music" and o["value"].lower() not in ("off", "none", "no music"):
                    stage(path, f"Finding {o['value']} music", ix)
                    try:
                        track = _mood_track(o["value"], ctx, client, log)
                    except Exception as e:  # noqa: BLE001
                        track = None
                        notes.append(f"No new music ({type(e).__name__}).")
                    if track:
                        o["file"] = _rel(track, ROOT)
                if o["op"] == "broll":
                    stage(path, f"Finding footage: {o['text']}", ix)
                    seconds = sum(y - x for a, b in o["ranges"] for x, y in tl.out_ranges(a, b))
                    try:
                        clip = _broll_clip(path, ctx, o["text"], seconds, _target_size(spec, base),
                                           f"r{n}/broll_{len(o['ranges'])}_{abs(hash(o['text'])) % 10000}.mp4",
                                           client, log)
                    except Exception as e:  # noqa: BLE001
                        clip = None
                        log(f"   ℹ️ footage failed ({type(e).__name__}: {str(e)[:120]})")
                    if clip:
                        o["file"] = _rel(clip, path)
                    else:
                        notes.append(f"No free footage of '{o['text']}' was found.")
            spec = compile_ops(all_ops, base["seconds"], base_words, base)
            transcript = caption_transcript(state, spec, tl, path, client) if (spec["captions"] or spec["language"]
                                                                               or spec["fixes"]) else None
            ass = (caption_ass(path, ctx, state, spec, transcript, tl.duration, os.path.join(rdir, "captions.ass"))
                   if spec["captions"] and transcript and transcript["segments"] else None)
            stage(path, "Making the video" + (" with its captions" if ass else ""), ix)
            final = render(path, state, spec, ctx, os.path.join(rdir, "final.mp4"), client, log, captions=ass)
            meta["transcript"] = transcript or caption_transcript(state, {**spec, "language": None, "fixes": []}, tl)
            meta["short"]["end"] = round(float(meta["short"].get("start") or 0) + tl.duration, 3)
            meta["short"]["seconds"] = round(tl.duration, 3)
        else:
            prev = state["revisions"][state["current"] - 1]["final"] if state.get("current") else None
            final = os.path.join(path, prev) if prev else None
        changed = _details(client, ctx, meta, details, meta["transcript"], log) if details else []
        stage(path, "Checking the result", ix)
        qa = []
        if final and file_changes:
            try:
                import video_qa
                qa = video_qa.check(final, long=tl.duration > 180, silent_ok=not base.get("audio"))
            except Exception:  # noqa: BLE001 — the check is extra
                qa = []
            base_spec = compile_ops([], base["seconds"], base_words, base)
            # Only THIS request's visible changes are checked: with a blur from an earlier edit in the chain,
            # "clean the audio" was sent to the frame check, which said "cannot be seen", and the edit was
            # planned and rendered a second time for nothing (live run, 4-nov-2026: 121 s instead of ~60).
            if any(o["op"] in VISIBLE_OPS for o in ops):
                done, problems = check(client, request, p.summary, os.path.join(path, base["served"]), final,
                                       spec, tl, timeline(base_spec))
            else:
                done, problems = None, []
        else:
            done, problems = None, []
        last = {"p": p, "ops": ops, "all_ops": all_ops, "final": final, "notes": notes, "remake": remake,
                "details": changed, "meta": meta, "seconds": tl.duration, "done": done, "problems": problems + qa,
                "n": n, "file_changes": file_changes}
        if done is False and attempt + 1 < MAX_PASSES and not qa:
            note = ("A first attempt was made and checked. The check says: " + "; ".join(problems)
                    + ". Plan again so the requested change really shows.")
            continue
        break
    p, n = last["p"], last["n"]
    rel = _rel(last["final"], path) if last["final"] else None
    rev = {"n": n, "prompt": request, "summary": p.summary, "assumptions": p.assumptions[:5],
           "why_not": p.why_not, "notes": last["notes"], "ops": last["ops"], "all_ops": last["all_ops"],
           "final": rel, "seconds": round(last["seconds"], 2), "details": last["details"],
           "check": {"done": last["done"], "problems": last["problems"]}, "meta": last["meta"], "at": _now(),
           "remake": last["remake"]}
    state["revisions"] = state["revisions"][:n - 1] + [rev]
    save(path, state)
    if rel:
        _publish(path, state, n)
    else:
        state["current"] = n
        save(path, state)
    stage(path, "Done", ix)
    return {"ok": True, "n": n, "summary": p.summary, "assumptions": rev["assumptions"], "why_not": p.why_not,
            "notes": last["notes"], "check": rev["check"], "seconds": rev["seconds"], "details": last["details"],
            "remake": last["remake"], "file_changed": last["file_changes"],
            "push": bool(last["details"]) and ctx["on_youtube"]}


# ---------------------------------------------------------------- suggestions: the editor proposes

SUGGEST_PROMPT = """You are a senior YouTube Shorts editor looking at one of the owner's videos before it goes
up. Watch it (attached when it is short) and read its edit sheet:

{sheet}

Suggest the {n} edits that would most improve how many viewers stay past the first seconds and to the end,
best first. Each one is ONE short instruction the owner could type into the editor, in {language}, naming the
exact moment by its words or seconds, e.g. "Pehle 1.2 second ki khamoshi kaat do", "'15,000' par zoom aur ding",
"Cut the first 0.8 s of silence". Only things this editor can do: {ops}.
Rules: never change a fact, a number or the story; nothing about OUR OWN BRANDING; no edit already in EDITS SO
FAR; skip music changes when a bed is fine; if the video is already strong, suggest fewer (even none).
When the sheet says where VIEWERS OF THIS CHANNEL leave, the first suggestion fixes this video's moments just
before that time (a pause, a slow line, nothing new on screen) and its "why" says so ("most leave by 0:03").
For each: text (the instruction, under 90 characters) and why (under 12 words)."""


class Suggestion(BaseModel):
    text: str
    why: str = ""


class Suggestions(BaseModel):
    items: List[Suggestion]


def suggest(job_id, client=None, n=4):
    """Edits the AI proposes for this video (one call, cached until the video changes):
    {"items": [{"text", "why"}], "at"}. Raises EditError for a video that cannot be edited."""
    import script_craft
    import short_kit as kit
    ctx = context(job_id)
    path, ix = ctx["path"], ctx["index"]
    served = studio.served(path, ix)
    cache = os.path.join(_edits(path, ix), "suggest.json")
    hit = _read_json(cache, None)
    key = f"{os.path.basename(served)}:{int(os.path.getmtime(served)) if os.path.isfile(served) else 0}"
    if hit and hit.get("key") == key:
        return hit
    if ctx["on_youtube"]:
        out = {"key": key, "at": _now(), "items": [
            {"text": "Write a better title", "why": "only the details of a live video can change"},
            {"text": "Write a better description", "why": "more search words, credits kept"}]}
        _write_json(cache, out)
        return out
    state = ensure_base(path, ix)
    base = state["base"]
    base_words = _words(base["meta"]["transcript"])
    spec = compile_ops(_current_ops(state), base["seconds"], base_words, base)
    tl = timeline(spec)
    words = words_now(base_words, tl)
    sheet = edit_sheet(ctx, state, tl, words)
    # The owner types Roman Urdu; English only for a video that clearly speaks English.
    toks = [re.sub(r"[^a-z]", "", w["word"].lower()) for w in words]
    english = sum(t in ("the", "and", "is", "of", "to", "in", "that", "this", "was", "you", "it", "for") for t in toks)
    roman = sum(t in ("hai", "hain", "ka", "ki", "ke", "mein", "aur", "nahi", "kya", "ne", "se", "ko", "bhi", "toh",
                      "yeh", "woh", "tha", "thi", "sirf", "kar", "ho", "hua", "liye", "diye", "jo") for t in toks)
    language = "simple English" if english >= max(3, 2 * roman) else "Roman Urdu (Latin letters)"
    ops = ", ".join(k for k in OPS if k not in ("remake", "undo", "description", "tags"))
    prompt = SUGGEST_PROMPT.format(sheet=sheet, n=n, language=language, ops=ops)
    parts = [prompt]
    watch = proxy(path, served, ix) if tl.duration <= PLAN_VIDEO_SECONDS and os.path.isfile(served) else None
    client = client or kit.gemini()
    if watch and os.path.getsize(watch) <= INLINE_VIDEO_BYTES:
        from google.genai import types
        with open(watch, "rb") as f:
            parts = [types.Part.from_bytes(data=f.read(), mime_type="video/mp4"), prompt]
    got = kit.ask_json(client, Suggestions, parts, model=os.environ.get("AI_EDIT_MODEL") or script_craft.writer_model(),
                       max_tokens=PLAN_TOKENS, invalid_tries=2)
    items, seen = [], set()
    for s in got.items:
        text = " ".join((s.text or "").split())[:120]
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        items.append({"text": text, "why": " ".join((s.why or "").split())[:100]})
    out = {"key": key, "at": _now(), "items": items[:n]}
    _write_json(cache, out)
    return out


# ---------------------------------------------------------------- status for the Studio

def status(job_id):
    path = studio.job_dir(job_id)
    ix = studio.split_ref(job_id)[1]
    state = load(path, ix) or {}
    task = _read_json(os.path.join(path, edits_name(ix), "task.json"), {})
    result = _read_json(os.path.join(path, edits_name(ix), "result.json"), None)
    revs = [{"n": r["n"], "prompt": r["prompt"], "summary": r["summary"], "at": r["at"], "seconds": r["seconds"],
             "check": r.get("check"), "notes": r.get("notes") or [], "assumptions": r.get("assumptions") or [],
             "details": r.get("details") or [], "has_file": bool(r.get("final"))}
            for r in state.get("revisions") or []]
    return {"current": state.get("current", 0), "revisions": revs, "stage": task.get("stage"),
            "stage_at": task.get("at"), "result": result,
            "base_seconds": (state.get("base") or {}).get("seconds")}


def write_request(job_id, prompt):
    path = studio.job_dir(job_id)
    ix = studio.split_ref(job_id)[1]
    _write_json(os.path.join(_edits(path, ix), "request.json"), {"prompt": prompt, "at": _now()})
    try:
        os.remove(os.path.join(path, edits_name(ix), "result.json"))
    except OSError:
        pass
    stage(path, "Starting", ix)


# ---------------------------------------------------------------- the owner's own uploaded videos

def uploads():
    return _read_json(UPLOADS_FILE, [])


def create_upload(src, filename, keep_days=7):
    """A new Studio job from an uploaded file: its own folder, the file as the clip, a details file. The
    words come from ``transcribe`` (run next, in a subprocess). Returns the job id."""
    import uuid
    info = _probe(src)
    if not info["seconds"]:
        raise EditError("That file is not a video ffmpeg can read.")
    job_id = str(uuid.uuid4())
    path = os.path.join(studio.OUTPUT_DIR, job_id)
    os.makedirs(path)
    stem = "Upload_" + time.strftime("%Y-%m-%d_%H%M%S")
    clip = os.path.join(path, f"{stem}_clip_1.mp4")
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", src, "-map", "0:v:0", "-map", "0:a:0?",
                        "-c", "copy", "-movflags", "+faststart", clip], capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not os.path.isfile(clip):
        # Not an MP4-friendly stream: make it one.
        r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", src, "-map", "0:v:0", "-map", "0:a:0?",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", clip],
                           capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            shutil.rmtree(path, ignore_errors=True)
            raise EditError("That video could not be read: " + r.stderr.strip()[-200:])
    name = os.path.splitext(os.path.basename(filename or "video"))[0][:80] or "My video"
    data = {"genre": UPLOAD_GENRE, "output_format": "upload", "transcript": None,
            "shorts": [{"seo_title": name, "seo_description": "", "seo_tags": [], "start": 0.0,
                        "end": round(info["seconds"], 3), "seconds": round(info["seconds"], 3)}]}
    with open(os.path.join(path, f"{stem}_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(os.path.join(path, ".source.json"), "w", encoding="utf-8") as f:
        json.dump({"genre": UPLOAD_GENRE, "keep_until": _now() + keep_days * 86400}, f)
    rows = [u for u in uploads() if os.path.isdir(os.path.join(studio.OUTPUT_DIR, u.get("job_id", "")))]
    rows.append({"job_id": job_id, "name": name, "at": _now()})
    _write_json(UPLOADS_FILE, rows[-200:])
    return job_id


def transcribe(job_id):
    """The uploaded video's words with their times, into its details file."""
    path = studio.job_dir(job_id)
    marker = os.path.join(path, ".transcribing")
    open(marker, "w").close()
    try:
        import transcribe_backends
        clip = os.path.join(path, f"{studio._base(path)}_clip_1.mp4")
        if not _probe(clip)["audio"]:
            transcript = {"language": "none", "segments": []}
        else:
            transcript = transcribe_backends.transcribe_media(clip)
        data = studio._read(path)
        data["transcript"] = {"language": transcript.get("language"), "segments": [
            {"start": float(s["start"]), "end": float(s["end"]), "text": (s.get("text") or "").strip(),
             "words": [{"word": w["word"], "start": float(w["start"]), "end": float(w["end"])}
                       for w in s.get("words") or []]} for s in transcript.get("segments") or []]}
        studio._write(path, data)
    finally:
        try:
            os.remove(marker)
        except OSError:
            pass


def _main(argv):
    if len(argv) == 3 and argv[1] == "apply":
        job_id = argv[2]
        path = studio.job_dir(job_id)
        ix = studio.split_ref(job_id)[1]
        req = _read_json(os.path.join(path, edits_name(ix), "request.json"), {})
        try:
            result = apply(job_id, req.get("prompt") or "")
        except studio.StudioError as e:
            result = {"ok": False, "message": str(e)}
        except Exception as e:  # noqa: BLE001 — the owner sees one plain line
            import traceback
            traceback.print_exc()
            result = {"ok": False, "message": f"The edit failed ({type(e).__name__}: {str(e)[:200]})."}
        result["prompt"] = req.get("prompt") or ""
        result["at"] = _now()
        _write_json(os.path.join(_edits(path, ix), "result.json"), result)
        stage(path, "Done" if result.get("ok") else "Stopped", ix)
        print("RESULT " + json.dumps({"ok": result.get("ok")}))
        return 0
    if len(argv) == 3 and argv[1] == "transcribe":
        transcribe(argv[2])
        print("TRANSCRIBED")
        return 0
    print("usage: ai_editor.py apply <job_id> | transcribe <job_id>")
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
