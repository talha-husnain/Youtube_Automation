"""A card takes another card's YouTube channel (owner, 5-nov-2026: no Google accounts left for new channels,
so the two weakest channels went to the horror and money cards). Nothing is deleted: the retired card's
files move to state/retired, its videos stay on YouTube."""
import json
import os

import pytest

import my_channels as mc
import youtube_account as ya


def V(name):
    """A YouTube-shaped video id (11 characters); an upload row's own "id" is 12 and is NOT the video."""
    return (name + "-" * 11)[:11]


@pytest.fixture(autouse=True)
def _main_token(tmp_path, monkeypatch):
    monkeypatch.setattr(ya, "TOKEN_FILE", str(tmp_path / "main_token.json"))
    monkeypatch.setattr(ya, "UPLOADS_FILE", str(tmp_path / "main_uploads.json"))


def _connect(cid, channel_id="UC_quiz", title="Sawal Paheli"):
    with ya.use(mc.account(cid)):
        ya._write(ya.token_file(), {"access_token": "t", "refresh_token": "r", "expires_at": 9e12, "granted_at": 1,
                                    "channel": {"id": channel_id, "title": title, "handle": "@sawalpaheli"}})
        ya._save_upload({"id": "old1", "publish_at": "2026-10-20T08:00:00+00:00", "status": "done",
                         "title": "Quiz #3"})


def _pair():
    quiz = mc.add("quiz", "Quiz and paheliyan")
    money = mc.add("money", "Paisa Kahani")
    _connect(quiz["id"])
    mc.remember_channel(quiz["id"], {"id": "UC_quiz", "title": "Sawal Paheli"})
    mc._change(quiz["id"], lambda c: c.update(about_credit=5, jobs=[{"job_id": "w1", "status": "done"}]))
    mc._change(money["id"], lambda c: c.update(about_credit=7, last_learn=9, long_uploads={"status": "allowed"}))
    return quiz["id"], money["id"]


def test_the_new_card_takes_the_channel_and_the_old_card_is_retired_with_its_files_kept():
    old, new = _pair()
    out = mc.hand_over(old, new, now=1793900000)
    assert out["ok"] and out["from"] == old and out["to"] == new and out["channel"] == "Sawal Paheli"
    assert out["dropped"] == 1                                   # the quiz Short still waiting never goes up
    assert mc.get(old) is None and [c["id"] for c in mc.channels()] == [new]
    with ya.use(mc.account(new)):
        st = ya.status()
        assert st["connected"] and st["channel"]["id"] == "UC_quiz"
        assert ya.uploads() == []                                # its numbers start from its own videos
    card = mc.get(new)
    assert card["yt_channel"] == "UC_quiz" and card["yt_title"] == "Sawal Paheli"
    assert card["took_over"]["from"] == "Quiz and paheliyan" and card["took_over"]["kind"] == "quiz"
    assert card["took_over"]["handle"] == "@sawalpaheli" and card["took_over"]["at"] == 1793900000
    for key in ("about_credit", "last_learn", "long_uploads"):
        assert key not in card                                   # asked again of the channel it has now
    # Nothing deleted: the old card's record and uploads log are in state/retired, without the token.
    dest = out["archive"]
    assert os.path.dirname(dest) == mc.retired_dir() and os.path.basename(dest).startswith(f"{old}-")
    assert json.load(open(os.path.join(dest, "card.json"), encoding="utf-8"))["id"] == old
    assert [r["id"] for r in json.load(open(os.path.join(dest, "uploads.json"), encoding="utf-8"))] == ["old1"]
    assert not os.path.exists(os.path.join(dest, "token.json")) and not os.path.exists(mc.folder(old))
    assert mc.wrong_pick(new, {"id": "UC_other", "title": "Other"})    # a later connect must pick this channel


def test_a_hand_over_is_refused_when_it_would_lose_or_mix_something():
    old, new = _pair()
    with pytest.raises(ValueError, match="two different"):
        mc.hand_over(old, old)
    with pytest.raises(ValueError, match="two different"):
        mc.hand_over("nope", new)
    with pytest.raises(ValueError, match="not connected"):
        mc.hand_over(new, old)                                   # the money card has no channel
    mc._change(new, lambda c: c.update(jobs=[{"job_id": "r1", "status": "running", "label": "x"}]))
    with pytest.raises(ValueError, match="making a video"):
        mc.hand_over(old, new)
    mc._change(new, lambda c: c.update(jobs=[]))
    _connect(new, "UC_money", "Money")
    with pytest.raises(ValueError, match="already has its own"):
        mc.hand_over(old, new)
    assert mc.get(old) and os.path.isfile(os.path.join(mc.folder(old), "token.json"))   # nothing moved


