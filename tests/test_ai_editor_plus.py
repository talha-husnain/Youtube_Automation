"""AI editor upgrades (4-nov-2026): a stretch at its own speed, bleep, blur, sound effects, stickers,
speech cleanup, fades, text colour/size, undo by prompt, footage across cut stretches."""
import os
import re
import shutil
import subprocess

import numpy as np
import pytest

import ai_editor as ae
import studio
from test_ai_editor import WORDS, _make_job

HAVE_FFMPEG = bool(shutil.which("ffmpeg"))


# ---------- time maps with a stretch of its own speed ----------

def test_a_slow_motion_stretch_maps_both_ways():
    tl = ae.Timeline([(0.0, 8.0)], segments=[(2.0, 4.0, 0.5)])
    assert tl.duration == pytest.approx(10.0) and not tl.uniform
    assert [p[2] for p in tl.pieces] == [1.0, 0.5, 1.0]
    assert tl.out(1.0) == pytest.approx(1.0) and tl.out(3.0) == pytest.approx(4.0) and tl.out(5.0) == pytest.approx(7.0)
    assert tl.base(4.0) == pytest.approx(3.0) and tl.base(7.0) == pytest.approx(5.0)
    assert tl.out_ranges(1.0, 5.0) == [(1.0, 7.0)]                    # pieces of one stretch are one range
    assert tl.base_ranges(1.0, 7.0) == [(1.0, 5.0)]


def test_stretch_speed_combines_with_cuts_and_the_whole_video_speed():
    tl = ae.Timeline([(0.0, 2.0), (3.0, 6.0)], speed=2.0, segments=[(4.0, 5.0, 0.5)])
    # 0-2 at 2x (1 s), 3-4 at 2x (0.5 s), 4-5 at 1x (1 s), 5-6 at 2x (0.5 s)
    assert tl.duration == pytest.approx(3.0)
    assert tl.out(4.5) == pytest.approx(2.0) and tl.out(2.5) is None
    assert ae.Timeline([(0.0, 4.0)], segments=[(0.0, 4.0, 0.01)]).pieces[0][2] == ae.SPEED_MIN
    assert ae.Timeline([(0.0, 2.0), (3.0, 6.0)], speed=2.0).uniform          # the old global-speed case


def test_the_old_global_speed_maps_exactly_as_before():
    tl = ae.Timeline([(0.0, 2.0), (3.0, 6.0)], speed=2.0)
    assert tl.duration == pytest.approx(2.5)
    assert tl.base_ranges(0.5, 2.0) == [(1.0, 2.0), (3.0, 5.0)]
    assert tl.out_ranges(1.5, 3.5) == [(0.75, 1.25)]


# ---------- regions ----------

def test_regions_from_a_box_or_a_named_spot():
    x0, y0, x1, y1 = ae._region("box=700,20,980,120")
    assert (x0, y0) == pytest.approx((0.68, 0.0)) and (x1, y1) == pytest.approx((1.0, 0.14))
    assert ae._region("top right corner") == ae.REGIONS["top-right"]
    assert ae._region("bottom-left") == ae.REGIONS["bottom-left"]
    assert ae._region("0.7, 0.0, 1.0, 0.15") == pytest.approx((0.68, 0.0, 1.0, 0.17))
    assert ae._region("the small logo") == ae.REGIONS["top-right"]       # "small" is not "all"
    assert ae._region("whole frame") == ae.REGIONS["full"]
    assert ae._region("somewhere nice") is None
    tiny = ae._region("box=500,500,501,501")
    assert tiny[2] - tiny[0] >= 0.04 - 1e-9 and tiny[3] - tiny[1] >= 0.04 - 1e-9


# ---------- the plan's new operations, checked ----------

def _resolve(ops, monkeypatch=None, on_youtube=False):
    ctx = {"on_youtube": on_youtube, "remakable": False, "upload": False, "genre": "cricket", "kind": "cricket"}
    state = {"base": {"stem": None, "audio": True}, "revisions": [], "current": 0}
    return ae.resolve(ae.Plan(summary="s", ops=ops), ctx, state, ae.Timeline([(0.0, 8.0)]), WORDS)


