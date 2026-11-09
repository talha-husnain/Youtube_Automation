"""Intel Quick Sync encoding (FFMPEG_ENCODER=qsv / auto) and the gradient grain (4-nov-2026)."""
import json
import os
import shutil
import subprocess

import pytest

import ffmpeg_utils
import short_kit
from ffmpeg_utils import DELIVERY, INTERMEDIATE, QUALITY, QUALITY_FAST, reset_encoder_cache, video_encode_args

TIERS = (QUALITY, QUALITY_FAST, DELIVERY, INTERMEDIATE)
FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("FFMPEG_ENCODER", raising=False)
    reset_encoder_cache()
    yield
    reset_encoder_cache()


def test_every_table_has_every_tier():
    for table in (ffmpeg_utils._X264_ARGS, ffmpeg_utils._NVENC_ARGS, ffmpeg_utils._QSV_ARGS):
        assert set(table) == set(TIERS)


def test_intermediate_x264_is_short_kits_old_fast_pass():
    assert video_encode_args(INTERMEDIATE) == short_kit.FAST_PASS


def test_qsv_mode_uses_quick_sync_when_the_probe_passes(monkeypatch):
    monkeypatch.setenv("FFMPEG_ENCODER", "qsv")
    monkeypatch.setattr(ffmpeg_utils, "_probe_qsv", lambda: True)
    for tier in TIERS:
        args = video_encode_args(tier)
        assert args[:2] == ["-c:v", "h264_qsv"] and "-global_quality" in args
        assert args[-2:] == ["-pix_fmt", "nv12"]
        assert not any(a.startswith("-map_metadata") or a == "-crf" for a in args)
    assert ffmpeg_utils.encoder_name() == "h264_qsv"


def test_qsv_mode_falls_back_to_x264(monkeypatch, capsys):
    monkeypatch.setenv("FFMPEG_ENCODER", "qsv")
    monkeypatch.setattr(ffmpeg_utils, "_probe_qsv", lambda: False)
    assert video_encode_args(QUALITY) == ["-c:v", "libx264", "-preset", "medium", "-crf", "18"]
    assert "falling back to libx264" in capsys.readouterr().out


def test_auto_prefers_nvenc_then_qsv_then_x264(monkeypatch):
    monkeypatch.setenv("FFMPEG_ENCODER", "auto")
    probes = {"nvenc": True, "qsv": True}
    monkeypatch.setattr(ffmpeg_utils, "_probe_nvenc", lambda: probes["nvenc"])
    monkeypatch.setattr(ffmpeg_utils, "_probe_qsv", lambda: probes["qsv"])
    assert video_encode_args(QUALITY)[1] == "h264_nvenc"
    reset_encoder_cache()
    probes["nvenc"] = False
    assert video_encode_args(QUALITY)[1] == "h264_qsv"
    reset_encoder_cache()
    probes["qsv"] = False
    assert video_encode_args(QUALITY)[1] == "libx264"


def test_x264_mode_never_probes(monkeypatch):
    monkeypatch.setattr(ffmpeg_utils, "_probe_qsv", lambda: 1 / 0)
    monkeypatch.setattr(ffmpeg_utils, "_probe_nvenc", lambda: 1 / 0)
    assert video_encode_args(DELIVERY)[1] == "libx264"


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_real_quick_sync_encode_keeps_bt709_tags(tmp_path):
    """On a machine with Quick Sync (the owner's laptop) a real encode with a caller's late
    -pix_fmt yuv420p still works and carries the BT.709 tags short_kit asks for."""
    if not ffmpeg_utils._probe_qsv():
        pytest.skip("no Intel Quick Sync here")
    out = str(tmp_path / "q.mp4")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=1",
                        "-vf", short_kit.TO_BT709, *ffmpeg_utils._QSV_ARGS[QUALITY], "-pix_fmt", "yuv420p",
                        *short_kit.BT709_TAGS, out], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    info = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,pix_fmt,color_space,color_primaries,color_transfer,color_range", "-of", "json", out]))
    s = info["streams"][0]
    assert (s["codec_name"], s["pix_fmt"], s["color_space"], s["color_primaries"], s["color_transfer"],
            s["color_range"]) == ("h264", "yuv420p", "bt709", "bt709", "bt709", "tv")


# ---------- gradient grain ----------

def test_gradient_gets_a_fixed_grain_by_default(monkeypatch):
    monkeypatch.delenv("GRADIENT_GRAIN", raising=False)
    src = short_kit.bg_source(["#2B0F3D", "#8B5CF6"], 3)
    assert src.endswith(",noise=alls=2") and "allf" not in src      # fixed, never per frame (345 Mbps)
    monkeypatch.setenv("GRADIENT_GRAIN", "0")
    assert "noise" not in short_kit.bg_source(["#2B0F3D"], 3)
    monkeypatch.setenv("GRADIENT_GRAIN", "99")
    assert short_kit.bg_source(["#2B0F3D"], 3).endswith("alls=8")
    monkeypatch.setenv("GRADIENT_GRAIN", "lots")
    assert short_kit.bg_source(["#2B0F3D"], 3).endswith("alls=2")


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_grain_removes_banding_on_a_dark_gradient(tmp_path, monkeypatch):
    """CAMBI (libvmaf's banding score) of a short dark gradient, flat vs grained."""
    probe = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    if "libvmaf" not in probe:
        pytest.skip("ffmpeg without libvmaf")

    def cambi(grain):
        monkeypatch.setenv("GRADIENT_GRAIN", str(grain))
        # fixed gradient points: the filter picks random ones otherwise
        src = short_kit.bg_source(["#111111", "#3A1C1C"], 1).replace("gradients=", "gradients=seed=7:")
        out, log = str(tmp_path / f"g{grain}.mp4"), str(tmp_path / f"c{grain}.json")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", src, "-vf", short_kit.TO_BT709,
                        *short_kit.FAST_PASS, out], check=True)
        lp = log.replace("\\", "/").replace(":", "\\:")
        subprocess.run(["ffmpeg", "-v", "error", "-i", out, "-i", out, "-lavfi",
                        f"[0:v][1:v]libvmaf=feature=name=cambi:log_fmt=json:log_path='{lp}'", "-f", "null", "-"],
                       check=True)
        return json.load(open(log))["pooled_metrics"]["cambi"]["mean"]

    flat, grained = cambi(0), cambi(2)
    assert grained < 1.0 and grained < flat, (flat, grained)