def test_the_handed_over_channel_gets_the_new_cards_about_text(monkeypatch):
    old, new = _pair()
    mc.hand_over(old, new)
    calls = []
    monkeypatch.setattr(ya, "add_to_channel_about", lambda line, if_empty=None, replace=None, backup=None:
                        calls.append((line, if_empty, replace, backup)) or True)
    assert mc.about_credit(mc.get(new), log=lambda m: None) is True
    line, _empty, replace, backup = calls[0]
    assert line == mc.VOICE_CREDIT and replace == mc.ABOUT["money"]
    assert backup.startswith(mc.folder(new)) and "about_backup_" in backup
    assert mc.get(new)["about_credit"]
    # A card that was always on its own channel still only adds the credit line.
    cricket = mc.add("cricket")
    _connect(cricket["id"], "UC_c", "Cric")
    calls.clear()
    monkeypatch.setattr(ya, "add_to_channel_about", lambda line, if_empty=None: calls.append(line) or True)
    assert mc.about_credit(mc.get(cricket["id"]), log=lambda m: None) is True     # the old call, unchanged
    assert calls == [mc.VOICE_CREDIT]


def test_the_horror_card_on_the_history_channel_gets_the_horror_about(monkeypatch):
    hist = mc.add("history", "History and stories")
    horror = mc.update(mc.add("history", "Raat Ki Kahaniyan")["id"], {"mode": "horror"})
    _connect(hist["id"], "UC_hist", "Tareekh History")
    mc.hand_over(hist["id"], horror["id"])
    calls = []
    monkeypatch.setattr(ya, "add_to_channel_about", lambda line, if_empty=None, replace=None, backup=None:
                        calls.append(replace) or True)
    mc.about_credit(mc.get(horror["id"]), log=lambda m: None)
    assert calls == [mc.ABOUT["horror"]]


def test_add_to_channel_about_can_replace_the_old_text_and_keeps_a_backup(monkeypatch, tmp_path):
    sent = []

    class R:
        status_code = 200

    monkeypatch.setattr(ya, "_get", lambda url, params: {"items": [{"id": "UC1", "brandingSettings": {
        "channel": {"description": "Daily quiz Shorts in Urdu.", "keywords": "quiz"}, "image": {"x": 1}}}]})
    monkeypatch.setattr(ya, "_token", lambda: "t")
    monkeypatch.setattr(ya, "spend", lambda n: None)
    monkeypatch.setattr(ya, "quota_used", lambda: 0)
    monkeypatch.setattr(ya.httpx, "put", lambda url, params=None, json=None, headers=None, timeout=None:
                        sent.append(json) or R())
    backup = str(tmp_path / "b" / "about_backup.txt")
    assert ya.add_to_channel_about("CREDIT", replace="Money stories.", backup=backup) is True
    chan = sent[0]["brandingSettings"]["channel"]
    assert chan["description"] == "Money stories.\n\nCREDIT" and chan["keywords"] == "quiz"
    assert sent[0]["brandingSettings"]["image"] == {"x": 1}      # the rest of the branding goes back as it was
    assert open(backup, encoding="utf-8").read() == "Daily quiz Shorts in Urdu."
    sent.clear()
    assert ya.add_to_channel_about("CREDIT") is True             # no replace: appended as before
    assert sent[0]["brandingSettings"]["channel"]["description"] == "Daily quiz Shorts in Urdu.\n\nCREDIT"


def test_the_take_over_api(monkeypatch):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    c = TestClient(app_module.app)
    old, new = _pair()
    assert c.post(f"/api/my-channels/{new}/take-over", json={"from": new}).status_code == 400
    r = c.post(f"/api/my-channels/{new}/take-over", json={"from": old})
    assert r.status_code == 200 and r.json()["card"]["youtube"]["connected"] is True
    assert r.json()["card"]["took_over"]["from"] == "Quiz and paheliyan"
    assert [x["id"] for x in c.get("/api/my-channels").json()["channels"]] == ["main", new]


