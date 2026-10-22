"""Script craft and viral remix (22-oct-2026): the doctor's rewrites are kept only when code
agrees, and a viral video is studied, never copied."""
from types import SimpleNamespace

import pytest

import script_craft as craft
import viral_remix as vr


def _story():
    return SimpleNamespace(
        hook_line="Aaj hum baat karenge Babar Azam ke records ki",
        facts=[SimpleNamespace(line="Babar ne 2019 mein 5 centuries banayi thi"),
               SimpleNamespace(line="Unka average 56.7 hai ODI mein")],
        question="Kaun behtar hai, comment mein batao")


FACTS = "Babar Azam scored 5 centuries in 2019. ODI average 56.7. Fastest to 5000 runs in 97 innings."


def test_spoken_lines_come_in_voice_order_and_can_be_limited():
    s = _story()
    assert [p for p, _t in craft.spoken(s)] == ["hook_line", "facts.0", "facts.1", "question"]
    assert [p for p, _t in craft.spoken(s, fields=("hook_line", "question"))] == ["hook_line", "question"]


def test_code_decides_which_rewrites_are_kept():
    old = "Babar ne 2019 mein 5 centuries banayi thi"
    assert craft.line_ok("2019 mein Babar ki 5 centuries, sab hairan", old, FACTS)
    assert not craft.line_ok("2019 mein Babar ki centuries, sab hairan", old, FACTS)      # dropped the 5
    assert not craft.line_ok("2019 mein Babar ki 5 centuries aur 7 fifties", old, FACTS)  # 7 is not researched
    assert not craft.line_ok("2019 mein Babar aur Kohli ki 5 centuries thi", old, FACTS)  # a new name
    assert not craft.line_ok("2019 में Babar ki 5 centuries banayi thi", old, FACTS)     # Devanagari
    assert not craft.line_ok("Dosto, 2019 mein Babar ki 5 centuries", old, FACTS)       # stale opener
    assert craft.banned_hits("Kya aap jaante hain?") == ["kya aap jaante hain"]
    assert craft.banned_hits("swagatam") == []


def test_polish_takes_a_clearly_better_hook_and_keeps_bad_lines(monkeypatch):
    monkeypatch.setenv("POLISH", "1")
    got = craft.Doctored(hook_score=2, hooks=[craft.Hook(text="Sirf 97 innings mein 5000 runs, kisi ne nahi kiya", score=9),
                                               craft.Hook(text="Kohli bhi hairan: 97 innings", score=10)],
                         lines=["x", "Babar ne 2019 mein 5 centuries thok di", "Average sirf 50 hai",
                                "Babar ya Kohli? Comment mein batao"])
    monkeypatch.setattr(craft.kit, "ask_json", lambda *a, **k: got)
    s = craft.polish(object(), _story(), FACTS, log=lambda m: None)
    assert s.hook_line == "Sirf 97 innings mein 5000 runs, kisi ne nahi kiya"   # Kohli is not in the facts
    assert s.facts[0].line == "Babar ne 2019 mein 5 centuries thok di"
    assert s.facts[1].line == "Unka average 56.7 hai ODI mein"                  # 56.7 dropped: kept
    assert s.question == "Kaun behtar hai, comment mein batao"                  # Kohli again: kept


def test_polish_never_breaks_a_video(monkeypatch):
    monkeypatch.setenv("POLISH", "1")

    def boom(*a, **k):
        raise RuntimeError("quota")
    monkeypatch.setattr(craft.kit, "ask_json", boom)
    s = craft.polish(object(), _story(), FACTS, log=lambda m: None)
    assert s.hook_line.startswith("Aaj hum")
    monkeypatch.setenv("POLISH", "0")
    assert craft.polish(object(), _story(), FACTS) .hook_line.startswith("Aaj hum")


CAPTIONS = ("pakistan ke sabse tez bowler ne ek over mein chhe wicket nahi liye lekin jo kiya woh kisi ne socha "
            "nahi tha aur phir stadium khamosh ho gaya jab last ball par woh hua") * 3


