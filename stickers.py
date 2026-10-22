"""Animated emoji stickers that pop up next to a voice line in the generated Shorts.

Google's Noto Emoji Animation (https://googlefonts.github.io/noto-emoji-animation/),
"Animated Noto Emoji is licensed under CC BY 4.0" (the site's FAQ, 22-oct-2026), so
every video that shows one carries CREDIT in its description. The files are the
512 px animated WebPs from fonts.gstatic.com/s/e/notoemoji/latest/<codepoint>/512.webp,
kept outside the repo as <codepoint>.webp in DIR (SOURCE.txt there says where from).

How ffmpeg 9.0.1 plays them (measured 22-oct-2026, scratch proof scripts):
- the demuxer is webp_anim, and it plays a file ONCE unless ``-ignore_loop 0`` (its
  default is to ignore the file's loop flag). ``-stream_loop -1`` does NOT loop it:
  still 32 frames / 0.96 s for the fire emoji, where -ignore_loop 0 -t 3 gave 99 frames.
- the input names its demuxer (-f webp_anim): ffmpeg's own libwebp_anim output probes
  as webp_pipe, where -ignore_loop is "Option not found". A still WebP is refused by
  webp_anim ("Invalid data"), so ``animated()`` reads the VP8X flag and stills are looped
  as pictures (-loop 1).
- with -ignore_loop 0 the input never ends by itself, so it always gets an input -t.
  Over footage that -t runs to the end of the video (``alive_until``): an overlay
  input that ended early is what stalled short_kit.render's footage path (CLAUDE.md,
  "Over footage"); the sticker is hidden outside its window by enable= and the fades.
  A 12 s footage test with three stickers finished either way (12.8 s alive, 10.2 s
  window-only), so on the gradient the cheaper window-only input is fine.
- alpha survives: the transparent corners of the sticker's box read the background
  colour exactly (43,14,61 on #2B0F3D) and the footage's own pixels over footage.
"""
import enum
import os

from pydantic import BaseModel, field_validator

import short_kit

DEFAULT_DIR = r"D:\youtube\oss\noto-emoji-animation"
DIR = os.environ.get("STICKER_DIR") or DEFAULT_DIR

# name -> Unicode codepoint (the file name and the gstatic path). Every one is in the
# animated set (the site's data/api.json) and downloaded 200 on 22-oct-2026.
EMOJI = {
    "fire": "1f525",
    "shocked": "1f631",
    "mind_blown": "1f92f",
    "joy": "1f602",
    "heartbreak": "1f494",
    "eyes": "1f440",
    "check": "2705",
    "cross": "274c",
    "hundred": "1f4af",
    "trophy": "1f3c6",
    "cricket": "1f3cf",
    "thinking": "1f914",
    "point_down": "1f447",
    "clap": "1f44f",
    "crying": "1f62d",
    "angry": "1f620",
    "rocket": "1f680",
    "crown": "1f451",
}
# What each one is for, said to the model.
MEANING = {
    "fire": "a record, a hot streak, a huge performance",
    "shocked": "a shocking number or fact",
    "mind_blown": "an unbelievable fact or twist",
    "joy": "something genuinely funny",
    "heartbreak": "a sports loss or a near miss",
    "eyes": "look at this, a twist is coming",
    "check": "a correct answer, something true",
    "cross": "a wrong answer, a myth, something false",
    "hundred": "a century, a perfect score, 100 of something",
    "trophy": "a win, a title, a cup",
    "cricket": "cricket action: batting, bowling, a match",
    "thinking": "a question to the viewer, a puzzle",
    "point_down": "telling the viewer to comment below or follow",
    "clap": "praise for a great effort",
    "crying": "sad sports news (a defeat, a dropped player)",
    "angry": "an unfair decision or a bad umpiring call",
    "rocket": "a fast rise, quick growth, a big jump",
    "crown": "the best ever, the king of something",
}
# Attribution for CC BY 4.0 (title, author, source, licence, changes). Goes in the
# description of every video that shows a sticker.
CREDIT = ("Animated emoji: Noto Emoji Animation by Google "
          "(https://googlefonts.github.io/noto-emoji-animation/), "
          "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), resized.")

