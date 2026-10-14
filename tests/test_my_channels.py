"""The owner's other channels: separate Google tokens and uploads, their own
Shorts, one job at a time, uploads into their own times, and the pure parts
of the quiz, song and player-photo makers."""
import asyncio
import json
import os
import time
from datetime import timezone

import pytest

import my_channels as mc
import youtube_account as ya


@pytest.fixture(autouse=True)
def _main_token(tmp_path, monkeypatch):
    monkeypatch.setattr(ya, "TOKEN_FILE", str(tmp_path / "main_token.json"))
    monkeypatch.setattr(ya, "UPLOADS_FILE", str(tmp_path / "main_uploads.json"))


def _connect(cid, channel_id="UC_other", title="Other"):
    acct = mc.account(cid) if cid != "main" else None
    with ya.use(acct):
        ya._write(ya.token_file(), {"access_token": "t", "refresh_token": "r", "expires_at": 9e12,
                                    "channel": {"id": channel_id, "title": title, "handle": "@other"}})


# ------------------------------------------------------------- accounts

def test_each_channel_has_its_own_token_and_uploads():
    ch = mc.add("cricket")
    _connect("main", "UC_main", "Punchline Bazaar")
    with ya.use(mc.account(ch["id"])):
        assert ya.status()["connected"] is False
        ya._save_upload({"id": "a", "publish_at": "2026-10-15T08:00:00+00:00", "status": "done"})
    assert ya.status()["connected"] is True and ya.uploads() == []
    with ya.use(mc.account(ch["id"])):
        assert [r["id"] for r in ya.uploads()] == ["a"]
    assert ya.token_file() == ya.TOKEN_FILE


def test_sign_in_remembers_the_channel_and_a_refused_one_restores_the_old_token(monkeypatch):
    monkeypatch.setenv("YT_CLIENT_ID", "id")
    monkeypatch.setenv("YT_CLIENT_SECRET", "secret")
    ch = mc.add("quiz")
    url = ya.auth_url("http://localhost:5173", mc.account(ch["id"]))
    assert "select_account+consent" in url
    state = url.split("state=")[1].split("&")[0]

    class R:
        status_code = 200

        def json(self):
            return {"access_token": "new", "refresh_token": "r2", "expires_in": 3600,
                    "refresh_token_expires_in": 604799}
    monkeypatch.setattr(ya.httpx, "post", lambda *a, **k: R())
    monkeypatch.setattr(ya, "channel", lambda: {"id": "UC_main", "title": "Punchline Bazaar"})
    with pytest.raises(RuntimeError, match="already connected"):
        ya.finish_connect("code", state, lambda me, acct: "That is Punchline Bazaar, already connected")
    assert not os.path.exists(mc.account(ch["id"])["token"])
    # Accepted: saved for that channel, not the main one, with its expiry.
    url = ya.auth_url("", mc.account(ch["id"]))
    me = ya.finish_connect("code", url.split("state=")[1].split("&")[0], lambda me, acct: None)
    assert me["id"] == "UC_main" and not os.path.exists(ya.TOKEN_FILE)
    with ya.use(mc.account(ch["id"])):
        st = ya.status()
    assert st["connected"] and st["expires"] > time.time() + 6 * 86400


def test_same_youtube_channel_cannot_be_connected_twice(monkeypatch):
    app_module = pytest.importorskip("app")
    _connect("main", "UC_main", "Punchline Bazaar")
    ch = mc.add("cricket")
    why = app_module._refuse_same_channel({"id": "UC_main", "title": "Punchline Bazaar"}, mc.account(ch["id"]))
    assert "already connected here as your main channel" in why
    assert app_module._refuse_same_channel({"id": "UC_new"}, mc.account(ch["id"])) is None


# ------------------------------------------------------------- settings

