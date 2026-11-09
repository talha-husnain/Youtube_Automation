"""The horror channel (5-nov-2026): the long-video pipeline's third mode. Original fiction written and checked
without web research, dark paintings and footage under one grade, a low narrator, a fiction note in every
description, and the channel wiring (ideas, Shorts, playlists, replies, upload category)."""
import os
import subprocess

import pytest

import history_videos as hv
import horror_stories as hs
import my_channels as mc
import youtube_account as ya

S = hv.Scene


def _story(**kw):
    base = dict(allowed=True, reason="", sacred=True, title="Purani Haveli Ka Band Kamra | Horror Story",
                thumb_text="KAMRA NO. 13", thumb_picture="a dark corridor", summary="Ek haveli, ek band kamra.",
                hook=[S(line="Raat ke teen baje darwaza khud khula " * 4, picture="a door ajar at night",
                        wiki="Badshahi Mosque", label="RAAT 3:00 BAJE", map="Mughal Empire | 1526 | 1707")],
                chapters=[hv.Chapter(title="Pehli raat", scenes=[S(line="Ali ne haveli kiraye par li " * 10,
                                                                 picture="old haveli courtyard", wiki="", label="")] * 2),
                          hv.Chapter(title="Woh awaaz", scenes=[S(line="Phir woh awaaz aayi " * 12,
                                                                picture="empty corridor, one lamp", wiki="", label="")] * 2)],
                outro="Kya aap ke saath kabhi aisa hua? Subscribe karein.", question="Aap hote to kya karte?",
                tags=["horror story in urdu", "darawni kahani"])
    base.update(kw)
    return hv.Script(**base)


@pytest.fixture
def horror_env(monkeypatch):
    monkeypatch.setenv("HISTORY_MODE", "horror")
    import script_craft
    monkeypatch.setattr(script_craft, "polish_opening", lambda *a, **k: None)


# ---------- the mode ----------

def test_the_mode_comes_from_the_job_and_brings_its_voice_words_and_grade(monkeypatch):
    monkeypatch.delenv("HISTORY_MODE", raising=False)
    assert hv.mode_now() == "history" and hv.mode_grade() == ""
    monkeypatch.setenv("HISTORY_MODE", "nonsense")
    assert hv.mode_now() == "history"
    monkeypatch.setenv("HISTORY_MODE", "horror")
    assert hv.mode_now() == "horror" and hv.voice_for("horror") == hs.VOICE and hv.voice_for("history") == "Charon"
    assert hv.mode_grade() == hs.GRADE + "," and "saturation=0.55" in hs.GRADE
    monkeypatch.setenv("CHANNEL_GRADE", "0")
    assert hv.mode_grade() == ""
    assert hv.words_for("urdu", "horror")["chapter"] == "HISSA" and hv.words_for("urdu")["chapter"] == "CHAPTER"
    assert "SUBSCRIBE" in hv.end_events(3.0, "@raat", "urdu", "horror")[0]
    assert hs.WORDS["urdu"]["next"] in hv.end_events(3.0, "@raat", "urdu", "horror")[2]


# ---------- the story ----------

def test_a_story_is_written_and_checked_without_any_web_research(monkeypatch, horror_env):
    calls = []

    def ask(client, schema, prompt, model=None):
        calls.append((schema.__name__, prompt))
        return _story() if schema is hv.Script else hv.Check(ok=True, problems=[])
    monkeypatch.setattr(hv.kit, "ask_json", ask)
    monkeypatch.setattr(hv, "research", lambda *a, **k: pytest.fail("fiction needs no web research"))
    script, brief, sources = hv.write(None, "A haveli and its locked room", "@raat", minutes=2, mode="horror")
    assert sources == [] and "Purani Haveli" in brief and "Pehli raat" in brief
    assert script.sacred is False                                            # a story is never "sacred" here
    assert all(s.wiki == "" and s.map == "" for s in hv.scenes_of(script))   # no Wikipedia pictures, no maps
    assert [c[0] for c in calls] == ["Script", "Check"]
    prompt = calls[0][1]
    assert "ORIGINAL FICTION" in prompt and "A haveli and its locked room" in prompt and "no gore" in prompt
    assert "real, named" in prompt and "Roman Urdu" in prompt


