"""AI edits from the phone (4-nov-2026): a Telegram reply to a review note or to an edited video starts
the AI editor on that video, and the new version (or why not) goes back to Telegram."""
import os

import pytest

import my_channels as mc
import telegram_notify as tn

JOB = "0f8d9c2a-1b2c-4d3e-8f4a-5b6c7d8e9f01"
OWNER = 4242


def _updates(monkeypatch, updates):
    sent, answered = [], []
    monkeypatch.setattr(tn, "_load", lambda: {"chat_id": OWNER, "offset": 0})
    monkeypatch.setattr(tn, "_save", lambda data: None)
    monkeypatch.setattr(tn, "_token", lambda: "t")

    def call(method, timeout=30, **kw):
        if method == "getUpdates":
            return updates
        if method == "answerCallbackQuery":
            answered.append(kw["data"]["text"])
        return {}
    monkeypatch.setattr(tn, "_call", call)
    monkeypatch.setattr(tn, "send_text", lambda text, buttons=None: sent.append(text))
    return sent, answered


def test_poll_hands_owner_replies_to_the_editor_and_ignores_the_rest(monkeypatch):
    note = f"Quiz: \"Q\" is ready...\nref {JOB}"
    sent, answered = _updates(monkeypatch, [
        {"update_id": 1, "message": {"chat": {"id": OWNER}, "text": "captions peele karo",
                                     "reply_to_message": {"text": note}}},
        {"update_id": 2, "message": {"chat": {"id": 999}, "text": "hack", "reply_to_message": {"text": note}}},
        {"update_id": 3, "message": {"chat": {"id": OWNER}, "text": "hello"}},              # not a reply
        {"update_id": 4, "callback_query": {"id": "q", "data": f"skip:c:{JOB}",
                                            "message": {"chat": {"id": OWNER}}}},
    ])
    got = []
    n = tn.poll(lambda data: "pressed " + data, on_text=lambda text, replied: got.append((text, replied)) or "ok")
    assert got == [("captions peele karo", note)]            # only the owner's reply
    assert n == 2 and sent == ["ok", f"pressed skip:c:{JOB}"] and answered == [f"pressed skip:c:{JOB}"]


def test_poll_without_a_text_handler_is_unchanged(monkeypatch):
    sent, _ = _updates(monkeypatch, [{"update_id": 1, "message": {"chat": {"id": OWNER}, "text": "x",
                                                                  "reply_to_message": {"text": f"ref {JOB}"}}}])
    assert tn.poll(lambda d: "p") == 0 and sent == []


def _channels(monkeypatch, status="done"):
    rows = [{"id": "quiz1", "name": "Quiz", "jobs": [{"job_id": JOB, "status": status}]}]
    monkeypatch.setattr(mc, "channels", lambda: rows)


def test_a_reply_starts_that_videos_edit(monkeypatch):
    _channels(monkeypatch)
    started = []
    monkeypatch.setattr(mc, "start_ai_edit", lambda job_id, prompt: started.append((job_id, prompt)))
    answer = mc.telegram_reply("pehle 2 second kaato", f"Quiz: ready\n{mc.PHONE_EDIT_HINT}\nref {JOB}")
    assert started == [(JOB, "pehle 2 second kaato")] and answer.startswith("Working on it")
    assert mc.telegram_reply("x", "a note without a ref") == ""                 # not ours: silent
    assert "no longer" in mc.telegram_reply("x", "ref 11111111-2222-4333-8444-555555555555")


def test_a_reply_says_why_not(monkeypatch):
    from fastapi import HTTPException
    for status, words in (("skipped", "was skipped"), ("failed", "was failed")):
        _channels(monkeypatch, status)
        monkeypatch.setattr(mc, "start_ai_edit", lambda *a: pytest.fail("must not start"))
        assert words in mc.telegram_reply("x", f"ref {JOB}")
    _channels(monkeypatch, "uploaded")
    monkeypatch.setattr(mc, "start_ai_edit", lambda *a: None)
    assert "only the title" in mc.telegram_reply("better title", f"ref {JOB}")

    def busy(*a):
        raise HTTPException(status_code=409, detail="An edit of this video is still running.")
    _channels(monkeypatch)
    monkeypatch.setattr(mc, "start_ai_edit", busy)
    assert "still running" in mc.telegram_reply("x", f"ref {JOB}")
    monkeypatch.setattr(mc, "start_ai_edit", None)
    assert "not running" in mc.telegram_reply("x", f"ref {JOB}")


def test_the_review_note_carries_the_ref_and_the_hint(monkeypatch):
    sent = []
    monkeypatch.setattr(tn, "status", lambda: {"connected": True})
    monkeypatch.setattr(tn, "send_text", lambda text, buttons=None: sent.append((text, buttons)))
    ch = {"id": "quiz1", "name": "Quiz", "review_hours": 3}
    mc._tell_review(ch, [JOB], lambda j: ("done", [{"title": "Kaun jeeta?"}]))
    text, buttons = sent[0]
    assert f"ref {JOB}" in text and mc.PHONE_EDIT_HINT in text and buttons == [("Skip this video", f"skip:quiz1:{JOB}")]
    assert mc._REF.search(text).group(1) == JOB


