"""The history channel's long videos: research gates, the fact check, picture
rules (free licences, no revered religious figures), the frame-exact timeline,
the description with chapters, and the channel / upload wiring."""
import json
import os
import types

import pytest

import history_videos as hv
import my_channels as mc
import youtube_account as ya

S = hv.Scene


def _script(**kw):
    base = dict(allowed=True, reason="", sacred=False, title="Rome Ki Poori Kahani", thumb_text="ROME GIRA",
                thumb_picture="ruins", summary="Rome ki kahani.",
                hook=[S(line="Saal 476 tha " * 6, picture="a fallen statue", wiki="Fall of Rome", label="476 AD")],
                chapters=[hv.Chapter(title="Shuruaat", scenes=[S(line="Rome ek gaon tha " * 10, picture="village",
                                                                 wiki="Rome", label="ROME")] * 2),
                          hv.Chapter(title="Zawaal", scenes=[S(line="Crisis aaya " * 12, picture="soldiers",
                                                               wiki="Crisis of the Third Century", label="")] * 2)],
                outro="Yeh thi kahani, subscribe karein.", question="Rome kyun gira?", tags=["Roman Empire", "rome"])
    base.update(kw)
    return hv.Script(**base)


def test_minutes_and_shape():
    assert hv.minutes_wanted("45") == 30 and hv.minutes_wanted("1") == 2 and hv.minutes_wanted("x") == 10
    words, chapters, scenes = hv.shape(10)
    assert words == 1500 and chapters == 6 and 3 <= scenes <= 5
    assert hv.shape(2)[1:] == (2, 2) and hv.shape(30)[1] == 12


def test_caption_groups_cover_the_paragraph_and_break_at_punctuation():
    got = hv.chunks("Saal 476 tha, aur Rome gir gaya. Phir kya hua yeh sab ko maloom nahi tha", 2.0, 10.0)
    assert got[0][0] == "Saal 476 tha," and got[0][1] == 2.0
    assert abs(got[-1][2] - 12.0) < 1e-6 and all(len(t.split()) <= 7 for t, _a, _b in got)
    assert all(abs(a[2] - b[1]) < 1e-6 for a, b in zip(got, got[1:]))   # no gaps between groups


def test_the_timeline_is_frame_exact_with_chapters_from_zero():
    script = _script()
    n = len(hv.scenes_of(script))
    said = [(f"v{k}.wav", 20.0) for k in range(n)] + [("o.wav", 8.0), ("q.wav", 4.0)]
    segs, voices, whooshes, marks, sections, total = hv.plan(script, said, "@h", "urdu")
    assert sum(s["frames"] for s in segs) == round(total * hv.FPS)
    assert marks[0] == ("Shuruaat", 0.0) and [m[0] for m in marks[1:]] == ["Shuruaat", "Zawaal"]
    assert len(voices) == n + 2 and voices[0] == ("v0.wav", 0.0)
    # every voice starts on a shot boundary of its own scene, never mid-card
    starts, t = set(), 0
    for s in segs:
        starts.add(round(t / hv.FPS, 3))
        t += s["frames"]
    assert all(round(at, 3) in starts for _w, at in voices)
    assert len(whooshes) == 1 + len(script.chapters) and sections[0] == 0.0 and sections[-1] == total
    assert all(s["frames"] <= hv.SHOT_SECONDS * 1.6 * hv.FPS for s in segs)   # a new shot every ~11 s
    assert segs[-1]["pic"] == "end" and any("SUBSCRIBE" in e for e in segs[-1]["events"])
    assert any("Rome kyun gira" in e for e in segs[-2]["events"])   # the question on screen


def _wiki_api(images, infos):
    def api(params, tries=4):
        if params.get("prop") == "images":
            return {"query": {"pages": {"1": {"images": [{"title": f"File:{n}"} for n in images]}}}}
        pages = {}
        for k, t in enumerate(params["titles"].split("|")):
            lic, w, h, desc = infos[t[5:]]
            pages[str(k)] = {"title": t, "imageinfo": [{
                "thumburl": f"https://upload.example/{k}.jpg", "width": w, "height": h,
                "extmetadata": {"LicenseShortName": {"value": lic}, "ImageDescription": {"value": desc},
                                "Artist": {"value": "<a>Someone</a>"}}}]}
        return {"query": {"pages": pages}}
    return api


