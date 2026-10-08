"""Never repeat a moment: which parts of which YouTube videos already became Shorts.

The record lives in ``output/.used_moments.json`` ({video_id: [{start, end, at,
job}]}) and not in the job folders: the retention sweep deletes those after a
day (``app.JOB_RETENTION_SECONDS``), and job folders never stored the source
link anyway. The clip picker gets the used spans of the video it is reading
(``main.get_viral_clips(used=)``): windows mostly made of them are not offered,
and a pick that still lands on one is dropped, so the job finds other moments
instead of remaking yesterday's Short. ``SKIP_USED=0`` turns it off.

Cricket topics and matches are kept in the same file under ``topic:<text>`` so
Autopilot does not make the same idea twice.
"""
import contextlib
import json
import os
import re
import time

PATH = os.environ.get("USED_MOMENTS_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "output", ".used_moments.json")
WINDOW_USED = 0.5   # a scoring window at least half made of old Shorts is not offered
CLIP_USED = 0.3     # a pick that is 30% an old Short is a repeat
_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")


class AllUsedError(RuntimeError):
    def __init__(self):
        super().__init__("Every good part of this video was already made into Shorts. Try another video.")


def enabled():
    return os.environ.get("SKIP_USED", "1").strip() != "0"


def video_id(url):
    m = _ID.search(url or "")
    return m.group(1) if m else None


@contextlib.contextmanager
def _locked():
    # Several job processes finish at once; a lock file keeps one writer.
    lock = PATH + ".lock"
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    deadline = time.time() + 10
    fd = None
    while fd is None:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > 30:   # left by a killed job
                    os.remove(lock)
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                break
            time.sleep(0.1)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
            with contextlib.suppress(OSError):
                os.remove(lock)


def _load():
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, PATH)


def ranges(url):
    """[(start, end)] already made into Shorts from this video."""
    vid = video_id(url)
    if not vid or not enabled():
        return []
    return [(float(r["start"]), float(r["end"])) for r in _load().get(vid, [])]


def covered(start, end, used):
    """Seconds of [start, end] that fall inside the used spans."""
    spans = sorted((max(start, s), min(end, e)) for s, e in used if e > start and s < end)
    total, reach = 0.0, start
    for s, e in spans:
        s = max(s, reach)
        if e > s:
            total += e - s
            reach = e
    return total


def fresh_windows(windows, used):
    if not used:
        return windows
    return [w for w in windows
            if covered(w["start"], w["end"], used) < WINDOW_USED * max(w["end"] - w["start"], 1e-6)]


def fresh_clips(shorts, used):
    if not used:
        return shorts
    return [c for c in shorts
            if covered(float(c.get("start", 0)), float(c.get("end", 0)), used)
            < CLIP_USED * max(float(c.get("end", 0)) - float(c.get("start", 0)), 1e-6)]


def record(url, spans, job=""):
    """Remember these (start, end) spans of ``url`` as used."""
    vid = video_id(url)
    spans = [(round(float(s), 2), round(float(e), 2)) for s, e in spans if float(e) > float(s)]
    if not vid or not spans:
        return
    with _locked():
        data = _load()
        rows = data.setdefault(vid, [])
        for s, e in spans:
            if not any(abs(r["start"] - s) < 1 and abs(r["end"] - e) < 1 for r in rows):
                rows.append({"start": s, "end": e, "at": int(time.time()), "job": job})
        _save(data)


def summary(url):
    """How much of this video is already used: {count, seconds, last}."""
    vid = video_id(url)
    rows = _load().get(vid, []) if vid else []
    return {"count": len(rows),
            "seconds": round(covered(0, 10 ** 7, [(r["start"], r["end"]) for r in rows]), 1),
            "last": max((r.get("at", 0) for r in rows), default=None)}


MOMENT_MIN, MOMENT_MAX, MOMENTS_MAX = 5, 119, 5
# Not inside a longer number: "750-800" is seconds, never "50-80".
_CLOCK = r"(?<![\d:.])\d{1,5}(?::\d{1,2}){0,2}(?:\.\d+)?(?![\d:])"


def _seconds(text):
    parts = [float(x) for x in text.split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def parse_ranges(text):
    """"12:30-13:20, 1:02:05-1:03:00" -> [(750.0, 800.0), (3725.0, 3780.0)].

    The moments the user wants as Shorts (main.manual_clips). Each one 5-119 s,
    at most 5. Raises ValueError with a sentence the dashboard can show."""
    found = re.findall(rf"({_CLOCK})\s*(?:-|–|—|to)\s*({_CLOCK})", text or "")
    if not found:
        raise ValueError("Write each moment as start-end, for example 12:30-13:20.")
    if len(found) > MOMENTS_MAX:
        raise ValueError(f"At most {MOMENTS_MAX} moments in one job.")
    out = []
    for a, b in found:
        s, e = _seconds(a), _seconds(b)
        if not MOMENT_MIN <= e - s <= MOMENT_MAX:
            raise ValueError(f"{a}-{b} must be {MOMENT_MIN} to {MOMENT_MAX} seconds long.")
        out.append((round(s, 2), round(e, 2)))
    return sorted(set(out))


def _topic_key(text):
    return "topic:" + re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def topic_used(text):
    return _topic_key(text) in _load()


def record_topic(text, job=""):
    if not (text or "").strip():
        return
    with _locked():
        data = _load()
        data.setdefault(_topic_key(text), []).append({"start": 0, "end": 0, "at": int(time.time()), "job": job})
        _save(data)
