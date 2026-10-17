"""Engagement after posting, reminders, the Today page and the new content
kinds (player vs player, fast match results, flag quiz, quiz numbers)."""
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone

import pytest

import engage
import my_channels as mc
import reminders
import youtube_account as ya


@pytest.fixture(autouse=True)
def _main(tmp_path, monkeypatch):
    monkeypatch.setattr(ya, "TOKEN_FILE", str(tmp_path / "main_token.json"))
    monkeypatch.setattr(ya, "UPLOADS_FILE", str(tmp_path / "main_uploads.json"))


def _connect(acct, cid="UC_x", handle="@x"):
    with ya.use(acct):
        ya._write(ya.token_file(), {"access_token": "t", "refresh_token": "r", "expires_at": 9e12,
                                    "channel": {"id": cid, "title": cid, "handle": handle}})


class FakeYouTube:
    """videos / commentThreads / comments / playlists, as the API answers them."""

    def __init__(self, public=(), comments=None):
        self.public, self.comments, self.posts = set(public), comments or {}, []

    def get(self, url, params):
        if url.endswith("/videos"):
            return {"items": [{"id": i, "status": {"privacyStatus": "public" if i in self.public else "private"}}
                              for i in params["id"].split(",")]}
        if url.endswith("/commentThreads"):
            return {"items": self.comments.get(params["videoId"], [])}
        if url.endswith("/playlists"):           # the channel's playlists: the ones made here
            return {"items": [{"id": f"new{k + 1}", "snippet": {"title": b["snippet"]["title"]}}
                              for k, (kind, b) in enumerate(self.posts) if kind == "playlists"]}
        if url.endswith("/playlistItems"):
            return {"items": [{"contentDetails": {"videoId": b["snippet"]["resourceId"]["videoId"]}}
                              for kind, b in self.posts
                              if kind == "playlistItems" and b["snippet"]["playlistId"] == params["playlistId"]]}
        raise AssertionError(url)

    def post(self, url, params, body):
        self.posts.append((url.rsplit("/", 1)[1], body))
        return {"id": f"new{len(self.posts)}"}


@pytest.fixture
def fake(monkeypatch):
    yt = FakeYouTube()
    monkeypatch.setattr(ya, "_get", yt.get)
    monkeypatch.setattr(engage, "_post", lambda url, params, body: (ya.spend(50), yt.post(url, params, body))[1])
    return yt


def _row(vid, minutes_ago=60, **kw):
    at = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    return {"id": vid, "video_id": vid, "status": "done", "created": time.time() - 3600, "publish_at": at,
            "title": f"Short {vid}", **kw}


# ------------------------------------------------------------- engagement

def test_first_comment_only_on_public_shorts_once_with_their_question(fake):
    fake.public = {"A"}
    for r in (_row("A", question="Kaun behtar? 👇"), _row("B"), _row("C", minutes_ago=-60)):
        ya._save_upload(r)
    assert engage.first_comments(None, "cricket", lambda *a: None) == 1
    kind, body = fake.posts[0]
    assert kind == "commentThreads" and body["snippet"]["videoId"] == "A"
    text = body["snippet"]["topLevelComment"]["snippet"]["textOriginal"]
    assert text.startswith("Kaun behtar? 👇") and "follow" in text.lower()
    assert engage.first_comments(None, "cricket", lambda *a: None) == 0   # never twice
    assert ya.quota_used() >= 50


def test_engagement_stops_at_the_quota_budget(fake, monkeypatch):
    fake.public = {"A"}
    ya._save_upload(_row("A"))
    ya.spend(engage.QUOTA_BUDGET)
    assert engage.first_comments(None, "quiz", lambda *a: None) == 0 and fake.posts == []


