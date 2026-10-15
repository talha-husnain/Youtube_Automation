"""The free voice (free_voice.py): Roman Urdu goes through Urdu script, its
word times reach the captions, and Gemini voices any line it fails."""
import json
import math
import struct
import wave

import free_voice as fv
import short_kit as kit


def _wav(path, secs=1.0, rate=24000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 9))) for i in range(int(secs * rate))))
    return secs


def test_roman_lines_are_read_in_urdu_script_english_as_is(monkeypatch):
    monkeypatch.setattr(kit, "ask_json", lambda c, schema, p, model=None: fv.Converted(lines=["0: پہلی لائن", "دوسری"]))
    items = [{"text": "pehli line", "voice": "Charon", "style": "calm documentary"},
             {"text": "doosri", "voice": "Kore"},
             {"text": "An English line", "voice": "Puck", "language": "English"}]
    got = fv.voice_items(None, items)
    assert got[0] == ("پہلی لائن", "ur-PK-AsadNeural", "-4%")
    assert got[1][:2] == ("دوسری", "ur-PK-UzmaNeural")
    assert got[2][:2] == ("An English line", "en-US-GuyNeural")
    # A conversion that loses a line: those lines go to Gemini, English still free.
    monkeypatch.setattr(kit, "ask_json", lambda c, schema, p, model=None: fv.Converted(lines=["only one"]))
    got = fv.voice_items(None, items)
    assert got[0] is None and got[1] is None and got[2][1] == "en-US-GuyNeural"


def test_a_line_the_free_voice_fails_is_voiced_by_gemini(monkeypatch, tmp_path):
    import ai_take
    monkeypatch.setenv("VOICE_ENGINE", "edge")
    monkeypatch.setattr(fv, "voice_items", lambda client, items: [("a", "ur-PK-AsadNeural", "+0%"),
                                                                 ("b", "ur-PK-AsadNeural", "+0%")])

    def free(text, path, voice, rate="+0%"):
        if text == "b":
            return None
        _wav(path)
        json.dump([["a", 0.1, 0.5]], open(path + ".words.json", "w", encoding="utf-8"))
        return 1.0
    monkeypatch.setattr(fv, "speak", free)
    gemini = []

    def speak(client, text, path, voice, style=None, language="Roman Urdu"):
        gemini.append(text)
        return _wav(path, 2.0)
    monkeypatch.setattr(ai_take, "speak", speak)
    said = kit.voice_lines(None, [{"text": "line a"}, {"text": "line b"}], str(tmp_path), "t")
    assert [s for _p, s in said] == [1.0, 2.0] and gemini == ["line b"]
    assert fv.heard_words(said[0][0]) == [("a", 0.1, 0.5)] and fv.heard_words(said[1][0]) == []
    monkeypatch.setenv("VOICE_ENGINE", "gemini")
    gemini.clear()
    kit.voice_lines(None, [{"text": "line c"}], str(tmp_path), "g")
    assert gemini == ["line c"]


def test_captions_take_the_free_voices_own_word_times(tmp_path, monkeypatch):
    monkeypatch.setenv("EXACT_CAPTIONS", "whisper")
    wav = str(tmp_path / "v.wav")
    _wav(wav, 3.0)
    json.dump([["پہلی", 0.2, 0.6], ["بات۔", 0.6, 1.0], ["دوسری", 1.8, 2.3], ["بات", 2.3, 2.8]],
              open(wav + ".words.json", "w", encoding="utf-8"))
    t = kit.line_word_times("Pehli baat. Doosri baat", wav, 3.0)
    assert t == [(0.2, 0.6), (0.6, 1.0), (1.8, 2.3), (2.3, 2.8)]


def test_pace_follows_the_style():
    assert fv.rate_for("like an excited Pakistani cricket commentator, fast and energetic") == "+12%"
    assert fv.rate_for("calm, captivating history documentary narrator") == "-4%"
    assert fv.rate_for(None) == "+4%"
