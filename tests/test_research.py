"""The research agent per niche (owner, 28-oct-2026: "find the most viral content in each niche, see
their videos, get ideas from it and recreate the videos ourselves"): Data API search + creators'
breakouts, Gemini watching by link, a playbook in every script prompt, studied ideas for every kind."""
import pytest

import my_channels as mc
import niche_research as nr
import viral_remix as vr
import yt_api


def _row(vid, views, title="Babar vs Kohli", channel="Rival", cid="UC" + "a" * 22, seconds=30):
    return {"id": vid, "url": f"https://www.youtube.com/watch?v={vid}", "title": title, "channel": channel,
            "channel_id": cid, "channel_url": f"https://www.youtube.com/channel/{cid}", "seconds": seconds,
            "views": views, "licence": "youtube"}


def _study(**kw):
    base = dict(fits=True, reason="", topic="Babar Azam vs Virat Kohli", kind="versus",
                angle="same innings count, different result", hook_pattern="two scorecards side by side",
                beats=["stakes", "twist", "payoff"], devices=["contrast"], why="fan rivalry",
                first_frame="two player cut-outs with giant numbers", visuals="one card, no cuts",
                text_style="huge yellow numbers", audio="beat drop", cta="asks who is better", length_seconds=6,
                transcript="")
    base.update(kw)
    return vr.Study(**base)


def test_iso_lengths_and_the_quota_guard(monkeypatch):
    assert yt_api.seconds("PT1M14S") == 74 and yt_api.seconds("PT8S") == 8 and yt_api.seconds("P0D") == 0
    assert yt_api.seconds("nonsense") is None
    calls = []
    monkeypatch.setattr(yt_api.ya, "_get", lambda url, params: calls.append(url) or {"items": []})
    monkeypatch.setattr(yt_api, "_spent", {})
    monkeypatch.setattr(yt_api, "BUDGET", 150)
    assert yt_api.search("cricket") == []                        # 100 units
    with pytest.raises(yt_api.OutOfQuota):
        yt_api.search("cricket again")                          # 200 > 150
    assert len(calls) == 1
    monkeypatch.setattr(yt_api, "BUDGET", 10_000)
    monkeypatch.setattr(yt_api.ya, "quota_used", lambda: yt_api.CEILING - 50)
    with pytest.raises(yt_api.OutOfQuota):                      # the project's ceiling keeps uploads' share
        yt_api.search("cricket")


def test_find_keeps_real_hits_and_the_breakouts_of_their_creators():
    big = "UC" + "b" * 22

    class Api:
        def search(self, q, **kw):
            return [_row("hit00000001", 2_000_000, cid=big, channel="Big"),
                    _row("edit0000001", 9_000_000, title="Kohli x song edit"),            # no story
                    _row("long0000001", 5_000_000, seconds=600),                           # not a Short
                    _row("low00000001", 900)]

        def channel_uploads(self, cid, n):
            tab = [_row(f"t{i:010d}", 20_000, cid=cid) for i in range(8)]
            return tab + [_row("brk00000001", 800_000, cid=cid)]
    rows, creators = nr.find("cricket", now=1793184000, api=Api(), log=lambda m: None)
    assert [r["id"] for r in rows] == ["hit00000001", "brk00000001"]
    assert creators[big]["best"] == 2_000_000 and creators[big]["read"] == 1793184000
    assert rows[1]["found"].startswith("breakout of")


def test_queries_rotate_by_day():
    a, b = nr.todays_queries("cricket", now=0), nr.todays_queries("cricket", now=86400)
    assert len(a) == 2 and a != b


