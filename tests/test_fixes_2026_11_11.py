"""Fixes of 11-nov-2026: why the channels' videos failed and looked cheap while Gemini had no credit."""
import json
import os
import types as pytypes

import pytest

import ai_fallback as af

BROKE = RuntimeError("402 RESOURCE_EXHAUSTED. {'error': {'code': 402, 'message': 'Your prepayment credits are "
                     "depleted. Please go to AI Studio.'}}")


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(af, "STATE_FILE", str(tmp_path / "ai_fallback.json"))
    monkeypatch.setattr(af, "_said", set())
    monkeypatch.setenv("AI_FALLBACK_TEST", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    return tmp_path


class _R:
    def __init__(self, data, code=200):
        self.status_code, self._d, self.text = code, data, json.dumps(data)

    def json(self):
        return self._d


class FakeGemini:
    def __init__(self):
        self.models = self

    def generate_content(self, model=None, contents=None, config=None):
        raise BROKE


SEARCHED = {"status": "completed", "output": [
    {"type": "web_search_call", "status": "completed"},
    {"type": "message", "content": [{"type": "output_text", "text": "REPORTED: he stepped down. ([dawn.com](x))",
                                     "annotations": [
                                         {"type": "url_citation", "url": "https://www.dawn.com/news/1?utm_source=openai",
                                          "title": "Babar resigns - DAWN"},
                                         {"type": "url_citation", "url": "https://www.icc-cricket.com/news/a",
                                          "title": "ICC"},
                                         {"type": "url_citation", "url": "https://www.dawn.com/news/1",
                                          "title": "again"}]}]}]}


# ------------------------------------------------------------------ search sources through the backup

def test_a_searched_backup_answer_carries_its_sources_like_gemini_grounding(monkeypatch):
    posts = []
    monkeypatch.setattr(af, "httpx", pytypes.SimpleNamespace(
        post=lambda url, **kw: posts.append(kw.get("json")) or _R(SEARCHED), get=lambda *a, **k: _R({}, 500)))
    from google.genai import types
    c = af.wrap(FakeGemini())
    r = c.models.generate_content(model="m", contents="facts please",
                                  config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
    assert posts[0]["tools"] == [{"type": "web_search"}]
    chunks = r.candidates[0].grounding_metadata.grounding_chunks
    assert [(ch.web.title, ch.web.uri) for ch in chunks] == [("Babar resigns - DAWN", "https://www.dawn.com/news/1"),
                                                           ("ICC", "https://www.icc-cricket.com/news/a")]
    assert r.text.startswith("REPORTED")


def test_controversy_research_counts_the_backups_sources(monkeypatch):
    monkeypatch.setattr(af, "httpx", pytypes.SimpleNamespace(post=lambda url, **kw: _R(SEARCHED),
                                                             get=lambda *a, **k: _R({}, 500)))
    import controversy_shorts as cs
    facts, sources = cs.research(af.wrap(FakeGemini()), "Babar Azam captaincy")
    assert len(sources) == 2 and sources[0][1] == "https://www.dawn.com/news/1"


def test_an_answer_without_search_has_no_candidates(monkeypatch):
    plain = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "hi"}]}]}
    monkeypatch.setattr(af, "httpx", pytypes.SimpleNamespace(post=lambda url, **kw: _R(plain),
                                                             get=lambda *a, **k: _R({}, 500)))
    r = af.wrap(FakeGemini()).models.generate_content(model="m", contents="x")
    assert r.candidates == [] and r.text == "hi"


# ------------------------------------------------------------------ pictures through fal

