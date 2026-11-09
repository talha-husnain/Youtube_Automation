"""The same song never goes up twice (owner, 5-nov-2026: "a duplicate-song check before upload, using
Chromaprint").

Chromaprint (acoustid/chromaprint, MIT core / LGPL as a whole; run as its own program, ``fpcalc``, found in
<project>/../oss/chromaprint/ or on PATH or FPCALC) fingerprints a recording; two files of the same recording
match even re-encoded, cut at another place or with an end card after it. Fingerprints of a channel's uploaded
songs are kept in state/fingerprints/<channel>.json; a new song's Short is compared before it uploads (a remake
or a retry that reused the same song, a song uploaded by hand from Studio...). Local only: the AcoustID web
service charges for commercial use and is never called. Two DIFFERENT songs (two Lyria takes on one theme) do not
match: this catches the same audio, not a similar melody.

A song mix (mood_mix.py) is never checked: it is built from the channel's songs on purpose.
"""
import glob
import json
import os
import shutil
import subprocess
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(ROOT, "state", "fingerprints")
SECONDS = 120                  # fingerprint the first two minutes
MATCH = 0.80                   # share of matching bits (1 - bit error rate) on the best overlap = the same recording
MIN_OVERLAP = 60               # fingerprint frames (~8 a second) two files must share to be compared
MAX_SHIFT = 600                # frames one may start after the other (a Short cut from the chorus, ~75 s)
KEEP = 400                     # fingerprints kept per channel
_lock = threading.Lock()


def fpcalc():
    """The fpcalc program, or None (the check is then skipped, never the upload)."""
    env = os.environ.get("FPCALC")
    if env and os.path.isfile(env):
        return env
    for p in glob.glob(os.path.join(ROOT, "..", "oss", "chromaprint", "**", "fpcalc*"), recursive=True):
        if os.path.isfile(p) and os.path.basename(p).lower() in ("fpcalc", "fpcalc.exe"):
            return os.path.abspath(p)
    return shutil.which("fpcalc")


def available():
    return fpcalc() is not None


def fingerprint(path, seconds=SECONDS):
    """The raw Chromaprint fingerprint (a list of 32-bit ints, ~8 a second), or None."""
    exe = fpcalc()
    if not exe or not os.path.isfile(path):
        return None
    try:
        r = subprocess.run([exe, "-raw", "-json", "-length", str(int(seconds)), path], capture_output=True, text=True,
                           timeout=180)
        data = json.loads(r.stdout or "{}")
        fp = [int(x) & 0xFFFFFFFF for x in data.get("fingerprint") or []]
        return fp or None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def similarity(a, b, max_shift=MAX_SHIFT, min_overlap=MIN_OVERLAP):
    """The best share of equal bits between ``a`` and ``b`` over every shift (either may start later): 1.0 = the
    same audio, ~0.5 = unrelated sound. 0.0 when they never overlap enough."""
    import numpy as np
    x = np.asarray(a, dtype=np.uint32)
    y = np.asarray(b, dtype=np.uint32)
    if len(x) < min_overlap or len(y) < min_overlap:
        return 0.0
    table = _popcount16()
    best = 0.0
    for shift in range(-min(max_shift, len(y) - min_overlap), min(max_shift, len(x) - min_overlap) + 1):
        xs = x[shift:] if shift >= 0 else x
        ys = y if shift >= 0 else y[-shift:]
        n = min(len(xs), len(ys))
        if n < min_overlap:
            continue
        bits = int(table[np.bitwise_xor(xs[:n], ys[:n]).view(np.uint16)].sum())
        best = max(best, 1.0 - bits / (32.0 * n))
    return round(best, 4)


_TABLE = []


def _popcount16():
    """Set bits of every 16-bit number (a lookup instead of unpacking bits: ~20x faster)."""
    if not _TABLE:
        import numpy as np
        t = np.zeros(65536, dtype=np.uint8)
        for k in range(16):
            t += ((np.arange(65536) >> k) & 1).astype(np.uint8)
        _TABLE.append(t)
    return _TABLE[0]


def _path(cid):
    return os.path.join(STATE_DIR, f"{''.join(c for c in str(cid) if c.isalnum() or c in '-_')[:60] or 'main'}.json")


def _load(cid):
    try:
        with open(_path(cid), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def remember(cid, key, title, fp):
    """Keep an uploaded song's fingerprint for the channel (the newest KEEP)."""
    if not fp:
        return
    with _lock:
        rows = [r for r in _load(cid) if r.get("key") != key]
        rows.append({"key": key, "title": (title or "")[:100], "at": int(time.time()), "fp": list(fp)})
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = _path(cid) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows[-KEEP:], f)
        os.replace(tmp, _path(cid))


def duplicate(cid, fp, exclude=None):
    """The kept song this fingerprint is the same recording as ({"key", "title", "score"}), or None."""
    if not fp:
        return None
    best = None
    for r in _load(cid):
        if exclude and r.get("key") == exclude:
            continue
        s = similarity(fp, r.get("fp") or [])
        if s >= MATCH and (best is None or s > best["score"]):
            best = {"key": r.get("key"), "title": r.get("title") or "", "score": s}
    return best
