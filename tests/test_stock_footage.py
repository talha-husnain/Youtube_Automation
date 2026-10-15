"""Free stock footage (stock_media.py) and the moving background (broll.py):
the library answers parsed and cached, clips picked per scene and not reused,
shots cut to the voice frame-exactly, and a real background rendered."""
import os
import subprocess
import types

import pytest

import broll
import stock_media as sm


class _R:
    def __init__(self, data, code=200):
        self.status_code, self._data = code, data

    def json(self):
        return self._data


PEXELS = {"videos": [
    {"id": 1, "duration": 12, "url": "https://pexels.com/video/1", "image": "https://img/1.jpg", "user": {"name": "Ann"},
     "video_files": [{"width": 720, "height": 1280, "link": "https://v/1-720"},
                     {"width": 1080, "height": 1920, "link": "https://v/1-1080"},
                     {"width": 2160, "height": 3840, "link": "https://v/1-4k"}]},
    {"id": 2, "duration": 8, "image": "https://img/2.jpg", "user": {"name": "Bo"},
     "video_files": [{"width": 1920, "height": 1080, "link": "https://v/2-land"}]},          # wrong way round
    {"id": 3, "duration": 9, "image": "https://img/3.jpg", "user": {"name": "Cy"},
     "video_files": [{"width": 540, "height": 960, "link": "https://v/3-small"}]},           # too small
]}
PIXABAY = {"hits": [{"id": 9, "duration": 15, "pageURL": "https://pixabay.com/v/9", "user": "Dee",
                     "videos": {"large": {"url": "https://p/9-l", "width": 1080, "height": 1920,
                                          "thumbnail": "https://p/9.jpg"},
                                "small": {"url": "https://p/9-s", "width": 360, "height": 640}}}]}


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "pk")
    monkeypatch.setenv("PIXABAY_API_KEY", "xk")


def test_search_takes_the_smallest_full_hd_rendition_and_caches(keys, monkeypatch):
    calls = []

    def get(url, headers=None, timeout=None):
        calls.append(url)
        return _R(PEXELS if "pexels" in url else PIXABAY)
    monkeypatch.setattr(sm.httpx, "get", get)
    got = sm.search("cricket stadium night")
    assert [(c["id"], c["url"]) for c in got] == [("pexels:v1", "https://v/1-1080"), ("pixabay:v9", "https://p/9-l")]
    assert got[0]["author"] == "Ann" and got[1]["thumb"] == "https://p/9.jpg"
    assert sm.search("Cricket  stadium night") == got and len(calls) == 2      # served from the cache
    assert "orientation=portrait" in calls[0] and "key=xk" in calls[1]


def test_openverse_needs_no_key_and_keeps_to_its_daily_cap(monkeypatch):
    monkeypatch.setenv("OPENVERSE", "1")
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    calls = []

    def get(url, headers=None, timeout=None):
        calls.append(url)
        return _R({"results": [{"id": "ab", "url": "https://live.staticflickr.com/x_b.jpg", "width": 2400,
                                "height": 1600, "thumbnail": "https://api.openverse.org/t", "creator": "Gary",
                                "foreign_landing_url": "https://flickr.com/x", "license": "cc0", "title": "Ruins"},
                               {"id": "cd", "url": "https://small", "width": 640, "height": 480}]})
    monkeypatch.setattr(sm.httpx, "get", get)
    assert sm.available()
    got = sm.search("roman ruins", portrait=False, kind="photo")
    assert [g["id"] for g in got] == ["openverse:ab"] and "license=cc0%2Cpdm" in calls[0]
    assert sm.search("roman ruins", portrait=False, kind="video") == []     # photos only
    monkeypatch.setattr(sm, "OPENVERSE_DAY_CAP", 1)
    assert sm.search("another", portrait=False, kind="photo") == [] and len(calls) == 1


