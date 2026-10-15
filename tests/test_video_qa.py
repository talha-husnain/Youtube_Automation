"""The last look before an unattended upload (video_qa.py)."""

import subprocess

import pytest

import my_channels as mc
import video_qa as qa


def _make(path, seconds=12, size="360x640", audio="sine=frequency=300", video="testsrc2"):
    src = f"{video}{':' if '=' in video else '='}size={size}:rate=30:duration={seconds}"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"{audio}:duration={seconds}"]
    subprocess.run(cmd + ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-shortest", str(path)],
                   check=True)
    return str(path)


def test_a_good_short_passes(tmp_path):
    assert qa.check(_make(tmp_path / "ok.mp4")) == []


def test_silent_black_frozen_and_wrong_shape_are_named(tmp_path):
    silent = _make(tmp_path / "s.mp4", audio="anullsrc=r=44100:cl=mono")
    assert any("silent" in p for p in qa.check(silent))
    black = _make(tmp_path / "b.mp4", video="color=c=black")
    assert any("black" in p for p in qa.check(black))
    frozen = _make(tmp_path / "f.mp4", seconds=20, video="color=c=blue")
    assert any("freezes" in p for p in qa.check(frozen))
    wide = _make(tmp_path / "w.mp4", size="640x360")
    assert any("not vertical" in p for p in qa.check(wide))
    assert qa.check(wide, long=True) == ["it is only 12 s long"]
    assert qa.check(str(tmp_path / "missing.mp4")) == ["the file cannot be read"]


def test_a_failed_check_keeps_the_short_off_youtube(monkeypatch):
    import youtube_account
    monkeypatch.setenv("VIDEO_QA", "1")
    ch = mc.add("quiz")
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "q1", "status": "done", "format": "mcq", "at": 1}]))
    monkeypatch.setattr(youtube_account, "status", lambda: {"connected": True})
    monkeypatch.setattr(youtube_account, "upload", lambda *a, **k: pytest.fail("a broken Short went up"))
    monkeypatch.setattr(qa, "check", lambda path, long=False: ["it is silent (mean volume -91.0 dB)"])
    clip = {"index": 0, "path": "p.mp4", "title": "T", "description": "D", "tags": []}
    got = mc.upload_waiting(mc.get(ch["id"]), lambda job: ("completed", [clip]), log=lambda *a: None)
    job = mc.get(ch["id"])["jobs"][0]
    assert got["done"] == 0 and job["status"] == "failed" and job["error"].startswith("quality check: it is silent")
