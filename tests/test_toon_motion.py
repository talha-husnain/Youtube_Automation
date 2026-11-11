"""Animated cartoon episodes (owner, 9-nov-2026: real cartoons with lip-sync and a proper story). The video model is
a fake that returns small real mp4 files, so joining, resizing and the budget run for real; nothing is uploaded."""
import base64
import json
import os
import subprocess

import pytest

import ai_fallback
import toon_motion as tm
import toon_shorts as ts


def _ep(**kw):
    def L(sp, text, how="annoyed"):
        return tm.SceneLine(speaker=sp, text=text, delivery=how)
    scenes = [
        tm.Scene(place="lounge", who=["guddu", "billo"], action="Guddu sits on the sofa holding the TV remote like "
                 "a judge's gavel while Billo paces in front of him.",
                 lines=[L("guddu", "Is ghar mein remote ka faisla main karunga!"), L("billo", "Tum abhi chal bhi nahi sakte.")]),
        tm.Scene(place="lounge", who=["billo", "sheru"], action="Billo whispers a plan to Sheru, who nods slowly and "
                 "walks off towards the kitchen.", lines=[L("billo", "Sheru, samosa le aao, remote hamara.", "sly")]),
        tm.Scene(place="kitchen", who=["sheru"], action="Sheru stands at the counter and eats the whole plate of "
                 "samosas himself, very happy, crumbs everywhere.", lines=[L("ammi", "Samosay kis ne khaye?!", "shouting")],
                 sound="a plate clattering"),
        tm.Scene(place="lounge", who=["guddu", "sheru"], action="Sheru comes back with crumbs on his face; Guddu "
                 "slowly raises the remote and switches the TV off.", lines=[L("guddu", "Faisla ho gaya. Sab so jao.", "deadpan")]),
    ]
    data = dict(title="Remote ka faisla Guddu karega", hook_caption="REMOTE KI JUNG", premise="Guddu claims the remote.",
                point="In every home the smallest one rules the TV.", shape="contest", scenes=scenes,
                twist="Guddu wins by switching it off.", question="Remote kis ke paas? Ammi ya Abbu?")
    data.update(kw)
    return tm.MotionEpisode(**data)


def test_a_good_story_passes_and_broken_ones_are_named():
    ep = _ep()
    assert tm.problems(ep) == []
    assert 24 <= sum(tm.seconds_of(s) for s in ep.scenes) <= 44
    bad = _ep()
    bad.scenes[0].who = ["guddu", "billo", "sheru"]
    bad.scenes[1].lines[0].speaker = "mithu"
    bad.scenes[3].lines[0].text = "Faisla " * 13
    bad.title = "ریموٹ"
    found = " | ".join(tm.problems(bad))
    for part in ("scene 1 has 3 characters", "mithu speaks but is not in the scene", "12 or fewer", "Latin letters"):
        assert part in found


def test_the_scene_prompt_carries_references_voices_and_no_music():
    ep = _ep()
    p = tm.clip_prompt(ep, 0)
    assert p.index("picture 1 is Guddu") < p.index("picture 2 is Billo")
    assert '"Is ghar mein remote ka faisla main karunga!"' in p and "toddler" in p and "first second" in p
    assert "no background music" in p and "Hindi-Urdu" in p
    off = tm.clip_prompt(ep, 2)
    assert "Ammi from off screen" in off and "a plate clattering" in off


def _mp4(path, secs=2, audio=True):
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=360x640:rate=24:d={secs}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", path]
    subprocess.run(cmd, check=True, capture_output=True)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


class FakeOmni:
    def __init__(self, tmp, error=None, silent_scene=None):
        self.calls, self.error, self.tmp, self.silent = [], error, tmp, silent_scene
        self.interactions = self

    def create(self, model=None, input=None, response_format=None):
        self.calls.append((model, input, response_format))
        if self.error:
            raise self.error
        k = len(self.calls)
        data = _mp4(str(self.tmp / f"src{k}.mp4"), 2, audio=k != self.silent)
        return type("I", (), {"output_video": type("V", (), {"data": data})()})()


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("TOON_UPSCALE", "0")
    monkeypatch.delenv("TOON_VIDEO_SECONDS_PER_DAY", raising=False)
    from PIL import Image
    ref = tmp_path / "ref.png"
    Image.new("RGB", (64, 64), (240, 140, 40)).save(ref)
    monkeypatch.setattr(ts, "cast_ref", lambda client, key: str(ref))
    monkeypatch.setattr(tm.time, "sleep", lambda s: None)
    work = tmp_path / "work"
    work.mkdir()
    return tmp_path, work


def test_scenes_are_animated_joined_and_made_1080x1920_within_the_budget(studio):
    tmp, work = studio
    client = FakeOmni(tmp, silent_scene=3)
    canvas, sound, times, wavs = tm.make_video(client, _ep(), str(work), log=lambda s: None)
    assert len(client.calls) == 4 and len(times) == 4 and len(wavs) == 4
    model, parts, fmt = client.calls[0]
    assert model == tm.MODEL and fmt["resolution"] == "360p" and fmt["aspect_ratio"] == "9:16"
    assert fmt["duration"] == f"{tm.seconds_of(_ep().scenes[0])}s"
    assert [p["type"] for p in parts] == ["image", "image", "text"]
    size = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", canvas], capture_output=True, text=True).stdout.strip()
    assert size == "1080,1920" and abs(times[-1][1] - 8.0) < 0.3 and os.path.isfile(sound)
    spent = json.load(open(tm._spend_file()))
    day = next(iter(spent.values()))
    assert day["clips"] == 4 and day["seconds"] == sum(tm.seconds_of(s) for s in _ep().scenes)
    assert abs(day["usd"] - day["seconds"] * tm.PRICE["360p"]) < 0.001


def test_the_daily_cap_stops_before_any_video_is_made(studio, monkeypatch):
    tmp, work = studio
    monkeypatch.setenv("TOON_VIDEO_SECONDS_PER_DAY", "20")
    client = FakeOmni(tmp)
    with pytest.raises(RuntimeError, match="budget"):
        tm.make_video(client, _ep(), str(work), log=lambda s: None)
    assert client.calls == []


def test_no_gemini_credit_says_so_and_does_not_retry(studio):
    tmp, work = studio
    client = FakeOmni(tmp, error=RuntimeError("402 RESOURCE_EXHAUSTED Your prepayment credits are depleted"))
    with pytest.raises(RuntimeError, match="no credit"):
        tm.make_video(client, _ep(), str(work), log=lambda s: None)
    assert len(client.calls) == 1


def test_the_story_is_written_by_the_full_model_on_the_backup(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_WRITER_MODEL", raising=False)
    assert ai_fallback.openai_model() == "gpt-5-mini"
    with ai_fallback.best_writer():
        assert ai_fallback.openai_model() == "gpt-5"
    assert ai_fallback.openai_model() == "gpt-5-mini"


def test_name_tags_and_captions_follow_the_scenes(studio):
    ep = _ep()
    times = [(0.0, 8.0), (8.0, 13.0), (13.0, 18.0), (18.0, 25.0)]
    ev = "\n".join(tm.text_events(ep, times, 7, 25.0))
    assert "REMOTE KI JUNG" in ev and "EP 7" in ev and "GUDDU" in ev and "AMMI (AWAAZ)" in ev
    cap = tm.captions(ep, times, [None] * 4)
    assert len(cap["segments"]) == 4 and cap["segments"][2]["text"] == "Samosay kis ne khaye?!"