def test_channels_are_added_kept_in_range_and_removed():
    a, b = mc.add("cricket"), mc.add("cricket")
    assert (a["id"], b["id"]) == ("cricket", "cricket2") and a["per_day"] == 8 and len(a["post_times"]) == 8
    ch = mc.update("cricket", {"per_day": 40, "post_times": ["9:00", "bad", "23:30", "09:00"],
                               "handle": "cricket facts", "color": "#abcdef", "enabled": 0})
    assert ch["per_day"] == mc.MAX_PER_DAY and ch["post_times"] == ["09:00", "23:30"]
    assert ch["handle"] == "@cricketfacts" and ch["color"] == "#ABCDEF" and ch["enabled"] is False
    with pytest.raises(ValueError):
        mc.add("cooking")
    os.makedirs(mc.folder("cricket2"), exist_ok=True)
    mc.remove("cricket2")
    assert mc.get("cricket2") is None and not os.path.exists(mc.folder("cricket2"))


def test_formats_are_each_tried_then_the_best_wins_most_of_the_time():
    import random
    ch = {"jobs": [{"status": "uploaded", "format": "mcq"}] * 3 + [{"status": "uploaded", "format": "riddle"}] * 3,
          "stats": {}}
    assert mc.pick_format(ch, ["mcq", "riddle", "math"]) == "math"
    ch["jobs"] += [{"status": "uploaded", "format": "math"}] * 3
    ch["stats"] = {"formats": {"mcq": {"shorts": 5, "median": 90}, "riddle": {"shorts": 4, "median": 300},
                               "math": {"shorts": 3, "median": 40}}}
    rnd = random.Random(1)
    picks = [mc.pick_format(ch, ["mcq", "riddle", "math"], rnd) for _ in range(200)]
    assert picks.count("riddle") > 140 and set(picks) == {"mcq", "riddle", "math"}


def test_wants_more_counts_today_tries_and_the_waiting_pile():
    day = mc.today()
    ch = {"enabled": True, "per_day": 2, "jobs": [{"day": day, "status": "uploaded"}]}
    assert mc.wants_more(ch)
    ch["jobs"].append({"day": day, "status": "running"})
    assert not mc.wants_more(ch)   # one at a time
    ch["jobs"][-1]["status"] = "failed"
    ch["jobs"] += [{"day": day, "status": "failed"}] * 2
    assert not mc.wants_more(ch)   # 4 tries for 2 Shorts: stop for today
    old = {"enabled": True, "per_day": 2, "jobs": [{"day": "2000-01-01", "status": "done"}] * 2}
    assert not mc.wants_more(old)  # a day's worth still waits to upload


# ------------------------------------------------------------- jobs

def _job_dir(output_dir, job_id, short):
    d = output_dir / job_id
    d.mkdir(parents=True)
    (d / "Quiz_1_metadata.json").write_text(json.dumps({"shorts": [short]}), encoding="utf-8")


def test_finished_jobs_wait_and_record_what_they_used(tmp_path):
    ch = mc.add("quiz")
    now = time.time()
    rows = [{"job_id": "j1", "status": "running", "at": now, "day": mc.today(), "format": "mcq"},
            {"job_id": "j2", "status": "running", "at": now, "day": mc.today()},
            {"job_id": "j3", "status": "running", "at": now - 4000, "day": mc.today()}]
    mc._change(ch["id"], lambda c: c.update(jobs=rows))
    _job_dir(tmp_path, "j1", {"quiz": {"questions": ["Q1?", "Q2?"]}})
    states = {"j1": ("completed", [{"index": 0}]), "j2": ("failed", []), "j3": ("processing", [])}
    ch = mc.refresh_jobs(mc.get(ch["id"]), lambda j: states[j], str(tmp_path), now)
    assert [j["status"] for j in ch["jobs"]] == ["done", "failed", "failed"]
    assert ch["used"] == ["Q1?", "Q2?"] and ch["jobs"][2]["error"] == "took too long"
    assert mc.keeps("j1", ch["id"], 3600) and not mc.keeps("j2", ch["id"], 3600)
    assert not mc.keeps("j1", ch["id"], 8 * 86400)


