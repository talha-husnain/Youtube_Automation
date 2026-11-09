"""stickers.py: the Gemini pick (faked), the code's own rules over it, and the ffmpeg pieces."""
import json
import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest

import stickers

ANIM_HEADER = b"RIFF\x00\x00\x00\x00WEBPVP8X" + bytes([10, 0, 0, 0, 0x12])  # alpha + animation flags


@pytest.fixture
def sticker_dir(tmp_path, monkeypatch):
    d = tmp_path / "stickers"
    d.mkdir()
    for code in stickers.EMOJI.values():
        (d / f"{code}.webp").write_bytes(ANIM_HEADER)
    monkeypatch.setenv("STICKER_DIR", str(d))
    monkeypatch.setenv("STICKERS", "1")
    return d


def fake_client(answer=None, error=None, calls=None):
    def generate_content(**kw):
        if calls is not None:
            calls.append(kw)
        if error:
            raise error
        text = answer if isinstance(answer, str) else json.dumps(answer)
        return SimpleNamespace(text=text)
    return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))


def rows(pairs):
    return {"lines": [{"line": n, "sticker": s} for n, s in pairs]}


LINES = [f"Line {i} about a cricket match" for i in range(1, 11)]


def test_one_call_and_spacing(sticker_dir):
    calls = []
    # The model asks for 1, 2, 3, 5, 6 and 9: lines 2 and 3 are too close to 1, 6 to 5.
    answer = rows([(1, "fire"), (2, "shocked"), (3, "trophy"), (4, "none"), (5, "clap"),
                   (6, "eyes"), (7, "none"), (8, "none"), (9, "crown"), (10, "none")])
    got = stickers.pick(fake_client(answer, calls=calls), LINES, log=lambda *_: None)
    assert len(calls) == 1
    assert got == ["fire", "", "", "", "clap", "", "", "", "crown", ""]
    # Never two in a row, and every pair at least GAP lines apart.
    on = [i for i, n in enumerate(got) if n]
    assert all(b - a >= stickers.GAP for a, b in zip(on, on[1:]))


def test_prompt_lists_only_the_closed_choice(sticker_dir):
    calls = []
    stickers.pick(fake_client(rows([]), calls=calls), LINES[:3], log=lambda *_: None)
    prompt = calls[0]["contents"]
    for name in stickers.EMOJI:
        assert f"- {name}:" in prompt
    assert "death" in prompt and "religion" in prompt and "allegation" in prompt
    assert "3. Line 3" in prompt


def test_unknown_names_and_bad_line_numbers_dropped(sticker_dir):
    answer = rows([(1, "unicorn"), (4, " Trophy "), (7, ""), (99, "fire"), (0, "fire")])
    got = stickers.pick(fake_client(answer), LINES, log=lambda *_: None)
    assert got == ["", "", "", "trophy", "", "", "", "", "", ""]


def test_name_without_a_file_dropped(sticker_dir):
    os.remove(sticker_dir / f"{stickers.EMOJI['fire']}.webp")
    assert stickers.path("fire") is None
    calls = []
    got = stickers.pick(fake_client(rows([(1, "fire"), (5, "clap")]), calls=calls), LINES,
                        log=lambda *_: None)
    assert got[0] == "" and got[4] == "clap"
    assert "- fire:" not in calls[0]["contents"]


def test_blocked_lines_get_nothing(sticker_dir):
    lines = ["Pakistan ne final jeet liya",
             "Lekin team ke purane coach ki maut ki khabar aayi",
             "Is par ilzaam hai ke usne paise liye",
             "Bowling attack ne kamaal kar diya",   # "attack" is cricket, not a block word
             "Imam-ul-Haq ne 100 banaye"]
    answer = rows([(1, "none"), (2, "heartbreak"), (3, "angry"), (4, "fire"), (5, "none")])
    got = stickers.pick(fake_client(answer), lines, log=lambda *_: None)
    assert got == ["", "", "", "fire", ""]
    assert stickers.enforce(["", "", "", "", "hundred"], lines)[4] == "hundred"


@pytest.mark.parametrize("client", [
    fake_client(error=ValueError("quota")),
    fake_client("this is not json"),
    fake_client({"lines": "wrong shape"}),
    None,
])
def test_failure_gives_blanks(sticker_dir, client):
    logs = []
    assert stickers.pick(client, LINES[:4], log=logs.append) == ["", "", "", ""]
    assert logs and "skipped" in logs[0]


def test_empty_lines(sticker_dir):
    assert stickers.pick(fake_client(rows([])), [], log=lambda *_: None) == []


def test_available_off_by_env_and_no_call(sticker_dir, monkeypatch):
    assert stickers.available()
    monkeypatch.setenv("STICKERS", "0")
    assert not stickers.available()
    calls = []
    assert stickers.pick(fake_client(rows([(1, "fire")]), calls=calls), LINES[:3],
                         log=lambda *_: None) == ["", "", ""]
    assert calls == []


def test_available_needs_files(tmp_path, monkeypatch):
    monkeypatch.setenv("STICKERS", "1")
    monkeypatch.setenv("STICKER_DIR", str(tmp_path / "missing"))
    assert not stickers.available()
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv("STICKER_DIR", str(tmp_path / "empty"))
    assert not stickers.available()
    assert stickers.path("fire") is None and stickers.path("nope") is None and stickers.path("") is None


