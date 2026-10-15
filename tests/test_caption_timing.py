"""Captions follow the voice: the pauses measured in our own TTS wav, and
Whisper's word times lined up with the Roman script clause by clause."""
import math
import struct
import wave

import short_kit as kit


def _wav(path, parts, rate=24000):
    """parts: [(seconds, loud)] -> a mono 16-bit wav of tone and silence."""
    frames = bytearray()
    for secs, loud in parts:
        for i in range(int(secs * rate)):
            v = int(9000 * math.sin(2 * math.pi * 220 * i / rate)) if loud else 0
            frames += struct.pack("<h", v)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return str(path)


def test_pauses_are_found_in_the_voice(tmp_path):
    wav = _wav(tmp_path / "v.wav", [(0.3, False), (1.0, True), (0.5, False), (1.2, True), (0.4, False)])
    spans = kit.speech_spans(wav)
    assert len(spans) == 2
    assert abs(spans[0][0] - 0.3) < 0.05 and abs(spans[0][1] - 1.3) < 0.05 and abs(spans[1][0] - 1.8) < 0.05


def test_a_sentence_end_takes_the_longest_pause_and_numbers_take_longer():
    assert kit.spoken_weight("680") > kit.spoken_weight("ka") and kit.spoken_weight("AD,") == 6
    words = "Ek do teen char. Paanch chhe saat aath nau das".split()
    spans = [(0.2, 1.0), (1.1, 2.0), (2.8, 6.0)]          # the long pause is 2.0-2.8
    times = kit.word_times(words, spans, 6.2)
    assert abs(times[3][1] - 2.0) < 1e-6 and abs(times[4][0] - 2.8) < 1e-6
    assert all(b > a for a, b in times) and all(times[k][0] >= times[k - 1][0] for k in range(1, len(times)))


def test_whisper_times_line_up_clause_by_clause():
    words = "Karbala ka maidan-e-jang garam tha. Pani band tha".split()
    # Whisper wrote izafat as two words and missed nothing: units match one to one.
    heard = [("کربلا", 0.0, 0.5), ("کا", 0.5, 0.7), ("میدانِ", 0.7, 1.1), ("جنگ", 1.1, 1.5), ("گرم", 1.5, 1.9),
             ("تھا۔", 1.9, 2.3), ("پانی", 3.0, 3.4), ("بند", 3.4, 3.7), ("تھا", 3.7, 4.0)]
    t = kit.align_heard(words, heard)
    assert t[2] == (0.7, 1.5) and t[4] == (1.9, 2.3) and t[5][0] == 3.0
    # One word too many in the second sentence: the first stays exact, the second is spread inside its own time.
    heard2 = heard[:6] + [("پانی", 3.0, 3.4), ("بالکل", 3.4, 3.6), ("بند", 3.6, 3.8), ("تھا", 3.8, 4.0)]
    t = kit.align_heard(words, heard2)
    assert t[4] == (1.9, 2.3) and 3.0 <= t[5][0] < t[6][0] < t[7][0] and abs(t[7][1] - 4.0) < 1e-6
    assert kit.align_heard(words, []) is None


def test_timed_transcript_uses_the_voice_when_it_has_it(tmp_path, monkeypatch):
    monkeypatch.setenv("EXACT_CAPTIONS", "pauses")
    wav = _wav(tmp_path / "v.wav", [(0.5, False), (1.0, True), (0.6, False), (1.0, True)])
    t = kit.timed_transcript([("Pehli baat. Doosri baat", 10.0, 13.1, wav)])
    words = t["segments"][0]["words"]
    assert abs(words[0]["start"] - 10.5) < 0.05             # waits for the voice to start
    assert abs(words[1]["end"] - 11.5) < 0.05 and abs(words[2]["start"] - 12.1) < 0.05
    plain = kit.timed_transcript([("Pehli baat. Doosri baat", 10.0, 13.1)])["segments"][0]["words"]
    assert plain[0]["start"] == 10.0                        # no wav: spread by length as before