def test_a_skipped_short_never_uploads_and_makes_room_for_another():
    ch = mc.add("music")
    day = mc.today()
    mc._change(ch["id"], lambda c: c.update(per_day=1, jobs=[{"job_id": "a", "status": "done", "day": day},
                                                             {"job_id": "b", "status": "uploaded", "day": day}]))
    assert not mc.skip(ch["id"], "b") and mc.skip(ch["id"], "a")
    c = mc.get(ch["id"])
    assert [j["status"] for j in c["jobs"]] == ["skipped", "uploaded"] and not mc.waiting(c)
    assert not mc.keeps("a", ch["id"], 60)


def test_uploads_go_into_the_channels_own_times_and_stop_at_the_limit(monkeypatch, tmp_path):
    ch = mc.add("cricket")
    _connect(ch["id"])
    jobs = [{"job_id": f"j{k}", "status": "done", "at": k, "day": mc.today(), "format": "topic",
             "topic": f"t{k}"} for k in range(3)]
    mc._change(ch["id"], lambda c: c.update(jobs=jobs))
    sent = []

    def upload(path, title, desc, tags, genre, publish_at=None, ai_made=False, meta=None):
        sent.append((title, genre, publish_at, meta["channel"]))
        if len(sent) == 3:
            return {"status": "failed", "error": ya.UPLOAD_LIMIT_TEXT}
        row = {"id": f"r{len(sent)}", "status": "done", "video_id": f"V{len(sent)}", "title": title,
               "publish_at": publish_at.astimezone(timezone.utc).isoformat()}
        ya._save_upload(row)
        return row
    monkeypatch.setattr(ya, "upload", upload)
    clips = lambda j: ("completed", [{"index": 0, "path": "x.mp4", "title": j, "description": "",
                                      "tags": [], "seconds": 40}])
    got = mc.upload_waiting(mc.get(ch["id"]), clips, lambda *a: None)
    assert got == {"done": 2, "limit": True}
    assert [s[1] for s in sent] == ["cricket"] * 3 and all(s[3] == ch["id"] for s in sent)
    assert sent[0][2] != sent[1][2]   # two different posting times
    assert sent[0][2].strftime("%H:%M") in mc.get(ch["id"])["post_times"]
    c = mc.get(ch["id"])
    assert [j["status"] for j in c["jobs"]] == ["uploaded", "uploaded", "done"]
    assert c["upload_paused_until"] > time.time() + 2 * 3600
    assert not mc.upload_due(c)
    # The main channel saw none of it.
    assert ya.uploads() == []


def test_the_loop_makes_one_short_for_the_channel_furthest_behind(monkeypatch, tmp_path):
    a, b, c = mc.add("cricket"), mc.add("quiz"), mc.add("music")
    for ch in (a, b):
        _connect(ch["id"], "UC_" + ch["id"])
    mc._change(a["id"], lambda x: x.update(jobs=[{"job_id": "old", "status": "uploaded", "day": mc.today()}]))
    submitted = []

    async def submit(payload):
        submitted.append(payload)
        return "job-new"
    monkeypatch.setattr(mc, "next_payload", lambda ch, client_fn, log=print: (
        {**mc._look(ch), "genre": mc.KINDS[ch["kind"]]["genre"]}, {"label": "x", "format": "mcq", "topic": ""}))
    for ch in (a, b, c):
        mc._change(ch["id"], lambda x: x.update(last_learn=time.time(), last_claim_check=time.time()))
    asyncio.run(mc.tick(submit, lambda j: ("processing", []), str(tmp_path), lambda: None, lambda *x: None))
    # quiz is furthest behind (0 of 8); music is not connected, so it makes nothing.
    assert len(submitted) == 1 and submitted[0]["channel"] == b["id"] and submitted[0]["genre"] == "quiz"
    assert submitted[0]["frame_handle"] == "@other"
    asyncio.run(mc.tick(submit, lambda j: ("processing", []), str(tmp_path), lambda: None, lambda *x: None))
    assert len(submitted) == 1   # still running: nothing else starts


