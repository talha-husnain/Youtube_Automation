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


def test_a_stale_phrase_left_after_the_polish_gets_one_targeted_fix(monkeypatch):
    monkeypatch.setenv("POLISH", "1")
    s = _story()
    s.hook_line = "Sirf 97 innings mein 5000 runs"
    s.question = "Like aur subscribe karo, Babar best hai? Comment mein batao"
    calls = []

    def ask(client, schema, prompt, model=None):
        calls.append(prompt)
        if schema is craft.Doctored:
            return craft.Doctored(hook_score=8, hooks=[], lines=[t for _p, t in craft.spoken(s)])
        assert "remove: like aur subscribe" in prompt
        return craft.Lines(lines=["Babar best hai ya nahi? Ek lafz mein comment mein batao"])
    monkeypatch.setattr(craft.kit, "ask_json", ask)
    craft.polish(object(), s, FACTS, log=lambda m: None)
    assert len(calls) == 2 and s.question.startswith("Babar best hai ya nahi")
    assert "Shape for this video: the order" in craft.short_rules(craft.FIXED_ORDER)
    assert all("MYSTERY" not in craft.short_rules(exclude=("MYSTERY",)) for _ in range(20))


def test_a_long_videos_opening_is_rewritten_only_on_a_clear_gain(monkeypatch):
    monkeypatch.setenv("POLISH", "1")
    facts = "In 1453 Sultan Mehmed II took Constantinople after 53 days. The walls were 1,000 years old."
    old = ["Aaj hum Constantinople ki kahani sunenge. Yeh ek purana shehar tha.",
           "Sultan Mehmed ne 1453 mein shehar ko gher liya. Lekin deewarein mazboot thi."]
    script = SimpleNamespace(hook=[SimpleNamespace(line=p) for p in old])
    new = ["53 din, 1,000 saal purani deewarein, aur ek jawan Sultan. Constantinople gir sakta tha?",
           "Sultan Mehmed ne 1453 mein shehar gher liya. Lekin deewarein toot nahi rahi thi. Kya Rome bacha?"]
    def fake(before, after, prefer_new=True):
        def ask(client, schema, prompt, model=None):
            if schema is craft.Pick:                  # the blind judge: pick the version holding "53 din"
                first = prompt.split("VERSION 2:")[0]
                return craft.Pick(better=1 if ("53 din" in first) == prefer_new else 2, why="")
            return craft.Opening(score_before=before, score_after=after, paragraphs=new)
        return ask
    monkeypatch.setattr(craft.kit, "ask_json", fake(3, 8))
    craft.polish_opening(object(), script, facts, log=lambda m: None)
    assert script.hook[0].line == new[0]          # "Lekin" and "Constantinople" start sentences: fine
    assert script.hook[1].line == old[1]          # "Rome" is a name the facts do not have
    monkeypatch.setattr(craft.kit, "ask_json", fake(3, 8, prefer_new=False))
    script = SimpleNamespace(hook=[SimpleNamespace(line=p) for p in old])
    craft.polish_opening(object(), script, facts, log=lambda m: None)
    assert [s.line for s in script.hook] == old   # the blind judge preferred the original
    monkeypatch.setattr(craft.kit, "ask_json", fake(7, 8))
    script = SimpleNamespace(hook=[SimpleNamespace(line=p) for p in old])
    craft.polish_opening(object(), script, facts, log=lambda m: None)
    assert [s.line for s in script.hook] == old   # a one-point gain is noise
    monkeypatch.setattr(craft.kit, "ask_json", fake(3, 9))
    faith = ["Hazrat Muhammad (SAW) ki peshgoi thi. 53 din, 1,000 saal purani deewarein.", old[1]]
    script = SimpleNamespace(hook=[SimpleNamespace(line=p) for p in faith], sacred=False)
    craft.polish_opening(object(), script, facts, log=lambda m: None)
    assert script.hook[0].line == faith[0]        # a paragraph about faith keeps its wording
    script = SimpleNamespace(hook=[SimpleNamespace(line=p) for p in old], sacred=True)
    craft.polish_opening(object(), script, facts, log=lambda m: None)
    assert [s.line for s in script.hook] == old   # a sacred story is never polished