def test_pictures_keep_free_places_and_drop_revered_figures(monkeypatch):
    import player_photo
    infos = {"Wikipedia-logo.png": ("CC BY-SA 3.0", 900, 900, ""),
             "Shrine of Imam Hussain in Karbala.jpg": ("CC BY-SA 4.0", 1200, 800, "The shrine at night"),
             "Imam Husayn on horseback.jpg": ("Public domain", 1600, 1000, "A painting"),
             "Battle of Karbala - Brooklyn Museum.jpg": ("Public domain", 1640, 826, "Oil painting"),
             "Iraq physical map.svg": ("CC0", 1238, 1260, "map"),
             "Agency photo.jpg": ("All rights reserved", 2000, 1300, ""),
             "Tiny.jpg": ("CC0", 300, 200, "")}
    monkeypatch.setattr(player_photo, "_api", _wiki_api(list(infos), infos))
    monkeypatch.setattr(hv.time, "sleep", lambda s: None)
    got = {p["file"] for p in hv.wiki_pictures("Battle of Karbala", sacred=True)}
    assert got == {"Shrine of Imam Hussain in Karbala.jpg", "Iraq physical map.svg"}
    # Not a sacred story: the museum painting may stay, a revered figure never.
    got = {p["file"] for p in hv.wiki_pictures("Battle of Karbala", sacred=False)}
    assert "Battle of Karbala - Brooklyn Museum.jpg" in got and "Imam Husayn on horseback.jpg" not in got
    one = hv.wiki_pictures("x")[0]
    assert one["artist"] == "Someone" and one["page"].startswith("https://commons.wikimedia.org/wiki/File:")


def test_a_picture_is_used_at_most_twice_and_ai_goes_to_the_hook_first(monkeypatch):
    picks = hv.Picks(picks=[hv.Pick(scene=k, picture=0) for k in range(4)] + [hv.Pick(scene=9, picture=0)])
    monkeypatch.setattr(hv.kit, "ask_json", lambda c, schema, p, model=None: picks)
    scenes = [S(line="l", picture="p", wiki="", label="")] * 4
    assert hv.pick(None, "t", scenes, [{"file": "a", "desc": ""}], False) == {0: 0, 1: 0}
    assert hv.ai_order(2, [3, 2]) == [0, 1, 2, 5, 3, 4, 6]


def test_a_sacred_story_drops_artwork_with_people_and_its_credit(monkeypatch, tmp_path):
    from PIL import Image
    script = _script(sacred=True)
    pool = [{"file": f"pic{k}.jpg", "url": f"u{k}", "desc": "", "artist": "A", "licence": "CC0", "page": "p"}
            for k in range(2)]
    monkeypatch.setattr(hv, "candidates", lambda articles, sacred: pool)
    monkeypatch.setattr(hv, "pick", lambda client, topic, scenes, pool, sacred: {0: 0, 1: 1})

    def download(url, out):
        Image.new("RGB", (1600, 900), (90, 60, 30)).save(out, "JPEG")
        return out
    monkeypatch.setattr(hv, "download", download)
    monkeypatch.setattr(hv.time, "sleep", lambda s: None)
    looked = []

    def artwork(client, paths):
        looked.append(len(paths))
        return {k for k, p in enumerate(paths) if p.endswith("w001")}   # the second picture is a painting
    monkeypatch.setattr(hv, "artwork_with_people", artwork)
    made = []

    def ai(client, prompt, out, sacred):
        made.append(sacred)
        Image.new("RGB", (1600, 900), (20, 20, 20)).save(out, "JPEG")
        return out
    monkeypatch.setattr(hv, "ai_picture", ai)
    monkeypatch.setattr(hv, "AI_IMAGES", 1)
    pics, title, credits, ai_used, first, stock = hv.pictures(None, script, "t", str(tmp_path), log=lambda *a: None)
    assert looked == [2] and [c.split(":")[0] for c in credits] == ["pic0.jpg"]
    assert ai_used == 1 and made == [True]          # the hook scene got an AI picture without people
    assert set(pics) == set(range(len(hv.scenes_of(script))))   # every scene has a picture
    assert all(os.path.isfile(os.path.join(tmp_path, v)) for p in pics.values() for v in p.values())
    # Not sacred: nobody looks, the painting stays.
    looked.clear()
    pics, title, credits, ai_used, first, stock = hv.pictures(None, _script(), "t", str(tmp_path), log=lambda *a: None)
    assert looked == [] and len(credits) == 2