# ------------------------------------------------------------- app

def test_channel_jobs_stay_out_of_the_main_ready_to_post(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    import post_queue
    monkeypatch.setattr(post_queue, "since", lambda: 0)
    for job_id, channel in (("main1", None), ("ck1", "cricket")):
        d = tmp_path / job_id
        d.mkdir()
        (d / "Short_metadata.json").write_text(json.dumps({"shorts": [{"start": 0, "end": 30}]}))
        (d / ".source.json").write_text(json.dumps({"genre": "comedy", "channel": channel}))
    monkeypatch.setattr(app_module, "_canonical_clip_file", lambda p, b, i: "Short_clip_1.mp4")
    for job_id in ("main1", "ck1"):
        (tmp_path / job_id / "Short_clip_1.mp4").write_bytes(b"x")
    assert {c["job_id"] for c in app_module._queue_clips()} == {"main1"}


def test_channel_api_adds_edits_and_refuses_unknown(monkeypatch):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    c = TestClient(app_module.app)
    r = c.post("/api/my-channels", json={"kind": "music", "name": "Night Songs"})
    assert r.status_code == 200 and r.json()["id"] == "music" and r.json()["youtube"]["connected"] is False
    assert c.post("/api/my-channels", json={"kind": "nope"}).status_code == 400
    r = c.put("/api/my-channels/music", json={"per_day": 9})
    assert r.json()["per_day"] == 9
    rows = c.get("/api/my-channels").json()
    assert [x["id"] for x in rows["channels"]] == ["main", "music"] and "quiz" in rows["kinds"]
    assert c.put("/api/my-channels/nope", json={}).status_code == 404
    monkeypatch.setenv("YT_CLIENT_ID", "id")
    monkeypatch.setenv("YT_CLIENT_SECRET", "s")
    r = c.get("/api/youtube/connect", params={"channel": "music"}, follow_redirects=False)
    assert r.status_code in (302, 307) and "accounts.google.com" in r.headers["location"]
    assert c.get("/api/youtube/connect", params={"channel": "nope"}, follow_redirects=False).status_code == 404
    assert c.delete("/api/my-channels/music").json() == {"ok": True}
    monkeypatch.setattr(app_module, "BILLING_ENABLED", True)
    assert c.get("/api/my-channels").status_code == 404


def test_process_tags_the_job_with_its_channel(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    c = TestClient(app_module.app)
    assert c.post("/api/process", json={"genre": "quiz", "channel": "nope"},
                  headers={"X-Shortkaar-Autopilot": "1"}).status_code == 400
    mc.add("quiz")
    r = c.post("/api/process", json={"genre": "quiz", "channel": "quiz", "quiz_format": "riddle",
                                     "quiz_avoid": ["Old?"], "acknowledged": True},
               headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 200, r.text
    src = json.loads((tmp_path / r.json()["job_id"] / ".source.json").read_text())
    assert src["genre"] == "quiz" and src["channel"] == "quiz" and src["url"] is None


# ------------------------------------------------------------- makers

def test_sung_lines_are_matched_split_and_mishearings_dropped():
    import music_shorts as m
    lyrics = ["Barefoot running through the cooling street", "Electric lanterns hum above our heads",
              "Drink up the midnight tangerine", "Painting our silhouettes in gold"]
    words = [(w, 3.3 + i * 0.5, 3.7 + i * 0.5) for i, w in enumerate(
        "Barefoot running through the cooling street Electric lanterns hum above our heads".split())]
    heard = [("Barefoot running through the cooling street Electric lanterns hum above our heads", 3.3, 10.5, words),
             ("Drink up the midnight tangerine", 33.3, 37.1, []),
             ("Pain in our sin, love always is gone", 37.1, 41.0, []),
             ("Totally unrelated words here now", 41.0, 43.0, [])]
    got = m.align(lyrics, heard)
    assert [t for t, _a, _b in got] == lyrics
    assert got[0][2] < got[1][1] + 0.01 and got[1][1] == pytest.approx(6.3)
    assert m.window(got, 52.0) == (pytest.approx(2.3), 52.0)
    long = [("x", 5.0, 9.0), ("y", 50.0, 55.0), ("z", 60.0, 66.0)]
    s, e = m.window(long, 90.0)
    assert s == pytest.approx(4.0) and e - s <= m.MAX_SONG


def test_quiz_keeps_only_answers_the_check_confirms(monkeypatch):
    import quiz_shorts as q
    qs = [q.Question(question=f"Q{k}?", options=["a", "b", "c", "d"], answer=1, answer_text="b", explain="")
          for k in range(4)]

    class C:
        class models:
            @staticmethod
            def generate_content(model, contents):
                return type("R", (), {"text": "1: OK\n2: WRONG - it is c\n3: ok\n4: OK"})()
    assert [x.question for x in q._checked(C(), "math", qs)] == ["Q0?", "Q2?", "Q3?"]
    assert not q._shape_ok(q.Question(question="x", options=["a", "b"], answer=3, answer_text="", explain=""),
                           q.FORMATS["mcq"])
    assert q._shape_ok(q.Question(question="x", options=[], answer=-1, answer_text="Chand", explain=""),
                       q.FORMATS["riddle"])


def test_only_free_licence_photos_are_used(monkeypatch, tmp_path):
    import player_photo as pp
    for ok in ("CC BY 3.0", "CC BY-SA 4.0", "CC0", "Public domain", "GODL-India", "cc-by-sa-2.0"):
        assert pp.FREE.match(ok), ok
    for bad in ("Fair use", "All rights reserved", "Copyrighted", ""):
        assert not pp.FREE.match(bad), bad
    calls = []

    def api(params, tries=4):
        calls.append(params)
        if params.get("prop") == "pageimages|description":
            return {"query": {"pages": {"1": {"title": "Babar Azam", "pageimage": "B.jpg",
                                              "description": "Pakistani cricketer"}}}}
        return {"query": {"pages": {"-1": {"imageinfo": [{
            "thumburl": "https://upload.wikimedia.org/b.jpg", "width": 900, "height": 900,
            "extmetadata": {"LicenseShortName": {"value": "Fair use"}, "Artist": {"value": "<a>X</a>"}}}]}}}}
    monkeypatch.setattr(pp, "_api", api)
    assert pp.lookup("Babar Azam") is None
    assert pp.lookup("babar  azam") is None and len(calls) == 2   # the miss is cached too
    assert pp.fetch("Nobody Here", str(tmp_path)) is None


def test_long_names_and_match_lines_shrink_instead_of_being_cut():
    import cricket_shorts as cs
    fs, name = cs._name("Mohammad Imran Randhawa")
    assert name == "Mohammad Imran Randhawa" and fs == r"\fs54"
    assert cs._name("Babar Azam") == ("", "Babar Azam")
    shape, text = cs._pill(0, 1, 190, "SL tour of Pakistan Rawalpindi 11 Oct 2026")
    assert "m 0 0" in shape or "\\p1" in shape
    assert r"\fs" in text and int(text.split(r"\fs")[1].split("\\")[0]) < 36
    assert r"\fs" not in cs._pill(0, 1, 190, "RESULT")[1]


def test_main_channel_row_reads_the_autopilot_settings(monkeypatch):
    app_module = pytest.importorskip("app")
    row = app_module._main_channel_row()
    assert row["id"] == "main" and row["main"] is True and "post_times" in row