def test_new_pictures_go_to_fal_with_the_asked_shape_and_a_daily_cap(monkeypatch, tmp_path):
    import ai_influencer
    import talkies
    from google.genai import types
    from PIL import Image
    monkeypatch.setenv("FAL_IMAGES", "1")
    monkeypatch.setenv("FAL_IMAGES_PER_DAY", "1")
    monkeypatch.setattr(ai_influencer, "key", lambda: "fal-test")
    asked = []

    def job(endpoint, payload, sleep=None):
        asked.append((endpoint, payload))
        return {"images": [{"url": "https://fal/pic.png"}]}

    def download(url, out):
        Image.new("RGB", (8, 8)).save(out, "PNG")
        return out
    monkeypatch.setattr(talkies, "fal_job", job)
    monkeypatch.setattr(talkies, "_download", download)
    monkeypatch.setattr(af, "httpx", pytypes.SimpleNamespace(post=lambda *a, **k: _R({}, 500), get=lambda *a, **k: _R({}, 500)))
    cfg = types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"],
                                      image_config=types.ImageConfig(aspect_ratio="16:9", image_size="2K"))
    c = af.wrap(FakeGemini())
    r = c.models.generate_content(model="img", contents=["a moonlit watermill"], config=cfg)
    assert r.parts[0].inline_data.data and asked[0][0] == af.FAL_IMAGE_MODEL
    assert asked[0][1]["image_size"] == {"width": 1920, "height": 1072} and "watermill" in asked[0][1]["prompt"]
    with pytest.raises(Exception):                         # the day's cap: no more fal, and not the cartoon channel
        c.models.generate_content(model="img", contents=["again"], config=cfg)
    assert len(asked) == 1


def test_a_picture_edit_never_goes_to_fal():
    assert not af.fal_images_ok([("text", "close the mouth"), ("image", b"..", "image/png")])


# ------------------------------------------------------------------ voices while Gemini has no credit

def test_the_gemini_voice_gives_up_at_the_first_no_credit(monkeypatch, tmp_path):
    import ai_take
    calls = []

    class C:
        class models:
            @staticmethod
            def generate_content(**kw):
                calls.append(kw["model"])
                raise BROKE

        class interactions:
            @staticmethod
            def create(**kw):
                calls.append(kw["model"])
                raise BROKE
    monkeypatch.setattr(ai_take.time, "sleep", lambda s: pytest.fail("no waiting on a no-credit answer"))
    assert ai_take.speak(C, "Ek line", str(tmp_path / "t.wav")) is None and len(calls) == 1


def test_a_long_paragraph_timing_out_does_not_rest_the_free_voice(monkeypatch, tmp_path):
    import asyncio
    import free_voice
    rested = []
    monkeypatch.setattr(free_voice, "_rest", lambda reason, seconds=0: rested.append(reason))
    monkeypatch.setattr(free_voice.time if hasattr(free_voice, "time") else __import__("time"), "sleep", lambda s: None)
    monkeypatch.setattr(free_voice, "resting", lambda: False)

    async def slow(*a, **k):
        raise asyncio.TimeoutError()
    monkeypatch.setattr(free_voice, "_say", slow)
    assert free_voice.speak("lafz " * 200, str(tmp_path / "a.wav"), "ur-PK-AsadNeural") is None
    assert not rested                                       # retried, never "the service is down"
    assert free_voice.speak("chhoti line", str(tmp_path / "b.wav"), "ur-PK-AsadNeural") is None
    assert rested                                           # a short line timing out is the network
    assert free_voice.timeout_for("x" * 2000) == 250 and free_voice.timeout_for("x") == free_voice.TIMEOUT


def test_lines_wait_for_the_free_voice_only_while_gemini_has_no_credit(monkeypatch):
    import time as _t
    import free_voice
    import short_kit
    slept = []
    monkeypatch.setattr(short_kit.time, "sleep", slept.append)
    monkeypatch.setattr(free_voice, "rest_info", lambda: {"until": _t.time() + 300, "reason": "TimeoutError"})
    monkeypatch.setattr(af, "status", lambda: {"gemini_down": False})
    assert short_kit.wait_for_free_voice() == 0 and not slept
    monkeypatch.setattr(af, "status", lambda: {"gemini_down": True})
    assert 290 < short_kit.wait_for_free_voice() <= 302 and slept
    monkeypatch.setattr(free_voice, "rest_info", lambda: None)
    assert short_kit.wait_for_free_voice() == 0


