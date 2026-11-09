"""parallax.render on a picture whose depth map is already cached (4-nov-2026): the float16 cache
reached cv2.remap as float16 and every reused or retried picture lost its parallax."""
import os
import shutil

import numpy as np
import pytest

import parallax


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_a_cached_depth_map_still_renders(tmp_path, monkeypatch):
    import cv2
    pic = str(tmp_path / "p.jpg")
    img = np.zeros((90, 160, 3), np.uint8)
    img[:, :, 1] = np.linspace(0, 255, 160, dtype=np.uint8)[None, :]
    cv2.imwrite(pic, img)
    calls = []

    def fake_depth(bgr):                       # no ONNX model in tests
        calls.append(1)
        h, w = bgr.shape[:2]
        return np.tile(np.linspace(0, 1, w, dtype=np.float32), (h, 1))

    monkeypatch.setattr(parallax, "depth_of", fake_depth)
    for n in (1, 2):                           # 1 = fresh depth, 2 = from the .depth.npy cache
        out = str(tmp_path / f"o{n}.mp4")
        parallax.render(pic, out, frames=4, fps=30, motion="right", size=(128, 72))
        assert os.path.getsize(out) > 0
    assert len(calls) == 1, "the second render must come from the cache"
    bgr = cv2.imread(pic)
    first = parallax._depth_cached(str(tmp_path / "direct"), bgr)
    again = parallax._depth_cached(str(tmp_path / "direct"), bgr)          # read back from the float16 file
    assert first.dtype == again.dtype == np.float32 and len(calls) == 2
