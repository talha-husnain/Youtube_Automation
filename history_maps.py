"""Animated empire maps for the history documentaries.

A scene can show one polity's territory changing over the years (the Ottoman Empire 1305 -> 1683,
the Mughal Empire 1529 -> 1707) with the year counting up in a corner: one 16:9 shot, frames
piped to ffmpeg the way parallax.py does it, so history_videos can join it with the other shots.

Data (outside the repo, ``HISTORY_MAPS_DIR``, default D:\\youtube\\oss\\maps):
- Cliopatria v0.2.1 (Seshat Global History Databank, CC BY 4.0, Bennett et al. 2025, Scientific
  Data 12:247): ~13.8k rows, one per polity per period (Name, FromYear, ToYear inclusive,
  polygons in EPSG:4326). Names in parentheses are composites, e.g. "(Delhi Sultanate)" is the
  union of its dynasties; "RELATION" rows (allegiances, vassalage) are left out.
- Natural Earth 50m land (public domain) for the background.
``python history_maps.py build <cliopatria.geojson.zip> <ne_50m_land.geojson>`` turns the
173 MB GeoJSON into ``cliopatria.npz`` + ``land.npz`` once (points thinned to one per 0.01 degree
cell, ~1 km), which load in a fraction of a second at render time.

Only numpy + Pillow (+ cv2 for the slow push-in when it is installed): no shapely/geopandas.
``HISTORY_MAPS=0`` turns it off.
"""

import difflib
import json
import math
import os
import re
import subprocess
import sys
import time
import unicodedata
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(HERE, "fonts")
DEFAULT_DIR = os.path.join(os.path.dirname(HERE), "oss", "maps")
POLITIES_FILE = "cliopatria.npz"
LAND_FILE = "land.npz"
SNAP = 0.01            # degrees: one kept point per grid cell when building the cache
SLACK_YEARS = 10       # a start this far before the first row shows the first row (rows start
                       # on round-ish years: Mughal data begins 1529, Panipat was 1526)
CREDIT = ("Map data: Cliopatria, Seshat Global History Databank (Bennett et al. 2025, Scientific Data "
          "12:247), CC BY 4.0 (creativecommons.org/licenses/by/4.0), borders simplified; "
          "land: Natural Earth (public domain).")

# Look: dark navy sea, dark slate land, the polity in gold with a glow.
SEA_IN, SEA_OUT = (18, 44, 82), (6, 15, 34)
GRID = (36, 64, 104)
LAND = (46, 52, 62)      # lighter than the sea everywhere: the first try (31,39,51) lost the Mediterranean
COAST = (98, 114, 136)
FILL_IN, FILL_EDGE = (186, 134, 36), (242, 192, 84)
EDGE = (255, 226, 150)
GLOW = (255, 170, 40)
TEXT = (247, 241, 226)
GOLD = (236, 184, 72)
ZOOM = 0.05            # slow push-in over the shot (cv2 only)
FADE_SECONDS = 0.3     # crossfade between two periods

GENERIC = {"the", "of", "and", "empire", "dynasty", "kingdom", "sultanate", "caliphate", "khanate",
           "emirate", "state", "republic", "great", "principality", "confederacy", "confederation",
           "realm", "rule", "period", "era", "polity", "a"}


def data_dir():
    return os.environ.get("HISTORY_MAPS_DIR", "").strip() or DEFAULT_DIR


def available():
    if os.environ.get("HISTORY_MAPS", "1").strip() == "0":
        return False
    d = data_dir()
    return os.path.isfile(os.path.join(d, POLITIES_FILE)) and os.path.isfile(os.path.join(d, LAND_FILE))


def _say(msg):
    try:
        print(f"   {msg}")
    except Exception:  # noqa: BLE001  (a console that cannot print must not fail a render)
        pass


# ----------------------------------------------------------------------------------------------
# Building the cache (once, from the downloaded GeoJSON)

def _features(path):
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            inner = next(n for n in z.namelist() if n.lower().endswith((".geojson", ".json")))
            data = json.loads(z.read(inner))
    else:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    return data.get("features") or []


def _rings(geom):
    """(coordinates, is_hole) for every ring of a Polygon/MultiPolygon, exterior first."""
    geom = geom or {}
    c = geom.get("coordinates") or []
    polys = [c] if geom.get("type") == "Polygon" else c if geom.get("type") == "MultiPolygon" else []
    for poly in polys:
        for i, ring in enumerate(poly):
            yield ring, i > 0


def _thin(ring, snap):
    """The ring as float32 (n, 2) lon/lat snapped to a ``snap`` grid, repeats dropped, open; None
    if < 3 points. Snapped, not "first point per cell": two provinces sharing a border walk it in
    opposite directions, so keeping each cell's first original point gave them different vertices
    and the Ottoman Empire showed hairline seams between its provinces (22-oct-2026)."""
    try:
        a = np.asarray(ring, dtype=np.float64)[:, :2]
    except (ValueError, IndexError, TypeError):
        try:
            a = np.asarray([p[:2] for p in ring], dtype=np.float64)
        except Exception:  # noqa: BLE001
            return None
    if a.ndim != 2 or len(a) < 3 or not np.isfinite(a).all():
        return None
    if snap > 0:
        q = np.round(a / snap)
        keep = np.ones(len(a), bool)
        keep[1:] = np.any(q[1:] != q[:-1], axis=1)
        a = q[keep] * snap
    if len(a) > 1 and np.all(a[0] == a[-1]):
        a = a[:-1]
    return a.astype(np.float32) if len(a) >= 3 else None


