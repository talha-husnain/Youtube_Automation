"""YouTube's own numbers (5-nov-2026, yt_insights.py): where viewers leave, what they searched, the 2027 YPP
targets, thumbnail reach and the CTR A/B test, podcasts, and where each shows (lessons, Studio, the week report)."""
import json
import time

import pytest

import engage
import my_channels as mc
import yt_insights as yi
import youtube_account as ya


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setattr(ya, "TOKEN_FILE", str(tmp_path / "main_token.json"))
    monkeypatch.setattr(ya, "UPLOADS_FILE", str(tmp_path / "main_uploads.json"))
    monkeypatch.setattr(yi, "STATE_FILE", str(tmp_path / "insights.json"))


def _answer(rows, names):
    return {"columnHeaders": [{"name": n} for n in names], "rows": rows}


# The live curve of the music channel's top Short (5-nov-2026), cut to 20 of its 100 points.
LIVE = [(0.01, 1.0435, 0.31), (0.05, 1.0, 0.3), (0.1, 0.9, 0.2), (0.11, 0.78, 0.1), (0.16, 0.478, 0.1), (0.2, 0.304, 0.1),
        (0.25, 0.217, 0.1), (0.3, 0.217, 0.1), (0.4, 0.174, 0.1), (0.5, 0.13, 0.1), (0.6, 0.13, 0.1),
        (0.7, 0.087, 0.1), (0.8, 0.087, 0.1), (0.9, 0.087, 0.1), (0.95, 0.043, 0.1), (1.0, 0.043, 0.1)]


def test_a_curve_says_where_viewers_leave_in_seconds():
    s = yi.curve_summary(LIVE, 52.6, drops=2)
    assert s["points"][0][0] == 0.5 and s["points"][0][1] == pytest.approx(104.35, abs=0.06)
    assert s["points"][-1] == [52.6, 4.3]
    assert 7 < s["half_at"] < 9 and s["end"] == 4.3 and s["vs_others"] < 0.5
    assert s["drops"] and all(d["lost"] > 0 and d["to"] > d["at"] for d in s["drops"])
    assert s["drops"][0]["at"] < 10                          # the big fall is in the first seconds
    assert yi.curve_summary([], 50) is None and yi.curve_summary(LIVE, 0) is None
    words = [{"word": " Sun", "start": 4.5, "end": 5.0}, {"word": " on", "start": 5.0, "end": 5.2},
             {"word": " later", "start": 20.0, "end": 20.5}]
    assert yi.words_at(words, 4.7, 6.3) == "Sun on"


def test_retention_and_search_ask_youtube_the_documented_way(monkeypatch):
    calls = []

    def get(url, params):
        calls.append((url, params))
        if params.get("dimensions") == "elapsedVideoTimeRatio":
            return _answer([[0.5, 0.6, 0.4], [0.01, 1.0, 0.5]], ["elapsedVideoTimeRatio", "audienceWatchRatio",
                                                                   "relativeRetentionPerformance"])
        return _answer([["long distance song", 9], ["", 4], ["pop punk", 3]], ["insightTrafficSourceDetail", "views"])
    monkeypatch.setattr(ya, "_get", get)
    assert yi.retention("VID") == [(0.01, 1.0, 0.5), (0.5, 0.6, 0.4)]
    assert calls[0][1]["filters"] == "video==VID" and calls[0][1]["ids"] == "channel==MINE"
    assert yi.search_terms("VID") == [("long distance song", 9), ("pop punk", 3)]
    p = calls[1][1]
    assert p["filters"] == "insightTrafficSourceType==YT_SEARCH;video==VID" and p["sort"] == "-views" and p["maxResults"] == 25
    assert "long distance song" in yi.search_hint([("long distance song", 9)]) and yi.search_hint([]) == ""


def test_the_2027_numbers_read_the_spellings_youtube_really_sends(monkeypatch):
    def get(url, params):
        if url.endswith("/channels"):
            return {"items": [{"statistics": {"subscriberCount": "321"}}]}
        if "engagedViews" in params["metrics"]:
            return _answer([["shorts", 714, 181]], ["creatorContentType", "views", "engagedViews"])
        return _answer([["shorts", 23], ["videoOnDemand", 600], ["liveStream", 60]],
                       ["creatorContentType", "estimatedMinutesWatched"])
    monkeypatch.setattr(ya, "_get", get)
    n = yi.ypp_numbers()
    assert n["shorts_views"] == 714 and n["shorts_engaged"] == 181 and n["long_hours"] == 11.0 and n["subscribers"] == 321
    line = yi.ypp_line("Music", n)
    assert "181 engaged views" in line and "10M" in line and "11 long-video watch hours" in line and "321 subscribers" in line
    assert "0.1 long-video" in yi.ypp_line("H", {**n, "long_hours": 0.1})


