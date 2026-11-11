"""Chacha Judge (clip_host.py) and how framed_layout draws him (11-nov-2026)."""
import json
import os
import subprocess

import pytest

import clip_host as ch
import framed_layout as fl

WORDS = [(0.8, "Toh"), (2.1, "aap"), (3.4, "HR"), (5.9, "ho?"), (9.6, "shaadi"), (12.2, "karoge?"),
         (16.5, "nahi"), (19.0, "bhai")]


def _item(**kw):
    base = {"index": 0, "laughs": [{"at": 6.0, "bubble": "HR ne resume wapas maang liya", "emoji": "fire"}],
            "score": 8, "verdict": "Uncle ko seedha out kar diya, aath number!", "question": "Aap kitne doge?"}
    base.update(kw)
    return ch.HostClip.model_validate(base)


# ------------------------------------------------------------------ the writer's answer

def test_a_laugh_is_snapped_onto_a_word_end_and_kept():
    rec = ch.clean(_item(), WORDS, 20.0)
    assert rec["laughs"] == [{"at": 5.9, "bubble": "HR ne resume wapas maang liya", "emoji": "fire"}]
    assert rec["score"] == 8 and rec["verdict"].endswith("aath number!") and rec["question"] == "Aap kitne doge?"


def test_laughs_too_close_too_early_or_off_the_words_are_dropped():
    laughs = [{"at": 0.5, "bubble": "Shuru se hi khatam", "emoji": "joy"},          # before EDGE_START
              {"at": 9.7, "bubble": "Shaadi ka sawal bhaari pad gaya", "emoji": "joy"},
              {"at": 12.0, "bubble": "Doosra bhi wahi baat hai", "emoji": "joy"},     # 2.3 s after the first
              {"at": 16.4, "bubble": "Teesra bhi aa gaya yahan", "emoji": "nope"},
              {"at": 19.5, "bubble": "Chautha kabhi nahi aata", "emoji": "joy"}]
    rec = ch.clean(_item(laughs=laughs), WORDS, 20.0)
    assert [x["at"] for x in rec["laughs"]] == [9.6, 16.5]                     # at most two, 4 s apart
    assert rec["laughs"][1]["emoji"] == "joy"                                   # an unknown emoji falls back


def test_lines_must_be_latin_and_the_right_length_and_never_name_the_comedian():
    import seo_copy
    names = seo_copy.name_pattern(seo_copy._by_names("SHAADI | STAND UP COMEDY BY RAJAT CHAUHAN"), "@PB")
    rec = ch.clean(_item(laughs=[{"at": 5.9, "bubble": "रजत ने कमाल कर दिया", "emoji": "joy"},
                                 {"at": 12.2, "bubble": "Rajat ne uncle ko dho diya 😂", "emoji": "joy"}],
                         verdict="Bas", question="Aapka faisla kya hai yaar bolo bhi abhi ke abhi"),
                   WORDS, 20.0, names)
    assert [x["bubble"] for x in rec["laughs"]] == ["bhai ne uncle ko dho diya"]  # Devanagari dropped, emoji too
    assert rec["verdict"] == "Faisla 8 number" and rec["question"] == ch.DEFAULT_QUESTION


def test_write_reads_the_models_answer(monkeypatch):
    seen = {}

    class _Models:
        def generate_content(self, **kw):
            seen["prompt"] = kw["contents"]
            return type("R", (), {"text": json.dumps({"clips": [
                {"index": 0, "laughs": [{"at": 6.0, "bubble": "HR ne resume wapas maang liya", "emoji": "fire"}],
                 "score": 9, "verdict": "Nau number, seedha out!", "question": "Aap kitne doge?"},
                {"index": 7, "laughs": [], "score": 5, "verdict": "x", "question": "y"}]})})()
    client = type("C", (), {"models": _Models()})()
    transcript = {"segments": [{"words": [{"word": w, "start": t - 0.3 + 100, "end": t + 100} for t, w in WORDS]}]}
    got = ch.write(client, "m", [{"start": 100, "end": 120, "seo_title": "HR ki shaadi"}], transcript, "@PB")
    assert list(got) == [0] and got[0]["score"] == 9 and got[0]["laughs"][0]["at"] == 5.9
    assert "ho?@5.9" in seen["prompt"] and "NEVER describe" in seen["prompt"]


