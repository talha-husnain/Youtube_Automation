"""Where the people are in a frame, so a 9:16 crop of landscape footage keeps them in.

broll cut every stock clip to the centre: a presenter or a fan standing to one side lost half a
face. YuNet (OpenCV zoo, MIT, 230 KB ONNX) through cv2.FaceDetectorYN, ~10 ms a frame on the CPU.
MediaPipe's face API is missing from the version installed here (main.py's face_detection is None),
so this is the only face detector that runs on this laptop. ``FACE_CROP=0`` turns it off.
"""
import os
import subprocess
import threading

MODEL = os.environ.get("FACE_MODEL") or r"D:\youtube\oss\models\yunet\face_detection_yunet_2023mar.onnx"
MIN_SCORE = 0.7
_lock = threading.Lock()      # one detector, and broll renders shots on 3 threads
_det = None


def available():
    return os.environ.get("FACE_CROP", "1") != "0" and os.path.exists(MODEL)


def _frame(path, at):
    import cv2
    import numpy as np
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(0.0, at):.2f}", "-i", path,
                        "-frames:v", "1", "-vf", "scale=640:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True, timeout=60)
    if r.returncode != 0 or not r.stdout:
        return None
    return cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)


def boxes(img):
    """[(x, y, w, h, score)] of the faces in a BGR image."""
    import cv2
    global _det
    h, w = img.shape[:2]
    with _lock:
        if _det is None:
            _det = cv2.FaceDetectorYN.create(MODEL, "", (w, h), MIN_SCORE)
        _det.setInputSize((w, h))
        _n, found = _det.detect(img)
    return [tuple(float(v) for v in f[:4]) + (float(f[-1]),) for f in (found if found is not None else [])]


def center_x(path, at):
    """The biggest face's centre as a fraction of the frame's width, or None (no face, no model,
    any failure: the caller keeps its centred crop)."""
    if not available():
        return None
    try:
        img = _frame(path, at)
        if img is None:
            return None
        found = [b for b in boxes(img) if b[4] >= MIN_SCORE and b[2] * b[3] >= 0.002 * img.shape[0] * img.shape[1]]
        if not found:
            return None
        x, _y, bw, _bh, _s = max(found, key=lambda b: b[2] * b[3])
        return min(1.0, max(0.0, (x + bw / 2) / img.shape[1]))
    except Exception:  # noqa: BLE001
        return None
