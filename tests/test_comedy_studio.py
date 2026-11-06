"""The main comedy channel in Studio (4-nov-2026): each clip of a job cut from one show is its own Studio video
("<job id>.<n>"), edited by the AI editor from its own slice of the show's words, without touching the other
clips, the shared transcript, or the post queue's order (a clip being edited is not auto-posted)."""
import json
import os
import shutil
import subprocess
import uuid

import pytest

import ai_editor as ae
import post_queue
import studio

HAVE_FFMPEG = bool(shutil.which("ffmpeg"))
BASE = "Jan_Rambo_Comedy_Show"
STARTS = (100.0, 200.0, 300.0)          # where each clip sits in the source show


def _w(word, a, b):
    return {"word": " " + word, "start": a, "end": b}


def _show_words():
    """The show's transcript, in SOURCE seconds: a few words in each clip, one long word running into clip 2."""
    segs = []
    for k, a in enumerate(STARTS):
        segs.append({"start": a + 0.5, "end": a + 3.5, "text": f"clip{k + 1} pehla doosra teesra",
                     "words": [_w(f"clip{k + 1}", a + 0.5, a + 1.0), _w("pehla", a + 1.2, a + 1.8),
                               _w("doosra", a + 2.0, a + 2.6), _w("teesra", a + 2.8, a + 3.5)]})
    # Starts 1.4 s before clip 2 and ends inside it (YouTube's captions give long words over pauses).
    segs.insert(1, {"start": 198.6, "end": 200.3, "text": "lamba", "words": [_w("lamba", 198.6, 200.3)]})
    return {"language": "hi", "source": "youtube_captions", "duration": 900, "segments": segs}


