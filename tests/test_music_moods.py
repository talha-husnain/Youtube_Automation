"""Moods and their playlists on the AI-song channel (owner, 5-nov-2026: "sad song, romantic song, workout song, gym
song"): each song is made for a mood, the moods stay balanced to the owner's "how often", and every song (old ones
too) is filed into its mood's playlist next to "New AI songs"."""
import collections
import os
import random
import time

import pytest

import engage
import music_moods as mm
import music_shorts
import youtube_account as ya


@pytest.fixture(autouse=True)
def _main(tmp_path, monkeypatch):
    monkeypatch.setattr(ya, "TOKEN_FILE", str(tmp_path / "main_token.json"))
    monkeypatch.setattr(ya, "UPLOADS_FILE", str(tmp_path / "main_uploads.json"))


def test_the_owner_asked_for_moods_are_there_with_their_own_playlists():
    for key in ("sad", "romantic", "workout", "gym"):
        assert key in mm.MOODS
    titles = [m["playlist"] for m in mm.MOODS.values()]
    assert len(set(titles)) == len(titles) and all(len(t) <= 150 for t in titles)
    # Every built-in style a mood names can really be sung (music_shorts.STYLES).
    for m in mm.MOODS.values():
        assert set(m["styles"]) <= set(music_shorts.STYLES), m["name"]


def test_settings_are_cleaned():
    s = mm.settings_of({"off": ["sad", "nope", "sad"], "often": {"gym": "more", "romantic": 9, "x": 2, "chill": "?"},
                        "custom": [{"name": "  Bhangra   party ", "sound": "dhol, 110 BPM", "themes": "mehndi, shaadi, ,mehndi"},
                                   {"name": "Bhangra party"}, {"name": ""}, "junk"]})
    assert s["off"] == ["sad"] and s["often"] == {"gym": 4, "romantic": 4}
    assert s["custom"] == [{"key": "c_bhangra_party", "name": "Bhangra party", "emoji": "🎵", "sound": "dhol, 110 BPM",
                            "themes": ["mehndi", "shaadi"], "playlist": "Bhangra party | AI Songs"}]
    assert mm.settings_of(None) == {"off": [], "often": {}, "custom": []}
    many = mm.settings_of({"custom": [{"name": f"m{k}"} for k in range(20)]})
    assert len(many["custom"]) == mm.CUSTOM_MAX


def test_moods_stay_balanced_to_how_often():
    rnd = random.Random(5)
    s = mm.settings_of({"often": {"sad": "more", "romantic": "normal", "party": "less"}, "off": ["chill"]})
    recent = []
    for _ in range(300):
        recent.append(mm.pick(s, recent, rnd))
    got = collections.Counter(recent[-90:])
    assert "chill" not in got
    # Weights: sad 4, romantic 2, party/workout/gym 1 (the other moods' default since 10-nov-2026) = 9:
    # of 90 songs about 40 / 20 / 10.
    assert 37 <= got["sad"] <= 43 and 18 <= got["romantic"] <= 22 and 8 <= got["party"] <= 12
    # A mood far behind comes first: ten sad songs in a row, the next is not sad.
    assert mm.pick(mm.settings_of({}), ["sad"] * 10, rnd) != "sad"
    assert mm.pick(mm.settings_of({"off": list(mm.MOODS)}), [], rnd) is None


def test_love_songs_are_two_in_three_by_default():
    # 19-oct-2026: romance and heartbreak are what the viewers click (75% love themes before moods);
    # 10-nov-2026: "make more romantic songs".
    rnd, recent = random.Random(9), []
    for _ in range(240):
        recent.append(mm.pick(mm.settings_of({}), recent, rnd))
    love = sum(m in ("sad", "romantic") for m in recent[-120:])
    assert 76 <= love <= 84 and {"gym", "workout"} <= set(recent[-30:])
    rows = {r["key"]: r for r in mm.summary(mm.settings_of({}), [])}
    assert rows["sad"]["often"] == "more" and rows["romantic"]["often"] == "more" and rows["gym"]["often"] == "less"


