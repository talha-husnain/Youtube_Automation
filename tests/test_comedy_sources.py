"""Punchline Bazaar's sources and moments (11-nov-2026): the known comedians' own Creative Commons
videos (comedy_sources.py) and YouTube's "Most replayed" graph (replay_heat.py)."""
import random
import time
from datetime import date

import pytest

import clip_selection
import comedy_sources as cs
import replay_heat as rh


def _graph(duration=900.0, n=100, peaks=((213, 1.0),), base=0.3, intro=0.9):
    step = duration / n
    pts = []
    for i in range(n):
        s = i * step
        v = intro if s < 20 else base
        for at, val in peaks:
            if s <= at < s + step:
                v = val
        pts.append({"start_time": s, "end_time": s + step, "value": v})
    return pts


# ------------------------------------------------------------------ replay heat

def test_the_intro_bump_is_ignored_and_the_body_rescaled():
    pts = rh.clean(_graph(peaks=((213, 0.5),)), 900)
    assert pts and min(s for s, _e, _v in pts) >= 25                    # the replayed start is not a moment
    assert max(v for _s, _e, v in pts) == pytest.approx(1.0)            # 0.5 is the body's peak
    assert rh.heat(pts, 200, 230) == pytest.approx(1.0)
    assert rh.heat(pts, 400, 450) == pytest.approx(0.6)                 # 0.3 / 0.5
    assert rh.heat(pts, 2000, 2100) == 0.0


def test_a_flat_or_missing_graph_gives_no_heat():
    assert rh.clean(_graph(peaks=()), 900) == []                        # every point the same
    assert rh.clean([], 900) == [] and rh.clean(None) == []
    assert rh.clean([{"start_time": "x"}] * 50) == []


def test_peak_span_is_the_hot_stretch_inside_the_window():
    pts = rh.clean(_graph(peaks=((213, 1.0), (222, 0.9), (231, 0.5))), 900)
    s, e = rh.peak_span(pts, 180, 270)
    assert s == pytest.approx(207) and e == pytest.approx(225)          # 213 and 222, not the 0.5 at 231
    assert rh.peak_span(pts, 215, 220) == (215, 220)                    # clamped to the window
    assert rh.peak_span([], 0, 10) is None


def test_hottest_moments_are_apart_and_in_time_order():
    pts = rh.clean(_graph(peaks=((213, 1.0), (222, 0.95), (600, 0.8))), 900)
    got = rh.hottest(pts, n=2, gap=30)
    assert [round(s) for s, _e, _v in got] == [207, 594]                # 222 is the same moment as 213
    assert rh.hottest(pts, n=5) == got                                  # the flat 0.3 body is no moment
    assert rh.clock(213.7) == "3:33"


def test_heat_never_exceeds_one_and_spans_stay_in_the_window_for_random_graphs():
    rnd = random.Random(7)
    for _ in range(200):
        dur = rnd.uniform(300, 4000)
        raw = [{"start_time": i * dur / 100, "end_time": (i + 1) * dur / 100, "value": rnd.random()} for i in range(100)]
        pts = rh.clean(raw, dur)
        a = rnd.uniform(0, dur)
        b = a + rnd.uniform(5, 120)
        h = rh.heat(pts, a, b)
        assert 0.0 <= h <= 1.0
        span = rh.peak_span(pts, a, b)
        if span:
            assert a <= span[0] < span[1] <= b


def test_a_clip_on_the_replay_peak_wins_the_trim():
    shorts = [{"start": 10, "predicted_score": 80}, {"start": 50, "predicted_score": 70, "replay_heat": 1.0},
              {"start": 90, "predicted_score": 75, "replay_heat": 0.0}]
    best = clip_selection.trim_to_best(shorts, 2)
    assert [s["start"] for s in best] == [10, 50]                       # 70 + 60 beats 75; order kept
    assert clip_selection.trim_to_best([{"predicted_score": 5, "replay_heat": "bad"}, {"predicted_score": 1}], 1)


# ------------------------------------------------------------------ known comedians

UC = "https://www.youtube.com/channel/UC" + "a" * 22
UC2 = "https://www.youtube.com/channel/UC" + "b" * 22


def test_a_vetted_find_makes_its_channel_a_known_creator():
    cs.remember([{"channel_url": UC, "channel": "Comic", "views": 900_000},
                 {"channel_url": "https://www.youtube.com/@handle", "channel": "No id", "views": 5},
                 {"channel_url": UC, "channel": "Comic", "views": 2_000_000}])
    got = cs.creators()
    assert list(got) == [UC] and got[UC]["kept"] == 2 and got[UC]["best_views"] == 2_000_000
    cs.remember([{"channel_url": UC2, "channel": "Blocked", "views": 1}], blocked=lambda u: u == UC2)
    assert UC2 not in cs.creators()


