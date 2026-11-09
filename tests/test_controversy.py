"""The controversy channel's gates: refused topics, too few sources, the
fairness check (one rewrite, then no video), real source links."""
import json
import types

import pytest

import controversy_shorts as cv
import my_channels as mc


def _story(**kw):
    base = {"found": True, "allowed": True, "reason": "", "person": "Shoaib Akhtar", "title": "T",
            "hook_line": "h", "beats": [{"when": "2008", "headline": "x", "detail": "d", "line": "l"}] * 4,
            "status_line": "s", "question": "q"}
    return cv.Story.model_validate({**base, **kw})


def _client(answers):
    """generate_content returns the next answer (str) or raises it."""
    it = iter(answers)

    class Models:
        def generate_content(self, model, contents, config=None):
            got = next(it)
            if isinstance(got, Exception):
                raise got
            return types.SimpleNamespace(text=got, candidates=[])
    return types.SimpleNamespace(models=Models())


def test_refused_topics_and_thin_research_make_no_video(monkeypatch):
    monkeypatch.setattr(cv, "research", lambda c, t: ("NOT ALLOWED: politics", [("a", "u")] * 5))
    with pytest.raises(RuntimeError, match="Not covered"):
        cv.write(None, "x vs y", "@h")
    monkeypatch.setattr(cv, "research", lambda c, t: ("REPORTED: something", [("a", "u"), ("b", "v")]))
    with pytest.raises(RuntimeError, match="Not enough reliable sources"):
        cv.write(None, "x", "@h")


def test_a_failed_fairness_check_gets_one_rewrite_then_no_video(monkeypatch):
    monkeypatch.setattr(cv, "research", lambda c, t: ("REPORTED: a\nALLEGED: b", [(str(k), "u") for k in range(4)]))
    calls = []

    def ask(client, schema, prompt, model=None):
        calls.append((schema.__name__, prompt))
        if schema is cv.Story:
            return _story()
        return cv.Check(ok=False, problems=["the allegation in beat 3 is said as a fact"])
    monkeypatch.setattr(cv.kit, "ask_json", ask)
    with pytest.raises(RuntimeError, match="fairness check"):
        cv.write(None, "x", "@h")
    assert [c[0] for c in calls] == ["Story", "Check", "Story", "Check"]
    assert "the allegation in beat 3 is said as a fact" in calls[2][1]   # the rewrite sees the notes


def test_a_script_that_passes_is_used_and_not_allowed_is_refused(monkeypatch):
    monkeypatch.setattr(cv, "research", lambda c, t: ("REPORTED: a", [(str(k), "u") for k in range(3)]))
    monkeypatch.setattr(cv.kit, "ask_json", lambda c, schema, p, model=None:
                        _story() if schema is cv.Story else cv.Check(ok=True, problems=[]))
    story, facts, sources = cv.write(None, "x", "@h")
    assert story.person == "Shoaib Akhtar" and len(sources) == 3
    monkeypatch.setattr(cv.kit, "ask_json", lambda c, schema, p, model=None:
                        _story(allowed=False, reason="religion") if schema is cv.Story else cv.Check(ok=True, problems=[]))
    with pytest.raises(RuntimeError, match="religion"):
        cv.write(None, "x", "@h")


def test_grounding_links_are_followed_to_the_article(monkeypatch):
    class R:
        headers = {"location": "https://www.skysports.com/cricket/news/1"}
    monkeypatch.setattr(cv.httpx, "head", lambda url, follow_redirects, timeout: R())
    assert cv._real_url("https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc") == \
        "https://www.skysports.com/cricket/news/1"
    assert cv._real_url("https://dawn.com/x") == "https://dawn.com/x"


def test_ideas_never_repeat_and_the_channel_sends_one_topic(monkeypatch):
    import cricket_shorts
    monkeypatch.setattr(cricket_shorts, "grounded", lambda client, prompt: (
        "topic: Shoaib Akhtar vs PCB: the 2008 ban\ntopic: Old one\nmatch: not for this channel", []))
    got = cv.channel_ideas(None, 4, avoid=["Old one"])
    assert got == [{"kind": "topic", "text": "Shoaib Akhtar vs PCB: the 2008 ban"}]
    ch = mc.add("controversy")
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["genre"] == "controversy" and payload["controversy_topic"].startswith("Shoaib")
    # A new channel has made nothing yet, so the second idea waits for the next Short.
    assert meta["format"] == "controversy" and [i["text"] for i in mc.get(ch["id"])["ideas"]] == ["Old one"]


def test_process_accepts_a_controversy_job(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    mc.add("controversy")
    r = TestClient(app_module.app).post("/api/process", json={
        "genre": "controversy", "channel": "controversy", "controversy_topic": "A vs B", "acknowledged": True},
        headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 200, r.text
    src = json.loads((tmp_path / r.json()["job_id"] / ".source.json").read_text())
    assert src["genre"] == "controversy" and src["channel"] == "controversy"