def _pack(rings):
    pts = [r for r, _ in rings]
    off = np.zeros(len(pts) + 1, np.int64)
    off[1:] = np.cumsum([len(r) for r in pts])
    allp = np.concatenate(pts).astype(np.float32) if pts else np.zeros((0, 2), np.float32)
    hole = np.array([h for _, h in rings], np.uint8)
    bbox = np.array([[r[:, 0].min(), r[:, 1].min(), r[:, 0].max(), r[:, 1].max()] for r in pts],
                    np.float32).reshape(-1, 4)
    return allp, off, hole, bbox


def _save(path, arrays):
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        np.savez_compressed(fh, **arrays)
    os.replace(tmp, path)


def build(cliopatria, land, out_dir=None, snap=SNAP):
    """Write cliopatria.npz and land.npz into ``out_dir`` (default data_dir()). Returns the dir."""
    out_dir = out_dir or data_dir()
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for f in _features(cliopatria):
        p = f.get("properties") or {}
        if str(p.get("Type") or "POLITY").upper() != "POLITY":
            continue
        name = str(p.get("Name") or "").strip()
        try:
            fy, ty = int(p["FromYear"]), int(p["ToYear"])
        except (KeyError, TypeError, ValueError):
            continue
        rings = [(r, h) for ring, h in _rings(f.get("geometry")) for r in [_thin(ring, snap)] if r is not None]
        if not name or not any(not h for _, h in rings):
            continue
        rows.append((name, min(fy, ty), max(fy, ty), float(p.get("Area") or 0.0),
                     str(p.get("Wikipedia") or "").replace("_", " ").strip(), rings))
    names = sorted({r[0] for r in rows})
    idx = {n: i for i, n in enumerate(names)}
    rows.sort(key=lambda r: (idx[r[0]], r[1]))
    rec_name = np.array([idx[r[0]] for r in rows], np.int32)
    by_name = {}     # the most used Wikipedia phrase per name: a second spelling for find()
    for r in rows:
        if r[4]:
            by_name.setdefault(r[0], {}).setdefault(r[4], 0)
            by_name[r[0]][r[4]] += 1
    wikis = [max(by_name[n].items(), key=lambda kv: kv[1])[0] if n in by_name else "" for n in names]
    pts, off, hole, bbox = _pack([x for r in rows for x in r[5]])
    rec_ring = np.zeros(len(rows) + 1, np.int64)
    rec_ring[1:] = np.cumsum([len(r[5]) for r in rows])
    _save(os.path.join(out_dir, POLITIES_FILE), {
        "names": np.array(names, dtype=str), "wiki": np.array(wikis, dtype=str),
        "name_rec": np.searchsorted(rec_name, np.arange(len(names) + 1)).astype(np.int64),
        "rec_from": np.array([r[1] for r in rows], np.int32), "rec_to": np.array([r[2] for r in rows], np.int32),
        "rec_area": np.array([r[3] for r in rows], np.float32), "rec_ring": rec_ring,
        "ring_off": off, "ring_hole": hole, "ring_bbox": bbox, "pts": pts, "snap": np.float32(snap)})
    land_rings = [(r, h) for f in _features(land) for ring, h in _rings(f.get("geometry"))
                  for r in [_thin(ring, snap)] if r is not None]
    pts, off, hole, bbox = _pack(land_rings)
    _save(os.path.join(out_dir, LAND_FILE), {"ring_off": off, "ring_hole": hole, "ring_bbox": bbox, "pts": pts})
    return out_dir


# ----------------------------------------------------------------------------------------------
# Loading + finding a polity

_CACHE = {}


def _load(fname):
    path = os.path.join(data_dir(), fname)
    key = (path, os.stat(path).st_mtime_ns)
    if key not in _CACHE:
        with np.load(path, allow_pickle=False) as z:
            _CACHE[key] = {k: z[k] for k in z.files}
    return _CACHE[key]


def _tokens(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    out = []
    for t in re.findall(r"[a-z0-9]+", s):
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]      # Mughals -> mughal, Abbasids -> abbasid
        out.append(t)
    return out


def _split(s):
    toks = _tokens(s)
    return [t for t in toks if t not in GENERIC], {t for t in toks if t in GENERIC}, " ".join(toks)


def _score(q, c):
    q_core, q_gen, q_all = q
    c_core, c_gen, c_all = c
    if q_all and q_all == c_all:
        return 1.2
    if not q_core or not c_core:
        return 0.0
    used, total = set(), 0.0
    for qt in q_core:
        best, bi = 0.0, None
        for i, ct in enumerate(c_core):
            r = 1.0 if qt == ct else difflib.SequenceMatcher(None, qt, ct).ratio()
            if r > best:
                best, bi = r, i
        if best < 0.8:
            return 0.0
        total += best
        used.add(bi)
    gen = len(q_gen & c_gen) / max(1, len(q_gen | c_gen))
    return total / len(q_core) - 0.1 * (len(c_core) - len(used)) + 0.1 * gen