def test_a_mood_picks_its_style_theme_and_brief():
    rnd = random.Random(1)
    style, theme, brief = mm.song_choice(mm.all_moods({})["gym"], music_shorts.STYLES, lambda o: o[0], rnd)
    assert style == "gym phonk" and theme in mm.MOODS["gym"]["themes"] and "GYM" in brief
    custom = mm.all_moods(mm.settings_of({"custom": [{"name": "Bhangra", "sound": "Punjabi bhangra pop, dhol",
                                                      "themes": "mehndi night"}]}))["c_bhangra"]
    style, theme, brief = mm.song_choice(custom, music_shorts.STYLES, lambda o: pytest.fail("no styles"), rnd)
    assert style == "Punjabi bhangra pop, dhol" and theme == "mehndi night" and "BHANGRA" in brief


@pytest.mark.parametrize("style,theme,mood", [
    ("heartbreak pop ballad", "she left without a goodbye", "sad"), ("romantic slow pop", "first crush", "romantic"),
    ("motivational anthem", "chasing dreams", "workout"), ("gym phonk", "beast mode", "gym"),
    ("upbeat pop", "gym motivation", "gym"), ("lo-fi chill", "late night drive", "chill"),
    ("afrobeats", "dancing all night", "party"), ("indie folk", "new beginnings", "workout"), ("x", "y", None)])
def test_old_songs_are_filed_by_their_style_and_theme(style, theme, mood):
    assert mm.infer(style, theme) == mood
    assert mm.mood_of({"format": style, "topic": theme}) == mood
    assert mm.mood_of({"mood": "party", "format": style, "topic": theme}) == "party"   # the one it was made for


def test_mood_search_tags_join_the_songs_own():
    tags = music_shorts._with_mood_tags([f"t{k}" for k in range(15)], "gym")
    assert len(tags) == 15 and "gym music" in tags and "gym phonk" in tags and tags[0] == "t0"
    assert music_shorts._with_mood_tags(["a", "", "b"], "") == ["a", "b"]


# ---------- the channel: planner, settings, card ----------

def test_the_song_channel_plans_a_song_for_a_mood(monkeypatch):
    import ai_influencer
    import my_channels as mc
    monkeypatch.setattr(ai_influencer, "available", lambda now=None: False)
    monkeypatch.setattr(mc, "remix_idea", lambda ch, log=print: None)
    ch = mc.update(mc.add("music")["id"], {"moods": {"mixes": 0}, "urdu_share": 0})   # English songs only
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    key = payload["music_mood"]
    assert payload["music_lang"] == "english" and meta["lang"] == "english"
    assert key in mm.MOODS and meta["mood"] == key and payload["music_brief"] == mm.MOODS[key]["brief"]
    assert payload["music_style"] in mm.MOODS[key]["styles"] and meta["label"].startswith(mm.MOODS[key]["name"])
    # The owner's "make a gym song now" wins once, then the balance goes on.
    mc.update(ch["id"], {"next_mood": "gym"})
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["music_mood"] == "gym"
    # All moods off: songs as before (no mood).
    mc.update(ch["id"], {"moods": {"off": list(mm.MOODS)}, "next_mood": ""})
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert "music_mood" not in payload and "mood" not in meta


def test_the_next_mood_is_cleared_once_its_song_starts(monkeypatch):
    import asyncio

    import ai_influencer
    import my_channels as mc
    monkeypatch.setattr(ai_influencer, "available", lambda now=None: False)
    monkeypatch.setattr(mc, "remix_idea", lambda ch, log=print: None)
    ch = mc.update(mc.add("music")["id"], {"next_mood": "romantic", "moods": {"mixes": 0}})

    async def submit(payload):
        assert payload["music_mood"] == "romantic"
        return "11111111-2222-4333-8444-555555555555"
    assert asyncio.run(mc.make_one(submit, ch, lambda: None, lambda *a: None))
    after = mc.get(ch["id"])
    assert not after.get("next_mood") and after["jobs"][-1]["mood"] == "romantic"


def test_the_card_shows_each_mood_with_its_songs_and_playlist(monkeypatch):
    import my_channels as mc
    ch = mc.add("music")
    mc._change(ch["id"], lambda c: c.update(jobs=[
        {"status": "uploaded", "mood": "sad"}, {"status": "done", "format": "gym phonk", "topic": "beast mode"},
        {"status": "failed", "mood": "sad"}]))
    engage._update(mc.account(ch["id"]), lambda s: s.update(playlists={mm.MOODS["sad"]["playlist"]: "PLsad"}))
    view = mc.summary(mc.get(ch["id"]))
    rows = {m["key"]: m for m in view["moods"]}
    assert rows["sad"]["songs"] == 1 and rows["gym"]["songs"] == 1 and rows["romantic"]["songs"] == 0
    assert rows["sad"]["url"] == "https://www.youtube.com/playlist?list=PLsad" and rows["gym"]["url"] is None
    assert view["mood_settings"] == {"off": [], "often": {}, "custom": []}


