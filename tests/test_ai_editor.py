"""ai_editor.py: the Studio's prompt editor. Time maps, quotes, plan checks, the render, undo and uploads."""
import json
import os
import shutil
import subprocess
import uuid

import pytest

import ai_editor as ae
import studio

HAVE_FFMPEG = bool(shutil.which("ffmpeg"))


def _w(word, a, b):
    return {"word": " " + word, "start": a, "end": b}


WORDS = [_w("Shaheen", 0.5, 1.0), _w("ne", 1.0, 1.2), _w("sirf", 1.3, 1.6), _w("31", 1.7, 2.0), _w("runs", 2.0, 2.4),
         _w("diye", 2.5, 2.9), _w("aur", 4.0, 4.2), _w("teen", 4.3, 4.6), _w("wicket", 4.6, 5.1), _w("liye.", 5.1, 5.5)]


def test_timeline_maps_both_ways_through_cuts_and_speed():
    tl = ae.Timeline([(0.0, 2.0), (3.0, 6.0)], speed=2.0)
    assert tl.duration == pytest.approx(2.5)
    assert tl.out(1.0) == pytest.approx(0.5) and tl.out(2.5) is None and tl.out(4.0) == pytest.approx(1.5)
    assert tl.base(1.5) == pytest.approx(4.0)
    assert tl.base_ranges(0.5, 2.0) == [(1.0, 2.0), (3.0, 5.0)]      # the cut part in between is skipped
    assert tl.out_ranges(1.5, 3.5) == [(0.75, 1.25)]


def test_quotes_are_found_exactly_or_nearly_and_cuts_never_split_a_word():
    words = [{"word": w["word"].strip(), "start": w["start"], "end": w["end"]} for w in WORDS]
    assert ae.find_quote(words, "sirf 31 runs") == (2, 4)
    assert ae.find_quote(words, "Teen wickets liye!") == (7, 9)       # one word spelt differently
    assert ae.find_quote(words, "kuch aur hi baat") is None
    # A cut starting in the middle of "sirf" (mostly cut) moves before it; ending inside "diye" (mostly kept) moves before it.
    assert ae._snap(1.35, words, "start") == pytest.approx(1.24)
    assert ae._snap(2.6, words, "end") == pytest.approx(2.44)


def _ctx(**kw):
    return {"job_id": "x", "path": "", "channel": "c1", "channel_name": "Cricket", "kind": "cricket", "genre": "cricket",
            "upload": False, "on_youtube": False, "video_id": None, "state": "waiting", "topic": "Shaheen",
            "remakable": True, "framed": True, **kw}


def _state(stem=None):
    return {"base": {"seconds": 8.0, "w": 1080, "h": 1920, "fps": 30, "audio": True, "captions": True, "stem": stem,
                     "meta": {"transcript": {"segments": [{"words": WORDS}]}, "short": {}}},
            "revisions": [], "current": 0}


def test_the_plan_is_checked_and_turned_into_base_time_records():
    tl = ae.Timeline([(0.0, 8.0)])
    words = ae.words_now(WORDS, tl)
    p = ae.Plan(summary="ok", ops=[
        ae.Op(op="cut", quote="sirf 31 runs"),
        ae.Op(op="text", text="31 RUNS!"),                                 # no time: the first 3 s
        ae.Op(op="zoom", start=4.0, end=5.5, amount=9),                    # clamped
        ae.Op(op="caption_style", value="color=yellow; size=1.3"),
        ae.Op(op="music", value="off"),                                    # no stem: refused with a reason
        ae.Op(op="dance", value="x"),                                      # not an operation
        ae.Op(op="title", text="Naya title"),
        ae.Op(op="remake", text="hook zyada strong")])
    ops, details, remake, notes = ae.resolve(p, _ctx(), _state(), tl, words)
    kinds = [o["op"] for o in ops]
    assert kinds == ["cut", "text", "zoom", "caption_style"]
    assert ops[0]["ranges"][0][0] == pytest.approx(1.24) and ops[0]["ranges"][0][1] == pytest.approx(2.46)
    assert ops[1]["ranges"] == [[0.0, 3.0]] and ops[2]["amount"] == 1.8
    assert details == {"title": {"text": "Naya title", "value": ""}} and remake == "hook zyada strong"
    assert any("mixed into its sound" in n for n in notes) and any("'dance'" in n for n in notes)


