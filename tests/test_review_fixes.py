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
