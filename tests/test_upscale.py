"""Local Real-ESRGAN upscaling (22-oct-2026): off when the program is missing, and a video keeps its
frame count, frame rate and sound through the PNG round trip."""
import glob
import os
import shutil
import subprocess

import upscale


def test_off_without_the_program(monkeypatch, tmp_path):
    monkeypatch.setattr(upscale, "EXE", str(tmp_path / "missing.exe"))
    assert not upscale.available()


def test_jobs_cover_every_gpu(monkeypatch):
    monkeypatch.setattr(upscale, "GPUS", "0,1")
    assert upscale._jobs() == "2:2,2:2"
    monkeypatch.setattr(upscale, "GPUS", "1")
    assert upscale._jobs() == "2:2:2"


def test_a_video_keeps_its_frames_rate_and_sound(monkeypatch, tmp_path):
    src = str(tmp_path / "src.mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=90x160:rate=24:duration=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", src], check=True, capture_output=True)

    def fake_run(src_dir, dst_dir, model, scale):      # what the real program does: same names, bigger frames
        for f in glob.glob(os.path.join(src_dir, "*.png")):
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", f, "-vf", f"scale=iw*{scale}:ih*{scale}",
                            os.path.join(dst_dir, os.path.basename(f))], check=True, capture_output=True)
    monkeypatch.setattr(upscale, "_run", fake_run)
    out = upscale.video(src, str(tmp_path / "out.mp4"))
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                            "stream=codec_type,width,height,r_frame_rate,nb_read_frames", "-of", "csv=p=0", out],
                           capture_output=True, text=True).stdout
    assert "video,180,320,24/1,24" in probe.replace("\r", "") and "audio" in probe


def test_frames_left_out_fail_the_video(monkeypatch, tmp_path):
    src = str(tmp_path / "src.mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=90x160:rate=24:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", src], check=True, capture_output=True)
    monkeypatch.setattr(upscale, "_run", lambda src_dir, dst_dir, model, scale: shutil.copy(
        sorted(glob.glob(os.path.join(src_dir, "*.png")))[0], dst_dir))
    try:
        upscale.video(src, str(tmp_path / "out.mp4"))
        raise AssertionError("should have failed")
    except RuntimeError as e:
        assert "left frames out" in str(e)