def find(query):
    """The best Cliopatria name for ``query`` ("Mughals", "Ottoman Empire", "delhi sultanate"),
    or None when nothing is close. Ties go to the larger polity (the composite "(Holy Roman
    Empire)" over its member, the Roman Empire over the Roman Kingdom)."""
    try:
        if not query or not str(query).strip():
            return None
        db = _load(POLITIES_FILE)
        q = _split(query)
        best, best_key = None, (0.79, 0.0)
        areas = db["rec_area"]
        nr = db["name_rec"]
        for i, (n, w) in enumerate(zip(db["names"], db["wiki"])):
            s = max(_score(q, _split(n)), _score(q, _split(w)) if w else 0.0)
            if s <= 0.79:
                continue
            key = (round(s, 3), float(areas[nr[i]:nr[i + 1]].max()) if nr[i + 1] > nr[i] else 0.0)
            if key > best_key:
                best, best_key = str(n), key
        return best
    except Exception as e:  # noqa: BLE001
        _say(f"History map lookup failed ({type(e).__name__}: {str(e)[:80]}).")
        return None


def span(name):
    """(first FromYear, last ToYear) in the data for an exact name or a query, else None."""
    try:
        db = _load(POLITIES_FILE)
        i = _index(db, name)
        if i is None:
            return None
        r0, r1 = db["name_rec"][i], db["name_rec"][i + 1]
        return int(db["rec_from"][r0:r1].min()), int(db["rec_to"][r0:r1].max())
    except Exception:  # noqa: BLE001
        return None


def _index(db, name):
    names = db["names"]
    hit = np.nonzero(names == str(name))[0]
    if len(hit):
        return int(hit[0])
    alt = find(name)
    if alt is None:
        return None
    hit = np.nonzero(names == alt)[0]
    return int(hit[0]) if len(hit) else None


# ----------------------------------------------------------------------------------------------
# Drawing

class _View:
    """Equirectangular with cos(latitude) scaling, fitted to a lon/lat box with margins."""

    def __init__(self, box, size, shift):
        lon0, lat0, lon1, lat1 = box
        W, H = size
        self.shift = shift
        self.latc = (lat0 + lat1) / 2
        self.lonc = (lon0 + lon1) / 2
        self.k = max(0.25, math.cos(math.radians(self.latc)))
        ml, mr, mt, mb = 0.07 * W, 0.07 * W, 0.17 * H, 0.11 * H
        iw, ih = W - ml - mr, H - mt - mb
        w, h = max((lon1 - lon0) * self.k, 1e-6), max(lat1 - lat0, 1e-6)
        # Never closer than ~12 degrees across: a small polity still shows where it is.
        self.s = min(iw / w, ih / h, W / (12.0 * self.k))
        self.cx, self.cy = ml + iw / 2, mt + ih / 2
        self.lon_l = self.lonc - self.cx / (self.k * self.s)
        self.lon_r = self.lonc + (W - self.cx) / (self.k * self.s)
        self.lat_t = self.latc + self.cy / self.s
        self.lat_b = self.latc - (H - self.cy) / self.s

    def xy(self, a, lon_off=0.0):
        out = np.empty_like(a, dtype=np.float64)
        out[:, 0] = self.cx + (a[:, 0] + lon_off - self.lonc) * self.k * self.s
        out[:, 1] = self.cy - (a[:, 1] - self.latc) * self.s
        return out


def _ring_offset(bb, shift):
    """+360 for a ring wholly west of 0 when the view is shifted across the antimeridian."""
    return 360.0 if shift and bb[2] < 0 else 0.0


def _draw_land(img, view, db, ss):
    """Natural Earth land with PIL (clean rings, so even-odd filling is right), each ring drawn
    again 360 degrees either side so a view across the antimeridian has its land."""
    d = ImageDraw.Draw(img)
    off, pts, hole, bbox = db["ring_off"], db["pts"], db["ring_hole"], db["ring_bbox"]
    span_lon = view.lon_r - view.lon_l
    for i in range(len(bbox)):
        bb = bbox[i]
        for o in (-360.0, 0.0, 360.0):
            if bb[2] + o < view.lon_l - 1 or bb[0] + o > view.lon_r + 1 or bb[3] < view.lat_b - 1 \
                    or bb[1] > view.lat_t + 1:
                continue
            a = pts[off[i]:off[i + 1]]
            if len(a) < 3:
                continue
            xy = view.xy(a, o) * ss
            # Rings bigger than the view are clipped by PIL; keep the numbers sane for it.
            np.clip(xy, -4 * span_lon * view.s * ss, 8 * img.size[0], out=xy)
            d.polygon(xy.ravel().tolist(), fill=0 if hole[i] else 255)
    return img


