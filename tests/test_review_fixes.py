"""Fixes from the review of 15-oct-2026 (moment Shorts, quality check, owner ideas)."""
import time
from datetime import datetime, timedelta, timezone

import pytest

import history_videos as hv
import my_channels as mc
import video_qa
import youtube_account as ya


def test_shorts_scheduled_for_the_same_minute_are_spread_out():
    at = datetime(2026, 10, 16, 18, 15, tzinfo=timezone.utc)
    rows = [{"status": "done", "publish_at": at.isoformat()},
            {"status": "done", "publish_at": (at + timedelta(minutes=40)).isoformat()},
            {"status": "failed", "publish_at": (at + timedelta(minutes=80)).isoformat()}]
    assert mc._clear_of(at, rows) == at + timedelta(minutes=80)
    assert mc._clear_of(at + timedelta(hours=5), rows) == at + timedelta(hours=5)


def test_a_long_videos_folder_goes_once_no_short_can_be_made_from_it():
    ch = mc.add("history")
    mc._change(ch["id"], lambda c: c.update(jobs=[
        {"job_id": "old", "status": "uploaded", "format": "history", "teaser": "started",
         "at": time.time() - mc.TEASER_WINDOW - 60, "video_id": "x" * 11}]))
    assert mc.keeps("old", ch["id"], 3600) is False


def test_a_checker_that_cannot_run_waits_instead_of_failing_the_video(monkeypatch):
    monkeypatch.setenv("VIDEO_QA", "1")
    ch = mc.add("quiz")
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "q1", "status": "done", "format": "mcq", "at": 1}]))
    monkeypatch.setattr(ya, "status", lambda: {"connected": True})
    monkeypatch.setattr(ya, "upload", lambda *a, **k: pytest.fail("not checked, so not uploaded"))

    def slow(path, long=False):
        raise video_qa.Unchecked("ffmpeg did not finish (TimeoutExpired)")
    monkeypatch.setattr(video_qa, "check", slow)
    clip = {"index": 0, "path": "p.mp4", "title": "T", "description": "D", "tags": []}
    for _ in range(mc.QA_TRIES - 1):
        mc.upload_waiting(mc.get(ch["id"]), lambda job: ("completed", [clip]), log=lambda *a: None)
        assert mc.get(ch["id"])["jobs"][0]["status"] == "done"          # waits for the next pass
    mc.upload_waiting(mc.get(ch["id"]), lambda job: ("completed", [clip]), log=lambda *a: None)
    job = mc.get(ch["id"])["jobs"][0]
    assert job["status"] == "failed" and "could not run 3 times" in job["error"]


def test_a_missing_ffprobe_is_unchecked_not_broken(monkeypatch):
    def gone(*a, **k):
        raise FileNotFoundError("ffprobe")
    monkeypatch.setattr(video_qa.subprocess, "run", gone)
    with pytest.raises(video_qa.Unchecked):
        video_qa.check("x.mp4")


def test_a_fresh_match_result_stays_ahead_of_the_owners_topic_and_replaces_a_typed_one(monkeypatch):
    ch = mc.add("cricket")
    mc._change(ch["id"], lambda c: c.update(ideas=[{"kind": "match", "text": "Pakistan vs India, Asia Cup",
                                                    "urgent": True}, {"kind": "topic", "text": "Fastest fifties"}]))
    mc.add_idea(ch["id"], "Babar vs Kohli")
    assert [i["text"] for i in mc.get(ch["id"])["ideas"]] == ["Pakistan vs India, Asia Cup", "Babar vs Kohli",
                                                              "Fastest fifties"]
    ch2 = mc.add("cricket")
    mc.add_idea(ch2["id"], "Australia vs England, Ashes 2nd Test")
    import cricket_shorts
    monkeypatch.setattr(cricket_shorts, "grounded", lambda client, prompt: (
        "MATCH: Australia vs England, Ashes, 2nd Test, Adelaide", []))
    new = mc.match_watch(mc.get(ch2["id"]), lambda: None, log=lambda *a: None, now=time.time() + 10 ** 6)
    ideas = mc.get(ch2["id"])["ideas"]
    assert len(new) == 1 and ideas[0]["urgent"] and len(ideas) == 1      # the typed one is replaced


def test_blocked_videos_are_never_linked():
    rows = [{"genre": "history", "status": "done", "video_id": "BLOCKEDVID1", "title": "Hit", "views": 9000,
             "blocked": 249},
            {"genre": "history", "status": "done", "video_id": "FINEVIDEO01", "title": "Fine", "views": 10}]
    desc = hv.watch_next("S\n\n#history", rows)
    assert "FINEVIDEO01" in desc and "BLOCKEDVID1" not in desc
    rows[0].update(series="Rome", series_part=1)
    assert hv.series_rows(rows, "Rome") == {}


def test_english_set_up_lines_keep_the_pronoun():
    assert hv._no_roman("Then I tell you what Yazid I did", "english") == "Then I tell you what Yazid I did"
    assert hv._no_roman("Phir Yazid I ne faisla kiya", "urdu") == "Phir Yazid ne faisla kiya"


