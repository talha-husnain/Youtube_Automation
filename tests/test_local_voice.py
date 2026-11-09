"""The local OmniVoice fallback (22-oct-2026): off unless its venv is there, one worker for a batch,
the same cloned narrator per gender, and a line the edge voice fails is read locally before Gemini."""
import json
import os

import local_voice
import short_kit as kit


def _fake_worker(seconds=2.0, fail=()):
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw))
        with open(cmd[-1], encoding="utf-8") as f:
            job = json.load(f)
        res = []
        for it in job["items"]:
            if it["text"] in fail:
                res.append({"out": it["out"], "error": "ValueError: bad"})
                continue
            open(it["out"], "wb").write(b"RIFF")
            res.append({"out": it["out"], "seconds": seconds})
        with open(cmd[-1] + ".out.json", "w", encoding="utf-8") as f:
            json.dump({"device": "cpu", "results": res}, f)
    return run, calls


def test_off_without_its_venv_or_when_switched_off(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_VOICE", "1")
    monkeypatch.setenv("OMNIVOICE_PYTHON", str(tmp_path / "missing.exe"))
    assert not local_voice.available()
    monkeypatch.setenv("OMNIVOICE_PYTHON", __file__)
    assert local_voice.available()
    monkeypatch.setenv("LOCAL_VOICE", "0")
    assert not local_voice.available()


def test_one_worker_voices_a_batch_with_one_narrator_per_gender(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_VOICE", "1")
    monkeypatch.setenv("OMNIVOICE_PYTHON", __file__)
    monkeypatch.setattr(local_voice, "VOICES_DIR", str(tmp_path / "voices"))
    run, calls = _fake_worker(fail={"bad line"})
    jobs = [("ek", str(tmp_path / "1.wav"), "male", "+12%"), ("do", str(tmp_path / "2.wav"), "female", "-4%"),
            ("bad line", str(tmp_path / "3.wav"), "male", "+0%")]
    assert local_voice.speak_many(jobs, run=run) == [2.0, 2.0, None]
    assert len(calls) == 1 and calls[0][1]["env"]["HF_HUB_OFFLINE"] == "1"
    assert local_voice.speed_of("+12%") == 1.12 and local_voice.speed_of("-4%") == 0.96


def test_a_broken_worker_hands_every_line_back(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_VOICE", "1")
    monkeypatch.setenv("OMNIVOICE_PYTHON", __file__)
    monkeypatch.setattr(local_voice, "VOICES_DIR", str(tmp_path / "voices"))

    def boom(cmd, **kw):
        raise OSError("no python")
    assert local_voice.speak_many([("ek", str(tmp_path / "1.wav"), "male", "+0%")], run=boom) == [None]


def test_a_line_the_edge_voice_fails_is_read_locally_before_gemini(monkeypatch, tmp_path):
    import ai_take
    import free_voice
    monkeypatch.setenv("VOICE_ENGINE", "edge")
    monkeypatch.setattr(free_voice, "resting", lambda: False)
    monkeypatch.setattr(free_voice, "PAUSE", 0)
    monkeypatch.setattr(free_voice, "voice_items", lambda client, items: [(it["text"], "ur-PK-AsadNeural", "+4%")
                                                                          for it in items])
    monkeypatch.setattr(free_voice, "speak", lambda text, path, voice, rate: 3.0 if text == "edge ok" else None)
    monkeypatch.setattr(local_voice, "available", lambda: True)
    local = []
    monkeypatch.setattr(local_voice, "speak_many", lambda jobs: local.extend(jobs) or
                        [4.0 if t == "local ok" else None for t, _p, _g, _r in jobs])
    paid = []
    monkeypatch.setattr(ai_take, "speak", lambda client, text, path, voice, style, **kw: paid.append(text) or 5.0)
    items = [{"text": t, "voice": "Charon"} for t in ("edge ok", "local ok", "nobody")]
    got = kit.voice_lines(None, items, str(tmp_path), "v")
    assert [s for _p, s in got] == [3.0, 4.0, 5.0]
    assert [t for t, *_ in local] == ["local ok", "nobody"] and paid == ["nobody"]


def test_omni_engine_skips_the_edge_voice(monkeypatch, tmp_path):
    import ai_take
    import free_voice
    monkeypatch.setenv("VOICE_ENGINE", "omni")
    monkeypatch.setattr(free_voice, "voice_items", lambda client, items: [(it["text"], "ur-PK-AsadNeural", "+4%")
                                                                          for it in items])
    monkeypatch.setattr(free_voice, "speak", lambda *a: (_ for _ in ()).throw(AssertionError("edge used")))
    monkeypatch.setattr(local_voice, "available", lambda: True)
    monkeypatch.setattr(local_voice, "speak_many", lambda jobs: [2.5] * len(jobs))
    monkeypatch.setattr(ai_take, "speak", lambda *a, **k: (_ for _ in ()).throw(AssertionError("gemini used")))
    got = kit.voice_lines(None, [{"text": "ek"}, {"text": "do"}], str(tmp_path), "v")
    assert [s for _p, s in got] == [2.5, 2.5]


def test_quran_translation_lines_use_the_local_voice_before_gemini(monkeypatch, tmp_path):
    import ai_take
    import free_voice
    import quran_videos as qv
    monkeypatch.setenv("VOICE_ENGINE", "edge")
    monkeypatch.setattr(free_voice, "resting", lambda: False)
    monkeypatch.setattr(free_voice, "PAUSE", 0)
    monkeypatch.setattr(free_voice, "speak", lambda text, path, voice, rate: 2.0 if text == "edge" else None)
    monkeypatch.setattr(local_voice, "available", lambda: True)
    monkeypatch.setattr(local_voice, "speak_many", lambda jobs: [3.0 if t == "local" else None for t, *_ in jobs])
    paid = []
    monkeypatch.setattr(ai_take, "speak", lambda client, text, path, voice, style, **kw: paid.append(text) or 4.0)
    got = qv.voice_translations(object(), ["edge", "local", "paid"], str(tmp_path), "urdu", log=lambda *a: None, wait=0)
    assert [s for _p, s in got] == [2.0, 3.0, 4.0] and paid == ["paid"]


def test_a_long_batch_goes_to_gemini_instead_of_holding_the_loop(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_VOICE", "1")
    monkeypatch.setenv("OMNIVOICE_PYTHON", __file__)
    monkeypatch.setattr(local_voice, "MAX_CHARS", 10)
    run, calls = _fake_worker()
    assert local_voice.speak_many([("a" * 11, str(tmp_path / "1.wav"), "male", "+0%")], run=run) == [None]
    assert calls == []


def test_the_worker_reads_the_model_from_the_project_cache(monkeypatch, tmp_path):
    """4-nov-2026: the user-profile Hugging Face cache lost the model; the cache now sits in oss/hf."""
    monkeypatch.setenv("LOCAL_VOICE", "1")
    monkeypatch.setenv("OMNIVOICE_PYTHON", __file__)
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.setattr(local_voice, "VOICES_DIR", str(tmp_path / "voices"))
    jobs = [("ek", str(tmp_path / "1.wav"), "male", "+0%")]
    monkeypatch.setattr(local_voice, "HF_DIR", str(tmp_path / "hf"))
    run, calls = _fake_worker()
    local_voice.speak_many(jobs, run=run)
    assert "HF_HOME" not in calls[-1][1]["env"]                     # folder missing: the default cache
    (tmp_path / "hf").mkdir()
    local_voice.speak_many(jobs, run=run)
    assert calls[-1][1]["env"]["HF_HOME"] == str(tmp_path / "hf")
    monkeypatch.setenv("HF_HOME", "X:/own")                           # the owner's own setting wins
    local_voice.speak_many(jobs, run=run)
    assert calls[-1][1]["env"]["HF_HOME"] == "X:/own"
