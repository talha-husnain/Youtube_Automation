"""Songs, movie dubs and cricket (song_shorts / movie_dub / cricket_shorts /
short_kit): the parts that decide what ends up on screen, plus real renders."""
import json
import re
import shutil
import subprocess

import numpy as np
import pytest

import cricket_shorts as ck
import movie_dub as md
import short_kit as kit
import song_shorts as ss

FFMPEG = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


# ------------------------------------------------------------- short_kit

def test_timed_transcript_spreads_words_over_each_line():
    t = kit.timed_transcript([("Biryani nahi toh", 1.0, 2.0), ("", 3.0, 4.0), ("Simple!", 5.0, 5.5)])
    words = [w for s in t["segments"] for w in s["words"]]
    assert [w["word"] for w in words] == [" Biryani", " nahi", " toh", " Simple!"]
    assert words[0]["start"] == 1.0 and abs(words[2]["end"] - 2.0) < 0.01
    assert words[0]["end"] - words[0]["start"] > words[1]["end"] - words[1]["start"]  # by length


def test_blend_keeps_backgrounds_dark():
    assert kit.blend("#FFFFFF", "#000000", 0.35) == "#595959"
    assert kit.blend("not a colour", "#2B0F3D", 0.5) == "#2B0F3D"


@FFMPEG
def test_generated_render_has_voice_sfx_and_length(tmp_path, monkeypatch):
    for k in ("FRAME_OUTRO", "FRAME_HANDLE"):
        monkeypatch.delenv(k, raising=False)
    voice = str(tmp_path / "v.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=300:d=1.5",
                    "-ar", "24000", "-ac", "1", voice], check=True)
    out = str(tmp_path / "o.mp4")
    ev = [kit.dialogue(1, 0, 3, "CkTitle", r"{\pos(540,400)}Hello")]
    kit.render(out, 4.0, ["#2B0F3D", "#8B5CF6"], ev, ck.STYLES, voices=[(voice, 0.5)],
               sfx=[(kit.WHOOSH, 0.3, 2.5)])
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", out]).decode())
    assert abs(dur - 4.0) < 0.1
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                                                "stream=width,height,codec_type", "-of", "json", out]))
    assert {(s["codec_type"], s.get("width")) for s in probe["streams"]} == {("video", 1080), ("audio", None)}
    vol = subprocess.run(["ffmpeg", "-ss", "0.7", "-t", "1", "-i", out, "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    assert float(vol.split("mean_volume:")[1].split("dB")[0]) > -40


# ------------------------------------------------------------- songs

def test_pick_windows_skips_the_intro_and_takes_the_loudest():
    rate, secs = 20, 200
    rms = np.full(secs * rate, 0.2)
    rms[0:20 * rate] = 1.0            # a loud intro: never picked (first 8%)
    rms[120 * rate:160 * rate] = 0.9  # the chorus
    starts = ss.pick_windows(rms, rate, secs, 1, 35)
    assert len(starts) == 1 and 118 <= starts[0] <= 127


def test_pick_windows_two_sections_do_not_overlap_and_follow_hooks():
    rate, secs = 20, 240
    rms = np.full(secs * rate, 0.5)
    starts = ss.pick_windows(rms, rate, secs, 2, 30, hooks=[60.0, 150.0])
    assert len(starts) == 2 and abs(starts[1] - starts[0]) >= 30
    assert any(abs(s - 60) <= 7 for s in starts) and any(abs(s - 150) <= 7 for s in starts)


def test_snap_moves_to_the_loudness_rise():
    rate = 20
    rms = np.full(100 * rate, 0.1)
    rms[int(50.6 * rate):] = 1.0
    assert abs(ss.snap(rms, rate, 50.0) - 50.6) < 0.1


def test_lyric_lines_light_up_in_clip_time_and_vibe_when_none():
    lines = [ss.LyricLine(start=1.0, end=3.0, text="Dil ki baat"), ss.LyricLine(start=5, end=5.1, text="x")]
    ev = ss.lyric_events(lines, 30)
    assert len(ev) == 1 and "0:00:01.00" in ev[0] and "\\kf" in ev[0]
    sec = ss.Section(start=10, end=40, title="T", vibe="Mood line", lyrics=[])
    assert any("Mood line" in e for e in ss.section_events(sec, "Song", 30, show_lyrics=True))


def test_a_mashup_of_songs_you_do_not_own_is_refused(monkeypatch):
    monkeypatch.setenv("SONG_OWNED", "0")
    with pytest.raises(RuntimeError, match="own"):
        ss.run(["a", "b"], ".", None)


# ------------------------------------------------------------- movie dub

def _words(*items):
    return {"segments": [{"words": [{"word": f" {w}", "start": s, "end": e} for w, s, e in items]}]}


def test_lines_split_at_pauses_not_whisper_segments():
    t = _words(("kya", 10.0, 10.3), ("hua", 10.3, 10.7), ("[Music]", 11.0, 12.0),
               ("chalo", 12.0, 12.4), ("ghar", 12.4, 12.9), ("bas", 20.0, 20.5))
    assert md._lines(t, 9.0, 21.0) == [(10.0, 10.7, "kya hua"), (12.0, 12.9, "chalo ghar"),
                                       (20.0, 20.5, "bas")]


def test_schedule_never_overlaps_and_cast_gives_distinct_voices():
    starts, end = md.schedule([(0.0, 2.0), (1.5, 3.0), (6.0, 7.0)], [2.5, 1.0, 1.0])
    assert starts[0] == 0.0 and starts[1] >= 2.5 and starts[2] == 6.0 and end == 7.0
    lines = [md.DubLine(index=0, speaker="A", gender="male", emotion="", text="x"),
             md.DubLine(index=1, speaker="b", gender="female", emotion="", text="y"),
             md.DubLine(index=2, speaker="C", gender="male", emotion="", text="z")]
    v = md.cast(lines)
    assert v["A"] in kit.MALE_VOICES and v["B"] in kit.FEMALE_VOICES and v["A"] != v["C"]


@FFMPEG
def test_black_bars_are_found_and_a_full_frame_is_left_alone(tmp_path):
    boxed = str(tmp_path / "boxed.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1280x536:rate=25:duration=12",
                    "-vf", "pad=1280:720:0:92:black", "-c:v", "libx264", boxed], check=True)
    crop = md.black_bars(boxed)
    assert crop and re.match(r"crop=1280:5\d\d:0:\d+", crop)
    full = str(tmp_path / "full.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=25:duration=12",
                    "-c:v", "libx264", full], check=True)
    assert md.black_bars(full) is None