def _make_show(real_video=False, seconds=4.0):
    job_id = str(uuid.uuid4())
    path = os.path.join(studio.OUTPUT_DIR, job_id)
    os.makedirs(path)
    for n in (1, 2, 3):
        clean = os.path.join(path, f"{BASE}_clip_{n}.mp4")
        if real_video:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                            f"testsrc=size=270x480:rate=25:duration={seconds}", "-f", "lavfi", "-i",
                            f"sine=frequency={200 * n}:duration={seconds}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-shortest", clean], check=True)
        else:
            with open(clean, "wb") as f:
                f.write(b"clean")
        shutil.copy(clean, os.path.join(path, f"subtitled_170000000{n}_{BASE}_clip_{n}.mp4"))
    data = {"shorts": [{"start": a, "end": a + seconds, "seo_title": f"Title {k + 1}", "seo_description": "d",
                        "seo_tags": ["comedy"], "video_title_for_youtube_short": f"Hook {k + 1}"}
                       for k, a in enumerate(STARTS)],
            "transcript": _show_words(), "source_video": None, "output_format": "framed"}
    with open(os.path.join(path, f"{BASE}_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)
    with open(os.path.join(path, ".source.json"), "w", encoding="utf-8") as f:
        json.dump({"url": "https://www.youtube.com/watch?v=x", "genre": "comedy", "autopilot": True, "channel": None}, f)
    with open(os.path.join(path, "frame.json"), "w", encoding="utf-8") as f:
        json.dump({"handle": "@PunchlineBazaar"}, f)
    return job_id, path


def _main_rows(job_id):
    return [{"job_id": job_id, "index": i, "title": f"Title {i + 1}", "created": 1_800_000_000} for i in range(3)]


# ---------- ids, the show's words, the romanizer ----------

def test_a_studio_id_names_one_clip():
    jid = str(uuid.uuid4())
    assert studio.split_ref(jid) == (jid, 0) and studio.split_ref(f"{jid}.1") == (jid, 0)
    assert studio.split_ref(f"{jid}.3") == (jid, 2)
    assert studio.ref_of(jid, 0) == jid and studio.ref_of(jid, 2) == f"{jid}.3"
    for bad in (f"{jid}.0", f"{jid}.x", f"{jid}.100", "../etc", f"{jid}/..", "", None):
        with pytest.raises(studio.StudioError):
            studio.split_ref(bad)
    assert ae.edits_name(0) == "edits" and ae.edits_name(2) == "edits_clip3"


def test_each_clip_reads_its_own_slice_of_the_shows_words():
    data = {"shorts": [{"start": a, "end": a + 4.0} for a in STARTS], "transcript": _show_words()}
    assert studio.shares_transcript(data, 1)
    tr = studio.clip_transcript(data, 1)
    words = [(w["word"].strip(), w["start"], w["end"]) for s in tr["segments"] for w in s["words"]]
    # The long word running in from before the clip starts at 0, as its caption does; no other clip's words.
    assert words[0] == ("lamba", 0.0, 0.3)
    assert [w for w, *_ in words] == ["lamba", "clip2", "pehla", "doosra", "teesra"]
    assert words[1][1:] == (0.5, 1.0) and tr["language"] == "hi"
    # A channel Short keeps its own words in clip time: the transcript as it is.
    own = {"shorts": [{"start": 0.0, "end": 8.0}], "transcript": {"segments": [{"words": [_w("a", 0.5, 1.0)]}]}}
    assert not studio.shares_transcript(own, 0) and studio.clip_transcript(own, 0) is own["transcript"]


def test_a_word_running_into_the_clip_is_romanized_too(monkeypatch):
    import caption_script as cs
    monkeypatch.setenv("CAPTION_SCRIPT", "roman")
    monkeypatch.setattr(cs, "_client", lambda: (object(), "gemini-x"))
    seen = []

    def ask(client, model, prompt):
        items = json.loads(prompt.split("Items (JSON): ", 1)[1].split("\n", 1)[0])
        seen.append(items)
        return {"words": [f"r{k}" for k in range(len(items))], "title": "t"}
    monkeypatch.setattr(cs, "_ask", ask)
    transcript = {"language": "hi", "segments": [
        {"start": 717.0, "end": 720.3, "text": "कि", "words": [_w("कि", 717.0, 720.3)]},
        {"start": 720.3, "end": 723.0, "text": "मुझे बताओ", "words": [_w("मुझे", 720.3, 721.0), _w("बताओ", 721.2, 723.0)]}]}
    clip = {"start": 720.089, "end": 750.0, "video_title_for_youtube_short": "शीर्षक"}
    cs.apply(transcript, [clip])
    # Before 4-nov-2026 "कि" (it starts 3 s before the clip) stayed in Devanagari on the Roman captions.
    assert seen == [["कि", "मुझे", "बताओ"]]
    assert [w["word"] for s in transcript["segments"] for w in s["words"]] == [" r0", " r1", " r2"]


# ---------- Studio: the list, a clip's page, what can change by hand ----------

def test_studio_lists_every_comedy_clip_with_its_posting_state():
    job_id, path = _make_show()
    post_queue.update(post_queue.item_id(job_id, 1), status="posted", youtube_id="yt2")
    post_queue.update(post_queue.item_id(job_id, 2), status="skipped")
    rows = {r["job_id"]: r for r in studio.videos([], main=_main_rows(job_id), main_name="Punchline Bazaar")}
    assert set(rows) == {job_id, f"{job_id}.2", f"{job_id}.3"}
    assert [rows[k]["state"] for k in (job_id, f"{job_id}.2", f"{job_id}.3")] == ["waiting", "uploaded", "skipped"]
    two = rows[f"{job_id}.2"]
    assert two["channel"] == "main" and two["channel_name"] == "Punchline Bazaar" and two["video_id"] == "yt2"
    assert two["url"] == f"/videos/{job_id}/subtitled_1700000002_{BASE}_clip_2.mp4" and two["label"] == "Title 2"


def test_a_clip_page_shows_that_clips_details_and_words_only():
    job_id, path = _make_show()
    d = studio.detail(f"{job_id}.2", [], main_name="Punchline Bazaar")
    assert d["job_id"] == f"{job_id}.2" and d["title"] == "Title 2" and d["main"] and d["clip"] == 2 and d["clips"] == 3
    assert d["state"] == "waiting" and d["channel"] == "main" and d["kind"] == "comedy"
    assert [c["text"] for c in d["captions"]] == ["lamba", "clip2 pehla doosra teesra"]
    assert d["manual"] is False and d["captions_editable"] is False
    with pytest.raises(studio.StudioError):
        studio.detail(f"{job_id}.4", [])                                   # the job has 3 clips


def test_hand_trims_and_caption_saves_go_through_the_ai_box_for_a_shared_clip():
    job_id, path = _make_show()
    before = open(os.path.join(path, f"{BASE}_metadata.json"), encoding="utf-8").read()
    files = sorted(os.listdir(path))
    for call in (lambda: studio.trim(f"{job_id}.2", [], 0.5, 3.5, reburn_fn=pytest.fail),
                 lambda: studio.save_captions(f"{job_id}.2", [], [{"text": "x"}, {"text": "y"}], reburn_fn=pytest.fail)):
        with pytest.raises(studio.StudioError, match="AI box"):
            call()
    # Nothing written: the shared words, and the other clips' captioned files (reburn clears every subtitled_).
    assert open(os.path.join(path, f"{BASE}_metadata.json"), encoding="utf-8").read() == before
    assert sorted(os.listdir(path)) == files


def test_a_clips_details_save_into_its_own_entry():
    job_id, path = _make_show()
    assert studio.save_details(f"{job_id}.3", [], title="Naya title", tags=["a", "b"]) == {"saved": True, "pushed": False}
    shorts = studio._read(path)["shorts"]
    assert shorts[2]["seo_title"] == "Naya title" and shorts[2]["seo_tags"] == ["a", "b"]
    assert shorts[0]["seo_title"] == "Title 1" and shorts[1]["seo_title"] == "Title 2"


def test_a_posted_clips_details_go_to_its_youtube_video(monkeypatch):
    import youtube_account as ya
    job_id, path = _make_show()
    post_queue.update(post_queue.item_id(job_id, 1), status="posted", youtube_id="yt2")
    pushed = []
    monkeypatch.setattr(ya, "update_video", lambda vid, **kw: pushed.append((vid, kw["title"])))
    assert studio.save_details(f"{job_id}.2", [], title="Better", push=True)["pushed"]
    assert pushed == [("yt2", "Better")]
    with pytest.raises(studio.StudioError, match="already on YouTube"):
        studio.trim(f"{job_id}.2", [], 0.5, 3.5)


def test_skip_and_put_back_a_comedy_clip():
    job_id, path = _make_show()
    ref = f"{job_id}.2"
    assert "will not be posted" in studio.act(ref, [], "skip")
    assert post_queue.status_of(job_id, 1) == "skipped" and post_queue.status_of(job_id, 0) == "ready"
    assert "Ready to post" in studio.act(ref, [], "approve")
    assert post_queue.status_of(job_id, 1) == "ready"
    with pytest.raises(studio.StudioError, match="cannot be made again"):
        studio.act(ref, [], "remake")
    post_queue.update(post_queue.item_id(job_id, 1), status="posted")
    with pytest.raises(studio.StudioError):
        studio.act(ref, [], "skip")


def test_the_editor_knows_a_comedy_clip_and_its_branding():
    job_id, path = _make_show()
    ctx = ae.context(f"{job_id}.2", channels=[])
    assert ctx["index"] == 1 and ctx["genre"] == "comedy" and ctx["main"] and ctx["channel"] == "main"
    assert "@PunchlineBazaar" in ctx["own"] and ctx["topic"] == "Title 2" and not ctx["remakable"]
    post_queue.update(post_queue.item_id(job_id, 1), status="posted", youtube_id="yt2")
    ctx = ae.context(f"{job_id}.2", channels=[])
    assert ctx["on_youtube"] and ctx["video_id"] == "yt2" and ctx["state"] == "uploaded"


# ---------- a real AI edit of clip 2 ----------

@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_an_ai_edit_of_clip_two_changes_clip_two_only(monkeypatch):
    job_id, path = _make_show(real_video=True)
    ref = f"{job_id}.2"
    meta_file = os.path.join(path, f"{BASE}_metadata.json")
    before = json.load(open(meta_file, encoding="utf-8"))
    served_1, served_3 = studio.served(path, 0), studio.served(path, 2)
    plan = ae.Plan(summary="Cut the start, yellow captions, new title", ops=[
        ae.Op(op="cut", start=0.0, end=0.4), ae.Op(op="caption_style", value="color=yellow"),
        ae.Op(op="title", text="Naya comedy title")])
    monkeypatch.setattr(ae, "plan", lambda *a, **k: plan)
    monkeypatch.setattr(ae, "check", lambda *a, **k: (True, []))
    monkeypatch.delenv("CAPTION_EMPHASIS", raising=False)
    result = ae.apply(ref, "pehle thoda kaato, captions peele, title behtar", client=object(), log=lambda *a: None)
    assert result["ok"] and result["n"] == 1 and result["details"] == ["title"], result
    new = studio.served(path, 1)
    assert os.path.basename(new).startswith("subtitled_") and f"_ai1_{BASE}_clip_2.mp4" in new
    assert studio.duration(new) == pytest.approx(3.6, abs=0.15)
    # The other clips play and upload exactly what they did.
    assert studio.served(path, 0) == served_1 and studio.served(path, 2) == served_3
    after = json.load(open(meta_file, encoding="utf-8"))
    assert after["transcript"] == before["transcript"]                   # the show's words serve every clip
    assert after["shorts"][0] == before["shorts"][0] and after["shorts"][2] == before["shorts"][2]
    two = after["shorts"][1]
    assert two["seo_title"] == "Naya comedy title" and two["seconds"] == pytest.approx(3.6, abs=0.05)
    assert (two["start"], two["end"]) == (200.0, 204.0)                  # its place in the show stays
    # Its own chain, its own captions (clip 2's words, the comedy look: no emphasis colours).
    assert os.path.isfile(os.path.join(path, "edits_clip2", "state.json"))
    assert not os.path.exists(os.path.join(path, "edits"))
    ass = open(os.path.join(path, "edits_clip2", "r1", "captions.ass"), encoding="utf-8").read().upper()
    assert "CLIP2" in ass and "CLIP1" not in ass and "CLIP3" not in ass
    assert os.environ.get("CAPTION_EMPHASIS") is None
    assert ae.status(ref)["current"] == 1 and ae.status(job_id)["revisions"] == []
    # Undo: clip 2's own first version and title come back; nothing else moves.
    ae.restore(ref, 0)
    assert os.path.basename(studio.served(path, 1)) == f"subtitled_1700000002_{BASE}_clip_2.mp4"
    assert json.load(open(meta_file, encoding="utf-8"))["shorts"][1]["seo_title"] == "Title 2"
    assert json.load(open(meta_file, encoding="utf-8"))["transcript"] == before["transcript"]


# ---------- the main channel's poster and the phone ----------

def test_the_poster_waits_for_a_clip_being_edited(monkeypatch):
    import datetime
    import time

    import app
    clips = [{"job_id": "a", "index": 0, "created": 1}, {"job_id": "a", "index": 1, "created": 1}]
    slots = lambda times, n: [datetime.datetime(2030, 1, 1)] * n           # noqa: E731
    post_queue.update(post_queue.item_id("a", 1), editing_until=int(time.time()) + 600)
    rows = post_queue.plan(clips, ["19:30"], slots)
    assert [r["editing"] for r in rows] == [False, True]
    sent = []
    monkeypatch.setattr(app, "_plan_items", lambda: rows)
    monkeypatch.setattr(app, "_post_all_run", lambda items: sent.append([x["id"] for x in items]))
    app._post_all["running"] = False
    app._auto_post_ready()
    assert sent == [["a:0"]]                                            # the edited clip waits for the next run
    post_queue.update(post_queue.item_id("a", 1), editing_until=0)
    assert not post_queue.plan(clips, ["19:30"], slots)[1]["editing"]


def test_a_phone_reply_reaches_a_comedy_clip(monkeypatch):
    import my_channels as mc
    job_id, path = _make_show()
    monkeypatch.setattr(mc, "channels", lambda: [])
    started = []
    monkeypatch.setattr(mc, "start_ai_edit", lambda ref, prompt: started.append((ref, prompt)))
    note = f"Done: captions peele\n{mc.PHONE_EDIT_HINT}\nref {job_id}.2"
    assert mc._REF.search(note).group(1) == f"{job_id}.2"
    assert mc._REF.search(f"ref {job_id}. More text").group(1) == job_id       # a full stop is not a clip number
    assert mc.telegram_reply("zoom karo", note).startswith("Working on it")
    assert started == [(f"{job_id}.2", "zoom karo")]
    post_queue.update(post_queue.item_id(job_id, 2), status="skipped")
    assert "was skipped" in mc.telegram_reply("x", f"ref {job_id}.3")
    assert "no longer" in mc.telegram_reply("x", f"ref {job_id}.4")             # no fourth clip
