"""The same song never uploads twice (5-nov-2026, audio_dedupe.py with Chromaprint's fpcalc)."""
import random

import pytest

import audio_dedupe as ad


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setattr(ad, "STATE_DIR", str(tmp_path / "fingerprints"))


def _fp(n, seed):
    rnd = random.Random(seed)
    return [rnd.getrandbits(32) for _ in range(n)]


def test_the_same_recording_matches_through_a_shift_and_noise():
    a = _fp(400, 1)
    cut = a[40:300]                                           # the Short starts 5 s into the song
    noisy = [x ^ (1 << (k % 32)) if k % 3 == 0 else x for k, x in enumerate(cut)]   # a re-encode flips some bits
    assert ad.similarity(a, cut) == 1.0 and ad.similarity(cut, a) == 1.0
    assert ad.similarity(a, noisy) >= 0.98
    other = _fp(400, 2)
    assert 0.4 < ad.similarity(a, other) < 0.6                # unrelated sound: about half the bits
    assert ad.similarity(a, a[:10]) == 0.0                    # too short to say


def test_a_kept_song_is_found_again_and_not_itself():
    a, b = _fp(300, 3), _fp(300, 4)
    ad.remember("music", "job-a", "Snow on Your Lapel", a)
    ad.remember("music", "job-b", "Cuff of Your Cardigan", b)
    dup = ad.duplicate("music", a[20:250])
    assert dup["key"] == "job-a" and dup["title"] == "Snow on Your Lapel" and dup["score"] == 1.0
    assert ad.duplicate("music", a, exclude="job-a") is None      # a job is never its own duplicate
    assert ad.duplicate("music", _fp(300, 5)) is None and ad.duplicate("music", None) is None
    assert ad.duplicate("quiz", a) is None                        # per channel


def test_the_kept_list_is_capped(monkeypatch):
    monkeypatch.setattr(ad, "KEEP", 3)
    for k in range(5):
        ad.remember("music", f"j{k}", f"t{k}", _fp(80, k))
    assert [r["key"] for r in ad._load("music")] == ["j2", "j3", "j4"]


@pytest.mark.skipif(not ad.available(), reason="fpcalc not installed")
def test_fpcalc_fingerprints_a_real_file(tmp_path):
    import subprocess
    src = tmp_path / "tone.wav"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "aevalsrc='sin(220*2*PI*t)*0.4+sin(330*2*PI*t*(1+0.2*sin(t)))*0.3':d=20", str(src)], check=True)
    fp = ad.fingerprint(str(src))
    assert fp and len(fp) > 100 and all(0 <= x < 2 ** 32 for x in fp)
    copy = tmp_path / "copy.m4a"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", "2", "-i", str(src), "-b:a", "96k", str(copy)],
                   check=True)
    assert ad.similarity(ad.fingerprint(str(copy)), fp) >= ad.MATCH


def test_a_repeated_song_is_skipped_before_upload(monkeypatch):
    import my_channels as mc
    import youtube_account as ya
    ch = mc.add("music")
    ad.remember(ch["id"], "old-job", "Snow on Your Lapel", _fp(300, 7))
    mc._change(ch["id"], lambda c: c.update(auto_upload=True, jobs=[{"job_id": "new-job", "status": "done",
                                                                       "format": "upbeat pop", "at": 1, "day": "d"}]))
    monkeypatch.setattr(ad, "available", lambda: True)
    monkeypatch.setattr(ad, "fingerprint", lambda path, seconds=ad.SECONDS: _fp(300, 7)[30:260])
    monkeypatch.setattr(ya, "status", lambda: {"connected": True})
    monkeypatch.setattr(ya, "upload", lambda *a, **k: pytest.fail("a repeated song must not upload"))
    clip = {"index": 0, "path": "x.mp4", "title": "Snow again", "description": "d", "tags": [], "seconds": 30}
    monkeypatch.setenv("VIDEO_QA", "0")
    monkeypatch.setenv("CREATIVE_QA", "0")
    mc.upload_waiting(mc.get(ch["id"]), lambda job_id: ("completed", [clip]), log=lambda *a: None)
    job = mc.get(ch["id"])["jobs"][0]
    assert job["status"] == "skipped" and "Snow on Your Lapel" in job["error"]
    # A new song uploads and is kept for the next check.
    sent = []
    monkeypatch.setattr(ad, "fingerprint", lambda path, seconds=ad.SECONDS: _fp(300, 8))
    monkeypatch.setattr(ya, "upload", lambda *a, **k: sent.append(1) or {"status": "done", "video_id": "NeWsOnG0001",
                                                                       "title": "Snow again"})
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "next-job", "status": "done", "format": "upbeat pop",
                                                   "at": 2, "day": "d"}]))
    mc.upload_waiting(mc.get(ch["id"]), lambda job_id: ("completed", [clip]), log=lambda *a: None)
    assert sent == [1] and [r["key"] for r in ad._load(ch["id"])] == ["old-job", "next-job"]