def test_the_local_voice_is_off_unless_asked(monkeypatch):
    import local_voice
    monkeypatch.delenv("LOCAL_VOICE", raising=False)
    monkeypatch.setenv("OMNIVOICE_PYTHON", __file__)
    assert not local_voice.available()                      # CC-BY-NC model: never on by default
    monkeypatch.setenv("LOCAL_VOICE", "1")
    assert local_voice.available()


# ------------------------------------------------------------------ jobs and the laptop's sleep

def test_a_jobs_age_leaves_out_the_laptops_sleep(monkeypatch):
    import my_channels as mc
    monkeypatch.setattr(mc, "_naps", [])
    monkeypatch.setattr(mc, "_tick_at", None)
    t0 = 1_000_000.0
    mc.note_tick(t0)
    mc.note_tick(t0 + 60)
    mc.note_tick(t0 + 60 + 8 * 3600)                        # asleep 04:55 -> 12:45
    mc.note_tick(t0 + 120 + 8 * 3600)
    assert mc.awake_since(t0 + 30, t0 + 120 + 8 * 3600) == pytest.approx(90)
    assert mc.awake_since(t0 + 8 * 3600 + 100, t0 + 120 + 8 * 3600) == pytest.approx(20)  # started after the nap


# ------------------------------------------------------------------ the mix and motion

def test_the_mix_moves_to_fal_on_the_first_no_credit(monkeypatch, tmp_path):
    import mood_mix
    import music_shorts as ms
    made = []
    monkeypatch.setattr(mood_mix, "_fal_route", lambda: False)
    monkeypatch.setattr(ms, "fal_enabled", lambda: True)
    monkeypatch.setattr(mood_mix.kit, "ask_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))

    def track(client, prompt, out, fal):
        if not fal:
            raise BROKE
        made.append(out)
        open(out, "wb").close()
    monkeypatch.setattr(mood_mix, "_lyria_track", track)
    monkeypatch.setattr(ms, "media_seconds", lambda p: 150.0)
    tracks = mood_mix.make_tracks(None, {"name": "Study", "sound": ["piano"]}, 5, 1.0, str(tmp_path), log=lambda t: None)
    assert len(tracks) >= 2 and made[0].endswith(".mix_t01.mp3")


def test_motion_is_off_without_a_key_and_counts_its_clips(monkeypatch, tmp_path):
    import ai_influencer
    import motion
    import talkies
    monkeypatch.setattr(motion, "STATE_FILE", str(tmp_path / "motion.json"))
    monkeypatch.setenv("MOTION", "1")
    monkeypatch.setattr(ai_influencer, "key", lambda: "")
    assert motion.animate("p.jpg", "x", str(tmp_path / "m.mp4")) is None
    monkeypatch.setattr(ai_influencer, "key", lambda: "fal-test")
    monkeypatch.setenv("MOTION_PER_DAY", "1")
    monkeypatch.setattr(talkies, "fal_upload", lambda p: "https://fal/up.png")
    sent = []
    monkeypatch.setattr(talkies, "fal_job", lambda ep, payload, sleep=None: sent.append(payload) or
                        {"video": {"url": "https://fal/v.mp4"}})
    import subprocess

    def fake_download(url, out):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=16:d=3", "-pix_fmt",
                        "yuv420p", out], check=True)
        return out
    monkeypatch.setattr(talkies, "_download", fake_download)
    out = motion.animate("p.jpg", "a misty mill", str(tmp_path / "m.mp4"), log=lambda t: None)
    assert out and sent[0]["image_url"] == "https://fal/up.png" and "misty mill" in sent[0]["prompt"]
    import music_shorts
    assert music_shorts.media_seconds(out) == pytest.approx(6.0, abs=0.3)   # forward then back
    assert motion.made_today() == 1 and motion.room_today() == 0
    assert motion.animate("p.jpg", "again", str(tmp_path / "m2.mp4")) is None   # the day's cap