def test_a_held_video_waits_its_review_hours_and_a_match_result_does_not(monkeypatch):
    ch = mc.add("cricket")
    mc.update(ch["id"], {"review_hours": 6})
    now = time.time()
    mc._change(ch["id"], lambda c: c.update(jobs=[
        {"job_id": "a", "status": "done", "format": "topic", "at": now - 600, "done_at": now - 600},
        {"job_id": "b", "status": "done", "format": "match", "at": now - 600, "done_at": now - 600, "urgent": True},
        {"job_id": "c", "status": "done", "format": "topic", "at": now - 8 * 3600, "done_at": now - 7 * 3600}]))
    monkeypatch.setattr(ya, "status", lambda: {"connected": True})
    went = []

    def upload(path, title, desc, tags, genre, publish_at=None, ai_made=False, meta=None):
        went.append(meta["job_id"])
        return {"status": "done", "video_id": "X" * 11, "title": title}
    monkeypatch.setattr(ya, "upload", upload)
    clip = {"index": 0, "path": "p.mp4", "title": "T", "description": "D", "tags": []}
    mc.upload_waiting(mc.get(ch["id"]), lambda job: ("completed", [clip]), log=lambda *a: None)
    assert sorted(went) == ["b", "c"]                    # "a" still has 5 h 50 min to be watched
    assert mc.get(ch["id"])["review_hours"] == 6
    mc.update(ch["id"], {"review_hours": 99})
    assert mc.get(ch["id"])["review_hours"] == mc.REVIEW_MAX_HOURS


def test_finished_videos_are_stamped_and_telegram_hears_of_held_ones(monkeypatch):
    import telegram_notify
    ch = mc.add("quiz")
    mc.update(ch["id"], {"review_hours": 2})
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "q", "status": "running", "at": time.time()}]))
    monkeypatch.setattr(telegram_notify, "status", lambda: {"connected": True})
    said = []
    monkeypatch.setattr(telegram_notify, "send_text", lambda text, **kw: said.append(text))
    clip = {"title": "Quiz #3"}
    mc.refresh_jobs(mc.get(ch["id"]), lambda job: ("completed", [clip]), "out")
    job = mc.get(ch["id"])["jobs"][0]
    assert job["status"] == "done" and job["done_at"] > 0
    assert len(said) == 1 and "Quiz #3" in said[0] and "2 h" in said[0]


def test_a_quota_or_network_failure_pauses_the_channel_without_using_a_try():
    ch = mc.add("quiz")
    mc._change(ch["id"], lambda c: c.update(per_day=1, jobs=[{"job_id": "q", "status": "running", "at": time.time(),
                                                              "day": mc.today()}]))
    mc.failure_reason = lambda job_id: "429 RESOURCE_EXHAUSTED: You exceeded your current quota"
    try:
        mc.refresh_jobs(mc.get(ch["id"]), lambda job: ("failed", []), "out")
    finally:
        mc.failure_reason = None
    c = mc.get(ch["id"])
    assert c["jobs"][0]["transient"] and c["paused_until"] > time.time() + 1700
    assert mc.wants_more(c) is False                                  # paused
    mc._change(ch["id"], lambda x: x.update(paused_until=time.time() - 1))     # the pause is over
    mc._change(ch["id"], lambda x: x["jobs"].append({"job_id": "q2", "status": "failed", "day": mc.today(),
                                                     "at": time.time(), "transient": True}))
    assert mc.wants_more(mc.get(ch["id"])) is True        # two outage failures, still a try left
    mc._change(ch["id"], lambda x: x["jobs"].append({"job_id": "q3", "status": "failed", "day": mc.today(),
                                                     "at": time.time(), "error": "Only 1 of the questions passed"}))
    mc._change(ch["id"], lambda x: x["jobs"].append({"job_id": "q4", "status": "failed", "day": mc.today(),
                                                     "at": time.time(), "error": "Only 1 of the questions passed"}))
    assert mc.wants_more(mc.get(ch["id"])) is False       # real failures still count
    assert not mc.TRANSIENT.search("Not enough reliable sources for this topic (2).")


def test_history_videos_stay_under_15_minutes_until_the_channel_is_verified(monkeypatch):
    ch = mc.add("history")
    mc.update(ch["id"], {"minutes": 25})
    monkeypatch.setattr(ya, "status", lambda: {"connected": True})
    asked = []
    monkeypatch.setattr(ya, "long_uploads", lambda: asked.append(1) or "eligible")
    assert mc.long_minutes(mc.get(ch["id"])) == mc.UNVERIFIED_MINUTES
    assert mc.long_minutes(mc.get(ch["id"])) == mc.UNVERIFIED_MINUTES and len(asked) == 1     # asked every 6 h
    monkeypatch.setattr(ya, "long_uploads", lambda: "allowed")
    later = time.time() + mc.LONG_CHECK_EVERY + 1
    assert mc.long_minutes(mc.get(ch["id"]), now=later) == 25
    monkeypatch.setattr(ya, "long_uploads", lambda: (_ for _ in ()).throw(RuntimeError("quota")))
    assert mc.long_minutes(mc.get(ch["id"]), now=later + mc.LONG_CHECK_EVERY + 1) == 25     # unknown keeps it
    mc.update(ch["id"], {"minutes": 10})
    assert mc.long_minutes(mc.get(ch["id"])) == 10
