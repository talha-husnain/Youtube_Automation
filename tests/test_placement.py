"""Found on the first day with all six channels connected (18-oct-2026): a
card connected to the wrong channel posted there, an outage read as a plain
failure, and a title kept its line break."""
import asyncio
import json
import os
import time

import my_channels as mc
import reminders
import youtube_account as ya


def test_any_exception_names_the_reason_so_an_outage_pauses(monkeypatch):
    import app
    monkeypatch.setitem(app.jobs, "net", {"logs": ["🔁 Gemini call failed (ConnectError); trying again in 20 s.",
                                                   "Traceback (most recent call last):",
                                                   "httpx.ConnectError: [Errno 11001] getaddrinfo failed"]})
    monkeypatch.setitem(app.jobs, "gem", {"logs": ["google.genai.errors.ServerError: 503 UNAVAILABLE. {'error': {}}"]})
    monkeypatch.setitem(app.jobs, "own", {"logs": ["RuntimeError: Not enough reliable sources."]})
    assert app._job_reason("net") == "ConnectError: [Errno 11001] getaddrinfo failed"
    assert app._job_reason("gem").startswith("ServerError: 503")
    assert app._job_reason("own") == "Not enough reliable sources."
    ch = mc.add("music")
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "net", "status": "running", "at": time.time(),
                                                   "day": mc.today()}]))
    monkeypatch.setattr(mc, "failure_reason", app._job_reason)
    mc.refresh_jobs(mc.get(ch["id"]), lambda job: ("failed", []), "out")
    job = mc.get(ch["id"])["jobs"][0]
    assert job["transient"] and mc.get(ch["id"])["paused_until"] > time.time()   # not one of the day's tries


def test_a_title_is_one_line():
    assert ya._clean_title("Babar Azam ka anokha record! \n #shorts  #cricket") == \
        "Babar Azam ka anokha record! #shorts #cricket"
    assert len(ya._clean_title("x " * 200)) <= ya.TITLE_MAX


def _patch_tick(monkeypatch, st, made, uploaded, checked):
    async def make(submit, c, client_fn, log=print, now=None):
        made.append(c["id"])
    monkeypatch.setattr(mc, "make_one", make)
    monkeypatch.setattr(mc, "connected", lambda c: st)
    monkeypatch.setattr(mc, "wants_more", lambda c: True)
    monkeypatch.setattr(mc, "upload_due", lambda c, t: True)
    monkeypatch.setattr(mc, "upload_waiting", lambda c, *a, **k: uploaded.append(c["id"]))
    monkeypatch.setattr(mc, "check_placement", lambda cid, log=print: checked.append(cid))
    monkeypatch.setattr(mc, "engage_pass", lambda *a, **k: None)
    monkeypatch.setattr(mc, "disk_free_gb", lambda: 50.0)


def test_a_fresh_connection_waits_before_making_or_uploading(monkeypatch):
    ch = mc.add("cricket")
    mc._change(ch["id"], lambda c: c.update(last_claim_check=time.time(), last_learn=time.time(),
                                            last_match_check=time.time()))
    st = {"connected": True, "granted_at": int(time.time()) - 60, "channel": {"id": "UCmusic", "title": "Music"}}
    assert mc.settling(st) == st["granted_at"] + mc.CONNECT_HOLD
    assert not mc.settling({**st, "granted_at": int(time.time()) - mc.CONNECT_HOLD - 1})
    assert not mc.settling({"connected": False, "granted_at": int(time.time())})
    made, uploaded, checked = [], [], []
    _patch_tick(monkeypatch, st, made, uploaded, checked)
    asyncio.run(mc.tick(None, lambda j: ("missing", []), "out", None, log=lambda *a: None))
    asyncio.run(mc.tick(None, lambda j: ("missing", []), "out", None, log=lambda *a: None))
    assert made == [] and uploaded == []
    assert checked == [ch["id"]]                        # once per connection, not every minute
    st["granted_at"] = int(time.time()) - mc.CONNECT_HOLD - 1
    asyncio.run(mc.tick(None, lambda j: ("missing", []), "out", None, log=lambda *a: None))
    assert made == [ch["id"]] and uploaded == [ch["id"]]


def test_a_video_is_remembered_with_the_channel_it_was_made_for(monkeypatch):
    ch = mc.add("quiz")
    monkeypatch.setattr(mc, "next_payload", lambda c, f, log: ({"genre": "quiz"},
                                                               {"label": "mcq", "format": "mcq", "topic": ""}))
    monkeypatch.setattr(mc, "connected", lambda c: {"connected": True, "channel": {"id": "UCquiz"}})

    async def submit(payload):
        return "job1"
    asyncio.run(mc.make_one(submit, mc.get(ch["id"]), None, log=lambda *a: None))
    assert mc.get(ch["id"])["jobs"][-1]["yt_channel"] == "UCquiz"


def test_a_video_made_for_another_channel_is_made_again_not_posted(monkeypatch):
    ch = mc.add("cricket")
    topic = "India vs West Indies, 3rd T20I"
    mc._change(ch["id"], lambda c: c.update(used=[topic], ideas=[{"kind": "topic", "text": "Babar's record"}], jobs=[
        {"job_id": "wrong", "status": "done", "format": "match", "topic": topic, "label": topic,
         "at": time.time(), "qa": "ok", "yt_channel": "UCmusic"}]))
    monkeypatch.setattr(ya, "status", lambda: {"connected": True, "channel": {"id": "UCcricket"}})
    monkeypatch.setattr(ya, "upload", lambda *a, **k: __import__("pytest").fail("posted with another channel's end card"))
    mc.upload_waiting(mc.get(ch["id"]), lambda job: ("completed", [{"path": "p"}]), log=lambda *a: None)
    c = mc.get(ch["id"])
    assert c["jobs"][0]["status"] == "skipped" and "another channel" in c["jobs"][0]["error"]
    assert c["ideas"][0] == {"kind": "match", "text": topic} and topic not in c["used"]