def _research(facts="REPORTED: Rome fell in 476 AD", n=4):
    return lambda client, topic, minutes: (facts, "Surprising: x", [(f"s{k}", f"https://s{k}") for k in range(n)])


def test_thin_research_and_refused_topics_make_no_video(monkeypatch):
    with pytest.raises(RuntimeError, match="reliable sources"):
        hv.write(None, "t", "@h", research_fn=_research("NOT FOUND"))
    with pytest.raises(RuntimeError, match="reliable sources"):
        hv.write(None, "t", "@h", research_fn=_research(n=2))
    monkeypatch.setattr(hv.kit, "ask_json", lambda c, schema, p, model=None:
                        _script(allowed=False, reason="only told by judging a sect"))
    with pytest.raises(RuntimeError, match="judging a sect"):
        hv.write(None, "t", "@h", research_fn=_research())


def test_the_fact_check_gets_one_rewrite_then_no_video(monkeypatch):
    calls = []

    def ask(client, schema, prompt, model=None):
        calls.append((schema.__name__, prompt))
        if schema is hv.Script:
            return _script()
        return hv.Check(ok=False, problems=["476 AD is right but the script says 467"])
    monkeypatch.setattr(hv.kit, "ask_json", ask)
    with pytest.raises(RuntimeError, match="fact check"):
        hv.write(None, "t", "@h", minutes=2, research_fn=_research())
    assert [c[0] for c in calls] == ["Script", "Check", "Script", "Check"]
    assert "the script says 467" in calls[2][1]


def test_a_short_script_is_asked_once_for_more_words(monkeypatch):
    calls = []

    longer = _script(chapters=[hv.Chapter(title=f"Hissa {k}", scenes=[S(line="Rome ek gaon tha " * 20,
                                                                      picture="p", wiki="", label="")] * 2)
                               for k in (1, 2)])

    def ask(client, schema, prompt, model=None):
        calls.append(schema.__name__)
        return longer if schema is hv.Script else hv.Check(ok=True, problems=[])
    monkeypatch.setattr(hv.kit, "ask_json", ask)
    script, facts, sources = hv.write(None, "t", "@h", minutes=10, research_fn=_research())
    # 10 minutes wants ~1500 words; the fake script has far fewer: one rewrite asked for more,
    # and the second (still short, fact check fine, long enough for 2 minutes) is used.
    assert calls == ["Script", "Check", "Script", "Check"] and len(sources) == 4
    # Under even 2 minutes twice: no video, and the reason says so.
    monkeypatch.setattr(hv.kit, "ask_json", lambda c, schema, p, model=None:
                        _script() if schema is hv.Script else hv.Check(ok=True, problems=[]))
    with pytest.raises(RuntimeError, match="too short twice"):
        hv.write(None, "t", "@h", minutes=10, research_fn=_research())


def test_the_description_has_chapters_sources_and_credits_within_youtubes_limit():
    script = _script()
    marks = [("Shuruaat", 0.0), ("Chapter one", 45.2), ("Chapter two", 3725.0)]
    credits = [f"File {k}.jpg: Artist {k}, CC BY-SA 4.0 (https://commons.wikimedia.org/wiki/File:{k})"
               for k in range(80)]
    d = hv.describe(script, marks, [("Britannica", "https://britannica.com/x")], credits, "@HistoryKahani",
                    "urdu", True)
    assert "0:00 Shuruaat\n0:45 Chapter one\n1:02:05 Chapter two" in d
    assert "- Britannica: https://britannica.com/x" in d and "AI illustrations" in d
    assert "more, credited on their Wikimedia Commons pages" in d and len(d) <= ya.DESCRIPTION_MAX
    assert d.rstrip().endswith("#history #urdu #RomanEmpire") and "@HistoryKahani" in d


