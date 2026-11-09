"""2.5D parallax for the still pictures of the long videos: near things slide a little more than far
ones as the camera pans, so a documentary made of Wikipedia pictures stops looking like a slideshow
(the biggest visual gap found in quality pass 2, 22-oct-2026).

Depth: Depth Anything V2 Small, ONNX export (onnx-community/depth-anything-v2-small, Apache-2.0; the
Base/Large/Giant weights are CC-BY-NC, so only Small may be used here). One inference per picture on
the CPU (onnxruntime, 518 px), cached next to the picture as .depth.npy. Frames: two cv2.remap calls
each (the pan, then the depth shift), piped to ffmpeg, which burns the same .ass the plain shot would.
The model lives outside the repo (DEPTH_MODEL); without it, or with PARALLAX=0, ``available()`` is False
and history_videos keeps its plain pan.
"""
import math
import os
import subprocess

import numpy as np

MODEL = os.environ.get("DEPTH_MODEL") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                      "oss", "models", "depth-anything-v2-small", "model.onnx")
INPUT = 518                     # the model's training size (a multiple of its 14 px patches)
AMP = 0.012                     # the nearest pixels move this share of the frame width more than the farthest
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_session = []


def available():
    return os.environ.get("PARALLAX", "1").strip() != "0" and os.path.isfile(MODEL)


def _sess():
    if not _session:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        _session.append(ort.InferenceSession(MODEL, sess_options=opts, providers=["CPUExecutionProvider"]))
    return _session[0]


def depth_of(bgr):
    """0..1 per pixel, 1 = nearest, smoothed so edges do not tear when shifted."""
    import cv2
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    x = cv2.resize(rgb, (INPUT, INPUT), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
    x = ((x - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)
    sess = _sess()
    d = sess.run(None, {sess.get_inputs()[0].name: x})[0]
    d = np.squeeze(d).astype(np.float32)
    lo, hi = np.percentile(d, 2), np.percentile(d, 98)
    d = np.clip((d - lo) / max(1e-6, hi - lo), 0, 1)
    h, w = bgr.shape[:2]
    d = cv2.resize(d, (w, h), interpolation=cv2.INTER_CUBIC)
    sigma = max(2.0, w / 250)
    return cv2.GaussianBlur(d, (0, 0), sigma)


def _depth_cached(path, bgr):
    cache = path + ".depth.npy"
    if os.path.isfile(cache):
        d = np.load(cache)
        if d.shape == bgr.shape[:2]:
            # The cache is float16 to save disk; cv2.remap has no float16 kernel ("ifunc != 0" in
            # imgwarp.cpp), so a cache hit used to fail every shot of a reused or retried picture
            # (server.log, 4-nov-2026: a 111-shot history video lost its parallax shot after shot).
            return d.astype(np.float32)
    d = depth_of(bgr)
    np.save(cache, d.astype(np.float16))
    return d.astype(np.float32)


# (pan x, pan y) as a function of the eased time e, and the camera's direction for the depth shift.
PATHS = {"right": (lambda e: e, lambda e: 0.5, (1, 0)), "left": (lambda e: 1 - e, lambda e: 0.5, (-1, 0)),
         "down": (lambda e: 0.5, lambda e: e, (0, 1)), "up": (lambda e: 0.5, lambda e: 1 - e, (0, -1)),
         "diag": (lambda e: e, lambda e: e, (0.7, 0.7)), "still": (lambda e: 0.5, lambda e: 0.5, (1, 0))}


def render(src, out, frames, fps, motion, size, vf_tail="", crf="20", cwd=None):
    """``src`` (the pan canvas) as ``frames`` frames of ``size`` panned along ``motion`` with parallax,
    encoded to ``out`` with ``vf_tail`` (e.g. the ass filter) after the frames. Raises on failure."""
    import cv2
    ow, oh = size
    bgr = cv2.imread(src if os.path.isabs(src) or not cwd else os.path.join(cwd, src), cv2.IMREAD_COLOR)
    if bgr is None:
        raise RuntimeError("picture could not be read")
    # Work at 1.15x the output (the canvas is ~2.3x): plenty of room to pan, a quarter of the pixels.
    scale = min(1.0, max(ow * 1.15 / bgr.shape[1], oh * 1.15 / bgr.shape[0]))
    if scale < 1.0:
        bgr = cv2.resize(bgr, (round(bgr.shape[1] * scale), round(bgr.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    depth = _depth_cached((src if os.path.isabs(src) or not cwd else os.path.join(cwd, src)) + f".{bgr.shape[1]}", bgr)
    H, W = bgr.shape[:2]
    if W < ow or H < oh:
        raise RuntimeError("picture smaller than the frame")
    px, py = W - ow, H - oh
    fx, fy, (dx, dy) = PATHS.get(motion, PATHS["right"])
    gx, gy = np.meshgrid(np.arange(ow, dtype=np.float32), np.arange(oh, dtype=np.float32))
    amp = AMP * ow
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{ow}x{oh}",
           "-r", str(fps), "-i", "-", "-vf", f"setsar=1,format=yuv420p{(',' + vf_tail) if vf_tail else ''}",
           "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", crf, "-pix_fmt", "yuv420p",
           "-video_track_timescale", "30000", "-an", out]
    p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for f in range(frames):
            e = 0.5 - 0.5 * math.cos(math.pi * f / max(1, frames - 1))
            ox, oy = px * fx(e), py * fy(e)
            # The depth under each output pixel, then the shift: near pixels lead the camera's way.
            d = cv2.remap(depth, gx + ox, gy + oy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            k = amp * (e - 0.5) * 2
            frame = cv2.remap(bgr, gx + ox - d * k * dx, gy + oy - d * k * dy, cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REFLECT)
            p.stdin.write(frame.tobytes())
        p.stdin.close()
        err = p.stderr.read().decode("utf-8", "replace")
        if p.wait(timeout=600) != 0:
            raise RuntimeError(f"parallax encode failed: {err.strip()[-300:]}")
    finally:
        if p.poll() is None:
            p.kill()
    return out
