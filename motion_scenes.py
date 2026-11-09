"""Motion-graphics scenes drawn as ASS vector events, for the money channel (money_shorts.py; owner,
29-oct-2026: a channel of "motion graphics" videos).

Why ASS (research of 29-oct-2026, timed on this laptop with other work holding the CPU at 91-100%): libass
drew a 1080x1920 frame of 10 growing bars, a title and a changing counter in 34 ms, 16 ms more beside the
x264 encode; Pillow anti-aliased took 656 ms a frame and matplotlib 486 ms (about 8.5 min for one Short).
Headless-browser renderers (Remotion, Revideo) do worst on this CPU, and Remotion's licence does not fit
this MIT repo. So every chart is shapes and text through short_kit.render, like the cricket boards.

A scene is one voice line (its window a..b). The model only fills data (money_shorts.Beat); code sorts,
scales, decides winners and computes every ratio and change, so a chart never contradicts its numbers.
Everything sits between BOARD_TOP and cricket_shorts.BOARD_END: the captions hang below. Pictures (flags)
are drawn UNDER the text layer by short_kit.render, so nothing opaque is drawn over a flag's spot.
"""
import math
import os
import re
import zlib

import cricket_shorts as cs
import framed_layout as fl
import short_kit as kit

CX = kit.OUT_W // 2
BOARD_TOP = 520
HEAD_Y = 590                       # each scene's headline
NOTE_Y = cs.BOARD_END - 24         # its source, small, on the board's foot
TEMPLATES = ("big_number", "versus", "bars", "timeline", "list", "grid", "fact")
MIN_ITEMS = {"big_number": 1, "versus": 2, "bars": 3, "timeline": 3, "list": 3, "grid": 1, "fact": 0}
MAX_ITEMS = {"big_number": 2, "versus": 2, "bars": 6, "timeline": 8, "list": 5, "grid": 4, "fact": 1}
TRACK = "&H2B140E&"                # the dark of cricket_shorts.panel, for empty bar tracks
GREY = "#5B6275"
# A colour set per video (by its topic, so a retry keeps it): the same look on every video is what
# YouTube's "made with a template" rule describes (answer/1311392). glow tints the gradient.
PALETTES = (
    {"name": "emerald", "glow": "#0E7C5A", "accent": "#34D399", "hi": "#FFD23F", "third": "#60A5FA"},
    {"name": "cobalt", "glow": "#1D4ED8", "accent": "#38BDF8", "hi": "#FFD23F", "third": "#F472B6"},
    {"name": "plum", "glow": "#7C3AED", "accent": "#C084FC", "hi": "#FDE047", "third": "#34D399"},
    {"name": "copper", "glow": "#C2410C", "accent": "#FB923C", "hi": "#FDE68A", "third": "#38BDF8"},
    {"name": "teal", "glow": "#0F766E", "accent": "#2DD4BF", "hi": "#FFD23F", "third": "#F9A8D4"},
)
POP = cs.POP
DING = cs.RANK_DING


def palette_for(topic):
    return PALETTES[zlib.crc32((topic or "").lower().encode("utf-8")) % len(PALETTES)]


def _c(hex_color):
    return cs._c(hex_color)


def _t(text, limit):
    return cs._txt(text, limit)


# ---------------------------------------------------------------- numbers on screen

_FIRST_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _indian(n):
    """12,34,567: the lakh grouping a number was written in."""
    s = str(int(round(n)))
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + parts + [tail])


def counting(shown, steps=14):
    """The texts a number shows while it counts up to ``shown`` ("$2.3B": $0.4B ... $2.3B): its first
    number climbs fast, then settles, in the decimals and grouping it is written in; the rest stays."""
    m = _FIRST_NUM.search(shown or "")
    if not m:
        return [shown or ""]
    raw = m.group(0)
    target = float(raw.replace(",", ""))
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    indian = bool(re.search(r"\d,\d\d,", raw))
    out = []
    for k in range(1, steps + 1):
        v = target * (1 - (1 - k / steps) ** 3)
        if decimals:
            text = f"{v:,.{decimals}f}" if "," in raw else f"{v:.{decimals}f}"
        elif indian:
            text = _indian(v)
        else:
            text = f"{v:,.0f}" if "," in raw else f"{v:.0f}"
        out.append(shown[:m.start()] + text + shown[m.end():])
    out[-1] = shown
    return out


