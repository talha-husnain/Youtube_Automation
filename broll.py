"""Moving background for the generated Shorts: free stock footage cut to the voice.

Our generated Shorts used to be text cards on a moving gradient: on a phone
they read as slides. Faceless channels that do well put real footage behind
everything (MoneyPrinterTurbo's whole idea), so each voice line now gets its
own clip or photo from stock_media, chosen for what the line says, and the
background cuts every CUT seconds (a new clip, another moment of the same
clip, or a closer crop), the pace Shorts viewers are used to.

Each shot is one small ffmpeg encode (a photo is decoded once and repeated
with the loop filter, a video is read from a moving offset), joined by the
concat demuxer; short_kit.render then lays the text over it (bg_video=).
Nothing found (no keys, no results): None, and the Short keeps its gradient.
"""
import os
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import List

from pydantic import BaseModel

import faces
import slowmo
import short_kit as kit
import stock_media

FPS = kit.FPS
CUT = 2.8          # a new shot about this often
MIN_SHOT = 1.4
# Text stays readable on bright footage. -0.10 until 29-oct-2026; the cards are glass over a blur now
# (cricket_shorts.GLASS_ALPHA) and every caption has its outline, so the footage keeps its light.
DIM = "eq=brightness=-0.04:saturation=1.08:contrast=1.04"
# One look per channel (owner, 22-oct-2026): footage from three libraries looked like three films.
# Applied to footage only (cards, captions and archival pictures keep their colours), before DIM.
# Previewed side by side on a cached clip; songs and history got a softer vignette (PI/6) because
# DIM already darkens. CHANNEL_GRADE=0 turns it off.
GRADES = {
    "cricket": "eq=contrast=1.05:saturation=1.15,colorbalance=rm=0.03:bm=-0.03:rh=0.02:bh=-0.02",
    "controversy": "eq=contrast=1.08:saturation=0.82,colorbalance=rs=-0.03:bs=0.05:rh=0.04:bh=-0.03",
    "quiz": "eq=saturation=1.2:brightness=0.02",
    "music": "eq=contrast=1.06:saturation=0.9:brightness=0.02,colorbalance=rs=-0.04:bs=0.06:rh=0.05:bh=-0.04,"
             "vignette=angle=PI/6",
    "history": "eq=saturation=0.85,colorbalance=rs=0.04:bs=-0.05:rm=0.03:bm=-0.03,vignette=angle=PI/6",
}


def grade():
    """The channel's grade as a filter prefix ("...," or "") for this job (CONTENT_GENRE)."""
    if os.environ.get("CHANNEL_GRADE", "1") == "0":
        return ""
    g = GRADES.get(os.environ.get("CONTENT_GENRE", ""), "")
    return g + "," if g else ""


class Terms(BaseModel):
    terms: List[str]


TERMS_PROMPT = """For each numbered line of a short video about: {topic}
write one search for free stock footage (Pexels, Pixabay): 2 to 4 English words a camera can film, a place,
object, action, crowd, weather or mood ("cricket stadium night", "judge gavel courtroom", "desert sunset
camels", "rain window night"). Never a person's name, a team, brand, logo, flag or text; stock libraries have
none. Make every line's search show something different from the line before it (the first footage Short
showed three courthouse domes in a row), and match the line's mood: serious lines, serious footage.
{rule}Lines may be Roman Urdu. Return exactly {n} terms, in order.

{lines}"""


def terms_for(client, topic, lines, rule=""):
    got = kit.ask_json(client, Terms, TERMS_PROMPT.format(
        topic=topic, n=len(lines), rule=rule, lines="\n".join(f"{k}: {t[:200]}" for k, t in enumerate(lines))))
    # A term longer than 5 words is the line echoed back: on 22-oct-2026 the hook "Sirf 31 balls par ODI
    # century, yeh pagalpan kisne kiya?" went to the libraries as is and found nothing.
    short = " ".join(topic.split()[:4])[:60]
    terms = [t.strip()[:60] if 0 < len(t.split()) <= 5 else short for t in got.terms][:len(lines)]
    return terms + [short] * (len(lines) - len(terms))