def test_new_operations_are_checked_and_placed(monkeypatch):
    import stickers
    monkeypatch.setattr(stickers, "path", lambda name: "x.webp" if name in stickers.EMOJI else None)
    ops, details, remake, notes = _resolve([
        ae.Op(op="bleep", quote="31 runs"),
        ae.Op(op="bleep", quote="teen", value="mute"),
        ae.Op(op="blur", value="box=700,20,980,120", text="pixelate"),
        ae.Op(op="blur", value="top-left"),
        ae.Op(op="sfx", quote="wicket", value="a ding sound", amount=3),
        ae.Op(op="sticker", quote="wicket", value="joy", text="middle"),
        ae.Op(op="speed", quote="aur teen wicket", amount=0.5),
        ae.Op(op="speed", amount=1.1),
        ae.Op(op="clean_audio"),
        ae.Op(op="fade", value="out", amount=1.0),
        ae.Op(op="text", text="WOW", value="middle; color=yellow; size=1.4"),
    ])
    by = {}
    for o in ops:
        by.setdefault(o["op"], []).append(o)
    assert by["bleep"][0]["value"] == "beep" and by["bleep"][1]["value"] == "mute"
    a, b = by["bleep"][0]["ranges"][0]
    assert a < 1.7 and b > 2.4                                              # the words "31 runs"
    assert by["blur"][0]["text"] == "pixelate" and by["blur"][0]["ranges"] == [[0.0, 8.0]]   # all video
    assert by["blur"][1]["box"] == list(ae.REGIONS["top-left"]) and by["blur"][1]["text"] == "blur"
    assert by["sfx"][0]["value"] == "ding" and by["sfx"][0]["amount"] == 3 and len(by["sfx"][0]["ranges"]) == 1
    st = by["sticker"][0]
    assert st["value"] == "joy" and st["text"] == "middle"
    assert st["ranges"][0][1] - st["ranges"][0][0] >= 2.0                    # held ~2 s, not just the word
    assert by["speed"][0]["ranges"] and by["speed"][0]["amount"] == 0.5
    assert "ranges" not in by["speed"][1] and by["speed"][1]["amount"] == 1.1
    assert by["clean_audio"][0]["amount"] == 0.6 and by["fade"][0] == {"op": "fade", "value": "out", "amount": 1.0}
    assert by["text"][0]["value"] == "middle" and by["text"][0]["style"] == {"color": "#FFE500", "size": 1.4}
    assert not notes, notes


def test_bad_new_operations_say_why(monkeypatch):
    import stickers
    monkeypatch.setattr(stickers, "path", lambda name: None)
    ops, _d, _r, notes = _resolve([ae.Op(op="sfx", quote="wicket", value="laughter"),
                                   ae.Op(op="sticker", quote="wicket", value="unicorn"),
                                   ae.Op(op="blur", value="somewhere nice"),
                                   ae.Op(op="bleep", value="beep")])
    assert ops == [] and len(notes) == 4
    assert "sounds are" in notes[0] and "sticker" in notes[1] and "corner" in notes[2] and "bleep" in notes[3]


def test_on_youtube_still_refuses_file_changes():
    ops, _d, _r, notes = _resolve([ae.Op(op="blur", value="top-left")], on_youtube=True)
    assert ops == [] and "already on YouTube" in notes[0]


def test_new_operations_fold_into_the_spec():
    ops = [{"op": "speed", "amount": 0.5, "ranges": [[2.0, 4.0]]},
           {"op": "bleep", "value": "beep", "ranges": [[1.0, 1.5]]},
           {"op": "blur", "box": [0.7, 0.0, 1.0, 0.15], "text": "blur", "ranges": [[0.0, 8.0]]},
           {"op": "sfx", "value": "pop", "amount": 0.0, "ranges": [[3.0, 3.5]]},
           {"op": "sticker", "value": "fire", "text": "top-left", "ranges": [[1.0, 3.0]]},
           {"op": "clean_audio", "value": "on", "amount": 0.7},
           {"op": "fade", "value": "both", "amount": 0.5}]
    spec = ae.compile_ops(ops, 8.0, WORDS)
    assert spec["speeds"] == [(2.0, 4.0, 0.5)] and spec["speed"] == 1.0
    assert ae.timeline(spec).duration == pytest.approx(10.0)
    assert spec["bleeps"] == [(1.0, 1.5, "beep")] and spec["sfx"] == [(3.0, "pop", 0.0)]
    assert spec["blurs"][0]["box"] == [0.7, 0.0, 1.0, 0.15] and spec["stickers"] == [(1.0, 3.0, "fire", "top-left")]
    assert spec["clean"] == 0.7 and spec["fade"] == ("both", 0.5)
    off = ae.compile_ops(ops + [{"op": "blur", "value": "off", "ranges": []}, {"op": "clean_audio", "value": "off",
                                                                              "amount": 0.6},
                                {"op": "fade", "value": "off", "amount": 0.6}], 8.0, WORDS)
    assert off["blurs"] == [] and off["clean"] is None and off["fade"] is None