def test_instagram_is_winners_only_when_channels_share_an_account():
    a = mc.update(mc.add("cricket")["id"], {"meta_page": "111"})
    b = mc.update(mc.add("controversy")["id"], {"meta_page": "222"})
    assert mc.meta_ig_mode(a) == "all" and mc.meta_ig_mode(b) == "all"         # an account each
    mc.update(b["id"], {"meta_page": "111"})
    assert mc.meta_ig_mode(mc.get(a["id"])) == "winners"                        # one account for both
    mc.update(a["id"], {"meta_ig_mode": "all"})
    assert mc.meta_ig_mode(mc.get(a["id"])) == "all" and mc.summary(mc.get(a["id"]))["meta_ig_now"] == "all"
    mc.update(b["id"], {"meta_ig": False})
    assert mc.meta_ig_mode(mc.get(b["id"])) == "all"
    mc.update(a["id"], {"meta_ig_mode": "nonsense"})
    assert mc.get(a["id"])["meta_ig_mode"] == "all"


def test_meta_score_reads_the_shorts_youtube_views_and_the_channel_median():
    ch = mc.add("cricket")
    mc._change(ch["id"], lambda c: c.update(stats={"median": 8}))
    with ya.use(mc.account(ch["id"])):
        ya._save_upload({"id": "yt9", "status": "done", "views": 120, "publish_at": "2026-11-05T08:00:00+00:00"})
    assert mc.meta_score({"channel": ch["id"], "video_id": "yt9"}) == (120, 8)
    assert mc.meta_score({"channel": ch["id"], "id": f"{ch['id']}_yt9"}) == (120, 8)
    assert mc.meta_score({"channel": ch["id"], "video_id": "nope"}) is None
    assert mc.meta_score({"channel": "gone", "video_id": "yt9"}) is None


def test_auto_link_puts_each_channel_on_its_page_and_instagram_by_the_suggested_groups():
    pages = [{"id": "1", "name": "CricRecordz Daily", "ig_id": "i1", "ig_username": "cric"},
             {"id": "2", "name": "Matter Kya Hai", "ig_id": "i2", "ig_username": "stories"},
             {"id": "3", "name": "Paisa Kahani"}, {"id": "4", "name": "Raat Ki Kahaniyan Official"},
             {"id": "5", "name": "Byte Beats Music"}, {"id": "6", "name": "Something Else"}]
    cric = mc.add("cricket", "Cricket facts and updates")
    mc._change(cric["id"], lambda c: c.update(yt_title="CricRecordz Daily"))
    cont = mc.add("controversy", "Matter Kya Hai")
    money = mc.add("money", "Paisa Kahani")
    horror = mc.update(mc.add("history", "Raat Ki Kahaniyan")["id"], {"mode": "horror"})
    music = mc.add("music", "Byte Beats Music")
    quran = mc.update(mc.add("quran", "Holy Quran")["id"], {"meta_page": "6"})       # the owner's own choice
    rows = {r["card"]: r for r in mc.auto_link(pages=pages, log=lambda m: None)}
    assert rows[cric["id"]] == {"card": cric["id"], "name": "Cricket facts and updates", "page": "CricRecordz Daily",
                                "instagram": "cric"}
    assert rows[cont["id"]]["instagram"] == "stories"
    assert rows[money["id"]]["page"] == "Paisa Kahani" and rows[money["id"]]["instagram"] == "stories"
    assert rows[horror["id"]]["page"] == "Raat Ki Kahaniyan Official" and rows[horror["id"]]["instagram"] == "stories"
    assert rows[music["id"]]["page"] == "Byte Beats Music" and rows[music["id"]]["instagram"] == ""
    assert mc.get(quran["id"])["meta_page"] == "6"                                     # kept
    assert mc.get(money["id"])["meta_ig_page"] == "2" and mc.get(music["id"])["meta_ig"] is False
    # One account for three channels: winners only there; cricket's own account takes every Short.
    assert mc.meta_ig_mode(mc.get(cont["id"])) == "winners" and mc.meta_ig_mode(mc.get(cric["id"])) == "all"