# A sticker needs room: lines with one are at least GAP apart (1 and 4, never 1 and 2).
GAP = 3
# Lines where a sticker reads as mockery. The model is told; this catches what it misses
# (Roman Urdu + English, whole words). Cricket words are left out on purpose: "attack"
# (a bowling attack), "blast", "crash out", "passed" (a record), Imam-ul-Haq, Mohammad
# Nabi, "god of cricket", and "fir" (Roman Urdu for "phir").
_BLOCK = {
    "death", "dead", "died", "dies", "die", "killed", "kill", "killing", "murder", "murdered",
    "funeral", "suicide", "rip", "maut", "inteqal", "intiqal", "wafat", "shaheed",
    "janaza", "qatl", "khudkushi", "tragedy", "tragic", "hadsa", "haadsa", "accident",
    "bomb", "terror", "terrorist", "flood", "earthquake", "zalzala", "sailab",
    "religion", "religious", "allah", "islam", "islamic", "quran", "prophet", "rasool",
    "masjid", "mosque", "mandir", "temple", "church", "namaz", "hazrat", "khuda",
    "allegation", "allegations", "alleged", "allegedly", "accused", "ilzaam", "ilzam", "ilzamat",
    "arrest", "arrested", "giraftar", "rape", "harassment", "fraud", "scandal", "fixing",
}
# Default spots on the 1080x1920 canvas: just above the captions (short_kit.CAPTION_TOP_PX
# 1430) and clear of the Shorts buttons on the right edge, alternating sides.
SIZE = 260
Y = 1290
X_SPOTS = (780, 300)
LEAD = 0.15   # the sticker lands a beat after its line starts
HOLD = 2.2    # and stays at most this long
POP = 0.32    # seconds of the pop-in (grow to 120%, settle at 100%)


def _dir():
    return os.environ.get("STICKER_DIR") or DIR


def available():
    """Stickers on (STICKERS != "0") and at least one sticker file in DIR."""
    if os.environ.get("STICKERS", "1").strip() == "0":
        return False
    try:
        return any(f.lower().endswith(".webp") for f in os.listdir(_dir()))
    except OSError:
        return False


def path(name):
    """The sticker file for ``name``, or None (unknown name, file missing)."""
    code = EMOJI.get(name or "")
    if not code:
        return None
    p = os.path.join(_dir(), f"{code}.webp")
    return p if os.path.isfile(p) else None


# The closed choice Gemini answers from. "none" stands for no sticker (an empty enum
# value is not a safe thing to send the API); pick() turns it into "".
Sticker = enum.Enum("Sticker", {n: n for n in [*EMOJI, "none"]}, type=str)


class _Line(BaseModel):
    line: int
    sticker: Sticker

    @field_validator("sticker", mode="before")
    @classmethod
    def _unknown_is_none(cls, v):
        # A name outside the list is dropped, not a failed call for the whole Short.
        v = str(getattr(v, "value", v) or "").strip().lower()
        return v if v in EMOJI else "none"


class _Picks(BaseModel):
    lines: list[_Line]


def _blocked(text):
    words = "".join(c.lower() if c.isalnum() else " " for c in str(text)).split()
    return any(w in _BLOCK for w in words)


def _prompt(lines, names):
    menu = "\n".join(f"- {n}: {MEANING.get(n, n)}" for n in names)
    numbered = "\n".join(f"{i}. {str(t).strip()}" for i, t in enumerate(lines, 1))
    return (
        "These are the voice lines of a YouTube Short, in order. An animated emoji sticker can "
        "pop up next to a few of them, matching what that line says.\n\n"
        f"Stickers:\n{menu}\n\n"
        "Rules:\n"
        f"- At most one sticker for every {GAP} lines, never on two lines in a row. Most lines get none.\n"
        "- Only where it clearly fits the line. When unsure: none.\n"
        "- Never a sticker on a line about a death, a tragedy (an accident, a disaster, an attack), "
        "religion, or an allegation against a person: none there.\n\n"
        f"Lines:\n{numbered}\n\n"
        f"Return one entry for every line (1 to {len(lines)}): its number and a sticker name or \"none\"."
    )


def enforce(picks, lines=None):
    """Code's own rules over the model's answer: known names with a file only, no sticker on a
    blocked line, and every two stickers at least GAP lines apart (the earlier one stays)."""
    out, last = [], -GAP
    for i, name in enumerate(picks):
        keep = bool(name) and path(name) is not None and i - last >= GAP
        if keep and lines is not None and i < len(lines) and _blocked(lines[i]):
            keep = False
        out.append(name if keep else "")
        if keep:
            last = i
    return out


def pick(client, lines, log=print):
    """[name or ""] per line: one Gemini call, then ``enforce``. Never raises: stickers off,
    no files or any failure gives a blank per line."""
    lines = list(lines or [])
    blank = [""] * len(lines)
    try:
        if not lines or not available():
            return blank
        names = [n for n in EMOJI if path(n)]
        if not names:
            return blank
        answer = short_kit.ask_json(client, _Picks, _prompt(lines, names))
        raw = list(blank)
        for row in answer.lines:
            name = row.sticker.value if isinstance(row.sticker, enum.Enum) else str(row.sticker)
            if 1 <= row.line <= len(lines) and name in names:
                raw[row.line - 1] = name
        picks = enforce(raw, lines)
        chosen = [f"{i + 1}:{n}" for i, n in enumerate(picks) if n]
        log(f"   🎭 Stickers: {', '.join(chosen) if chosen else 'none'}")
        return picks
    except Exception as e:  # noqa: BLE001 — a sticker is never worth a failed Short
        try:
            log(f"   🎭 Stickers skipped ({type(e).__name__}).")
        except Exception:  # noqa: BLE001
            pass
        return blank