def windows_from(segments, total):
    """[(start, end, line)] tiling 0..total from caption segments (one per voice line)."""
    segs = [s for s in segments if (s.get("text") or "").strip()]
    if not segs:
        return []
    starts = [0.0] + [float(s["start"]) for s in segs[1:]]
    ends = starts[1:] + [total]
    return [(a, b, s["text"]) for a, b, s in zip(starts, ends, segs) if b - a > 0.05]


BEAT_TOLERANCE = 0.35    # a cut moves at most this far to land on a beat


def _on_beat(t, beats, after):
    """``t`` moved to the nearest beat within BEAT_TOLERANCE, if that keeps the shot at least
    MIN_SHOT long after ``after``; else ``t``."""
    import bisect
    i = bisect.bisect_left(beats, t)
    near = [x for x in beats[max(0, i - 1):i + 1] if abs(x - t) <= BEAT_TOLERANCE]
    if not near:
        return t
    x = min(near, key=lambda v: abs(v - t))
    return x if x - after >= MIN_SHOT else t


def borrow(k, have, uses, prev, nxt):
    """The clip a line without its own takes: the one used least so far, not the clip of the line
    before or after it when another will do, the nearest earlier one on a tie. A line with no pick
    used to repeat the clip before it, so two empty lines showed one clip three times running;
    MoneyPrinterTurbo uses every clip once before repeating any (its video.py)."""
    return min(have, key=lambda j: (uses[j], j in (prev, nxt), abs(k - j) + (0.5 if j > k else 0)))


def cut_seconds():
    """CUT, or this job's length from the "pace" test (BROLL_CUT: the winners' pace teardown.py measured,
    my_channels.EXPERIMENTS), kept between MIN_SHOT and 6 s."""
    try:
        v = float(os.environ.get("BROLL_CUT") or CUT)
    except ValueError:
        v = CUT
    return max(MIN_SHOT, min(6.0, v))


def plan_shots(windows, items, seed=7, beats=None):
    """[(frames, item, offset, close)]: each window cut into shots of about CUT
    seconds; a window without an item borrows one (``borrow``). Frame counts add
    up exactly to the windows' total. ``beats`` (a song's beat times, beats.py):
    every cut but the last lands on the nearest beat."""
    rnd = random.Random(seed)
    have = [k for k, it in enumerate(items) if it]
    if not have:
        return []
    shots, frames_done, t_done = [], 0, 0.0
    end = windows[-1][1] if windows else 0.0
    uses, prev = {j: 1 for j in have}, None
    cut = cut_seconds()
    for k, (a, b, _line) in enumerate(windows):
        j = k if k < len(items) and items[k] else None
        if j is None:
            j = borrow(k, have, uses, prev, k + 1 if k + 1 < len(items) and items[k + 1] else None)
            uses[j] += 1
        it, borrowed, prev = items[j], j != k, j
        n = max(1, int((b - a) / cut + 0.5))
        while n > 1 and (b - a) / n < MIN_SHOT:
            n -= 1
        for s in range(n):
            before = t_done
            t_done = a + (b - a) * (s + 1) / n
            if beats and t_done < end - 1e-6:
                t_done = _on_beat(t_done, beats, before)
            f = round(t_done * FPS) - frames_done
            if f <= 0:
                continue
            frames_done += f
            span = max(0.0, (it.get("seconds") or 0) - f / FPS - 0.5)
            offset = 0.3 + (rnd.uniform(0, span) if (s or borrowed) and span > 0 else 0.0)
            shots.append((f, it, round(offset, 2), bool(s % 2) or borrowed))
    return shots


# Quality pass 2 (22-oct-2026): every footage shot used to be static (every other one a fixed 0.86 crop)
# and photos panned in a straight line. Now each shot moves: a slow push-in, or on the "close" shots a
# pull-out from the old 0.86 framing, eased in and out (cosine), and upscaled stock gets a light sharpen.
# BROLL_MOTION=0 restores the static shots.
PUSH = (1.0, 1.08)
PULL = (1 / 0.86, 1.08)
SHARPEN = "unsharp=5:5:0.4"


def _ease(d):
    return f"(0.5-0.5*cos(PI*t/{d:.3f}))"