def test_a_story_that_fails_its_check_is_rewritten_once_then_dropped(monkeypatch, horror_env):
    calls = []

    def ask(client, schema, prompt, model=None):
        calls.append((schema.__name__, prompt))
        if schema is hv.Script:
            return _story()
        return hv.Check(ok=False, problems=["it retells the film Tumbbad"])
    monkeypatch.setattr(hv.kit, "ask_json", ask)
    with pytest.raises(RuntimeError, match="did not pass its check twice"):
        hs.write(None, "t", "@raat", minutes=2)
    assert [c[0] for c in calls] == ["Script", "Check", "Script", "Check"] and "Tumbbad" in calls[2][1]
    monkeypatch.setattr(hv.kit, "ask_json", lambda c, schema, p, model=None:
                        _story(allowed=False, reason="needs gore") if schema is hv.Script else hv.Check(ok=True, problems=[]))
    with pytest.raises(RuntimeError, match="needs gore"):
        hs.write(None, "t", "@raat", minutes=2)


def test_ideas_rotate_plot_kinds_and_a_series_becomes_parts(monkeypatch):
    import cricket_shorts as cs
    asked = {}

    def grounded(client, prompt):
        asked["prompt"] = prompt
        return ("topic: A night nurse and the ward that should be empty\ntopic: Old haveli story\n"
                "series: The Highway | The first passenger | The second night\nnot an idea"), []
    monkeypatch.setattr(cs, "grounded", grounded)
    monkeypatch.setattr(hs, "trending", lambda lang, limit=8: ["Purani Haveli (2,000,000 views)"])
    ideas = hv.channel_ideas(None, 2, avoid=["Old haveli story"], notes="jinn stories", mode="horror",
                             requests=["hostel ki kahani"])
    texts = [i["text"] for i in ideas]
    assert "A night nurse and the ward that should be empty" in texts and "Old haveli story" not in texts
    assert any(i.get("series") == "The Highway" for i in ideas)
    p = asked["prompt"]
    assert "the graveyard caretaker" in p and "jinn stories" in p and "hostel ki kahani" in p
    assert "Purani Haveli (2,000,000 views)" in p and "Never:" in p


# ---------- pictures, sound, words ----------

def test_horror_pictures_are_footage_and_dark_paintings_never_wikipedia(monkeypatch, tmp_path):
    import stock_media
    from PIL import Image
    monkeypatch.setattr(hv, "candidates", lambda articles, sacred: (articles and pytest.fail("no Wikipedia")) or [])
    monkeypatch.setattr(stock_media, "available", lambda: False)
    monkeypatch.setattr(hs, "AI_IMAGES", 3)
    styles = []

    def paint(client, prompt, out, sacred, style=None):
        styles.append(style)
        Image.new("RGB", (1920, 1080), (20, 20, 30)).save(out)
        return out
    monkeypatch.setattr(hv, "ai_picture", paint)
    script = _story()
    pics, title, credits, ai_used, thumb, stock = hv.pictures(None, script, "t", str(tmp_path), log=lambda *a: None,
                                                              mode="horror")
    assert ai_used == 3 and styles == [hs.AI_STYLE] * 3 and credits == [] and stock == []
    assert set(pics) == set(range(len(hv.scenes_of(script))))              # every scene has a picture
    assert "No blood" in hs.AI_STYLE and "never a photograph" in hs.AI_STYLE


def test_a_painted_scene_replaces_a_stock_photo_and_its_credit(monkeypatch, tmp_path):
    import broll
    import stock_media
    from PIL import Image
    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (2400, 1350), (60, 60, 60)).save(photo)
    monkeypatch.setattr(hv, "candidates", lambda articles, sacred: [])
    monkeypatch.setattr(stock_media, "available", lambda: True)
    rules = []
    monkeypatch.setattr(broll, "terms_for", lambda client, topic, lines, rule="": rules.append(rule) or ["t"] * len(lines))
    item = {"kind": "photo", "path": str(photo), "seconds": 0.0, "provider": "Pixabay", "author": "", "page": "q"}
    monkeypatch.setattr(stock_media, "for_scenes", lambda client, topic, lines, terms, portrait, log, rule: [item] * len(lines))
    monkeypatch.setattr(hs, "AI_IMAGES", 1)
    monkeypatch.setattr(hv, "ai_picture", lambda client, prompt, out, sacred, style=None:
                        Image.new("RGB", (1920, 1080), (9, 9, 9)).save(out) or out)
    script = _story(sacred=False)          # as horror_stories.write leaves every story
    pics, title, credits, ai_used, thumb, stock = hv.pictures(None, script, "t", str(tmp_path), log=lambda *a: None,
                                                              mode="horror")
    assert ai_used == 1 and rules == [hs.FOOTAGE_RULE]
    assert "Never blood" in hs.FOOTAGE_RULE and "never a child in danger" in hs.FOOTAGE_RULE
    # The hook got the painting; the photo still shows (and is credited) on the other scenes.
    assert all(s["path"] == str(photo) for s in stock) and stock


