"""The song Shorts after the owner's notes of 10-nov-2026: the whole song (never cut inside a line), opening on its
chorus; songs in Urdu as well as English; Lyria through fal.ai when the Gemini API has no credit."""
import os
import types as pytypes

import pytest

import music_shorts as ms


def _plan(**kw):
    base = dict(title="Tera Intezaar", youtube_title="t", genre="pop", lyria_style="Pakistani sad ballad, 72 BPM",
                chorus=["c1", "c2", "c3", "c4"], verse=["v1", "v2", "v3", "v4"], pre_chorus=["p1", "p2"],
                image_prompt="x", colors=[], description="d", tags=[], hashtags=[], hook="h")
    base.update(kw)
    return ms.SongPlan(**base)


# ---------- the whole song, never cut inside a line ----------

def test_a_song_too_long_ends_after_a_phrase_with_a_breath_never_inside_one():
    # Phrases every 4 s with 0.4 s between them (no breath), except a real pause after the one ending at 80 s.
    heard, t = [], 0.4
    while t < 118:
        end = round(t + 3.6, 3)
        heard.append(("words", t, end, []))
        t = round(end + (2.0 if abs(end - 80.0) < 0.01 else 0.4), 3)
    assert any(abs(b - 80.0) < 0.01 for _x, _a, b, _w in heard)
    start, end, fade = ms.song_span([], heard, 120.0)
    assert start == 0.0 and 80.0 < end <= 82.0 and end - start <= ms.MAX_SONG and fade >= 0.5
    # No sung phrase is running when the music stops.
    assert all(b <= 80.0 + 1e-6 or a >= end for _x, a, b, _w in heard)


def test_a_line_whisper_heard_but_could_not_match_still_counts_as_singing():
    # The timed lyrics end at 30 s; Whisper also heard something at 30.5-88 s it could not match.
    lines = [("a", 1.0, 30.0)]
    heard = [("a", 1.0, 30.0, []), ("la la la la", 30.5, 88.0, []), ("b c d", 89.0, 95.0, [])]
    start, end, _fade = ms.song_span(lines, heard, 100.0)
    assert end <= 31.5              # the only breath before the limit is after 30 s: never inside 30.5-88


def test_a_song_that_fits_is_used_to_its_own_end():
    lines = [("x", 2.4, 5.0), ("y", 30.0, 60.5)]
    start, end, fade = ms.song_span(lines, [("x y z", 2.4, 5.0, [])], 64.0)
    assert (start, end) == (pytest.approx(1.8), 64.0) and fade == ms.FADE


def test_a_long_instrumental_ending_is_cut_after_the_last_sung_line():
    # 10-nov-2026: the last line ended at 48.8 s of a 65 s song; Whisper then "heard" a lone "You" at 63.6 s.
    lines = [("hold tight i need you", 0.0, 3.2), ("hold tight im holding you closer", 45.5, 48.8)]
    heard = [("hold tight i need you", 0.0, 5.8, []), ("hold tight im holding you closer", 45.5, 48.8, []),
             ("You", 63.6, 65.0, [])]
    start, end, fade = ms.song_span(lines, heard, 65.0)
    assert start == 0.0 and end == pytest.approx(48.8 + ms.TAIL) and fade == pytest.approx(ms.TAIL - 0.3)
    # A one-word chunk after the sheet is never shown as a line.
    assert len(ms._norm("You")) < 3


# ---------- chorus first ----------

def test_the_song_opens_on_its_chorus_and_closes_on_it_with_a_changed_last_line():
    p = _plan(final_line="c4 twisted")
    assert [tag for tag, _s, _x in ms.sections(p)] == ["Chorus", "Verse", "Pre-Chorus", "Final Chorus"]
    assert ms.sections(p)[-1][1] == ["c1", "c2", "c3", "c4 twisted"]
    prompt = ms.lyria_prompt(p)
    assert prompt.index("[Chorus]") < prompt.index("[Verse]") < prompt.index("[Pre-Chorus]") < prompt.index("[Final Chorus]")
    assert "OPENS ON THE CHORUS" in prompt and prompt.count("c1") == 2 and "c4 twisted" in prompt
    assert ms.sections(_plan())[-1][1] == ["c1", "c2", "c3", "c4"]          # no final line: the chorus as it is


def test_the_writer_is_told_chorus_first_complete_lines_and_original_words(monkeypatch):
    seen = {}

    def fake_ask(client, schema, prompt, model=None):
        seen["prompt"] = prompt
        return _plan()
    monkeypatch.setattr(ms.kit, "ask_json", fake_ask)
    ms.plan(None, "gym phonk", "beast mode", "a male lead singer", "A GYM song")
    p = seen["prompt"]
    assert "OPENS ON THE CHORUS" in p and "complete phrase on its own" in p
    assert "never copy, quote or rework" in p and "a workout song never gets a love hook" in p
    assert "Write the lyrics in ROMAN URDU" not in p


# ---------- Urdu ----------

