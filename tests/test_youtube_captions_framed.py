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
    for k in ("FRAME_BG_COLOR", "FRAME_CROP", "FRAME_ZOOM", "FRAME_TITLE",
              "FRAME_OUTRO", "FRAME_HANDLE", "FRAME_OUTRO_SECONDS"):
        monkeypatch.delenv(k, raising=False)
    fl.write_job(str(tmp_path), {"bg": "#7B1E3A", "crop": "square", "zoom": 1.25, "title": False,
                                 "outro": False, "handle": "@PunchlineBazaar"},
                 200, {"x_clip_1.mp4": "Title"})
    cfg = fl.settings(str(tmp_path))
    assert cfg == {"bg": "#7B1E3A", "crop": "square", "zoom": 1.25, "title": False,
                   "outro": False, "handle": "@PunchlineBazaar", "outro_seconds": 3.0}
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


def test_handle_is_cleaned():
    assert fl.clean_handle("PunchlineBazaar") == "@PunchlineBazaar"
    assert fl.clean_handle("{b1}bad'name") == "@b1badname"
    assert fl.clean_handle("Punchline Bazaar") == "Punchline Bazaar"
    assert len(fl.clean_handle("x" * 80)) <= 31


def test_overlay_has_title_handle_and_end_card(tmp_path):
    p = tmp_path / "o.ass"
    geo = fl.geometry(1920, 1080)
    fl.overlay_ass(str(p), geo, "#2B0F3D", 40.0, title="Hello", handle="@PunchlineBazaar", outro=True)
    text = p.read_text(encoding="utf-8")
    assert "Hello" in text and "FOLLOW" in text and "FOR MORE" in text
    assert text.count("@PunchlineBazaar") == 2  # top tag + the end card button
    # The end card starts where the clip ends and lasts OUTRO_SECONDS (3 s).
    assert "0:00:40.00,0:00:43.00,OutroBig" in text
    assert "\p1" in text  # the button and rings are drawn shapes


def test_end_card_length_is_clamped(monkeypatch):
    monkeypatch.setenv("FRAME_OUTRO_SECONDS", "9")
    assert fl.settings()["outro_seconds"] == 3.0
    monkeypatch.setenv("FRAME_OUTRO_SECONDS", "0.2")
    assert fl.settings()["outro_seconds"] == 1.0


def test_end_card_events_stay_inside_the_card():
    ev = fl.end_card_events(10.0, 1.0, "@x", "#2B0F3D")
    ends = [e.split(",")[2] for e in ev]
    assert all(e <= "0:00:11.00" for e in ends)


def test_no_end_card_when_off(tmp_path):
    p = tmp_path / "o.ass"
    fl.overlay_ass(str(p), fl.geometry(1920, 1080), "#000000", 10.0, title="Hi")
    assert "FOLLOW" not in p.read_text(encoding="utf-8")


def test_seo_hashtags_cleaned_deduped_and_lead_with_shorts():
    import seo_copy
    tags = seo_copy._clean_tags(["comedy", "#Comedy", "#stand up", "", "#namanjain"], hashtag=True)
    assert tags[0] == "#shorts" and "#standup" in tags and len(tags) == 4


def test_seo_description_is_assembled_in_order():
    import seo_copy
    d = seo_copy.build_description(
        "Hook here?", "Para one.\nPara two.\n\n\nPara three. #stray #tags",
        "@PunchlineBazaar", ["#shorts", "#comedy", "#funny", "#a", "#b", "#c"])
    blocks = d.split("\n\n")
    assert blocks[0] == "Hook here?" and blocks[1:4] == ["Para one.", "Para two.", "Para three."]
    assert blocks[4] == "Follow @PunchlineBazaar for daily clips"
    assert blocks[5] == "#shorts #comedy #funny #a #b"
    assert "Credit" not in d


def test_seo_one_block_body_is_split_into_three_paragraphs():
    import seo_copy
    body = " ".join(f"Sentence number {i} has a few more words in it." for i in range(9))
    paras = seo_copy._paragraphs(body).split("\n\n")
    assert len(paras) == 3 and " ".join(paras) == body
    assert seo_copy._paragraphs("Short. Body. Here.") == "Short. Body. Here."


def test_seo_creator_name_is_found_and_scrubbed():
    import seo_copy
    assert seo_copy._by_names("LADKI_KA_CHAKKAR | STAND UP COMEDY BY NAMAN JAIN") == ["NAMAN JAIN"]
    p = seo_copy.name_pattern(["Naman Jain", "", "Punchline Bazaar"], "@PunchlineBazaar")
    for hit in ("Naman Jain ne bataya", "#NamanJain", "namanjain comedy", "Naman ka scene"):
        assert p.search(hit), hit
    for miss in ("Jain sahab", "Punchline Bazaar", "namaste", "Follow @PunchlineBazaar"):
        assert not p.search(miss), miss
    assert seo_copy._scrub("Naman Jain ne bataya", p) == "comedian ne bataya"
    assert seo_copy.name_pattern(["", "PunchlineBazaar"], "@PunchlineBazaar") is None


def test_seo_word_count_counts_roman_urdu_words():
    import seo_copy
    assert seo_copy.word_count("Naman Jain ne bataya, kya scene tha! Don't miss.") == 9


def test_seo_retry_prefers_latin_everyday_long_copy():
    import seo_copy

    def item(body, title="Goa mein panga #shorts"):
        return seo_copy.ClipSEO(index=0, on_screen_title="t", hook="h", summary="s",
                                youtube_title=title, description_hook="hook", description_body=body,
                                creator="", hashtags=["#shorts"], tags=[], tiktok_caption="c")
    long_body = "word " * 160
    good = seo_copy._quality(item(long_body), latin=True)
    assert all(good[:2])
    assert not seo_copy._quality(item("word " * 20), latin=True)[1]
    assert not seo_copy._quality(item(long_body + "राय"), latin=True)[0]
    assert not seo_copy._quality(item(long_body, "Ladai ka apratyashit ant"), latin=True)[0]
    assert seo_copy._quality(item(long_body + "राय"), latin=False)[0]
    assert good > seo_copy._quality(item("word " * 20), latin=True)


def test_seo_copy_off_or_without_key_changes_nothing(monkeypatch):
    import seo_copy
    clips = [{"start": 0, "end": 10, "video_title_for_youtube_short": "x"}]
    monkeypatch.setenv("SEO_COPY", "0")
    assert seo_copy.apply(clips, None) == 0
    monkeypatch.setenv("SEO_COPY", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert seo_copy.apply(clips, None) == 0 and "seo_title" not in clips[0]


def test_section_fetch_retries_with_fresh_links(monkeypatch, tmp_path):
    import types as _t
    import section_fetch as sf
    resolves = []

    def fake_resolve(url):
        resolves.append(url)
        return "T", [{"url": f"https://v{len(resolves)}"}]

    def fake_run(cmd, **kw):
        out = cmd[-1]
        # The first set of links is refused for section 2 only.
        if "https://v1" in cmd and out.endswith("section_2.mp4"):
            return _t.SimpleNamespace(returncode=1, stderr="403 Forbidden")
        open(out, "wb").write(b"x" * (sf.MIN_CUT_BYTES + 1))
        return _t.SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(sf, "resolve", fake_resolve)
    monkeypatch.setattr(sf.subprocess, "run", fake_run)
    title, got = sf.fetch("u", [(0, 10), (20, 30)], str(tmp_path))
    assert title == "T" and sorted(got) == [0, 1] and len(resolves) == 2
