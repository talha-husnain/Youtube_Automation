"""The songs channel's AI singer (owner, 22-oct-2026): off until there is a
fal.ai key and a chosen character, at most DAILY_MAX a day, fal's queue used
the way its docs say, and a song is never lost to a failed dance."""
import json
import os

import pytest

import ai_influencer as ai
import music_shorts


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(ai, "CHARACTER_FILE", str(tmp_path / "character.json"))
    monkeypatch.setattr(ai, "SPEND_FILE", str(tmp_path / "spend.json"))
    monkeypatch.setattr(ai, "ROOT", str(tmp_path))          # no .env there: no key unless a test sets one
    monkeypatch.delenv("FAL_KEY", raising=False)
    return tmp_path


def _character(tmp_path):
    pic = tmp_path / "look.png"
    pic.write_bytes(b"png")
    return ai.pick(str(pic), "Aria", "a pop singer")


def test_off_without_a_key_a_character_or_room_in_the_day(state, monkeypatch):
    assert not ai.available()
    monkeypatch.setenv("FAL_KEY", "k")
    assert not ai.available()                    # no character chosen yet
    assert _character(state)["name"] == "Aria"
    assert ai.available()
    for _ in range(ai.DAILY_MAX):
        ai.record(0.67)
    assert not ai.available() and ai.made_today() == ai.DAILY_MAX
    assert json.load(open(state / "spend.json"))  # what was spent stays on record
    assert ai.cost(15) == round(ai.STILL_PRICE + 15 * 0.04, 2)


class _Resp:
    def __init__(self, data=None, status=200, content=b"x"):
        self._data, self.status_code, self.content = data, status, content

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _Stream:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_bytes(self, n):
        yield b"video"


def test_fal_queue_is_used_with_the_urls_it_returns(monkeypatch, tmp_path):
    monkeypatch.setenv("FAL_KEY", "k")
    calls = []
    states = iter([{"status": "IN_QUEUE"}, {"status": "IN_PROGRESS"}, {"status": "COMPLETED"}])

    def post(url, **kw):
        calls.append(("post", url, kw.get("json"), kw["headers"]["Authorization"]))
        return _Resp({"request_id": "r", "status_url": "https://queue.fal.run/fal-ai/wan/requests/r/status",
                      "response_url": "https://queue.fal.run/fal-ai/wan/requests/r"})

    def get(url, **kw):
        calls.append(("get", url))
        return _Resp(next(states)) if url.endswith("/status") else _Resp({"video": {"url": "https://v3.fal.media/x.mp4"}})
    monkeypatch.setattr(ai.httpx, "post", post)
    monkeypatch.setattr(ai.httpx, "get", get)
    monkeypatch.setattr(ai.httpx, "stream", lambda *a, **k: _Stream())
    out = ai.animate("https://img", "https://vid", str(tmp_path / "o.mp4"), sleep=lambda s: None)
    assert open(out, "rb").read() == b"video"
    assert calls[0] == ("post", ai.QUEUE + ai.MODEL, {"image_url": "https://img", "video_url": "https://vid",
                                                     "resolution": ai.RESOLUTION}, "Key k")
    # The returned URLs, not ones built from the full model path (that answers 405).
    assert [c[1] for c in calls[1:]] == ["https://queue.fal.run/fal-ai/wan/requests/r/status"] * 3 + [
        "https://queue.fal.run/fal-ai/wan/requests/r"]


def test_a_failed_fal_job_says_completed_and_still_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("FAL_KEY", "k")
    monkeypatch.setattr(ai.httpx, "post", lambda url, **kw: _Resp({"status_url": "s/status", "response_url": "r"}))
    monkeypatch.setattr(ai.httpx, "get", lambda url, **kw: _Resp(
        {"status": "COMPLETED", "error": "out of credit"} if url.endswith("/status") else {"detail": "no"}))
    with pytest.raises(RuntimeError, match="out of credit"):
        ai.animate("i", "v", str(tmp_path / "o.mp4"), sleep=lambda s: None)


def test_a_failed_dance_leaves_the_song_its_footage(state, monkeypatch, tmp_path):
    monkeypatch.setenv("FAL_KEY", "k")
    _character(state)
    monkeypatch.setattr(ai, "still", lambda client, ch, song, out: out)
    monkeypatch.setattr(ai, "dance_clips", lambda client, seconds, log=print: [
        {"path": "a.mp4", "use": 8.0, "id": "pixabay:v1"}, {"path": "b.mp4", "use": 7.0, "id": "pixabay:v2"}])
    monkeypatch.setattr(ai, "driving", lambda src, seconds, out: out)

    def boom(*a):
        raise RuntimeError("fal is down")
    path, clips, spent = ai.dance_background(None, {"title": "t", "genre": "pop", "theme": "love", "scene": "x"},
                                             15, str(tmp_path), log=lambda m: None, animate_fn=boom,
                                             upload_fn=lambda p, t: "https://u")
    assert path is None and clips == [] and spent == ai.STILL_PRICE      # the picture was paid for


def test_a_dance_short_is_the_chorus_as_long_as_the_dance():
    lines = [("verse one", 4.0, 7.0), ("verse two", 8.0, 11.0), ("chorus line", 20.0, 23.0),
             ("chorus two", 24.0, 27.0), ("chorus three", 28.0, 31.0), ("outro", 40.0, 44.0)]
    assert music_shorts.window(lines, 50.0, 15.0, "chorus line") == (19.2, 32.5)
    assert music_shorts.window(lines, 50.0) == (3.0, 50.0)               # an ordinary song is unchanged


def test_the_songs_channel_asks_for_a_dance_only_when_she_can_dance(monkeypatch):
    import my_channels as mc
    ch = mc.add("music")
    monkeypatch.setattr(ai, "available", lambda now=None: False)
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert "music_dance" not in payload and meta["format"] != "dance"
    monkeypatch.setattr(ai, "available", lambda now=None: True)
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["music_dance"] is True and meta["format"] == "dance" and meta["label"].startswith("Dance: ")


def test_process_passes_the_dance_switch(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    r = TestClient(app_module.app).post("/api/process", json={
        "genre": "music", "music_style": "upbeat pop", "music_theme": "love", "music_dance": True,
        "acknowledged": True}, headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 200, r.text
    assert app_module.jobs[r.json()["job_id"]]["env"]["MUSIC_DANCE"] == "1"
    assert os.path.basename(ai.CHARACTER_FILE) == "character.json"


def test_a_drawn_dancer_is_dropped_even_when_the_picker_chose_it(monkeypatch, tmp_path):
    import stock_media
    clips = [{"id": f"pixabay:v{k}", "seconds": 9.0, "thumb": f"t{k}", "kind": "video"} for k in (1, 2)]
    monkeypatch.setattr(stock_media, "recently_used", lambda: set())
    monkeypatch.setattr(stock_media, "search", lambda term, portrait, kind: clips)
    monkeypatch.setattr(stock_media, "choose", lambda client, topic, scenes, pools, rule="": [clips[0], clips[1], None])
    monkeypatch.setattr(stock_media, "download", lambda c: str(tmp_path / f"{c['id'][-1]}.mp4"))
    monkeypatch.setattr(stock_media, "mark_used", lambda ids: None)
    monkeypatch.setattr(ai, "filmed", lambda client, c: c["id"] != "pixabay:v1")   # v1 is line art on green
    got = ai.dance_clips(None, 8.0)
    assert [c["id"] for c in got] == ["pixabay:v2"]
