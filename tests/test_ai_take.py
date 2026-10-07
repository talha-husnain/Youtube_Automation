"""ai_take.py + the take segment in framed_layout: timeline, 3-minute guard,
job-file round trip and a real ffmpeg render with a voice."""
import json
import os
import shutil
import subprocess
import wave

import pytest

import ai_take
import framed_layout


def test_take_events_light_words_in_time_with_the_voice():
    take = {"text": "Sach bataun yeh har ghar ki kahani hai", "seconds": 4.0, "voice_seconds": 3.05}
    ev = framed_layout.take_events(10.0, take)
    assert len(ev) == 3 and all("0:00:10.00" in e for e in ev)
    text = ev[2]
    ks = [int(k) for k in __import__("re").findall(r"\\kf(\d+)", text)]
    assert len(ks) == 8 and abs(sum(ks) - 305) <= 8      # spread over the voice
    assert "\\k35}" in text                               # waits for the pop-in


def test_end_card_moves_after_the_take(tmp_path):
    p = str(tmp_path / "o.ass")
    geo = framed_layout.geometry(1920, 1080)
    take = {"text": "Aap ka kya khayal hai?", "seconds": 5.0, "voice_seconds": 4.05}
    framed_layout.overlay_ass(p, geo, "#2B0F3D", 20.0, title="T", handle="@x", outro=True,
                              outro_seconds=3.0, take=take)
    s = open(p, encoding="utf-8").read()
    assert "Style: TakeText" in s and "HAMARA TAKE" in s
    follow = [l for l in s.splitlines() if l.endswith("FOLLOW")][0]
    assert follow.split(",")[1] == "0:00:25.00"


def test_no_take_leaves_the_overlay_unchanged(tmp_path):
    geo = framed_layout.geometry(1920, 1080)
    a, b = str(tmp_path / "a.ass"), str(tmp_path / "b.ass")
    framed_layout.overlay_ass(a, geo, "#2B0F3D", 20.0, title="T", handle="@x", outro=True)
    framed_layout.overlay_ass(b, geo, "#2B0F3D", 20.0, title="T", handle="@x", outro=True, take=None)
    assert open(a, encoding="utf-8").read() == open(b, encoding="utf-8").read()
    assert "Take" not in open(a, encoding="utf-8").read()


def test_take_round_trips_through_the_job_file(tmp_path):
    d = str(tmp_path)
    (tmp_path / "v_clip_1.take.wav").write_bytes(b"x")
    framed_layout.write_job(d, {"bg": "#000000"}, 10, {"v_clip_1.mp4": "t"},
                            {"v_clip_1.mp4": {"text": "Kya baat hai", "audio": "v_clip_1.take.wav",
                                              "voice_seconds": 2.0}})
    job = framed_layout.load_job(d)
    take, voice = framed_layout._take_for(d, job, "trim_123_v_clip_1.mp4")  # editor re-render
    assert take["seconds"] == 2.95 and voice.endswith("v_clip_1.take.wav")
    os.remove(voice)
    take, voice = framed_layout._take_for(d, job, "v_clip_1.mp4")
    assert voice is None and take["seconds"] == framed_layout.TEXT_ONLY_SECONDS
    assert framed_layout._take_for(d, job, "other.mp4") == (None, None)
    framed_layout.write_job(d, {"bg": "#000000"}, 10, {})
    assert "takes" not in framed_layout.load_job(d)


def test_long_clip_gets_no_take_and_short_one_does(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("AI_TAKE", "1")
    monkeypatch.setattr(ai_take, "write_takes", lambda *a, **k: {0: "Ek", 1: "Do"})

    def fake_speak(client, text, path, voice):
        open(path, "wb").close()
        return 4.0
    monkeypatch.setattr(ai_take, "speak", fake_speak)
    monkeypatch.setattr("google.genai.Client", lambda **k: None)
    clips = [{"start": 0, "end": 60}, {"start": 0, "end": 172}]
    takes = ai_take.apply(clips, {"segments": []}, str(tmp_path), ["a.mp4", "b.mp4"], outro_seconds=3.0)
    assert list(takes) == ["a.mp4"] and takes["a.mp4"]["audio"] == "a.take.wav"
    assert clips[0]["ai_take"] == "Ek" and "ai_take" not in clips[1]


def test_off_switch(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_TAKE", "0")
    assert ai_take.apply([{"start": 0, "end": 10}], {}, str(tmp_path), ["a.mp4"]) == {}


def test_seo_copy_is_roman_even_when_subtitles_are_not(monkeypatch):
    import seo_copy
    seen = {}

    def fake_ask(client, model, items, handle, source, style, latin, extra=""):
        seen["style"], seen["latin"] = style, latin
        return {}
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("CAPTION_SCRIPT", "original")
    monkeypatch.delenv("SEO_SCRIPT", raising=False)
    monkeypatch.setattr(seo_copy, "_ask", fake_ask)
    monkeypatch.setattr("google.genai.Client", lambda **k: None)
    seo_copy.apply([{"start": 0, "end": 5}], {"segments": []})
    assert seen["latin"] and seen["style"] == seo_copy.LANGUAGE_STYLE["roman"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_real_render_with_a_voiced_take(tmp_path, monkeypatch):
    for k in ("FRAME_OUTRO", "FRAME_OUTRO_SECONDS", "FRAME_TITLE", "FRAME_HANDLE"):
        monkeypatch.delenv(k, raising=False)
    src = str(tmp_path / "temp_v_clip_1.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=4",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-shortest",
                    "-c:v", "libx264", "-c:a", "aac", src], check=True)
    voice = str(tmp_path / "v_clip_1.take.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=2",
                    "-ar", "24000", "-ac", "1", voice], check=True)
    with wave.open(voice) as w:
        vs = w.getnframes() / w.getframerate()
    framed_layout.write_job(str(tmp_path), {"bg": "#2B0F3D", "handle": "@x"}, 10, {"v_clip_1.mp4": "Title"},
                            {"v_clip_1.mp4": {"text": "Yeh to kamaal ho gaya, aap ka kya khayal hai?",
                                              "audio": "v_clip_1.take.wav", "voice_seconds": vs}})
    out = str(tmp_path / "v_clip_1.mp4")
    framed_layout.render(src, out, title="Title")
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", out]).decode())
    assert abs(dur - (4 + vs + framed_layout.TAKE_LEAD + framed_layout.TAKE_TAIL + 3)) < 0.25
    # The voice is in the mix: loud where the take speaks (4.35 s - 6.35 s).
    vol = subprocess.run(["ffmpeg", "-v", "info", "-ss", "4.6", "-t", "1.2", "-i", out, "-af", "volumedetect",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    assert float(vol.split("mean_volume:")[1].split("dB")[0]) > -40
