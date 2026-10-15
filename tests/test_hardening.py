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


def _echo_srt(tmp_path):
    srt = tmp_path / "c.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:03,000\nChaar September ko ek larke\n\n"
                   "2\n00:00:03,000 --> 00:00:06,000\nko takht se utaara gaya. Woh aakhri\n\n"
                   "3\n00:00:06,000 --> 00:00:09,000\nshehanshah tha.\n\n", encoding="utf-8")
    return srt


def test_english_subtitles_are_translated_by_sentence_at_the_same_times(tmp_path):
    import history_videos as hv
    srt = _echo_srt(tmp_path)
    sentences = hv.srt_sentences(hv.read_srt(str(srt)))
    assert [s[0] for s in sentences] == ["Chaar September ko ek larke ko takht se utaara gaya.",
                                        "Woh aakhri shehanshah tha."]
    assert sentences[0][1] == 0 and 3 < sentences[0][2] < 6 and sentences[1][1] == sentences[0][2]
    asked = []

    def ask(client, schema, prompt, **kw):
        asked.append(prompt)
        if len(asked) == 1:                      # drops one, and a note is not a translation
            return hv.Cues(lines=[hv.Cue(n=1, en="(I must translate only this line)")])
        return hv.Cues(lines=[hv.Cue(n=1, en="On 4 September a boy was removed from the throne."),
                              hv.Cue(n=2, en="He was the last emperor.")])
    out = hv.translate_srt(None, str(srt), str(tmp_path / "en.srt"), ask=ask)
    cues = hv.read_srt(out)
    assert [c[2] for c in cues] == ["On 4 September a boy was removed from the throne.", "He was the last emperor."]
    assert cues[0][0] == 0 and cues[-1][1] == 9 and len(asked) == 2
    assert hv.translate_srt(None, str(srt), str(tmp_path / "x.srt"),
                            ask=lambda *a, **k: hv.Cues(lines=[])) is None      # nothing back: no track


def test_a_long_sentence_is_shown_in_even_pieces(tmp_path):
    import history_videos as hv
    text = "The boy was Romulus Augustulus, who proved to be the last emperor of the Western Roman Empire."
    parts = hv._pieces(text, 0, 6)
    assert len(parts) == 2 and all(len(p[0]) <= hv.EN_CUE_CHARS for p in parts)
    assert parts[0][2] == parts[1][1] and parts[1][2] == 6 and min(len(p[0]) for p in parts) > 30


def test_the_english_track_goes_up_after_the_urdu_one(tmp_path, monkeypatch):
    srt = _echo_srt(tmp_path)
    ch = mc.add("history")
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "L", "status": "done", "format": "history", "at": 1}]))
    monkeypatch.setattr(ya, "status", lambda: {"connected": True})
    monkeypatch.setattr(ya, "upload", lambda *a, **k: {"status": "done", "video_id": "LoNg0000001", "title": "T"})
    monkeypatch.setattr(ya, "long_uploads", lambda: "eligible", raising=False)
    tracks = []
    monkeypatch.setattr(ya, "add_captions", lambda row, path, language="ur", key="captions":
                        tracks.append((language, key)) or row)
    clip = {"index": 0, "path": "p.mp4", "title": "T", "description": "D", "tags": [],
            "captions": str(srt), "captions_language": "ur", "captions_extra": [(str(srt), "en")]}
    mc.upload_waiting(mc.get(ch["id"]), lambda job: ("completed", [clip]), log=lambda *a: None)
    assert tracks == [("ur", "captions"), ("en", "captions_en")]


def test_each_caption_track_keeps_its_own_status(tmp_path, monkeypatch):
    srt = _echo_srt(tmp_path)
    ya.spend(9000 - ya.quota_used() + 1)
    row = ya.add_captions({"id": "r1", "video_id": "LONG1", "status": "done"}, str(srt), "en", key="captions_en")
    assert row["captions_en"] == "skipped" and "captions" not in row