def motion():
    return os.environ.get("BROLL_MOTION", "1").strip() != "0"


def upscaled(item, w, h, slow=False):
    """True when the clip is enlarged by more than 5% to fill a w x h frame: only those are
    sharpened (29-oct-2026: every shot was, a full-HD clip too). The size is the one the search
    downloaded (stock_media's rendition); a ``slow`` (RIFE) copy is at most slowmo.LONG_SIDE
    (1280) on its long side, so it is; a clip of unknown size is sharpened as before."""
    if slow:
        return max(w, h) > slowmo.LONG_SIDE * 1.05
    size = (item.get("w") or 0, item.get("h") or 0)
    if not all(size):
        return True
    return max(w / size[0], h / size[1]) > 1.05


FROST_BLUR = "boxblur=luma_radius=22:luma_power=2:chroma_radius=11:chroma_power=2"


def mask(w, h, radius):
    """A white rounded rectangle on black, w x h: a card panel's shape for the blurred footage under it
    (made once, cached in output/ next to the shade)."""
    path = os.path.join(os.path.dirname(stock_media.CACHE_DIR), f".broll_mask_{w}x{h}_{radius}.png")
    if not os.path.isfile(path):
        import threading
        from PIL import Image, ImageDraw
        im = Image.new("L", (w, h), 0)
        ImageDraw.Draw(im).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}_{threading.get_ident()}.png"
        im.save(tmp)
        os.replace(tmp, path)
    return path


def _frost_graph(vf, frost, d):
    """The shot's filters with the footage under a card's glass panel blurred: (graph, mask path).
    The blur clears in as the card lands (it swipes in for 0.3 s) and fades with the card."""
    x, y, bw, bh, r, a, b = frost
    fade = ""
    if a > -0.05:
        # From 2/3 of the way in: earlier, a blurred patch showed ahead of the sliding panel.
        fade += f",fade=t=in:st={max(0.0, a) + 0.2:.3f}:d=0.2:alpha=1"
    if b < d - 0.05:
        fade += f",fade=t=out:st={max(0.0, b - 0.2):.3f}:d=0.2:alpha=1"
    on = f"between(t,{max(0.0, a):.3f},{min(d, b):.3f})"
    return (f"[0:v]{vf}[base];[base]split=2[bm][bs];"
            f"[bs]crop={bw}:{bh}:{x}:{y},{FROST_BLUR},format=yuva420p[bb];"
            f"[1:v]format=gray,scale={bw}:{bh}[bk];[bb][bk]alphamerge{fade}[bf];"
            f"[bm][bf]overlay={x}:{y}:enable='{on}',format=yuv420p[v]"), mask(bw, bh, r)


def _located(job_dir, item):
    """``item`` with a path ffmpeg finds from inside ``job_dir`` (its cwd): a path relative to the project
    instead of the job (a history teaser's pictures of its long video) becomes absolute."""
    p = item.get("path") or ""
    if p and not os.path.isabs(p) and not os.path.exists(os.path.join(job_dir, p)) and os.path.exists(p):
        return {**item, "path": os.path.abspath(p)}
    return item


