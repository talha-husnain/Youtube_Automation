"""The Studio (studio.py): open a channel's finished video, fix its details, captions or length, and approve,
skip or remake it before it goes up (29-oct-2026)."""
import glob
import json
import os
import shutil
import subprocess
import time

import pytest

import my_channels as mc
import studio
import youtube_account as ya

FFMPEG = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
JOB = "0123abcd-0000-4000-8000-00000000abcd"


def _words(text, t0, step=0.4):
    return [{"word": " " + w, "start": round(t0 + k * step, 3), "end": round(t0 + (k + 1) * step, 3)}
            for k, w in enumerate(text.split())]


def _job(tmp_path, seconds=8, status="done", review=0, make_video=True):
    path = os.path.join(studio.OUTPUT_DIR, JOB)
    os.makedirs(path, exist_ok=True)
    clean = os.path.join(path, "Cricket_x_clip_1.mp4")
    if make_video:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=270x480:rate=30:duration={seconds}",
                        "-f", "lavfi", "-i", f"sine=f=300:d={seconds}", "-shortest", "-c:v", "libx264", "-pix_fmt",
                        "yuv420p", "-c:a", "aac", clean], check=True)
    else:
        open(clean, "wb").close()
    segs = [{"start": 0.5, "end": 2.1, "text": "Babar ne 97 innings", "words": _words("Babar ne 97 innings", 0.5)},
            {"start": 4.0, "end": 5.6, "text": "kohli ne 120 mein", "words": _words("kohli ne 120 mein", 4.0)}]
    meta = {"shorts": [{"start": 0.0, "end": float(seconds), "seo_title": "Babar ya Kohli? #shorts",
                        "seo_description": "D", "seo_tags": ["babar"], "video_title_for_youtube_short": "Babar ya Kohli"}],
            "transcript": {"language": "ur", "segments": segs}, "output_format": "framed", "genre": "cricket"}
    with open(os.path.join(path, "Cricket_x_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    ch = mc.add("cricket")
    mc._change(ch["id"], lambda c: c.update(review_hours=review, jobs=[
        {"job_id": JOB, "status": status, "at": time.time() - 60, "done_at": time.time() - 30, "label": "Babar vs Kohli",
         "format": "versus", "topic": "Babar vs Kohli", "qa": "ok", "look": "first frame 7/10, polish 8/10",
         **({"video_id": "AbCdEfGhIjK"} if status == "uploaded" else {})}]))
    return path, mc.get(ch["id"])


def _meta(path):
    return json.load(open(glob.glob(os.path.join(path, "*_metadata.json"))[0], encoding="utf-8"))


def test_ids_are_checked_before_any_path_is_built():
    for bad in ("../../etc", "x", JOB + "/..", ""):
        with pytest.raises(studio.StudioError):
            studio.job_dir(bad)


def test_the_list_and_the_detail_show_what_the_owner_reviews(tmp_path):
    path, ch = _job(tmp_path, make_video=False, review=6)
    rows = studio.videos(mc.channels())
    assert [r["job_id"] for r in rows] == [JOB] and rows[0]["state"] == "held for review"
    assert rows[0]["url"] == f"/videos/{JOB}/Cricket_x_clip_1.mp4"
    open(os.path.join(path, "subtitled_1_Cricket_x_clip_1.mp4"), "wb").close()
    assert studio.videos(mc.channels())[0]["url"].endswith("subtitled_1_Cricket_x_clip_1.mp4")   # the served file
    d = studio.detail(JOB, mc.channels())
    assert d["title"] == "Babar ya Kohli? #shorts" and d["captions_editable"]
    assert [c["text"] for c in d["captions"]] == ["Babar ne 97 innings", "kohli ne 120 mein"]


def test_details_are_saved_for_the_upload_and_pushed_to_youtube_when_up(tmp_path, monkeypatch):
    path, ch = _job(tmp_path, make_video=False)
    with pytest.raises(studio.StudioError, match="allows 100"):
        studio.save_details(JOB, mc.channels(), title="x" * 101)
    assert studio.save_details(JOB, mc.channels(), title="  New   title ", tags=["a", " ", "b"]) == \
        {"saved": True, "pushed": False}
    short = _meta(path)["shorts"][0]
    assert short["seo_title"] == "New title" and short["seo_tags"] == ["a", "b"]
    mc._set_job(ch["id"], JOB, status="uploaded", video_id="AbCdEfGhIjK")
    sent = {}
    monkeypatch.setattr(ya, "update_video", lambda vid, **kw: sent.update(vid=vid, **kw) or True)
    assert studio.save_details(JOB, mc.channels(), description="Better", push=True)["pushed"]
    assert sent["vid"] == "AbCdEfGhIjK" and sent["description"] == "Better" and sent["title"] == "New title"


def test_title_ideas_pass_the_tournament_checks_and_come_with_search_phrases(tmp_path, monkeypatch):
    import script_craft
    import short_kit as kit
    _job(tmp_path, make_video=False)
    monkeypatch.setattr(kit, "ask_json", lambda client, schema, contents, model=None: schema(titles=[
        "Babar ne 97 innings mein kya kiya jo Kohli nahi kar saka?",     # its numbers and names are in the video
        "Babar ne 50 innings mein record tod diya, Kohli dekhte reh gaye",  # 50: not in the video
        "BABAR YA KOHLI: ASAL BADSHAH KAUN HAI AAKHIR?",                   # shouting
        "Babar ne 97 innings mein kya kiya jo Kohli nahi kar saka?"]))     # the same angle twice
    asked = []
    got = studio.title_options(JOB, mc.channels(), client=object(),
                               suggest=lambda q: asked.append(q) or [f"{q} stats", "babar vs kohli"])
    assert got["current"] == "Babar ya Kohli? #shorts"
    assert got["options"] == ["Babar ne 97 innings mein kya kiya jo Kohli nahi kar saka? #shorts"]   # the tail kept
    assert asked == ["babar vs kohli", "babar vs"]                     # the video's own subject first
    assert got["searches"][:3] == ["babar vs kohli stats", "babar vs kohli", "babar vs stats"]
    assert script_craft.title_ok(got["options"][0].replace(" #shorts", ""), "Babar ya Kohli?", "Babar ne 97 innings")


def test_a_caption_fix_keeps_its_timing_and_the_checks_run_again(tmp_path):
    path, ch = _job(tmp_path, make_video=False)
    burned = []
    url = studio.save_captions(JOB, mc.channels(), [{"text": "Babar ne 97 innings"}, {"text": "Kohli ne 120 mein"}],
                               reburn_fn=burned.append)
    segs = _meta(path)["transcript"]["segments"]
    assert burned == [path] and url.startswith(f"/videos/{JOB}/")
    assert segs[1]["words"][0] == {"word": " Kohli", "start": 4.0, "end": 4.4}            # same timing, new spelling
    studio.save_captions(JOB, mc.channels(), [{"text": "Babar ne sirf 97 innings mein"}, {"text": "Kohli ne 120 mein"}],
                         reburn_fn=burned.append)
    words = _meta(path)["transcript"]["segments"][0]["words"]
    assert len(words) == 6 and words[0]["start"] == 0.5 and abs(words[-1]["end"] - 2.1) < 0.01   # spread over it
    job = mc.get(ch["id"])["jobs"][0]
    assert job["qa"] is None and job["look"] is None                                     # checked again before upload
    with pytest.raises(studio.StudioError, match="changed since"):
        studio.save_captions(JOB, mc.channels(), [{"text": "only one"}], reburn_fn=burned.append)


@FFMPEG
def test_a_trim_cuts_the_clean_render_and_moves_the_captions(tmp_path):
    path, ch = _job(tmp_path, seconds=8)
    burned = []
    url = studio.trim(JOB, mc.channels(), 1.0, 6.0, reburn_fn=burned.append)
    recut = glob.glob(os.path.join(path, "recut_*_Cricket_x_clip_1.mp4"))
    assert len(recut) == 1 and url.endswith(os.path.basename(recut[0])) and burned == [path]
    assert abs(studio.duration(recut[0]) - 5.0) < 0.15
    data = _meta(path)
    segs = data["transcript"]["segments"]
    assert [s["text"] for s in segs] == ["97 innings", "kohli ne 120 mein"]              # words before 1.0 s are gone
    assert segs[1]["start"] == 3.0 and data["shorts"][0]["seconds"] == 5.0
    with pytest.raises(studio.StudioError, match="3 seconds"):
        studio.trim(JOB, mc.channels(), 1.0, 2.0, reburn_fn=burned.append)


def test_approve_skip_and_remake(tmp_path):
    path, ch = _job(tmp_path, make_video=False, review=6)
    assert mc.held_for_review(ch, ch["jobs"][0])
    assert "Approved" in studio.act(JOB, mc.channels(), "approve")
    assert not mc.held_for_review(mc.get(ch["id"]), mc.get(ch["id"])["jobs"][0])
    assert studio.videos(mc.channels())[0]["state"] == "waiting"
    assert "made again next" in studio.act(JOB, mc.channels(), "remake")
    c = mc.get(ch["id"])
    assert c["jobs"][0]["status"] == "skipped" and c["ideas"][0]["text"] == "Babar vs Kohli"
    with pytest.raises(studio.StudioError, match="has not gone up"):
        studio.act(JOB, mc.channels(), "skip")


def test_an_uploaded_video_keeps_its_file(tmp_path):
    _job(tmp_path, make_video=False, status="uploaded")
    with pytest.raises(studio.StudioError, match="already on YouTube"):
        studio.trim(JOB, mc.channels(), 1.0, 6.0, reburn_fn=lambda p: None)
    with pytest.raises(studio.StudioError, match="already on YouTube"):
        studio.save_captions(JOB, mc.channels(), [{"text": "a"}, {"text": "b"}], reburn_fn=lambda p: None)


def test_the_routes_answer(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_module
    _job(tmp_path, make_video=False)
    client = TestClient(app_module.app)
    got = client.get("/api/studio/videos").json()["videos"]
    assert got[0]["job_id"] == JOB
    r = client.put(f"/api/studio/video/{JOB}/details", json={"title": "x" * 120})
    assert r.status_code == 400 and "allows 100" in r.json()["detail"]
    assert client.post(f"/api/studio/video/{JOB}/explode").status_code == 404
    assert client.get("/api/studio/video/not-a-job").status_code == 400
