"""Facebook / Instagram cross-posting (22-oct-2026): the connect flow keeps Page tokens, a Short is
queued only with a Page chosen, posts go out at their YouTube time through Meta's documented steps,
a failure is tried TRIES times, and the daily cap holds."""
import json
import os
import subprocess

import pytest

import meta_publish as mp


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(mp, "STATE_DIR", str(tmp_path / "meta"))
    monkeypatch.setattr(mp, "TOKEN_FILE", str(tmp_path / "meta" / "token.json"))
    monkeypatch.setattr(mp, "QUEUE_FILE", str(tmp_path / "meta" / "queue.json"))
    monkeypatch.setattr(mp, "OUTBOX", str(tmp_path / "meta" / "outbox"))
    monkeypatch.setenv("META_APP_ID", "123")
    monkeypatch.setenv("META_APP_SECRET", "s3cret")
    return tmp_path


class _R:
    def __init__(self, data, code=200):
        self.status_code, self._d = code, data

    def json(self):
        return self._d


class FakeMeta:
    """Answers the Graph API calls meta_publish makes, and records them."""

    def __init__(self, fail_ig=False):
        self.calls, self.fail_ig = [], fail_ig

    def get(self, url, params=None, timeout=None):
        self.calls.append(("GET", url, dict(params or {})))
        if url.endswith("/oauth/access_token"):
            return _R({"access_token": "long" if params.get("grant_type") else "short", "expires_in": 5184000})
        if url.endswith("/me"):
            return _R({"id": "u1", "name": "Owner"})
        if url.endswith("/u1/accounts"):
            return _R({"data": [{"id": "111", "name": "Cricket Page", "access_token": "pagetok",
                                 "instagram_business_account": {"id": "999", "username": "cric_ig"}}]})
        if "fields" in (params or {}) and params["fields"] == "status":
            return _R({"status": {"video_status": "ready"}})
        if (params or {}).get("fields") == "status_code,status":
            return _R({"status_code": "FINISHED"})
        return _R({}, 404)

    def post(self, url, data=None, headers=None, content=None, timeout=None):
        self.calls.append(("POST", url, dict(data or {}), dict(headers or {})))
        if url.endswith("/video_reels") and data.get("upload_phase") == "start":
            return _R({"video_id": "v77"})
        if url.endswith("/video_reels"):
            return _R({"success": True})
        if "rupload" in url:
            return _R({"success": True})
        if url.endswith("/999/media"):
            if self.fail_ig:
                return _R({"error": {"message": "nope"}}, 400)
            return _R({"id": "c55", "uri": "https://rupload.facebook.com/ig-api-upload/v26.0/c55"})
        if url.endswith("/media_publish"):
            return _R({"id": "m88"})
        return _R({}, 404)


def _connect(http):
    url = mp.auth_url("http://127.0.0.1:5180")
    state = url.split("state=")[1].split("&")[0]
    return mp.finish_connect("code", state, http=http)


def _short(tmp_path, secs=5, w=108, h=192):
    path = str(tmp_path / f"short_{w}x{h}_{secs}.mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=red:s={w}x{h}:d={secs}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", path], check=True, capture_output=True)
    return path


def test_connect_keeps_page_tokens_and_never_shows_them(state):
    st = _connect(FakeMeta())
    assert st["connected"] and st["pages"] == [{"id": "111", "name": "Cricket Page", "instagram": "cric_ig"}]
    assert "pagetok" not in json.dumps(st) and mp.page("111")["access_token"] == "pagetok"
    with pytest.raises(RuntimeError):
        mp.finish_connect("code", "old-state", http=FakeMeta())


def test_nothing_is_queued_without_a_page_or_for_a_long_video(state):
    _connect(FakeMeta())
    path = _short(state)
    assert mp.enqueue({"id": "cricket"}, {"title": "t"}, path) is None
    ch = {"id": "cricket", "meta_page": "111"}
    assert mp.enqueue(ch, {"title": "t"}, _short(state, w=192, h=108)) is None      # 16:9 stays on YouTube
    item = mp.enqueue(ch, {"title": "Babar ka record", "video_id": "yt1",
                           "description": "Hook line.\n\nMore: https://youtube.com/x\n\n#cricket #babar #shorts"}, path)
    assert item["fb"]["status"] == "pending" and item["ig"]["status"] == "pending" and os.path.isfile(item["file"])
    assert item["caption"] == "Babar ka record\n\nHook line.\n\n#cricket #babar"


def test_a_due_short_goes_to_facebook_and_instagram_with_the_ai_label(state):
    http = FakeMeta()
    _connect(http)
    item = mp.enqueue({"id": "cricket", "meta_page": "111"}, {"title": "t", "video_id": "yt1"}, _short(state),
                      publish_at=1000)
    assert mp.post_pass(log=lambda *a: None, now=999, http=http, sleep=lambda s: None) == 0    # not its time yet
    assert mp.post_pass(log=lambda *a: None, now=2000, http=http, sleep=lambda s: None) == 2
    posts = [c for c in http.calls if c[0] == "POST"]
    finish = next(c for c in posts if c[1].endswith("/video_reels") and c[2].get("upload_phase") == "finish")
    assert finish[2]["is_ai_generated"] == "true" and finish[2]["video_state"] == "PUBLISHED"
    up = [c for c in posts if "rupload" in c[1]]
    assert len(up) == 2 and all(c[3]["Authorization"] == "OAuth pagetok" and c[3]["offset"] == "0" for c in up)
    q = mp.queue()[0]
    assert q["fb"]["id"] == "v77" and q["ig"]["id"] == "m88" and not os.path.exists(item["file"])


def test_a_failing_platform_is_tried_three_times_then_given_up(state):
    http = FakeMeta(fail_ig=True)
    _connect(http)
    mp.enqueue({"id": "quiz", "meta_page": "111", "meta_fb": False}, {"title": "t", "video_id": "y"}, _short(state),
               publish_at=1)
    for n in range(mp.TRIES):
        mp.post_pass(log=lambda *a: None, now=10 + n, http=http, sleep=lambda s: None)
    ig = mp.queue()[0]["ig"]
    assert ig["status"] == "failed" and ig["tries"] == mp.TRIES and "nope" in ig["error"]
    assert mp.queue()[0]["fb"]["status"] == "off"


def test_the_daily_cap_and_the_90_second_facebook_limit(state, monkeypatch):
    http = FakeMeta()
    _connect(http)
    monkeypatch.setattr(mp, "DAILY_MAX", 1)
    ch = {"id": "c", "meta_page": "111", "meta_ig": False}
    mp.enqueue(ch, {"title": "a", "video_id": "1"}, _short(state), publish_at=1)
    mp.enqueue(ch, {"title": "b", "video_id": "2"}, _short(state, secs=4), publish_at=1)
    assert mp.post_pass(log=lambda *a: None, now=100, http=http, sleep=lambda s: None) == 1
    assert [q["fb"]["status"] for q in mp.queue()] == ["posted", "pending"]
    monkeypatch.setattr(mp, "FB_MAX_SECONDS", 3)
    long = mp.enqueue(ch, {"title": "c", "video_id": "3"}, _short(state, secs=5), publish_at=1)
    assert long["fb"]["status"] == "skipped"
