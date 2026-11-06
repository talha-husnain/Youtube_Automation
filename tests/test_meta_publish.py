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
    assert st["connected"] and st["pages"] == [{"id": "111", "name": "Cricket Page", "instagram": "cric_ig",
                                                "ig_per_day": 1, "ig_full_on": None}]
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


# ------------------------------------------------- few Instagram accounts (5-nov-2026)

def _quiet():
    return {"log": lambda *a: None, "sleep": lambda s: None}


def test_a_new_instagram_account_starts_with_one_reel_a_day(state, monkeypatch):
    http = FakeMeta()
    _connect(http)
    ch = {"id": "c", "meta_page": "111", "meta_fb": False}
    for n in range(3):
        mp.enqueue(ch, {"title": f"t{n}", "video_id": f"v{n}"}, _short(state), publish_at=1)
    day = 86400
    assert mp.ig_cap("111", now=10) == 1 and mp.ig_full_on("111") is None
    assert mp.post_pass(now=100, http=http, **_quiet()) == 1          # week one: one Reel a day
    assert mp.post_pass(now=200, http=http, **_quiet()) == 0
    assert mp.ig_full_on("111") == 100 + 14 * day
    assert mp.ig_cap("111", now=100 + 8 * day) == 2 and mp.ig_cap("111", now=100 + 15 * day) == 3
    assert mp.post_pass(now=100 + 8 * day, http=http, **_quiet()) == 2  # week two: two
    assert mp.status()["pages"][0]["ig_per_day"] == 3                   # (it is past day 14 by now)


def test_a_shared_instagram_takes_only_shorts_that_won_on_youtube_the_best_first(state):
    http = FakeMeta()
    _connect(http)
    ch = {"id": "c", "meta_page": "111"}
    views = {"win": (90, 10), "big": (400, 10), "lose": (12, 10)}
    for vid in views:
        mp.enqueue(ch, {"title": vid, "video_id": vid}, _short(state), publish_at=1000, ig_wait=True)
    score = lambda item: views.get(item["video_id"])
    mp.post_pass(now=2000, http=http, score=score, **_quiet())
    q = {x["video_id"]: x for x in mp.queue()}
    assert all(x["fb"]["status"] == "posted" for x in q.values())     # Facebook Pages take every Short
    assert all(x["ig"]["status"] == "pending" for x in q.values())    # Instagram waits for a day of views
    mp.post_pass(now=1000 + mp.WIN_AFTER, http=http, score=score, **_quiet())
    q = {x["video_id"]: x for x in mp.queue()}
    assert q["big"]["ig"]["status"] == "posted" and q["big"]["ig"]["ratio"] == 40.0   # the bigger win first
    assert q["win"]["ig"]["status"] == "pending" and q["lose"]["ig"]["status"] == "pending"
    mp.post_pass(now=1000 + mp.WIN_UNTIL, http=http, score=score, **_quiet())
    q = {x["video_id"]: x for x in mp.queue()}
    assert q["lose"]["ig"]["status"] == "skipped" and "12 views" in q["lose"]["ig"]["why"]
    assert q["win"]["ig"]["status"] == "posted"       # it won too: the next day's one slot was its


def test_a_short_queued_during_a_pass_is_kept_and_finished_ones_leave_after_a_month(state, monkeypatch):
    http = FakeMeta()
    _connect(http)
    ch = {"id": "c", "meta_page": "111", "meta_ig": False}
    mp.enqueue(ch, {"title": "a", "video_id": "1"}, _short(state), publish_at=1)
    real = mp.post_facebook

    def slow_post(*a, **k):
        mp.enqueue(ch, {"title": "b", "video_id": "2"}, _short(state, secs=4), publish_at=10 ** 9)  # an upload meanwhile
        return real(*a, **k)
    monkeypatch.setattr(mp, "post_facebook", slow_post)
    mp.post_pass(now=100, http=http, **_quiet())
    assert sorted(x["video_id"] for x in mp.queue()) == ["1", "2"]
    monkeypatch.setattr(mp, "post_facebook", real)
    mp.post_pass(now=200, http=http, **_quiet())
    assert next(x for x in mp.queue() if x["video_id"] == "1")["done"] == 100     # set once
    mp.post_pass(now=100 + 31 * 86400, http=http, **_quiet())
    assert [x["video_id"] for x in mp.queue()] == ["2"]


# ------------------------------------------------- just paste the keys (5-nov-2026)

class _Keys:
    def __init__(self, ok=True):
        self.ok, self.calls = ok, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        return _R({"access_token": "app|tok"}) if self.ok else _R({"error": {"message": "Invalid client_secret"}}, 400)


