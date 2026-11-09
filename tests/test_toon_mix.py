"""toon_mix.py: the cartoon channel's weekly compilation of its own kept episodes (a long video for watch hours)."""
import json
import os
import subprocess
import time

import my_channels as mc
import short_kit as kit
import toon_mix as tm


def _clip(path, seconds=2.0, colour="red"):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"color=c={colour}:s=1080x1920:r=30:d={seconds}", "-f", "lavfi", "-i",
                    f"sine=frequency=440:duration={seconds}", "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True, timeout=120)
    return str(path)


def _keep(tmp_path, n, seconds=3.0):
    src = _clip(tmp_path / f"src{n}.mp4", seconds + 1.5)
    from PIL import Image
    pic = str(tmp_path / f"pic{n}.png")
    Image.new("RGB", (90, 160), (200, 100, 30)).save(pic)
    return tm.keep(src, seconds, n, f"Episode title {n}", pic)


def test_an_episode_is_kept_cut_before_its_end_card(tmp_path):
    out = _keep(tmp_path, 4, seconds=2.0)
    assert out and os.path.isfile(out) and os.path.isfile(out[:-4] + ".jpg")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1",
                            out], capture_output=True, text=True)
    assert abs(float(probe.stdout) - 2.0) < 0.15
    rows = tm.kept()
    assert [r["n"] for r in rows] == [4] and rows[0]["title"] == "Episode title 4" and rows[0]["picture"]
    assert tm.keep(str(tmp_path / "missing.mp4"), 2.0, 5, "x") is None


def test_a_compilation_is_due_with_enough_new_episodes_once_a_week(tmp_path, monkeypatch):
    monkeypatch.setattr(tm, "MIN_EPISODES", 3)
    for n in (1, 2):
        _keep(tmp_path, n, 1.0)
    assert not tm.due()
    _keep(tmp_path, 3, 1.0)
    now = time.time()
    assert tm.due(now=now)
    assert not tm.due([{"format": "mix", "day": time.strftime("%Y-%m-%d", time.localtime(now))}], now=now)
    tm._save_mixes([{"vol": 1, "episodes": [1], "at": int(now) - 86400}])
    assert not tm.due(now=now)                                   # the last one was yesterday
    assert [r["n"] for r in tm.pending()] == [2, 3]
    monkeypatch.setenv("TOON_MIX", "0")
    assert not tm.due(now=now + 30 * 86400)


def test_chapters_start_at_zero_and_add_up():
    rows = [{"n": 3, "title": "Remote kahan hai? #funny", "seconds": 31.5}, {"n": 4, "title": "B", "seconds": 40},
            {"n": 5, "title": "C", "seconds": 35}]
    assert tm.chapters(rows) == [(0.0, "EP 3: Remote kahan hai?"), (31.5, "EP 4: B"), (71.5, "EP 5: C")]
    text = tm.describe(rows, 2, "@billo")
    assert "0:00 EP 3" in text and "0:31 EP 4" in text and "1:11 EP 5" in text and "@billo" in text
    assert len(tm.title(rows * 10, 12)) <= 100 and tm.clock(3725) == "1:02:05"


class _Pipeline:
    def auto_caption_clip(self, *a, **k):
        raise AssertionError("a compilation is captioned already")


def test_the_compilation_joins_the_episodes_in_order_and_marks_them(tmp_path, monkeypatch):
    for n in (1, 2, 3):
        _keep(tmp_path, n, 1.5)
    out_dir = tmp_path / "job"
    out_dir.mkdir()
    monkeypatch.setattr(kit, "level", lambda path, **k: path)
    final = tm.run(str(out_dir), _Pipeline())
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of",
                            "json", final], capture_output=True, text=True)
    info = json.loads(probe.stdout)
    assert abs(float(info["format"]["duration"]) - 4.5) < 0.4
    assert {(s.get("width"), s.get("height")) for s in info["streams"] if s.get("width")} == {(1080, 1920)}
    meta = json.loads(next((out_dir).glob("*_metadata.json")).read_text())
    clip = meta["shorts"][0]
    assert clip["toon_mix"]["episodes"] == [1, 2, 3] and len(clip["chapters"]) == 3 and clip["ai_made"]
    assert os.path.isfile(out_dir / "thumbnail.jpg")
    assert tm.mixes()[0]["episodes"] == [1, 2, 3] and tm.pending() == []


def test_the_cartoon_card_sends_its_compilation_first_and_uploads_it_long(tmp_path, monkeypatch):
    import youtube_account
    monkeypatch.setattr(tm, "MIN_EPISODES", 2)
    for n in (1, 2):
        _keep(tmp_path, n, 1.0)
    ch = mc.add("toons")
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["toon_mix"] is True and payload["genre"] == "toons" and meta["format"] == "mix"
    assert mc.upload_genre(mc.get(ch["id"]), {"format": "mix"}) == "toons_mix"
    assert mc.upload_genre(mc.get(ch["id"]), {"format": "toons"}) == "toons"
    assert "toons_mix" in youtube_account.LONG_GENRES and youtube_account.CATEGORY["toons_mix"] == "23"
    mc.update(ch["id"], {"toon_mix": False})
    assert not mc.mix_due(mc.get(ch["id"]))


def test_a_long_vertical_video_is_not_sent_to_reels(monkeypatch, tmp_path):
    import meta_publish
    f = tmp_path / "long.mp4"
    f.write_bytes(b"x")
    monkeypatch.setattr(meta_publish, "targets", lambda ch: ({"id": "p"}, {"id": "p"}))
    monkeypatch.setattr(meta_publish, "_probe", lambda path: (1080, 1920, 420.0))
    assert meta_publish.enqueue({"id": "c"}, {"title": "t"}, str(f)) is None