def test_apply_voices_the_verdicts_and_numbers_the_series(monkeypatch, tmp_path):
    import short_kit
    monkeypatch.setenv("CLIP_HOST", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr("google.genai.Client", lambda **k: None)
    rec = ch.clean(_item(), WORDS, 20.0)
    monkeypatch.setattr(ch, "write", lambda *a, **k: {0: dict(rec), 1: dict(rec, verdict="Paanch number bas")})

    def fake_voice(client, items, job_dir, prefix):
        out = []
        for k, it in enumerate(items):
            if k == 1:
                out.append((None, 0.0))                                       # this one stays text only
                continue
            p = os.path.join(job_dir, f".{prefix}_{k + 1}.wav")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=d=2", p], check=True)
            out.append((p, 2.0))
        return out
    monkeypatch.setattr(short_kit, "voice_lines", fake_voice)
    clips = [{"start": 0, "end": 20}, {"start": 30, "end": 50}]
    takes = ch.apply(clips, {"segments": []}, str(tmp_path), ["a_clip_1.mp4", "a_clip_2.mp4"], outro_seconds=3.0)
    a, b = takes["a_clip_1.mp4"], takes["a_clip_2.mp4"]
    assert a["audio"] == "a_clip_1.take.wav" and a["voice_seconds"] == 2.0 and (tmp_path / "a_clip_1.take.wav").exists()
    assert b["audio"] is None and b["text"] == "Paanch number bas"
    assert (a["host"]["series"], b["host"]["series"]) == (1, 2)
    assert a["host"]["look"] == ch.look("a_clip_1.mp4|1")                       # the same look on a re-render
    assert clips[0]["host"]["score"] == 8 and clips[0]["ai_take"].startswith("Uncle")
    takes = ch.apply(clips[:1], {"segments": []}, str(tmp_path), ["c.mp4"])
    assert takes["c.mp4"]["host"]["series"] == 3


def test_apply_gives_way_to_the_plain_take_when_the_writer_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIP_HOST", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr("google.genai.Client", lambda **k: None)

    def down(*a, **k):
        raise RuntimeError("no credit")
    monkeypatch.setattr(ch, "write", down)
    assert ch.apply([{"start": 0, "end": 20}], {"segments": []}, str(tmp_path), ["a.mp4"]) == {}


def test_the_host_is_comedy_only_and_goes_with_the_take(monkeypatch):
    monkeypatch.setenv("CLIP_HOST", "1")
    monkeypatch.setenv("CONTENT_GENRE", "comedy")
    assert ch.enabled()
    monkeypatch.setenv("AI_TAKE", "0")
    assert not ch.enabled()
    monkeypatch.setenv("AI_TAKE", "1")
    monkeypatch.setenv("CONTENT_GENRE", "songs")
    assert not ch.enabled()


def test_looks_vary_but_repeat_for_the_same_clip():
    looks = {json.dumps(ch.look(f"clip_{i}|{i}"), sort_keys=True) for i in range(40)}
    assert len(looks) > 10 and ch.look("x|1") == ch.look("x|1")


# ------------------------------------------------------------------ drawing him

HOST = {"laughs": [{"at": 3.2, "bubble": "Uncle ki izzat ka janaza nikal gaya", "emoji": "crying"},
                   {"at": 8.4, "bubble": "HR ne resume wapas maang liya", "emoji": "fire"}],
        "score": 9, "verdict": "Nau number!", "question": "Aap kitne doge?", "series": 12,
        "look": {"fill": "#FFD23F", "ink": "#1A1A1A", "side": "right", "sound": "boom", "zoom": 1.14}}
GEO = {"w": 1080, "h": 810, "x": 0, "y": 384}


def test_the_title_steps_aside_for_each_bubble():
    spans = fl.title_spans(HOST, 12.0)
    assert spans == [(0.0, pytest.approx(3.65)), (pytest.approx(6.25), pytest.approx(8.85)),
                     (pytest.approx(11.45), 12.0)]
    assert fl.title_spans(HOST, 4.0) == [(0.0, 4.0)]                           # no room for a bubble: title stays


def test_bubbles_carry_the_hosts_name_and_line():
    ev = fl.bubble_events(HOST, GEO, 12.0)
    text = "\n".join(ev)
    assert text.count(fl.HOST_LABEL) == 2 and r"Uncle ki izzat ka\Njanaza nikal gaya" in text
    assert fl.bubble_events(HOST, GEO, 2.0) == []                              # both laughs cut by a trim


def test_the_verdict_card_shows_series_score_line_and_question():
    ev = "\n".join(fl.verdict_events(20.0, {"text": "Nau number!", "seconds": 3.0, "voice_seconds": 2.0,
                                            "host": HOST}))
    assert "PUNCHLINE ADALAT #12" in ev and "FAISLA" in ev and "9/10" in ev and "AAP KITNE DOGE?" in ev
    assert "HAMARA TAKE" not in ev and "Nau" in ev


def test_zoom_and_sound_pieces():
    z = fl.zoom_filters(GEO, 1.14, [(3.2, 4.8), (8.4, 10.0)])
    assert "crop=946:710:67:35" in z and "between(t,3.200,4.800)+between(t,8.400,10.000)" in z
    assert fl.zoom_filters(GEO, 1.14, []) == ""
    assert "adelay=3220|3220[fx0]" in fl.laugh_sound("boom", 3.22, 0)
    assert "highpass" in fl.laugh_sound("tss", 1.0, 1) and "[fx1]" in fl.laugh_sound("nope", 1.0, 1)


def _job(tmp_path, host):
    d = str(tmp_path)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=12",
                    "-f", "lavfi", "-i", "sine=f=300:d=12", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", os.path.join(d, "src.mp4")], check=True)
    fl.write_job(d, {"bg": "#2B0F3D", "outro": True, "handle": "@PB", "outro_seconds": 1.0}, 186,
                 {"v_clip_1.mp4": "Uncle ne chup kara diya"},
                 {"v_clip_1.mp4": {"text": "Nau number!", "audio": None, "voice_seconds": 0, "host": host}})
    return d


def _seconds(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", path]).decode()
    return float(out)


def test_a_real_render_with_the_host(tmp_path):
    d = _job(tmp_path, HOST)
    fl.render(os.path.join(d, "src.mp4"), os.path.join(d, "v_clip_1.mp4"))
    assert _seconds(os.path.join(d, "v_clip_1.mp4")) == pytest.approx(12 + fl.TEXT_ONLY_SECONDS + 1.0, abs=0.15)


def test_a_failed_host_layer_renders_the_plain_frame(tmp_path, monkeypatch):
    d = _job(tmp_path, HOST)
    monkeypatch.setattr(fl, "zoom_filters", lambda geo, z, windows: ",this_filter_does_not_exist" if windows else "")
    fl.render(os.path.join(d, "src.mp4"), os.path.join(d, "v_clip_1.mp4"))  # no exception
    assert os.path.getsize(os.path.join(d, "v_clip_1.mp4")) > 1000
