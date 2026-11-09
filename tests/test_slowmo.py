"""RIFE slow motion for short stock clips (22-oct-2026): only a 1.15-4x stretch, exactly
round(need * fps) frames asked of RIFE, off with SLOWMO=0 or without the program, and any failure
returns None (broll then loops the clip as before). The real program never runs here."""
import os
import subprocess

import pytest

import slowmo


@pytest.fixture
def exe(monkeypatch, tmp_path):
    path = tmp_path / "rife" / "rife-ncnn-vulkan.exe"
    path.parent.mkdir()
    path.write_bytes(b"")
    monkeypatch.setattr(slowmo, "EXE", str(path))
    monkeypatch.delenv("SLOWMO", raising=False)
    return path


class FakeRun:
    """Does what the three real commands do to the disk: frames out of ffmpeg, RIFE's numbered
    frames, then the encoded file."""

    def __init__(self, src_frames=60, rife_frames=None, fail_on=None):
        self.calls, self.src_frames, self.rife_frames, self.fail_on = [], src_frames, rife_frames, fail_on

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if self.fail_on and self.fail_on in os.path.basename(cmd[0]):
            raise subprocess.CalledProcessError(1, cmd, stderr=b"vkCreateInstance failed")
        if cmd[0] == slowmo.EXE:
            folder = cmd[cmd.index("-o") + 1]
            n = self.rife_frames if self.rife_frames is not None else int(cmd[cmd.index("-n") + 1])
            for i in range(1, n + 1):
                open(os.path.join(folder, f"{i:08d}.png"), "wb").close()
        elif cmd[-1].endswith("f%06d.png"):
            for i in range(1, self.src_frames + 1):
                open(cmd[-1] % i, "wb").close()
        else:
            with open(cmd[-1], "wb") as f:
                f.write(b"mp4")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    def rife(self):
        return next(c for c in self.calls if c[0] == slowmo.EXE)


@pytest.mark.parametrize("have,need", [(2, 2.2), (2, 2.29), (2, 8.2), (1, 10), (2, 2)])
def test_outside_the_ratio_limits_nothing_runs(exe, tmp_path, have, need):
    run = FakeRun()
    assert slowmo.stretch("a.mp4", 0, have, need, str(tmp_path / "o.mp4"), run=run) is None
    assert run.calls == []


@pytest.mark.parametrize("have,need", [(2, 2.3), (2, 4), (2, 8)])
def test_inside_the_limits_it_stretches(exe, tmp_path, have, need):
    run = FakeRun()
    out = str(tmp_path / "o.mp4")
    assert slowmo.stretch("a.mp4", 1.5, have, need, out, run=run) == out
    assert len(run.calls) == 3


@pytest.mark.parametrize("need,fps,frames", [(4, 30, 120), (3.3, 30, 99), (2.5, 24, 60), (3.71, 30, 111)])
def test_rife_is_asked_for_exactly_the_frames_the_shot_needs(exe, tmp_path, need, fps, frames):
    run = FakeRun()
    slowmo.stretch("a.mp4", 0, 2, need, str(tmp_path / "o.mp4"), fps=fps, run=run)
    cmd = run.rife()
    assert cmd[cmd.index("-n") + 1] == str(frames)
    assert cmd[cmd.index("-m") + 1].endswith(slowmo.MODEL)
    enc = run.calls[-1]
    assert enc[enc.index("-framerate") + 1] == str(fps) and enc[enc.index("-frames:v") + 1] == str(frames)
    assert enc[enc.index("-start_number") + 1] == "1" and "-an" in enc


def test_only_the_usable_segment_is_read_and_scaled_down(exe, tmp_path):
    run = FakeRun()
    slowmo.stretch("a.mp4", 3.25, 1.8, 4, str(tmp_path / "o.mp4"), run=run)
    ext = run.calls[0]
    assert ext[ext.index("-ss") + 1] == "3.250" and ext[ext.index("-t") + 1] == "1.800"
    assert "min(iw,1280)" in ext[ext.index("-vf") + 1] and "min(ih,1280)" in ext[ext.index("-vf") + 1]
    run = FakeRun()
    slowmo.stretch("a.mp4", 0, 2, 4, str(tmp_path / "o.mp4"), size=(720, 1280), run=run)
    assert "min(iw,720)" in run.calls[0][run.calls[0].index("-vf") + 1]


def test_off_by_env_or_without_the_program(exe, monkeypatch, tmp_path):
    assert slowmo.available()
    monkeypatch.setenv("SLOWMO", "0")
    assert not slowmo.available()
    run = FakeRun()
    assert slowmo.stretch("a.mp4", 0, 2, 4, str(tmp_path / "o.mp4"), run=run) is None and run.calls == []
    monkeypatch.delenv("SLOWMO")
    monkeypatch.setattr(slowmo, "EXE", str(tmp_path / "missing.exe"))
    assert not slowmo.available()


def test_a_failed_rife_returns_none_and_cleans_up(exe, monkeypatch, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(slowmo.tempfile, "mkdtemp", lambda prefix="": str(work / "w"))
    out = tmp_path / "o.mp4"
    assert slowmo.stretch("a.mp4", 0, 2, 4, str(out), run=FakeRun(fail_on="rife")) is None
    assert not (work / "w").exists() and not out.exists()


@pytest.mark.parametrize("run", [FakeRun(rife_frames=119), FakeRun(src_frames=1), FakeRun(fail_on="ffmpeg")])
def test_any_other_failure_returns_none(exe, tmp_path, run):
    out = tmp_path / "o.mp4"
    assert slowmo.stretch("a.mp4", 0, 2, 4, str(out), run=run) is None
    assert not out.exists()


@pytest.mark.parametrize("have,need", [(0, 4), (-1, 2), (None, 4), ("x", 4)])
def test_bad_numbers_never_raise(exe, tmp_path, have, need):
    assert slowmo.stretch("a.mp4", 0, have, need, str(tmp_path / "o.mp4"), run=FakeRun()) is None


def test_jobs_cover_every_gpu(monkeypatch):
    monkeypatch.setattr(slowmo, "GPUS", "0,1")
    assert slowmo._jobs() == "1:2,2:2"
    monkeypatch.setattr(slowmo, "GPUS", "0")
    assert slowmo._jobs() == "1:2:2"