def test_due_reads_new_creators_first_then_the_biggest_and_rests_them():
    now = time.time()
    data = {"old_big": {"best_views": 9_000_000, "read": now - 6 * 86400},
            "new_small": {"best_views": 10, "read": 0},
            "fresh_read": {"best_views": 99_000_000, "read": now - 3600},
            "old_mid": {"best_views": 500_000, "read": now - 30 * 86400}}
    assert cs.due(data, now=now, n=3) == ["new_small", "old_big", "old_mid"]
    assert cs.due(data, now=now, n=3, skip=lambda u: u == "old_big") == ["new_small", "old_mid"]


def test_videos_keeps_only_creative_commons_uploads(monkeypatch):
    import yt_api
    cs.remember([{"channel_url": UC, "channel": "Comic", "views": 1}])
    rows = [{"id": "A" * 11, "url": "u1", "title": "set 1", "channel": "Comic", "seconds": 900, "views": 5_000_000,
             "licence": "creativeCommon"},
            {"id": "B" * 11, "url": "u2", "title": "set 2", "channel": "Comic", "seconds": 900, "views": 7_000_000,
             "licence": "youtube"}]
    asked = []
    monkeypatch.setattr(yt_api, "uploads", lambda cid, limit: asked.append(cid) or rows)
    notes = []
    got = cs.videos(notes.append)
    assert asked == ["UC" + "a" * 22] and [v["id"] for v in got] == ["A" * 11]
    assert got[0]["channel_url"] == UC and got[0]["views"] == 5_000_000
    row = cs.creators()[UC]
    assert row["cc"] == 1 and row["best_views"] == 5_000_000 and row["read"] > 0
    assert any("1 Creative Commons videos of 2" in n for n in notes)
    assert cs.videos(notes.append) == []                                # resting for CREATOR_REST


def test_a_creator_that_cannot_be_read_is_tried_again(monkeypatch):
    import yt_api
    cs.remember([{"channel_url": UC, "channel": "Comic", "views": 1}])

    def down(cid, limit):
        raise RuntimeError("quota")
    monkeypatch.setattr(yt_api, "uploads", down)
    assert cs.videos(lambda t: None) == [] and cs.creators()[UC]["read"] == 0


def test_queries_rotate_through_the_whole_bank():
    seen = set()
    for d in range(len(cs.QUERY_BANK)):
        today = cs.queries_today(date.fromordinal(730_000 + d))
        assert len(today) == cs.QUERIES_PER_DAY and len(set(today)) == cs.QUERIES_PER_DAY
        seen.update(today)
    assert seen == set(cs.QUERY_BANK)


def test_research_adds_the_known_comedians_and_drops_reaction_videos(monkeypatch):
    import autopilot_local as ap
    import channel_tools
    import short_kit
    import used_moments
    v = lambda i, title, views, url="https://www.youtube.com/@s": {
        "id": f"S{i:010d}", "url": f"https://www.youtube.com/watch?v=S{i:010d}", "title": title, "channel": "s",
        "channel_url": url, "seconds": 900, "views": views}
    monkeypatch.setattr(channel_tools, "search", lambda q, **k: [v(1, "Stand up REACTION!!", 3_000_000),
                                                                  v(2, "my set", 200_000)])
    monkeypatch.setattr(cs, "videos", lambda log, skip: [v(3, "crowd work", 2_000_000, UC)])
    monkeypatch.setattr(used_moments, "summary", lambda url: {"count": 0, "seconds": 0})
    monkeypatch.setattr(short_kit, "gemini", lambda: None)
    vetted = []

    def keep_all(c, schema, contents, **k):
        ids = [line.split('"id": "')[1][:11] for line in contents.splitlines() if '"id": "' in line]
        vetted.extend(ids)
        return schema.model_validate({"videos": [{"id": i, "keep": True, "reason": "ok"} for i in ids]})
    monkeypatch.setattr(short_kit, "ask_json", keep_all)
    fresh, _ = ap.research_videos({**ap.settings(), "research_queries": ["x"]}, lambda t: None)
    assert "S0000000001" not in vetted                                  # a reaction video never takes a slot
    assert [x["id"] for x in fresh] == ["S0000000003", "S0000000002"]   # the comedian's 2M set first
    assert cs.creators()[UC]["kept"] == 1