def test_reputable_sources_are_listed_first():
    got = hv.rank_sources([("wikihow.com", "u1"), ("odysseytraveller.com", "u2"), ("britannica.com", "u3"),
                           ("medium.com", "u4"), ("mpm.edu", "u5")])
    assert [n for n, _u in got] == ["britannica.com", "mpm.edu", "odysseytraveller.com", "wikihow.com", "medium.com"]


def test_ideas_hear_the_owner_and_what_gets_views(monkeypatch):
    import cricket_shorts
    seen = {}

    def grounded(client, prompt):
        seen["prompt"] = prompt
        return "topic: Karbala: what happened in 680 AD\ntopic: Old one\nmatch: no", []
    monkeypatch.setattr(cricket_shorts, "grounded", grounded)
    monkeypatch.setattr(hv, "trending", lambda lang: ["Rome ki kahani (900,000 views)"])
    got = hv.channel_ideas(None, 2, avoid=["Old one"], notes="Rome, Karbala", lang="urdu", minutes=12)
    assert got == [{"kind": "topic", "text": "Karbala: what happened in 680 AD"}]
    assert "Rome, Karbala" in seen["prompt"] and "900,000 views" in seen["prompt"] and "12-minute" in seen["prompt"]


def test_the_history_channel_makes_1_to_3_long_videos(monkeypatch):
    ch = mc.add("history")
    assert ch["per_day"] == 2 and ch["minutes"] == 10 and ch["lang"] == "urdu" and "Karbala" in ch["notes"]
    ch = mc.update(ch["id"], {"per_day": 9, "minutes": 45, "lang": "french", "post_times": ["1:00", "2:00",
                                                                                            "3:00", "4:00"]})
    assert ch["per_day"] == 3 and ch["minutes"] == 30 and ch["lang"] == "urdu" and len(ch["post_times"]) == 3
    ch = mc.update(ch["id"], {"minutes": 12, "lang": "english"})
    s = mc.summary(mc.get(ch["id"]))
    assert s["max_per_day"] == 3 and s["long"] is True and s["minutes"] == 12 and s["lang"] == "english"
    assert mc.summary(mc.get(mc.add("quiz")["id"]))["max_per_day"] == mc.MAX_PER_DAY
    asked = {}

    def ideas(client, count, avoid, best, worst, **kw):
        asked.update(kw)
        return [{"kind": "topic", "text": "Rome: how the greatest empire fell"}]
    monkeypatch.setattr(hv, "channel_ideas", ideas)
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["genre"] == "history" and payload["history_minutes"] == 12 and payload["history_lang"] == "english"
    assert payload["history_topic"].startswith("Rome") and meta["format"] == "history"
    assert asked == {"notes": ch["notes"], "lang": "english", "minutes": 12}


def test_a_history_job_waits_up_to_3_hours_before_it_counts_as_stuck():
    ch = mc.add("history")
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "j1", "status": "running", "at": 1000, "day": "d"}]))
    ch = mc.refresh_jobs(mc.get(ch["id"]), lambda j: ("running", []), "out", now=1000 + 2 * 3600)
    assert ch["jobs"][0]["status"] == "running"
    ch = mc.refresh_jobs(ch, lambda j: ("running", []), "out", now=1000 + 4 * 3600)
    assert ch["jobs"][0]["status"] == "failed"


