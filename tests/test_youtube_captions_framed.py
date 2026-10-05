"""YouTube captions as the transcript, and the FRAMED layout geometry."""
import json

import framed_layout as fl
import youtube_captions as yc


AUTO_TRACK = {"events": [
    {"tStartMs": 240, "dDurationMs": 4760, "segs": [
        {"utf8": "please"}, {"utf8": " welcome", "tOffsetMs": 400},
        {"utf8": " naman", "tOffsetMs": 959}]},
    {"tStartMs": 5110, "segs": [{"utf8": "\n"}]},  # rolling-caption line break
    {"tStartMs": 5120, "dDurationMs": 2000, "segs": [
        {"utf8": "i"}, {"utf8": " just", "tOffsetMs": 320}]},
]}

MANUAL_TRACK = {"events": [
    {"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "aa bbbb"}]},
]}


def test_auto_track_keeps_word_offsets():
    t = yc.json3_to_transcript(AUTO_TRACK, "hi")
    assert t["language"] == "hi"
    assert [s["text"] for s in t["segments"]] == ["please welcome naman", "i just"]
    words = t["segments"][0]["words"]
    assert [w["start"] for w in words] == [0.24, 0.64, 1.199]
    # Each word ends where the next starts; the last one gets a natural length,
    # not the rest of the (overlapping) caption line.
    assert words[0]["end"] == 0.64
    assert words[-1]["end"] <= 1.199 + 0.8 + 1e-9


def test_words_never_end_before_they_start():
    t = yc.json3_to_transcript(AUTO_TRACK, "hi")
    assert all(w["end"] > w["start"] for s in t["segments"] for w in s["words"])


def test_manual_track_spreads_words_over_the_line_by_length():
    t = yc.json3_to_transcript(json.dumps(MANUAL_TRACK), "en")
    words = t["segments"][0]["words"]
    assert words[0]["start"] == 1.0 and words[-1]["end"] == 3.0
    assert words[0]["end"] - words[0]["start"] < words[1]["end"] - words[1]["start"]


def test_max_seconds_cuts_the_transcript():
    t = yc.json3_to_transcript(AUTO_TRACK, "hi", max_seconds=5)
    assert len(t["segments"]) == 1


def test_fetch_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("YT_CAPTIONS", "0")
    assert yc.fetch("https://www.youtube.com/watch?v=x") is None


def test_classic_geometry_on_1080p():
    g = fl.geometry(1920, 1080, "classic", 1.12)
    assert (g["w"], g["h"]) == (1080, 810)
    assert g["y"] == 384
    # Most of the vertical trim comes off the bottom (burned-in subtitles).
    assert g["crop_y"] < (1080 - g["crop_h"]) - g["crop_y"]
    # The captions hang below the picture, inside generate_ass's clamp.
    assert (g["y"] + g["h"]) * 288 / 1920 < fl.caption_margin_units(g) <= 270


def test_portrait_source_is_never_widened():
    g = fl.geometry(1080, 1920, "classic", 1.0)
    assert g["crop_w"] <= 1080 and g["h"] <= int(1920 * 0.62)


def test_settings_fall_back_to_the_job_file(tmp_path, monkeypatch):
    for k in ("FRAME_BG_COLOR", "FRAME_CROP", "FRAME_ZOOM", "FRAME_TITLE"):
        monkeypatch.delenv(k, raising=False)
    fl.write_job(str(tmp_path), {"bg": "#7B1E3A", "crop": "square", "zoom": 1.25, "title": False},
                 200, {"x_clip_1.mp4": "Title"})
    cfg = fl.settings(str(tmp_path))
    assert cfg == {"bg": "#7B1E3A", "crop": "square", "zoom": 1.25, "title": False}
    assert fl.job_caption_margin(str(tmp_path)) == 200
    assert fl.job_caption_margin(str(tmp_path / "missing")) is None


def test_bad_env_values_use_defaults(monkeypatch):
    monkeypatch.setenv("FRAME_BG_COLOR", "red;drawtext")
    monkeypatch.setenv("FRAME_CROP", "nope")
    monkeypatch.setenv("FRAME_ZOOM", "9")
    cfg = fl.settings()
    assert cfg["bg"] == fl.DEFAULT_BG and cfg["crop"] == "classic" and cfg["zoom"] == 1.5


def test_title_is_cleaned_for_ass():
    assert fl.clean_title("Big {\\b1}news #shorts #viral") == "Big (b1)news"


def test_track_choice_prefers_spoken_language_then_its_asr():
    info = {"language": "hi", "subtitles": {"en": [1]},
            "automatic_captions": {"hi-orig": [1], "fr": [1]}}
    assert yc.choose_track(info) == ("auto", "hi-orig")
    info["subtitles"]["hi"] = [1]
    assert yc.choose_track(info) == ("manual", "hi")
    assert yc.choose_track({"automatic_captions": {"fr": [1]}}) == (None, None)


def test_section_command_seeks_each_stream_and_maps_video_plus_audio():
    import section_fetch as sf
    fmts = [{"url": "https://v", "http_headers": {"User-Agent": "UA"}}, {"url": "https://a"}]
    cmd = sf._ffmpeg_cmd(fmts, 100.0, 140.5, "out.mp4")
    assert cmd.count("-ss") == 2 and cmd[cmd.index("-t") + 1] == "40.500"
    assert ["-map", "0:v:0"] == cmd[cmd.index("-map"):cmd.index("-map") + 2]
    assert "User-Agent: UA\r\n" in cmd and cmd[-1] == "out.mp4"


def test_section_fetch_off_or_empty_means_full_download(monkeypatch):
    import section_fetch as sf
    assert sf.fetch("u", [], ".") is None
    monkeypatch.setenv("DOWNLOAD_SECTIONS", "0")
    assert sf.fetch("u", [(0, 10)], ".") is None


def _hi_transcript():
    words = [{"word": " मैंने", "start": 1.0, "end": 1.4}, {"word": " कहा", "start": 1.4, "end": 2.0}]
    return {"language": "hi", "segments": [
        {"start": 1.0, "end": 2.0, "text": "मैंने कहा", "words": words}]}


def test_roman_keeps_each_word_timing(monkeypatch):
    import caption_script as cs
    monkeypatch.setenv("CAPTION_SCRIPT", "roman")
    monkeypatch.setattr(cs, "_client", lambda: (object(), "gemini-x"))
    monkeypatch.setattr(cs, "_ask", lambda c, m, p: {"words": ["main ne", "kaha"], "title": "Kya hua"})
    t = _hi_transcript()
    clips = [{"start": 0.0, "end": 3.0, "video_title_for_youtube_short": "क्या हुआ"}]
    assert cs.apply(t, clips) == "roman"
    w = t["segments"][0]["words"]
    assert [x["word"] for x in w] == [" main ne", " kaha"] and w[1]["start"] == 1.4
    assert clips[0]["video_title_for_youtube_short"] == "Kya hua"


def test_roman_count_mismatch_keeps_original(monkeypatch):
    import caption_script as cs
    monkeypatch.setenv("CAPTION_SCRIPT", "roman")
    monkeypatch.setattr(cs, "_client", lambda: (object(), "gemini-x"))
    monkeypatch.setattr(cs, "_ask", lambda c, m, p: {"words": ["only one"], "title": "x"})
    t = _hi_transcript()
    cs.apply(t, [{"start": 0.0, "end": 3.0}])
    assert t["segments"][0]["words"][0]["word"] == " मैंने"


def test_latin_script_needs_no_call(monkeypatch):
    import caption_script as cs
    monkeypatch.setenv("CAPTION_SCRIPT", "roman")
    monkeypatch.setattr(cs, "_client", lambda: (_ for _ in ()).throw(AssertionError("called")))
    t = {"language": "en", "segments": [{"start": 0, "end": 1, "text": "hello there",
                                          "words": [{"word": " hello", "start": 0, "end": 1}]}]}
    assert cs.apply(t, [{"start": 0, "end": 1}]) == "original"


def test_english_spreads_words_over_the_line(monkeypatch):
    import caption_script as cs
    monkeypatch.setenv("CAPTION_SCRIPT", "english")
    monkeypatch.setattr(cs, "_client", lambda: (object(), "gemini-x"))
    monkeypatch.setattr(cs, "_ask", lambda c, m, p: {"lines": ["I said"], "title": "What happened"})
    t = _hi_transcript()
    cs.apply(t, [{"start": 0.0, "end": 3.0}])
    w = t["segments"][0]["words"]
    assert [x["word"] for x in w] == [" I", " said"] and w[0]["start"] == 1.0 and w[-1]["end"] == 2.0


def test_clips_are_capped_under_two_minutes():
    import main
    data = {"shorts": [{"start": 10.0, "end": 200.0}, {"start": 0.0, "end": 45.0}]}
    main.cap_clip_lengths(data)
    assert data["shorts"][0]["end"] - data["shorts"][0]["start"] < 120
    assert data["shorts"][1]["end"] == 45.0


def test_emoji_dropped_from_burned_title():
    assert fl.clean_title("Raat 4 baje police ne roka! \U0001F631\U0001F92B") == "Raat 4 baje police ne roka!"


def test_roman_falls_back_to_lines_when_words_do_not_align(monkeypatch):
    import caption_script as cs
    monkeypatch.setenv("CAPTION_SCRIPT", "roman")
    monkeypatch.setattr(cs, "_client", lambda: (object(), "gemini-x"))

    def fake(c, m, prompt):
        if "Items (JSON)" in prompt:
            return {"words": ["wrong count"], "title": "x"}
        return {"lines": ["main ne kaha"], "title": "Kya hua"}
    monkeypatch.setattr(cs, "_ask", fake)
    t = _hi_transcript()
    clips = [{"start": 0.0, "end": 3.0}]
    cs.apply(t, clips)
    w = t["segments"][0]["words"]
    assert "".join(x["word"] for x in w).strip() == "main ne kaha"
    assert w[0]["start"] == 1.0 and abs(w[-1]["end"] - 2.0) < 1e-6