def place(picks, spans, seconds=None, size=SIZE, y=Y, xs=X_SPOTS):
    """Timed stickers from per-line picks and each line's (start, end) seconds:
    [{"name", "path", "t0", "t1", "x", "y", "size"}], sides alternating. A sticker
    lands LEAD after its line starts and stays to the line's end (1.0-HOLD s)."""
    out = []
    for name, span in zip(picks, spans):
        p = path(name) if name else None
        if not p or not span:
            continue
        start, end = float(span[0]), float(span[1])
        t0 = start + LEAD
        t1 = min(max(end, t0 + 1.0), t0 + HOLD)
        if seconds is not None:
            t1 = min(t1, float(seconds))
        if t1 - t0 < 0.6:
            continue
        out.append({"name": name, "path": p, "t0": round(t0, 3), "t1": round(t1, 3),
                    "x": xs[len(out) % len(xs)], "y": y, "size": size})
    return out


def animated(sticker_path):
    """True for an animated WebP: RIFF/WEBP with a VP8X chunk whose animation flag (0x02) is set."""
    try:
        with open(sticker_path, "rb") as f:
            head = f.read(21)
    except OSError:
        return False
    return (len(head) == 21 and head[:4] == b"RIFF" and head[8:12] == b"WEBP"
            and head[12:16] == b"VP8X" and bool(head[20] & 0x02))


def overlay_args(sticker_path, idx, t0, t1, x, y, size=SIZE, src="[0:v]", label="stk0",
                 alive_until=None, fps=short_kit.FPS):
    """ffmpeg pieces for one sticker shown from t0 to t1, centred at (x, y), ``size`` px wide.

    Returns (inputs, filters, out): ``cmd += inputs``, ``graph += filters``, and ``out``
    (``[<label>_v]``) is the picture with the sticker on it. ``idx`` is the input number
    the sticker gets; ``src`` the picture label it goes over.

    Over footage pass ``alive_until`` = the render's length: the input then runs to the
    end instead of stopping at t1 (see the module note on the footage stall).

    The proven command (22-oct-2026, ffmpeg 9.0.1, fire at 0.3-2.7 s on a 3 s canvas):
      ffmpeg -f lavfi -i color=c=0x2B0F3D:s=1080x1920:r=30:d=3
             -f webp_anim -ignore_loop 0 -t 3.2 -i 1f525.webp -filter_complex
      "[1:v]setpts=PTS-STARTPTS+0.3/TB,fps=30,format=rgba,
       scale=w='trunc(400*if(lt(t-0.3,0.18),0.3+5*(t-0.3),if(lt(t-0.3,0.32),1.2-(t-0.3-0.18)/0.7,1))/2)*2'
       :h=-2:eval=frame,fade=t=in:st=0.3:d=0.12:alpha=1,fade=t=out:st=2.45:d=0.25:alpha=1[stk0];
       [0:v][stk0]overlay=x='540-w/2':y='960-h/2':eof_action=pass:enable='between(t,0.3,2.7)'"
    """
    t0, t1 = float(t0), float(t1)
    t1 = max(t1, t0 + 0.4)
    size = max(40, int(size))
    length = t1 - t0
    if alive_until is not None:
        length = max(length, float(alive_until) - t0 + 0.5)
    if animated(sticker_path):
        # -f names the demuxer: probed as webp_pipe, -ignore_loop is "Option not found".
        inputs = ["-f", "webp_anim", "-ignore_loop", "0", "-t", f"{length:.3f}", "-i", str(sticker_path)]
    else:
        # webp_anim refuses a still ("Invalid data"): held like short_kit's pictures.
        inputs = ["-loop", "1", "-framerate", str(fps), "-t", f"{length:.3f}", "-i", str(sticker_path)]
    k = f"max(t-{t0:.3f},0)"
    # 30% -> 120% in 0.18 s, back to 100% by POP (0.32 s): a pop, then still.
    grow = f"if(lt({k},0.18),0.3+5*{k},if(lt({k},{POP:g}),1.2-({k}-0.18)/0.7,1))"
    fade_out = max(t0, t1 - 0.25)
    filters = [
        f"[{idx}:v]setpts=PTS-STARTPTS+{t0:.3f}/TB,fps={fps},format=rgba,"
        f"scale=w='trunc({size}*{grow}/2)*2':h=-2:eval=frame,"
        f"fade=t=in:st={t0:.3f}:d=0.12:alpha=1,fade=t=out:st={fade_out:.3f}:d=0.25:alpha=1[{label}]",
        f"{src}[{label}]overlay=x='{float(x):.0f}-w/2':y='{float(y):.0f}-h/2':"
        f"eof_action=pass:enable='between(t,{t0:.3f},{t1:.3f})'[{label}_v]",
    ]
    return inputs, filters, f"[{label}_v]"