def _shot(job_dir, k, frames, item, offset, close, w, h, frost=None):
    item = _located(job_dir, item)
    out = f".broll/s{k:03d}.mp4"
    zoom = 0.86 if close else 1.0      # a closer crop on every other shot: a cut that feels new
    cw, ch = round(w * zoom / 2) * 2, round(h * zoom / 2) * 2
    d = frames / FPS
    if item["kind"] == "video":
        src = ["-ss", f"{offset:.2f}", "-stream_loop", "-1", "-i", item["path"]]
        slow = None
        # A clip that ends before its shot does is stretched with RIFE (slowmo.py, smooth slow motion)
        # instead of looping back to its first frame mid-shot; 1.15-4x only, else the loop stays.
        have = (item.get("seconds") or 0) - offset
        if 0 < have < d and slowmo.available():
            slow = slowmo.stretch(os.path.join(job_dir, item["path"]), offset, have, d,
                                  os.path.join(job_dir, f".broll/s{k:03d}_slow.mp4"))
            if slow:
                src = ["-i", os.path.relpath(slow, job_dir)]
        # The first crop follows the biggest face (faces.py); centred when there is none.
        fx = faces.center_x(os.path.join(job_dir, item["path"]), offset + d / 2)
        fill = f"crop={w}:{h}" + (f":x='min(max(iw*{fx:.4f}-ow/2,0),iw-ow)'" if fx is not None else "")
        if motion():
            a, b = PULL if close else PUSH
            z = f"({a:.4f}+{b - a:.4f}*{_ease(d)})"
            sharp = f"{SHARPEN}," if upscaled(item, w, h, bool(slow)) else ""
            vf = (f"fps={FPS},setpts=PTS-STARTPTS,scale={w}:{h}:force_original_aspect_ratio=increase,{fill},"
                  f"scale=w='trunc({w}*{z}/2)*2':h=-2:eval=frame:flags=bicubic,crop={w}:{h},"
                  f"{sharp}setsar=1,{grade()}{DIM},format=yuv420p")
        else:
            vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,{fill},"
                  f"crop={cw}:{ch},scale={w}:{h},fps={FPS},setsar=1,{grade()}{DIM},format=yuv420p")
    else:
        # A photo: decoded once, then a slow pan on a 2x canvas (half-pixel steps).
        W2, H2 = round(w * 1.12) * 2, round(h * 1.12) * 2
        e = _ease(d) if motion() else f"t/{d:.3f}"
        x = random.Random(k).choice([f"(iw-ow)*{e}", f"(iw-ow)*(1-{e})", "(iw-ow)/2"])
        y = f"(ih-oh)*{e}" if x.endswith("/2") else "(ih-oh)/2"
        src = ["-i", item["path"]]
        vf = (f"scale={W2}:{H2}:force_original_aspect_ratio=increase,crop={W2}:{H2},"
              f"loop=loop={frames - 1}:size=1:start=0,setpts=N/{FPS}/TB,"
              f"crop={cw * 2}:{ch * 2}:x='{x}':y='{y}',scale={w}:{h}:flags=bicubic,setsar=1,{DIM},format=yuv420p")
    if frost:
        graph, frost_mask = _frost_graph(vf, frost, d)
        filters = ["-loop", "1", "-framerate", str(FPS), "-i", frost_mask, "-filter_complex", graph, "-map", "[v]"]
    else:
        filters = ["-vf", vf]
    # crf 17 (was 20): this is the first of three encodes (shot, render, captions); each one loses detail.
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", *src, *filters, "-frames:v", str(frames), "-r", str(FPS),
                        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17" if motion() else "20", "-pix_fmt", "yuv420p",
                        "-video_track_timescale", "30000", out],
                       cwd=job_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                       timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"footage shot failed: {r.stderr.strip()[-300:]}")
    return out


