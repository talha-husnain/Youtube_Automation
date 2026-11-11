"""Quality pass (owner, 22-oct-2026: ~1,200 views a week on six channels): same-day
Google trends in the planners, shorter Shorts that open on the hook, quiz titles that
open on the challenge, an Islamic quiz, songs that start on the chorus."""
import json

import music_shorts
import my_channels as mc
import quiz_shorts
import trends

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
<item><title>tri series</title><ht:approx_traffic>200+</ht:approx_traffic>
<ht:news_item><ht:news_item_title>Arafat Minhas&apos; 6-40 sink England</ht:news_item_title></ht:news_item>
<ht:news_item><ht:news_item_title>Pakistan vs England LIVE</ht:news_item_title></ht:news_item>
<ht:news_item><ht:news_item_title>third headline is dropped</ht:news_item_title></ht:news_item></item>
<item><title>tom banton</title><ht:approx_traffic>1000+</ht:approx_traffic></item>
</channel></rss>"""


class _R:
    text = RSS


def test_google_trends_are_read_with_their_headlines_and_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(trends, "RSS_FILE", str(tmp_path / "rss.json"))
    monkeypatch.delenv("TRENDS", raising=False)
    calls = []
    rows = trends.searches(geos=("PK",), get=lambda url, **k: calls.append(url) or _R(), now=1000)
    assert rows[0] == {"geo": "PK", "query": "tri series", "traffic": "200+",
                       "news": ["Arafat Minhas' 6-40 sink England", "Pakistan vs England LIVE"]}
    assert rows[1]["news"] == [] and calls == ["https://trends.google.com/trending/rss?geo=PK"]
    assert trends.searches(geos=("PK",), get=lambda *a, **k: 1 / 0, now=2000) == rows    # an hour's cache
    monkeypatch.setattr(trends, "searches", lambda: rows)
    hint = trends.searches_hint()
    assert "FIRST idea" in hint and "tri series (PK, 200+ searches): Arafat Minhas' 6-40" in hint


def test_a_failed_feed_means_no_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(trends, "RSS_FILE", str(tmp_path / "rss.json"))
    assert trends.searches(get=lambda *a, **k: 1 / 0) == []
    monkeypatch.setattr(trends, "searches", lambda: [])
    assert trends.searches_hint() == ""


def test_the_islamic_quiz_swaps_the_no_religion_rule(monkeypatch):
    seen = []

    def ask(client, schema, prompt, model=None):
        seen.append(prompt)
        q = quiz_shorts.Question(question="Quran mein kitni surah hain?", options=["114", "110", "99", "120"],
                                 answer=0, answer_text="114", explain="Quran ki 114 surah hain.")
        return quiz_shorts.Quiz(title="t", hook_line="h", questions=[q] * 5, outro_line="o")
    monkeypatch.setattr(quiz_shorts.kit, "ask_json", ask)
    monkeypatch.setattr(quiz_shorts, "_checked", lambda client, fmt, good: good)
    quiz_shorts.write(None, "islamic", "the five pillars of Islam", "@q")
    assert "every Muslim school agrees on" in seen[0] and "nothing about religion" not in seen[0]
    quiz_shorts.write(None, "mcq", "science", "@q")
    assert "nothing about religion" in seen[1]
    assert "islamic" in quiz_shorts.FACT_FORMATS and "islamic" in mc.FORMATS["quiz"]


def test_an_islamic_quiz_gets_an_islamic_topic_even_with_owner_notes(monkeypatch):
    ch = mc.add("quiz")
    mc.update(ch["id"], {"notes": "cricket"})
    monkeypatch.setattr(mc, "pick_format", lambda ch, options, rnd=None: "islamic")
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["quiz_format"] == "islamic" and payload["quiz_topic"] in quiz_shorts.ISLAMIC_TOPICS


def test_scripts_are_shorter_and_open_on_the_hook():
    import controversy_shorts
    import cricket_shorts
    assert cricket_shorts.MAX_BEATS == 8 and "never a greeting" in cricket_shorts.STORY_PROMPT.lower()
    assert "beats: 3 to 4" in controversy_shorts.STORY_PROMPT


def test_every_song_short_is_the_whole_song_opening_on_its_chorus():
    # Owner, 10-nov-2026: songs of 20-40 s cut "in the middle of the sentence". The song itself opens on its
    # chorus (music_shorts.sections), and the Short runs from the first sung word to the song's own end.
    lines = [("the chorus", 3.0, 6.0), ("chorus 2", 7.0, 10.0), ("verse", 20.0, 23.0), ("verse 2", 24.0, 27.0),
             ("the chorus", 40.0, 43.0), ("end", 52.0, 56.0)]
    start, end, fade = music_shorts.song_span(lines, [], 61.0)
    assert (start, end) == (2.4, 61.0) and fade < 0.5
    # A song that opens on its first word is used from 0.
    assert music_shorts.song_span([("a", 0.4, 2.0), ("b", 40.0, 47.0)], [], 50.0)[:2] == (0.0, 50.0)
    # The dance Short (chorus only, as long as the dance) still has its window.
    assert json.dumps(music_shorts.window(lines, 60.0, 15.0, "the chorus")) == json.dumps([2.2, 11.5])