# ---------- playlists on YouTube ----------

class FakeYouTube:
    def __init__(self):
        self.posts = []

    def get(self, url, params):
        if url.endswith("/playlists"):
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


def _song(vid, days_ago=0, **kw):
    return {"id": vid, "video_id": vid, "status": "done", "created": time.time() - days_ago * 86400 - 60,
            "title": f"Song {vid}", **kw}


def test_every_song_goes_into_its_mood_playlist_old_ones_too(monkeypatch):
    yt = FakeYouTube()
    monkeypatch.setattr(ya, "_get", yt.get)
    monkeypatch.setattr(engage, "_post", lambda url, params, body: (ya.spend(50), yt.post(url, params, body))[1])
    ya._save_upload(_song("OLD1", days_ago=30, format="sad piano ballad", topic="missing her at 3 am"))
    ya._save_upload(_song("OLD2", days_ago=20, format="gym phonk", topic="beast mode"))
    ya._save_upload(_song("NEW", mood="romantic", format="indie folk", topic="first crush"))
    ya._save_upload(_song("ODD", days_ago=40, format="x", topic="y"))         # no mood found: left alone
    n = engage.add_to_playlists(None, "music", lambda *a: None, moods=mm.settings_of({}))
    lists = {b["snippet"]["title"]: f"new{k + 1}" for k, (kind, b) in enumerate(yt.posts) if kind == "playlists"}
    items = collections.defaultdict(list)
    for kind, b in yt.posts:
        if kind == "playlistItems":
            items[b["snippet"]["playlistId"]].append(b["snippet"]["resourceId"]["videoId"])
    titles = {pid: t for t, pid in lists.items()}
    filed = {titles[pid]: vids for pid, vids in items.items()}
    assert filed[mm.LANGS["english"]["playlist"]] == ["NEW"]                  # the all-songs list: new uploads
    assert filed[mm.MOODS["sad"]["playlist"]] == ["OLD1"] and filed[mm.MOODS["gym"]["playlist"]] == ["OLD2"]
    assert filed[mm.MOODS["romantic"]["playlist"]] == ["NEW"] and n == 4
    about = next(b["snippet"]["description"] for k, b in yt.posts
                 if k == "playlists" and b["snippet"]["title"] == mm.MOODS["sad"]["playlist"])
    assert "Sad songs" in about and "AI" in about
    # Nothing twice.
    before = len(yt.posts)
    assert engage.add_to_playlists(None, "music", lambda *a: None, moods=mm.settings_of({})) == 0
    assert len(yt.posts) == before


class FakeYouTubeWithPut(FakeYouTube):
    def __init__(self):
        super().__init__()
        self.puts = []

    def put(self, url, params, body):
        self.puts.append((url.rsplit("/", 1)[1], body))
        return {"id": body.get("id")}


def _fake(monkeypatch):
    yt = FakeYouTubeWithPut()
    monkeypatch.setattr(ya, "_get", yt.get)
    monkeypatch.setattr(engage, "_post", lambda url, params, body: (ya.spend(50), yt.post(url, params, body))[1])
    monkeypatch.setattr(engage, "_put", lambda url, params, body: (ya.spend(50), yt.put(url, params, body))[1])
    return yt


def _filed(yt):
    lists = {f"new{k + 1}": b["snippet"]["title"] for k, (kind, b) in enumerate(yt.posts) if kind == "playlists"}
    out = collections.defaultdict(list)
    for kind, b in yt.posts:
        if kind == "playlistItems":
            out[lists.get(b["snippet"]["playlistId"], b["snippet"]["playlistId"])].append(
                b["snippet"]["resourceId"]["videoId"])
    return out