def count_up(layer, t0, t1, x, y, shown, style, tags="", secs=0.9, steps=14):
    """``shown`` counting up from 0 over ``secs`` at (x, y), then held to t1 after a small pop."""
    texts = counting(shown, steps)
    n = len(texts)
    ev = [kit.dialogue(layer, t0 + secs * k / n, t0 + secs * (k + 1) / n, style, rf"{{\pos({x},{y}){tags}}}{text}")
          for k, text in enumerate(texts[:-1])]
    ev.append(kit.dialogue(layer, t0 + secs * (n - 1) / n, t1, style,
                           rf"{{\pos({x},{y}){tags}\t(0,110,\fscx112\fscy112)\t(110,260,\fscx100\fscy100)}}{texts[-1]}"))
    return ev


_MONEY = (("₹", r"₹|\bINR\b"), ("$", r"\$|\bUSD\b"), ("Rs", r"\bRs\.?|\bPKR\b|\brupees?\b"),
          ("AED", r"\bAED\b|\bdirhams?\b"), ("SAR", r"\bSAR\b|\briyals?\b"), ("£", r"£|\bGBP\b"),
          ("€", r"€|\bEUR\b"), ("¥", r"¥|\bJPY\b|\bCNY\b|\byuan\b"), ("%", r"%"))


def currency(shown):
    """The currency (or %) a shown number is in, by its sign or code; "" for a plain number."""
    for name, pattern in _MONEY:
        if re.search(pattern, shown or "", re.I):
            return name
    return ""


def comparable(items):
    """True when the items' numbers can be set against each other: one currency (or none) for all, and
    "Rs" never across countries (Pakistani and Indian rupees). A first preview compared Rs 45,000 with
    AED 2,500 and called it 18x (29-oct-2026)."""
    kinds = {currency(i.shown) for i in items}
    if len(kinds) > 1:
        return False
    countries = {(getattr(i, "country", "") or "").strip().lower() for i in items} - {""}
    return not (kinds == {"Rs"} and len(countries) > 1)


def change(new, old):
    """How ``new`` compares to ``old``, the way the screen says it: "3.2x" from 1.5 times up, else a
    percentage ("+45%", "-67%"); "" when it cannot be said (no old value)."""
    if not old or old <= 0 or new is None or new < 0:
        return ""
    r = new / old
    if r >= 1.5:
        return f"{r:.1f}".rstrip("0").rstrip(".") + "x"
    pct = (r - 1) * 100
    return f"{pct:+.0f}%" if abs(pct) >= 1 else "0%"


# ---------------------------------------------------------------- drawing pieces

def _shape(layer, t0, t1, drawing, colour, x, y, an=7, alpha="00", extra=""):
    return cs._shape(layer, t0, t1, drawing, colour, at=(round(x), round(y)), alpha=alpha, extra=extra, an=an)


def _poly(points):
    """An ASS drawing of the polygon ``points``, moved so its corner is (0, 0); (drawing, x, y) to place
    it with \\an7: libass aligns a drawing by its box, so coordinates are kept local."""
    x0, y0 = min(p[0] for p in points), min(p[1] for p in points)
    return "m " + " l ".join(f"{px - x0:.0f} {py - y0:.0f}" for px, py in points), x0, y0