def _bp(**kw):
    base = dict(fits=True, reason="", topic="Fastest spells in PSL history", kind="topic",
                angle="the spell nobody remembers", hook_pattern="opens on a number and withholds the name",
                beats=["stakes", "twist", "payoff"], devices=["open loop"], why="rivalry")
    base.update(kw)
    return vr.Blueprint(**base)


def test_a_viral_video_is_studied_and_its_words_never_reach_our_script(monkeypatch):
    def fetch(url, max_seconds=None, info_out=None):
        info_out.update({"id": "abcdefghijk", "title": "Fastest spell ever", "views": 2_100_000,
                         "channel": "Rival", "seconds": 38})
        return {"text": CAPTIONS}
    seen = {}

    def ask(client, schema, prompt, model=None):
        seen["prompt"] = prompt
        return _bp()
    monkeypatch.setattr(vr.kit, "ask_json", ask)
    rec = vr.study(object(), "https://youtube.com/shorts/abcdefghijk", "cricket", log=lambda m: None, fetch=fetch)
    assert rec["topic"] == "Fastest spells in PSL history" and "2,100,000" in seen["prompt"]
    note = vr.note_for("fastest spells in PSL history!")
    assert "the spell nobody remembers" in note and "stadium khamosh" not in note
    with pytest.raises(RuntimeError):
        vr.guard(rec["topic"], "Suno, jo kiya woh kisi ne socha nahi tha aur phir stadium khamosh ho gaya")
    vr.guard(rec["topic"], "Ek spell jo sab bhool gaye, 4 overs mein 5 wicket")
    assert vr.as_idea(rec)["remix"] == "abcdefghijk"
    with pytest.raises(ValueError):            # the same creator again this week
        vr.study(object(), "abcdefghijz", "cricket", fetch=fetch, skip_channels=vr.recent_channels())


def test_unfit_or_captionless_videos_are_refused_and_not_tried_again(monkeypatch):
    monkeypatch.setattr(vr.kit, "ask_json", lambda *a, **k: _bp(fits=False, reason="politics"))
    with pytest.raises(ValueError, match="politics"):
        vr.study(object(), "abcdefghijk", "controversy", fetch=lambda u, **k: {"text": CAPTIONS})
    with pytest.raises(ValueError, match="captions"):
        vr.study(object(), "zzzzzzzzzzz", "cricket", fetch=lambda u, **k: None)
    assert {"abcdefghijk", "zzzzzzzzzzz"} <= vr.studied_ids()
    with pytest.raises(ValueError):
        vr.study(object(), "not a link", "cricket")


def test_auto_idea_takes_the_top_unseen_hit(monkeypatch):
    monkeypatch.setenv("VIRAL_REMIX", "1")
    tried = []

    def study(client, vid, kind, log=print, skip_channels=()):
        tried.append(vid)
        return {"id": vid, "topic": "Babar Azam vs Virat Kohli", "kind": "versus"}
    rows = [{"id": "low00000000", "views": 900}, {"id": "hit00000000", "views": 5_000_000}]
    idea = vr.auto_idea(object(), "cricket", log=lambda m: None, videos=rows, study_fn=study)
    assert tried == ["hit00000000"] and idea["kind"] == "versus" and idea["remix"] == "hit00000000"
    assert vr.auto_idea(object(), "history", videos=rows, study_fn=study) is None


def test_a_pasted_link_becomes_the_next_idea(monkeypatch):
    import my_channels as mc
    monkeypatch.setattr(vr, "study", lambda client, url, kind, **k: {
        "id": "abcdefghijk", "topic": "Shoaib Akhtar vs PCB fine", "kind": "topic"})
    monkeypatch.setattr("short_kit.gemini", lambda: object())
    ch = mc.add("controversy")
    mc.add_idea(ch["id"], "https://www.youtube.com/watch?v=abcdefghijk&t=3")
    idea = mc.get(ch["id"])["ideas"][0]
    assert idea["text"] == "Shoaib Akhtar vs PCB fine" and idea["remix"] == "abcdefghijk" and idea["owner"]