# ------------------------------------------------------------- cricket

def _story():
    return ck.Story(
        found=True, title="Final ka faisla", match_line="Asia Cup Final · Dubai · 28 Sep 2025",
        result_line="India 5 wicket se jeeta", winner=1,
        teams=[ck.Team(name="Pakistan", short="PAK", score="146", overs="19.1", color="#01411C"),
               ck.Team(name="India", short="IND", score="150/5", overs="19.4", color="#1F4E9E")],
        stars=[ck.Star(name="Tilak Varma", team="IND", figures="69* (53)", note="Final ka hero")],
        moments=[ck.Moment(label="Over 13", text="Kuldeep ne 3 wicket liye")],
        beats=[ck.Beat(scene=s, ref=0, line="line") for s in ("intro", "scores", "star", "moment", "result")],
        question="Kaun jeetna chahiye tha? Comment mein batao")


def test_every_scene_draws_and_scores_count_up_to_the_real_number():
    story = _story()
    for beat in story.beats:
        assert ck.scene_events(beat, 1.0, 4.0, story), beat.scene
    scores = " ".join(ck.scene_events(story.beats[1], 1.0, 4.0, story))
    assert "}150/5" in scores and "}146" in scores and "WINNER" in scores


def test_on_screen_text_avoids_glyphs_the_font_lacks():
    assert ck._txt("Asia Cup Final · Dubai — 2025", 60) == "Asia Cup Final | Dubai | 2025"
    assert "·" not in " ".join(ck.frame_events(_story(), 10, "@x", "T"))


def test_a_match_the_search_cannot_find_stops_with_a_clear_message():
    class _Models:
        def generate_content(self, **kw):
            return type("R", (), {"text": "NOT FOUND: no such match", "candidates": []})()
    client = type("C", (), {"models": _Models()})()
    with pytest.raises(RuntimeError, match="teams, tournament and date"):
        ck.find_story(client, "Pakistan vs Mars", "@x")