def test_text_colour_and_size_reach_the_ass(tmp_path):
    p = ae._text_ass([(0.0, 2.0, "WOW", "top", {"color": "#FFE500", "size": 1.4}), (2.0, 3.0, "plain", "top")],
                     (1080, 1920), str(tmp_path / "t.ass"))
    text = open(p, encoding="utf-8").read()
    assert r"\1c&H00E5FF&" in text and r"\fscx140\fscy140" in text            # BGR in ASS
    assert r"\fscx85\fscy85\t(0,140,\fscx104\fscy104)\t(140,240,\fscx100\fscy100)}plain" in text   # unchanged look


def test_the_planner_is_told_about_every_operation():
    for name in ("bleep", "blur", "sfx", "sticker", "clean_audio", "fade", "undo"):
        assert name in ae.OPS
    assert "undo" not in ae.FILE_OPS and "blur" in ae.FILE_OPS
    assert ae._atempo(1.0) == "" and ae._atempo(0.25) == "atempo=0.5,atempo=0.5000," and ae._atempo(2.0) == "atempo=2.0000,"


# ---------- real renders ----------

def _frame(video, t, box=None):
    """One RGB frame (numpy) at ``t`` s, optionally cropped to a fraction box."""
    from PIL import Image
    import io
    png = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-f", "image2pipe",
                          "-vcodec", "png", "-"], capture_output=True, check=True).stdout
    im = np.asarray(Image.open(io.BytesIO(png)).convert("L"), dtype=np.float32)
    if box:
        h, w = im.shape
        x0, y0, x1, y1 = box
        im = im[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    return im


def _db(video, a, b, af=""):
    r = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", video, "-af",
                        (af + "," if af else "") + "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else -99.0


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_a_real_render_with_every_new_operation(tmp_path, monkeypatch):
    job_id, path, base = _make_job(tmp_path)
    box = [0.0, 0.0, 0.5, 0.25]
    plan = ae.Plan(summary="Slow-mo, bleep, blur, sounds, fade", ops=[
        ae.Op(op="speed", start=4.0, end=6.0, amount=0.5),           # 2 s of slow motion: 8 s -> 10 s
        ae.Op(op="bleep", start=1.0, end=1.6),                       # a beep there
        ae.Op(op="bleep", start=2.4, end=3.0, value="mute"),         # silence there
        ae.Op(op="blur", value="box=0,0,500,250"),
        ae.Op(op="sfx", start=0.5, value="ding"), ae.Op(op="sfx", start=3.2, value="whoosh"),
        ae.Op(op="clean_audio", amount=0.5), ae.Op(op="fade", value="out", amount=0.5),
        ae.Op(op="text", text="WOW", value="bottom; color=yellow; size=1.3")])
    monkeypatch.setattr(ae, "plan", lambda *a, **k: plan)
    monkeypatch.setattr(ae, "check", lambda *a, **k: (True, []))
    result = ae.apply(job_id, "sab kuch", client=object(), log=lambda *a: None)
    assert result["ok"], result
    out = studio.served(path)
    assert studio.duration(out) == pytest.approx(10.0, abs=0.2)
    clean = os.path.join(path, f"{base}_clip_1.mp4")
    # Blur: the box lost its detail (testsrc is all sharp edges), the rest of the frame kept it.
    assert _frame(out, 2.0, box).std() < 0.6 * _frame(clean, 2.0, box).std()
    assert _frame(out, 2.0, [0.5, 0.5, 1.0, 0.75]).std() > 0.6 * _frame(clean, 2.0, [0.5, 0.5, 1.0, 0.75]).std()
    # Bleep: a 1 kHz tone as loud as the speech in its window (the voice there is the 300 Hz sine, muted);
    # the muted window is (near) silent.
    band = "bandpass=f=1000:width_type=q:w=5,bandpass=f=1000:width_type=q:w=5"
    assert _db(out, 1.15, 1.45, band) > _db(out, 1.8, 2.2, band) + 25
    assert _db(out, 1.15, 1.45) > _db(out, 1.8, 2.2) - 6                   # not a faint tone under silence
    assert _db(out, 2.55, 2.85) < -45
    # The fade: the last frame is near black.
    assert _frame(out, 9.95).mean() < 30


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_undo_typed_into_the_box(tmp_path, monkeypatch):
    job_id, path, base = _make_job(tmp_path)
    plans = iter([ae.Plan(summary="Cut", ops=[ae.Op(op="cut", quote="sirf 31 runs")]),
                  ae.Plan(summary="Zoom", ops=[ae.Op(op="zoom", quote="teen wicket")]),
                  ae.Plan(summary="Wapas", ops=[ae.Op(op="undo")]),
                  ae.Plan(summary="Sab wapas", ops=[ae.Op(op="undo", value="all")]),
                  ae.Plan(summary="Aur wapas", ops=[ae.Op(op="undo")])])
    monkeypatch.setattr(ae, "plan", lambda *a, **k: next(plans))
    monkeypatch.setattr(ae, "check", lambda *a, **k: (True, []))
    for req in ("cut", "zoom"):
        assert ae.apply(job_id, req, client=object(), log=lambda *a: None)["ok"]
    assert "_ai2_" in os.path.basename(studio.served(path))
    r = ae.apply(job_id, "undo", client=object(), log=lambda *a: None)
    assert r["ok"] and r["undone"] and r["n"] == 1 and "_ai1_" in os.path.basename(studio.served(path))
    r = ae.apply(job_id, "sab wapas", client=object(), log=lambda *a: None)
    assert r["ok"] and r["n"] == 0
    assert os.path.basename(studio.served(path)) == f"subtitled_1700000000_{base}_clip_1.mp4"
    assert len(ae.status(job_id)["revisions"]) == 2                          # still there to redo
    r = ae.apply(job_id, "undo", client=object(), log=lambda *a: None)       # nothing left to take back
    assert not r["ok"] and "no AI edit" in r["message"]


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_a_sticker_renders_when_the_noto_files_are_here(tmp_path, monkeypatch):
    import stickers
    if not stickers.path("joy"):
        pytest.skip("no Noto sticker files on this machine")
    job_id, path, base = _make_job(tmp_path)
    monkeypatch.setattr(ae, "plan", lambda *a, **k: ae.Plan(summary="Joy", ops=[
        ae.Op(op="sticker", start=1.0, end=3.0, value="joy", text="middle")]))
    monkeypatch.setattr(ae, "check", lambda *a, **k: (True, []))
    assert ae.apply(job_id, "hasne wala emoji", client=object(), log=lambda *a: None)["ok"]
    out = studio.served(path)
    clean = os.path.join(path, f"{base}_clip_1.mp4")
    mid = [0.4, 0.38, 0.6, 0.52]
    assert np.abs(_frame(out, 2.0, mid) - _frame(clean, 2.0, mid)).mean() > 10      # something is drawn there
    assert np.abs(_frame(out, 6.0, mid) - _frame(clean, 6.0, mid)).mean() < 6       # and gone later


# ---------- fixes from the first live run (4-nov-2026) ----------

def test_a_sound_at_a_moment_is_not_dropped():
    ops, _d, _r, notes = _resolve([ae.Op(op="sfx", start=0.0, end=0.0, value="whoosh"),
                                   ae.Op(op="sfx", quote="no such words here", start=4.2, end=4.2, value="ding")])
    assert not notes, notes
    assert ops[0]["ranges"] == [[0.0, 0.3]] and ops[1]["ranges"][0][0] == pytest.approx(4.2)


def test_the_sheet_names_our_own_branding(tmp_path, monkeypatch):
    job_id, path, base = _make_job(tmp_path)
    import json
    with open(os.path.join(path, "frame.json"), "w", encoding="utf-8") as f:
        json.dump({"handle": "@cricrecordzdaily"}, f)
    ctx = ae.context(job_id, channels=[])
    assert ctx["own"] == ["@cricrecordzdaily"]
    state = ae.ensure_base(path)
    tl = ae.Timeline([(0.0, state["base"]["seconds"])])
    sheet = ae.edit_sheet(ctx, state, tl, ae.words_now(ae._words(state["base"]["meta"]["transcript"]), tl))
    assert "OUR OWN BRANDING" in sheet and "@cricrecordzdaily" in sheet
    assert "never means OUR OWN BRANDING" in ae.PROMPT


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_a_clip_of_a_longer_source_edits_its_slice_and_never_rewrites_the_shared_words(tmp_path, monkeypatch):
    # Until 4-nov-2026 such a clip was refused (the editor read the whole show's words); now it reads the slice
    # its captions came from (studio.clip_transcript), and the shared transcript stays as it was.
    job_id, path, base = _make_job(tmp_path)
    data = studio._read(path)
    data["transcript"]["segments"].append({"start": 400.0, "end": 402.0, "text": "far later",
                                           "words": [{"word": " far", "start": 400.0, "end": 401.0}]})
    studio._write(path, data)
    shared = studio._read(path)["transcript"]
    monkeypatch.setattr(ae, "plan", lambda *a, **k: ae.Plan(summary="yellow", ops=[ae.Op(op="caption_style",
                                                                                       value="color=yellow")]))
    monkeypatch.setattr(ae, "check", lambda *a, **k: (True, []))
    assert ae.apply(job_id, "captions peele", client=object(), log=lambda *a: None)["ok"]
    assert studio._read(path)["transcript"] == shared
    words = [w["word"].strip() for w in ae._words(ae.load(path)["base"]["meta"]["transcript"])]
    assert "far" not in words and "Shaheen" in words


# ---------- suggestions ----------

def test_suggestions_are_cleaned_cached_and_redone_when_the_video_changes(tmp_path, monkeypatch):
    import short_kit as kit
    job_id, path, base = _make_job(tmp_path)
    calls = []

    def fake_ask(client, schema, parts, model=None, **kw):
        calls.append(parts[-1])
        assert kw.get("max_tokens") and kw.get("invalid_tries") == 2     # a runaway answer is capped
        return ae.Suggestions(items=[ae.Suggestion(text="Pehle 0.5 second  kaat do", why="dead air"),
                                     ae.Suggestion(text="pehle 0.5 second kaat do", why="same again"),
                                     ae.Suggestion(text="'31 runs' par zoom aur ding", why="the key number"),
                                     ae.Suggestion(text="   ", why="empty")])
    monkeypatch.setattr(kit, "ask_json", fake_ask)
    got = ae.suggest(job_id, client=object())
    assert [s["text"] for s in got["items"]] == ["Pehle 0.5 second kaat do", "'31 runs' par zoom aur ding"]
    assert "Roman Urdu" in calls[0] and "SPOKEN WORDS" in calls[0] and "bleep" in calls[0]
    assert ae.suggest(job_id, client=object())["items"] == got["items"] and len(calls) == 1      # cached
    served = studio.served(path)
    os.utime(served, (os.path.getmtime(served) + 5,) * 2)                                         # the video changed
    ae.suggest(job_id, client=object())
    assert len(calls) == 2


def test_a_live_video_only_gets_detail_suggestions(tmp_path, monkeypatch):
    job_id, path, base = _make_job(tmp_path)
    real = ae.context
    monkeypatch.setattr(ae, "context", lambda j, channels=None: {**real(j, channels=[]), "on_youtube": True})
    got = ae.suggest(job_id, client=object())
    assert [s["text"] for s in got["items"]] == ["Write a better title", "Write a better description"]


def test_the_suggest_route_answers(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app
    monkeypatch.setattr(ae, "suggest", lambda job_id: {"items": [{"text": "x", "why": "y"}]})
    monkeypatch.setattr(app, "_local_only", lambda: None)
    c = TestClient(app.app)
    r = c.post("/api/studio/ai/0f8d9c2a-1b2c-4d3e-8f4a-5b6c7d8e9f01/suggest")
    assert r.status_code == 200 and r.json()["items"][0]["text"] == "x"

    def broken(job_id):
        raise ValueError("model said no")
    monkeypatch.setattr(ae, "suggest", broken)
    r = c.post("/api/studio/ai/0f8d9c2a-1b2c-4d3e-8f4a-5b6c7d8e9f01/suggest")
    assert r.status_code == 502 and "No suggestions" in r.json()["detail"]


def test_an_op_without_a_moment_goes_where_the_one_before_it_went(monkeypatch):
    import stickers
    monkeypatch.setattr(stickers, "path", lambda name: "x.webp")
    ops, _d, _r, notes = _resolve([ae.Op(op="speed", quote="aur teen wicket", amount=0.5),
                                   ae.Op(op="sticker", value="fire")])
    assert not notes, notes
    speed, sticker = ops
    assert sticker["ranges"][0][0] == pytest.approx(speed["ranges"][0][0])
    ops, _d, _r, notes = _resolve([ae.Op(op="sticker", value="fire")])            # nothing before it
    assert ops == [] and notes


def test_quotes_match_spoken_variants_but_not_other_words():
    words = [{"word": w, "start": i, "end": i + 0.5} for i, w in
             enumerate(["Kohli", "ne", "sab", "records", "tod", "diye", "zabardast", "15,000", "runs"])]
    assert ae.find_quote(words, "record tod diye") == (3, 5)
    assert ae.find_quote(words, "zabardust 15000 runs") == (6, 8)
    assert ae.find_quote(words, "Babar ne century") is None
    assert not ae._same("ne", "se") and not ae._same("run", "rang")


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_only_this_requests_visible_changes_go_to_the_frame_check(tmp_path, monkeypatch):
    job_id, path, base = _make_job(tmp_path)
    plans = {"blur karo": ae.Plan(summary="Blur", ops=[ae.Op(op="blur", value="top-left")]),
             "awaaz saaf karo": ae.Plan(summary="Saaf", ops=[ae.Op(op="clean_audio")])}
    monkeypatch.setattr(ae, "plan", lambda client, request, *a, **k: plans[request])
    checked = []
    monkeypatch.setattr(ae, "check", lambda client, request, *a: checked.append(request) or (False, ["cannot be seen"]))
    r1 = ae.apply(job_id, "blur karo", client=object(), log=lambda *a: None)
    r2 = ae.apply(job_id, "awaaz saaf karo", client=object(), log=lambda *a: None)
    assert r1["ok"] and r2["ok"] and r2["n"] == 2
    # the blur was checked (and "failed", so it got its one more pass); the audio edit never was
    assert all(req == "blur karo" for req in checked) and r2["check"] == {"done": None, "problems": []}


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_a_failed_second_plan_keeps_the_first_version(tmp_path, monkeypatch):
    """Live run, 4-nov-2026: the fix-up plan came back as broken JSON and the whole edit was lost."""
    job_id, path, base = _make_job(tmp_path)
    calls = []

    def plan(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            return ae.Plan(summary="WOW text", ops=[ae.Op(op="text", text="WOW", value="middle")])
        raise ValueError("Invalid JSON: EOF while parsing")
    monkeypatch.setattr(ae, "plan", plan)
    monkeypatch.setattr(ae, "check", lambda *a, **k: (False, ["text too small"]))
    r = ae.apply(job_id, "WOW likho", client=object(), log=lambda *a: None)
    assert r["ok"] and r["n"] == 1 and len(calls) == 2
    assert any("first one" in p for p in r["check"]["problems"]) and "_ai1_" in os.path.basename(studio.served(path))


def test_ask_json_caps_and_retries_broken_json_only_when_asked():
    import short_kit as kit
    from pydantic import BaseModel

    class S(BaseModel):
        a: int

    class R:
        def __init__(self, text):
            self.text = text

    class Models:
        def __init__(self, answers):
            self.answers, self.configs = list(answers), []

        def generate_content(self, model, contents, config):
            self.configs.append(config)
            return R(self.answers.pop(0))

    class C:
        def __init__(self, answers):
            self.models = Models(answers)

    c = C(['{"a": 1', '{"a": 2}'])
    assert kit.ask_json(c, S, "x", model="m", max_tokens=100, invalid_tries=2).a == 2
    assert c.models.configs[0].max_output_tokens == 100
    c = C(['{"a": 1'])
    with pytest.raises(Exception):
        kit.ask_json(c, S, "x", model="m")                         # the old behaviour: no second ask
    assert c.models.configs[0].max_output_tokens is None
