"""my_channels.learn: views, posting hours and how much of each Short people watch."""
import time
from datetime import datetime, timedelta, timezone

import my_channels as mc
import youtube_account as ya


def test_learning_keeps_views_hours_and_retention_per_format(monkeypatch):
    ch = mc.add("quiz")
    acct = mc.account(ch["id"])
    old = (datetime.now(timezone.utc) - timedelta(days=3)).replace(minute=0, second=0, microsecond=0)
    with ya.use(acct):
        for vid, fmt in (("V1", "mcq"), ("V2", "mcq"), ("V3", "flags"), ("V4", "flags")):
            ya._save_upload({"id": vid, "video_id": vid, "status": "done", "created": time.time() - 3 * 86400,
                             "format": fmt, "genre": "quiz", "title": vid, "publish_at": old.isoformat()})
    views = {"V1": 100, "V2": 300, "V3": 40, "V4": 60}

    def get(url, params):
        return {"items": [{"id": v, "statistics": {"viewCount": views[v]}, "status": {"privacyStatus": "public"},
                           "snippet": {"publishedAt": old.isoformat().replace("+00:00", "Z")}}
                          for v in params["id"].split(",")]}
    monkeypatch.setattr(ya, "status", lambda: {"connected": True})
    monkeypatch.setattr(ya, "_get", get)
    monkeypatch.setattr(ya, "video_analytics", lambda days=90: {
        "V1": {"avg_percent": 70.0, "avg_seconds": 30}, "V2": {"avg_percent": 90.0, "avg_seconds": 40},
        "V3": {"avg_percent": 40.0, "avg_seconds": 20}})
    stats = mc.learn(mc.get(ch["id"]), log=lambda *a: None)["stats"]
    assert stats["counted"] == 4 and stats["median"] == 80
    assert stats["formats"]["mcq"] == {"shorts": 2, "median": 200, "watched": 80}
    assert stats["formats"]["flags"] == {"shorts": 2, "median": 50, "watched": 40}
    assert stats["watched"] == 70
    assert stats["hours"] == {f"{old.astimezone().hour:02d}": {"shorts": 4, "median": 80}}
    with ya.use(acct):
        assert next(r for r in ya.uploads() if r["id"] == "V2")["retention"] == 90.0


def test_formats_are_compared_on_views_at_the_same_age(monkeypatch):
    # An old Short's lifetime views must not beat a young one's: each keeps its views at 48-72 h.
    ch = mc.add("quiz")
    acct = mc.account(ch["id"])
    now = datetime.now(timezone.utc)
    published = {"OLD": now - timedelta(hours=50), "NEW": now - timedelta(hours=50)}
    with ya.use(acct):
        for vid, fmt in (("OLD", "mcq"), ("NEW", "flags")):
            ya._save_upload({"id": vid, "video_id": vid, "status": "done", "created": time.time() - 3 * 86400,
                             "format": fmt, "genre": "quiz", "title": vid, "publish_at": published[vid].isoformat()})
    views = {"OLD": 100, "NEW": 150}

    def get(url, params):
        return {"items": [{"id": v, "statistics": {"viewCount": views[v]}, "status": {"privacyStatus": "public"},
                           "snippet": {"publishedAt": published[v].isoformat().replace("+00:00", "Z")}}
                          for v in params["id"].split(",")]}
    monkeypatch.setattr(ya, "status", lambda: {"connected": True})
    monkeypatch.setattr(ya, "_get", get)
    monkeypatch.setattr(ya, "video_analytics", lambda days=90: {})
    mc.learn(mc.get(ch["id"]), log=lambda *a: None)
    # Ten days on, the old one has piled up lifetime views; the young one was only just published.
    published["OLD"] = now - timedelta(days=10)
    views["OLD"] = 900
    stats = mc.learn(mc.get(ch["id"]), log=lambda *a: None)["stats"]
    assert stats["formats"]["mcq"]["median"] == 100 and stats["formats"]["flags"]["median"] == 150
    assert stats["median"] == 525                                      # what Today shows stays lifetime views
    with ya.use(acct):
        assert next(r for r in ya.uploads() if r["id"] == "OLD")["views_48h"] == 100


def test_learning_still_works_when_analytics_refuses(monkeypatch):
    ch = mc.add("quiz")
    acct = mc.account(ch["id"])
    old = datetime.now(timezone.utc) - timedelta(days=3)
    with ya.use(acct):
        ya._save_upload({"id": "V1", "video_id": "V1", "status": "done", "created": time.time() - 3 * 86400,
                         "format": "mcq", "genre": "quiz", "title": "V1", "publish_at": old.isoformat()})
    monkeypatch.setattr(ya, "status", lambda: {"connected": True})
    monkeypatch.setattr(ya, "_get", lambda url, params: {"items": [{
        "id": "V1", "statistics": {"viewCount": 5}, "status": {"privacyStatus": "public"},
        "snippet": {"publishedAt": old.isoformat().replace("+00:00", "Z")}}]})

    def refuse(days=90):
        raise RuntimeError("Insufficient permission")
    monkeypatch.setattr(ya, "video_analytics", refuse)
    stats = mc.learn(mc.get(ch["id"]), log=lambda *a: None)["stats"]
    assert stats["counted"] == 1 and stats["watched"] is None and "watched" not in stats["formats"]["mcq"]


def test_formats_people_watch_to_the_end_win_over_slightly_more_views():
    assert mc.format_score({"median": 100, "watched": 90}) > mc.format_score({"median": 120, "watched": 40})
    assert mc.format_score({"median": 100}) == 100
    ch = {"jobs": [{"status": "uploaded", "format": f} for f in ("mcq", "flags") for _ in range(mc.MIN_FOR_LEARNING)],
          "stats": {"formats": {"mcq": {"shorts": 9, "median": 120, "watched": 40},
                                "flags": {"shorts": 9, "median": 100, "watched": 90}}}}

    class NoExplore:
        def random(self):
            return 0.99
    assert mc.pick_format(ch, ["mcq", "flags"], rnd=NoExplore()) == "flags"