def test_pasted_keys_are_checked_with_meta_then_saved_to_env_without_a_restart(state, monkeypatch):
    monkeypatch.delenv("META_CONFIG_ID", raising=False)
    env = state / ".env"
    env.write_text("GEMINI_API_KEY=g\nMETA_APP_ID=old\n", encoding="utf-8")
    good_secret = "a" * 32
    with pytest.raises(ValueError, match="App ID"):
        mp.save_keys("abc", good_secret, http=_Keys(), env_file=str(env))
    with pytest.raises(ValueError, match="App Secret"):
        mp.save_keys("1234567890", "short", http=_Keys(), env_file=str(env))
    with pytest.raises(ValueError, match="did not accept"):
        mp.save_keys("1234567890", good_secret, http=_Keys(ok=False), env_file=str(env))
    assert "old" in env.read_text()                                  # nothing written on a refusal
    st = mp.save_keys(" 1234567890 ", good_secret, "9876543210", http=_Keys(), env_file=str(env))
    text = env.read_text()
    assert "GEMINI_API_KEY=g" in text and "META_APP_ID=1234567890" in text and "META_APP_ID=old" not in text
    assert f"META_APP_SECRET={good_secret}" in text and "META_CONFIG_ID=9876543210" in text
    assert st["configured"] and st["config_id"] and st["app_id"] == "1234567890"
    assert good_secret not in json.dumps(st)
    assert "config_id=9876543210" in mp.auth_url() and "scope=" not in mp.auth_url()
    monkeypatch.delenv("META_CONFIG_ID")
    assert "scope=" in mp.auth_url()


def test_a_test_can_never_write_the_real_env():
    with pytest.raises(RuntimeError, match="real .env"):
        mp.write_env({"X": "1"}, mp._REAL_ENV_FILE)


class _TwoPages(FakeMeta):
    """Page 111 (cricket, Instagram 999) and Page 222 (money, no Instagram), until ig2 is linked."""

    def __init__(self, ig2=False, **kw):
        super().__init__(**kw)
        self.ig2 = ig2

    def get(self, url, params=None, timeout=None):
        if url.endswith("/u1/accounts"):
            self.calls.append(("GET", url, dict(params or {})))
            two = {"id": "222", "name": "Paisa Kahani", "access_token": "tok222"}
            if self.ig2:
                two["instagram_business_account"] = {"id": "888", "username": "paisa_ig"}
            return _R({"data": [{"id": "111", "name": "CricRecordz Daily", "access_token": "pagetok",
                                 "instagram_business_account": {"id": "999", "username": "cric_ig"}}, two]})
        if url.endswith("/999/content_publishing_limit"):
            return _R({"data": [{"quota_usage": 0}]})
        if url.endswith("/888/content_publishing_limit"):
            return _R({"error": {"message": "Application does not have permission"}}, 403)
        if url.endswith("/111") or url.endswith("/222"):
            return _R({"name": "x"})
        return super().get(url, params, timeout)


def test_a_channel_without_its_own_instagram_posts_reels_through_a_shared_one(state):
    http = _TwoPages()
    _connect(http)
    ch = {"id": "money", "meta_page": "222", "meta_ig_page": "111"}
    item = mp.enqueue(ch, {"title": "Paisa", "video_id": "m1"}, _short(state), publish_at=1)
    assert item["page"] == "222" and item["ig_page"] == "111"
    mp.post_pass(now=100, http=http, **_quiet())
    q = mp.queue()[0]
    assert q["fb"]["status"] == "posted" and q["ig"]["status"] == "posted"
    ups = [c for c in http.calls if c[0] == "POST" and "rupload" in c[1]]
    assert {c[3]["Authorization"] for c in ups} == {"OAuth tok222", "OAuth pagetok"}   # Facebook via 222, Instagram via 111
    assert mp.targets({"id": "x", "meta_page": "222"}) == (mp.page("222"), None)       # no Instagram of its own
    assert mp.targets({"id": "x", "meta_page": "222", "meta_fb": False}) is None


def test_pages_are_read_again_and_checked_without_posting(state):
    _connect(_TwoPages())
    assert [p.get("instagram") for p in mp.status()["pages"]] == ["cric_ig", None]
    st = mp.refresh_pages(http=_TwoPages(ig2=True))
    assert [p.get("instagram") for p in st["pages"]] == ["cric_ig", "paisa_ig"]
    rows = {r["id"]: r for r in mp.check(http=_TwoPages(ig2=True))}
    assert rows["111"]["facebook"] == "ok" and rows["111"]["instagram"] == "ok"
    assert "permission" in rows["222"]["instagram"]
    assert "tok222" not in json.dumps(rows)


def test_the_sign_in_address_switches_between_localhost_and_127(state, monkeypatch):
    monkeypatch.delenv("META_REDIRECT", raising=False)
    env = state / ".env"
    monkeypatch.setattr(mp, "ENV_FILE", str(env))
    assert mp.redirect_uri() == "http://localhost:8000/api/meta/callback"
    assert mp.use_redirect_host("127.0.0.1") == "http://127.0.0.1:8000/api/meta/callback"
    assert mp.redirect_uri() == "http://127.0.0.1:8000/api/meta/callback"
    assert "META_REDIRECT=http://127.0.0.1:8000/api/meta/callback" in env.read_text()
    with pytest.raises(ValueError):
        mp.use_redirect_host("evil.example.com")


def test_reels_ask_to_be_sent_on_the_kinds_that_have_a_line():
    """Instagram names sends per reach first (5-nov-2026); a caption asks for the send, the same line per video."""
    import meta_publish as mp
    one = mp.caption_for("Remote kis ka?", "Billo aur Guddu ki jung.\n\n#cartoon #funny", "toons", "abc")
    assert one == mp.caption_for("Remote kis ka?", "Billo aur Guddu ki jung.\n\n#cartoon #funny", "toons", "abc")
    assert any(line in one for line in mp.SHARE_LINES["toons"]) and one.index("bhejo") < one.index("#cartoon")
    assert not any(line in mp.caption_for("t", "b", "quran") for lines in mp.SHARE_LINES.values() for line in lines)
    assert mp.caption_for("t", "b") == "t\n\nb"
