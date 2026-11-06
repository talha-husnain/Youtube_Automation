"""Smooth slow motion for short stock clips with RIFE (ncnn-vulkan build, MIT, nihui/rife-ncnn-vulkan 20221029).

Why: when a stock clip is shorter than the shot it fills, ``broll`` loops it with ``-stream_loop -1``
and the picture visibly jumps back to its first frame mid-shot. Stretching the clip instead (RIFE
makes the in-between frames, so it plays slower without stutter) hides that jump. Only a modest
stretch is worth it: under 1.15x the loop is barely seen anyway, over 4x the made-up frames smear.

Measured on this laptop (Iris Xe + Arc A370M through Vulkan, no NVIDIA) on 22-oct-2026, rife-v4.6,
3 s of a real 1080x1920 30 fps stock clip (90 frames) doubled to 180, RIFE alone:
  720x1280:  both GPUs (-g 0,1) 11.8-12.4 s, Arc alone 12.5-13.0 s, Iris Xe alone 18.7 s
  1080x1920: both GPUs 25.0-32.5 s, Arc alone 27.8-28.0 s, Iris Xe alone 35.9 s
Both GPUs vary run to run and are about even with the Arc alone; the Iris Xe alone is the slow one.
Whole ``stretch`` (extract + RIFE + encode), 2 s stretched to 4 s (120 frames): 11-14 s at the
default 1280 long side, 25.6 s at full 1080x1920. Hence the 1280 cap: broll upscales and sharpens anyway.


The program lives outside the repo (``RIFE_EXE``, default D:/youtube/oss/rife), so no binary is
committed. Without it ``available()`` is False and broll keeps looping. ``SLOWMO=0`` turns it off.
"""
import glob
import os
import re
import shutil
import subprocess
import tempfile

EXE = os.environ.get("RIFE_EXE") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "oss",
                                                  "rife", "rife-ncnn-vulkan-20221029-windows", "rife-ncnn-vulkan.exe")
# rife-v4.x is the only family that takes ``-n`` (any target frame count, any timestep);
# the older models in the zip only double. v4.6 is the newest one in this build.
MODEL = os.environ.get("RIFE_MODEL") or "rife-v4.6"
GPUS = os.environ.get("RIFE_GPUS") or "0,1"
LONG_SIDE = 1280                 # frames are scaled down to this for speed, aspect kept
MIN_RATIO, MAX_RATIO = 1.15, 4.0
TIMEOUT = 10 * 60


def available():
    return os.environ.get("SLOWMO", "1").strip() != "0" and os.path.isfile(EXE)


def _jobs():
    n = len(GPUS.split(","))
    return "1:" + ",".join(["2"] * n) + ":2"


def _frames(folder):
    return sorted(glob.glob(os.path.join(folder, "*.png")))


def stretch(src, offset, have_seconds, need_seconds, out, fps=30, size=None, run=subprocess.run):
    """``src`` from ``offset`` for ``have_seconds`` slowed to fill ``need_seconds``, written to ``out``.

    Returns ``out``, or None when it should not or could not be done (never raises): the caller
    then loops the clip as before. ``size`` is the (w, h) box the frames are fitted into, aspect
    kept, never upscaled; by default the long side is at most 1280. The result has exactly
    ``round(need_seconds * fps)`` frames at ``fps``, libx264 crf 18, yuv420p, no sound.
    """
    if not available():
        return None
    try:
        have, need = float(have_seconds), float(need_seconds)
        if have <= 0 or not MIN_RATIO <= need / have <= MAX_RATIO:
            return None
        target = int(round(need * fps))
        bw, bh = size or (LONG_SIDE, LONG_SIDE)
    except (TypeError, ValueError):
        return None
    work = tempfile.mkdtemp(prefix="slowmo_")
    try:
        frames, made = os.path.join(work, "in"), os.path.join(work, "out")
        os.makedirs(frames)
        os.makedirs(made)
        # The source's own frames (any fps): RIFE spreads ``target`` frames evenly over them.
        fit = (f"scale=w='min(iw,{int(bw)})':h='min(ih,{int(bh)})':force_original_aspect_ratio=decrease"
               f":force_divisible_by=2,setsar=1")
        run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{max(0.0, float(offset)):.3f}", "-i", src,
             "-t", f"{have:.3f}", "-an", "-vf", fit, os.path.join(frames, "f%06d.png")],
            check=True, capture_output=True, timeout=TIMEOUT)
        if len(_frames(frames)) < 2:
            raise RuntimeError("fewer than 2 source frames")
        run([EXE, "-i", frames, "-o", made, "-n", str(target), "-m", os.path.join(os.path.dirname(EXE), MODEL),
             "-g", GPUS, "-j", _jobs(), "-f", "%08d.png"],
            cwd=os.path.dirname(EXE), check=True, capture_output=True, timeout=TIMEOUT)
        got = _frames(made)
        if len(got) != target:
            raise RuntimeError(f"RIFE made {len(got)} frames, wanted {target}")
        first = int(re.sub(r"\D", "", os.path.basename(got[0])) or 0)
        run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-framerate", str(fps), "-start_number", str(first),
             "-i", os.path.join(made, "%08d.png"), "-frames:v", str(target), "-an", "-c:v", "libx264",
             "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", out],
            check=True, capture_output=True, timeout=TIMEOUT)
        if not os.path.isfile(out) or os.path.getsize(out) == 0:
            raise RuntimeError("no output file")
        return out
    except Exception as e:  # any failure: the caller loops the clip instead
        err = getattr(e, "stderr", None)
        detail = (err.decode("utf-8", "replace") if isinstance(err, bytes) else str(err or "")).strip()[-200:]
        print(f"slowmo: {type(e).__name__}: {e} {detail}".strip())
        try:
            if os.path.isfile(out):
                os.remove(out)
        except OSError:
            pass
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)