def test_a_watched_study_keeps_the_transcript_for_the_guard_only(monkeypatch):
    monkeypatch.setenv("VIRAL_WATCH", "1")
    said = "babar ne 97 innings mein jo kiya woh kohli 120 innings mein bhi nahi kar saka aur phir sab"
    rec = vr.study(object(), "abcdefghijk", "cricket", log=lambda m: None, meta=_row("abcdefghijk", 3_000_000),
                   watcher=lambda client, vid, kind, info: _study(transcript=said))
    assert rec["kind"] == "versus" and rec["niche"] == "cricket" and "transcript" not in rec["blueprint"]
    note = vr.note_for(rec["topic"])
    assert "two player cut-outs" in note and "97 innings" not in note
    with pytest.raises(RuntimeError):
        vr.guard(rec["topic"], "Suno babar ne 97 innings mein jo kiya woh kohli 120 innings mein bhi nahi kar saka")


def test_a_study_reads_the_audience_and_never_keeps_the_comments(monkeypatch):
    monkeypatch.setenv("VIRAL_WATCH", "1")
    monkeypatch.setenv("AUDIENCE_RESEARCH", "1")
    got = {"items": [{"snippet": {"topLevelComment": {"snippet": {"textDisplay": t, "likeCount": n}}}}
                     for t, n in (("Do one on Shaheen vs Bumrah next!", 900), ("kohli is overrated  ", 40))]}
    monkeypatch.setattr(yt_api.ya, "_get", lambda url, params: got)
    monkeypatch.setattr(yt_api, "_spent", {})
    seen = {}

    def watcher(client, vid, kind, info):
        seen["comments"] = info.get("top_comments")
        return _study(audience="fans fight over who is overrated", asks=["Shaheen Afridi vs Jasprit Bumrah"])
    rec = vr.study(object(), "abcdefghijk", "cricket", log=lambda m: None,
                   meta={**_row("abcdefghijk", 3_000_000), "comments": 2}, watcher=watcher)
    assert [c["likes"] for c in seen["comments"]] == [900, 40]              # most liked first
    assert seen["comments"][1]["text"] == "kohli is overrated"
    assert rec["blueprint"]["asks"] == ["Shaheen Afridi vs Jasprit Bumrah"]
    assert "Do one on" not in str(rec)                                       # comments themselves are not kept
    assert "fans fight" in vr.note_for(rec["topic"])
    assert nr.asks("cricket") == ["Shaheen Afridi vs Jasprit Bumrah"]
    assert "commenters: fans fight" in nr._study_line(rec)


def test_the_planner_hears_what_viewers_of_viral_videos_asked_for(monkeypatch):
    import cricket_shorts
    ch = mc.add("cricket")
    monkeypatch.setattr(nr, "asks", lambda niche: ["Shaheen vs Bumrah"] if niche == "cricket" else [])
    seen = {}

    def ideas(client, count=2, avoid=(), best=(), worst=(), requests=()):
        seen["requests"] = list(requests)
        return [{"kind": "versus", "text": "Shaheen Afridi vs Jasprit Bumrah T20I"}]
    monkeypatch.setattr(cricket_shorts, "channel_ideas", ideas)
    mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert seen["requests"] == ["Shaheen vs Bumrah (asked under a viral video in this niche)"]


def test_comments_off_or_a_comment_failure_still_studies(monkeypatch):
    def refuse(url, params):
        raise RuntimeError("commentsDisabled")
    monkeypatch.setattr(yt_api.ya, "_get", refuse)
    monkeypatch.setattr(yt_api, "_spent", {})
    assert yt_api.comments("abcdefghijk") == []
    prompt = vr.WATCH_PROMPT.format(views=1, title="t", channel="c", what="w", rules="r", topic_rule="x", comments="")
    assert "VIEWER COMMENTS" not in prompt and "asks:" in prompt