def test_the_result_goes_back_to_the_phone(monkeypatch, tmp_path):
    import app
    import studio
    videos, texts = [], []
    monkeypatch.setattr(tn, "status", lambda: {"connected": True})
    monkeypatch.setattr(tn, "send_video", lambda path, caption="": videos.append((path, caption)))
    monkeypatch.setattr(tn, "send_text", lambda text, buttons=None: texts.append(text))
    monkeypatch.setattr(studio, "job_dir", lambda j: str(tmp_path))
    monkeypatch.setattr(studio, "served", lambda p, index=0: os.path.join(p, "v.mp4"))
    app._tell_phone_edit(JOB, {"ok": True, "file_changed": True, "summary": "Captions peele",
                               "notes": [], "check": {"problems": ["text cut off"]}})
    path, caption = videos[0]
    assert path.endswith("v.mp4") and caption.startswith("Done: Captions peele") and f"ref {JOB}" in caption
    assert "text cut off" in caption

    def too_big(path, caption=""):
        raise RuntimeError("The video is over Telegram's 50 MB limit; watch it in Shortkaar's Studio.")
    monkeypatch.setattr(tn, "send_video", too_big)
    app._tell_phone_edit(JOB, {"ok": True, "file_changed": True, "summary": "Long one"})
    assert texts[-1].startswith("Done: Long one") and "50 MB" in texts[-1] and f"ref {JOB}" in texts[-1]
    app._tell_phone_edit(JOB, {"ok": False, "message": "Could not find that moment."})
    assert texts[-1].startswith("Could not do that: Could not find that moment.")
    app._tell_phone_edit(JOB, {"ok": True, "file_changed": False, "summary": "Naya title", "details": ["title"]})
    assert texts[-1].startswith("Done: Naya title")


def test_the_phone_hook_needs_the_running_loop(monkeypatch):
    import app
    monkeypatch.setattr(app, "_main_loop", None)
    with pytest.raises(RuntimeError):
        app._phone_ai_edit(JOB, "x")


def test_the_phone_hook_starts_the_edit_on_the_event_loop_thread(monkeypatch):
    import asyncio
    import threading
    import app
    calls = []

    def fake_start(job_id, prompt, phone=False):
        calls.append((job_id, prompt, phone, threading.get_ident()))
        return {"started": True}
    monkeypatch.setattr(app, "_start_ai_edit", fake_start)

    async def main():
        monkeypatch.setattr(app, "_main_loop", asyncio.get_running_loop())
        await asyncio.to_thread(app._phone_ai_edit, JOB, "zoom karo")      # as the Telegram poll does
        return threading.get_ident()
    loop_thread = asyncio.run(main())
    assert calls == [(JOB, "zoom karo", True, loop_thread)]


def test_suggest_from_the_phone_sends_buttons_and_a_tap_applies_one(monkeypatch, tmp_path):
    import json
    import ai_editor
    import studio
    _channels(monkeypatch)
    started, sent = [], []
    monkeypatch.setattr(mc, "start_ai_edit", lambda job_id, prompt: started.append((job_id, prompt)))
    items = [{"text": "Pehle 1 second kaat do", "why": "khamoshi"}, {"text": "'15000' par ding", "why": ""}]
    monkeypatch.setattr(ai_editor, "suggest", lambda job_id: {"items": items})
    monkeypatch.setattr(tn, "send_text", lambda text, buttons=None, rows=False: sent.append((text, buttons, rows)))
    assert mc.telegram_reply("Suggest?", f"ref {JOB}") == ""            # the buttons are the answer
    text, buttons, rows = sent[0]
    assert rows and buttons == [("1. Pehle 1 second kaat do", f"ed:{JOB}:0"), ("2. '15000' par ding", f"ed:{JOB}:1")]
    assert f"ref {JOB}" in text and "(khamoshi)" in text and not started
    assert all(len(d.encode()) <= 64 for _l, d in buttons)                # Telegram's callback_data limit
    # the tap: suggest.json in the job's edits folder holds the texts
    job = tmp_path / JOB
    (job / ai_editor.EDITS).mkdir(parents=True)
    (job / ai_editor.EDITS / "suggest.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    monkeypatch.setattr(studio, "job_dir", lambda j: str(tmp_path / j))
    answer = mc.telegram_press(f"ed:{JOB}:1")
    assert started == [(JOB, "'15000' par ding")] and answer.startswith("Working on it")
    assert "gone" in mc.telegram_press(f"ed:{JOB}:7")
    monkeypatch.setattr(ai_editor, "suggest", lambda job_id: {"items": []})
    assert "nothing to suggest" in mc.telegram_reply("ideas", f"ref {JOB}")


def test_buttons_one_per_row(monkeypatch):
    got = {}
    monkeypatch.setattr(tn, "_chat", lambda: OWNER)
    monkeypatch.setattr(tn, "_call", lambda method, **kw: got.update(kw["data"]))
    import json
    tn.send_text("x", buttons=[("a", "1"), ("b", "2")], rows=True)
    assert json.loads(got["reply_markup"])["inline_keyboard"] == [[{"text": "a", "callback_data": "1"}],
                                                                   [{"text": "b", "callback_data": "2"}]]
    tn.send_text("x", buttons=[("a", "1"), ("b", "2")])
    assert len(json.loads(got["reply_markup"])["inline_keyboard"]) == 1    # the old single row