def test_no_keys_means_no_footage_and_the_old_look(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    assert sm.for_scenes(None, "t", ["a", "b"], ["x", "y"]) == [None, None]
    monkeypatch.setenv("STOCK_FOOTAGE", "1")
    assert broll.background_for("t", [{"start": 0, "text": "a"}], 3.0, "unused") == (None, [])


def test_each_scene_gets_its_pick_and_used_clips_rest(keys, monkeypatch):
    pool = {"cricket": [{"id": "pexels:v1", "kind": "video", "thumb": "t1", "url": "u1", "provider": "Pexels"},
                        {"id": "pexels:v2", "kind": "video", "thumb": "t2", "url": "u2", "provider": "Pexels"}],
            "court": [{"id": "pixabay:v9", "kind": "video", "thumb": "t9", "url": "u9", "provider": "Pixabay"}]}
    monkeypatch.setattr(sm, "search", lambda term, portrait=True, kind="video": pool[term] if kind == "video" else [])
    sm.mark_used(["pexels:v1"])
    seen = {}

    def choose(client, topic, scenes, pools, model=None, rule=""):
        seen["pools"] = [[c["id"] for c in p] for p in pools]
        seen["rule"] = rule
        return [pools[0][0], None]
    monkeypatch.setattr(sm, "choose", choose)
    monkeypatch.setattr(sm, "download", lambda item: f"/cache/{item['id']}.mp4")
    got = sm.for_scenes(None, "topic", ["line one", "line two"], ["cricket", "court"], log=lambda *a: None,
                        rule="no handcuffs")
    assert seen["pools"] == [["pexels:v2"], ["pixabay:v9"]] and seen["rule"] == "no handcuffs"
    assert got[0]["path"] == "/cache/pexels:v2.mp4" and got[1] is None
    assert "pexels:v2" in sm.recently_used()
    assert sm.credit_line(got) == "Stock footage and photos (free licence): Pexels."


def test_the_picker_sees_each_clip_once_and_never_reuses_one(monkeypatch):
    a = {"id": "a", "kind": "video", "thumb": "ta"}
    b = {"id": "b", "kind": "photo", "thumb": "tb", "alt": "court"}
    monkeypatch.setattr(sm, "_thumb_part", lambda url: f"part:{url}")
    asked = {}

    def ask(client, schema, contents, model=None):
        asked["parts"] = contents[:-1]
        return sm.Choices(picks=[sm.Choice(scene=0, clip=0, fit=8), sm.Choice(scene=1, clip=0, fit=9),
                                 sm.Choice(scene=2, clip=1, fit=7), sm.Choice(scene=3, clip=1, fit=9)])
    import short_kit
    monkeypatch.setattr(short_kit, "ask_json", ask)
    got = sm.choose(None, "t", ["s0", "s1", "s2", "s3"], [[a, b], [a], [b], []])
    assert asked["parts"] == ["part:ta", "part:tb"]
    assert [g["id"] if g else None for g in got] == ["a", None, "b", None]

    def loose(client, schema, contents, model=None):
        return sm.Choices(picks=[sm.Choice(scene=0, clip=0, fit=4), sm.Choice(scene=1, clip=1, fit=6)])
    monkeypatch.setattr(short_kit, "ask_json", loose)
    got = sm.choose(None, "t", ["records", "stadium"], [[a], [b]])
    assert got[0] is None and got[1]["id"] == "b"      # a loose fit (an old book for "records") is dropped


def test_too_little_good_footage_keeps_the_shorts_own_look(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCK_FOOTAGE", "1")
    monkeypatch.setenv("PEXELS_API_KEY", "pk")
    monkeypatch.setattr(broll, "_find", lambda client, topic, lines, rule, log: [None, None, {"kind": "video"}])
    segs = [{"start": 0.0, "text": "a"}, {"start": 3.0, "text": "b"}, {"start": 6.0, "text": "c"}]
    assert broll.background_for("t", segs, 9.0, str(tmp_path), client=object(), log=lambda *a: None) == (None, [])


def test_shots_cut_to_the_voice_add_up_to_the_frame(monkeypatch):
    segs = [{"start": 0.5, "text": "one"}, {"start": 6.0, "text": "two"}, {"start": 9.0, "text": "three"}]
    windows = broll.windows_from(segs, 15.0)
    assert [(a, b) for a, b, _t in windows] == [(0.0, 6.0), (6.0, 9.0), (9.0, 15.0)]
    clip = {"kind": "video", "seconds": 20.0, "path": "c.mp4"}
    shots = broll.plan_shots(windows, [clip, None, clip])
    assert sum(f for f, *_ in shots) == round(15.0 * broll.FPS)
    assert all(f >= broll.MIN_SHOT * broll.FPS - 1 for f, *_ in shots)
    assert shots[0][3] is False and shots[1][3] is True          # every other shot is a closer crop
    assert broll.plan_shots(windows, [None, None, None]) == []


def test_a_real_background_is_built_from_a_clip_and_a_photo(tmp_path):
    clip, photo = tmp_path / "c.mp4", tmp_path / "p.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=360x640:d=4:r=30",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    from PIL import Image
    Image.new("RGB", (720, 1280), (120, 80, 40)).save(photo)
    shots = broll.plan_shots([(0.0, 3.0, "a"), (3.0, 5.0, "b")],
                             [{"kind": "video", "seconds": 4.0, "path": str(clip)},
                              {"kind": "photo", "seconds": 0.0, "path": str(photo)}])
    out = broll.build(str(tmp_path), shots, size=(360, 640))
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-count_frames", "-show_entries",
                            "stream=width,height,nb_read_frames", "-of", "csv=p=0", out],
                           capture_output=True, text=True).stdout.strip()
    assert probe == "360,640,150"