def test_urdu_and_english_songs_go_into_their_own_language_playlists(monkeypatch):
    # Owner, 10-nov-2026: "one playlist will be English one and one will be for Urdu one, and inside them...
    # sad songs, romantic song, workout song".
    yt = _fake(monkeypatch)
    ya._save_upload(_song("EN", mood="sad", format="sad piano ballad", topic="heartbreak"))
    ya._save_upload(_song("UR", mood="sad", lang="urdu", format="Pakistani sad ballad", topic="judaai"))
    ya._save_upload(_song("UR2", mood="romantic", lang="urdu", format="Sufi pop love song", topic="pehli nazar"))
    engage.add_to_playlists(None, "music", lambda *a: None, moods=mm.settings_of({}))
    filed = _filed(yt)
    assert filed[mm.LANGS["english"]["playlist"]] == ["EN"]
    assert filed[mm.LANGS["urdu"]["playlist"]] == ["UR", "UR2"]
    assert filed["English Sad Songs 💔 Heartbreak AI Songs"] == ["EN"]
    assert filed["Urdu Sad Songs 💔 Dard Bhare AI Gaane"] == ["UR"]
    assert filed["Urdu Romantic Songs ❤️ Pyar Bhare AI Gaane"] == ["UR2"]
    # One shelf per language on the channel page: its all-songs list first, then its mood lists.
    shelves = {b["snippet"]["title"]: b["contentDetails"]["playlists"] for k, b in yt.posts if k == "channelSections"}
    lists = engage.load(None)["playlists"]
    assert shelves["Urdu Songs 🎧"] == [lists[mm.LANGS["urdu"]["playlist"]], lists["Urdu Sad Songs 💔 Dard Bhare AI Gaane"],
                                       lists["Urdu Romantic Songs ❤️ Pyar Bhare AI Gaane"]]
    assert shelves["English Songs 🎧"][0] == lists[mm.LANGS["english"]["playlist"]]
    assert all(b["snippet"]["type"] == "multiplePlaylists" for k, b in yt.posts if k == "channelSections")
    # Nothing again, and a new Urdu mood playlist updates the Urdu shelf in place.
    before = len(yt.posts)
    engage.add_to_playlists(None, "music", lambda *a: None, moods=mm.settings_of({}))
    assert len(yt.posts) == before and not yt.puts
    ya._save_upload(_song("UR3", mood="gym", lang="urdu", format="desi gym rap", topic="sher ka dil"))
    engage.add_to_playlists(None, "music", lambda *a: None, moods=mm.settings_of({}))
    assert [k for k, _b in yt.puts] == ["channelSections"]
    assert len(yt.puts[0][1]["contentDetails"]["playlists"]) == 4 and yt.puts[0][1]["id"]


def test_the_old_playlists_are_renamed_to_english_and_keep_their_songs(monkeypatch):
    yt = _fake(monkeypatch)
    engage._update(None, lambda s: s.update(playlists={"New AI songs": "PLall", "Sad Songs 💔 Heartbreak AI Songs": "PLsad"},
                                            playlisted={"OLD": "PLall"}, mood_playlisted={"OLD": "PLsad"}))
    ya._save_upload(_song("OLD", days_ago=2, format="sad piano ballad", topic="heartbreak"))
    ya._save_upload(_song("NEW", mood="sad", format="sad piano ballad", topic="missing her"))
    engage.add_to_playlists(None, "music", lambda *a: None, moods=mm.settings_of({}))
    renamed = {b["id"]: b["snippet"]["title"] for k, b in yt.puts if k == "playlists"}
    assert renamed == {"PLall": mm.LANGS["english"]["playlist"], "PLsad": "English Sad Songs 💔 Heartbreak AI Songs"}
    lists = engage.load(None)["playlists"]
    assert lists[mm.LANGS["english"]["playlist"]] == "PLall" and "New AI songs" not in lists
    # The new English song joins the renamed lists (no new playlist made), the old one is not added twice.
    assert not [b for k, b in yt.posts if k == "playlists"]
    assert _filed(yt) == {"PLall": ["NEW"], "PLsad": ["NEW"]}
    # Renamed once only.
    engage.add_to_playlists(None, "music", lambda *a: None, moods=mm.settings_of({}))
    assert len([1 for k, _b in yt.puts if k == "playlists"]) == 2