def test_replies_go_to_new_viewer_comments_with_the_quiz_answers(fake, monkeypatch):
    acct = mc.account(mc.add("quiz")["id"])
    with ya.use(acct):
        ya._save_upload(_row("Q", answers=["Markhor", "Indus"]))
    fake.comments = {"Q": [
        {"snippet": {"totalReplyCount": 0, "topLevelComment": {"id": "c1", "snippet": {
            "textDisplay": "markhor aur indus! 2/2", "authorChannelId": {"value": "UC_viewer"}}}}},
        {"snippet": {"totalReplyCount": 0, "topLevelComment": {"id": "c2", "snippet": {
            "textDisplay": "first comment from us", "authorChannelId": {"value": "UC_me"}}}}},
        {"snippet": {"totalReplyCount": 3, "topLevelComment": {"id": "c3", "snippet": {
            "textDisplay": "answered already", "authorChannelId": {"value": "UC_v2"}}}}}]}
    seen = {}

    class Models:
        def generate_content(self, model, contents, config):
            seen["prompt"] = contents
            return type("R", (), {"text": json.dumps({"replies": [{"id": "c1", "reply": "Bilkul sahi! 🎉", "skip": False}]})})()
    client = type("C", (), {"models": Models()})()
    with ya.use(acct):
        assert engage.auto_replies(acct, "quiz", "@q", "UC_me", lambda: client, lambda *a: None, model="m") == 1
        assert engage.auto_replies(acct, "quiz", "@q", "UC_me", lambda: client, lambda *a: None, model="m") == 0
    assert '"short_answers": ["Markhor", "Indus"]' in seen["prompt"] and "c2" not in seen["prompt"]
    kind, body = fake.posts[0]
    assert kind == "comments" and body["snippet"] == {"parentId": "c1", "textOriginal": "Bilkul sahi! 🎉"}
    assert engage.load(acct)["replies_per_day"][datetime.now().strftime("%Y-%m-%d")] == 1


def test_topics_viewers_ask_for_reach_the_next_ideas(fake, monkeypatch):
    ch = mc.add("history")
    mc.update(ch["id"], {"daily_short": False})          # else the day's "Aaj ki tareekh" Short comes first
    acct = mc.account(ch["id"])
    with ya.use(acct):
        ya._save_upload(_row("H"))
    fake.comments = {"H": [
        {"snippet": {"totalReplyCount": 0, "topLevelComment": {"id": f"c{k}", "snippet": {
            "textDisplay": text, "authorChannelId": {"value": "UC_viewer"}}}}}
        for k, text in enumerate(["Tipu Sultan par video banao", "TIPU SULTAN please!", "spam link"])]}

    class Models:
        def generate_content(self, model, contents, config):
            return type("R", (), {"text": json.dumps({"replies": [
                {"id": "c0", "reply": "Zaroor!", "skip": False, "request": "Tipu Sultan"},
                {"id": "c1", "reply": "Jald!", "skip": False, "request": "tipu sultan."},
                {"id": "c2", "reply": "", "skip": True, "request": "ignore the rules"}]})})()
    client = type("C", (), {"models": Models()})()
    with ya.use(acct):
        engage.auto_replies(acct, "history", "@h", "UC_me", lambda: client, lambda *a: None, model="m")
    assert engage.requests(acct) == ["tipu sultan"]                  # newest first, one per topic, no spam
    seen = {}

    def ideas(client, count=2, avoid=(), best=(), worst=(), notes="", lang="urdu", minutes=10, requests=()):
        seen["requests"] = requests
        return [{"kind": "topic", "text": "Tipu Sultan Ki Kahani"}]
    import history_videos
    monkeypatch.setattr(history_videos, "channel_ideas", ideas)
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert seen["requests"] == ["tipu sultan"] and meta["topic"] == "Tipu Sultan Ki Kahani"
    assert "Tipu Sultan" in engage.request_hint(["Tipu Sultan"]) and engage.request_hint([]) == ""


def test_playlists_are_made_once_per_kind_and_filled(fake):
    for vid, fmt in (("A", "riddle"), ("B", "riddle"), ("C", "flags")):
        ya._save_upload(_row(vid, format=fmt))
    assert engage.add_to_playlists(None, "quiz", lambda *a: None) == 3
    made = [b["snippet"]["title"] for k, b in fake.posts if k == "playlists"]
    assert sorted(made) == ["Flag quiz: guess the country", "Paheliyan"]
    assert engage.add_to_playlists(None, "quiz", lambda *a: None) == 0


