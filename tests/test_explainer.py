"""The long channel's explainer mode (owner, 21-oct-2026: the history videos
got no views): hot topics planned from rival channels, stale news dropped,
the top videos studied but never copied, and the wiring from the card to the job."""
import time

import pytest

import history_videos as hv
import my_channels as mc
import trend_explainer as te
from tests.test_history import _script


def test_news_ideas_go_stale_but_the_owners_stay():
    now = time.time()
    ideas = [{"text": "new", "at": now - 3600}, {"text": "old", "at": now - (te.IDEA_HOURS + 1) * 3600},
             {"text": "history idea with no time"}, {"text": "mine", "owner": True}]
    assert [i["text"] for i in te.fresh(ideas, now)] == ["new", "mine"]


def test_eight_words_in_a_row_from_another_video_count_as_copied():
    theirs = "Houthis ne Saudi Arabia ke oil plant par drone se hamla kiya aur duniya hil gayi"
    assert te.copied_runs("Kal raat Houthis ne Saudi Arabia ke oil plant par drone se hamla kiya", [theirs])
    assert not te.copied_runs("Houthis ne Saudi Arabia ke oil plant ko nuqsan hua", [theirs])  # 7 in a row is not
    assert not te.copied_runs("anything", ["हूती ने सऊदी अरब पर हमला किया"])                # other scripts never match


def test_the_explainer_script_learns_from_rivals_and_is_rewritten_when_it_copies(monkeypatch):
    prompts, checks = [], []
    copied_line = "this is a sentence that the other creator said in their video"
    scripts = iter([_script(outro=copied_line), _script()])

    def ask(client, schema, prompt, model=None):
        if schema is hv.Script:
            prompts.append(prompt)
            return next(scripts)
        checks.append(prompt)
        return hv.Check(ok=True, problems=[])
    monkeypatch.setattr(hv.kit, "ask_json", ask)
    research = lambda client, topic, minutes, prompts_=None: ("facts " * 50, "extra", [("a", "u")] * 3)  # noqa: E731
    study = lambda client, topic: {"notes": "They open on the drone strike.", "titles": ["Rival title (1,000 views)"],  # noqa: E731
                                   "texts": [copied_line]}
    script, _f, _s = hv.write(None, "Houthis vs Saudi", "@h", 1, mode="explainer", research_fn=research,
                              study_fn=study, keywords_fn=lambda topic, client=None: ["houthi attacks saudi"])
    assert len(prompts) == 2
    assert "They open on the drone strike." in prompts[0] and "houthi attacks saudi" in prompts[0]
    assert "Rival title" in prompts[0] and "reports ke mutabiq" in prompts[0]
    assert "word for word" in prompts[1]                       # the rewrite is told what it copied
    assert "REPORTED or ALLEGED told as confirmed" in checks[0]
    assert script.outro != copied_line


def test_a_script_that_still_copies_after_the_rewrite_is_not_made(monkeypatch):
    copied_line = "this is a sentence that the other creator said in their video"
    monkeypatch.setattr(hv.kit, "ask_json", lambda c, schema, p, model=None: (
        _script(outro=copied_line) if schema is hv.Script else hv.Check(ok=True, problems=[])))
    with pytest.raises(RuntimeError, match="another creator"):
        hv.write(None, "t", "@h", 1, mode="explainer",
                 research_fn=lambda *a: ("facts " * 50, "extra", [("a", "u")] * 3),
                 study_fn=lambda c, t: {"texts": [copied_line]}, keywords_fn=lambda t, c=None: [])


def test_history_mode_is_untouched(monkeypatch):
    prompts = []
    monkeypatch.setattr(hv.kit, "ask_json", lambda c, schema, p, model=None: (
        prompts.append(p) or _script() if schema is hv.Script else hv.Check(ok=True, problems=[])))
    hv.write(None, "Rome", "@h", 1, research_fn=lambda *a: ("facts " * 50, "extra", [("a", "u")] * 3))
    assert "youtube documentary" in prompts[0].lower() and "reports ke mutabiq" not in prompts[0]


def test_the_planner_switches_with_the_mode(monkeypatch):
    called = {}
    monkeypatch.setattr(te, "channel_ideas", lambda *a, **k: called.setdefault("explainer", [{"text": "x"}]))
    assert hv.channel_ideas(None, 2, mode="explainer") == [{"text": "x"}]


def test_the_card_switches_to_explainer_and_the_job_follows(monkeypatch):
    ch = mc.add("history")
    mc._change(ch["id"], lambda c: c.update(ideas=[{"kind": "topic", "text": "Rome"}]))
    ch = mc.update(ch["id"], {"mode": "explainer", "minutes": 12})
    assert ch["mode"] == "explainer" and ch["ideas"] == []        # history ideas are not news
    assert mc.summary(mc.get(ch["id"]))["mode"] == "explainer"
    assert not mc.today_short_due(mc.get(ch["id"]))              # "Aaj ki tareekh" is a history Short
    assert mc.engage_kind(mc.get(ch["id"])) == "explainer"
    asked = {}

    def ideas(client, count, avoid, best, worst, **kw):
        asked.update(kw)
        return [{"kind": "topic", "text": "Why Houthis attacked Saudi Arabia", "at": time.time()}]
    monkeypatch.setattr(hv, "channel_ideas", ideas)
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert asked["mode"] == "explainer" and payload["history_mode"] == "explainer"
    assert payload["history_topic"].startswith("Why Houthis")


def test_stale_news_is_planned_again(monkeypatch):
    ch = mc.add("history")
    mc.update(ch["id"], {"mode": "explainer"})
    mc._change(ch["id"], lambda c: c.update(ideas=[{"kind": "topic", "text": "Old news", "at": 1}]))
    monkeypatch.setattr(hv, "channel_ideas", lambda *a, **k: [{"kind": "topic", "text": "Fresh news",
                                                               "at": time.time()}])
    payload, _meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["history_topic"] == "Fresh news"


def test_explainer_words_for_comments_playlists_and_the_description():
    import engage
    assert engage.PLAYLISTS[("explainer", None)] and engage.PLAYLISTS[("explainer", "teaser")]
    assert "explainer" in engage.FIRST_COMMENTS and "explainer" in engage.WHO
    text = hv.describe(_script(tags=["Houthis"]), [("Shuruaat", 0.0)], [], [], "@h", "urdu", False, mode="explainer")
    assert te.FOLLOW["urdu"] in text and "#explained" in text and "#history" not in text
    assert "tareekhi" not in hv.describe(_script(), [], [], [], "@h", "urdu", False, mode="explainer")


def test_process_passes_the_mode_to_the_job(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    mc.add("history")
    r = TestClient(app_module.app).post("/api/process", json={
        "genre": "history", "channel": "history", "history_topic": "Why Houthis attacked Saudi Arabia",
        "history_mode": "explainer", "acknowledged": True}, headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 200, r.text
    assert app_module.jobs[r.json()["job_id"]]["env"]["HISTORY_MODE"] == "explainer"


def test_keyword_seeds_come_from_the_model_and_fall_back_to_the_topic():
    class C:
        class models:
            @staticmethod
            def generate_content(model, contents):
                return type("R", (), {"text": "1. houthi attacks saudi\nsaudi houthi war\nx"})()
    assert te.seeds("Why Houthis attacked Saudi Arabia", C()) == ["houthi attacks saudi", "saudi houthi war"]
    assert te.seeds("Why Houthis attacked Saudi Arabia") == ["Why Houthis attacked"]