def test_the_week_report_ends_with_the_2027_targets():
    import reminders
    now = time.time()
    rows = {"main": [{"video_id": "a" * 11, "status": "done", "created": now - 3600, "title": "One"}]}
    text = reminders.week_text({"channels": [{"id": "main", "name": "Punchline Bazaar"}, {"id": "q", "name": "Quiz"}]},
                               now, rows_fn=lambda cid: (rows.get(cid, []), lambda r: 5),
                               ypp_fn=lambda cid: {"shorts_engaged": 5000, "long_hours": 2.5, "subscribers": 40}
                               if cid == "main" else None)
    assert "1 Feb 2027" in text and "YPP 2027, Punchline Bazaar" in text and "YPP 2027, Quiz" not in text


def test_reach_reports_add_up_impressions_and_clicks(monkeypatch):
    import httpx
    csv_a = "date,channel_id,video_id,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n" \
            "20261101,UC1,V1,1000,0.05\n20261101,UC1,V2,0,0\n"
    csv_b = "date,channel_id,video_id,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n20261102,UC1,V1,1000,3\n"
    assert yi.parse_reach(csv_a) == {"V1": [1000.0, 50.0]}
    made = []

    def reporting(method, path, **kw):
        if path == "/jobs" and method == "GET":
            return {"jobs": []}
        if path == "/jobs" and method == "POST":
            made.append(kw["json"])
            return {"id": "J1"}
        return {"reports": [{"id": "r1", "startTime": "a", "downloadUrl": "u1"},
                            {"id": "r2", "startTime": "b", "downloadUrl": "u2"}]}
    monkeypatch.setattr(yi, "_reporting", reporting)
    monkeypatch.setattr(yi, "_auth", lambda: {})
    monkeypatch.setattr(httpx, "get", lambda url, **kw: type("R", (), {"status_code": 200,
                                                                       "text": csv_a if url == "u1" else csv_b})())
    got = yi.reach("music")
    assert made == [{"reportTypeId": "channel_reach_basic_a1", "name": "Shortkaar thumbnail reach"}]
    assert got == {"V1": {"impressions": 2000, "ctr": 4.0}}                 # 5% of 1000 + 3% of 1000
    assert yi.reach("music") == got                                        # read once: no report counted twice


# ---------- the channel: lessons, the CTR test ----------

def test_lessons_reach_the_writers():
    rows = [{"curve": {"points": [[0, 100], [10, 40]], "half_at": h, "drops": [{"at": d, "to": d + 1, "lost": 20}],
                       "end": 30}} for h, d in ((3.0, 1.0), (4.0, 2.0), (5.0, 3.0))]
    lesson = yi.retention_lesson(rows)
    assert "0:04" in lesson and "0:02" in lesson and "30% are still there" in lesson
    assert yi.retention_lesson(rows[:2]) == ""                              # too few to say
    text = mc.hook_text({"retention_lesson": lesson, "search": [["long distance song", 9]]})
    assert "WHERE THIS CHANNEL'S VIEWERS LEAVE" in text and "long distance song" in text
    assert mc.hook_text({}) == ""


def test_long_videos_test_the_thumbnail_side_by_click_rate():
    ch = mc.add("history")
    a = mc.ab_choice(mc.get(ch["id"]), "thumb")
    mc._change(ch["id"], lambda c: c.update(jobs=[{"thumb": a, "status": "uploaded", "at": time.time()}]))
    assert mc.ab_choice(mc.get(ch["id"]), "thumb") != a                     # alternates until a side wins
    rows = ([{"thumb": "left", "ctr": 3.0 + k / 10, "views": 1, "created": time.time()} for k in range(12)]
            + [{"thumb": "right", "ctr": 6.0 + k / 10, "views": 1, "created": time.time()} for k in range(12)]
            + [{"thumb": "right", "views": 9, "created": time.time()}])     # no reach numbers yet: not counted
    res = mc.ab_stats(rows)["thumb"]
    assert res["left"]["shorts"] == 12 and res["right"]["shorts"] == 12 and res["right"]["median"] == 6.55
    assert mc.ab_winner(res, "thumb") == "right"
    line = mc.ab_line({"kind": "history", "stats": {"ab": {"thumb": res}}})[0]
    assert "% click rate" in line and "text right" in line