def test_process_accepts_a_history_job(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    mc.add("history")
    r = TestClient(app_module.app).post("/api/process", json={
        "genre": "history", "channel": "history", "history_topic": "Karbala: 680 AD", "history_minutes": 99,
        "history_lang": "english", "bg_music": True, "acknowledged": True}, headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 200, r.text
    env = app_module.jobs[r.json()["job_id"]]["env"]
    assert env["HISTORY_TOPIC"] == "Karbala: 680 AD" and env["HISTORY_MINUTES"] == "30"
    assert env["HISTORY_LANG"] == "english" and env["BG_MUSIC"] == "1" and env["CONTENT_GENRE"] == "history"


def test_job_clips_carry_the_thumbnail_and_the_ai_label(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    job = tmp_path / "jobh"
    job.mkdir()
    (job / "History_x_clip_1.mp4").write_bytes(b"v")
    (job / "thumbnail.jpg").write_bytes(b"j")
    (job / "History_x_metadata.json").write_text(json.dumps({"genre": "history", "shorts": [{
        "start": 0, "end": 600, "seo_title": "T", "seo_description": "D", "ai_made": True,
        "thumbnail_file": "thumbnail.jpg", "comment_question": "Q?"}]}))
    state, clips = app_module._job_clips("jobh")
    assert clips[0]["ai_made"] is True and clips[0]["thumbnail"] == str(job / "thumbnail.jpg")
    assert clips[0]["seconds"] == 600 and clips[0]["question"] == "Q?"


class _R:
    def __init__(self, code, body=None, headers=None):
        self.status_code, self._body, self.headers, self.text = code, body or {}, headers or {}, ""

    def json(self):
        return self._body


def test_a_long_video_streams_up_with_its_length_and_gets_a_watch_link(tmp_path, monkeypatch):
    clip = tmp_path / "long.mp4"
    clip.write_bytes(os.urandom(9 << 20))   # more than one 8 MB piece
    ya._write(ya.TOKEN_FILE, {"access_token": "tok", "refresh_token": "r", "expires_at": 9e12})
    sent = {}
    monkeypatch.setattr(ya.httpx, "post", lambda url, params=None, headers=None, json=None, timeout=None, **kw:
                        _R(200, headers={"location": "https://upload.example/s"}) if "videos" in url else None)

    def put(url, content=None, headers=None, timeout=None):
        sent["data"] = b"".join(content)
        sent["headers"] = headers
        return _R(200, {"id": "LONG1", "status": {"privacyStatus": "private"}})
    monkeypatch.setattr(ya.httpx, "put", put)
    row = ya.upload(str(clip), "Rome", "D", [], "history", privacy="public")
    assert sent["data"] == clip.read_bytes() and sent["headers"]["Content-Length"] == str(9 << 20)
    assert row["url"] == "https://youtube.com/watch?v=LONG1"


def test_a_refused_thumbnail_is_recorded_and_spends_its_units(tmp_path, monkeypatch):
    thumb = tmp_path / "t.jpg"
    thumb.write_bytes(b"jpeg")
    ya._write(ya.TOKEN_FILE, {"access_token": "tok", "refresh_token": "r", "expires_at": 9e12})
    before = ya.quota_used()
    monkeypatch.setattr(ya.httpx, "post", lambda *a, **k: types.SimpleNamespace(
        status_code=403, text='{"error": {"message": "The authenticated user doesnt have permissions to upload '
                              'and set custom video thumbnails."}}',
        json=lambda: {"error": {"message": "The authenticated user doesnt have permissions to upload and set "
                                           "custom video thumbnails."}}))
    row = ya.add_thumbnail({"id": "r1", "video_id": "LONG1", "status": "done"}, str(thumb))
    assert row["thumbnail"] == "failed" and "thumbnails" in row["thumbnail_error"]
    assert ya.quota_used() == before + 50


def test_an_uploaded_long_video_gets_its_teaser_short_next(monkeypatch):
    import time as _t
    ch = mc.add("history")
    now = _t.time()
    mc._change(ch["id"], lambda c: c.update(per_day=1, jobs=[
        {"job_id": "long1", "status": "uploaded", "at": now - 600, "day": mc.today(), "label": "Rome",
         "topic": "Rome", "format": "history", "video_id": "AbCdEfGhIjK", "slot": "2026-10-15T18:00:00+05:00"}]))
    ch = mc.get(ch["id"])
    assert mc.teaser_due(ch)["job_id"] == "long1"
    assert mc.wants_more(ch)                                        # past today's 1 long video, still a teaser
    payload, meta = mc.next_payload(ch, lambda: None)
    assert payload["history_teaser_of"] == "long1" and payload["history_video_id"] == "AbCdEfGhIjK"
    assert meta["format"] == "teaser" and meta["publish_after"] == "2026-10-15T18:00:00+05:00"
    ch = mc.get(ch["id"])
    assert mc.teaser_due(ch) is None                                # started: not asked twice
    assert mc.keeps("long1", ch["id"], 3600) is False               # its teaser is under way
    mc._change(ch["id"], lambda c: c["jobs"].append({"job_id": "t1", "status": "done", "day": mc.today(),
                                                     "format": "teaser", "at": now}))
    assert len(mc._jobs_on(mc.get(ch["id"]), mc.today(), ("done", "uploaded"))) == 1    # teasers are extra


def test_a_long_video_waiting_for_its_teaser_is_kept_and_an_old_one_is_not(monkeypatch):
    import time as _t
    ch = mc.add("history")
    mc._change(ch["id"], lambda c: c.update(jobs=[
        {"job_id": "long1", "status": "uploaded", "at": _t.time() - 600, "format": "history", "video_id": "x" * 11}]))
    assert mc.keeps("long1", ch["id"], 600) is True
    mc._change(ch["id"], lambda c: c["jobs"][0].update(at=_t.time() - mc.TEASER_WINDOW - 60))
    assert mc.teaser_due(mc.get(ch["id"])) is None
    assert mc.teaser_due(mc.get(mc.add("quiz")["id"])) is None       # Shorts channels have no teasers


def test_the_teaser_uses_the_opening_under_a_minute(tmp_path):
    import math
    import struct
    import wave
    names = []
    for k, secs in enumerate([18.0, 16.0, 20.0, 12.0]):
        name = f".hv_{k + 1}.wav"
        with wave.open(str(tmp_path / name), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(struct.pack("<h", 0) * int(secs * 8000))
        names.append(name)
    script = _script()        # 1 hook scene, then chapter scenes
    plan = hv.teaser_plan(script, names, str(tmp_path))
    assert [p[0] for p in plan] == [0, 1]                           # hook + one scene, then 25 s reached
    assert sum(p[3] for p in plan) <= hv.TEASER_MAX
    assert hv.teaser_plan(script, [None] * 4, str(tmp_path)) == []


def test_process_accepts_a_teaser_only_for_a_job_on_this_computer(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    client = TestClient(app_module.app)
    body = {"genre": "history", "history_teaser_of": "longjob-123", "history_video_id": "AbCdEfGhIjK",
            "acknowledged": True}
    r = client.post("/api/process", json=body, headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 400
    (tmp_path / "longjob-123").mkdir()
    r = client.post("/api/process", json=body, headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 200, r.text
    env = app_module.jobs[r.json()["job_id"]]["env"]
    assert env["HISTORY_TEASER_OF"] == str(tmp_path / "longjob-123") and env["HISTORY_VIDEO_ID"] == "AbCdEfGhIjK"


def test_a_teaser_goes_up_15_minutes_after_its_long_video(monkeypatch):
    from datetime import datetime, timedelta
    import youtube_account
    ch = mc.add("history")
    after = (datetime.now().astimezone() + timedelta(hours=5)).replace(microsecond=0)
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "t1", "status": "done", "format": "teaser",
                                                   "at": 1, "publish_after": after.isoformat()}]))
    monkeypatch.setattr(youtube_account, "status", lambda: {"connected": True})
    sent = {}

    def upload(path, title, desc, tags, genre, publish_at=None, ai_made=False, meta=None):
        sent.update(genre=genre, at=publish_at, meta=meta)
        return {"status": "done", "video_id": "TeAsEr00001", "title": title}
    monkeypatch.setattr(youtube_account, "upload", upload)
    clip = {"index": 0, "path": "p.mp4", "title": "T", "description": "D", "tags": []}
    got = mc.upload_waiting(mc.get(ch["id"]), lambda job: ("completed", [clip]), log=lambda *a: None)
    assert got["done"] == 1 and sent["genre"] == "history_teaser"
    assert sent["at"] == after + timedelta(minutes=15) and sent["meta"]["format"] == "teaser"
    assert youtube_account.CATEGORY["history_teaser"] == "27" and "history_teaser" not in youtube_account.LONG_GENRES


def test_a_stock_clip_plays_as_a_history_shot(tmp_path):
    import subprocess
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1280x720:d=2:r=25",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    events = hv.shot_events(3.0, "476 AD", [("Rome gir gaya", 0.2, 1.5)], "@h")
    # 3 s from a 2 s clip: it loops; the closer crop and a later start must work too.
    hv.segment_video(str(tmp_path), str(clip), "s.mp4", 90, 0.8, True, events)
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                            "stream=width,height,nb_read_frames,r_frame_rate", "-of", "csv=p=0", str(tmp_path / "s.mp4")],
                           capture_output=True, text=True).stdout.strip()
    assert probe == "1920,1080,30/1,90"
    assert not list(tmp_path.glob("*.ass"))


def test_scenes_wikipedia_has_nothing_for_get_stock_footage_for_free(monkeypatch, tmp_path):
    import subprocess
    import broll
    import stock_media
    from PIL import Image
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:d=3:r=30",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (2400, 1350), (90, 70, 50)).save(photo)
    monkeypatch.setattr(hv, "candidates", lambda articles, sacred: [])
    monkeypatch.setattr(hv, "AI_IMAGES", 0)
    monkeypatch.setattr(stock_media, "available", lambda: True)
    asked = {}
    monkeypatch.setattr(broll, "terms_for", lambda client, topic, lines, rule="": asked.update(rule=rule) or ["t"] * len(lines))
    items = [{"kind": "video", "path": str(clip), "seconds": 3.0, "provider": "Pexels", "author": "Ann", "page": "p"},
             {"kind": "photo", "path": str(photo), "seconds": 0.0, "provider": "Pixabay", "author": "", "page": "q"}]
    monkeypatch.setattr(stock_media, "for_scenes", lambda client, topic, lines, terms, portrait, log, rule:
                        (items + [None] * len(lines))[:len(lines)])
    script = _script(sacred=True)
    pics, title, credits, ai_used, thumb, stock = hv.pictures(None, script, "t", str(tmp_path), log=lambda *a: None)
    assert pics[0]["video"] == str(clip) and os.path.isfile(os.path.join(tmp_path, pics[0]["full"]))
    assert "video" not in pics[1] and len(stock) == 2 and ai_used == 0 and credits == []
    assert "modern things" in asked["rule"] and "NO people" in asked["rule"]        # sacred: no people in footage
    assert set(pics) == set(range(len(hv.scenes_of(script))))


def test_a_failed_matching_call_falls_back_to_each_scenes_own_article():
    scenes = [S(line="l", picture="p", wiki="Colosseum", label=""), S(line="l", picture="p", wiki="Colosseum", label=""),
              S(line="l", picture="p", wiki="Nowhere", label="")]
    pool = [{"file": "a", "article": "Colosseum"}, {"file": "b", "article": "Rome"}, {"file": "c", "article": "Colosseum"}]
    assert hv.own_article_picks(scenes, pool) == {0: 0, 1: 2}


def test_gemini_blips_are_retried_and_real_errors_are_not(monkeypatch):
    import short_kit as kit
    monkeypatch.setattr(kit.time, "sleep", lambda s: None)
    calls = []

    class Models:
        def generate_content(self, model, contents, config=None):
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("httpx.ConnectError: [Errno 11001] getaddrinfo failed")
            return types.SimpleNamespace(text='{"ok": true, "problems": []}')
    client = types.SimpleNamespace(models=Models())
    assert kit.ask_json(client, hv.Check, "x").ok and len(calls) == 3
    calls.clear()

    class Bad:
        def generate_content(self, model, contents, config=None):
            calls.append(1)
            raise ValueError("400 INVALID_ARGUMENT: bad schema")
    with pytest.raises(ValueError):
        kit.ask_json(types.SimpleNamespace(models=Bad()), hv.Check, "x")
    assert len(calls) == 1