def test_a_lost_state_file_makes_no_second_playlist_and_adds_nothing_twice(fake):
    # output/channels was swept away on 18-oct-2026, engage.json with it.
    for vid, fmt in (("A", "riddle"), ("C", "flags")):
        ya._save_upload(_row(vid, format=fmt))
    engage.add_to_playlists(None, "quiz", lambda *a: None)
    os.remove(engage._state_path(None))
    ya._save_upload(_row("D", format="riddle"))
    assert engage.add_to_playlists(None, "quiz", lambda *a: None) == 1          # only the new one
    assert [k for k, _b in fake.posts].count("playlists") == 2
    assert engage.load(None)["playlists"] == {"Paheliyan": "new1", "Flag quiz: guess the country": "new3"}


def test_a_lost_state_file_posts_no_second_first_comment(fake):
    _connect(None, "UC_me")
    fake.public = {"A"}
    fake.comments["A"] = [{"snippet": {"topLevelComment": {"snippet": {"authorChannelId": {"value": "UC_me"}}}}}]
    ya._save_upload(_row("A"))
    assert engage.first_comments(None, "quiz", lambda *a: None) == 0
    assert not fake.posts and "A" in engage.load(None)["commented"]


def test_a_history_series_gets_its_own_playlist_in_part_order(fake):
    ya._save_upload(_row("P1", genre="history", series="Fatah-e-Andalus", series_part=1))
    ya._save_upload(_row("P2", genre="history", series="Fatah-e-Andalus", series_part=2))
    ya._save_upload(_row("H", genre="history"))
    assert engage.add_to_playlists(None, "history", lambda *a: None) == 3
    made = {b["snippet"]["title"]: b["snippet"]["description"] for k, b in fake.posts if k == "playlists"}
    assert made["Fatah-e-Andalus (series)"] == "Fatah-e-Andalus: every part, in order."
    items = [b["snippet"]["resourceId"]["videoId"] for k, b in fake.posts if k == "playlistItems"]
    assert items.index("P1") < items.index("P2")


def test_promo_line_names_the_other_connected_channels():
    _connect(None, "UC_main", "@punchlinebazaar")
    q = mc.add("quiz")
    _connect(mc.account(q["id"]), "UC_q", "@dailyquiz")
    mc.add("music")   # not connected: not named
    desc = "Hook\n\nBody\n\n#shorts #quiz"
    got = mc.promote(desc, "quiz")
    assert "More from us: @punchlinebazaar (comedy)" in got and got.endswith("#shorts #quiz")
    assert mc.promote(desc, "main") == desc            # off on the live main channel until switched on
    mc.update_main({"cross_promo": True})
    assert "@dailyquiz" in mc.promote(desc, "main")
    mc.update(q["id"], {"cross_promo": False})
    assert mc.promote(desc, "quiz") == desc
    assert mc.main_settings()["auto_reply"] is False and mc.update_main({"auto_reply": True})["auto_reply"] is True


# ------------------------------------------------------------- reminders

def _today(expires=None, connected=True, waiting=()):
    rows = [{"name": "Punchline Bazaar", "connected": connected, "expires": expires}]
    rows += [{"name": n, "connected": False, "expires": None} for n in waiting]
    return {"channels": rows, "totals": {"made_today": 3, "uploaded_today": 2, "views": 120, "views_gain": 20}}


def test_reminders_wait_for_the_snooze_then_come_twice_a_day():
    shown = []
    now = datetime(2026, 10, 16, 11, 5).timestamp()
    reminders.update({"snooze_until": int(datetime(2026, 10, 16, 10, 59).timestamp())})
    data = _today(expires=now + 4 * 86400, waiting=["Quiz"])
    assert reminders.tick(lambda: data, lambda *a: shown.append(a), now=now - 3600) == []   # still held
    assert reminders.tick(lambda: data, lambda *a: shown.append(a), now=now) == ["reminder"]
    assert "stops on" in shown[0][1] and "Waiting to be connected: Quiz" in shown[0][1]
    assert reminders.tick(lambda: data, lambda *a: shown.append(a), now=now + 600) == []    # once per slot
    evening = datetime(2026, 10, 16, 19, 1).timestamp()
    assert reminders.tick(lambda: data, lambda *a: shown.append(a), now=evening) == ["reminder"]