def test_the_week_report_compares_new_scripts_with_the_month_before():
    import reminders
    since = 1_000_000_000
    now = since + 10 * 86400

    def row(day, views, ret=None, fmt="topic"):
        return {"video_id": f"v{day}{views}", "status": "done", "created": since + day * 86400, "views": views,
                "format": fmt, **({"retention": ret} if ret is not None else {})}
    rows = [row(-5, 100, 40), row(-4, 200, 50), row(-3, 300, 60), row(-40, 9999),
            row(1, 400, 70), row(2, 500, 80), row(3, 600, 90), row(9.5, 5000), row(4, 99999, fmt="history")]
    line = reminders.craft_line(rows, lambda r: r["views"], now, since=since)
    assert line == "  New scripts: median 500 views, 80% watched (3 Shorts); the month before: median 200 views, 50% watched (3 Shorts)."
    assert reminders.craft_line(rows[:5], lambda r: r["views"], now, since=since) == ""     # too few after


def test_a_blind_judge_decides_whether_the_polished_script_replaces_the_writers(monkeypatch):
    monkeypatch.setenv("POLISH", "1")
    for prefer_new in (True, False):
        s = _story()
        s.hook_line = "Babar Azam ke ODI records dekhte hain"                 # plain, not stale
        orders = []

        def ask(client, schema, prompt, model=None):
            if schema is craft.Pick:
                first = prompt.split("VERSION 2:")[0]
                orders.append("Sirf 97" in first)
                return craft.Pick(better=1 if ("Sirf 97" in first) == prefer_new else 2, why="")
            return craft.Doctored(hook_score=5, lines=[t for _p, t in craft.spoken(s)],
                                  hooks=[craft.Hook(text="Sirf 97 innings mein 5000 runs, kisi ne nahi kiya", score=9)])
        monkeypatch.setattr(craft.kit, "ask_json", ask)
        craft.polish(object(), s, FACTS, log=lambda m: None)
        assert (s.hook_line.startswith("Sirf 97")) == prefer_new and len(orders) == 1


def test_polish_never_breaks_a_video(monkeypatch):
    monkeypatch.setenv("POLISH", "1")

    def boom(*a, **k):
        raise RuntimeError("quota")
    monkeypatch.setattr(craft.kit, "ask_json", boom)
    s = craft.polish(object(), _story(), FACTS, log=lambda m: None)
    assert s.hook_line.startswith("Aaj hum")
    monkeypatch.setenv("POLISH", "0")
    assert craft.polish(object(), _story(), FACTS) .hook_line.startswith("Aaj hum")


def test_footage_is_cropped_around_the_biggest_face(monkeypatch, tmp_path):
    import broll
    import faces
    seen = []

    def run(cmd, **k):
        seen.append(cmd[cmd.index("-vf") + 1])
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(broll.subprocess, "run", run)
    monkeypatch.setattr(faces, "center_x", lambda path, at: 0.8)
    broll._shot(str(tmp_path), 0, 30, {"kind": "video", "path": "a.mp4"}, 0.0, False, 1080, 1920)
    monkeypatch.setattr(faces, "center_x", lambda path, at: None)
    broll._shot(str(tmp_path), 1, 30, {"kind": "video", "path": "a.mp4"}, 0.0, True, 1080, 1920)
    assert "crop=1080:1920:x='min(max(iw*0.8000-ow/2,0),iw-ow)'" in seen[0]
    assert "iw*0." not in seen[1] and "crop=1080:1920," in seen[1]


def test_a_footage_term_that_echoes_the_line_is_replaced(monkeypatch):
    import broll
    monkeypatch.setattr(broll.kit, "ask_json", lambda *a, **k: broll.Terms(
        terms=["Sirf 31 balls par ODI century, yeh pagalpan kisne kiya?", "cricket stadium night"]))
    got = broll.terms_for(object(), "Fastest centuries in ODI cricket history", ["a", "b", "c"])
    assert got == ["Fastest centuries in ODI", "cricket stadium night", "Fastest centuries in ODI"]