def test_the_owner_picks_voice_and_footage_for_every_generated_job(monkeypatch, tmp_path):
    import my_channels as mc
    assert mc.look() == {"voice": "edge", "footage": True}
    mc.update_look({"voice": "gemini", "footage": False, "other": 1})
    assert mc.look() == {"voice": "gemini", "footage": False}
    assert mc.look_env() == {"VOICE_ENGINE": "gemini", "STOCK_FOOTAGE": "0"}
    mc.update_look({"voice": "robot"})
    assert mc.look()["voice"] == "gemini"
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    r = TestClient(app_module.app).post("/api/process", json={
        "genre": "quiz", "quiz_format": "mcq", "acknowledged": True}, headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 200, r.text
    env = app_module.jobs[r.json()["job_id"]]["env"]
    assert env["VOICE_ENGINE"] == "gemini" and env["STOCK_FOOTAGE"] == "0"


def test_planners_hear_what_gets_views_this_week(monkeypatch, tmp_path):
    import channel_tools
    import trends
    monkeypatch.setenv("TRENDS", "1")
    monkeypatch.setattr(trends, "CACHE_FILE", str(tmp_path / "trends.json"))
    calls = []

    def search(q, cc=True, duration="any", date="any", sort="relevance", limit=20):
        calls.append((q, duration, date, sort))
        return [{"id": q, "title": f"Hot {q}", "views": 1000 + len(calls)},
                {"id": "dup", "title": "Same video", "views": 5}]
    monkeypatch.setattr(channel_tools, "search", search)
    h = trends.hint("cricket")
    assert "this week" in h and "Hot cricket facts shorts" in h and h.count("Same video") == 1
    assert calls[0][1:] == ("short", "week", "views")
    n = len(calls)
    assert trends.hint("cricket") == h and len(calls) == n          # cached
    assert trends.hint("music") == ""                              # no queries for that niche


def test_footage_credits_name_the_people_and_a_busy_library_rests(keys, monkeypatch):
    line = sm.credit_line([{"provider": "Pexels", "author": "Ann"}, {"provider": "Pexels", "author": "Bo"},
                           {"provider": "Pixabay", "author": ""}, None])
    assert line == "Stock footage and photos (free licence): Pexels (Ann, Bo); Pixabay."
    calls = []

    def get(url, headers=None, timeout=None):
        calls.append(url)
        return _R({}, 429) if "pexels" in url else _R(PIXABAY)
    monkeypatch.setattr(sm.httpx, "get", get)
    got = sm.search("rain at night")
    assert [g["provider"] for g in got] == ["Pixabay"]
    calls.clear()
    sm.search("another term")
    assert not any("pexels" in c for c in calls)        # Pexels rests for an hour


def test_a_library_that_does_not_answer_rests_after_two_timeouts(keys, monkeypatch):
    calls = []

    def get(url, headers=None, timeout=None):
        calls.append(url)
        if "pixabay" in url:
            raise sm.httpx.ReadTimeout("slow")
        return _R(PEXELS)
    monkeypatch.setattr(sm.httpx, "get", get)
    sm.search("one")
    sm.search("two")
    calls.clear()
    assert [g["provider"] for g in sm.search("three")] == ["Pexels"]
    assert not any("pixabay" in c for c in calls)


def test_the_free_voice_rests_after_microsoft_refuses(monkeypatch, tmp_path):
    import free_voice as fv

    async def refused(text, voice, rate, mp3):
        raise RuntimeError("WSServerHandshakeError: 403, message='Invalid response status'")
    monkeypatch.setattr(fv, "_say", refused)
    assert fv.speak("lafz", str(tmp_path / "a.wav"), "ur-PK-AsadNeural") is None
    assert fv.resting()
    called = []
    monkeypatch.setattr(fv, "_say", lambda *a: called.append(1))
    assert fv.speak("lafz", str(tmp_path / "b.wav"), "ur-PK-AsadNeural") is None and called == []


def test_a_short_over_footage_renders_through_with_a_card_a_bed_and_voices(tmp_path):
    """The mix that stalled for good (15-oct-2026): a photo card that ends early,
    a looped music bed and several voice lines over a footage background."""
    import math
    import struct
    import wave
    import cricket_shorts as cs
    import short_kit as kit
    from PIL import Image
    bg = tmp_path / "bg.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"testsrc2=s={kit.OUT_W}x{kit.OUT_H}:d=6:r=30", "-pix_fmt", "yuv420p",
                    "-video_track_timescale", "30000", str(bg)], check=True)
    card = tmp_path / "card.png"
    Image.new("RGBA", (400, 400), (200, 160, 40, 255)).save(card)
    voices = []
    for k in range(3):
        p = tmp_path / f"v{k}.wav"
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(i / 7))) for i in range(24000)))
        voices.append((str(p), 0.3 + k * 1.8))
    out = tmp_path / "short.mp4"
    kit.render(str(out), 6.0, ["#111111", "#222222"], [kit.dialogue(4, 0, 5, "CkText", "x")], cs.STYLES,
               voices=voices, sfx=[(kit.WHOOSH, 0.3, 1.0)], bed=(str(voices[0][0]), 5.5),
               images=[{"path": str(card), "t0": 0.2, "t1": 1.5, "zoom": 0.06}], bg_video=str(bg), fast=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration",
                            "-of", "compact", str(out)], capture_output=True, text=True).stdout
    assert "codec_type=video" in probe and "codec_type=audio" in probe
    assert abs(float(probe.split("duration=")[1].split()[0]) - 6.0) < 0.1
    assert not list(tmp_path.glob("gen_*"))            # its temporary files are gone