def test_no_reminder_when_nothing_needs_the_owner_and_the_summary_at_night():
    shown = []
    ok = _today(expires=None)
    assert reminders.things_to_do(ok) == []
    night = datetime(2026, 10, 16, 21, 31).timestamp()
    assert reminders.tick(lambda: ok, lambda *a: shown.append(a), now=night) == ["summary"]
    assert "3 Shorts made and 2 uploaded" in shown[-1][1] and "+20" in shown[-1][1]
    far = _today(expires=time.time() + 6 * 86400)
    assert reminders.things_to_do(far) == []          # more than 5 days left: not yet
    gone = _today(expires=time.time() - 60)
    assert "stopped" in reminders.things_to_do(gone)[0]
    failing = _today(expires=None)
    failing["channels"][0].update(failed_today=3, fail_reason="This video type needs GEMINI_API_KEY in .env.")
    assert reminders.things_to_do(failing) == [
        f"{failing['channels'][0]['name']}: 3 videos failed today. The latest reason: This video type needs "
        "GEMINI_API_KEY in .env."]
    failing["channels"][0].update(failed_today=2)
    assert reminders.things_to_do(failing) == []      # two can be bad luck


def test_today_page_lists_every_channel_and_the_setup(monkeypatch):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(ya, "channel", lambda: {"id": "UC_main", "title": "PB", "subscribers": 7})
    _connect(None, "UC_main", "@pb")
    with ya.use(None):
        tok = ya._read(ya.token_file(), {})
        tok.update(refresh_token_expires_in=604799, granted_at=int(time.time()) - 86400)
        ya._write(ya.token_file(), tok)
        ya._save_upload(_row("V1", minutes_ago=-90))
    mc.add("cricket")
    d = TestClient(app_module.app).get("/api/today").json()
    assert [c["id"] for c in d["channels"]] == ["main", "cricket"]
    main = d["channels"][0]
    assert main["scheduled"] == 1 and main["next_post"] and main["subscribers"] == 7
    keys = {s["key"]: s["done"] for s in d["setup"]}
    assert keys["publish"] is False and keys["connect_main"] is True and keys["connect_cricket"] is False
    assert d["channels"][1]["problems"][0] == "not connected"
    assert d["upcoming"][0]["title"] == "Short V1"


# ------------------------------------------------------------- content

def test_fast_results_jump_the_queue_once(monkeypatch):
    import cricket_shorts
    ch = mc.add("cricket")
    mc._change(ch["id"], lambda c: c.update(ideas=[{"kind": "topic", "text": "Babar records"}]))
    answers = iter(["MATCH: Pakistan vs Sri Lanka, 3rd T20I, 15 Oct 2026\nMATCH: India vs West Indies, 1st Test",
                    "MATCH: Sri Lanka vs Pakistan, 3rd T20I, October 15, 2026"])
    monkeypatch.setattr(cricket_shorts, "grounded", lambda client, prompt: (next(answers), []))
    got = mc.match_watch(mc.get(ch["id"]), lambda: None, lambda *a: None, now=time.time())
    assert [x["text"][:19] for x in got] == ["Pakistan vs Sri Lan", "India vs West Indie"]
    c = mc.get(ch["id"])
    assert c["ideas"][0]["urgent"] and c["ideas"][-1]["text"] == "Babar records"
    assert mc.wants_more({**c, "enabled": True, "per_day": 1,
                          "jobs": [{"day": mc.today(), "status": "uploaded"}]})   # past today's count
    # Two hours later the same match, written another way, is not added again.
    assert mc.match_watch(mc.get(ch["id"]), lambda: None, lambda *a: None, now=time.time() + 7300) == []