def test_titles_are_translated_for_hindi_and_urdu_viewers_and_sent_with_the_upload(monkeypatch, tmp_path):
    import localize
    import youtube_account as ya
    monkeypatch.setenv("LOCALIZE", "1")
    desc = "Sirf 31 balls mein century! AB de Villiers ka record.\n\nCredit: photo by X, CC BY-SA 4.0\n\n#shorts #cricket"
    monkeypatch.setattr(localize.kit, "ask_json", lambda *a, **k: localize.Out(items=[
        localize.Item(lang="hi", title="सिर्फ 31 गेंदों में शतक! #shorts", hook="एबी डिविलियर्स का रिकॉर्ड।"),
        localize.Item(lang="ur", title="Sirf 31 balls", hook=""),                 # not translated: dropped
        localize.Item(lang="fr", title="Seulement 31 balles", hook="x")]))        # not asked for: dropped
    got = localize.build(object(), "Sirf 31 balls mein century! #shorts", desc, "cricket", log=lambda m: None)
    assert list(got) == ["hi"] and got["hi"]["title"].startswith("सिर्फ")
    assert got["hi"]["description"].startswith("एबी") and got["hi"]["description"].endswith(desc)  # credits kept
    assert localize.build(object(), "t", desc, "music") == {}                                    # songs: none
    sent = {}

    def post(url, params=None, json=None, **k):
        sent.update(params=params, body=json)
        raise RuntimeError("stop here")
    monkeypatch.setattr(ya.httpx, "post", post)
    monkeypatch.setattr(ya, "_token", lambda: "tok")
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"x")
    try:
        ya.upload(str(clip), "Sirf 31 balls mein century!", desc, ["cricket"], "cricket", localizations=got)
    except Exception:  # noqa: BLE001
        pass
    assert sent["params"]["part"] == "snippet,status,localizations"
    assert sent["body"]["snippet"]["defaultLanguage"] == "en" and sent["body"]["localizations"]["hi"]["title"]


def test_the_seo_writer_hears_what_people_search(monkeypatch):
    import cricket_shorts as cs
    monkeypatch.setenv("TRENDS", "1")
    asked = []

    def suggest(q):
        asked.append(q)
        return [q + " bowling", q + " wickets"]
    hint = cs._search_hint("Wasim Akram's best spells", suggest=suggest)
    assert asked == ["wasim akram", "wasim akram best spells"]
    assert "wasim akram bowling" in hint and "title's first words" in hint
    monkeypatch.setenv("TRENDS", "0")
    assert cs._search_hint("Wasim Akram", suggest=suggest) == ""


def test_a_scene_naming_an_empire_gets_its_own_map_entry(monkeypatch):
    import history_maps
    import history_videos as hv
    monkeypatch.setattr(history_maps, "available", lambda: True)
    monkeypatch.setattr(history_maps, "find", lambda q: "Mughal Empire" if "mughal" in q.lower() else
                        "Islamic Republic of Pakistan" if "pakistan" in q.lower() else None)
    monkeypatch.setattr(history_maps, "span", lambda n: (1947, 2024) if "Pakistan" in n else (1529, 1858))
    assert hv.add_maps(SimpleNamespace(hook=[SimpleNamespace(map="Pakistan | 1947 | 2020")], chapters=[]),
                       {0: {}}, log=lambda m: None) == 0                     # never modern borders
    S = SimpleNamespace
    script = S(hook=[S(map="Mughals | 1526 | 1707", label="MUGHALS AT PEAK"), S(map="", label="AGRA")],
               chapters=[S(scenes=[S(map="Atlantis | 1 | 2"), S(map="Mughal Empire | 1707 | 1600"),
                                   S(map="Mughal Empire | 1600 | 1700"), S(map="Mughal Empire | 1700 | 1750")])])
    shared = {"full": "a.jpg"}
    pics = {k: shared for k in range(6)}
    assert hv.add_maps(script, pics, log=lambda m: None) == 2              # MAX_MAPS
    assert pics[0]["map"] == ("Mughal Empire", 1526, 1707) and pics[4]["map"] == ("Mughal Empire", 1600, 1700)
    assert "map" not in shared and "map" not in pics[1] and "map" not in pics[3]   # backwards years: none
    assert script.hook[0].label == "" and script.hook[1].label == "AGRA"     # the map names it already
    monkeypatch.setattr(history_maps, "available", lambda: False)
    assert hv.add_maps(script, {k: {} for k in range(6)}) == 0