def test_a_video_already_on_youtube_only_takes_details():
    tl = ae.Timeline([(0.0, 8.0)])
    p = ae.Plan(summary="ok", ops=[ae.Op(op="cut", start=0, end=2), ae.Op(op="title", value="better")])
    ops, details, _remake, notes = ae.resolve(p, _ctx(on_youtube=True), _state(), tl, ae.words_now(WORDS, tl))
    assert ops == [] and "title" in details and any("already on YouTube" in n for n in notes)


def test_edits_fold_into_one_render_spec():
    ops = [{"op": "cut", "ranges": [[0.0, 0.5]]}, {"op": "look", "value": "darker", "amount": 0.5},
           {"op": "look", "value": "brighter", "amount": 0.4}, {"op": "look", "value": "warm", "amount": 0.5},
           {"op": "caption_style", "value": "color=yellow"}, {"op": "caption_style", "value": "size=1.5; position=middle"},
           {"op": "music", "value": "sad piano", "amount": -3}, {"op": "volume", "value": "all", "amount": 4},
           {"op": "tighten", "amount": 0.3}]
    spec = ae.compile_ops(ops, 8.0, WORDS, {"captions": True})
    assert spec["look"] == {"brighter": 0.4, "warm": 0.5}                 # brighter replaced darker
    assert spec["style"] == {"color": "#FFE500", "size": 1.5, "position": "middle"}
    assert spec["music"]["value"] == "sad piano" and spec["volume"]["all"] == 4
    # 0-0.5 cut, and the 1.1 s pause between "diye" and "aur" shortened to 0.3 s.
    assert spec["keep"][0][0] == pytest.approx(0.5)
    assert any(a == pytest.approx(3.05) for a, _b in spec["keep"]) or any(b == pytest.approx(3.05) for _a, b in spec["keep"])
    assert sum(b - a for a, b in spec["keep"]) == pytest.approx(8.0 - 0.5 - 0.8, abs=0.01)