class _Resp:
    def __init__(self, code, data=None, headers=None):
        self.status_code, self._data, self.headers = code, data or {}, headers or {}
        self.text = str(data)

    def json(self):
        return self._data


def test_a_dropped_upload_resumes_where_youtube_stopped(tmp_path, monkeypatch):
    import httpx
    video = tmp_path / "v.mp4"
    video.write_bytes(bytes(range(256)) * 4)                      # 1,024 bytes
    ya._write(ya.TOKEN_FILE, {"access_token": "tok", "refresh_token": "r", "expires_at": 9e12})
    monkeypatch.setattr(ya.httpx, "post", lambda *a, **k: _Resp(200, {}, {"location": "https://up/session"}))
    sent, calls = [], []

    def put(url, content=None, headers=None, timeout=None, **kw):
        calls.append(dict(headers))
        if headers.get("Content-Range", "").startswith("bytes */"):
            return _Resp(308, headers={"range": "bytes=0-399"})          # YouTube has the first 400
        body = b"".join(content)
        if len(calls) == 1:
            raise httpx.ConnectError("the network dropped")
        sent.append(body)
        return _Resp(200, {"id": "ReSuMeD0001", "status": {"privacyStatus": "public"}})
    monkeypatch.setattr(ya.httpx, "put", put)
    waits = []
    monkeypatch.setattr(ya.time, "sleep", waits.append)
    row = ya.upload(str(video), "T", "D", genre="history")
    assert row["status"] == "done" and row["video_id"] == "ReSuMeD0001"
    assert calls[1] == {"Content-Range": "bytes */1024", "Content-Length": "0"}
    assert calls[2]["Content-Range"] == "bytes 400-1023/1024" and calls[2]["Content-Length"] == "624"
    assert sent == [video.read_bytes()[400:]] and waits == [ya.RESUME_WAITS[0]]


def test_an_upload_that_stays_offline_fails_after_the_waits(tmp_path, monkeypatch):
    import httpx
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 100)
    ya._write(ya.TOKEN_FILE, {"access_token": "tok", "refresh_token": "r", "expires_at": 9e12})
    monkeypatch.setattr(ya.httpx, "post", lambda *a, **k: _Resp(200, {}, {"location": "https://up/session"}))

    def put(url, content=None, headers=None, timeout=None, **kw):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(ya.httpx, "put", put)
    waits = []
    monkeypatch.setattr(ya.time, "sleep", waits.append)
    row = ya.upload(str(video), "T", "D")
    assert row["status"] == "failed" and "offline" in row["error"] and waits == list(ya.RESUME_WAITS)


def test_a_damaged_state_file_comes_back_from_its_backup(tmp_path, monkeypatch):
    import os
    import safe_json
    path = str(tmp_path / "state.json")
    safe_json.write(path, {"channels": [1]})
    assert not os.path.exists(path + ".bak")                  # nothing to back up yet
    safe_json.write(path, {"channels": [1, 2]})
    assert safe_json.read(path + ".bak", {}) == {"channels": [1]}
    safe_json.write(path, {"channels": [1, 2, 3]})
    assert safe_json.read(path + ".bak", {}) == {"channels": [1]}      # at most once an hour
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"channels": [1, 2, 3')                            # a write cut short
    assert safe_json.read(path, {}) == {"channels": [1]}
    os.utime(path + ".bak", (1, 1))                                  # an hour later...
    safe_json.write(path, {"channels": [9]})
    assert safe_json.read(path + ".bak", {}) == {"channels": [1]}      # ...the damaged file is not backed up
    os.remove(path)
    assert safe_json.read(path, {}) == {}                             # missing is a fresh start, not damage
    ch = mc.add("quiz")
    with open(mc.STATE_FILE, "w", encoding="utf-8") as f:
        f.write("{")
    with open(mc.STATE_FILE + ".bak", "w", encoding="utf-8") as f:
        f.write('{"channels": [{"id": "%s", "kind": "quiz", "name": "Q"}]}' % ch["id"])
    assert [c["id"] for c in mc.channels()] == [ch["id"]]
