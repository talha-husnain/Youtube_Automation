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
    pics, title, credits, ai_used, first = hv.pictures(None, script, "t", str(tmp_path), log=lambda *a: None)
    assert looked == [2] and [c.split(":")[0] for c in credits] == ["pic0.jpg"]
    assert ai_used == 1 and made == [True]          # the hook scene got an AI picture without people
    assert set(pics) == set(range(len(hv.scenes_of(script))))   # every scene has a picture
    assert all(os.path.isfile(os.path.join(tmp_path, v)) for p in pics.values() for v in p.values())
    # Not sacred: nobody looks, the painting stays.
    looked.clear()
    pics, title, credits, ai_used, first = hv.pictures(None, _script(), "t", str(tmp_path), log=lambda *a: None)
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
