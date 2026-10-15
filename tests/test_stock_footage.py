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
    assert sm.credit_line(got) == "Stock footage and photos: Pexels (free licence)."


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
