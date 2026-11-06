"""Glamour on the channels (owner, 19-oct-2026): love and heartbreak songs with
a woman as the song's character, the "guess the star" quiz from free photos,
and planners that give famous women their share of the stories."""
import random

import pytest

import my_channels as mc


def test_most_songs_are_about_love_and_a_woman_sings_most_of_them(monkeypatch):
    import music_shorts as ms
    rnd = random.Random(7)
    themes = [ms.pick_theme(rnd) for _ in range(400)]
    love = sum(t in ms.LOVE_THEMES for t in themes) / len(themes)
    assert 0.7 < love < 0.9           # LOVE_SHARE plus the love themes in THEMES itself
    assert "heartbreak pop ballad" in ms.STYLES and "romantic slow pop" in ms.STYLES
    seen = {}

    def fake_ask(client, schema, prompt, model=None):
        seen["prompt"] = prompt
        return ms.SongPlan(title="T", youtube_title="T", genre="pop", lyria_style="pop", verse=["a", "b"],
                           pre_chorus=[], chorus=["c", "d"], image_prompt="x", colors=[], description="d",
                           tags=[], hashtags=[])
    monkeypatch.setattr(ms.kit, "ask_json", fake_ask)
    ms.plan(None, "romantic slow pop", "heartbreak", "a female lead singer")
    assert "Lead vocal: a female lead singer" in seen["prompt"]
    assert "never revealing or suggestive" in seen["prompt"]


def test_song_footage_welcomes_a_woman_but_never_anything_suggestive():
    import music_shorts as ms
    assert "woman" in ms.FOOTAGE_RULE and "never revealing, lingerie or suggestive" in ms.FOOTAGE_RULE
    assert "never a person singing" in ms.FOOTAGE_RULE.lower()


def test_the_music_channel_plans_love_themes(monkeypatch):
    import music_moods
    import music_shorts as ms
    m = mc.update(mc.add("music")["id"], {"moods": {"mixes": 0}})      # songs: no weekly mix due
    # Since 5-nov-2026 a song is made for a mood; sad and romantic start at "more often" (music_moods.DEFAULT_OFTEN).
    mc.update(m["id"], {"next_mood": "sad"})
    payload, meta = mc.next_payload(mc.get(m["id"]), lambda: None)
    assert payload["music_theme"] in music_moods.MOODS["sad"]["themes"] and meta["topic"] == payload["music_theme"]
    assert music_moods.DEFAULT_OFTEN == {"sad": 4, "romantic": 4}
    # With every mood off, the love-theme share (pick_theme) works as before.
    mc.update(m["id"], {"moods": {"off": list(music_moods.MOODS)}, "next_mood": ""})
    monkeypatch.setattr(ms, "pick_theme", lambda rnd=None: "she left without a goodbye")
    payload, meta = mc.next_payload(mc.get(m["id"]), lambda: None)
    assert payload["music_theme"] == "she left without a goodbye" and meta["topic"] == payload["music_theme"]


def _fake_fetch(calls, wrong=()):
    def fetch(name, out_dir, size=(700, 760), kind="cricket"):
        calls.append((name, kind, size))
        title = "Someone Else" if name in wrong else name
        return {"card": f"{name}.png", "info": {"player": title, "artist": f"by {name[:3]}",
                                                 "licence": "CC BY 3.0", "page": f"https://c/{name}"}}
    return fetch