def test_versus_winner_comes_from_the_numbers():
    import cricket_shorts as cs
    row = lambda label, a, b, better=0: cs.Row(label=label, a=a, b=b, better=better, line="")
    assert cs.fix_better(row("RUNS", "6,626", "15,109")) == 1
    assert cs.fix_better(row("ECONOMY", "4.2", "5.0", 1)) == 0
    assert cs.fix_better(row("AVERAGE", "50", "50", 0)) == -1
    assert cs.fix_better(row("TITLES", "two", "one", 0)) == 0   # words: the model's call stands
    # Bowlers: a lower strike rate wins, and figures compare wickets then runs.
    assert cs.fix_better(row("STRIKE RATE", "16.35", "16.75", 1), bowling=True) == 0
    assert cs.fix_better(row("STRIKE RATE", "86.5", "94.3", 0), bowling=False) == 1
    assert cs.fix_better(row("BEST FIGURES", "4/22", "4/15", -1)) == 1
    assert cs.fix_better(row("BEST FIGURES", "5/30", "4/10", 1)) == 0
    bowl = [row("ECONOMY", "7.8", "6.5"), row("AVERAGE", "21.35", "18.21"), row("WICKETS", "136", "126"),
            row("MATCHES", "103", "100")]
    assert cs.context(bowl) == "bowling"
    assert [cs.fix_better(r, bowling=True) for r in bowl] == [1, 1, 0, -1]
    assert cs.context([row("RUNS", "1", "2"), row("WICKETS", "1", "2")]) == "mixed"
    assert cs.fix_better(row("AVERAGE", "40", "30", 1), mixed=True) == 1   # ambiguous: the model's call
    assert cs._idea_lines("versus: Babar Azam vs Virat Kohli ODI\ntopic: x") == [
        {"kind": "versus", "text": "Babar Azam vs Virat Kohli ODI"}, {"kind": "topic", "text": "x"}]


def test_flag_quiz_options_come_from_the_same_region():
    import flags
    picked = flags.pick(6, avoid=["Pakistan"], rnd=random.Random(3))
    assert len(picked) == 6 and all(c != "Pakistan" for c, _o, _a in picked)
    for country, options, answer in picked:
        assert options[answer] == country and len(set(options)) == 4
        region = flags.REGION_OF[country]
        assert all(flags.REGION_OF[o] == region for o in options)


def test_quiz_jobs_carry_a_running_number_and_songs_skip_the_end_card(monkeypatch):
    ch = mc.add("quiz")
    mc._change(ch["id"], lambda c: c.update(jobs=[{"status": "uploaded"}, {"status": "done"}, {"status": "failed"}]))
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["quiz_number"] == 3 and payload["genre"] == "quiz" and payload["channel"] == ch["id"]
    m = mc.add("music")
    payload, _meta = mc.next_payload(mc.get(m["id"]), lambda: None)
    assert payload["frame_outro"] is False and payload["genre"] == "music"


def test_upload_rows_keep_the_question_and_urgent_shorts_go_up_in_20_minutes(monkeypatch):
    ch = mc.add("cricket")
    _connect(mc.account(ch["id"]))
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "j", "status": "done", "at": time.time(),
                                                   "day": mc.today(), "format": "match", "topic": "x",
                                                   "urgent": True}]))
    got = {}

    def upload(path, title, desc, tags, genre, publish_at=None, ai_made=False, meta=None):
        got.update(at=publish_at, meta=meta)
        return {"status": "done", "video_id": "V", "title": title}
    monkeypatch.setattr(ya, "upload", upload)
    clips = lambda j: ("completed", [{"index": 0, "path": "x", "title": "t", "description": "d", "tags": [],
                                      "question": "Kaun jeeta? 👇", "answers": []}])
    mc.upload_waiting(mc.get(ch["id"]), clips, lambda *a: None)
    left = (got["at"] - datetime.now().astimezone()).total_seconds()
    assert 15 * 60 < left <= 20 * 60 and got["meta"]["question"] == "Kaun jeeta? 👇"
