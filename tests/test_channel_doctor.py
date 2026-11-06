"""channel_doctor.py (5-nov-2026, the REA repo's method): each question answered from the channel's own numbers,
problems first, unknowns said as unknown, every answer with its evidence. Its first live run found that three
channels had posted 6 of 14 Shorts in a week (a 4-day outage) and the Quran channel was stuck on one passage."""
import my_channels as mc
import channel_doctor as cd
import youtube_account as ya

DAY = 86400
NOW = 1_800_000_000


def _rows(n, views, age_days, fmt="topic", **kw):
    return [{"id": f"row{age_days}_{i}", "video_id": f"yt{age_days}_{i}", "status": "done", "format": fmt, "created": NOW - age_days * DAY - i,
             "views": views, "title": f"Video {i}", **kw} for i in range(n)]


def test_a_week_of_missed_posts_is_a_problem_and_a_full_week_is_good():
    ch = {"id": "c", "kind": "cricket", "per_day": 2, "created": NOW - 30 * DAY,
          "jobs": [{"status": "failed", "at": NOW - DAY, "label": "Run-out", "error": "the job was lost"}]}
    c = cd.posting(ch, _rows(6, 5, 1), NOW, mc.EXTRA_FORMATS)
    assert c["status"] == "problem" and c["finding"].startswith("6 of 14 planned videos")
    assert "1 failed" in c["finding"] and "the job was lost" in c["evidence"][0]
    assert cd.posting(ch, _rows(13, 5, 1), NOW, mc.EXTRA_FORMATS)["status"] == "good"
    # Teasers are on top of the plan, and a card taken over today is too new to judge.
    assert cd.posting(ch, _rows(14, 5, 1, fmt="teaser"), NOW, mc.EXTRA_FORMATS)["status"] == "problem"
    assert cd.posting(ch, [], NOW, mc.EXTRA_FORMATS, started=NOW - 3600)["status"] == "unknown"


def test_reach_says_unknown_until_enough_videos_then_problem_or_growing():
    assert cd.reach(_rows(2, 5, 3), NOW)["status"] == "unknown"
    low = cd.reach(_rows(4, 3, 3) + _rows(5, 4, 12), NOW)
    assert low["status"] == "problem" and "median of 3 views" in low["finding"]
    assert low["evidence"][0]["url"].startswith("https://youtu.be/yt3_")
    up = cd.reach(_rows(4, 40, 3) + _rows(5, 6, 12), NOW)
    assert up["status"] == "good" and "Growing" in up["finding"]
    assert cd.reach(_rows(4, 1200, 3), NOW)["status"] == "good"


def test_staying_uses_the_watch_share_and_where_half_the_viewers_are_gone():
    ch = {"stats": {"watched": 27, "retention_lesson": "WHERE THIS CHANNEL'S VIEWERS LEAVE: ..."}}
    rows = [{"retention": 27, "curve": {"half_at": 8.0}}] * 3
    c = cd.staying(ch, rows, long=False)
    assert c["status"] == "problem" and "27% of each video" in c["finding"] and "gone by 0:08" in c["finding"]
    assert cd.staying({"stats": {"watched": 30}}, rows, long=True)["status"] == "tip"
    assert cd.staying({"stats": {}}, [], long=False)["status"] == "unknown"


def test_the_niche_check_names_its_measured_gap_and_its_winners():
    import teardown as td
    m = {"seconds": 30, "first_cut": 1.0, "shot": 1.5, "first_word": 0.1, "hook_words": 9, "wps": 3.4,
         "first_luma": 120, "loop": True}
    research = {"anatomy": {f"w{i}": {"m": m, "title": f"Hit {i}", "views": 10 ** 6 - i} for i in range(5)},
                "ours": {f"o{i}": {"m": {**m, "first_cut": 4.0}} for i in range(3)}}
    c = cd.niche(research, td.compare, td.winners, (td.MIN_THEIRS, td.MIN_OURS))
    assert c["status"] == "tip" and "the first picture change" in c["finding"]
    assert any(isinstance(e, dict) and e["url"] == "https://youtu.be/w0" for e in c["evidence"])
    assert cd.niche({}, td.compare, td.winners, (4, 3))["status"] == "unknown"


def test_a_long_channel_that_is_not_verified_is_a_problem():
    c = cd.verified({"long_uploads": {"status": "eligible"}, "minutes": 20}, 14)
    assert c["status"] == "problem" and "14 minutes" in c["finding"] and "youtube.com/verify" in c["next"]
    assert cd.verified({"long_uploads": {"status": "allowed"}}, 14)["status"] == "good"


def test_every_card_gets_its_checks_problems_first():
    ch = mc.add("cricket")
    mc._change(ch["id"], lambda c: c.update(created=NOW - 30 * DAY, stats={"watched": 27, "median": 8}))
    checks = cd.run(mc.get(ch["id"]), _rows(4, 3, 3), {}, {"connected": False}, now=NOW)
    assert checks[0]["status"] == "problem" and {c["key"] for c in checks} >= {"connection", "posting", "reach"}
    order = [cd.STATUS_ORDER[c["status"]] for c in checks]
    assert order == sorted(order)
    assert cd.run({"id": "main"}, [], {}) == []
    s = mc.summary(mc.get(ch["id"]))
    assert s["doctor"] and all({"question", "status", "finding", "evidence", "next"} <= set(c) for c in s["doctor"])


def test_a_handed_over_channel_reads_only_the_searches_since_then(monkeypatch):
    import yt_insights
    asked = []
    monkeypatch.setattr(yt_insights, "search_terms", lambda video_id=None, days=90, limit=12:
                        asked.append(days) or [("paisa kitna", 3)])
    monkeypatch.setattr(yt_insights, "retention_lesson", lambda rows, long=False: "")
    ch = mc.add("money")
    took = {"at": 1_000_000, "from": "Quiz"}
    import time as _t
    monkeypatch.setattr(_t, "time", lambda: 1_000_000 + DAY)              # a day after the hand-over
    out = mc._insights({**ch, "took_over": took, "stats": {"search": [["mushkil paheliyan", 7]]}}, [], log=lambda m: None)
    assert out["search"] == [] and asked == []
    monkeypatch.setattr(_t, "time", lambda: 1_000_000 + 5 * DAY)
    out = mc._insights({**ch, "took_over": took, "stats": {"search_at": 0}}, [], log=lambda m: None)
    assert asked == [5] and out["search"] == [("paisa kitna", 3)]
