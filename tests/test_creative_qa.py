"""creative_qa: a vision look at every finished video before it uploads unattended (29-oct-2026)."""
import io
import json
import shutil
import subprocess

import pytest

import creative_qa as cq
import my_channels as mc
import youtube_account as ya

FFMPEG = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def _verdict(*issues, first=7, polish=8):
    return cq.Verdict(first_frame=first, polish=polish, best_fix="bigger hook text",
                      issues=[cq.Issue(kind=k, frame=f, detail=d, severity=s) for k, f, d, s in issues])


@FFMPEG
def test_pictures_are_the_first_frame_and_a_numbered_sheet(tmp_path):
    from PIL import Image
    video = str(tmp_path / "v.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=30:duration=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", video], check=True)
    first, sheet = cq.pictures(video)
    a, b = Image.open(io.BytesIO(first)), Image.open(io.BytesIO(sheet))
    assert a.size == (540, 960)
    assert b.width == 4 * (270 + 6) + 6 and b.height == 3 * (480 + 6) + 6       # 12 portrait cells, 4 a row


def test_only_a_defect_both_looks_call_broken_holds_the_video_back(monkeypatch):
    monkeypatch.setattr(cq, "pictures", lambda path: (b"first", b"sheet"))
    monkeypatch.setattr(cq, "_shape", lambda first: "vertical Short", raising=False)
    looks = iter([_verdict(("cut_text", 4, "'7 SEPT 201' is cut", "broken"), ("unreadable", 2, "dim", "broken")),
                  _verdict(("cut_text", 4, "the date is cut", "broken"))])
    got = cq.review("v.mp4", "T", "controversy", look=lambda f, s, p: next(looks))
    assert got["blocked"] == ["cut_text"] and "7 SEPT 201" in got["reason"]   # "unreadable" never blocks
    rows = [json.loads(line) for line in open(cq.LOG, encoding="utf-8")]
    assert rows[-1]["blocked"] == ["cut_text"] and rows[-1]["kind"] == "controversy"

    looks = iter([_verdict(("garbage", 6, "streaks", "broken")), _verdict()])
    assert cq.review("v.mp4", "T", "quiz", look=lambda f, s, p: next(looks))["blocked"] == []   # second look disagrees

    def down(f, s, p):
        raise RuntimeError("503 UNAVAILABLE")
    assert cq.review("v.mp4", "T", "quiz", look=down) is None                  # the check could not run
    digest = cq.digest()
    assert digest["controversy"]["videos"] == 1 and digest["controversy"]["issues"]["cut_text"] == 1


def test_the_week_report_carries_each_channels_look(monkeypatch):
    import reminders
    monkeypatch.setattr(cq, "pictures", lambda path: (b"first", b"sheet"))
    monkeypatch.setattr(cq, "_shape", lambda first: "vertical Short")
    for issue in (("overlap", 2, "title over photo", "minor"), ("overlap", 5, "x", "minor")):
        cq.review("v.mp4", "T", "quiz", look=lambda f, s, p, i=issue: _verdict(i, first=6, polish=7))
    assert reminders.look_line("quiz") == ("  Looks (2 checked): first frame 6.0/10, polish 7.0/10; "
                                           "seen most: overlap (2x).")
    assert reminders.look_line("music") == ""


def test_the_prompt_expects_each_channels_scripts():
    p = cq.PROMPT.format(shape="vertical Short", channel="Holy Quran", title="t", n=12, scripts=cq.SCRIPTS["quran"])
    assert "Arabic script" in p and "placeholders" in p


def _job(monkeypatch, verdict):
    monkeypatch.setenv("CREATIVE_QA", "1")
    ch = mc.add("quiz")
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "q1", "status": "done", "format": "mcq", "at": 1}]))
    monkeypatch.setattr(ya, "status", lambda: {"connected": True})
    monkeypatch.setattr(cq, "review", lambda path, title, kind, name="": verdict)
    return ch


def test_a_broken_video_is_held_back_before_upload(monkeypatch):
    ch = _job(monkeypatch, {"blocked": ["boxes"], "reason": "boxes (frame 3): squares for letters",
                            "first_frame": 5, "polish": 4})
    monkeypatch.setattr(ya, "upload", lambda *a, **k: pytest.fail("a broken video must not go up"))
    clip = {"index": 0, "path": "p.mp4", "title": "T", "description": "D", "tags": []}
    mc.upload_waiting(mc.get(ch["id"]), lambda job: ("completed", [clip]), log=lambda *a: None)
    job = mc.get(ch["id"])["jobs"][0]
    assert job["status"] == "failed" and job["error"].startswith("visual check: boxes")


def test_report_mode_and_a_clean_video_go_up_with_their_scores(monkeypatch):
    ch = _job(monkeypatch, {"blocked": ["boxes"], "reason": "boxes", "first_frame": 5, "polish": 4})
    monkeypatch.setenv("CREATIVE_QA", "report")
    sent = []

    def upload(path, title, desc, tags, genre, publish_at=None, ai_made=False, meta=None, **kw):
        sent.append(title)
        return {"status": "done", "video_id": "AbCdEfGhIjK", "title": title}
    monkeypatch.setattr(ya, "upload", upload)
    clip = {"index": 0, "path": "p.mp4", "title": "T", "description": "D", "tags": []}
    mc.upload_waiting(mc.get(ch["id"]), lambda job: ("completed", [clip]), log=lambda *a: None)
    job = mc.get(ch["id"])["jobs"][0]
    assert sent == ["T"] and job["look"] == "first frame 5/10, polish 4/10"
