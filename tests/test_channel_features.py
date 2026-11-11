"""Never-repeat tracker, video finder, YouTube account, "what works" report and
the local Autopilot (used_moments / channel_tools / youtube_account /
what_works / autopilot_local). Every file they write goes to tmp_path."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

import autopilot_local as ap
import channel_tools as ct
import used_moments as um
import what_works as ww
import youtube_account as ya


@pytest.fixture(autouse=True)
def _files(tmp_path, monkeypatch):
    monkeypatch.setattr(um, "PATH", str(tmp_path / "used.json"))
    monkeypatch.setattr(ya, "TOKEN_FILE", str(tmp_path / "token.json"))
    monkeypatch.setattr(ya, "UPLOADS_FILE", str(tmp_path / "uploads.json"))
    monkeypatch.setattr(ww, "REPORT_FILE", str(tmp_path / "report.json"))
    monkeypatch.setattr(ap, "SETTINGS_FILE", str(tmp_path / "autopilot.json"))
    monkeypatch.setattr(ap, "LAST_SETTINGS_FILE", str(tmp_path / "last.json"))
    monkeypatch.delenv("SKIP_USED", raising=False)


# ------------------------------------------------------------- never repeat

def test_video_ids_from_every_link_shape():
    for link in ("https://www.youtube.com/watch?v=XRUbpqdBT10&t=5", "https://youtu.be/XRUbpqdBT10",
                 "https://youtube.com/shorts/XRUbpqdBT10", "https://www.youtube.com/live/XRUbpqdBT10"):
        assert um.video_id(link) == "XRUbpqdBT10"
    assert um.video_id("https://vimeo.com/123") is None


def test_used_spans_are_skipped_and_recorded_once():
    url = "https://www.youtube.com/watch?v=XRUbpqdBT10"
    um.record(url, [(100, 140), (100.4, 140.2), (300, 330)], "job1")   # the 2nd is the same moment
    assert um.ranges(url) == [(100.0, 140.0), (300.0, 330.0)]
    assert um.summary(url)["count"] == 2 and um.summary(url)["seconds"] == 70.0
    assert um.covered(90, 150, [(100, 140), (120, 145)]) == 45          # overlaps merge
    windows = [{"start": 90, "end": 180}, {"start": 0, "end": 90}, {"start": 290, "end": 340}]
    assert um.fresh_windows(windows, um.ranges(url)) == windows[:2]     # 30/50 s used -> dropped
    clips = [{"start": 120, "end": 160}, {"start": 130, "end": 170}, {"start": 200, "end": 240}]
    assert um.fresh_clips(clips, um.ranges(url)) == clips[1:]   # 50% repeat dropped, 25% kept


def test_skip_used_off_and_topics(monkeypatch):
    url = "https://youtu.be/XRUbpqdBT10"
    um.record(url, [(0, 30)])
    monkeypatch.setenv("SKIP_USED", "0")
    assert um.ranges(url) == []
    assert not um.topic_used("LBW rule, explained!")
    um.record_topic("LBW rule, explained!")
    assert um.topic_used("lbw rule explained")


def test_a_video_with_nothing_new_fails_before_any_ai_call(monkeypatch):
    main = pytest.importorskip("main")
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(main.llm_backend, "active", lambda: False)
    words = [{"word": f" w{i}", "start": i * 2.0, "end": i * 2.0 + 1} for i in range(60)]
    transcript = {"language": "ur", "segments": [{"start": 0, "end": 120, "text": "x", "words": words}]}
    with pytest.raises(um.AllUsedError):
        main.get_viral_clips(transcript, 120, used=[(0, 120)])


# ------------------------------------------------------------- finder

def test_search_filter_is_youtubes_creative_commons_filter():
    assert ct.search_filter() == "EgQQATAB"                     # type=video + Creative Commons
    assert ct.search_filter(cc=False) == "EgIQAQ=="
    assert ct.search_filter(duration="long", sort="views") == "CAMSBhABGAIwAQ=="


def test_channel_links_are_rebuilt_on_youtube_only():
    assert ct.channel_url("@PunchlineBazaar") == "https://www.youtube.com/@PunchlineBazaar"
    assert ct.channel_url("https://www.youtube.com/@mubariz.siddiqui/videos") == "https://www.youtube.com/@mubariz.siddiqui"
    assert ct.channel_url("UCaI1nsH7ZTFeQIkMa6Pu3yA") == "https://www.youtube.com/channel/UCaI1nsH7ZTFeQIkMa6Pu3yA"
    assert ct.channel_url("https://youtube.com/channel/UCaI1nsH7ZTFeQIkMa6Pu3yA") == \
        "https://www.youtube.com/channel/UCaI1nsH7ZTFeQIkMa6Pu3yA"
    for bad in ("https://evil.com/@foo", "https://evil.com/channel/UCaI1nsH7ZTFeQIkMa6Pu3yA", "", "a/b"):
        assert ct.channel_url(bad) is None


def test_licence_reads_the_label_and_never_raises(monkeypatch):
    import section_fetch
    monkeypatch.setattr(ct, "_cache", {})
    monkeypatch.setattr(section_fetch, "video_info", lambda u: {
        "license": "Creative Commons Attribution license (reuse allowed)", "title": "T", "duration": 61})
    assert ct.licence("https://youtu.be/AAAAAAAAAAA")["licence"] == "creative_commons"
    monkeypatch.setattr(section_fetch, "video_info", lambda u: {"title": "T"})
    assert ct.licence("https://youtu.be/BBBBBBBBBBB")["licence"] == "standard"

    def boom(u):
        raise RuntimeError("bot check")
    monkeypatch.setattr(section_fetch, "video_info", boom)
    assert ct.licence("https://youtu.be/CCCCCCCCCCC")["licence"] == "unknown"


# ------------------------------------------------------------- youtube account

def test_next_slots_skip_taken_times():
    tz = timezone(timedelta(hours=5))
    after = datetime(2026, 10, 8, 12, 0, tzinfo=tz)
    taken = datetime(2026, 10, 8, 13, 0, tzinfo=tz).astimezone(timezone.utc).isoformat()
    ya._write(ya.UPLOADS_FILE, [{"id": "a", "publish_at": taken, "status": "done"}])
    got = ya.next_slots(["19:00", "13:00"], 3, tz=tz, after=after)
    assert [s.strftime("%d %H:%M") for s in got] == ["08 19:00", "09 13:00", "09 19:00"]


def test_upload_fields_follow_youtube_limits():
    assert ya._clean("<b>Title</b>" + "x" * 200, ya.TITLE_MAX) == "bTitle/b" + "x" * 92
    assert sum(len(t) + 1 for t in ya._tags(["#" + "t" * 50] * 20)) <= ya.TAGS_MAX
    assert ya._iso_seconds("PT1M5S") == 65 and ya._iso_seconds("PT45S") == 45


def test_google_returns_only_to_a_local_dashboard():
    assert ya.back_url("http://localhost:5173", "connected=1") == "http://localhost:5173/#app?tab=channel&connected=1"
    assert ya.back_url("https://evil.example", "x=1").startswith(ya.DASHBOARD_URL)


def test_a_callback_we_did_not_start_is_refused(monkeypatch):
    monkeypatch.setenv("YT_CLIENT_ID", "id")
    monkeypatch.setenv("YT_CLIENT_SECRET", "secret")
    with pytest.raises(RuntimeError, match="expired"):
        ya.finish_connect("code", "made-up-state")
    assert "state=" in ya.auth_url("http://localhost:5173")


# ------------------------------------------------------------- what works

def _rows():
    return [{"id": str(i), "title": t, "views": v} for i, (t, v) in enumerate([
        ("Police checking mein maal? 😂", 66), ("Buzurg ki gaali sunkar kya kiya?", 12),
        ("मेरी मां घर में मां", 200), ("भाभी जी को अटेंशन", 3), ("Goa mein police checking", 14),
        ("Tinku se ladai", 3)])]


def test_comparisons_are_counted_in_code():
    g = {x["name"]: x for x in ww.groups(_rows())}
    q = g["Title asks a question (?)"]
    assert (q["yes"], q["yes_median"], q["no"], q["no_median"]) == (2, 39, 4, 8)   # median of 200, 3, 14, 3 is 8.5, rounded to even
    roman = g["Title in Roman letters (not Hindi/Urdu script)"]
    assert roman["yes"] == 4 and roman["no"] == 2


def test_report_needs_five_shorts_and_rules_reach_the_prompt_only_when_on(monkeypatch):
    monkeypatch.setattr(ww, "collect", lambda handle: (_rows()[:3], "public"))
    assert ww.build("@x")["enough"] is False
    assert ww.guidance() == ""
    ww._save({"use": True, "title_rules": ["Start with the situation."]})
    assert "Start with the situation." in ww.guidance()
    ww.set_use(False)
    assert ww.guidance() == ""


# ------------------------------------------------------------- autopilot

def test_settings_stay_in_range():
    cfg = ap.save({"comedy_per_day": 99, "cricket_per_day": -3, "run_at": "7:5", "post_times": ["25:00", "9:30"],
                   "cricket_kinds": "nope", "channels": [{"url": "u"}, "bad"], "enabled": 1})
    assert cfg["comedy_per_day"] == 10 and cfg["cricket_per_day"] == 0 and cfg["run_at"] == "07:05"
    assert cfg["post_times"] == ["09:30"] and cfg["cricket_kinds"] == "both"
    assert cfg["channels"] == [{"url": "u"}] and cfg["enabled"] is True


def test_due_once_a_day_after_the_time():
    cfg = {**ap.DEFAULTS, "enabled": True, "run_at": "03:00"}
    assert ap.due(cfg, datetime(2026, 10, 8, 3, 1))
    assert not ap.due(cfg, datetime(2026, 10, 8, 2, 59))
    assert not ap.due({**cfg, "last_run": "2026-10-08"}, datetime(2026, 10, 8, 9, 0))
    assert not ap.due({**cfg, "enabled": False}, datetime(2026, 10, 8, 9, 0))


def test_look_of_the_last_hand_made_job_is_kept_per_type():
    ap.remember_look({"url": "https://youtu.be/x", "genre": "comedy", "frame_bg_color": "#000000",
                      "clip_max_seconds": 60, "acknowledged": True})
    assert ap.look("comedy")["frame_bg_color"] == "#000000" and "url" not in ap.look("comedy")
    assert ap.look("cricket") == ap.BRAND


def test_videos_are_picked_new_first_round_robin_and_licence_checked(monkeypatch):
    vids = {
        "A": [{"url": "https://youtu.be/AAAAAAAAAA1", "title": "a1", "seconds": 1200},
              {"url": "https://youtu.be/AAAAAAAAAA2", "title": "a2", "seconds": 60}],      # too short
        "B": [{"url": "https://youtu.be/BBBBBBBBBB1", "title": "b1", "seconds": 1800},
              {"url": "https://youtu.be/BBBBBBBBBB2", "title": "b2", "seconds": 900}],
    }
    monkeypatch.setattr(ct, "channel_videos", lambda url, n: vids[url])
    monkeypatch.setattr(ct, "licence", lambda url: {"licence": "standard" if url.endswith("B1") else "creative_commons"})
    um.record("https://youtu.be/AAAAAAAAAA1", [(0, 60)])                  # partly used: comes after new ones
    cfg = {**ap.DEFAULTS, "channels": [{"url": "A"}, {"url": "B"}], "cc_only": True, "research": False}
    notes = []
    got = ap.pick_videos(cfg, 5, notes.append)
    assert [(v["title"], n) for v, n in got] == [("b2", 2), ("a1", 2)]          # two moments a video
    assert any("b1" in n for n in notes)


def test_ideas_skip_used_topics_and_alternate(monkeypatch):
    import cricket_shorts
    import short_kit
    monkeypatch.setattr(short_kit, "gemini", lambda: None)
    monkeypatch.setattr(cricket_shorts, "ideas", lambda c: [
        {"kind": "match", "text": "PAK vs IND"}, {"kind": "match", "text": "AUS vs ENG"},
        {"kind": "topic", "text": "LBW rule"}, {"kind": "topic", "text": "Babar stats"}])
    um.record_topic("LBW rule")
    got = ap.pick_ideas({**ap.DEFAULTS}, 3, print)
    assert [i["text"] for i in got] == ["Babar stats", "PAK vs IND", "AUS vs ENG"]


def test_a_run_submits_jobs_with_the_saved_look(monkeypatch):
    ap.save({"channels": [{"url": "A"}], "comedy_per_day": 2, "cricket_per_day": 1, "cc_only": False, "research": False})
    ap.remember_look({"genre": "comedy", "frame_bg_color": "#111111"})
    monkeypatch.setattr(ap, "pick_videos", lambda cfg, n, log: [({"url": "https://youtu.be/AAAAAAAAAA1", "title": "a1"}, 2)])
    monkeypatch.setattr(ap, "pick_ideas", lambda cfg, n, log: [{"kind": "topic", "text": "Babar stats"}])
    sent = []

    async def submit(payload):
        sent.append(payload)
        return f"job{len(sent)}"
    run = asyncio.run(ap.run_now(submit, "manual"))
    assert sent[0]["frame_bg_color"] == "#111111" and sent[0]["target_clips"] == 2 and sent[0]["genre"] == "comedy"
    assert sent[1]["genre"] == "cricket" and sent[1]["cricket_mode"] == "topic"
    assert [j["job_id"] for j in run["jobs"]] == ["job1", "job2"]
    assert um.topic_used("Babar stats") and ap.settings()["runs"][0]["reason"] == "manual"
    assert ap.settings()["last_run"] == datetime.now().strftime("%Y-%m-%d")


# ------------------------------------------------------------- API

def test_endpoints_refuse_bad_input(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    c = TestClient(app_module.app)
    assert c.get("/api/finder/licence", params={"url": "https://vimeo.com/1"}).status_code == 400
    assert c.get("/api/finder/channel", params={"url": "https://evil.com/@x"}).status_code == 400
    assert c.get("/api/finder/search", params={"q": "x", "sort": "nope"}).status_code == 400
    assert c.post("/api/youtube/upload", json={"job_id": "x", "clip_index": 0}).status_code == 400
    r = c.put("/api/local-autopilot", json={"comedy_per_day": 4})
    assert r.status_code == 200 and r.json()["settings"]["comedy_per_day"] == 4
    monkeypatch.setattr(app_module, "BILLING_ENABLED", True)
    assert c.get("/api/local-autopilot").status_code == 404


def test_old_shorts_survive_the_pickers_retry_path(monkeypatch):
    # get_viral_clips has its own local `used` (window ids) in the clip-floor
    # retry; it once shadowed the old-Shorts spans and failed every such job.
    main = pytest.importorskip("main")
    import test_clip_floor as cf
    first = [cf._clip(0, "window_001"), cf._clip(120, "window_003")]
    second = [cf._clip(240, "window_005"), cf._clip(300, "window_006"),
              cf._clip(360, "window_007"), cf._clip(420, "window_008")]
    real = main.get_viral_clips
    monkeypatch.setattr(main, "get_viral_clips", lambda t, d: real(t, d, used=[(115, 150)]))
    clips, _calls = cf._run(monkeypatch, [first, second])
    assert len(clips) == 5 and all(c["start"] != 120 for c in clips)


def test_upload_sends_a_scheduled_private_video_and_records_it(tmp_path, monkeypatch):
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"\x00" * 1000)
    ya._write(ya.TOKEN_FILE, {"access_token": "tok", "refresh_token": "r", "expires_at": 9e12})
    sent = {}

    class R:
        def __init__(self, code, body=None, headers=None):
            self.status_code, self._body, self.headers, self.text = code, body or {}, headers or {}, ""

        def json(self):
            return self._body

    def post(url, params=None, headers=None, json=None, timeout=None, **kw):
        sent["start"] = (url, params, headers, json)
        return R(200, headers={"location": "https://upload.example/session"})

    def put(url, content=None, headers=None, timeout=None):
        sent["put"] = (url, len(content if isinstance(content, bytes) else b"".join(content)))
        return R(200, {"id": "VID123", "status": {"privacyStatus": "private"}})
    monkeypatch.setattr(ya.httpx, "post", post)
    monkeypatch.setattr(ya.httpx, "put", put)
    at = datetime(2026, 10, 9, 19, 0, tzinfo=timezone(timedelta(hours=5)))
    row = ya.upload(str(clip), "Title <b>", "Desc", ["#comedy", "funny"], "comedy", publish_at=at,
                    ai_made=True, meta={"job_id": "j", "clip_index": 0})
    url, params, headers, body = sent["start"]
    assert params == {"uploadType": "resumable", "part": "snippet,status"}
    assert headers["X-Upload-Content-Length"] == "1000" and headers["Authorization"] == "Bearer tok"
    assert body["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                              "containsSyntheticMedia": True, "publishAt": "2026-10-09T14:00:00Z"}
    assert body["snippet"]["title"] == "Title b" and body["snippet"]["categoryId"] == "23"
    assert sent["put"] == ("https://upload.example/session", 1000)
    assert row["status"] == "done" and row["video_id"] == "VID123" and not row["locked_private"]
    assert ya.uploads()[-1]["job_id"] == "j"
    # Asked public, came back private: the unaudited-project lock.
    row = ya.upload(str(clip), "T", "D", [], "comedy", privacy="public")
    assert row["locked_private"] is True


# ------------------------------------------------------------- ready to post

import comment_replies as cr  # noqa: E402
import post_queue as pq  # noqa: E402


def _clips(now):
    return [{"job_id": "j1", "index": 0, "title": "Police checking mein maal? 😂 #shorts", "created": now - 50},
            {"job_id": "j1", "index": 1, "title": "Buzurg ki gaali #shorts #funny", "created": now - 50},
            {"job_id": "j2", "index": 0, "title": "Goa mein police checking", "created": now - 10}]


def test_ready_shorts_get_the_next_times_oldest_first():
    import time as _t
    now = _t.time()
    pq.update("j1:1", status="posted")
    slots = [datetime(2026, 10, 8, 13, tzinfo=timezone.utc), datetime(2026, 10, 8, 19, tzinfo=timezone.utc)]
    got = {x["id"]: x for x in pq.plan(_clips(now), ["13:00"], lambda times, n: slots[:n])}
    assert got["j1:0"]["slot"].startswith("2026-10-08T13") and got["j2:0"]["slot"].startswith("2026-10-08T19")
    assert got["j1:1"]["status"] == "posted" and "slot" not in got["j1:1"] and got["j1:1"]["posted_at"]
    with pytest.raises(ValueError):
        pq.update("j1:0", status="deleted")


def test_waiting_shorts_keep_their_job_for_a_week():
    assert pq.keeps("j1", 2, 3 * 86400)               # nothing marked yet: both wait
    pq.update("j1:0", status="posted")
    pq.update("j1:1", status="skipped")
    assert not pq.keeps("j1", 2, 3 * 86400)           # all done: the sweep may go
    assert not pq.keeps("j9", 1, 8 * 86400)           # past a week: goes anyway


def test_posted_titles_find_their_views():
    import time as _t
    posted = [{**c, "id": pq.item_id(c["job_id"], c["index"])} for c in _clips(_t.time())[:2]]
    shorts = [{"id": "AAA", "title": "Police checking mein MAAL? 😂 #shorts #comedy", "views": 66},
              {"id": "BBB", "title": "something else", "views": 3}]
    assert pq.match_views(posted, shorts) == 1
    assert pq._load()["j1:0"] == {"views": 66, "youtube_id": "AAA"}


def test_the_plan_starts_empty_and_stays_put():
    first = pq.since()
    assert pq.since() == first


def test_pinned_comment_is_roman_urdu_or_refused():
    class M:
        def __init__(self, text):
            self.text = text

        def generate_content(self, **kw):
            assert "Never name the comedian" in kw["contents"]
            return type("R", (), {"text": self.text})()
    clip = {"job_id": "j1", "index": 0, "title": "t", "hook": "h", "words": "w"}
    got = pq.pinned_comment(type("C", (), {"models": M('"Team biryani ya team pulao? 😅"')})(), "m", clip, "@x")
    assert got == "Team biryani ya team pulao? 😅" and pq._load()["j1:0"]["pinned_comment"] == got
    with pytest.raises(RuntimeError):
        pq.pinned_comment(type("C", (), {"models": M("यह क्या है")})(), "m", clip, "@x")


# ------------------------------------------------------------- comments

def test_only_unanswered_viewer_comments_are_offered():
    comments = [
        {"id": "a", "parent": "root", "text": "kya baat", "author_is_uploader": False},
        {"id": "b", "parent": "root", "text": "answered one", "author_is_uploader": False},
        {"id": "b.r", "parent": "b", "text": "shukriya", "author_is_uploader": True},
        {"id": "c", "parent": "root", "text": "our own pinned", "author_is_uploader": True},
        {"id": "d", "parent": "root", "text": "   ", "author_is_uploader": False},
    ]
    assert [c["id"] for c in cr.unanswered(comments)] == ["a"]


def test_drafts_are_stored_and_hidden_comments_stay_gone(monkeypatch):
    import channel_tools
    monkeypatch.setattr(channel_tools, "channel_shorts", lambda h, n: [{"id": "V1", "title": "Short"}])
    monkeypatch.setattr(cr, "_video_comments", lambda v: [
        {"id": "a", "parent": "root", "text": "kya baat", "author": "@x", "timestamp": 2, "video_id": "V1", "video_title": "Short"},
        {"id": "s", "parent": "root", "text": "buy followers http://x", "author": "@y", "timestamp": 1, "video_id": "V1", "video_title": "Short"}])

    class M:
        def generate_content(self, **kw):
            return type("R", (), {"text": json.dumps({"replies": [
                {"id": "a", "reply": "Shukriya bhai! Agla kaun sa dekhoge?", "skip": False},
                {"id": "s", "reply": "", "skip": True}]})})()
    rows = cr.draft(type("C", (), {"models": M()})(), "m", cr.fetch("@x")["comments"], "@x")
    assert rows[0]["draft"].startswith("Shukriya") and rows[1]["skip"] is True
    assert cr.fetch("@x")["comments"][0]["draft"].startswith("Shukriya")   # kept, no second AI call needed
    cr.mark("a", status="hidden")
    assert [c["id"] for c in cr.fetch("@x")["comments"]] == ["s"]


# ------------------------------------------------------------- long video

import shutil as _shutil  # noqa: E402
import subprocess as _sp  # noqa: E402

import long_video as lv  # noqa: E402


def test_on_screen_text_and_chapters():
    assert lv.clean_text("Date pe waiter ka khaana? 🤣 #shorts — yaar") == "Date pe waiter ka khaana? yaar"
    assert lv.clock(65) == "1:05" and lv.clock(3725) == "1:02:05"
    assert lv.chapters([(0, "Intro"), (3.5, "#3 One")]) == "0:00 Intro\n0:03 #3 One"


def test_hook_text_files_have_plain_line_ends(tmp_path):
    lv._txt(str(tmp_path), "h.txt", "a\nb")
    assert (tmp_path / "h.txt").read_bytes() == b"a\nb"


@pytest.mark.skipif(not _shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_a_long_video_is_built_wide_with_end_cards_cut(tmp_path, monkeypatch):
    import channel_tools
    monkeypatch.setattr(channel_tools, "licence", lambda url: {"licence": "creative_commons", "title": "Stage show", "channel": "FSD Fun Zone"})
    shorts = []
    for k in range(3):
        src = str(tmp_path / f"s{k}.mp4")
        _sp.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=540x960:rate=30:duration=4",
                 "-f", "lavfi", "-i", "sine=f=440:d=4", "-shortest", "-c:v", "libx264", "-c:a", "aac", src], check=True)
        keep = lv.keep_seconds(src, {"outro": True, "outro_seconds": 1.5})
        assert abs(keep - 2.5) < 0.1
        shorts.append({"id": f"j:{k}", "path": src, "hook": f"Hook number {k} 😂", "title": "t", "keep_seconds": keep,
                       "sources": ["https://youtu.be/AAAAAAAAAAA"]})
    meta = lv.build(str(tmp_path / "job"), shorts, "@PunchlineBazaar", progress=lambda s: None)
    out = tmp_path / "job" / [f for f in __import__("os").listdir(tmp_path / "job") if f.endswith("_clip_1.mp4")][0]
    dims = _sp.check_output(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                             "-of", "csv=p=0", str(out)]).decode().strip()
    assert dims == "1920,1080"
    total = lv._probe(str(out))
    assert abs(total - (lv.INTRO_SECONDS + 3 * 2.5 + lv.OUTRO_SECONDS)) < 0.6
    d = meta["shorts"][0]["seo_description"]
    assert "0:00 Intro" in d and "#3 Hook number 0" in d and "#1 Hook number 2" in d
    # One credit for the one CC source, after the chapters and before the hashtags; never on screen.
    assert d.count("FSD Fun Zone") == 1 and d.index("Chapters") < d.index("Credit") < d.index("#comedy")
    assert meta["genre"] == "long" and not any(f.startswith(".part") for f in __import__("os").listdir(tmp_path / "job"))
    with pytest.raises(ValueError):
        lv.build(str(tmp_path / "x"), shorts[:2], "@x")


def test_weekly_long_video_once_on_its_day():
    cfg = {**ap.DEFAULTS, "weekly_long": True, "weekly_day": 6, "run_at": "03:00"}
    sunday = datetime(2026, 10, 11, 4, 0)
    assert ap.weekly_due(cfg, sunday) and not ap.weekly_due(cfg, datetime(2026, 10, 10, 4, 0))
    assert not ap.weekly_due({**cfg, "last_weekly": "2026-10-11"}, sunday)
    run = ap.run_weekly(lambda: None)
    assert "fewer than 3" in run["notes"][0] and ap.settings()["last_weekly"]
    assert ap.run_weekly(lambda: "job9")["jobs"][0]["job_id"] == "job9"


@pytest.mark.skipif(not _shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_long_video_thumbnail_uses_a_frame_of_its_number_one(tmp_path, monkeypatch):
    import json as _json
    import os as _os
    app_module = pytest.importorskip("app")
    import thumbnail
    from fastapi.testclient import TestClient
    out = tmp_path / "output"
    short = out / "shortjob"
    short.mkdir(parents=True)
    _sp.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=540x960:rate=30:duration=4",
             "-c:v", "libx264", str(short / "S_clip_1.mp4")], check=True)
    (short / "S_metadata.json").write_text(_json.dumps({"shorts": [{"start": 0, "end": 4, "seo_title": "t"}]}))
    long_id = "3202b727-a877-4b8d-a0c4-fd84957d25fe"
    lj = out / long_id
    lj.mkdir()
    (lj / "Weekly_x_metadata.json").write_text(_json.dumps({"shorts": [{"seo_title": "Top 3 😂", "seo_description": "Intro line\n\nChapters"}]}))
    (lj / ".source.json").write_text(_json.dumps({"genre": "long", "shorts": ["x:0", "shortjob:0"]}))
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(out))
    monkeypatch.setattr(app_module, "THUMBNAILS_DIR", str(out / "thumbnails"))
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    seen = {}

    def fake(api_key, title, session_id, face_image_path=None, **kw):
        seen.update(title=title, session=session_id, ref=face_image_path, context=kw.get("video_context"))
        return [{"url": f"/thumbnails/{session_id}/a.jpg", "text": "HASO"}]
    monkeypatch.setattr(thumbnail, "generate_thumbnail", fake)
    r = TestClient(app_module.app).post(f"/api/long-video/{long_id}/thumbnail")
    assert r.status_code == 200 and r.json()["thumbnails"][0]["text"] == "HASO"
    assert seen["title"] == "Top 3 😂" and seen["context"] == "Intro line" and _os.path.exists(seen["ref"])
    assert _json.loads((lj / "thumbs.json").read_text())[0]["url"].endswith("a.jpg")


def test_new_titles_are_roman_urdu_and_use_the_channel_rules():
    seen = {}

    class M:
        def generate_content(self, **kw):
            seen["prompt"] = kw["contents"]
            return type("R", (), {"text": json.dumps({"titles": [
                {"title": "Date pe waiter ne kya kar diya? 😂 #shorts", "why": "curiosity"},
                {"title": "यह हिंदी है", "why": "x"}]})})()
    got = pq.retitle(type("C", (), {"models": M()})(), "m", {"title": "Old", "views": 4, "words": "w"}, "@x",
                     rules="- Start with the situation.", winners=["Police checking mein maal?"])
    assert got == [{"title": "Date pe waiter ne kya kar diya? 😂 #shorts", "why": "curiosity"}]
    assert "4 views" in seen["prompt"] and "Start with the situation" in seen["prompt"] and "Police checking" in seen["prompt"]


def test_system_check_reads_plainly(monkeypatch, tmp_path):
    import system_check as sc
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert sc.gemini()["status"] == "error"
    assert sc._ver("2026.08.19") == sc._ver("2026.8.19") < sc._ver("2026.9.1")
    (tmp_path / "f.bin").write_bytes(b"x" * 1000)
    assert sc.disk(str(tmp_path), 25)["name"] == "Disk space"
    assert sc.autopilot()["status"] == "warn"            # off by default
    ap.save({"enabled": True, "channels": [{"url": "u"}], "research": False})
    assert sc.autopilot()["status"] == "ok" and "Next run" in sc.autopilot()["detail"]


def test_system_check_names_the_free_voice_stock_keys_and_quota(monkeypatch):
    import free_voice
    import stock_media
    import system_check as sc
    monkeypatch.setenv("VOICE_ENGINE", "edge")
    monkeypatch.setattr(free_voice, "rest_info", lambda: {"until": 2e9, "reason": "Microsoft refused"})
    row = sc.free_voice()
    assert row["status"] == "warn" and "Microsoft refused" in row["detail"]
    monkeypatch.setattr(sc, "_env", lambda: {"PEXELS_API_KEY": "k"})
    monkeypatch.setattr(stock_media, "_resting", lambda p: p == "openverse")
    row = sc.stock()
    assert row["status"] == "warn" and "Keys: Pexels." in row["detail"] and "openverse" in row["detail"]
    monkeypatch.setattr(sc, "_env", lambda: {"PEXELS_API_KEY": "k", "PIXABAY_API_KEY": "k"})
    monkeypatch.setattr(stock_media, "_resting", lambda p: False)
    assert sc.stock()["status"] == "ok"
    assert "of 10,000 units" in sc.quota()["detail"]


def test_batch_starts_one_job_per_video_with_the_saved_look(monkeypatch):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    ap.remember_look({"genre": "comedy", "frame_bg_color": "#123456"})
    sent = []

    async def fake_submit(payload):
        sent.append(payload)
        if "BBBBBBBBBBB" in payload["url"]:
            raise RuntimeError("400: bad")
        return f"job{len(sent)}"
    monkeypatch.setattr(app_module, "_autopilot_submit", fake_submit)
    c = TestClient(app_module.app)
    r = c.post("/api/finder/batch", json={"urls": ["https://youtu.be/AAAAAAAAAAA", "https://youtu.be/BBBBBBBBBBB",
                                                   "https://youtu.be/AAAAAAAAAAA", "https://evil.com/x"], "clips": 2})
    assert r.status_code == 200 and r.json()["started"] == ["job1"] and len(r.json()["failed"]) == 1
    assert sent[0]["frame_bg_color"] == "#123456" and sent[0]["target_clips"] == 2 and len(sent) == 2
    assert c.post("/api/finder/batch", json={"urls": []}).status_code == 400


def test_posting_pack_zips_ready_shorts_with_their_copy(tmp_path, monkeypatch):
    import io as _io
    import zipfile as _zip
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    out = tmp_path / "output"
    job = out / "jobA"
    job.mkdir(parents=True)
    (job / "S_clip_1.mp4").write_bytes(b"video")
    (job / "S_metadata.json").write_text(json.dumps({"shorts": [{"start": 0, "end": 30, "seo_title": "Police checking 😂",
                                                                 "seo_description": "Desc", "video_description_for_tiktok": "tt"}]}))
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(out))
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "jobs", {})
    pq._save({"_since": 0})
    r = TestClient(app_module.app).get("/api/queue/pack")
    assert r.status_code == 200
    z = _zip.ZipFile(_io.BytesIO(r.content))
    names = sorted(z.namelist())
    assert names == ["01_Police_checking.mp4", "01_Police_checking.txt"]
    text = z.read(names[1]).decode()
    assert "TITLE:\nPolice checking 😂" in text and "TIKTOK:\ntt" in text and "POST AT:" in text
    pq.update("jobA:0", status="posted")
    assert TestClient(app_module.app).get("/api/queue/pack").status_code == 404


def test_an_uploaded_short_leaves_ready_to_post(monkeypatch):
    monkeypatch.setattr(ya, "upload", lambda *a, **k: {"status": "done", "video_id": "VID9"})
    ya.upload_and_mark("p", "t", "d", [], "comedy", None, "public", False, {"job_id": "jobZ", "clip_index": 1})
    assert pq._load()["jobZ:1"]["status"] == "posted" and pq._load()["jobZ:1"]["youtube_id"] == "VID9"
    monkeypatch.setattr(ya, "upload", lambda *a, **k: {"status": "failed"})
    ya.upload_and_mark("p", "t", "d", meta={"job_id": "jobY", "clip_index": 0})
    assert "jobY:0" not in pq._load()


# ------------------------------------------------------------- your own moments

def test_moments_parse_clock_and_seconds_and_refuse_nonsense():
    assert um.parse_ranges("12:30-13:20, 1:02:05 to 1:03:00; 750-800") == [(750.0, 800.0), (3725.0, 3780.0)]
    assert um.parse_ranges("2:15 – 2:59") == [(135.0, 179.0)]
    for bad, why in (("hello", "start-end"), ("1:00-1:02", "5 to 119"), ("0:00-5:00", "5 to 119"),
                     ("1-9,10-20,30-40,50-60,70-80,90-99", "At most 5")):
        with pytest.raises(ValueError, match=why):
            um.parse_ranges(bad)


def test_manual_moments_replace_the_ai_pick(monkeypatch):
    main = pytest.importorskip("main")
    monkeypatch.setenv("MANUAL_CLIPS", "[[10.2, 40.0], [500, 530]]")
    words = [{"word": f" w{i}", "start": i * 1.0, "end": i * 1.0 + 0.6} for i in range(120)]
    t = {"language": "ur", "segments": [{"start": 0, "end": 120, "text": "x", "words": words}]}
    got = main.get_viral_clips(t, 120.0)["shorts"]          # no Gemini key needed: no AI call
    assert len(got) == 1 and 9.5 <= got[0]["start"] <= 10.5 and 39 <= got[0]["end"] <= 41
    assert got[0]["video_title_for_youtube_short"].startswith("w10") and got[0]["why"] == "Picked by you"


def test_moments_are_refused_for_other_video_types(monkeypatch):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    c = TestClient(app_module.app)
    r = c.post("/api/process", json={"genre": "cricket", "cricket_match": "Pakistan vs India", "moments": "1:00-1:30",
                                     "acknowledged": True})
    assert r.status_code == 400 and "comedy" in r.json()["detail"]


# ------------------------------------------------------------- similar channels

def test_similar_channels_are_ranked_and_summed_up(monkeypatch, tmp_path):
    import rivals
    monkeypatch.setattr(rivals, "STATE_FILE", str(tmp_path / "rivals.json"))
    with pytest.raises(ValueError, match="Add at least one"):
        rivals.build(None, "m", "@x")
    rivals.save_channels([{"url": "https://www.youtube.com/@a", "name": "A"}, {"url": "https://www.youtube.com/@b", "name": "B"}])
    shorts = {"https://www.youtube.com/@a": [{"id": f"a{i}", "url": "u", "title": f"A {i}", "views": 1000 * i} for i in range(1, 5)],
              "https://www.youtube.com/@b": [{"id": "b1", "url": "u", "title": "B 1", "views": 50}, {"id": "b2", "url": "u", "title": "B 2", "views": None}]}
    import channel_tools
    monkeypatch.setattr(channel_tools, "channel_shorts", lambda url, n: shorts[url])
    seen = {}

    class M:
        def generate_content(self, **kw):
            seen["prompt"] = kw["contents"]
            return type("R", (), {"text": json.dumps({"summary": "A wins.", "patterns": ["p"],
                                                      "ideas": [{"idea": "family", "search": "urdu family comedy"}]})})()
    report = rivals.build(type("C", (), {"models": M()})(), "m", "@me")
    assert [r["id"] for r in report["top"][:2]] == ["a4", "a3"] and report["count"] == 5   # no-view row left out
    assert report["channels"][0] == {"channel": "A", "shorts": 4, "median": 2500, "best": 4000}
    assert "4000 | A | A 4" in seen["prompt"] and "Never copy their titles" in seen["prompt"]
    assert rivals.load()["report"]["ideas"][0]["search"] == "urdu family comedy"


def test_rival_channels_must_be_youtube(monkeypatch):
    app_module = pytest.importorskip("app")
    import rivals
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(rivals, "STATE_FILE", str(__import__("pathlib").Path(__import__("tempfile").mkdtemp()) / "r.json"))
    r = TestClient(app_module.app).put("/api/rivals", json={"channels": [{"url": "@good"}, {"url": "https://evil.com/@x"}]})
    assert r.json()["channels"] == [{"url": "https://www.youtube.com/@good", "name": ""}]


# ------------------------------------------------------------- telegram

class _TgFake:
    """Records Telegram calls; answers like the Bot API."""
    def __init__(self, updates=()):
        self.calls, self.updates = [], list(updates)

    def __call__(self, url, timeout=None, data=None, files=None, **kw):
        method = url.rsplit("/", 1)[1]
        self.calls.append((method, dict(data or {}), bool(files)))
        result = self.updates if method == "getUpdates" else {"message_id": len(self.calls)}
        return type("R", (), {"status_code": 200, "json": lambda s: {"ok": True, "result": result}})()


def test_telegram_connects_to_the_chat_that_said_hi_and_sends_shorts(tmp_path, monkeypatch):
    import telegram_notify as tg
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:SECRET")
    fake = _TgFake([{"message": {"chat": {"id": 42, "type": "private", "first_name": "Talha"}, "text": "hi"}}])
    monkeypatch.setattr(tg.httpx, "post", fake)
    assert tg.connect()["connected"] is True and tg._load()["chat_id"] == 42
    clip = tmp_path / "s.mp4"
    clip.write_bytes(b"v" * 10)
    tg.send_short(str(clip), "Title 😂", "Desc", "Pinned?", "2026-10-09 19:00", "tt")
    methods = [c[0] for c in fake.calls]
    assert methods == ["getUpdates", "sendMessage", "sendVideo", "sendMessage"]
    video = fake.calls[2]
    assert video[2] is True and video[1]["caption"] == "Post at: 2026-10-09 19:00\nTitle 😂"
    assert "PINNED COMMENT:\nPinned?" in fake.calls[3][1]["text"]


def test_telegram_errors_never_show_the_token(monkeypatch):
    import telegram_notify as tg
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:SECRET")
    monkeypatch.setattr(tg.httpx, "post", lambda url, **kw: type("R", (), {
        "status_code": 401, "json": lambda s: {"ok": False, "description": "Unauthorized"}})())
    with pytest.raises(RuntimeError) as e:
        tg._call("getUpdates")
    assert "Unauthorized" in str(e.value) and "SECRET" not in str(e.value)
    monkeypatch.setattr(tg.httpx, "post", _TgFake([]))
    with pytest.raises(RuntimeError, match="send it any message"):
        tg.connect()


def test_autopilot_sends_its_new_shorts_to_the_phone_once(monkeypatch):
    import telegram_notify as tg
    monkeypatch.setattr(tg, "status", lambda: {"connected": True})
    ap.save({"auto_phone": True})
    cfg = ap.settings()
    cfg["runs"] = [{"at": 1, "date": "d", "reason": "schedule", "notes": [],
                    "jobs": [{"job_id": "jobA", "kind": "comedy", "label": "x", "source": None, "clips": 2}]}]
    ap._write(ap.SETTINGS_FILE, cfg)
    items = [{"id": "jobA:0", "job_id": "jobA", "status": "ready", "slot": "2026-10-09T19:00"},
             {"id": "jobA:1", "job_id": "jobA", "status": "ready", "slot": "2026-10-09T13:00"},
             {"id": "jobB:0", "job_id": "jobB", "status": "ready", "slot": "2026-10-09T12:00"}]
    sent = []

    def send(x):
        sent.append(x["id"])
        pq.update(x["id"], telegram_sent=True)
    assert ap.phone_finished(lambda: items, send) == 2 and sent == ["jobA:1", "jobA:0"]   # posting order, Autopilot jobs only
    assert ap.phone_finished(lambda: items, send) == 0                                    # never twice


def test_phone_send_route_is_not_taken_by_the_queue_item_route(monkeypatch):
    app_module = pytest.importorskip("app")
    import telegram_notify as tg
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(tg, "status", lambda: {"connected": False})
    r = TestClient(app_module.app).post("/api/phone/send", json={})
    assert r.status_code == 400 and "Connect Telegram" in r.json()["detail"]


# ------------------------------------------------------------- match watch, take voice

def test_match_watch_makes_one_short_per_finished_match(monkeypatch):
    import cricket_shorts
    ap.save({"match_watch": True, "match_team": "  Pakistan  "})
    assert ap.settings()["match_team"] == "Pakistan" and ap.match_due(ap.settings())
    answers = iter(["MATCH: Pakistan vs India, Asian Games T20I, 02 October 2026", "NONE",
                    "MATCH: Pakistan vs India, Asian Games T20I, 02 October 2026"])
    monkeypatch.setattr(cricket_shorts, "grounded", lambda client, prompt: (next(answers), []))
    sent = []

    async def submit(payload):
        sent.append(payload)
        return f"job{len(sent)}"
    run = asyncio.run(ap.run_match_watch(submit, lambda: None))
    assert sent[0]["cricket_mode"] == "match" and sent[0]["cricket_match"].startswith("Pakistan vs India")
    assert run["reason"] == "match watch" and not ap.match_due(ap.settings())     # checked: wait 3 h
    assert asyncio.run(ap.run_match_watch(submit, lambda: None)) is None          # NONE: nothing
    assert asyncio.run(ap.run_match_watch(submit, lambda: None)) is None          # same match: never twice
    assert len(sent) == 1


def test_take_voice_is_checked_and_kept_for_autopilot(monkeypatch):
    app_module = pytest.importorskip("app")
    import ai_take
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    c = TestClient(app_module.app)
    r = c.post("/api/process", json={"url": "https://youtu.be/AAAAAAAAAAA", "genre": "comedy", "acknowledged": True,
                                     "take_voice": "Hacker"})
    assert r.status_code == 400 and r.json()["detail"] == "Unknown voice"
    assert "take_voice" in ap.LOOK_FIELDS
    assert c.get("/api/take-voice/sample", params={"voice": "Nope"}).status_code == 400
    monkeypatch.setattr(app_module, "THUMBNAILS_DIR", str(__import__("pathlib").Path(__import__("tempfile").mkdtemp())))
    made = []

    def fake_speak(client, text, path, voice):
        made.append(voice)
        open(path, "wb").write(b"RIFF")
        return 3.2
    monkeypatch.setattr(ai_take, "speak", fake_speak)
    import short_kit
    monkeypatch.setattr(short_kit, "gemini", lambda: None)
    assert c.get("/api/take-voice/sample", params={"voice": "Kore"}).json()["url"].endswith("/voice_samples/Kore.wav")
    c.get("/api/take-voice/sample", params={"voice": "Kore"})
    assert made == ["Kore"]                                                         # made once, then kept


# ------------------------------------------------------------- credits for CC sources

def test_cc_sources_are_credited_in_the_copy_only(monkeypatch):
    import channel_tools
    import credits
    lic = {"AAAAAAAAAAA": {"licence": "creative_commons", "title": "Stage Drama 2016", "channel": "FSD Fun Zone"},
           "BBBBBBBBBBB": {"licence": "standard", "title": "Big Show", "channel": "Real Owner"}}
    monkeypatch.setattr(channel_tools, "licence", lambda url: lic[url[-11:]])
    clip = {"seo_description": "Hook\n\nBody\n\nFollow @PunchlineBazaar for daily clips\n\n#shorts #funny",
            "video_description_for_instagram": "Hook\n\nBody\n\n#shorts #funny #comedy",
            "video_description_for_tiktok": "Funny one 😂 #shorts", "seo_title": "Title stays"}
    found = credits.apply([clip], ["https://www.youtube.com/watch?v=AAAAAAAAAAA", "https://youtu.be/AAAAAAAAAAA"])
    assert len(found) == 1                                                     # same video once
    d = clip["seo_description"]
    assert '"Stage Drama 2016" by FSD Fun Zone: https://www.youtube.com/watch?v=AAAAAAAAAAA' in d
    assert d.index("Follow") < d.index("Credit") < d.index("#shorts") and d.endswith("#shorts #funny")
    assert "FSD Fun Zone" in clip["video_description_for_instagram"]
    assert clip["video_description_for_tiktok"].startswith("Funny one")
    assert "Credit: FSD Fun Zone (CC BY)" in clip["video_description_for_tiktok"]
    assert clip["seo_title"] == "Title stays"                                  # nothing on screen or in the title
    credits.apply([clip], ["https://youtu.be/AAAAAAAAAAA"])
    assert clip["seo_description"].count("Credit") == 1                        # never twice
    plain = {"seo_description": "Hook\n\n#shorts"}
    assert credits.apply([plain], ["https://youtu.be/BBBBBBBBBBB"]) == [] and "credit" not in plain   # standard: owner's rule
    monkeypatch.setenv("CREDIT_CC", "0")
    off = {"seo_description": "Hook"}
    assert credits.apply([off], ["https://youtu.be/AAAAAAAAAAA"]) == [] and off["seo_description"] == "Hook"


# ------------------------------------------------------------- research + post all

def test_research_finds_most_viewed_unused_cc_videos_with_no_channels(monkeypatch):
    import channel_tools
    import used_moments

    def vid(i, views, channel, seconds=900):
        return {"id": f"V{i:010d}", "url": f"https://www.youtube.com/watch?v=V{i:010d}", "title": f"video {i}",
                "channel": channel, "channel_url": f"https://www.youtube.com/@{channel}", "seconds": seconds, "views": views}
    pool = [vid(1, 900_000, "big"), vid(2, 800_000, "big"), vid(3, 700_000, "big"),    # 3rd from one channel: dropped
            vid(4, 500_000, "mid"), vid(5, 5_000, "tiny"),                              # under min views: dropped
            vid(6, 600_000, "short", seconds=60), vid(7, 400_000, "used")]              # too short / fully used
    asked = []

    def fake_search(q, cc=True, duration="any", date="any", sort="relevance", limit=20):
        asked.append((q, cc, duration, sort))
        return pool if duration == "long" else pool[:2]
    monkeypatch.setattr(channel_tools, "search", fake_search)
    monkeypatch.setattr(used_moments, "summary", lambda url: {"count": 3, "seconds": 900} if "V0000000007" in url
                        else {"count": 0, "seconds": 0})
    monkeypatch.setattr(channel_tools, "licence", lambda url: {"licence": "creative_commons"})
    import short_kit
    monkeypatch.setattr(short_kit, "gemini", lambda: None)
    seen_ids = []

    def fake_ask(client, schema, contents, **kw):
        ids = [line.split('"id": "')[1][:11] for line in contents.splitlines() if '"id": "' in line]
        seen_ids.extend(ids)
        return schema.model_validate({"videos": [{"id": i, "keep": i != "V0000000004", "reason": "r"} for i in ids]})
    monkeypatch.setattr(short_kit, "ask_json", fake_ask)
    cfg = ap.save({"channels": [], "research": True, "research_queries": ["urdu comedy", " urdu  comedy ", ""],
                   "min_views": 20000, "comedy_per_day": 7})
    assert cfg["research_queries"] == ["urdu comedy"]                          # cleaned, no duplicates
    assert all(cc and sort == "views" for _q, cc, _d, sort in asked) or not asked
    notes = []
    picked = ap.pick_videos(ap.settings(), 7, notes.append)
    assert {d for _q, _c, d, _s in asked} == {"medium", "long"} and all(a[1] for a in asked)
    assert "V0000000005" not in seen_ids and "V0000000006" not in seen_ids and "V0000000007" not in seen_ids
    assert [v["id"][-1] for v, _n in picked] == ["1", "2"]                    # by views, 2 per channel, 4 vetted out
    assert [n for _v, n in picked] == [2, 2]                                  # the two best moments of each
    assert any("kept 3 of 4" in n for n in notes)

    def broken(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(short_kit, "ask_json", broken)
    notes = []
    assert ap.research_videos(ap.settings(), notes.append) == ([], [])       # unchecked finds are never used
    assert any("none were used" in n for n in notes)


def test_research_off_and_no_channels_asks_for_one(monkeypatch):
    ap.save({"channels": [], "research": False, "comedy_per_day": 3, "cricket_per_day": 0})
    sent = []

    async def submit(payload):
        sent.append(payload)
        return "job"
    run = asyncio.run(ap.run_now(submit))
    assert not sent and any("turn on research" in n for n in run["notes"])


def test_post_all_uploads_every_waiting_short_into_its_slot(monkeypatch):
    app_module = pytest.importorskip("app")
    import youtube_account
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    c = TestClient(app_module.app)
    monkeypatch.setattr(youtube_account, "status", lambda: {"connected": False})
    assert c.post("/api/youtube/post-all", json={}).status_code == 400
    monkeypatch.setattr(youtube_account, "status", lambda: {"connected": True})
    items = [{"id": "a:0", "job_id": "a", "index": 0, "status": "ready", "title": "A", "slot": "2026-10-13T13:00"},
             {"id": "b:0", "job_id": "b", "index": 0, "status": "posted", "title": "B"},
             {"id": "c:1", "job_id": "c", "index": 1, "status": "ready", "title": "C", "slot": "2026-10-12T19:00"},
             {"id": "d:0", "job_id": "d", "index": 0, "status": "ready", "title": "D", "slot": "2026-10-14T13:00"}]
    monkeypatch.setattr(app_module, "_plan_items", lambda: items)

    def job_clips(job_id):
        if job_id == "d":
            return "missing", []
        return "completed", [{"index": i, "path": f"{job_id}.mp4", "title": f"T{job_id}", "description": "D",
                              "tags": ["x"], "genre": "comedy", "ai_made": False} for i in range(2)]
    monkeypatch.setattr(app_module, "_job_clips", job_clips)
    monkeypatch.setattr(youtube_account, "next_slots", lambda times, n=1: [__import__("datetime").datetime(2026, 10, 13, 13, 0).astimezone()])
    done = []

    def fake_upload(path, title, description, tags, genre, publish_at=None, ai_made=False, meta=None):
        done.append((meta["job_id"], meta["clip_index"], publish_at is not None))
        return {"status": "done" if meta["job_id"] != "a" else "failed", "error": "quota"}
    monkeypatch.setattr(youtube_account, "upload_and_mark", fake_upload)
    monkeypatch.setattr(app_module, "_spawn", lambda fn, *a: fn(*a))
    r = c.post("/api/youtube/post-all", json={})
    assert r.status_code == 200 and r.json()["total"] == 3                     # posted one left out
    assert done == [("c", 1, True), ("a", 0, True)]                            # by slot, all scheduled
    st = c.get("/api/youtube/post-all").json()
    assert not st["running"] and st["done"] == 1 and st["failed"] == 2
    assert [u["title"] for u in st["uploaded"]] == ["C"] and st["uploaded"][0]["slot"].startswith("2026-10-13T13:00")
    assert any("quota" in e for e in st["errors"]) and any("no longer on this computer" in e for e in st["errors"])
    monkeypatch.setattr(app_module, "_plan_items", lambda: [items[1]])
    assert c.post("/api/youtube/post-all", json={}).json()["detail"] == "Nothing is waiting to be posted."


def test_channel_errors_are_plain_words():
    import channel_tools
    assert "no videos" in channel_tools.why_not(Exception("ERROR: [youtube:tab] @JanRambo: This channel does not have a videos tab"))
    assert "No YouTube channel" in channel_tools.why_not(Exception("HTTP Error 404: Not Found"))
    assert "Try again" in channel_tools.why_not(Exception("timed out"))


def test_post_all_stops_at_the_channels_daily_upload_limit(monkeypatch):
    app_module = pytest.importorskip("app")
    import youtube_account
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    c = TestClient(app_module.app)
    monkeypatch.setattr(youtube_account, "status", lambda: {"connected": True})
    items = [{"id": f"j{k}:0", "job_id": f"j{k}", "index": 0, "status": "ready", "title": f"T{k}",
              "slot": f"2026-10-14T{11 + k}:00"} for k in range(5)]
    monkeypatch.setattr(app_module, "_plan_items", lambda: items)
    monkeypatch.setattr(app_module, "_job_clips", lambda job_id: ("completed", [
        {"index": 0, "path": "x.mp4", "title": job_id, "description": "D", "tags": [], "genre": "comedy", "ai_made": False}]))
    monkeypatch.setattr(youtube_account, "next_slots", lambda times, n=1: [__import__("datetime").datetime(2026, 10, 14, 11, 0).astimezone()])
    tried = []

    def fake_upload(path, title, *a, meta=None, **k):
        tried.append(title)
        if len(tried) <= 2:
            return {"status": "done", "video_id": f"v{len(tried)}"}
        return {"status": "failed", "error": youtube_account.UPLOAD_LIMIT_TEXT}
    monkeypatch.setattr(youtube_account, "upload_and_mark", fake_upload)
    monkeypatch.setattr(app_module, "_spawn", lambda fn, *a: fn(*a))
    c.post("/api/youtube/post-all", json={})
    st = c.get("/api/youtube/post-all").json()
    assert tried == ["j0", "j1", "j2"]                                        # stopped at the first refusal
    assert st["done"] == 2 and st["limit"] and "The other 3 stay in Ready to post" in st["errors"][0]


def test_youtube_names_the_upload_limit_in_plain_words():
    import youtube_account

    class R:
        status_code = 400
        text = ""

        def json(self):
            return {"error": {"message": "The user has exceeded the number of videos they may upload.",
                              "errors": [{"reason": "uploadLimitExceeded"}]}}
    assert youtube_account._google_error(R()) == youtube_account.UPLOAD_LIMIT_TEXT
    assert youtube_account.upload_limit_hit("YouTube said 400: The user has exceeded the number of videos they may upload.")
    assert not youtube_account.upload_limit_hit("YouTube said 500: backend error")


# ------------------------------------------------------------- claims, auto upload, sound tags

def test_series_titles_are_left_out_of_research():
    assert ap.looks_like_a_series("PATI PATNI AUR PADOSAN - Episode 14 | New Twist")
    assert ap.looks_like_a_series("PAKISTANI STAGE DRAMA 2016 ZAFRI KHAN")
    assert ap.looks_like_a_series("Dhoka - EP 01 | Love, Loss, Betrayal")
    assert not ap.looks_like_a_series("EP 29: From Reels to Stage | Mubar podcast")
    assert not ap.looks_like_a_series("The Jan Rambo Show | Agha Majid | Saleem Albela")
    assert not ap.looks_like_a_series("Terrorism has a religion - Aakash Deep | Stand Up Comedy 2024")


def test_claim_check_finds_blocked_uploads(monkeypatch):
    import youtube_account as ya
    rows = [{"id": "r1", "video_id": "AAA", "status": "done", "created": int(__import__("time").time()), "job_id": "j1", "clip_index": 0},
            {"id": "r2", "video_id": "BBB", "status": "done", "created": int(__import__("time").time()), "job_id": "j2", "clip_index": 0},
            {"id": "r3", "video_id": "CCC", "status": "done", "created": int(__import__("time").time()), "job_id": "j3", "clip_index": 0}]
    for r in rows:
        ya._save_upload(r)
    monkeypatch.setattr(ya, "_get", lambda url, params: {"items": [
        {"id": "AAA", "contentDetails": {"regionRestriction": {"blocked": [f"C{i}" for i in range(250)]}}, "status": {}},
        {"id": "BBB", "contentDetails": {}, "status": {"uploadStatus": "processed"}},
        {"id": "CCC", "contentDetails": {"regionRestriction": {"blocked": ["PK"]}}, "status": {}}]})
    found = ya.claim_check()
    assert [r["video_id"] for r in found] == ["AAA", "CCC"]
    assert ya.claim_check() == []                                              # marked once
    assert {r["video_id"]: bool(r.get("blocked")) for r in ya.uploads()} == {"AAA": True, "BBB": False, "CCC": True}


def test_a_blocked_short_bans_its_source_and_pulls_its_siblings(monkeypatch):
    app_module = pytest.importorskip("app")
    import channel_tools
    import post_queue
    import youtube_account
    monkeypatch.setattr(youtube_account, "status", lambda: {"connected": True})
    monkeypatch.setattr(youtube_account, "claim_check", lambda: [{"job_id": "j1", "clip_index": 0, "block_reason": "copyright claim"}])
    src = "https://www.youtube.com/watch?v=HuDEDfAntiw"
    # j1's dir is gone (24 h retention): its link comes from Autopilot's run log.
    monkeypatch.setattr(app_module, "_job_source", lambda d: {"url": src} if d.endswith("j2") else {} if d.endswith("j1") else {"url": "other"})
    cfg0 = ap.settings()
    cfg0["runs"] = [{"date": "2026-10-12", "jobs": [{"job_id": "j1", "source": src}]}]
    ap._write(ap.SETTINGS_FILE, cfg0)
    monkeypatch.setattr(app_module, "_plan_items", lambda: [
        {"id": "j1:2", "job_id": "j1", "status": "ready", "title": "sibling"},
        {"id": "j2:0", "job_id": "j2", "status": "ready", "title": "same video, other job"},
        {"id": "j3:0", "job_id": "j3", "status": "ready", "title": "different video"}])
    monkeypatch.setattr(channel_tools, "licence", lambda url: {"licence": "creative_commons", "title": "PATI PATNI Episode 14",
                                                            "channel": "Golden Hyderabadiz", "channel_url": "https://www.youtube.com/@gh"})
    ap.save({"channels": [{"url": "https://www.youtube.com/@gh", "name": "GH"}, {"url": "https://www.youtube.com/@ok"}]})
    notes = []
    app_module._check_claims(notes.append)
    state = post_queue._load()
    assert state["j1:0"]["blocked"] and state["j1:2"]["status"] == "skipped" and state["j2:0"]["status"] == "skipped"
    assert "j3:0" not in state
    cfg = ap.settings()
    assert cfg["blocked_sources"][0]["video"] == "HuDEDfAntiw" and [c["url"] for c in cfg["channels"]] == ["https://www.youtube.com/@ok"]
    assert ap.is_blocked(cfg, {"url": "https://youtu.be/XXXXXXXXXXX", "channel_url": "https://www.youtube.com/@gh"})
    assert ap.is_blocked(cfg, {"url": src, "channel_url": ""}) and not ap.is_blocked(cfg, {"url": "https://youtu.be/YYYYYYYYYYY"})
    assert not ap.block_source(src, "again")                                   # once


def test_auto_upload_waits_three_hours_after_the_daily_limit(monkeypatch):
    import time as _t
    import youtube_account
    monkeypatch.setattr(youtube_account, "status", lambda: {"connected": True})
    ap.save({"auto_upload": True})
    assert ap.auto_post_due(ap.settings())
    calls = []

    def post_ready():
        calls.append(1)
        return {"done": 3, "limit": True}
    ap.run_auto_post(post_ready, print)
    cfg = ap.settings()
    assert calls and cfg["upload_paused_until"] >= _t.time() + 3 * 3600 - 5
    assert not ap.auto_post_due(cfg)                                           # paused
    assert not ap.auto_post_due(cfg, now=_t.time() + 3 * 3600 - 60)
    assert ap.auto_post_due(cfg, now=_t.time() + 3 * 3600 + 60)
    ap.save({"auto_upload": False})
    assert not ap.auto_post_due(ap.settings(), now=_t.time() + 10 ** 6)


def test_sound_tags_are_never_burned_as_captions():
    import subtitles
    tr = {"segments": [{"words": [{"word": "[Music]", "start": 0.0, "end": 2.0},
                                  {"word": " Jab", "start": 2.0, "end": 2.3}, {"word": " date", "start": 2.3, "end": 2.6},
                                  {"word": "(applause)", "start": 2.6, "end": 3.0}]}]}
    words = [w["word"] for b in subtitles._collect_word_blocks(tr, 0, 5) for w in b]
    assert words == ["Jab", "date"]


# ------------------------------------------------------------- learning loop

def _counted(n, exp, arm, views, start=0):
    return {f"v{exp}{arm}{start + k}": {"counted": True, "exp": exp, "arm": arm, "views": views, "public": True}
            for k in range(n)}


def test_tests_alternate_per_job_and_a_clear_winner_is_kept():
    import learning
    sides = [learning.next_arm() for _ in range(4)]
    assert [(s["exp"], s["arm"]) for s in sides] == [("end_card", "on"), ("end_card", "off")] * 2
    assert sides[1]["overrides"] == {"frame_outro": False} and sides[0]["overrides"] == {}
    st = learning.load()
    st["stats"] = {**_counted(8, "end_card", "on", 4), **_counted(8, "end_card", "off", 20)}
    notes = []
    learning._evaluate(st, notes.append)
    assert st["adopted"] == {"frame_outro": False} and st["done"] == ["end_card"]
    assert st["experiment"]["key"] == "ai_take" and "'off' won" in notes[0]
    learning._save(st)
    nxt = learning.next_arm()
    assert nxt["exp"] == "ai_take" and nxt["overrides"]["frame_outro"] is False   # kept change rides along
    assert learning.summary()["kept"] == ["FOLLOW end card at the end: off"]


def test_a_small_difference_keeps_the_current_look():
    import learning
    learning.next_arm()
    st = learning.load()
    st["stats"] = {**_counted(9, "end_card", "on", 6), **_counted(8, "end_card", "off", 8)}   # 1.33x but only 2 views
    learning._evaluate(st, lambda t: None)
    assert st["adopted"] == {} and st["done"] == ["end_card"] and "no clear difference" in st["history"][-2]["text"]
    st2 = learning.load()
    st2["experiment"] = {"key": "length", "started": int(__import__("time").time()) - 30 * 86400, "assigned": {}}
    st2["stats"] = _counted(2, "length", "short", 50)
    learning._evaluate(st2, lambda t: None)                                      # 21 days, still too few: stop
    assert "length" in st2["done"] and st2["adopted"] == {}
    off = learning.set_learn(False)
    assert not off["learn"] and learning.next_arm()["exp"] is None             # learning off: no tests


def test_sources_are_scored_and_a_poor_one_rests(monkeypatch):
    import learning
    st = learning.load()
    st["stats"] = {f"g{k}": {"counted": True, "views": 40, "source": f"https://youtu.be/GOODGOODG{k:02d}"} for k in range(3)}
    st["stats"].update({f"p{k}": {"counted": True, "views": 0, "source": f"https://youtu.be/POORPOORP{k:02d}"} for k in range(3)})
    monkeypatch.setattr(learning, "_channel_of", lambda s, url: {"url": "https://www.youtube.com/@" + url[-11:-2],
                                                                  "name": url[-11:-2]})
    learning._score_sources(st, lambda t: None)
    good, poor = st["sources"]["https://www.youtube.com/@GOODGOODG"], st["sources"]["https://www.youtube.com/@POORPOORP"]
    assert good["score"] > 1 and poor["score"] == 0.3 and poor["rest_until"] > __import__("time").time()
    assert learning.source_factor("https://www.youtube.com/@POORPOORP", st) == 0.0
    assert learning.source_factor("https://www.youtube.com/@unknown", st) == 1.0


def test_refresh_counts_shorts_after_two_days_and_spots_stuck_private(monkeypatch):
    import learning
    import time as _t
    import youtube_account as ya
    from datetime import datetime, timezone
    now = _t.time()
    iso = lambda ts: datetime.fromtimestamp(ts, timezone.utc).isoformat()
    for vid, age_h in (("OLD", 60), ("NEW", 5), ("STUCK", 70)):
        ya._save_upload({"id": vid, "video_id": vid, "status": "done", "created": int(now - age_h * 3600),
                         "publish_at": iso(now - age_h * 3600), "title": vid, "job_id": "j" + vid, "clip_index": 0,
                         "exp": "end_card", "arm": "on"})
    monkeypatch.setattr(ya, "video_analytics", lambda days: {"OLD": {"avg_percent": 71.0, "subs": 1}})
    monkeypatch.setattr(ya, "_get", lambda url, params: {"items": [
        {"id": "OLD", "statistics": {"viewCount": "120"}, "status": {"privacyStatus": "public"}, "contentDetails": {"duration": "PT31S"}},
        {"id": "NEW", "statistics": {"viewCount": "3"}, "status": {"privacyStatus": "public"}, "contentDetails": {}},
        {"id": "STUCK", "statistics": {}, "status": {"privacyStatus": "private"}, "contentDetails": {}}]})
    st = learning.load()
    learning.refresh(st)
    s = st["stats"]
    assert s["OLD"]["counted"] and s["OLD"]["views"] == 120 and s["OLD"]["avg_percent"] == 71.0 and s["OLD"]["seconds"] == 31
    assert not s["NEW"]["counted"] and not s["STUCK"]["counted"] and st["locked"] == 1


def test_research_leaves_out_a_resting_source(monkeypatch):
    import channel_tools
    import learning
    import short_kit
    import used_moments
    v = lambda i, ch, views: {"id": f"R{i:010d}", "url": f"https://www.youtube.com/watch?v=R{i:010d}", "title": f"stand up {i}",
                              "channel": ch, "channel_url": f"https://www.youtube.com/@{ch}", "seconds": 900, "views": views}
    monkeypatch.setattr(channel_tools, "search", lambda q, **k: [v(1, "resting", 900_000), v(2, "fine", 150_000)])
    monkeypatch.setattr(used_moments, "summary", lambda url: {"count": 0, "seconds": 0})
    monkeypatch.setattr(short_kit, "gemini", lambda: None)
    monkeypatch.setattr(short_kit, "ask_json", lambda c, schema, contents, **k: schema.model_validate(
        {"videos": [{"id": line.split('"id": "')[1][:11], "keep": True, "reason": "ok"}
                    for line in contents.splitlines() if '"id": "' in line]}))
    st = learning.load()
    st["sources"] = {"https://www.youtube.com/@resting": {"score": 0.3, "rest_until": __import__("time").time() + 999}}
    learning._save(st)
    fresh, _ = ap.research_videos({**ap.settings(), "research_queries": ["x"]}, lambda t: None)
    assert [x["channel"] for x in fresh] == ["fine"]


def test_learning_endpoint_answers(monkeypatch):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    c = TestClient(app_module.app)
    d = c.get("/api/learning").json()
    assert d["learn"] and d["counted"] == 0 and d["mature_hours"] == 48
    assert c.put("/api/learning", json={"learn": False}).json()["learn"] is False


def test_a_second_copy_of_the_app_never_runs_the_autopilot_loop(monkeypatch):
    app_module = pytest.importorskip("app")
    started = []

    async def fake_loop(*a, **k):
        started.append(1)
    monkeypatch.setattr(ap, "loop_forever", fake_loop)
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)

    async def enter():
        async with app_module.app.router.lifespan_context(app_module.app):
            await asyncio.sleep(0.05)
    monkeypatch.setenv("AUTOPILOT_LOCAL", "0")
    asyncio.run(enter())
    assert started == []
    monkeypatch.setenv("AUTOPILOT_LOCAL", "1")
    asyncio.run(enter())
    assert started == [1]
