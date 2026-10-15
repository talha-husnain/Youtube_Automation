"""The history channel's daily "Aaj ki tareekh" Short (history_today.py)."""
import json
import time
from datetime import datetime, timedelta

import pytest

import history_today as ht
import history_videos as hv
import my_channels as mc
import youtube_account as ya


def _story(**kw):
    base = dict(found=True, allowed=True, reason="", sacred=False, event="Battle of Plassey", year="1757",
                title="23 June: Plassey ki jang", hook_line="Aaj ke din 1757 mein ek jang ne Hindustan badal diya.",
                beats=[ht.Beat(when="1757", headline="Jang", detail="d", line="Ek line hai yahan par.")] * 4,
                why_line="Is din ke baad angrez yahan ke maalik ban gaye, aaj bhi asar hai.",
                question="Aap kya sochte hain? comment mein batao")
    base.update(kw)
    return ht.Story(**base)


def test_one_daily_short_comes_first_on_top_of_the_long_videos():
    ch = mc.add("history")
    mc._change(ch["id"], lambda c: c.update(per_day=1, used=["today:Battle of Plassey", "Rome"], jobs=[
        {"job_id": "l1", "status": "done", "format": "history", "day": mc.today(), "at": time.time()}]))
    c = mc.get(ch["id"])
    assert mc.today_short_due(c) and mc.wants_more(c)              # the day's long video is made, the Short is extra
    payload, meta = mc.next_payload(c, lambda: None)
    assert payload["history_today"] is True and payload["history_avoid"] == ["Battle of Plassey"]
    assert meta["format"] == "today"
    mc._change(ch["id"], lambda x: x["jobs"].append({"job_id": "t1", "status": "running", "format": "today",
                                                     "day": mc.today(), "at": time.time()}))
    assert not mc.today_short_due(mc.get(ch["id"]))
    assert len(mc._jobs_on(mc.get(ch["id"]), mc.today())) == 1     # not one of the day's long videos
    mc.update(ch["id"], {"daily_short": False})
    mc._change(ch["id"], lambda x: x.update(jobs=[]))
    assert not mc.today_short_due(mc.get(ch["id"]))
    assert not mc.today_short_due(mc.get(mc.add("quiz")["id"]))


def test_the_daily_short_goes_up_on_its_own_day_from_noon_and_is_checked_as_a_short(monkeypatch):
    monkeypatch.setenv("VIDEO_QA", "1")
    import video_qa
    seen = {}
    monkeypatch.setattr(video_qa, "check", lambda path, long=False: seen.update(long=long) or [])
    ch = mc.add("history")
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "t1", "status": "done", "format": "today", "at": 1}]))
    monkeypatch.setattr(ya, "status", lambda: {"connected": True})
    sent = {}

    def upload(path, title, desc, tags, genre, publish_at=None, ai_made=False, meta=None):
        sent.update(genre=genre, at=publish_at)
        return {"status": "done", "video_id": "ToDaY000001", "title": title}
    monkeypatch.setattr(ya, "upload", upload)
    clip = {"index": 0, "path": "p.mp4", "title": "T", "description": "D", "tags": []}
    mc.upload_waiting(mc.get(ch["id"]), lambda job: ("completed", [clip]), log=lambda *a: None)
    now = datetime.now().astimezone()
    assert seen["long"] is False and sent["genre"] == "history_teaser"
    assert sent["at"] >= now.replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
    assert sent["at"] >= now + timedelta(minutes=mc.URGENT_AFTER_MINUTES - 1)


def test_the_story_needs_sources_and_passes_its_fact_check(monkeypatch):
    d = datetime(2026, 6, 23)
    with pytest.raises(RuntimeError, match="No well-sourced event"):
        ht.write(None, d, "@h", research_fn=lambda c, d, a: ("facts", [("a", "u")]))
    answers = iter([_story(), ht.Check(ok=False, problems=["the year is wrong"]), _story(year="1757"),
                    ht.Check(ok=True, problems=[])])
    prompts = []

    def ask(client, schema, prompt, **kw):
        prompts.append(prompt)
        return next(answers)
    monkeypatch.setattr(ht.kit, "ask_json", ask)
    story, facts, sources = ht.write(None, d, "@h", research_fn=lambda c, d, a: ("facts", [("a", "u")] * 3))
    assert story.event == "Battle of Plassey" and "23 June" in prompts[0] and "the year is wrong" in prompts[2]
    assert "Hazrat" in prompts[0]                                    # the long videos' honorifics apply


def test_process_marks_the_job_as_the_daily_short(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    r = TestClient(app_module.app).post("/api/process", json={
        "genre": "history", "history_today": True, "history_avoid": ["Battle of Plassey"], "acknowledged": True},
        headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 200, r.text
    env = app_module.jobs[r.json()["job_id"]]["env"]
    assert env["HISTORY_TODAY"] == "1" and json.loads(env["HISTORY_AVOID"]) == ["Battle of Plassey"]


def test_a_finished_daily_short_puts_its_event_on_the_avoid_list(tmp_path):
    (tmp_path / "x_metadata.json").write_text(json.dumps({"shorts": [{"history": {"today": True,
                                                                                    "event": "Battle of Plassey"}}]}))
    assert mc._used_items(str(tmp_path)) == ["today:Battle of Plassey"]