def test_a_clip_shorter_than_its_shot_is_stretched_not_looped(monkeypatch, tmp_path):
    import broll
    import slowmo
    seen, asked = [], []

    def run(cmd, **k):
        seen.append(cmd)
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(broll.subprocess, "run", run)
    monkeypatch.setattr(slowmo, "available", lambda: True)
    monkeypatch.setattr(slowmo, "stretch", lambda src, off, have, need, out: asked.append((have, need)) or out)
    broll._shot(str(tmp_path), 0, 90, {"kind": "video", "path": "a.mp4", "seconds": 2.0}, 0.3, False, 1080, 1920)
    assert asked == [(1.7, 3.0)] and "-stream_loop" not in seen[0] and ".broll" in " ".join(seen[0])
    broll._shot(str(tmp_path), 1, 60, {"kind": "video", "path": "a.mp4", "seconds": 9.0}, 0.3, False, 1080, 1920)
    assert len(asked) == 1 and "-stream_loop" in seen[1]          # long enough: no stretch needed


def test_each_channel_grades_its_footage_and_photos_keep_their_colours(monkeypatch, tmp_path):
    import broll
    seen = []

    def run(cmd, **k):
        seen.append(cmd[cmd.index("-vf") + 1])
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(broll.subprocess, "run", run)
    monkeypatch.setenv("CONTENT_GENRE", "controversy")
    broll._shot(str(tmp_path), 0, 30, {"kind": "video", "path": "a.mp4"}, 0.0, False, 1080, 1920)
    broll._shot(str(tmp_path), 1, 30, {"kind": "photo", "path": "a.jpg"}, 0.0, False, 1080, 1920)
    assert broll.GRADES["controversy"] in seen[0] and broll.GRADES["controversy"] not in seen[1]
    monkeypatch.setenv("CHANNEL_GRADE", "0")
    assert broll.grade() == ""
    monkeypatch.setenv("CHANNEL_GRADE", "1")
    monkeypatch.setenv("CONTENT_GENRE", "comedy")
    assert broll.grade() == ""                    # the comedy clips are untouched


def test_beats_are_found_and_footage_cuts_land_on_them():
    import numpy as np
    import beats
    import broll
    sr = beats.SR
    t = np.arange(int(12 * sr)) / sr
    y = 0.02 * np.random.default_rng(1).standard_normal(len(t)).astype(np.float32)
    for b in np.arange(0.4, 12, 0.625):                        # 96 BPM clicks
        i, n = int(b * sr), int(0.05 * sr)
        y[i:i + n] += (np.sin(2 * np.pi * 1000 * t[:n]) * np.exp(-60 * t[:n])).astype(np.float32)
    env = beats.onset_envelope(y)
    found = beats.beat_times(env, beats.tempo_period(env))
    true = np.arange(0.4, 12, 0.625)
    assert len(found) >= len(true) - 1 and max(min(abs(true - x)) for x in found) < 0.06
    windows = [(0.0, 6.0, "a"), (6.0, 12.0, "b")]
    items = [{"path": "x.mp4", "seconds": 30}, {"path": "y.mp4", "seconds": 30}]
    grid = [round(x, 3) for x in np.arange(0.4, 12, 0.625)]
    plain = broll.plan_shots(windows, items)
    synced = broll.plan_shots(windows, items, beats=grid)
    assert sum(s[0] for s in synced) == sum(s[0] for s in plain) == 12 * broll.FPS     # same total
    cuts, at = [], 0
    for frames, *_rest in synced[:-1]:
        at += frames
        cuts.append(at / broll.FPS)
    assert all(min(abs(c - g) for g in grid) <= 1 / broll.FPS + 1e-6 for c in cuts)  # every cut on a beat