def test_the_thumbnail_text_takes_the_side_it_is_given(tmp_path, monkeypatch):
    import history_videos as hv
    from PIL import Image
    src = tmp_path / "pic.jpg"
    Image.new("RGB", (1920, 1080), (200, 200, 200)).save(src)
    script = hv.Script(allowed=True, reason="", sacred=False, title="T", thumb_text="ROME GIRA", thumb_picture="",
                       summary="", hook=[], chapters=[], outro="", question="", tags=[])
    monkeypatch.setattr(hv, "AI_THUMBNAIL", False)
    for side in ("left", "right"):
        monkeypatch.setenv("HISTORY_THUMB", side)
        out = hv._thumbnail(None, script, str(tmp_path), str(src))
        im = Image.open(out).convert("L")
        left, right = im.crop((0, 0, 200, 720)), im.crop((1080, 0, 1280, 720))
        dark_left = sum(left.getdata()) < sum(right.getdata())
        assert dark_left == (side == "left")                                   # the fade sits under the text


# ---------- Studio ----------

def test_studio_shows_an_uploaded_videos_curve_with_the_words_said(monkeypatch, tmp_path):
    import studio
    import uuid
    ch = mc.add("music")
    jid = str(uuid.uuid4())
    path = tmp_path / "studio_output" / jid
    monkeypatch.setattr(studio, "OUTPUT_DIR", str(tmp_path / "studio_output"))
    path.mkdir(parents=True)
    (path / "Song_metadata.json").write_text(json.dumps({"shorts": [{"start": 0, "end": 30}], "transcript": {
        "segments": [{"words": [{"word": " Sun", "start": 4.6, "end": 5.0}, {"word": " fades", "start": 5.0, "end": 6.0}]}]}}),
        encoding="utf-8")
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": jid, "status": "uploaded", "video_id": "VID00000001"}]))
    with ya.use(mc.account(ch["id"])):
        ya._save_upload({"id": "row1", "video_id": "VID00000001", "status": "done", "views": 55, "retention": 23.1,
                         "curve": {"points": [[0, 100], [30, 5]], "drops": [{"at": 4.7, "to": 6.3, "lost": 26.1}],
                                   "half_at": 7.9, "end": 4.3, "vs_others": 0.11},
                         "search": [["long distance song", 9]], "search_at": time.time()})
    got = studio.insights(jid, mc.channels())
    assert got["on_youtube"] and got["views"] == 55 and got["curve"]["drops"][0]["said"] == "Sun fades"
    assert got["search"] == [["long distance song", 9]]
    assert studio.insights(str(uuid.uuid4()), mc.channels()) == {"on_youtube": False}


# ---------- podcasts ----------

def test_long_playlists_become_podcasts_once(monkeypatch, tmp_path):
    import httpx
    acct = None
    engage._update(acct, lambda s: s.update(playlists={"History and stories": "PL1", "History in 60 seconds": "PL2",
                                                       "Fatah-e-Andalus (series)": "PL3"}))
    monkeypatch.setattr(ya, "_get", lambda url, params: {"items": [{"snippet": {"title": "History and stories",
                                                                                "description": "d"},
                                                                    "status": {"privacyStatus": "public"}}]})
    monkeypatch.setattr(ya, "_token", lambda: "t")
    posts, puts = [], []

    def post(url, params=None, content=None, headers=None, timeout=None):
        posts.append((url, params, content))
        return type("R", (), {"status_code": 200})()

    def put(url, params=None, json=None, headers=None, timeout=None):
        puts.append(json)
        return type("R", (), {"status_code": 200})()
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(httpx, "put", put)
    n = engage.podcasts(acct, "history", "Tareekh", "#1F1408", log=lambda *a: None)
    assert n == 2                                                           # the 60-second list is not a show
    assert all(p[0] == engage.PLAYLIST_IMAGES_UPLOAD and b'"type": "hero"' in p[2] and b"image/jpeg" in p[2] for p in posts)
    assert all(j["status"]["podcastStatus"] == "enabled" and j["snippet"]["title"] for j in puts)
    assert engage.podcasts(acct, "history", "Tareekh", log=lambda *a: None) == 0      # once each
    assert engage.podcasts(acct, "quiz", "Q", log=lambda *a: None) == 0              # Shorts channels: never


def test_the_podcast_cover_is_square_and_small(tmp_path):
    from PIL import Image
    out = engage.podcast_image("Horror Stories in Urdu: full stories", "Raat Ki Kahaniyan", str(tmp_path / "c.jpg"))
    with Image.open(out) as im:
        assert im.size == (1400, 1400)
    assert (tmp_path / "c.jpg").stat().st_size < 2 * 1024 * 1024