def test_the_old_videos_are_set_private_a_few_per_pass_within_the_quota(monkeypatch):
    old, new = _pair()
    archive = mc.hand_over(old, new)["archive"]
    with open(os.path.join(archive, "uploads.json"), "w", encoding="utf-8") as f:
        json.dump([{"id": f"row{i:09d}", "video_id": V(f"v{i}"), "status": "done", "created": i} for i in range(4)]
                  + [{"id": "rowfailed000", "video_id": V("vf"), "status": "failed", "created": 9}], f)
    with open(os.path.join(archive, "engage.json"), "w", encoding="utf-8") as f:
        json.dump({"playlists": {"Quiz": "PLq"}}, f)
    done = []
    monkeypatch.setattr(ya, "unschedule", lambda vid: done.append(vid) or vid != V("v2"))    # v2 already gone
    monkeypatch.setattr(ya, "playlist_private", lambda pid: done.append(pid) or True)
    used = [0]
    monkeypatch.setattr(ya, "quota_used", lambda: used[0])
    monkeypatch.setattr(mc, "HIDE_PER_PASS", 2)
    assert mc.hide_retired(mc.get(new), log=lambda m: None, now=1000) == 0           # not asked yet
    mc.update(new, {"hide_old": True})
    assert mc.hide_retired(mc.get(new), log=lambda m: None, now=1000) == 2
    assert done == [V("v0"), V("v1")] and mc.get(new)["took_over"]["hide_left"] == 3
    assert mc.hide_retired(mc.get(new), log=lambda m: None, now=1100) == 0           # HIDE_EVERY
    used[0] = mc.HIDE_CEILING                                                         # the day's quota is for uploads
    assert mc.hide_retired(mc.get(new), log=lambda m: None, now=2000) == 0
    used[0] = 0
    mc.hide_retired(mc.get(new), log=lambda m: None, now=3000)
    mc.hide_retired(mc.get(new), log=lambda m: None, now=4000)
    assert done == [V("v0"), V("v1"), V("v2"), V("v3"), "PLq"] and V("vf") not in done              # only the old card's uploads
    t = mc.get(new)["took_over"]
    assert t["hide_done"] and t["hide_left"] == 0 and t["hidden"] == 5
    hidden = json.load(open(os.path.join(archive, "hidden.json"), encoding="utf-8"))
    assert hidden["videos"][V("v2")] == "gone" and hidden["playlists"]["PLq"] == "private"


def test_hiding_never_touches_videos_on_another_channel_and_skips_a_forbidden_one(monkeypatch):
    old, new = _pair()
    archive = mc.hand_over(old, new)["archive"]
    with open(os.path.join(archive, "uploads.json"), "w", encoding="utf-8") as f:
        json.dump([{"id": "row000000001", "video_id": V("ours1"), "status": "done", "created": 1, "yt_channel": "UC_quiz"},
                   {"id": "row000000002", "video_id": V("elsewhere1"), "status": "done", "created": 2, "elsewhere": "CricRecordz Daily"},
                   {"id": "row000000003", "video_id": V("other1"), "status": "done", "created": 3, "yt_channel": "UC_cricket"},
                   {"id": "row000000004", "video_id": V("denied1"), "status": "done", "created": 4}], f)
    with open(os.path.join(archive, "engage.json"), "w", encoding="utf-8") as f:
        json.dump({}, f)
    done = []

    def hide(vid):
        done.append(vid)
        if vid == V("denied1"):
            raise RuntimeError("YouTube said 403: forbidden")
        return True
    monkeypatch.setattr(ya, "unschedule", hide)
    monkeypatch.setattr(ya, "quota_used", lambda: 0)
    mc.update(new, {"hide_old": True})
    assert mc.hide_retired(mc.get(new), log=lambda m: None, now=1000) == 2
    assert done == [V("ours1"), V("denied1")]                       # never the rows of another channel
    t = mc.get(new)["took_over"]
    assert t["hide_done"] and t["hide_left"] == 0
    hidden = json.load(open(os.path.join(archive, "hidden.json"), encoding="utf-8"))
    assert hidden["videos"] == {V("ours1"): "private", V("denied1"): "not this channel's"}


def test_a_pass_that_kept_our_row_ids_is_done_again_with_youtube_ids(monkeypatch):
    old, new = _pair()
    archive = mc.hand_over(old, new)["archive"]
    with open(os.path.join(archive, "uploads.json"), "w", encoding="utf-8") as f:
        json.dump([{"id": "e26636447192", "video_id": V("real1"), "status": "done", "created": 1}], f)
    with open(os.path.join(archive, "hidden.json"), "w", encoding="utf-8") as f:
        json.dump({"videos": {"e26636447192": "gone"}, "playlists": {}}, f)      # the first live pass
    mc._change(new, lambda c: c["took_over"].update(hide=1, hide_done=2, hide_at=2))
    done = []
    monkeypatch.setattr(ya, "unschedule", lambda vid: done.append(vid) or True)
    monkeypatch.setattr(ya, "quota_used", lambda: 0)
    assert mc.hide_retired(mc.get(new), log=lambda m: None, now=5000) == 0            # finished, until asked again
    mc.update(new, {"hide_old": True})
    assert mc.hide_retired(mc.get(new), log=lambda m: None, now=5000) == 1 and done == [V("real1")]
    hidden = json.load(open(os.path.join(archive, "hidden.json"), encoding="utf-8"))
    assert hidden["videos"] == {V("real1"): "private"}