def _nonzero(shape, rings):
    """Rasterise ``rings`` [(pixel xy (n, 2), is_hole)] with the NONZERO winding rule, sampling
    pixel centres. Exteriors and holes are first turned opposite ways, so the result is the union
    of (exterior minus its holes): drawing rings in order with PIL (even-odd, a hole painted 0)
    lets one polygon's hole erase a neighbour, and a self-overlapping ring leaves a gap. Two
    provinces sharing an edge leave no seam (half-open sampling)."""
    H2, W2 = shape
    xa, ya, xb, yb = [], [], [], []
    for xy, hole in rings:
        if len(xy) < 3:
            continue
        x, y = xy[:, 0], xy[:, 1]
        area = float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))
        if (area < 0) != bool(hole):
            x, y = x[::-1], y[::-1]
        xa.append(x)
        ya.append(y)
        xb.append(np.roll(x, -1))
        yb.append(np.roll(y, -1))
    if not xa:
        return np.zeros(shape, bool)
    x0, y0, x1, y1 = (np.concatenate(v) for v in (xa, ya, xb, yb))
    keep = y0 != y1
    x0, y0, x1, y1 = x0[keep], y0[keep], x1[keep], y1[keep]
    d = np.where(y1 > y0, 1, -1).astype(np.int16)
    # Scanline j (centre j + 0.5) crosses an edge when lo <= j + 0.5 < hi.
    lo, hi = np.minimum(y0, y1), np.maximum(y0, y1)
    j0 = np.clip(np.ceil(lo - 0.5), 0, H2).astype(np.int64)
    j1 = np.clip(np.ceil(hi - 0.5), 0, H2).astype(np.int64)
    cnt = np.maximum(0, j1 - j0)
    tot = int(cnt.sum())
    if tot == 0:
        return np.zeros(shape, bool)
    e = np.repeat(np.arange(len(cnt)), cnt)
    start = np.cumsum(cnt) - cnt
    j = j0[e] + (np.arange(tot) - start[e])
    x = x0[e] + (j + 0.5 - y0[e]) * ((x1 - x0) / (y1 - y0))[e]
    # Pixel i (centre i + 0.5) is right of the crossing when x <= i + 0.5.
    i = np.clip(np.ceil(x - 0.5), 0, W2).astype(np.int64)
    diff = np.zeros((H2, W2 + 1), np.int16)
    np.add.at(diff, (j, i), d[e])
    return np.cumsum(diff[:, :W2], axis=1, dtype=np.int16) != 0


def _polity_mask(size, view, db, ring_ids, ss=2):
    W, H = size
    off, pts, hole, bbox = db["ring_off"], db["pts"], db["ring_hole"], db["ring_bbox"]
    lim = 8.0 * max(W, H) * ss
    rings = []
    for i in ring_ids:
        a = pts[off[i]:off[i + 1]]
        if len(a) >= 3:
            xy = view.xy(a, _ring_offset(bbox[i], view.shift)) * ss
            np.clip(xy, -lim, lim, out=xy)
            rings.append((xy, bool(hole[i])))
    full = np.zeros((H * ss, W * ss), np.uint8)
    if rings:
        # Only the territory's own pixel box is rasterised (rows are independent; crossings left
        # of the box clip to its first column, right of it to past its last).
        allxy = np.concatenate([xy for xy, _ in rings])
        bx0, by0 = max(0, int(np.floor(allxy[:, 0].min()))), max(0, int(np.floor(allxy[:, 1].min())))
        bx1 = min(W * ss, int(np.ceil(allxy[:, 0].max())) + 1)
        by1 = min(H * ss, int(np.ceil(allxy[:, 1].max())) + 1)
        if bx1 > bx0 and by1 > by0:
            o = np.array([bx0, by0], np.float64)
            sub = _nonzero((by1 - by0, bx1 - bx0), [(xy - o, h) for xy, h in rings])
            full[by0:by1, bx0:bx1] = sub.view(np.uint8) * np.uint8(255)
    img = Image.fromarray(full)
    return img.reduce(ss) if ss > 1 else img


def _land_mask(size, view, land, ss=2):
    W, H = size
    img = Image.new("L", (W * ss, H * ss), 0)
    _draw_land(img, view, land, ss)
    return img.reduce(ss) if ss > 1 else img


def _f(img):
    return np.asarray(img, dtype=np.float32) / 255.0


def _background(size, view, land):
    W, H = size
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
    r = r[..., None]
    base = np.array(SEA_IN, np.float32) * (1 - r) + np.array(SEA_OUT, np.float32) * r
    # Graticule on the sea: 8-14 lines across.
    across = view.lon_r - view.lon_l
    step = next((s for s in (1, 2, 5, 10, 15, 20, 30) if across / s <= 14), 30)
    g = Image.new("L", size, 0)
    d = ImageDraw.Draw(g)
    for lon in np.arange(math.floor(view.lon_l / step) * step, view.lon_r + step, step):
        x = view.cx + (lon - view.lonc) * view.k * view.s
        d.line([(x, 0), (x, H)], fill=255, width=1)
    for lat in np.arange(math.floor(view.lat_b / step) * step, view.lat_t + step, step):
        if abs(lat) > 85:
            continue
        y = view.cy - (lat - view.latc) * view.s
        d.line([(0, y), (W, y)], fill=255, width=1)
    ga = _f(g)[..., None] * 0.45
    base = base * (1 - ga) + np.array(GRID, np.float32) * ga
    lm = _land_mask(size, view, land)
    L = _f(lm)[..., None]
    base = base * (1 - L) + np.array(LAND, np.float32) * L
    E = np.clip(L - _f(lm.filter(ImageFilter.MinFilter(3)))[..., None], 0, 1) * 0.85
    base = base * (1 - E) + np.array(COAST, np.float32) * E
    # Static grain: no banding in the sea gradient once x264 has it.
    base += np.random.default_rng(7).normal(0, 1.1, (H, W, 1)).astype(np.float32)
    vig = (1 - 0.30 * np.clip(r * 1.25, 0, 1) ** 2).astype(np.float32)
    return base, vig


