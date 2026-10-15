"""History series: one big story in 2-4 parts that link to each other."""
import json

import pytest

import history_videos as hv
import my_channels as mc
import youtube_account as ya


def test_a_series_line_becomes_one_idea_per_part_in_order():
    text = ("topic: Karbala: what happened in 680 AD\n"
            "series: The Ottoman Empire | Osman's small state | Constantinople falls | Suleiman's golden age\n"
            "series: The Mughals | Babur | Akbar\n")
    got = hv.series_ideas(text)
    assert [i["text"] for i in got] == ["Osman's small state", "Constantinople falls", "Suleiman's golden age"]
    assert got[2] == {"kind": "topic", "text": "Suleiman's golden age", "series": "The Ottoman Empire", "part": 3,
                      "parts": 3, "before": ["Osman's small state", "Constantinople falls"]}
    assert hv.series_ideas("series: Rome | only one part") == []
    assert hv.series_ideas("series: Rome | A | B", seen={"b"}) == []


def test_a_part_knows_its_series_and_carries_its_number(monkeypatch):
    monkeypatch.setenv("HISTORY_SERIES", "The Ottoman Empire")
    monkeypatch.setenv("HISTORY_PART", "2")
    monkeypatch.setenv("HISTORY_PARTS", "3")
    monkeypatch.setenv("HISTORY_BEFORE", json.dumps(["Osman's small state"]))
    s = hv.series_env()
    assert s == {"name": "The Ottoman Empire", "part": 2, "parts": 3, "before": ["Osman's small state"]}
    note = hv.series_note(s)
    assert "PART 2 of 3" in note and "Osman's small state" in note and "where part 1 ended" in note
    assert "what part 3 will tell" in note
    assert "closes the whole series" in hv.series_note({**s, "part": 3})
    assert hv.series_topic("Constantinople falls", s) == "The Ottoman Empire: Constantinople falls"
    assert hv.part_title("Constantinople Kaise Gira?", 2) == "Constantinople Kaise Gira? | Part 2"
    assert hv.part_title("Usmani Saltanat Part 2: Constantinople", 2) == "Usmani Saltanat Part 2: Constantinople"
    monkeypatch.setenv("HISTORY_PART", "5")
    assert hv.series_env() is None                                    # past the series' own count


def test_the_next_part_is_planned_with_its_series(monkeypatch):
    ch = mc.add("history")
    mc._change(ch["id"], lambda c: c.update(daily_short=False, ideas=hv.series_ideas("series: Rome | Rise | Fall")))
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["history_series"] == "Rome" and payload["history_part"] == 1 and payload["history_parts"] == 2
    assert meta["series"] == "Rome" and meta["series_part"] == 1 and meta["label"] == "Part 1: Rise"
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["history_before"] == ["Rise"] and meta["series_part"] == 2


def test_process_hands_the_series_to_the_job(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    r = TestClient(app_module.app).post("/api/process", json={
        "genre": "history", "history_topic": "Fall", "history_series": "Rome", "history_part": 2,
        "history_parts": 2, "history_before": ["Rise"], "acknowledged": True},
        headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 200, r.text
    env = app_module.jobs[r.json()["job_id"]]["env"]
    assert env["HISTORY_SERIES"] == "Rome" and env["HISTORY_PART"] == "2" and json.loads(env["HISTORY_BEFORE"]) == ["Rise"]


def test_parts_link_back_on_upload_and_the_last_part_gets_a_next_link(monkeypatch):
    ch = mc.add("history")
    acct = mc.account(ch["id"])
    with ya.use(acct):
        ya._save_upload({"id": "p1", "genre": "history", "status": "done", "video_id": "PART1PART11", "title": "Rise",
                         "series": "Rome", "series_part": 1, "publish_at": "2026-10-14T13:00:00+00:00"})
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "j2", "status": "done", "format": "history", "at": 1,
                                                   "series": "Rome", "series_part": 2}]))
    monkeypatch.setattr(ya, "status", lambda: {"connected": True})
    sent, linked = {}, []

    def upload(path, title, desc, tags, genre, publish_at=None, ai_made=False, meta=None):
        sent.update(desc=desc, meta=meta)
        row = {"id": "p2", "status": "done", "video_id": "PART2PART22", "title": title, "genre": genre, **meta}
        ya._save_upload(row)
        return row
    monkeypatch.setattr(ya, "upload", upload)
    monkeypatch.setattr(ya, "add_to_description", lambda vid, line: linked.append((vid, line)) or True)
    clip = {"index": 0, "path": "p.mp4", "title": "Fall", "description": "Summary\n\nFollow\n\n#history #urdu",
            "tags": []}
    mc.upload_waiting(mc.get(ch["id"]), lambda job: ("completed", [clip]), log=lambda *a: None)
    # Part 1 is linked once, as the previous part, not again under "Aur kahaniyan".
    assert sent["desc"] == "Summary\n\nFollow\n\nPichla hissa (Part 1): https://youtu.be/PART1PART11\n\n#history #urdu"
    assert sent["meta"]["series"] == "Rome" and sent["meta"]["series_part"] == 2
    assert linked == [("PART1PART11", "Agla hissa (Part 2): https://youtu.be/PART2PART22")]
    with ya.use(acct):
        assert next(r for r in ya.uploads() if r["id"] == "p1")["next_linked"] == "PART2PART22"


def test_adding_a_line_sends_the_snippet_back_whole(monkeypatch):
    ya._write(ya.TOKEN_FILE, {"access_token": "tok", "refresh_token": "r", "expires_at": 9e12})
    monkeypatch.setattr(ya, "_get", lambda url, params: {"items": [{"snippet": {
        "title": "Rise", "categoryId": "27", "tags": ["rome"], "description": "Text\n\n#history", "channelId": "x"}}]})
    put = {}

    class R:
        status_code = 200

    def fake_put(url, params=None, json=None, headers=None, timeout=None):
        put.update(json=json, params=params)
        return R()
    monkeypatch.setattr(ya.httpx, "put", fake_put)
    before = ya.quota_used()
    assert ya.add_to_description("PART1PART11", "Agla hissa (Part 2): link") is True
    assert put["json"] == {"id": "PART1PART11", "snippet": {"title": "Rise", "categoryId": "27", "tags": ["rome"],
                                                             "description": "Text\n\nAgla hissa (Part 2): link\n\n#history"}}
    assert put["params"] == {"part": "snippet"} and ya.quota_used() == before + 51


def test_dropping_one_part_drops_the_rest_of_its_series():
    ch = mc.add("history")
    mc._change(ch["id"], lambda c: c.update(ideas=hv.series_ideas("series: Rome | Rise | Fall")
                                                   + [{"kind": "topic", "text": "Karbala"}]))
    view = mc.summary(mc.get(ch["id"]))
    assert view["up_next_series"] == ["Rome, part 1 of 2", "Rome, part 2 of 2", ""]
    mc.drop_idea(ch["id"], "Fall")
    c = mc.get(ch["id"])
    assert [i["text"] for i in c["ideas"]] == ["Karbala"] and {"Rise", "Fall"} <= set(c["used"])
