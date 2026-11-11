"""YouTube's "Most replayed" graph of a source video, as a guide to its funniest moments.

Owner, 11-nov-2026: Punchline Bazaar's clips were moments nobody watches; "find the best possible shots".
The transcript tells the clip picker what is SAID; the graph tells it what viewers of the original
rewatched, which on a stand-up set is the laugh. yt-dlp hands the graph over with the video's info
(``heatmap``: about 100 points of {start_time, end_time, value 0-1}) for videos with enough views, at no
extra cost (main.download_youtube_video keeps it in main.SOURCE_HEAT).

The start of almost every video is replayed most (people skip back to it), so the first INTRO seconds
are ignored and the rest is rescaled so its hottest point is 1.0. A flat graph says nothing and gives
no heat at all. Used by main.get_viral_clips: window heat raises the scoring pass, the hottest span of a
hot window is named in the detail prompt, and clip heat counts in clip_selection.trim_to_best.
"""

INTRO_SECONDS = 25.0
INTRO_SHARE = 0.04
# The peak must be this many times the median of the graph, or the graph is flat.
FLAT_RATIO = 1.35
# A window at least this hot gets its peak span named in the detail prompt.
HOT = 0.6
# The peak span: the hottest point and its neighbours within this share of it.
SPAN_FLOOR = 0.75


def clean(points, duration=None):
    """[(start, end, value 0-1)] past the intro, rescaled so the hottest is 1.0; [] when missing or flat."""
    pts = []
    for p in points or []:
        try:
            s, e, v = float(p["start_time"]), float(p["end_time"]), float(p["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if e > s and v >= 0:
            pts.append((s, e, v))
    if len(pts) < 10:
        return []
    pts.sort()
    try:
        total = float(duration) if duration else pts[-1][1]
    except (TypeError, ValueError):
        total = pts[-1][1]
    intro = max(INTRO_SECONDS, INTRO_SHARE * total)
    body = [p for p in pts if p[0] >= intro]
    if len(body) < 5:
        return []
    values = sorted(v for _, _, v in body)
    top, median = values[-1], values[len(values) // 2]
    if top <= 0 or top < FLAT_RATIO * max(median, 1e-6):
        return []
    return [(s, e, v / top) for s, e, v in body]


def heat(pts, start, end):
    """0-1: the hottest point overlapping [start, end] (0 without a graph)."""
    return max((v for s, e, v in pts if s < end and e > start), default=0.0)


def peak_span(pts, start, end):
    """(start, end) of the hottest stretch inside [start, end]: its hottest point and the neighbours
    that stay within SPAN_FLOOR of it, clamped to the window. None without heat there."""
    inside = [p for p in pts if p[0] < end and p[1] > start]
    if not inside:
        return None
    i = max(range(len(inside)), key=lambda k: inside[k][2])
    peak = inside[i][2]
    if peak <= 0:
        return None
    lo = hi = i
    while lo > 0 and inside[lo - 1][2] >= SPAN_FLOOR * peak:
        lo -= 1
    while hi < len(inside) - 1 and inside[hi + 1][2] >= SPAN_FLOOR * peak:
        hi += 1
    return max(start, inside[lo][0]), min(end, inside[hi][1])


def hottest(pts, n=3, gap=30.0, floor=HOT):
    """The n hottest moments [(start, end, value)] of at least ``floor``, ``gap`` seconds apart, in time
    order (a flat stretch is not a moment)."""
    out = []
    for p in sorted(pts, key=lambda p: -p[2]):
        if p[2] < floor:
            break
        if all(abs(p[0] - q[0]) >= gap for q in out):
            out.append(p)
        if len(out) >= n:
            break
    return sorted(out)


def clock(seconds):
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"