def _connect(cid, yid, title):
    path = mc.account(cid)["token"] if cid != "main" else ya.TOKEN_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"refresh_token": "r", "channel": {"id": yid, "title": title}}, f)


def test_an_upload_found_on_another_of_our_channels_goes_on_the_to_do_list(monkeypatch):
    mc.add("cricket")
    mc.add("music")
    _connect("cricket", "UCcricket", "CricRecordz Daily")
    _connect("music", "UCmusic", "Byte Beats Music")
    now = time.time()
    with ya.use(mc.account("cricket")):
        for vid in ("A", "B"):
            ya._save_upload({"id": vid.lower(), "video_id": vid, "status": "done", "title": f"Short {vid}",
                             "created": int(now), "publish_at": "2026-10-18T06:30:00+00:00"})
    # Each token sees only its own private videos.
    where = {"A": ("UCmusic", "private", "2026-10-18T06:30:00Z"), "B": ("UCcricket", "private", "x")}

    def get(url, params):
        mine = ya.status()["channel"]["id"]
        return {"items": [{"id": v, "snippet": {"channelId": where[v][0]},
                           "status": {"privacyStatus": where[v][1], "publishAt": where[v][2]}}
                          for v in params["id"].split(",") if v in where and where[v][0] == mine]}
    monkeypatch.setattr(ya, "_get", get)
    said = []
    marked = mc.check_placement("cricket", log=said.append)
    assert [r["video_id"] for r in marked] == ["A"] and "Byte Beats Music" in said[0]
    away = mc.elsewhere("cricket")
    assert away == [{"title": "Short A", "video_id": "A", "on": "Byte Beats Music",
                     "publish_at": "2026-10-18T06:30:00+00:00"}]
    todo = reminders.things_to_do({"channels": [{"name": "Cricket facts", "connected": True, "elsewhere": away}]})
    assert "studio.youtube.com/video/A/edit" in todo[0] and "Byte Beats Music" in todo[0]
    with ya.use(mc.account("cricket")):
        assert [r["id"] for r in ya.uploads()] == ["a", "b"]          # marked in place, order kept
    where["A"] = ("UCmusic", "private", None)                         # the owner set it to Private
    mc.check_placement("cricket", log=said.append)
    assert mc.elsewhere("cricket") == []


def test_a_short_with_a_silent_line_is_not_made(tmp_path, monkeypatch):
    import pytest
    import short_kit as kit
    calls = []

    def lines(client, items, job_dir, prefix):
        calls.append([i["text"] for i in items])
        return [(None, 0.0) if i["text"] in down else (str(tmp_path / i["text"]), 1.0) for i in items]
    monkeypatch.setattr(kit, "voice_lines", lines)
    down = {"b", "c"}
    with pytest.raises(RuntimeError) as e:
        kit.voice_all(None, [{"text": t} for t in "abc"], str(tmp_path), "q", wait=0)
    assert calls == [["a", "b", "c"], ["b", "c"]] and mc.TRANSIENT.search(str(e.value))
    # The network is back for the second try: every line has its voice.
    monkeypatch.setattr(kit, "voice_lines", lambda client, items, d, p: [
        (str(tmp_path / i["text"]), 1.0) if i["text"] == "a" or p.endswith("r") else (None, 0.0) for i in items])
    assert all(p for p, _ in kit.voice_all(None, [{"text": t} for t in "abc"], str(tmp_path), "q", wait=0))


def test_a_short_without_its_description_is_not_made_or_posted(monkeypatch):
    import pytest
    import seo_copy
    import short_kit as kit
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("SEO_COPY", raising=False)
    tries = []
    monkeypatch.setattr(seo_copy, "apply", lambda clips, *a, **k: tries.append(1) and 0)
    with pytest.raises(RuntimeError) as e:
        kit.seo_or_fail([{}], None, wait=0)
    assert len(tries) == 2 and mc.TRANSIENT.search(str(e.value))
    ch = mc.add("quiz")
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "q", "status": "done", "format": "mcq",
                                                   "at": time.time(), "qa": "ok"}]))
    monkeypatch.setattr(ya, "status", lambda: {"connected": True})
    monkeypatch.setattr(ya, "upload", lambda *a, **k: pytest.fail("posted with an empty description"))
    clip = {"index": 0, "path": "p.mp4", "title": "Quiz", "description": "  ", "tags": []}
    mc.upload_waiting(mc.get(ch["id"]), lambda job: ("completed", [clip]), log=lambda *a: None)
    assert mc.get(ch["id"])["jobs"][0]["status"] == "failed"


def test_a_video_on_another_channel_gets_no_comment_or_playlist_from_this_one():
    import engage
    mc.add("cricket")
    with ya.use(mc.account("cricket")):
        for vid, away in (("A", "Byte Beats Music"), ("B", None)):
            ya._save_upload({"id": vid.lower(), "video_id": vid, "status": "done", "created": int(time.time()),
                             **({"elsewhere": away} if away else {})})
        assert [r["video_id"] for r in engage._live_rows(7)] == ["B"]