def test_the_description_says_it_is_fiction_and_lists_no_sources():
    desc = hv.describe(_story(), [("Shuruaat", 0.0), ("Pehli raat", 40.0)], [], [], "@raat", "urdu", True,
                       mode="horror")
    assert hs.FICTION["urdu"] in desc and "Sources:" not in desc and "#horrorstory" in desc
    assert hs.WORDS["urdu"]["follow"] in desc and "0:40 Pehli raat" in desc


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="ffmpeg not installed")
def test_chapter_cards_get_a_low_hit_instead_of_the_whoosh(tmp_path, monkeypatch):
    monkeypatch.setattr(hv.kit, "level", lambda path: None)
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "color=black:s=320x180:d=3:r=30",
                    "-pix_fmt", "yuv420p", str(tmp_path / "v.mp4")], check=True)
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", "3", str(tmp_path / "n.wav")], check=True)
    hv.mix(str(tmp_path), "v.mp4", "n.wav", "out.mp4", 3.0, [0.5], [0.0, 3.0], [], sting=True)
    out = subprocess.run(["ffmpeg", "-nostdin", "-v", "info", "-i", str(tmp_path / "out.mp4"), "-af", "volumedetect",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    assert "max_volume" in out and "-inf" not in out.split("max_volume:")[1].split("\n")[0]


def test_red_thumbnail_text():
    import thumbnail
    from PIL import Image
    im = thumbnail.burn_thumbnail_text(Image.new("RGB", (1280, 720), (0, 0, 0)).convert("RGBA"), "WOH AAYI",
                                       "left", "red").convert("RGB")
    assert (230, 28, 28) in {c for _n, c in im.getcolors(1 << 22)}


# ---------- the channel ----------

def _horror_card():
    ch = mc.add("history")
    return mc.update(ch["id"], {"mode": "horror", "name": "Raat Ki Kahaniyan"})


def test_a_long_channel_in_horror_mode_is_a_horror_channel(monkeypatch):
    ch = _horror_card()
    assert mc.niche_of(ch) == "horror" and mc.engage_kind(ch) == "horror" and not mc.today_short_due(ch)
    assert mc.summary(mc.get(ch["id"]))["kind_label"] == "Horror stories (long videos)"
    asked = {}

    def ideas(client, count, avoid, best, worst, **kw):
        asked.update(kw)
        return [{"kind": "topic", "text": "A night nurse and the empty ward"}]
    monkeypatch.setattr(hv, "channel_ideas", ideas)
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["genre"] == "history" and payload["history_mode"] == "horror" and asked["mode"] == "horror"
    assert payload["history_topic"] == "A night nurse and the empty ward"
    # Uploads: Entertainment, long; its Shorts too.
    assert mc.upload_genre(ch, {"format": "history"}) == "horror"
    assert mc.upload_genre(ch, {"format": "teaser"}) == "horror_teaser"
    assert mc.upload_genre(mc.add("history"), {"format": "teaser"}) == "history_teaser"
    assert ya.CATEGORY["horror"] == ya.CATEGORY["horror_teaser"] == "24" and "horror" in ya.LONG_GENRES


def test_engagement_speaks_horror():
    import engage
    assert engage.playlist_title("horror", None).startswith("Horror Stories")
    assert engage.playlist_title("horror", "teaser") == "Horror in 60 seconds"
    assert engage.FIRST_COMMENTS["horror"] and "fiction" in engage.WHO["horror"]
    assert "never say a story or a haunting is real" in engage.HORROR_EXTRA
    assert engage.promo_line([("@raat", "horror")]) == "More from us: @raat (horror stories)"
    assert "fiction" in mc.ABOUT["horror"]


def test_the_research_and_remix_know_the_horror_niche():
    import niche_research
    import viral_remix
    assert "horror story urdu" in niche_research.NICHES["horror"]["queries"]
    assert "horror" in viral_remix.KINDS and "fiction" in viral_remix.WHAT["horror"]
    assert viral_remix._rules("horror") == hs.RULES


def test_watch_next_links_earlier_horror_stories():
    rows = [{"genre": "horror", "status": "done", "video_id": "AAAAAAAAAAA", "title": "Haveli", "views": 50}]
    assert "https://youtu.be/AAAAAAAAAAA" in hv.watch_next("Story.\n\n#horror", rows)


def test_process_passes_the_horror_mode(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    r = TestClient(app_module.app).post("/api/process", json={
        "genre": "history", "history_topic": "A haveli at night", "history_minutes": 20, "history_mode": "horror",
        "acknowledged": True}, headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 200, r.text
    assert app_module.jobs[r.json()["job_id"]]["env"]["HISTORY_MODE"] == "horror"


def test_a_story_is_planned_at_the_slow_horror_pace():
    words, chapters, scenes = hs.shape(14)
    assert words == round(14 * hs.WPM * hs.FILL) and chapters == 8
    # At the measured 160 words a minute (first live story) it ends under 14:45 with a minute of cards...
    assert words / 160 * 60 + 60 < hv.UNVERIFIED_LIMIT
    # ...and a voice as slow as 125 a minute still fits once fit_voices speeds it up (at most FIT_MAX).
    assert words / 125 * 60 / hv.FIT_MAX + 30 < 900
    assert hv.shape(14)[0] == 14 * hv.WORDS_PER_MINUTE                      # the documentary pace is unchanged


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="ffmpeg not installed")
def test_a_film_too_long_for_an_unverified_channel_gets_a_faster_narration(tmp_path):
    wav = tmp_path / "p.wav"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=200:duration=10",
                    str(wav)], check=True)
    # Cards and pauses alone past 14:45: nothing a faster voice can fix, left as it is.
    assert hv.fit_voices([(str(wav), 10.0)], 900.0, str(tmp_path), log=lambda *a: None) == [(str(wav), 10.0)]
    # 600 s of voice in a 960 s film: 360 s of cards and pauses leave 525 s, so 600 / 525 = 1.143x.
    out = hv.fit_voices([(str(wav), 600.0), (None, 0)], 960.0, str(tmp_path), log=lambda *a: None)
    assert out[1] == (None, 0) and out[0][0].endswith("_fit.wav") and out[0][1] == pytest.approx(525.0, abs=0.05)
    # Far too long: capped at FIT_MAX (the upload may still be refused; the log says so).
    out = hv.fit_voices([(str(wav), 600.0)], 1100.0, str(tmp_path), log=lambda *a: None)
    assert out[0][1] == pytest.approx(600 / hv.FIT_MAX, abs=0.05)
    # The sped-up file really is shorter.
    secs = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 out[0][0]], capture_output=True, text=True).stdout)
    assert secs == pytest.approx(10 / hv.FIT_MAX, abs=0.1)