def test_a_failed_watch_falls_back_to_the_captions(monkeypatch):
    import youtube_captions
    monkeypatch.setenv("VIRAL_WATCH", "1")
    monkeypatch.setattr(youtube_captions, "fetch", lambda url, max_seconds=None, info_out=None: {"text": "word " * 40})
    monkeypatch.setattr(vr.kit, "ask_json", lambda *a, **k: vr.Blueprint(
        fits=True, reason="", topic="Fastest spells in PSL", kind="topic", angle="a", hook_pattern="h",
        beats=["b"], devices=["d"], why="w"))
    notes = []

    def broken(*a):
        raise RuntimeError("video not reachable")
    rec = vr.study(object(), "abcdefghijk", "cricket", log=notes.append, meta=_row("abcdefghijk", 1), watcher=broken)
    assert rec["topic"] == "Fastest spells in PSL" and "reading its captions" in notes[0]


def test_quiz_and_music_studies_carry_our_formats_and_styles(monkeypatch):
    monkeypatch.setenv("VIRAL_WATCH", "1")
    rec = vr.study(object(), "abcdefghijk", "quiz", meta=_row("abcdefghijk", 1),
                   watcher=lambda *a: _study(topic="Capitals of Asia", kind="flags quiz"))
    assert rec["kind"] == "mcq"                                  # not one of ours: the first format
    rec = vr.study(object(), "abcdefghijz", "music", meta=_row("abcdefghijz", 1, channel="Other"),
                   watcher=lambda *a: _study(topic="missing her at 3 am", kind="sad piano ballad"))
    assert rec["kind"] == "sad piano ballad"
    assert "{styles}" not in vr._topic_rule("music") and "lo-fi chill" in vr._topic_rule("music")


def test_a_pass_studies_builds_the_playbook_and_never_raises(monkeypatch):
    class Api:
        def search(self, q, **kw):
            return [_row(f"v{i:010d}", 3_000_000 - i, channel=f"C{i}", cid="UC" + str(i) * 22) for i in range(5)]

        def channel_uploads(self, cid, n):
            return []
    made = []

    def study_fn(client, vid, niche, log=print, skip_channels=(), meta=None):
        return vr.study(client, vid, niche, log=log, skip_channels=skip_channels, meta=meta,
                        watcher=lambda *a: made.append(vid) or _study(topic=f"Topic {vid}"))
    monkeypatch.setenv("VIRAL_WATCH", "1")
    monkeypatch.setattr(nr, "STUDIES_PER_RUN", 3)
    asked = {}

    def ask(client, schema, prompt, model=None):
        if schema is nr.Picks:          # the title screen keeps all but the last find
            return nr.Picks(videos=[nr.Pick(id=f"v{i:010d}", keep=i < 4) for i in range(5)])
        asked["prompt"] = prompt
        return nr.Playbook(topics=["records only one player holds"], hooks=["two numbers side by side"],
                           structure="contrast then payoff", length="6-20 s", on_screen=["giant numbers"],
                           audio="beat drop", endings=["who is better?"], titles=["A vs B: same balls"],
                           avoid=["slow intros"])
    monkeypatch.setattr(nr.kit, "ask_json", ask)
    out = nr.run("cricket", object(), log=lambda m: None, now=1793184000, api=Api(), study_fn=study_fn,
                 ours="41 videos, median 4 views")
    assert len(made) == 3 and out["playbook"] and "median 4 views" in asked["prompt"]
    text = nr.playbook_text("cricket")
    assert "6-20 s" in text and "two numbers side by side" in text and text.startswith("WHAT WINS")
    assert not nr.due("cricket", now=1793184000 + 3600) and nr.due("cricket", now=1793184000 + 21 * 3600)

    class Down:
        def search(self, q, **kw):
            raise yt_api.OutOfQuota("used")

        def channel_uploads(self, cid, n):
            raise yt_api.OutOfQuota("used")
    assert nr.run("quiz", object(), log=lambda m: None, api=Down())["found"] == 0


