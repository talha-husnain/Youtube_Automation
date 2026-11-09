"""Quality pass 2 (22-oct-2026): music ducked under the voices with a limiter on the sum."""
import short_kit as kit


def test_the_bed_is_ducked_under_the_voices_and_the_sum_limited(monkeypatch):
    monkeypatch.delenv("MUSIC_DUCK", raising=False)
    graph = []
    kit._final_mix(graph, ["[0:a]", "[bed]", "[vo0]", "[vo1]", "[sx0]"])
    text = ";".join(graph)
    assert "[vo0][vo1]amix=inputs=2:normalize=0,asplit=2[vox][vkey]" in text
    assert "[bed][vkey]sidechaincompress" in text
    assert graph[-1].startswith("[0:a][sx0][vox][bedd]amix=inputs=4:duration=first") and "alimiter" in graph[-1]


def test_no_bed_or_switched_off_is_the_plain_sum(monkeypatch):
    graph = []
    kit._final_mix(graph, ["[0:a]", "[vo0]"])
    assert graph == ["[0:a][vo0]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=0[a]"]
    monkeypatch.setenv("MUSIC_DUCK", "0")
    graph = []
    kit._final_mix(graph, ["[0:a]", "[bed]", "[vo0]"])
    assert "sidechaincompress" not in ";".join(graph)
    graph = []
    kit._final_mix(graph, ["[1:a]"])
    assert graph == ["[1:a]anull[a]"]


def test_numbers_and_names_are_coloured_only_when_asked(monkeypatch, tmp_path):
    import subtitles
    assert subtitles._emphasised(["Babar", "Azam", "ne", "120", "runs", "banaye.", "Phir", "Lahore", "mein"]) == {0, 1, 3, 7}
    assert subtitles._emphasised(["Aaj", "120", "runs"]) == {1}      # a number does not pull in the word before
    tr = {"segments": [{"start": 0, "end": 3, "words": [
        {"word": " Babar", "start": 0.0, "end": 0.5}, {"word": " Azam", "start": 0.5, "end": 1.0},
        {"word": " ne", "start": 1.0, "end": 1.3}, {"word": " 120", "start": 1.3, "end": 2.0},
        {"word": " runs", "start": 2.0, "end": 3.0}]}]}
    out = str(tmp_path / "a.ass")
    st = subtitles.AUTO_CAPTION_STYLE
    kw = dict(max_chars=st["max_chars"], max_duration=st["max_duration"], fontsize=st["font_size"],
              font_name=st["font_name"], highlight_color=st["highlight_color"], effect=st["effect"],
              uppercase=st["uppercase"])
    monkeypatch.setenv("CAPTION_EMPHASIS", "1")
    subtitles.generate_ass(tr, 0, 3, out, **kw)
    on = open(out, encoding="utf-8-sig").read()
    monkeypatch.setenv("CAPTION_EMPHASIS", "0")
    subtitles.generate_ass(tr, 0, 3, out, **kw)
    off = open(out, encoding="utf-8-sig").read()
    colour = subtitles._hex_to_ass_inline_color(subtitles.EMPHASIS_COLOR)
    assert colour in on and colour not in off


def test_generated_shorts_end_quickly_so_they_loop(monkeypatch):
    monkeypatch.delenv("SHORT_OUTRO_SECONDS", raising=False)
    assert kit.outro_seconds({"outro_seconds": 3.0}) == 1.5
    assert kit.outro_seconds({"outro_seconds": 1.2}) == 1.2
    monkeypatch.setenv("SHORT_OUTRO_SECONDS", "0.2")
    assert kit.outro_seconds({"outro_seconds": 3.0}) == 1.0
    import cricket_shorts
    assert cricket_shorts.LEAD < 0.2


def test_history_shots_are_shorter_and_eased_unless_switched_off():
    import importlib
    import os
    import history_videos as hv
    assert hv.SHOT_SECONDS == 7.0 and hv._motion() and hv.CRF == "20"
    os.environ["HISTORY_MOTION"] = "0"
    try:
        importlib.reload(hv)
        assert hv.SHOT_SECONDS == 11.0 and not hv._motion()
    finally:
        del os.environ["HISTORY_MOTION"]
        importlib.reload(hv)


def test_parallax_renders_every_frame_and_falls_back_without_its_model(monkeypatch, tmp_path):
    import subprocess
    import numpy as np
    import parallax
    src = str(tmp_path / "pic.png")
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=240x140",
                    "-frames:v", "1", src], check=True, capture_output=True)
    monkeypatch.setattr(parallax, "_depth_cached", lambda path, bgr: np.tile(
        np.linspace(0, 1, bgr.shape[1], dtype=np.float32), (bgr.shape[0], 1)))
    out = parallax.render(src, str(tmp_path / "out.mp4"), 12, 30, "right", (192, 108))
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                            "stream=width,height,nb_read_frames", "-of", "csv=p=0", out], capture_output=True, text=True)
    assert probe.stdout.strip().replace("\r", "") == "192,108,12"
    monkeypatch.setattr(parallax, "MODEL", str(tmp_path / "missing.onnx"))
    assert not parallax.available()


def test_a_cutout_is_used_only_for_cricket_and_only_when_it_is_clean(monkeypatch, tmp_path):
    import player_photo as pp
    from PIL import Image
    src = str(tmp_path / "p.jpg")
    Image.new("RGB", (300, 400), (90, 90, 90)).save(src)
    mask = Image.new("L", (300, 400), 0)
    mask.paste(255, (80, 60, 220, 400))           # a bust: a third of the picture, down to the bottom edge
    monkeypatch.setenv("CUTOUT", "1")
    monkeypatch.setattr(pp, "CUTOUT_MODEL", __file__)
    monkeypatch.setattr(pp, "person_mask", lambda path: mask)
    monkeypatch.setattr(pp, "_clean_cut", lambda im: True)
    assert pp.cutout_card(src, str(tmp_path / "c.png"), (140, 160)) == str(tmp_path / "c.png")
    monkeypatch.setattr(pp, "_clean_cut", lambda im: False)
    assert pp.cutout_card(src, str(tmp_path / "d.png"), (140, 160)) is None
    floating = Image.new("L", (300, 400), 0)
    floating.paste(255, (100, 50, 200, 200))     # does not reach the bottom: not a person's bust
    monkeypatch.setattr(pp, "person_mask", lambda path: floating)
    monkeypatch.setattr(pp, "_clean_cut", lambda im: True)
    assert pp.cutout_card(src, str(tmp_path / "e.png"), (140, 160)) is None


def test_history_captions_fill_word_by_word_within_their_time(monkeypatch):
    import re
    import history_videos as hv
    text = hv._karaoke("Sultan Mehmed ne 1453 mein Constantinople fatah kiya", 3.2)
    cs = [int(x) for x in re.findall(r"\\kf?(\d+)", text)]
    assert text.startswith("{\\k") and text.count("\\kf") == 8 and abs(sum(cs) - 320) <= 8
    ev = hv.shot_events(4.0, caps=[("ek do", 0.2, 1.4)])
    assert any("HvCapK" in e for e in ev)
    monkeypatch.setenv("HISTORY_KARAOKE", "0")
    assert any("HvCap," in e for e in hv.shot_events(4.0, caps=[("ek do", 0.2, 1.4)]))
