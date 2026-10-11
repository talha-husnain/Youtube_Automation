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
    cfg = {**ap.DEFAULTS, "channels": [{"url": "A"}, {"url": "B"}], "cc_only": True}
    notes = []
    got = ap.pick_videos(cfg, 5, notes.append)
    assert [(v["title"], n) for v, n in got] == [("b2", 3), ("a1", 2)]
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
    ap.save({"channels": [{"url": "A"}], "comedy_per_day": 2, "cricket_per_day": 1, "cc_only": False})
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
        sent["put"] = (url, len(content))
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
    ap.save({"enabled": True, "channels": [{"url": "u"}]})
    assert sc.autopilot()["status"] == "ok" and "Next run" in sc.autopilot()["detail"]


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