def bar(layer, t0, t1, x, y, w, h, colour, at=0.0, ms=600, alpha="00", vertical=False):
    """A rounded bar with its top-left at (x, y) that grows from nothing ``at`` s after t0: left to right,
    or bottom up when ``vertical`` (drawn from its foot)."""
    w, h = max(2, round(w)), max(2, round(h))
    r = max(1, min(w, h) // 2 if not vertical else min(w // 2, 18))
    # The bar appears when it starts to grow: a waiting bar at 1% showed as a sliver.
    grow = rf"\fscy1\t(0,{ms},0.5,\fscy100)" if vertical else rf"\fscx1\t(0,{ms},0.5,\fscx100)"
    if vertical:
        return _shape(layer, t0 + at, t1, fl._round_rect(w, h, r), colour, x, y + h, an=1, alpha=alpha, extra=grow)
    return _shape(layer, t0 + at, t1, fl._round_rect(w, h, r), colour, x, y, an=7, alpha=alpha, extra=grow)


def headline(text, a, b, from_left=False):
    t = _t(text, 34)
    fs = 64 if len(t) <= 20 else 54 if len(t) <= 28 else 46
    x0 = CX + (-cs.SWIPE if from_left else cs.SWIPE)
    return kit.dialogue(4, a, b, "CkStar", rf"{{\an5\move({x0},{HEAD_Y},{CX},{HEAD_Y},0,{cs.SWIPE_MS})\fs{fs}"
                                           rf"\bord0\shad3\fad(0,180)}}{t}")


def note(text, a, b):
    t = _t(text, 44)
    if not t:
        return []
    return [kit.dialogue(4, a + 0.5, b, "CkSmall", rf"{{\an5\pos({CX},{NOTE_Y})\fs28\1c{_c('#AEB4C6')}"
                                                   rf"\bord0\shad0\fad(200,150)}}Source: {t}")]


def backdrop(total, pal):
    """Faint chart-paper lines drifting up behind everything (cricket_shorts._finish adds short_kit's
    soft dots on a Short without footage)."""
    ev = []
    for k in range(-1, 14):
        y = 160 * k
        ev.append(kit.dialogue(0, 0, total, "Shape", rf"{{\an7\move(0,{y + 160},0,{y})\1c{_c(pal['accent'])}"
                                                     rf"\1a&HEC&\bord0\shad0\p1}}m 0 0 l {kit.OUT_W} 0 "
                                                     rf"l {kit.OUT_W} 2 l 0 2{{\p0}}"))
    for k in range(1, 7):
        x = 160 * k - 20
        ev.append(kit.dialogue(0, 0, total, "Shape", rf"{{\an7\pos({x},0)\1c{_c(pal['accent'])}\1a&HF2&\bord0"
                                                     rf"\shad0\p1}}m 0 0 l 2 0 l 2 {kit.OUT_H} l 0 {kit.OUT_H}{{\p0}}"))
    return ev


def _flag(flags, item, height):
    """The path of the item's flag badge of this height, or None."""
    got = (flags or {}).get((getattr(item, "country", "") or "").strip().lower())
    return got.get(height) if got else None


def _img(path, t0, t1, x, y, fade=0.15):
    return {"path": path, "t0": t0, "t1": t1, "x": round(x), "y": round(y), "zoom": 0.0, "fade_in": fade}


# ---------------------------------------------------------------- the templates
# Each returns (events, images, sfx) for one scene in its window a..b.

def big_number(beat, a, b, pal, flags):
    ev, images, sfx = [], [], []
    main = beat.items[0]
    shown = _t(main.shown, 12)
    fs = 210 if len(shown) <= 5 else 170 if len(shown) <= 8 else 130 if len(shown) <= 11 else 110
    ev.append(cs.panel(2, a, b, 50, 650, 980, 520, 48, alpha="38",
                       move=(50 + cs.SWIPE, 650, 50, 650, 0, cs.SWIPE_MS), extra=r"\fad(0,200)"))
    ev += count_up(5, a + 0.3, b, CX, 830, shown, "CkBigC", rf"\an5\fs{fs}\1c{_c(pal['hi'])}\bord0\shad5")
    ev.append(kit.dialogue(4, a + 0.5, b, "CkNote", rf"{{\an5\pos({CX},985)\fs46\bord0\shad2\fad(200,150)}}"
                                                    rf"{_t(main.name, 30)}"))
    ev.append(bar(4, a, b, CX - 260, 1030, 520, 10, _c(pal["hi"]), at=0.55, ms=500))
    sfx.append((POP, 0.35, a + 1.2))
    if len(beat.items) > 1:
        other = beat.items[1]
        ev.append(kit.dialogue(4, a + 1.1, b, "CkName", rf"{{\an5\pos({CX},1085)\fs38\1c{_c('#D8D8E8')}\bord0"
                                                        rf"\fad(200,150)}}{_t(other.name, 18)}: {_t(other.shown, 12)}"))
        said = change(main.value, other.value) if comparable([main, other]) else ""
        if said:
            ev += cs._pill(a + 1.4, b, 1148, said, colour=pal["accent"], layer=5)
            sfx.append((POP, 0.3, a + 1.4))
    return ev, images, sfx


def versus(beat, a, b, pal, flags):
    ev, images, sfx = [], [], []
    left, right = beat.items[:2]
    lower = (beat.better or "").lower() == "lower"
    same = comparable([left, right])          # else no winner, no ratio and bars of one height
    if not same or left.value == right.value:
        win = -1
    else:
        win = 0 if (left.value < right.value) == lower else 1
    top_v = max(left.value, right.value, 1e-9)
    base, tall, w = 1105, 320, 230
    for k, (item, x) in enumerate(((left, 300), (right, 780))):
        h = (max(0.06, item.value / top_v) if same and item.value > 0 else 0.7 if not same else 0.06) * tall
        colour = _c(pal["hi"]) if k == win else _c(pal["accent"])
        ev.append(bar(3, a, b, x - w // 2, base - h, w, h, colour, at=0.25 + 0.15 * k, ms=650, vertical=True))
        ev += count_up(5, a + 0.9 + 0.15 * k, b, x, round(base - h - 42), _t(item.shown, 12), "CkBigC",
                       rf"\an5\fs{64 if len(_t(item.shown, 12)) <= 7 else 50}\1c&HFFFFFF&\bord0\shad3", secs=0.6)
        name = _t(item.name, 18)
        fs = 40 if len(name) <= 10 else 34 if len(name) <= 14 else 28
        flag = _flag(flags, item, 44)
        if flag:
            images.append(_img(flag, a + 0.2, b, x - 130, 1158))
            ev.append(kit.dialogue(4, a + 0.2, b, "CkName", rf"{{\an4\pos({x - 86},1158)\fs{fs}\bord0\shad2"
                                                            rf"\fad(150,150)}}{name}"))
        else:
            ev.append(kit.dialogue(4, a + 0.2, b, "CkName", rf"{{\an5\pos({x},1158)\fs{fs}\bord0\shad2"
                                                            rf"\fad(150,150)}}{name}"))
    ev.append(kit.dialogue(4, a + 0.1, b, "CkVs", rf"{{\an5\pos({CX},{base - 150})\fs90\fscx160\fscy160"
                                                  rf"\t(0,220,\fscx100\fscy100)\fad(0,150)}}VS"))
    hi, lo = max(left.value, right.value), min(left.value, right.value)
    said = change(hi, lo) if win >= 0 else ""
    if said:
        # The ratio names the BIGGER value, whichever wins: with a cheaper price as the "winner" the first live
        # Short read "JAN 2005: 9.4x" for a price that was 9.4 times lower (29-oct-2026).
        bigger = left if left.value >= right.value else right
        ev += cs._pill(a + 1.7, b, 668, f"{_t(bigger.name, 14).upper()}: {said}", colour=pal["hi"], layer=6)
        sfx.append((POP, 0.4, a + 1.7))
    return ev, images, sfx


def bars(beat, a, b, pal, flags):
    ev, images, sfx = [], [], []
    subject = beat.items[0]
    items = sorted(beat.items, key=lambda i: -i.value)
    n = len(items)
    pitch = min(96, 540 // n)
    top_v = max((i.value for i in items), default=1) or 1
    with_flags = any(_flag(flags, i, 36) for i in items)
    x0 = 150 if with_flags else 70
    width = 1010 - x0
    for k, item in enumerate(items):
        y = 662 + k * pitch
        colour = _c(pal["hi"]) if item is subject else _c(pal["accent"])
        at = 0.25 + k * min(0.22, max(0.08, (b - a - 1.6) / n))
        ev.append(_shape(2, a, b, fl._round_rect(width, 40, 20), TRACK, x0, y + 22, alpha="50", extra=r"\fad(150,150)"))
        ev.append(bar(3, a, b, x0, y + 22, max(0.03, item.value / top_v) * width, 40, colour, at=at, ms=550))
        ev.append(kit.dialogue(4, a + at, b, "CkName", rf"{{\an4\pos({x0},{y})\fs32\bord0\shad2\fad(150,150)}}"
                                                       rf"{_t(item.name, 22)}"))
        ev += count_up(5, a + at + 0.2, b, 1010, y, _t(item.shown, 12), "CkBigC",
                       rf"\an6\fs44\1c{colour}\bord0\shad2", secs=0.5, steps=8)
        flag = _flag(flags, item, 36)
        if flag:
            images.append(_img(flag, a + at, b, 96, y + 42))
    sfx.append((POP, 0.3, a + 0.4))
    return ev, images, sfx


def timeline(beat, a, b, pal, flags):
    ev, images, sfx = [], [], []
    pts = beat.items
    n = len(pts)
    # The top leaves room for the highest point's label under the change pill at 668.
    left, right, top, bottom = 130, 970, 790, 1095
    vals = [p.value for p in pts]
    lo = 0.0 if min(vals) <= 0.35 * max(vals) else min(vals) * 0.8
    hi_v = max(vals) * 1.06 if max(vals) > lo else lo + 1

    def xy(k, v):
        return (left + (right - left) * k / max(1, n - 1), bottom - (bottom - top) * (v - lo) / (hi_v - lo))
    coords = [xy(k, v) for k, v in enumerate(vals)]
    draw_ms = round(min(1800, max(900, (b - a - 1.2) * 1000)))
    reveal = (rf"\clip({left - 30},{top - 60},{left - 29},{bottom + 4})"
              rf"\t(250,{250 + draw_ms},\clip({left - 30},{top - 60},{right + 40},{bottom + 4}))")
    # The baseline, then the area under the line, the line in pieces and a dot on every point.
    ev.append(_shape(2, a, b, "m 0 0 l 860 0 l 860 3 l 0 3", _c("#FFFFFF"), left, bottom + 2, alpha="A0",
                     extra=r"\fad(150,150)"))
    area, ax, ay = _poly([(left, bottom)] + coords + [(right, bottom)])
    ev.append(_shape(2, a, b, area, _c(pal["accent"]), ax, ay, alpha="B4", extra=reveal))
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1
        nx, ny = -dy / length * 5, dx / length * 5
        seg, sx, sy = _poly([(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)])
        ev.append(_shape(3, a, b, seg, _c(pal["hi"]), sx, sy, extra=reveal))
    for k, ((x, y), p) in enumerate(zip(coords, pts)):
        at = a + 0.25 + draw_ms / 1000 * k / max(1, n - 1)
        ev.append(_shape(4, at, b, fl._circle(9), _c(pal["hi"]), x, y, an=5,
                         extra=r"\fscx40\fscy40\t(0,160,\fscx130\fscy130)\t(160,300,\fscx100\fscy100)"))
        if n <= 6 or k in (0, n - 1) or k % 2 == 0:
            ev.append(kit.dialogue(4, at, b, "CkSmall", rf"{{\an8\pos({round(x)},{bottom + 14})\fs26\bord0\shad0"
                                                        rf"\1c{_c('#C9CEDC')}\fad(150,150)}}{_t(p.name, 9)}"))
        if k in (0, n - 1) or p.value == max(vals):
            big = k == n - 1
            ev.append(kit.dialogue(5, at + 0.1, b, "CkBigC",
                                   rf"{{\an2\pos({round(x)},{round(y) - 16})\fs{56 if big else 40}\bord0\shad3"
                                   rf"\1c{_c(pal['hi'] if big else '#FFFFFF')}\fscx60\fscy60"
                                   rf"\t(0,200,\fscx100\fscy100)}}{_t(p.shown, 12)}"))
    said = change(vals[-1], vals[0])
    if said:
        ev += cs._pill(a + 0.25 + draw_ms / 1000 + 0.2, b, 668, f"{_t(pts[0].name, 9)} SE {said}",
                       colour=pal["hi"], layer=6)
        sfx.append((POP, 0.4, a + 0.45 + draw_ms / 1000))
    # The newest point keeps pulsing: where the story is now.
    lx, ly = coords[-1]
    ev.append(_shape(3, a + 0.3 + draw_ms / 1000, b, fl._circle(22), _c(pal["hi"]), lx, ly, an=5, alpha="90",
                     extra=r"\t(0,700,\fscx180\fscy180\1a&HFF&)"))
    return ev, images, sfx


def ranked(beat, a, b, pal, flags):
    """A countdown board: rows #n..#1 revealed in turn during the line, #1 last with a bell."""
    ev, images, sfx = [], [], []
    lower = (beat.better or "").lower() == "lower"
    items = sorted(beat.items, key=lambda i: i.value if lower else -i.value)[:5]
    n = len(items)
    pitch, h = 110, 86
    y0 = 1180 - (n - 1) * pitch - h // 2 - 4
    with_flags = any(_flag(flags, i, 40) for i in items)
    # A flag sits left of its row's track: anything drawn over a picture dims it.
    track_x = 200 if with_flags else 110
    track_w = 1010 - track_x
    span = max(0.6, b - a - 0.9)
    for rank, item in enumerate(items, 1):
        y = y0 + (rank - 1) * pitch
        at = a + 0.3 + span * (n - rank) / max(1, n - 1) * (0.85 if n > 1 else 0)
        if rank == 1:
            ev.append(_shape(1, at, b, fl._round_rect(track_w + 12, h + 12, (h + 12) // 2), _c(pal["hi"]),
                             track_x - 6, y - h // 2 - 6, extra=r"\fad(150,0)"))
            sfx.append((DING, 0.6, at + 0.1))
        else:
            sfx.append((kit.WHOOSH, 0.25, max(a, at - 0.1)))
        ev.append(_shape(2, a, b, fl._round_rect(track_w, h, h // 2), TRACK, track_x, y - h // 2, alpha="38",
                         extra=r"\fad(150,150)"))
        ev.append(_shape(3, a, b, fl._circle(36), _c(pal["hi"] if rank == 1 else pal["accent"]), 64, y, an=5,
                         extra=r"\fad(150,150)"))
        ev.append(kit.dialogue(4, a, b, "CkBadgeDark", rf"{{\an5\pos(64,{y})\fs52\fad(150,150)}}{rank}"))
        ev.append(kit.dialogue(4, a, at + 0.05, "CkNote",
                               rf"{{\an5\pos({track_x + track_w // 2},{y})\fs56\alpha&H70&}}?"))
        x_name = track_x + 30
        flag = _flag(flags, item, 40)
        if flag:
            images.append(_img(flag, at, b, 150, y))
        pop = r"\fscx70\fscy70\t(0,200,\fscx100\fscy100)"
        ev.append(kit.dialogue(4, at, b, "CkName", rf"{{\an4\pos({x_name},{y})\fs{38 if len(item.name) <= 14 else 32}"
                                                   rf"\bord0\shad2{pop}}}{_t(item.name, 20)}"))
        ev.append(kit.dialogue(5, at + 0.1, b, "CkBigC",
                               rf"{{\an6\pos(990,{y})\fs{56 if len(item.shown) <= 7 else 44}\bord0\shad3"
                               rf"\1c{_c(pal['hi'] if rank == 1 else '#FFFFFF')}{pop}}}{_t(item.shown, 12)}"))
    return ev, images, sfx


def grid(beat, a, b, pal, flags):
    """Groups out of 100 (or 10) as a grid of dots filling group by group, with a legend."""
    ev, images, sfx = [], [], []
    groups = [i for i in beat.items if i.value > 0][:4]
    counts = [max(0, round(i.value)) for i in groups]
    total = 10 if sum(counts) <= 10 and all(float(i.value).is_integer() for i in groups) else 100
    counts = counts[:]
    colours = [pal["hi"], pal["accent"], pal["third"], "#F8FAFC"]
    cells = []
    for g, c in enumerate(counts):
        cells += [g] * c
    cells = (cells + [-1] * total)[:total]
    if total == 100:
        pitch, rad, gx, gy, cols = 52, 19, 96, 690, 10
    else:
        pitch, rad, gx, gy, cols = 108, 40, CX - 2 * 108, 760, 5
    fill_ms = 1300
    for k, g in enumerate(cells):
        x, y = gx + (k % cols) * pitch, gy + (k // cols) * pitch
        ev.append(_shape(2, a, b, fl._circle(rad), _c(GREY), x, y, an=5, alpha="40", extra=r"\fad(150,150)"))
        if g >= 0:
            at = 0.3 + fill_ms / 1000 * k / max(1, total - 1)
            ev.append(_shape(3, a + at, b, fl._circle(rad), _c(colours[g]), x, y, an=5,
                             extra=r"\fscx30\fscy30\t(0,140,\fscx100\fscy100)"))
    lx = 660 if total == 100 else 700
    for g, (item, c) in enumerate(zip(groups, counts)):
        y = 720 + g * 120 if total == 100 else 1000 + g * 56
        if total == 10:
            lx = 160
        at = a + 0.3 + fill_ms / 1000 * (sum(counts[:g]) + c / 2) / total
        ev.append(_shape(4, at, b, fl._circle(16), _c(colours[g]), lx, y, an=5, extra=r"\fad(120,150)"))
        ev.append(kit.dialogue(4, at, b, "CkBigC", rf"{{\an4\pos({lx + 30},{y - (16 if total == 100 else 0)})"
                                                   rf"\fs{52 if total == 100 else 40}\bord0\shad2\1c{_c(colours[g])}"
                                                   rf"\fad(120,150)}}{_t(item.shown, 10)}"))
        if total == 100:
            ev.append(kit.dialogue(4, at, b, "CkSmall", rf"{{\an4\pos({lx + 30},{y + 30})\fs28\bord0\shad0"
                                                        rf"\fad(120,150)}}{_t(item.name, 18)}"))
        else:
            ev.append(kit.dialogue(4, at, b, "CkSmall", rf"{{\an4\pos({lx + 190},{y})\fs30\bord0\shad0"
                                                        rf"\fad(120,150)}}{_t(item.name, 22)}"))
    sfx.append((POP, 0.3, a + 0.3 + fill_ms / 1000))
    return ev, images, sfx


def fact(beat, a, b, pal, flags):
    """One striking fact: its number slams in like a stamp, the words below it."""
    ev, images, sfx = [], [], []
    ev.append(cs.panel(2, a, b, 50, 650, 980, 520, 48, alpha="38",
                       move=(50 - cs.SWIPE, 650, 50, 650, 0, cs.SWIPE_MS), extra=r"\fad(0,200)"))
    words = _t(beat.headline, 34)
    if beat.items:
        stamp = _t(beat.items[0].shown, 12)
        fs = 190 if len(stamp) <= 6 else 140 if len(stamp) <= 9 else 110
        w = min(900, round(len(stamp) * fs * 0.5 + 120))
        # The stamp's frame is only its outline: the fill stays clear (\1a), the border fades in (\3a).
        ev.append(kit.dialogue(3, a + 0.35, b, "Shape",
                               rf"{{\an5\pos({CX},840)\1a&HFF&\3c{_c(pal['hi'])}\3a&HFF&\bord8\shad0\frz-5"
                               rf"\fscx260\fscy260\t(0,200,\fscx100\fscy100\3a&H00&)\p1}}"
                               rf"{fl._round_rect(w, fs + 70, 28)}{{\p0}}"))
        ev.append(kit.dialogue(5, a + 0.35, b, "CkBigC",
                               rf"{{\an5\pos({CX},840)\fs{fs}\bord0\shad4\1c{_c(pal['hi'])}\frz-5\fscx260\fscy260"
                               rf"\alpha&HFF&\t(0,200,\fscx100\fscy100\alpha&H00&)}}{stamp}"))
        sfx.append((POP, 0.5, a + 0.5))
        text, y, fs_text = _wrap(words, 24), 1040, 50
    else:
        # No number: the words are the picture (the voice line is already in the captions).
        text, y, fs_text = _wrap(words, 16), 880, 76
    ev.append(kit.dialogue(4, a + 0.6 if beat.items else a + 0.2, b, "CkNote",
                           rf"{{\an5\pos({CX},{y})\fs{fs_text}\bord0\shad2\fscx90\fscy90\t(0,220,\fscx100\fscy100)"
                           rf"\fad(200,150)}}{text}"))
    return ev, images, sfx


def _wrap(text, width):
    """``text`` in at most 3 lines of about ``width`` characters, as even as they come: a greedy wrap
    left "to" alone on a line ("The deal Yahoo said no / to")."""
    words = (text or "").split()
    if len(" ".join(words)) <= width or len(words) < 2:
        return " ".join(words)
    best = None
    for n in (2, 3):
        for cuts in ([(i,) for i in range(1, len(words))] if n == 2 else
                     [(i, j) for i in range(1, len(words)) for j in range(i + 1, len(words))]):
            parts = [" ".join(words[a:b]) for a, b in zip((0,) + cuts, cuts + (len(words),))]
            score = (max(len(p) for p in parts) > width, n, max(len(p) for p in parts))
            if best is None or score < best[0]:
                best = (score, parts)
        if best and not best[0][0]:
            break
    return r"\N".join(best[1])


DRAW = {"big_number": big_number, "versus": versus, "bars": bars, "timeline": timeline, "list": ranked,
        "grid": grid, "fact": fact}


# ---------------------------------------------------------------- the whole Short

def hook_poster(script, b, pal, flags):
    """Frame 0, the one the feed shows while people decide: the hook's number huge and the hook in
    words, both at full strength from the first frame (no fade from nothing)."""
    ev = []
    number = _t(script.hook_number, 12)
    if number:
        fs = 230 if len(number) <= 5 else 190 if len(number) <= 8 else 150
        ev.append(kit.dialogue(4, 0, b, "CkBigC", rf"{{\an5\pos({CX},740)\fs{fs}\bord0\shad0\blur14"
                                                  rf"\1c{_c(pal['accent'])}\alpha&H70&}}{number}"))
        ev.append(kit.dialogue(5, 0, b, "CkBigC", rf"{{\an5\pos({CX},740)\fs{fs}\bord0\shad6\1c{_c(pal['hi'])}"
                                                  rf"\t(0,260,\fscx106\fscy106)\t(260,520,\fscx100\fscy100)"
                                                  rf"\fad(0,180)}}{number}"))
        ev += cs.hook_card(script.hook_line, 0, b, y=1010, size=78)
    else:
        ev += cs.hook_card(script.hook_line, 0, b, y=860)
    return ev


def payoff(script, a, b, pal):
    """The biggest number of the story, last: rays turning behind it, counting up, a bell."""
    ev = []
    # Each ray is drawn from (0, 0) and placed by its foot (\an2): libass aligns a drawing by its box.
    for k in range(12):
        ev.append(kit.dialogue(1, a, b, "Shape",
                               rf"{{\an2\pos({CX},780)\org({CX},780)\frz{k * 30}\t(0,{round((b - a) * 1000)},"
                               rf"\frz{k * 30 + 25})\clip(0,{BOARD_TOP - 40},{kit.OUT_W},{cs.BOARD_END})"
                               rf"\1c{_c(pal['hi'])}\1a&HE4&\bord0\shad0\fad(250,200)\p1}}"
                               rf"m 0 0 l 92 0 l 60 440 l 32 440{{\p0}}"))
    shown = _t(script.payoff_shown, 12)
    if not shown:
        # The number gate dropped the payoff's number: the verdict in words, never a label with nothing.
        ev.append(kit.dialogue(5, a + 0.2, b, "CkStar", rf"{{\an5\pos({CX},860)\fs66\bord0\shad4\fscx85\fscy85"
                                                        rf"\t(0,220,\fscx100\fscy100)}}{_wrap(_t(script.verdict_line, 90), 20)}"))
        return ev
    fs = 220 if len(shown) <= 5 else 170 if len(shown) <= 8 else 130
    ev += count_up(5, a + 0.2, b, CX, 800, shown, "CkBigC", rf"\an5\fs{fs}\1c{_c(pal['hi'])}\bord0\shad6", secs=1.0)
    ev.append(kit.dialogue(4, a + 0.5, b, "CkStar", rf"{{\an5\pos({CX},990)\fs52\bord0\shad3\fad(200,150)}}"
                                                    rf"{_t(script.payoff_label, 32)}"))
    return ev


def events(script, windows, body_end, handle, pal, flags=None):
    """(events, images, sfx) for the whole Short: windows are hook, one per beat, the payoff, the question."""
    import types
    ev = backdrop(body_end, pal)
    ev += cs.topic_frame_events(types.SimpleNamespace(kicker=_t(script.kicker, 22) or "MONEY", title=script.title),
                                body_end, handle)
    images, sfx = [], []
    n = len(script.beats)
    for k, a, b in windows:
        if k == 0:
            ev += hook_poster(script, b, pal, flags)
            continue
        if k <= n:
            beat = script.beats[k - 1]
            ev.append(cs._flash(a))
            ev.append(headline(beat.headline, a, b, from_left=k % 2 == 0))
            got, pics, sounds = DRAW[beat.template](beat, a, b, pal, flags)
            ev += got + note(beat.note, a, b)
            images += pics
            sfx += [(kit.WHOOSH, 0.3, max(0.0, a - 0.15))] + sounds
        elif k == n + 1:
            ev.append(cs._flash(a))
            ev += payoff(script, a, b, pal)
            sfx += [(kit.WHOOSH, 0.3, max(0.0, a - 0.15)), (DING, 0.6, a + 1.2)]
        else:
            ev += cs._pill(a, body_end, 760, "AAPKI RAAYE?", colour=pal["hi"], layer=6)
            ev.append(kit.dialogue(6, a + 0.1, body_end, "CkText", rf"{{\an5\pos({CX},940)\1c{_c(pal['hi'])}"
                                                                   rf"\fad(200,200)}}{_t(script.question, 110)}"))
            sfx.append((kit.WHOOSH, 0.3, max(0.0, a - 0.15)))
    return ev, images, sfx


# ---------------------------------------------------------------- flags

def flag_badges(beats, out_dir):
    """{country: {height: path}}: each country's flag (flags.fetch: Wikipedia, public domain, cached) as
    small rounded badges for the rows (36, 40, 44 px tall) and a bigger one (64). Never raises."""
    from PIL import Image, ImageDraw
    import flags as flag_files
    out = {}
    for beat in beats:
        for item in beat.items:
            name = (getattr(item, "country", "") or "").strip()
            if not name or name.lower() in out:
                continue
            try:
                src = flag_files.fetch(name)
                if not src:
                    continue
                badges = {}
                with Image.open(src) as im:
                    im = im.convert("RGBA")
                    for height in (36, 40, 44, 64):
                        w = max(8, round(im.width * height / im.height))
                        w = min(w, round(height * 1.9))
                        small = im.resize((w, height), Image.LANCZOS)
                        frame = Image.new("RGBA", (w + 4, height + 4), (255, 255, 255, 235))
                        frame.alpha_composite(small, (2, 2))
                        mask = Image.new("L", frame.size, 0)
                        ImageDraw.Draw(mask).rounded_rectangle((0, 0, frame.width - 1, frame.height - 1),
                                                               radius=max(4, height // 6), fill=255)
                        frame.putalpha(mask)
                        path = os.path.join(out_dir, f"flag_{flag_files._slug(name)}_{height}.png")
                        frame.save(path)
                        badges[height] = path
                out[name.lower()] = badges
            except Exception as e:  # noqa: BLE001 — a row without its flag is still a row
                print(f"   ℹ️ No flag for {name} ({type(e).__name__}).")
    return out