def test_an_urdu_song_is_written_in_roman_urdu_and_sung_from_devanagari(monkeypatch):
    sung = ["दिल " + str(k) for k in range(10)]
    seen = {}

    def fake_ask(client, schema, prompt, model=None):
        seen.setdefault("prompt", prompt)            # the writer's brief (the editor's comes after)
        return _plan(sung=sung)
    monkeypatch.setattr(ms.kit, "ask_json", fake_ask)
    p = ms.plan(None, "Pakistani sad ballad", "judaai", "a female lead singer", lang="urdu")
    assert "ROMAN URDU" in seen["prompt"] and "DEVANAGARI" in seen["prompt"] and "South Asian woman" in seen["prompt"]
    assert "never both" in seen["prompt"] and "no religious words" in seen["prompt"]
    order = ms.sections(p)
    assert order[0][1] == ["c1", "c2", "c3", "c4"] and order[0][2] == sung[:4]          # shown / sung
    assert order[1][2] == sung[4:8] and order[2][2] == sung[8:] and order[3][2] == sung[:4]
    prompt = ms.lyria_prompt(p, "urdu")
    assert "Sung in Urdu" in prompt and "दिल 0" in prompt and "c1" not in prompt
    # With a final line, the singer gets 11 Devanagari lines and the last one ends the song.
    p2 = _plan(final_line="c4 twist", sung=sung + ["अंत"])
    assert ms._sung_ok(p2) and ms.sections(p2)[-1][2] == sung[:3] + ["अंत"]


def test_an_urdu_editor_fixes_grammar_but_never_breaks_the_song(monkeypatch):
    sung = ["x"] * 10
    writer = _plan(sung=sung, verse=["Tum keh ke bola", "v2", "v3", "v4"])
    fixed = _plan(sung=sung, verse=["Tum ne kaha", "v2", "v3", "v4"])
    asked = []

    def fake_ask(client, schema, prompt, model=None):
        asked.append(prompt)
        return [writer, fixed][len(asked) - 1]
    monkeypatch.setattr(ms.kit, "ask_json", fake_ask)
    p = ms.plan(None, "s", "t", lang="urdu")
    assert p.verse[0] == "Tum ne kaha" and "Tum keh ke bola" in asked[1] and "Urdu editor" in asked[1]
    # An edit that loses a line, or fails, leaves the writer's song as it was.
    asked.clear()
    broken = _plan(sung=sung[:9], verse=["v1", "v2", "v3"])
    monkeypatch.setattr(ms.kit, "ask_json", lambda *a, **k: (asked.append(1), [writer, broken][len(asked) - 1])[1])
    assert ms.plan(None, "s", "t", lang="urdu").verse[0] == "Tum keh ke bola"
    # English songs get no Urdu edit.
    asked.clear()
    monkeypatch.setattr(ms.kit, "ask_json", lambda *a, **k: (asked.append(1), writer)[1])
    ms.plan(None, "s", "t")
    assert len(asked) == 1


def test_an_urdu_song_whose_devanagari_lines_do_not_match_is_asked_again(monkeypatch):
    answers = [_plan(sung=["x"] * 7), _plan(sung=["x"] * 10)]
    prompts = []

    def fake_ask(client, schema, prompt, model=None):
        prompts.append(prompt)
        return answers.pop(0)
    monkeypatch.setattr(ms.kit, "ask_json", fake_ask)
    assert len(ms.plan(None, "s", "t", lang="urdu").sung) == 10
    assert "needs exactly 10" in prompts[1]
    monkeypatch.setattr(ms.kit, "ask_json", lambda *a, **k: _plan(sung=["x"]))
    with pytest.raises(RuntimeError, match="Devanagari"):
        ms.plan(None, "s", "t", lang="urdu")


def test_devanagari_is_matched_letter_for_letter_and_shown_in_roman_urdu():
    assert ms._norm("दिल, मेरा!") == ["दिल", "मेरा"]
    assert ms._norm("ज़िंदगी") == ms._norm("जिंदगी")            # the nukta Whisper may leave out
    assert ms._norm("Don't stop!") == ["dont", "stop"]
    sung = ["तेरी याद में", "दिल रोता है", "बारिश की रात"]
    shown = ["Teri yaad mein", "Dil rota hai", "Baarish ki raat"]
    heard = [("तेरी याद में", 1.0, 3.0, []), ("दिल रोता हैं", 3.5, 5.5, []), ("बारिश की रात", 6.0, 8.0, [])]
    assert [t for t, _a, _b in ms.align(sung, heard, shown)] == shown


# ---------- who sings ----------

def _no_gemini(monkeypatch):
    import ai_fallback
    monkeypatch.setattr(ai_fallback, "status", lambda: {"gemini_down": True})