def shade(w=kit.OUT_W, h=kit.OUT_H):
    """A see-through PNG that darkens the top and bottom of the frame, where
    the title and the captions sit: on the first footage Short the title ran
    over bright sky and busy windows. Made once, cached in output/."""
    path = os.path.join(os.path.dirname(stock_media.CACHE_DIR), f".broll_shade_{w}x{h}.png")
    if os.path.isfile(path):
        return path
    from PIL import Image
    alpha = Image.new("L", (1, h), 0)
    top, bottom = round(h * 0.30), round(h * 0.60)
    for y in range(h):
        if y < top:
            a = 150 * (1 - y / top) ** 1.4
        elif y > bottom:
            a = 175 * ((y - bottom) / (h - bottom)) ** 1.2
        else:
            a = 0
        alpha.putpixel((0, y), round(a))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    img.putalpha(alpha.resize((w, h)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    return path


def _frost_in_shots(shots, frost, w):
    """Per shot, the glass panel that covers most of it in the shot's own time, scaled to the
    background's width: (x, y, w, h, radius, start, end) or None."""
    k = w / kit.OUT_W
    out, done = [], 0
    for frames, *_rest in shots:
        a, b = done / FPS, (done + frames) / FPS
        best = None
        for x, y, bw, bh, r, t0, t1 in frost or ():
            over = min(b, t1) - max(a, t0)
            if over > 0.05 and (best is None or over > best[0]):
                best = (over, tuple(round(v * k) for v in (x, y, bw, bh, r)) + (t0 - a, t1 - a))
        out.append(best[1] if best else None)
        done += frames
    return out


def build(job_dir, shots, out_name=".broll.mp4", size=(kit.OUT_W, kit.OUT_H), workers=3, frost=()):
    os.makedirs(os.path.join(job_dir, ".broll"), exist_ok=True)
    w, h = size
    glass = _frost_in_shots(shots, frost, w)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        names = list(ex.map(lambda a: _shot(job_dir, a[0], *a[1], w, h, frost=glass[a[0]]), enumerate(shots)))
    with open(os.path.join(job_dir, ".broll_parts.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(f"file '{n}'\n" for n in names))
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", ".broll_parts.txt",
                        "-c", "copy", out_name], cwd=job_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, errors="replace", timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"footage join failed: {r.stderr.strip()[-300:]}")
    return os.path.join(job_dir, out_name)


# Under half the lines with good footage: a background that jumps between
# footage and borrowed shots looks worse than the Short's own animated look.
MIN_COVERAGE = 0.5
_pending = {}          # job dir -> (lines, Future of their footage), started while the lines are voiced
_early = ThreadPoolExecutor(max_workers=1)


def _find(client, topic, lines, rule, log):
    client = client or kit.gemini()
    log(f"🎞️ Finding stock footage for {len(lines)} lines...")
    terms = terms_for(client, topic, lines, rule)
    # The job's channel kind's checked footage (stock_media.pool, cricket only so far) fills the lines
    # whose own search finds nothing.
    pool = stock_media.pool(os.environ.get("CONTENT_GENRE", ""), client, log)
    return stock_media.for_scenes(client, topic, lines, terms, portrait=True, log=log, rule=rule,
                                  **({"pool": pool} if pool else {}))


def prefetch(job_dir, topic, lines, rule="", client=None, log=print):
    """Start finding footage for these voice lines now, while they are being
    voiced (it needs only the words; the timing comes later): about a minute
    saved per Short. background_for picks the result up when the lines match."""
    if os.environ.get("STOCK_FOOTAGE", "1") == "0" or not stock_media.available() or not lines:
        return

    def safe():
        try:
            return _find(client, topic, list(lines), rule, log)
        except Exception as e:  # noqa: BLE001
            log(f"   ℹ️ Footage search failed ({type(e).__name__}).")
            return [None] * len(lines)
    _pending[os.path.abspath(job_dir)] = ([t for t in lines], _early.submit(safe))


def background_for(topic, segments, total, job_dir, client=None, rule="", log=print, beats=None, frost=()):
    """The whole step for one Short: (background video path, footage items) or
    (None, []) when footage is off, there are no keys or nothing was found.
    Never raises: a Short without footage is still a Short. ``frost``: the
    cards' glass panels (cricket_shorts.frost_boxes), blurred in the footage."""
    if os.environ.get("STOCK_FOOTAGE", "1") == "0" or not stock_media.available():
        return None, []
    windows = windows_from(segments, total)
    if not windows:
        return None, []
    try:
        client = client or kit.gemini()
        lines = [line for _a, _b, line in windows]
        early = _pending.pop(os.path.abspath(job_dir), None)
        if early and early[0] == lines:
            items = early[1].result()
        else:
            items = _find(client, topic, lines, rule, log)
        found = sum(1 for i in items if i)
        if found < len(windows) * MIN_COVERAGE:
            log(f"   ℹ️ Good footage for only {found} of {len(windows)} lines: this Short keeps its own look.")
            return None, []
        shots = plan_shots(windows, items, beats=beats)
        if not shots:
            return None, []
        path = build(job_dir, shots, frost=frost)
        log(f"   ✅ Footage background: {len(shots)} shots from {sum(1 for i in items if i)} clips.")
        return path, [i for i in items if i]
    except Exception as e:  # noqa: BLE001
        log(f"   ℹ️ No footage this time ({type(e).__name__}: {str(e)[:120]}); the gradient stays.")
        return None, []