def _layer(base, vig, base_vig, mask, rect, pad):
    """The map frame (uint8) with one territory drawn in. Only the territory's own box (plus the
    glow) is composited: over the whole changing area it took ~0.95 s a period on the Ottomans."""
    frame = base_vig.copy()
    bb = mask.getbbox()
    if not bb:
        return frame
    x0, y0 = max(rect[0], bb[0] - pad), max(rect[1], bb[1] - pad)
    x1, y1 = min(rect[2], bb[2] + pad), min(rect[3], bb[3] + pad)
    if x1 <= x0 or y1 <= y0:
        return frame
    w, h = x1 - x0, y1 - y0
    # Glow and inner shading from a quarter-size copy, scaled back for this box only.
    q = mask.reduce(4)
    qbox = (x0 / 4, y0 / 4, x1 / 4, y1 / 4)
    inner = np.asarray(q.filter(ImageFilter.GaussianBlur(2.5)).resize((w, h), Image.BILINEAR, box=qbox),
                       np.float32) * (1 / 255)
    halo = np.asarray(q.filter(ImageFilter.GaussianBlur(7)).resize((w, h), Image.BILINEAR, box=qbox),
                      np.float32) * (1 / 255)
    mc = mask.crop((x0, y0, x1, y1))
    m = np.asarray(mc, np.float32) * (1 / 255)
    # A bright 2-3 px stroke just inside the border (a blur, not a rank filter: 0.26 s each).
    edge = np.clip((m - np.asarray(mc.filter(ImageFilter.GaussianBlur(1.6)), np.float32) * (1 / 255)) * 3.0, 0, 1)
    # glow over the land, then the fill (darker inside, lighter toward the border), then the stroke:
    # base*keep + [GLOW, FILL_IN, FILL_EDGE-FILL_IN, EDGE] . weights, the colours as one matmul
    # (per-channel strided maths took ~0.75 s on a frame-sized territory).
    ga = np.clip(halo * 1.7, 0, 1)
    ga *= 0.55
    ga *= 1 - m
    fa = m * 0.86
    ne = 1 - edge
    wts = np.empty((h, w, 4), np.float32)
    np.multiply(ga * (1 - fa), ne, out=wts[..., 0])
    np.multiply(fa, ne, out=wts[..., 1])
    np.multiply(np.clip((1 - inner) * 2.2, 0, 1), wts[..., 1], out=wts[..., 2])
    wts[..., 3] = edge
    keep = (1 - ga) * (1 - fa) * ne
    out = (wts.reshape(-1, 4) @ _COLOURS).reshape(h, w, 3)
    out += base[y0:y1, x0:x1] * keep[..., None]
    out *= vig[y0:y1, x0:x1]
    np.clip(out, 0, 255, out=out)
    frame[y0:y1, x0:x1] = out.astype(np.uint8)
    return frame


_COLOURS = np.array([GLOW, FILL_IN, [e - i for e, i in zip(FILL_EDGE, FILL_IN)], EDGE], np.float32)


def _font(name, px):
    return ImageFont.truetype(os.path.join(FONTS_DIR, name), max(8, int(px)))


def _latin(s):
    return all(ord(c) < 0x250 or c.isspace() for c in s)


def _tracked(draw, xy, text, font, fill, tracking):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += font.getlength(ch) + tracking
    return x


def _tracked_width(text, font, tracking):
    return sum(font.getlength(ch) for ch in text) + tracking * max(0, len(text) - 1)


def _year_text(y):
    return f"{-y} BCE" if y < 0 else str(y)