def test_real_swooshes_replace_the_chirp(monkeypatch):
    import short_kit as kit
    cmd, graph, mix = [], [], []
    kit._voice_sfx_inputs(cmd, graph, mix, 1, [], [(kit.WHOOSH, 0.3, 1.0), (kit.WHOOSH, 0.3, 2.0)])
    files = kit.whoosh_files()
    assert len(files) >= 2 and cmd.count("-i") == 2 and cmd[1] != cmd[3]     # a different one per card
    assert graph[0].startswith("[1:a]volume=") and "adelay=1000|1000" in graph[0]
    monkeypatch.setenv("REAL_SFX", "0")
    cmd, graph = [], []
    kit._voice_sfx_inputs(cmd, graph, [], 1, [], [(kit.WHOOSH, 0.3, 1.0)])
    assert not cmd and graph[0].startswith("aevalsrc=")


def test_wikipedia_most_read_skips_its_own_pages_and_falls_back_a_day(monkeypatch, tmp_path):
    import trends
    monkeypatch.setenv("TRENDS", "1")
    monkeypatch.setattr(trends, "WIKI_FILE", str(tmp_path / "wiki.json"))
    asked = []

    def get(url):
        asked.append(url)
        if "en.wikipedia" in url and "/10/21" in url:
            return {"items": [{"articles": [{"article": "Main_Page", "views": 9}, {"article": "Special:Search", "views": 8},
                                            {"article": "Babar_Azam", "views": 7}]}]}
        return None
    rows = trends.wiki_top(get=get, now=1792713600)          # 22-oct-2026 00:00 UTC
    assert rows == [{"title": "Babar Azam", "views": 7, "wiki": "en"}]
    assert sum("hi.wikipedia" in u for u in asked) == 2      # yesterday, then the day before
    assert trends.wiki_top(get=lambda u: 1 / 0, now=1792713600 + 60) == rows   # cached


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


def test_candidates_add_the_breakout_shorts_of_the_channels_search_finds():
    tab = [{"id": f"t{i:010d}", "title": "Babar ka record", "views": 10_000} for i in range(8)]
    tab += [{"id": "big00000000", "title": "Babar ne 3 balls mein", "views": 400_000},
            {"id": "edit0000000", "title": "Babar x song edit", "views": 900_000}]
    searched = []

    def search(q):
        searched.append(q)
        return [{"id": "s0000000000", "title": "Cricket facts", "views": 30_000, "channel_url": "https://yt/@rival"}]
    rows = vr.candidates("cricket", search=search, shorts=lambda url, n: tab, now=1792713600)
    assert [r["id"] for r in rows] == ["big00000000", "s0000000000"]      # the edit is dropped
    assert len(searched) == 2
    assert vr.candidates("cricket", search=lambda q: 1 / 0, now=1792713600 + 60) == rows   # cached a day
    assert vr.outliers(tab[:3]) == []                                     # too few to know the median


def test_a_pasted_link_becomes_the_next_idea(monkeypatch):
    import my_channels as mc
    monkeypatch.setattr(vr, "study", lambda client, url, kind, **k: {
        "id": "abcdefghijk", "topic": "Shoaib Akhtar vs PCB fine", "kind": "topic"})
    monkeypatch.setattr("short_kit.gemini", lambda: object())
    ch = mc.add("controversy")
    mc.add_idea(ch["id"], "https://www.youtube.com/watch?v=abcdefghijk&t=3")
    idea = mc.get(ch["id"])["ideas"][0]
    assert idea["text"] == "Shoaib Akhtar vs PCB fine" and idea["remix"] == "abcdefghijk" and idea["owner"]