def test_the_title_keeps_the_search_words():
    assert hs.search_title("Khali ward mein 3:15 baje bajti hai emergency bell") == \
        "Khali ward mein 3:15 baje bajti hai emergency bell | Horror Story in Urdu"
    assert hs.search_title("Purani Haveli | Horror Story") == "Purani Haveli | Horror Story"
    assert hs.search_title("Bhoot wali raat") == "Bhoot wali raat"
    assert len(hs.search_title("x" * 120)) == 100 and hs.search_title("Raat", "english") == "Raat | Horror Story"


def test_a_shot_the_dark_grade_turns_black_is_made_again_lighter(tmp_path, monkeypatch, capsys):
    """The first live story was refused at upload for "6 s of black picture" (5-nov-2026): a chapter card and a
    night shot under the dark grade. A dark grey clip (0x282828) is black under GRADE and fine under GRADE_LIFT."""
    src = str(tmp_path / "night.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x282828:s=320x180:d=3",
                    "-pix_fmt", "yuv420p", src], check=True)
    monkeypatch.setenv("HISTORY_MODE", "horror")
    monkeypatch.setenv("HISTORY_MOTION", "0")
    out = hv.segment_video(str(tmp_path), src, "s.mp4", 48, 0.0, False, [])
    assert not hv.too_dark(str(tmp_path / out))
    assert "lighter (1)" in capsys.readouterr().out
    # Outside horror nothing is measured or made twice.
    monkeypatch.setenv("HISTORY_MODE", "history")
    monkeypatch.setattr(hv, "too_dark", lambda path: (_ for _ in ()).throw(AssertionError("measured")))
    hv.segment_video(str(tmp_path), src, "h.mp4", 24, 0.0, False, [])
    assert hv.mode_grade(1) == "" and hv.mode_grade() == ""