def _label(size, name, a, b, title_lines):
    """Top-left label as (RGB image, alpha mask, box). ``title_lines`` False = the name line is
    drawn by libass (a non-Latin title); only the accent bar and the range are drawn here."""
    W, H = size
    pw, ph = int(W * 0.66), int(H * 0.30)
    x, y = int(W * 0.045), int(H * 0.06)
    alpha = Image.new("L", (pw, ph), 0)
    rgb = Image.new("RGB", (pw, ph), TEXT)
    da, dr = ImageDraw.Draw(alpha), ImageDraw.Draw(rgb)
    track = max(1, round(H * 0.003))
    if title_lines:
        text = name.upper()
        fs = H * 0.056
        font = _font("Montserrat-ExtraBold.ttf", fs)
        while _tracked_width(text, font, track) > pw - x - 40 and fs > H * 0.03:
            fs *= 0.92
            font = _font("Montserrat-ExtraBold.ttf", fs)
        name_h = font.getbbox("HM")[3]
        ty = y
    else:
        name_h = int(H * 0.085)
        ty = None
    rng = f"{_year_text(a)}  -  {_year_text(b)}"
    rfont = _font("Montserrat-ExtraBold.ttf", H * 0.031)
    ry = y + name_h + int(H * 0.022)
    bar_h = ry + rfont.getbbox("0")[3] - y
    # Shadow first (alpha only), then the text in its colour.
    sh = Image.new("L", (pw, ph), 0)
    ds = ImageDraw.Draw(sh)
    if ty is not None:
        _tracked(ds, (x + 28, ty + 3), text, font, 255, track)
    _tracked(ds, (x + 28, ry + 3), rng, rfont, 255, track)
    sh = sh.filter(ImageFilter.GaussianBlur(H * 0.008))
    shadow = np.asarray(sh, np.float32) * 0.75
    if ty is not None:
        _tracked(da, (x + 28, ty), text, font, 255, track)
    _tracked(da, (x + 28, ry), rng, rfont, 255, track)
    gold_mask = Image.new("L", (pw, ph), 0)
    dg = ImageDraw.Draw(gold_mask)
    dg.rectangle([x, y + 4, x + max(4, round(H * 0.0065)), y + bar_h], fill=255)
    _tracked(dg, (x + 28, ry), rng, rfont, 255, track)
    da.rectangle([x, y + 4, x + max(4, round(H * 0.0065)), y + bar_h], fill=255)
    dr.bitmap((0, 0), gold_mask, fill=GOLD)
    a_text = np.asarray(alpha, np.float32)
    a_all = np.maximum(a_text, shadow)
    # Where only the shadow is, the colour is black.
    col = np.asarray(rgb, np.float32) * (a_text / np.maximum(a_all, 1))[..., None]
    rgb_img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8))
    a_img = Image.fromarray(np.clip(a_all, 0, 255).astype(np.uint8))
    box = a_img.getbbox() or (0, 0, 1, 1)       # pasted every frame: only the part with ink
    return rgb_img.crop(box), a_img.crop(box), box


class _Years:
    """The year counter, bottom right, over a thin progress bar. Per year a tight text mask and
    its blurred shadow mask are cached; each frame pastes black through one, the colour through
    the other."""

    def __init__(self, size):
        W, H = size
        self.size = size
        self.font = _font("Anton-Regular.ttf", H * 0.155)
        self.right = W - int(W * 0.045)
        self.bar_w = int(W * 0.17)
        self.bar_h = max(3, round(H * 0.004))
        self.bar_y = H - int(H * 0.075)
        self.base = self.bar_y - int(H * 0.025)
        self.pad = int(H * 0.03)
        self.cache = {}

    def get(self, y):
        hit = self.cache.get(y)
        if hit:
            return hit
        W, H = self.size
        text = _year_text(y)
        l, t, r, b = self.font.getbbox(text)
        p = self.pad
        w, h = r - l + 2 * p, b - t + 2 * p
        ox, oy = self.right - r - p, self.base - b - p
        tm = Image.new("L", (w, h), 0)
        ImageDraw.Draw(tm).text((p - l + 0, p - t + 0), text, font=self.font, fill=255)
        sm = Image.new("L", (w, h), 0)
        sm.paste(tm, (4, 6))
        sm = sm.filter(ImageFilter.GaussianBlur(H * 0.01)).point(lambda v: int(v * 0.8))
        # Clip to the frame (a very long BCE year on a small frame).
        cx0, cy0 = max(0, -ox), max(0, -oy)
        cx1, cy1 = min(w, W - ox), min(h, H - oy)
        hit = (ox + cx0, oy + cy0, tm.crop((cx0, cy0, cx1, cy1)), sm.crop((cx0, cy0, cx1, cy1)))
        self.cache[y] = hit
        return hit

    def draw(self, buf, y, progress):
        ox, oy, tm, sm = self.get(y)
        w, h = tm.size
        if w > 0 and h > 0:
            patch = Image.fromarray(buf[oy:oy + h, ox:ox + w])
            patch.paste((0, 0, 0), (0, 0, w, h), sm)
            patch.paste(TEXT, (0, 0, w, h), tm)
            buf[oy:oy + h, ox:ox + w] = np.asarray(patch)
        x0, x1 = self.right - self.bar_w, self.right
        y0, y1 = self.bar_y, self.bar_y + self.bar_h
        buf[y0:y1, x0:x1] = (70, 78, 92)
        buf[y0:y1, x0:x0 + round(self.bar_w * min(1.0, max(0.0, progress)))] = GOLD


def _ass_title(path, size, title):
    """A non-Latin title (Urdu) for libass, centred on the name slot of ``_label``. Nastaliq's
    line box is far taller than its letters: top-aligned at 0.06 H it came out tiny and high."""
    W, H = size
    x, y = int(W * 0.045) + 28, int(H * 0.06) + int(H * 0.085) // 2
    body = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {W}\nPlayResY: {H}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: T,Noto Nastaliq Urdu,{int(H * 0.095)},&H00E2F1F7,&H00E2F1F7,&H00000000,&H90000000,"
        "0,0,0,0,100,100,0,0,1,0,3,7,0,0,0,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,9:59:59.00,T,,0,0,0,,{{\\an4\\pos({x},{y})}}"
        + title.replace("\n", " ").replace("{", "(").replace("}", ")") + "\n")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)


