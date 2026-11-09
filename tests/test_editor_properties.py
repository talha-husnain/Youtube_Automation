"""Invariants of the AI editor's time maths over thousands of seeded random cases (no extra dependency):
a wrong map puts captions, zooms and cuts on the wrong words."""
import random

import pytest

import ai_editor as ae
import studio

CASES = 1500


def _random_timeline(rng):
    length = rng.uniform(5, 120)
    marks = sorted(rng.uniform(0, length) for _ in range(rng.randrange(0, 8) * 2))
    keep, last = [], 0.0
    for a, b in zip(marks[::2], marks[1::2]):          # cut [a, b]
        keep.append((last, a))
        last = b
    keep.append((last, length))
    segs = []
    for _ in range(rng.randrange(0, 3)):
        a = rng.uniform(0, length)
        segs.append((a, min(length, a + rng.uniform(0.1, 10)), rng.choice([0.25, 0.5, 0.75, 1.5, 2.0, 3.0])))
    return ae.Timeline(keep, speed=rng.choice([1.0, 1.0, 1.25, 0.8, 2.0]), segments=segs), length


def test_timeline_roundtrip_order_and_duration():
    rng = random.Random(1104)
    for _ in range(CASES):
        tl, length = _random_timeline(rng)
        assert tl.duration == pytest.approx(sum((b - a) / f for a, b, f in tl.pieces))
        assert all(b > a and f > 0 for a, b, f in tl.pieces)
        assert all(p[1] <= q[0] + 1e-9 for p, q in zip(tl.pieces, tl.pieces[1:]))   # in order, no overlap
        prev = -1.0
        for _ in range(20):
            t = rng.uniform(0, length)
            o = tl.out(t)
            kept = any(a - 1e-6 <= t <= b + 1e-6 for a, b, _f in tl.pieces)
            assert (o is not None) == kept
            if o is None:
                continue
            assert -1e-6 <= o <= tl.duration + 1e-6
            assert tl.base(o) == pytest.approx(t, abs=1e-5)                          # roundtrip
        # Output time never runs backwards as base time goes forward.
        for t in sorted(rng.uniform(0, length) for _ in range(30)):
            o = tl.out(t)
            if o is not None:
                assert o >= prev - 1e-6
                prev = o


def test_out_ranges_and_base_ranges_agree():
    rng = random.Random(7)
    for _ in range(CASES):
        tl, length = _random_timeline(rng)
        a = rng.uniform(0, length)
        b = min(length, a + rng.uniform(0.5, 20))
        for lo, hi in tl.out_ranges(a, b):
            assert 0 <= lo < hi <= tl.duration + 1e-6
            # Every output moment shown comes from inside [a, b]. (Not the ends: an output time on a cut's seam
            # is both pieces' moment and base() answers with the earlier side, the same frame on screen.)
            for x in (lo + (hi - lo) * 0.01, (lo + hi) / 2, hi - (hi - lo) * 0.01):
                assert a - 1e-3 <= tl.base(x) <= b + 1e-3


def test_compile_ops_keeps_sorted_disjoint_ranges_inside_the_video():
    rng = random.Random(42)
    for _ in range(CASES):
        length = rng.uniform(5, 90)
        ops = []
        for _ in range(rng.randrange(1, 6)):
            a = rng.uniform(-2, length + 2)
            ops.append({"op": rng.choice(["cut", "keep"]), "ranges": [[a, a + rng.uniform(0, 15)]]})
        keep = ae.compile_ops(ops, length, [], {"captions": False})["keep"]
        assert all(0 <= a < b <= length + 1e-6 for a, b in keep)
        assert all(p[1] <= q[0] + 1e-9 for p, q in zip(keep, keep[1:]))


def test_a_clip_slice_holds_only_that_clips_words_from_zero():
    rng = random.Random(3)
    for _ in range(300):
        words, t = [], 0.0
        for _ in range(200):
            t += rng.uniform(0, 2)
            words.append({"word": " w", "start": round(t, 3), "end": round(t + rng.uniform(0.05, 3), 3)})
        a = rng.uniform(0, t)
        b = a + rng.uniform(5, 60)
        data = {"shorts": [{"start": a, "end": b}, {"start": 0, "end": 1}],
                "transcript": {"segments": [{"words": words}]}}
        got = [w for s in studio.clip_transcript(data, 0)["segments"] for w in s["words"]]
        want = [w for w in words if w["end"] > a and w["start"] < b]
        assert len(got) == len(want)
        assert all(0 <= w["start"] <= w["end"] and w["start"] < b - a for w in got)