def test_studied_ideas_are_offered_once_and_never_for_quran_or_comedy(monkeypatch):
    monkeypatch.setenv("VIRAL_WATCH", "1")
    vr.study(object(), "abcdefghijk", "cricket", meta=_row("abcdefghijk", 5),
             watcher=lambda *a: _study(topic="Babar Azam vs Virat Kohli"))
    idea = nr.next_idea("cricket", used=[])
    assert idea["text"] == "Babar Azam vs Virat Kohli" and idea["remix"] == "abcdefghijk"
    assert nr.next_idea("cricket") is None                      # taken
    vr.study(object(), "abcdefghijz", "quran", meta=_row("abcdefghijz", 5, channel="Q"),
             watcher=lambda *a: _study(topic="Surah Ar-Rahman", kind="quran"))
    assert nr.next_idea("quran") is None and nr.next_idea("comedy") is None


def test_channels_take_one_studied_idea_a_day_and_carry_the_playbook(monkeypatch):
    monkeypatch.setenv("RESEARCH", "1")
    monkeypatch.setenv("VIRAL_REMIX", "1")
    monkeypatch.setenv("VIRAL_WATCH", "1")
    vr.study(object(), "abcdefghijk", "quiz", meta=_row("abcdefghijk", 5),
             watcher=lambda *a: _study(topic="Prophets named in the Quran", kind="islamic"))
    data = nr.load("quiz")
    data["playbook"] = {"topics": ["Islamic GK"], "hooks": ["only 1% get all 3"], "structure": "fast",
                        "length": "15-25 s", "on_screen": [], "audio": "", "endings": ["comment your score"],
                        "titles": ["Sirf genius 3/3"], "avoid": []}
    nr._save("quiz", data)
    q = mc.add("quiz")
    payload, meta = mc.next_payload(mc.get(q["id"]), lambda: None)
    assert payload["quiz_format"] == "islamic" and payload["quiz_topic"] == "Prophets named in the Quran"
    assert "only 1% get all 3" in payload["niche_playbook"]
    payload, _ = mc.next_payload(mc.get(q["id"]), lambda: None)
    assert payload["quiz_topic"] != "Prophets named in the Quran"      # one a day


def test_the_research_pass_runs_one_due_niche_per_tick(monkeypatch):
    monkeypatch.setenv("RESEARCH", "1")
    ran = []
    monkeypatch.setattr(nr, "run", lambda niche, client, log=print, now=None, ours="", ours_files=None:
                        ran.append(niche))
    assert mc.research_pass(["cricket", "quiz"], lambda: object(), log=lambda m: None) == "comedy"
    assert ran == ["comedy"]
    monkeypatch.setenv("RESEARCH", "0")
    assert mc.research_pass(["cricket"], lambda: object()) is None


def test_niche_of_cards():
    assert mc.niche_of({"id": "main"}) == "comedy"
    assert mc.niche_of({"id": "h", "kind": "history", "mode": "explainer"}) == "explainer"
    assert mc.niche_of({"id": "h", "kind": "history"}) == "history"
    assert mc.niche_of({"id": "c", "kind": "cricket"}) == "cricket"


def test_the_playbook_reaches_the_script_rules(monkeypatch):
    import script_craft as craft
    monkeypatch.delenv("NICHE_PLAYBOOK", raising=False)
    assert craft.playbook() == ""
    monkeypatch.setenv("NICHE_PLAYBOOK", "WHAT WINS IN THIS NICHE NOW:\n- Length: 6-20 s")
    assert "6-20 s" in craft.short_rules() and "6-20 s" in craft.long_rules()


def test_the_licence_comes_from_the_data_api(monkeypatch):
    import channel_tools
    monkeypatch.setattr(channel_tools, "_cache", {})
    monkeypatch.setattr(yt_api, "videos", lambda ids: [{**_row(ids[0], 10), "licence": "creativeCommon"}])
    assert channel_tools.licence("https://www.youtube.com/watch?v=abcdefghijk")["licence"] == "creative_commons"
    monkeypatch.setattr(channel_tools, "_cache", {})
    monkeypatch.setattr(yt_api, "videos", lambda ids: [{**_row(ids[0], 10), "licence": "youtube"}])
    assert channel_tools.licence("https://www.youtube.com/watch?v=abcdefghijk")["licence"] == "standard"
