"""Local AI upscaling with Real-ESRGAN (ncnn-vulkan build, BSD-3, xinntao/Real-ESRGAN v0.2.5.0).

Why: Gemini Omni Flash bills 360p at a third of 720p. On 22-oct-2026 an 8 s 360x640 cartoon clip
went to 720x1280 with ``realesr-animevideov3`` in 62 s on this laptop (Iris Xe + Arc A370M together
through Vulkan, no NVIDIA needed), visibly sharper than a lanczos resize and close to a real 720p clip.
One GPU alone took ~100 s; the PNG round trip is most of the rest.

The program lives outside the repo (``REALESRGAN_EXE``, default D:/youtube/oss/realesrgan/bin), so
no binary is committed. Without it ``available()`` is False and callers keep their own resize.
"""
import glob
import os
import shutil
import subprocess
import tempfile

EXE = os.environ.get("REALESRGAN_EXE") or r"D:\youtube\oss\realesrgan\bin\realesrgan-ncnn-vulkan.exe"
VIDEO_MODEL = "realesr-animevideov3"      # made for video frames; x2/x3/x4 weights ship with the build
PHOTO_MODEL = "realesrgan-x4plus"          # stills (paintings, photos); x4 only
GPUS = os.environ.get("REALESRGAN_GPUS") or "0,1"
TIMEOUT = 30 * 60


def available():
    return os.path.isfile(EXE)


def _jobs():
    n = len(GPUS.split(","))
    return "2:" + ",".join(["2"] * n) + ":2"


def _run(src_dir, dst_dir, model, scale):
    subprocess.run([EXE, "-i", src_dir, "-o", dst_dir, "-n", model, "-s", str(scale), "-f", "png",
                    "-g", GPUS, "-j", _jobs()], cwd=os.path.dirname(EXE), check=True,
                   capture_output=True, timeout=TIMEOUT)


def fps_of(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=r_frame_rate", "-of", "csv=p=0", path],
                         capture_output=True, text=True, timeout=60).stdout.strip()
    num, _, den = out.partition("/")
    return f"{num}/{den or 1}" if num else "30"


def video(src, out, scale=2):
    """``src`` upscaled ``scale`` times (2-4) into ``out``, sound copied. Raises on failure."""
    work = tempfile.mkdtemp(prefix="upscale_")
    try:
        frames, big = os.path.join(work, "in"), os.path.join(work, "out")
        os.makedirs(frames)
        os.makedirs(big)
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", src, os.path.join(frames, "f%05d.png")],
                       check=True, capture_output=True, timeout=TIMEOUT)
        _run(frames, big, VIDEO_MODEL, scale)
        if len(glob.glob(os.path.join(big, "*.png"))) != len(glob.glob(os.path.join(frames, "*.png"))):
            raise RuntimeError("Real-ESRGAN left frames out")
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-framerate", fps_of(src),
                        "-i", os.path.join(big, "f%05d.png"), "-i", src, "-map", "0:v", "-map", "1:a?",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                        "-c:a", "copy", "-shortest", out], check=True, capture_output=True, timeout=TIMEOUT)
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def image(src, out):
    """A still upscaled 4x with the photo model into ``out`` (PNG)."""
    work = tempfile.mkdtemp(prefix="upscale_")
    try:
        os.makedirs(os.path.join(work, "in"))
        os.makedirs(os.path.join(work, "out"))
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", src, os.path.join(work, "in", "still.png")],
                       check=True, capture_output=True, timeout=300)
        _run(os.path.join(work, "in"), os.path.join(work, "out"), PHOTO_MODEL, 4)
        shutil.move(os.path.join(work, "out", "still.png"), out)
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)