def _timeline(n, a, b, fps):
    """Displayed year per frame: hold the start, count up eased, hold the end."""
    hold_a, hold_b = round(0.45 * fps), round(1.0 * fps)
    mid = n - hold_a - hold_b
    if mid < 2:
        hold_a, hold_b, mid = 0, 0, n
    years = []
    for f in range(n):
        u = min(1.0, max(0.0, (f - hold_a) / max(1, mid - 1)))
        e = 0.5 - 0.5 * math.cos(math.pi * u)
        years.append(int(round(a + (b - a) * e)))
    return years


def render(name, from_year, to_year, out, seconds=7.0, size=(1920, 1080), fps=30, title="", cwd=None,
           vf_tail="", crf="18"):
    """``name``'s territory from ``from_year`` to ``to_year`` as a ``seconds`` clip at ``out``
    (relative to ``cwd`` when given; ffmpeg runs there, so ``vf_tail`` can name files by bare
    name). ``title`` replaces the English name on the label (an Urdu title is set by libass).
    Returns ``out``, or None on any failure (never raises)."""
    t0 = time.time()
    path = None
    try:
        if not available():
            return None
        path = out if os.path.isabs(out) or not cwd else os.path.join(cwd, out)
        n = _render(name, int(from_year), int(to_year), out, path, float(seconds), tuple(size), int(fps),
                    str(title or ""), cwd, vf_tail, str(crf))
        if n is None:
            return None
        _say(f"Map of {name}: {n} frames in {time.time() - t0:.1f}s.")
        return out
    except Exception as e:  # noqa: BLE001
        _say(f"History map skipped ({type(e).__name__}: {str(e)[:120]}).")
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
        return None


