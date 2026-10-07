"""compilation.py: moment choice, joined timeline, join command, and a real
ffmpeg join of two sources with different sizes and frame rates."""
import shutil
import subprocess

import pytest

import compilation


def _clip(start, end, score):
    return {"start": start, "end": end, "predicted_score": score}


def test_choose_gives_every_video_its_best_then_fills_by_score():
    a = [_clip(0, 50, 90), _clip(100, 140, 85), _clip(200, 230, 60)]
    b = [_clip(10, 40, 70), _clip(300, 340, 65)]
    picked = compilation.choose({0: a, 1: b}, budget=125, fade=0.4)
    got = [(v, c["start"]) for v, c in picked]
    # Best overall opens; the rest in link order and time.
    assert got[0] == (0, 0)
    assert (1, 10) in got and (0, 100) in got
    total = sum(c["end"] - c["start"] for _, c in picked) - 0.4 * (len(picked) - 1)
    assert total <= 125
    assert got[1:] == sorted(got[1:])


def test_choose_skips_what_does_not_fit_and_handles_empty():
    assert compilation.choose({0: [], 1: []}, budget=100) == []
    picked = compilation.choose({0: [_clip(0, 200, 99), _clip(0, 30, 10)]}, budget=60)
    assert [(c["start"], c["end"]) for _, c in picked] == [(0, 30)]


def test_merged_transcript_moves_words_onto_the_joined_timeline():
    def w(word, s):
        return {"word": word, "start": s, "end": s + 0.5}
    t1 = {"segments": [{"words": [w(" a", 9.0), w(" b", 10.0), w(" c", 15.0)]}]}
    t2 = {"segments": [{"words": [w(" x", 100.0), w(" y", 101.0)]}]}
    m = compilation.merged_transcript([(t1, 10.0, 14.0, 0.0), (t2, 100.0, 105.0, 3.6)], "hi")
    words = [(x["word"], x["start"]) for s in m["segments"] for x in s["words"]]
    assert words == [(" b", 0.0), (" x", 3.6), (" y", 4.6)]
    assert m["language"] == "hi"


def test_offsets_overlap_by_the_fade():
    assert compilation._offsets([10.0, 20.0, 5.0], fade=0.5) == [0.0, 9.5, 29.0]


def test_join_command_chains_xfade_at_the_right_offsets():
    cmd = compilation.join_command(["a.mp4", "b.mp4", "c.mp4"], [10.0, 20.0, 5.0], "o.mp4", fade=0.5)
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade=transition=fade:duration=0.5:offset=9.500[x1]" in graph
    assert "offset=29.000[x2]" in graph and "acrossfade=d=0.5[y2]" in graph
    assert cmd[cmd.index("-map") + 1] == "[x2]"


def test_budget_stays_under_three_minutes_with_the_end_card(monkeypatch):
    monkeypatch.setenv("COMPILE_SECONDS", "500")
    monkeypatch.setenv("FRAME_OUTRO", "1")
    monkeypatch.setenv("FRAME_OUTRO_SECONDS", "3")
    assert compilation.budget_seconds() + 3 < 180
    monkeypatch.setenv("COMPILE_SECONDS", "90")
    assert compilation.budget_seconds() == 90


def _words(*pairs):
    return {"segments": [{"words": [{"word": f" {w}", "start": s, "end": s + 0.3} for w, s in pairs]}]}


def test_trim_to_speech_drops_the_source_intro_and_end_screen():
    import main
    # Captions of a real source (6-oct-2026): applause and music until 9.6 s.
    t = _words(("[प्रशंसा]", 1.9), ("[संगीत]", 2.5), ("इसमें", 9.6), ("तो", 9.9),
               ("ok", 20.0), ("bye", 40.0), ("now", 44.0), ("end", 48.0), ("[Music]", 52.0))
    data = {"shorts": [{"start": 6.0, "end": 25.3}, {"start": 30.0, "end": 60.0},
                       {"start": 19.9, "end": 30.0}]}
    main.trim_to_speech(data, t)
    a, b, c = data["shorts"]
    assert (a["start"], a["end"]) == (9.35, 25.3)          # intro music cut
    assert (b["start"], b["end"]) == (39.75, 49.8)          # silence + end screen cut
    assert (c["start"], c["end"]) == (19.9, 30.0)          # starts on speech: untouched


def test_clip_cap_follows_the_chosen_range(monkeypatch):
    import main
    long = {"shorts": [{"start": 0.0, "end": 200.0}]}
    monkeypatch.delenv("CLIP_MAX_SECONDS", raising=False)
    assert main.cap_clip_lengths(long)["shorts"][0]["end"] == main.MAX_CLIP_SECONDS  # default: under 2 min
    monkeypatch.setenv("CLIP_MAX_SECONDS", "150")
    assert main.cap_clip_lengths({"shorts": [{"start": 10.0, "end": 200.0}]})["shorts"][0]["end"] == 160.0
    monkeypatch.setenv("CLIP_MAX_SECONDS", "400")
    assert main.clip_length_cap() == main.SHORTS_CEILING_SECONDS  # never past Shorts' 3 min


def test_trim_to_speech_leaves_clips_alone_without_words():
    import main
    data = {"shorts": [{"start": 0.0, "end": 30.0}]}
    assert main.trim_to_speech(data, {"segments": []}) == {"shorts": [{"start": 0.0, "end": 30.0}]}
    assert main.trim_to_speech(None, _words(("a", 1.0))) is None


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_real_join_of_mismatched_sources(tmp_path):
    srcs = []
    for name, size, rate, secs in (("a", "1280x720", 25, 3), ("b", "1920x800", 30, 4)):
        p = str(tmp_path / f"{name}.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error",
                        "-f", "lavfi", "-i", f"testsrc=size={size}:rate={rate}:duration={secs}",
                        "-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}",
                        "-shortest", "-c:v", "libx264", "-c:a", "aac", p], check=True)
        srcs.append(p)
    durs = [compilation._duration(p) for p in srcs]
    out = str(tmp_path / "joined.mp4")
    subprocess.run(compilation.join_command(srcs, durs, out), check=True)
    probe = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate", "-of", "csv=p=0", out]).decode().strip()
    assert probe == "1920,1080,30/1"
    assert abs(compilation._duration(out) - (sum(durs) - compilation.FADE)) < 0.3
