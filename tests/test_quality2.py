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