def test_a_shelf_that_youtube_refuses_waits_a_week(monkeypatch):
    yt = _fake(monkeypatch)

    def post(url, params, body):
        if url.endswith("/channelSections"):
            raise RuntimeError("403 forbidden")
        return (ya.spend(50), yt.post(url, params, body))[1]
    monkeypatch.setattr(engage, "_post", post)
    ya._save_upload(_song("EN", mood="sad", format="sad piano ballad", topic="heartbreak"))
    said = []
    engage.add_to_playlists(None, "music", said.append, moods=mm.settings_of({}))
    assert any("trying again in a week" in s for s in said) and engage.load(None)["shelf_failed"]
    assert _filed(yt)[mm.LANGS["english"]["playlist"]] == ["EN"]           # the songs are filed all the same


def test_languages_alternate_at_half_and_half():
    rnd = random.Random(3)
    recent = []
    for _ in range(40):
        recent.append(mm.pick_lang(0.5, recent, rnd))
    assert recent.count("urdu") == 20 and "urdu,urdu,urdu" not in ",".join(recent)
    # A channel of English songs starts Urdu, then they alternate.
    assert mm.pick_lang(0.5, [None] * 30, rnd) == "urdu"
    assert mm.pick_lang(0, [], rnd) == "english" and mm.pick_lang(1, ["urdu"] * 9, rnd) == "urdu"
    assert mm.urdu_share({}) == mm.URDU_SHARE and mm.urdu_share({"urdu_share": "7"}) == 1.0


def test_an_urdu_song_gets_urdu_themes_styles_tags_and_label(monkeypatch):
    import ai_influencer
    import my_channels as mc
    monkeypatch.setattr(ai_influencer, "available", lambda now=None: False)
    ch = mc.update(mc.add("music")["id"], {"moods": {"mixes": 0}, "urdu_share": 1, "next_mood": "sad"})
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["music_lang"] == "urdu" and meta["lang"] == "urdu" and meta["label"].startswith("Urdu · Sad songs")
    assert payload["music_theme"] in mm.MOODS["sad"]["urdu_themes"]
    assert payload["music_style"] in mm.MOODS["sad"]["urdu_styles"]
    assert set(mm.MOODS["sad"]["urdu_styles"]) <= set(music_shorts.STYLES)
    tags = music_shorts._with_mood_tags(["a"], "sad", "urdu")
    assert "urdu sad song" in tags and "sad songs" not in tags
    assert mc.summary(mc.get(ch["id"]))["urdu_share"] == 1.0
    # Urdu songs stay out of the (English) mood mixes for now.
    songs = [{"job_id": "j1", "mood": "sad", "lang": "urdu"}, {"job_id": "j2", "mood": "sad"}]
    assert [s["job_id"] for s in mm.mix_songs("sad", {"j1", "j2"}, songs)] == ["j2"]


def test_old_songs_catch_up_a_few_each_pass(monkeypatch):
    yt = FakeYouTube()
    monkeypatch.setattr(ya, "_get", yt.get)
    monkeypatch.setattr(engage, "_post", lambda url, params, body: (ya.spend(50), yt.post(url, params, body))[1])
    for k in range(engage.MOOD_PER_PASS + 3):
        ya._save_upload(_song(f"S{k}", days_ago=30, format="sad piano ballad", topic="heartbreak"))
    assert engage.add_to_playlists(None, "music", lambda *a: None, moods=mm.settings_of({})) == engage.MOOD_PER_PASS
    assert engage.add_to_playlists(None, "music", lambda *a: None, moods=mm.settings_of({})) == 3
    # Another kind of channel never files by mood.
    assert engage.add_to_playlists(None, "quiz", lambda *a: None) == 0


def test_make_now_takes_a_mood(monkeypatch):
    app_module = pytest.importorskip("app")
    import my_channels as mc
    from fastapi.testclient import TestClient
    ch = mc.add("music")
    client = TestClient(app_module.app)
    mc.update(ch["id"], {"moods": {"off": ["party"]}})
    r = client.post(f"/api/my-channels/{ch['id']}/make", json={"mood": "party"})
    assert r.status_code == 400 and "switched off" in r.json()["detail"]
    monkeypatch.setattr(mc, "running", lambda c: True)
    r = client.post(f"/api/my-channels/{ch['id']}/make", json={"mood": "gym"})
    assert r.status_code == 200 and r.json()["queued"] and "Gym songs" in r.json()["message"]
    assert mc.get(ch["id"])["next_mood"] == "gym"
    assert client.post(f"/api/my-channels/{ch['id']}/make").status_code == 409       # no body: as before
