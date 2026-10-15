"""Unattended running: lost jobs, YouTube's byte limits, a full disk, the
stay-awake request, and the weekly report (15-oct-2026)."""
import asyncio
import time

import keep_awake
import my_channels as mc
import reminders
import youtube_account as ya


def test_a_job_lost_in_a_server_restart_fails_soon_without_using_a_try():
    ch = mc.add("quiz")
    start = time.time() - mc.LOST_AFTER - 5
    mc._change(ch["id"], lambda c: c.update(per_day=1, jobs=[
        {"job_id": "gone", "status": "running", "at": start, "day": mc.today()},
        {"job_id": "new", "status": "running", "at": time.time() - 30, "day": mc.today()}]))
    mc.refresh_jobs(mc.get(ch["id"]), lambda job: ("missing", []), "out")
    jobs = {j["job_id"]: j for j in mc.get(ch["id"])["jobs"]}
    assert jobs["gone"]["status"] == "failed" and jobs["gone"]["transient"]
    assert jobs["new"]["status"] == "running"                 # just submitted: the server may not list it yet
    assert not mc.get(ch["id"]).get("paused_until")           # a restart is not an outage to wait out


def test_descriptions_are_cut_by_bytes_and_tags_count_their_quotes():
    text = "😀" * 2000                                         # 2,000 characters, 8,000 bytes
    out = ya._clean_description(text)
    assert len(out.encode("utf-8")) <= ya.DESCRIPTION_MAX and out == "😀" * (ya.DESCRIPTION_MAX // 4)
    assert ya._clean_description("<b>ok</b>") == "bok/b"
    tags = ya._tags(["two words"] * 100 + ["a,b"])
    assert sum(len(t) + 1 + (2 if " " in t else 0) for t in tags) <= ya.TAGS_MAX
    assert all("," not in t for t in ya._tags(["a,b"]))


def test_no_new_video_starts_on_a_full_disk(monkeypatch):
    ch = mc.add("quiz")
    mc._change(ch["id"], lambda c: c.update(sample_wanted=1))
    made = []

    async def make(submit, c, client_fn, log=print, now=None):
        made.append(c["id"])
    monkeypatch.setattr(mc, "make_one", make)
    monkeypatch.setattr(mc, "connected", lambda c: {"connected": False})
    monkeypatch.setattr(mc, "engage_pass", lambda *a, **k: None)
    monkeypatch.setattr(mc, "disk_free_gb", lambda: 2.0)
    said = []
    asyncio.run(mc.tick(None, lambda j: ("missing", []), "out", None, log=said.append))
    assert made == [] and "GB free" in said[0]
    monkeypatch.setattr(mc, "disk_free_gb", lambda: 50.0)
    asyncio.run(mc.tick(None, lambda j: ("missing", []), "out", None, log=said.append))
    assert made == [ch["id"]]
    todo = reminders.things_to_do({"channels": [], "totals": {"disk_free_gb": 3.2}})
    assert "3.2 GB free" in todo[0]


def test_the_laptop_stays_awake_only_while_working_and_on_the_charger(monkeypatch):
    calls = []
    monkeypatch.setattr(keep_awake, "_set", lambda flags: calls.append(flags) or True)
    monkeypatch.setattr(keep_awake, "_state", {"awake": False, "why": "idle"})
    monkeypatch.setattr(keep_awake, "on_charger", lambda: True)
    assert keep_awake.refresh(True)["awake"] is True
    assert calls == [keep_awake.ES_CONTINUOUS | keep_awake.ES_SYSTEM_REQUIRED]
    keep_awake.refresh(True)
    assert len(calls) == 1                                    # asked once, not every minute
    assert keep_awake.refresh(False)["awake"] is False and calls[-1] == keep_awake.ES_CONTINUOUS
    with keep_awake.task():                                   # an upload outside any job
        assert keep_awake.refresh(False)["awake"] is True
    monkeypatch.setattr(keep_awake, "on_charger", lambda: False)
    assert keep_awake.refresh(True)["awake"] is False         # on battery it may sleep
    monkeypatch.setenv("KEEP_AWAKE", "0")
    assert keep_awake.refresh(True)["why"].startswith("off")


def test_the_weekly_report_lists_each_channel_and_its_best_video():
    now = time.time()
    rows = {"main": [{"video_id": "a" * 11, "status": "done", "created": now - 86400, "title": "Funny one #shorts"},
                     {"video_id": "b" * 11, "status": "done", "created": now - 3600, "title": "Better one"},
                     {"video_id": "c" * 11, "status": "done", "created": now - 9 * 86400, "title": "Old"}],
            "q": [{"video_id": "d" * 11, "status": "failed", "created": now}]}
    views = {"a" * 11: 40, "b" * 11: 1200, "c" * 11: 9999}
    text = reminders.week_text({"channels": [{"id": "main", "name": "Punchline Bazaar"}, {"id": "q", "name": "Quiz"}]},
                               now, rows_fn=lambda cid: (rows[cid], lambda r: views.get(r["video_id"], 0)))
    assert text.splitlines()[0] == "This week: 2 videos, 1,240 views on them so far."
    assert "Punchline Bazaar: 2 videos, 1,240 views. Best: Better one (1,200)." in text and "Quiz" not in text
    assert reminders.week_text({"channels": []}, now) == "No videos went up this week."


def test_reminders_go_to_the_phone_too_when_telegram_is_connected(monkeypatch):
    import telegram_notify
    sent = []
    monkeypatch.setattr(telegram_notify, "status", lambda: {"connected": True})
    monkeypatch.setattr(telegram_notify, "send_text", lambda text: sent.append(text))
    monkeypatch.setattr(reminders, "week_text", lambda today, now=None: "This week: 3 videos")
    sunday = time.mktime((2026, 10, 18, 21, 45, 0, 0, 0, -1))           # a Sunday, past SUMMARY_AT
    today = {"channels": [], "totals": {"made_today": 2, "uploaded_today": 1, "views": None}}
    got = reminders.tick(lambda: today, lambda *a: None, now=sunday)
    assert got == ["summary", "week"]
    assert sent[0].startswith("Shortkaar today") and sent[1] == "Shortkaar this week\nThis week: 3 videos"
    reminders.update({"phone": False})
    sent.clear()
    reminders.tick(lambda: today, lambda *a: None, now=sunday + 86400)
    assert sent == []