def _render(name, a, b, out, path, seconds, size, fps, title, cwd, vf_tail, crf):
    db = _load(POLITIES_FILE)
    land = _load(LAND_FILE)
    i = _index(db, name)
    if i is None:
        _say(f"History map: no polity like {name!r} in Cliopatria.")
        return None
    name = str(db["names"][i])
    r0, r1 = int(db["name_rec"][i]), int(db["name_rec"][i + 1])
    rf, rt = db["rec_from"][r0:r1], db["rec_to"][r0:r1]
    if a > b:
        a, b = b, a
    lo, hi = int(rf.min()), int(rt.max())
    a, b = max(a, lo - SLACK_YEARS), min(b, hi)
    if b < lo or a > b:
        _say(f"History map: {name} has no territory in those years (data {lo}-{hi}).")
        return None
    W, H = size
    n = max(1, int(round(seconds * fps)))
    years = _timeline(n, a, b, fps)

    def rec_at(y):
        j = int(np.searchsorted(rf, y, side="right")) - 1
        return r0 + max(0, j)       # before the first row: the first; a gap or past the end: hold

    keys = [rec_at(y) for y in years]
    used = sorted(set(keys))
    rr = db["rec_ring"]
    ring_ids = {k: range(int(rr[k]), int(rr[k + 1])) for k in used}
    bbox = db["ring_bbox"]
    ext = np.concatenate([bbox[list(ring_ids[k])] for k in used])
    ext = ext[np.array([not db["ring_hole"][j] for k in used for j in ring_ids[k]])]
    shift = False
    lon0, lon1 = float(ext[:, 0].min()), float(ext[:, 2].max())
    if lon1 - lon0 > 180:
        west = ext[:, 2] < 0
        s0 = float(np.where(west, ext[:, 0] + 360, ext[:, 0]).min())
        s1 = float(np.where(west, ext[:, 2] + 360, ext[:, 2]).max())
        if s1 - s0 < lon1 - lon0 - 1:
            shift, lon0, lon1 = True, s0, s1
    box = (lon0, max(-85.0, float(ext[:, 1].min())), lon1, min(85.0, float(ext[:, 3].max())))
    view = _View(box, size, shift)

    # Where any territory (plus its glow) can be: the only part of the frame that ever changes.
    xs, ys = [], []
    for k in used:
        for j in ring_ids[k]:
            bb = bbox[j]
            o = _ring_offset(bb, shift)
            p = view.xy(np.array([[bb[0], bb[1]], [bb[2], bb[3]]], np.float64), o)
            xs += [p[0, 0], p[1, 0]]
            ys += [p[0, 1], p[1, 1]]
    pad = int(H * 0.06)
    rect = (max(0, int(min(xs)) - pad), max(0, int(min(ys)) - pad),
            min(W, int(max(xs)) + pad + 1), min(H, int(max(ys)) + pad + 1))
    if rect[2] <= rect[0] or rect[3] <= rect[1]:
        rect = (0, 0, W, H)

    base, vig = _background(size, view, land)
    base_vig = np.clip(base * vig, 0, 255).astype(np.uint8)
    latin = not title or _latin(title)
    lab_rgb, lab_a, lab_box = _label(size, title if (title and latin) else name, a, b, latin)
    counter = _Years(size)

    run_dir = cwd or os.path.dirname(os.path.abspath(path)) or "."
    out_arg = out if cwd else os.path.abspath(path)
    vf = "setsar=1,format=yuv420p"
    ass_name = None
    if not latin:
        from ffmpeg_utils import escape_filter_value
        ass_name = f"_map_title_{os.getpid()}_{int(time.time() * 1000) % 100000}.ass"
        _ass_title(os.path.join(run_dir, ass_name), size, title)
        vf += f",ass=filename='{ass_name}':fontsdir='{escape_filter_value(FONTS_DIR)}'"
    if vf_tail:
        vf += "," + vf_tail
    try:
        import cv2
    except Exception:  # noqa: BLE001
        cv2 = None
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-vf", vf, "-frames:v", str(n), "-c:v", "libx264", "-preset", "veryfast",
           "-crf", crf, "-pix_fmt", "yuv420p", "-video_track_timescale", "30000", "-an", out_arg]
    p = subprocess.Popen(cmd, cwd=run_dir, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    # Each change crossfades until the next one starts (3 frames at least, FADE_SECONDS at most):
    # a fixed 9-frame fade lagged behind the Ottomans' changes every ~2 frames and left ghosts.
    fade_max = max(1, int(round(FADE_SECONDS * fps)))
    change = [f for f in range(1, n) if keys[f] != keys[f - 1]]
    fade_len = {f: max(3, min(fade_max, g - f)) for f, g in zip(change, change[1:] + [n + fade_max])}
    x0, y0, x1, y1 = rect
    pad = int(H * 0.06)
    shown = None
    cur, src, dst, fade_at, fade = None, None, None, 0, fade_max
    buf = np.empty((H, W, 3), np.uint8)
    zc = (view.cx, view.cy)
    try:
        for f in range(n):
            k = keys[f]
            if k != cur:
                mask = _polity_mask(size, view, db, ring_ids[k])
                layer = _layer(base, vig, base_vig, mask, rect, pad)
                if shown is None:
                    shown = layer.copy()
                    src = None
                else:
                    src = shown[y0:y1, x0:x1].copy()
                    fade_at, fade = f, fade_len.get(f, fade_max)
                dst = layer[y0:y1, x0:x1].copy()
                cur = k
            if src is not None:
                t = (f - fade_at + 1) / fade
                if t >= 1:
                    shown[y0:y1, x0:x1] = dst
                    src = None
                else:
                    t = t * t * (3 - 2 * t)
                    if cv2 is not None:
                        shown[y0:y1, x0:x1] = cv2.addWeighted(src, 1 - t, dst, t, 0)
                    else:
                        w = int(round(256 * t))
                        shown[y0:y1, x0:x1] = ((src.astype(np.uint16) * (256 - w) + dst.astype(np.uint16) * w)
                                               >> 8).astype(np.uint8)
            if cv2 is not None and ZOOM > 0 and n > 1:
                e = 0.5 - 0.5 * math.cos(math.pi * f / (n - 1))
                z = 1 + ZOOM * e
                M = np.array([[z, 0, (1 - z) * zc[0]], [0, z, (1 - z) * zc[1]]], np.float64)
                cv2.warpAffine(shown, M, (W, H), dst=buf, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            else:
                np.copyto(buf, shown)
            lx0, ly0, lx1, ly1 = lab_box
            patch = Image.fromarray(buf[ly0:ly1, lx0:lx1])
            patch.paste(lab_rgb, (0, 0), lab_a)
            buf[ly0:ly1, lx0:lx1] = np.asarray(patch)
            counter.draw(buf, years[f], (years[f] - a) / (b - a) if b > a else 1.0)
            p.stdin.write(buf.tobytes())
        p.stdin.close()
        err = p.stderr.read().decode("utf-8", "replace")
        if p.wait(timeout=600) != 0:
            raise RuntimeError(f"map encode failed: {err.strip()[-300:]}")
    except (BrokenPipeError, OSError) as e:
        err = ""
        try:
            p.wait(timeout=30)
            err = p.stderr.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"ffmpeg stopped ({e}): {err.strip()[-300:]}") from e
    finally:
        if p.poll() is None:
            p.kill()
        if ass_name:
            try:
                os.remove(os.path.join(run_dir, ass_name))
            except OSError:
                pass
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError("no output written")
    return n


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["build"] and len(args) >= 3:
        t = time.time()
        print(build(args[1], args[2], args[3] if len(args) > 3 else None), f"{time.time() - t:.1f}s")
    elif args[:1] == ["find"] and len(args) >= 2:
        q = " ".join(args[1:])
        print(q, "->", find(q), span(q))
    elif args[:1] == ["render"] and len(args) >= 5:
        print(render(args[1], int(args[2]), int(args[3]), args[4], seconds=float(args[5]) if len(args) > 5 else 7.0,
                     title=args[6] if len(args) > 6 else ""))
    else:
        print("usage: history_maps.py build <cliopatria.geojson.zip> <ne_50m_land.geojson> [out_dir]\n"
              "       history_maps.py find <query>\n"
              "       history_maps.py render <name> <from> <to> <out.mp4> [seconds] [title]")