def test_the_star_quiz_names_only_photos_filed_under_that_star(monkeypatch, tmp_path):
    import player_photo
    import quiz_shorts as q
    calls = []
    group = q.STARS["bollywood"]
    monkeypatch.setattr(player_photo, "fetch", _fake_fetch(calls, wrong={group[0], group[1]}))
    monkeypatch.setattr(q.kit, "ask_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    rnd = random.Random(1)
    monkeypatch.setattr(rnd, "choice", lambda seq: "bollywood" if "bollywood" in seq else seq[0])
    quiz, cards, photos = q.write_stars(None, "@x", str(tmp_path), rnd)
    assert len(quiz.questions) == q.FORMATS["stars"]["count"] == len(cards) == len(photos)
    names = [x.answer_text for x in quiz.questions]
    assert group[0] not in names and group[1] not in names       # a photo of someone else is never the answer
    assert all(kind == "star" and size == q.STAR_CARD for _n, kind, size in calls)
    for x in quiz.questions:
        assert x.options[x.answer] == x.answer_text and len(set(x.options)) == 4
        assert all(o in group for o in x.options)                 # wrong names from the same group
    assert quiz.title and "comment" in quiz.outro_line.lower()     # the fallback copy when the model fails


def test_the_star_quiz_shows_new_stars_first_and_credits_without_naming(monkeypatch, tmp_path):
    import player_photo
    import quiz_shorts as q
    group = q.STARS["hollywood"]
    shown = group[:-4]
    monkeypatch.setenv("QUIZ_AVOID", __import__("json").dumps([f"star:{n}" for n in shown]))
    monkeypatch.setattr(player_photo, "fetch", _fake_fetch([]))
    monkeypatch.setattr(q.kit, "ask_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    rnd = random.Random(2)
    monkeypatch.setattr(rnd, "choice", lambda seq: "hollywood" if "hollywood" in seq else seq[0])
    quiz, _cards, photos = q.write_stars(None, "", str(tmp_path), rnd)
    assert sorted(x.answer_text for x in quiz.questions) == sorted(group[-4:])
    line = q.star_credits(photos)
    assert "CC BY 3.0" in line and "1) by " in line
    assert not any(f"of {x.answer_text}" in line for x in quiz.questions)


def test_a_star_fact_shows_only_when_google_search_confirms_it(monkeypatch):
    import cricket_shorts
    import quiz_shorts as q
    asked = []
    monkeypatch.setattr(cricket_shorts, "grounded", lambda client, prompt: (asked.append(prompt), (
        "1: OK\n3: WRONG - that was another drama", []))[1])
    out = q._checked_facts(None, ["A", "B", "C", "D"], ["film one", "", "drama two", "song three"])
    assert out == ["film one", "", "", ""]                 # 4 never answered: left out too
    assert "2. B" not in asked[0] and "1. A: film one" in asked[0]
    monkeypatch.setattr(cricket_shorts, "grounded", lambda c, p: (_ for _ in ()).throw(OSError("dns")))
    assert q._checked_facts(None, ["A"], ["film one"]) == [""]


def test_star_names_drop_the_wikipedia_disambiguation():
    import quiz_shorts as q
    assert q.star_name("Meera (Pakistani actress)") == "Meera"
    assert all(len(q.star_name(n)) <= 22 for g in q.STARS.values() for n in g)   # fits an option row


def test_the_star_quiz_is_a_planned_format():
    import engage
    import quiz_shorts as q
    assert "stars" in mc.FORMATS["quiz"] and "stars" in q.FORMAT_TEXT
    assert "stars" not in q.FACT_FORMATS        # no topic and no Google check: the photo is the fact
    assert ("quiz", "stars") in engage.PLAYLISTS


@pytest.mark.parametrize("desc,ok", [("Indian actress", True), ("Pakistani singer", True),
                                      ("American film director", False), ("Pakistani politician", False)])
def test_a_star_photo_needs_an_article_that_says_she_acts_or_sings(desc, ok):
    import player_photo
    assert player_photo._fits(desc, "star") is ok


def test_planners_give_famous_women_their_share():
    import controversy_shorts
    import history_videos
    assert "famous WOMEN" in controversy_shorts.IDEAS_PROMPT
    assert "famous woman of history" in history_videos.IDEAS_PROMPT
    assert "Never a woman of the Prophet's family" in history_videos.IDEAS_PROMPT