def _make_job(tmp_path, seconds=8.0):
    job_id = str(uuid.uuid4())
    path = os.path.join(studio.OUTPUT_DIR, job_id)
    os.makedirs(path)
    base = "Cricket_2026-10-29_120000"
    clean = os.path.join(path, f"{base}_clip_1.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=540x960:rate=30:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}", "-c:v", "libx264", "-pix_fmt",
                    "yuv420p", "-c:a", "aac", "-shortest", clean], check=True)
    shutil.copy(clean, os.path.join(path, f"subtitled_1700000000_{base}_clip_1.mp4"))
    data = {"genre": "cricket", "output_format": "framed",
            "transcript": {"segments": [{"start": 0.5, "end": 2.9, "text": "Shaheen ne sirf 31 runs diye",
                                         "words": WORDS[:6]},
                                        {"start": 4.0, "end": 5.5, "text": "aur teen wicket liye.", "words": WORDS[6:]}]},
            "shorts": [{"seo_title": "Shaheen ka spell", "seo_description": "d", "seo_tags": ["a"], "start": 0.0,
                        "end": seconds}]}
    with open(os.path.join(path, f"{base}_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)
    return job_id, path, base


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_a_real_edit_renders_publishes_and_undoes(tmp_path, monkeypatch):
    job_id, path, base = _make_job(tmp_path)
    plans = [ae.Plan(summary="Cut 31 runs, zoom, yellow captions", ops=[
        ae.Op(op="cut", quote="sirf 31 runs"), ae.Op(op="zoom", quote="teen wicket", amount=1.3),
        ae.Op(op="text", text="WOW", value="top"), ae.Op(op="caption_style", value="color=yellow"),
        ae.Op(op="title", value="better")])]
    monkeypatch.setattr(ae, "plan", lambda *a, **k: plans[0])
    monkeypatch.setattr(ae, "check", lambda *a, **k: (True, []))
    import script_craft
    monkeypatch.setattr(script_craft, "pick_title", lambda client, title, facts, **k: "Shaheen ne 3 wicket kaise liye?")
    result = ae.apply(job_id, "31 runs wala hissa kaato, wicket pe zoom, captions peele", client=object(), log=lambda *a: None)
    assert result["ok"] and result["n"] == 1 and result["details"] == ["title"]
    served = studio.served(path)
    assert os.path.basename(served).startswith("subtitled_") and "_ai1_" in os.path.basename(served)
    assert studio.duration(served) == pytest.approx(8.0 - 1.22, abs=0.15)
    data = studio._read(path)
    assert data["shorts"][0]["seo_title"] == "Shaheen ne 3 wicket kaise liye?"
    said = [w["word"].strip() for s in data["transcript"]["segments"] for w in s["words"]]
    assert "31" not in said and "teen" in said                          # the cut words are gone from the captions
    st = ae.status(job_id)
    assert st["current"] == 1 and st["revisions"][0]["summary"].startswith("Cut 31 runs")
    # Undo: the original is what plays again, with its own details.
    ae.restore(job_id, 0)
    assert os.path.basename(studio.served(path)) == f"subtitled_1700000000_{base}_clip_1.mp4"
    assert studio._read(path)["shorts"][0]["seo_title"] == "Shaheen ka spell"
    # Redo by restoring version 1.
    ae.restore(job_id, 1)
    assert "_ai1_" in os.path.basename(studio.served(path))


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_a_question_comes_back_without_touching_the_video(tmp_path, monkeypatch):
    job_id, path, base = _make_job(tmp_path)
    monkeypatch.setattr(ae, "plan", lambda *a, **k: ae.Plan(summary="", ops=[], question="Kaunsa hissa?"))
    result = ae.apply(job_id, "woh hissa hata do", client=object(), log=lambda *a: None)
    assert not result["ok"] and result["question"] and result["message"] == "Kaunsa hissa?"
    assert os.path.basename(studio.served(path)) == f"subtitled_1700000000_{base}_clip_1.mp4"


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_an_upload_becomes_a_studio_video_of_its_own(tmp_path):
    src = str(tmp_path / "my clip.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=3",
                    "-pix_fmt", "yuv420p", src], check=True)
    job_id = ae.create_upload(src, "my clip.mp4")
    path = studio.job_dir(job_id)
    with open(os.path.join(path, ".source.json"), encoding="utf-8") as f:
        assert json.load(f)["genre"] == "studio_upload"
    rows = [r for r in studio.videos([]) if r["job_id"] == job_id]
    assert rows and rows[0]["channel"] == "uploads" and rows[0]["state"] == "your upload" and rows[0]["label"] == "my clip"
    assert studio.detail(job_id, [])["upload"] is True


def test_studio_uploads_never_reach_the_main_channels_queue(tmp_path, monkeypatch):
    import app
    import post_queue
    monkeypatch.setattr(app, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(post_queue, "since", lambda: 0)
    job = tmp_path / str(uuid.uuid4())
    job.mkdir()
    (job / "Upload_x_metadata.json").write_text(json.dumps({"shorts": [{"seo_title": "t"}]}), encoding="utf-8")
    (job / "Upload_x_clip_1.mp4").write_bytes(b"x")
    (job / ".source.json").write_text(json.dumps({"genre": "studio_upload", "keep_until": 9e9}), encoding="utf-8")
    assert app._queue_clips() == []
    assert app._waiting_to_post(job.name, str(job), 1e9) is True          # kept past the 24 h sweep while it lasts


def test_an_edited_description_keeps_every_credit_block():
    old = ("Shaheen ka spell.\n\nCredit (original video, licensed under CC BY):\n- Some Creator: https://youtu.be/x\n\n"
           "Stock footage and photos (free licence): Pexels (Ann).\n\n#cricket #shorts")
    new = studio.keep_credits(old, "Naya behtar description.\n\n#cricket #pakistan")
    assert new.startswith("Naya behtar description.")
    assert "Credit (original video, licensed under CC BY):\n- Some Creator: https://youtu.be/x" in new
    assert "Stock footage and photos" in new and new.endswith("#cricket #pakistan")
    assert studio.keep_credits(old, old) == old.strip()                    # nothing lost, nothing added
    long = studio.keep_credits(old, "x" * 6000)                             # the body is cut, never the credits
    assert len(long.encode("utf-8")) <= studio.DESCRIPTION_MAX and "Credit (original video" in long


def test_an_edit_in_progress_holds_the_upload():
    import my_channels
    ch = {"review_hours": 0}
    assert my_channels.held_for_review(ch, {"editing_until": 2e9, "approved": True}, now=1e9)
    assert not my_channels.held_for_review(ch, {"editing_until": 1, "approved": True}, now=1e9)


def test_owner_notes_reach_the_script_rules(monkeypatch):
    import script_craft
    monkeypatch.delenv("OWNER_NOTES", raising=False)
    assert script_craft.owner_notes() == ""
    monkeypatch.setenv("OWNER_NOTES", "hook  zyada strong rakho")
    assert "hook zyada strong rakho" in script_craft.short_rules() and "hook zyada strong rakho" in script_craft.long_rules()