def test_without_gemini_credit_lyria_sings_through_fal(tmp_path, monkeypatch):
    import talkies
    _no_gemini(monkeypatch)
    monkeypatch.setenv("MUSIC_FAL", "1")
    monkeypatch.setenv("FAL_KEY", "k")
    jobs = []
    monkeypatch.setattr(talkies, "fal_job", lambda endpoint, payload: jobs.append((endpoint, payload)) or
                        {"audio": {"url": "https://fal.media/song.mp3"}})
    monkeypatch.setattr(talkies, "_download", lambda url, out: open(out, "wb").write(b"ID3fal") and out)
    monkeypatch.setattr(ms, "free_sing", lambda *a, **k: pytest.fail("ACE-Step is the last resort"))
    out = ms.sing(None, _plan(), str(tmp_path / "s.mp3"))
    assert open(out, "rb").read() == b"ID3fal" and jobs[0][0] == "google/lyria-3.5"
    assert jobs[0][1]["prompt"].startswith("Pakistani sad ballad") and "[Chorus]" in jobs[0][1]["prompt"]
    assert ms.SUNG_BY["engine"] == "Google Lyria (through fal.ai)"


def test_a_fal_refusal_writes_another_song_and_a_fal_outage_falls_to_ace_step(tmp_path, monkeypatch):
    _no_gemini(monkeypatch)
    monkeypatch.setattr(ms, "fal_enabled", lambda: True)

    def refused(*a, **k):
        raise RuntimeError("fal said 422: content_policy_violation")
    monkeypatch.setattr(ms, "fal_sing", refused)
    with pytest.raises(RuntimeError, match="content filter"):
        ms.sing(None, _plan(), str(tmp_path / "s.mp3"))

    def down(*a, **k):
        raise RuntimeError("fal.ai has no credit left")
    monkeypatch.setattr(ms, "fal_sing", down)
    monkeypatch.setattr(ms, "free_sing", lambda p, out, lang="english": open(out, "wb").write(b"ace") and out)
    import free_song
    monkeypatch.setattr(free_song, "enabled", lambda: True)
    ms.sing(None, _plan(), str(tmp_path / "s.mp3"))
    assert ms.SUNG_BY["engine"].startswith("ACE-Step")
    monkeypatch.setattr(free_song, "enabled", lambda: False)
    with pytest.raises(RuntimeError, match="no credit"):
        ms.sing(None, _plan(), str(tmp_path / "s.mp3"))


def test_tests_never_sing_through_fal_for_real():
    assert os.environ.get("MUSIC_FAL") == "0" and not ms.fal_enabled()


# ---------- every line timed ----------

def _words(text, a, b):
    ws = text.split()
    step = (b - a) / len(ws)
    return [(w, a + k * step, a + (k + 1) * step) for k, w in enumerate(ws)]


def _chunk(text, a, b):
    return (text, a, b, _words(text, a, b))


def test_a_chorus_heard_as_one_chunk_still_gets_every_line_timed():
    lyrics = ["chai aur tum raat mein tum", "khidki pe baarish paas ho tum", "garam cup haath mein pyaar tum",
              "har dua har dhadkan bas tum", "meri chai thandi tum na aaye", "phone pe tera aakhri message"]
    heard = [_chunk(" ".join(lyrics[:4]), 0.5, 12.5), _chunk(" ".join(lyrics[4:]), 13.0, 19.0)]
    got = ms.time_lines(lyrics, heard)
    assert [t for t, _a, _b in got] == lyrics
    assert got[0][1] < 1.5 and 2.0 < got[1][1] < 5.5 and got[3][2] <= 12.8 and got[4][1] >= 12.5
    assert all(got[k][2] <= got[k + 1][1] for k in range(len(got) - 1))


def test_a_misheard_line_is_still_matched_and_an_unheard_one_is_placed_between():
    lyrics = ["thumb on the fogged glass tracing your name", "time stops moving right in this frame",
              "promise you will keep this midnight glow", "nowhere else in the world to go"]
    heard = [_chunk("oh come on the fog flies tracing your name", 1.0, 5.0),
             _chunk("promise you will keep this midnight glow", 10.0, 14.0),
             _chunk("nowhere else in the world to go", 14.5, 18.0)]
    got = ms.time_lines(lyrics, heard)
    assert [t for t, _a, _b in got] == lyrics                       # "time stops..." was not heard at all
    assert 4.0 < got[1][1] < got[1][2] <= 10.0                       # placed in the gap it was sung in


def test_the_second_chorus_matches_the_second_time_it_is_sung_and_unsung_lines_are_left_out():
    chorus = ["go ahead and count me out again", "heavy bass breaking through the pain"]
    lyrics = chorus + ["you swore i would never make it"] + chorus + ["one line nobody sang at the end"]
    heard = [_chunk(" ".join(chorus), 1.0, 7.0), _chunk("you swore i would never make it", 8.0, 11.0),
             _chunk(" ".join(chorus), 12.0, 18.0)]
    got = ms.time_lines(lyrics, heard)
    assert [t for t, _a, _b in got] == lyrics[:5]
    assert got[3][1] >= 11.5 and got[0][1] < 2.0


def test_urdu_lines_are_timed_from_devanagari_and_shown_in_roman_urdu():
    sung = ["तेरी याद में", "दिल रोता है", "बारिश की रात"]
    shown = ["Teri yaad mein", "Dil rota hai", "Baarish ki raat"]
    got = ms.time_lines(sung, [_chunk("तेरी याद में दिल रोता हैं बारिश की रात", 1.0, 7.0)], shown)
    assert [t for t, _a, _b in got] == shown