def test_overlay_args_window(sticker_dir):
    p = str(sticker_dir / "1f525.webp")
    inputs, filters, out = stickers.overlay_args(p, 3, 1.0, 3.0, 780, 1290, size=260,
                                                 src="[v_im0]", label="stk1")
    assert inputs == ["-f", "webp_anim", "-ignore_loop", "0", "-t", "2.000", "-i", p]
    assert filters[0].startswith("[3:v]setpts=PTS-STARTPTS+1.000/TB,")
    assert "eval=frame" in filters[0] and filters[0].endswith("[stk1]")
    assert "fade=t=out:st=2.750:d=0.25:alpha=1" in filters[0]
    assert filters[1].startswith("[v_im0][stk1]overlay=")
    assert "enable='between(t,1.000,3.000)'" in filters[1]
    assert "x='780-w/2'" in filters[1] and "y='1290-h/2'" in filters[1]
    assert out == "[stk1_v]" and filters[1].endswith(out)


def test_overlay_args_kept_alive_over_footage(sticker_dir):
    p = str(sticker_dir / "1f525.webp")
    inputs, filters, _ = stickers.overlay_args(p, 2, 4.0, 6.0, 300, 1290, alive_until=30.0)
    assert inputs[inputs.index("-t") + 1] == "26.500"
    assert "enable='between(t,4.000,6.000)'" in filters[1]


def test_still_webp_is_looped_as_a_picture(tmp_path):
    still = tmp_path / "still.webp"
    still.write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8L" + b"\x00" * 16)
    assert not stickers.animated(str(still))
    inputs, _, _ = stickers.overlay_args(str(still), 1, 0.5, 2.0, 540, 960)
    assert inputs[:4] == ["-loop", "1", "-framerate", "30"] and "-ignore_loop" not in inputs


def test_place_times_and_sides(sticker_dir):
    picks = ["fire", "", "", "clap", "", "", "crown"]
    spans = [(0.2, 3.0), (3.0, 5.0), (5.0, 7.0), (7.0, 7.9), (8, 10), (10, 12), (12.0, 20.0)]
    got = stickers.place(picks, spans, seconds=13.0)
    assert [g["name"] for g in got] == ["fire", "clap", "crown"]
    assert got[0]["t0"] == pytest.approx(0.35) and got[0]["t1"] == pytest.approx(2.55)  # HOLD caps it
    assert got[1]["t1"] == pytest.approx(8.15)   # a short line still shows 1 s
    assert got[2]["t1"] == pytest.approx(13.0)   # never past the video
    # The top-left corner: never over the captions (which moved up out of YouTube's overlay into the
    # old sticker band) or a card, nor under YouTube's button column or the centred kicker pill.
    import cricket_shorts
    import short_kit
    for g in got:
        assert g["y"] + g["size"] / 2 < cricket_shorts.CARD_Y - 72 < short_kit.CAPTION_TOP_PX
        assert g["x"] - g["size"] / 2 >= 0 and g["x"] + g["size"] / 2 <= 380


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_overlay_renders_with_transparency(tmp_path):
    """The helper's own inputs + filters in a real ffmpeg run: a moving red box with a
    transparent surround, looped, over a solid background."""
    anim = tmp_path / "anim.webp"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "color=c=red:s=64x64:r=10:d=0.5,format=rgba,geq=r='255':g='0':b='0':"
                    "a='if(lt(abs(X-32-20*sin(T*6)),10)*lt(abs(Y-32),20),255,0)'",
                    "-c:v", "libwebp_anim", "-lossless", "1", "-loop", "0", "-f", "webp", str(anim)],
                   check=True, timeout=60)
    assert stickers.animated(str(anim))
    out = tmp_path / "out.mp4"
    inputs, filters, label = stickers.overlay_args(str(anim), 1, 0.2, 1.8, 160, 160, size=128,
                                                   alive_until=2.0)
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "color=c=0x2B0F3D:s=320x320:r=30:d=2", *inputs,
                    "-filter_complex", ";".join(filters + [f"{label}format=yuv420p[v]"]),
                    "-map", "[v]", "-t", "2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10",
                    str(out)], check=True, timeout=120)

    def pixel(t, x, y):
        raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(t), "-i", str(out),
                              "-frames:v", "1", "-vf", f"crop=1:1:{x}:{y},format=rgb24",
                              "-f", "rawvideo", "-"], capture_output=True, check=True, timeout=60).stdout
        return tuple(raw[:3])

    bg = pixel(1.0, 5, 5)
    assert pixel(1.0, 160 - 60, 160 - 60) == pytest.approx(bg, abs=4)   # transparent corner of the box
    assert pixel(0.1, 160, 160) == pytest.approx(bg, abs=4)             # before t0
    assert pixel(1.95, 160, 160) == pytest.approx(bg, abs=4)            # after t1
    # The box moves (sin over 0.5 s, looped): some frame in the window has red at the centre
    # and some does not, after the 0.32 s pop.
    centre = [pixel(t, 160, 160) for t in (0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3)]
    assert any(c[0] > 200 and c[2] < 60 for c in centre)
    assert len(set(centre)) > 1
