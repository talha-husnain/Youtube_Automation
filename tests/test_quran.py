"""The Quran channel (owner, 22-oct-2026): a real qari's recitation, the
published Arabic and translations from Quran.com, 2-5 minute passages planned
in order, no AI anywhere in the Quran itself, and no cross promotion."""
import json

import pytest

import my_channels as mc
import quran_videos as qv

CHAPTERS = {str(n): {"n": n, "name": f"Surah-{n}", "arabic": "سورة", "meaning": f"meaning {n}", "ayat": 10,
                     "bismillah": True} for n in range(1, 115)}
CHAPTERS.update({str(n): {"n": n, "name": name, "arabic": "سورة", "meaning": meaning, "ayat": ayat, "bismillah": b}
                 for n, name, meaning, ayat, b in [
                (1, "Al-Fatihah", "The Opener", 7, False), (2, "Al-Baqarah", "The Cow", 286, True),
                (9, "At-Tawbah", "The Repentance", 129, False), (36, "Ya-Sin", "Ya Sin", 83, True),
                (55, "Ar-Rahman", "The Beneficent", 78, True), (67, "Al-Mulk", "The Sovereignty", 30, True),
                (112, "Al-Ikhlas", "The Sincerity", 4, True), (113, "Al-Falaq", "The Daybreak", 5, True),
                (114, "An-Nas", "Mankind", 6, True)]})


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(qv, "chapters", lambda: CHAPTERS)

    def verses(s, urdu=54, english=19):
        return [{"n": n, "key": f"{s}:{n}", "ar": "بِسْمِ ٱللَّهِ" if (s, n) == (1, 1) else f"آية {n}",
                 "ur": f"اردو ترجمہ {n}", "en": f"English {n}.", "ruku": 1 + (n - 1) // 12, "sajda": False}
                for n in range(1, CHAPTERS[str(s)]["ayat"] + 1)]
    monkeypatch.setattr(qv, "verses", verses)


def test_owner_requests_are_understood():
    assert qv.parse_request("Surah Yaseen")["surah"] == 36
    assert qv.parse_request("surah rehman")["surah"] == 55
    assert qv.parse_request("Al-Mulk")["surah"] == 67
    assert qv.parse_request("36")["text"] == "Surah Ya-Sin"
    kursi = qv.parse_request("Ayat ul Kursi")
    assert (kursi["surah"], kursi["from"], kursi["to"]) == (2, 255, 255) and kursi["owner"]
    part = qv.parse_request("2:1-20")
    assert (part["from"], part["to"], part["text"]) == (1, 20, "Surah Al-Baqarah, Ayat 1-20")
    assert qv.parse_request("2:300") is None and qv.parse_request("my favourite song") is None


def _ruku_every_12(s):
    return [1 + (n - 1) // 12 for n in range(1, CHAPTERS[str(s)]["ayat"] + 1)]


def test_a_long_surah_is_made_in_parts_that_end_on_a_ruku():
    ideas = [qv.idea(36)]
    passage, left = qv.plan_next(ideas, {}, cost_fn=lambda s, n: 20.0, open_fn=lambda s, a: 0.0,
                                 rukus_fn=_ruku_every_12)
    assert passage["segments"] == [[36, 1, 12]] and passage["part"] == 1      # 240 s, the first ruku ends
    assert left[0]["from"] == 13 and left[0]["part"] == 2 and left[0]["text"] == "Surah Ya-Sin, Ayat 13-83"
    passage, left = qv.plan_next(left, {}, cost_fn=lambda s, n: 20.0, open_fn=lambda s, a: 0.0,
                                 rukus_fn=_ruku_every_12)
    assert passage["segments"] == [[36, 13, 24]] and passage["part"] == 2
    assert qv.title_of(passage["segments"], qv.settings_of({}), passage["part"]).startswith(
        "Surah Ya-Sin Part 2 (Ayat 13-24) | Urdu Tarjuma ke Saath")


def test_a_video_never_passes_five_minutes_but_always_has_an_ayah():
    passage, _left = qv.plan_next([qv.idea(36)], {}, cost_fn=lambda s, n: 130.0, open_fn=lambda s, a: 0.0,
                                  rukus_fn=_ruku_every_12)
    assert passage["segments"] == [[36, 1, 2]] and passage["seconds"] <= qv.MAX_SECONDS
    huge, _left = qv.plan_next([qv.idea(2, 282, 282)], {}, cost_fn=lambda s, n: 400.0,
                               open_fn=lambda s, a: 0.0, rukus_fn=_ruku_every_12)
    assert huge["segments"] == [[2, 282, 282]]


def test_short_surahs_share_a_video_but_parts_never_do():
    ideas = [qv.idea(112), qv.idea(113), qv.idea(114), qv.idea(36)]
    passage, left = qv.plan_next(ideas, {}, cost_fn=lambda s, n: 9.0, open_fn=lambda s, a: 6.0,
                                 rukus_fn=_ruku_every_12)
    assert passage["segments"] == [[112, 1, 4], [113, 1, 5], [114, 1, 6]] and passage["part"] is None
    assert left[0]["surah"] == 36           # Ya-Sin does not fit whole, so it starts the next video
    assert qv.title_of(passage["segments"], qv.settings_of({})).startswith("Surah Al-Ikhlas, Al-Falaq, An-Nas |")


def test_the_bismillah_opens_a_surah_but_not_al_fatiha_at_tawbah_or_a_later_part():
    keys = lambda segs: [u["key"] for u in qv.units(segs, qv.settings_of({}))]  # noqa: E731
    assert keys([[36, 1, 2]]) == ["1:1", "36:1", "36:2"]
    assert keys([[1, 1, 2]]) == ["1:1", "1:2"]
    assert keys([[9, 1, 1]]) == ["9:1"]
    assert keys([[36, 13, 14]]) == ["36:13", "36:14"]


def test_long_ayat_are_paged_at_their_pause_marks():
    word = "كتبوا"              # five letters
    text = " ".join([word] * 12 + ["ۖ"] + [word] * 12 + ["ۚ"] + [word] * 12)
    pages = qv.arabic_pages(text, limit=70)
    assert len(pages) == 3 and pages[0].endswith("ۖ") and pages[1].endswith("ۚ")
    assert all(qv.letters(p) <= 70 for p in pages)
    assert qv.arabic_pages("الم") == ["الم"]
    parts = qv.split_words("one two three, four five six seven eight", [1, 1])
    assert parts == ["one two three,", "four five six seven eight"]


def test_translations_lose_their_footnote_numbers():
    assert qv.clean_translation('اس کتاب میں<sup foot_note=160812>1</sup> کوئی شک نہیں') == "اس کتاب میں کوئی شک نہیں"


def test_captions_merge_a_page_shown_while_recited_and_read_out(tmp_path):
    path = qv.write_srt(str(tmp_path / "c.srt"), [(0, 4, "a"), (4.1, 8, "a"), (8, 9, "b"), (9, 10, "")])
    text = open(path, encoding="utf-8").read()
    assert text.count("-->") == 2 and "00:00:00,000 --> 00:00:08,000\na" in text


def test_the_description_credits_the_qari_the_translators_and_quran_com():
    st = qv.settings_of({"reciter": 2, "urdu": 234})
    text = qv.describe([[36, 1, 12]], st, "@quran", "Stock footage: Pixabay.", True)
    assert "Abdul Basit Abdul Samad" in text and "Fateh Muhammad Jalandhari" in text and "Pickthall" in text
    assert "Quran.com (Quran Foundation)" in text and "No music." in text and "AI ki hai" in text
    assert "AI" not in qv.describe([[36, 1, 12]], qv.settings_of({"voice": "off"}), "", "", False)
    assert qv.settings_of({"reciter": 999, "screen": "x", "voice": "off"}) == {**qv.DEFAULTS, "voice": "off"}


def test_the_card_is_a_quran_channel_without_ai_replies_or_promotion():
    ch = mc.add("quran")
    assert ch["auto_reply"] is False and ch["cross_promo"] is False and ch["quran"] == qv.DEFAULTS
    assert "minutes" not in ch
    s = mc.summary(mc.get(ch["id"]))
    assert s["long"] and s["plans_ideas"] and s["quran_options"]["reciters"] and "mode" not in s
    assert mc.teaser_due(mc.get(ch["id"])) is None and not mc.today_short_due(mc.get(ch["id"]))
    ch = mc.update(ch["id"], {"quran": {"reciter": 6, "voice": "off", "urdu": 1}})
    assert ch["quran"]["reciter"] == 6 and ch["quran"]["voice"] == "off" and ch["quran"]["urdu"] == 54
    assert mc.promote("desc", ch["id"]) == "desc"
    assert all(kind != "quran" for _h, kind in mc.promo_targets("main"))


def test_the_next_video_is_planned_and_a_finished_surah_is_remembered(monkeypatch):
    ch = mc.add("quran")
    asked = {}

    def plan(ideas, settings):
        asked["ideas"], asked["settings"] = ideas, settings
        return {"segments": [[1, 1, 7]], "seconds": 104.8, "part": None}, ideas[1:]
    monkeypatch.setattr(qv, "plan_next", plan)
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert asked["ideas"][0]["surah"] == 1 and asked["settings"]["reciter"] == 7
    assert payload["genre"] == "quran" and payload["quran_plan"]["segments"] == [[1, 1, 7]]
    assert payload["quran_plan"]["voice"] == "urdu" and payload["frame_outro"] is False
    assert meta["format"] == "quran" and meta["label"] == "Surah Al-Fatihah" and "series" not in meta
    after = mc.get(ch["id"])
    assert "quran:1" in after["used"] and after["ideas"][0]["surah"] == 36


def test_a_failed_passage_is_made_again_before_the_next_one(monkeypatch):
    ch = mc.add("quran")
    passage = {"segments": [[36, 1, 12]], "seconds": 250, "part": 1}
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "j1", "status": "failed", "format": "quran",
                                                    "passage": passage, "label": "Surah Ya-Sin Part 1",
                                                    "passage_try": 1, "at": 1}]))
    monkeypatch.setattr(qv, "plan_next", lambda *a: pytest.fail("planned past a failed passage"))
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["quran_plan"]["segments"] == [[36, 1, 12]] and meta["passage_try"] == 2
    assert meta["series"] == "Surah Ya-Sin, Urdu Tarjuma ke Saath" and meta["series_part"] == 1
    assert mc.get(ch["id"])["jobs"][0]["redone"] is True


def test_owner_can_put_a_surah_first_and_drop_one():
    ch = mc.add("quran")
    mc._change(ch["id"], lambda c: c.update(ideas=qv.queue()[:3]))
    mc.add_idea(ch["id"], "Surah Mulk")
    assert mc.get(ch["id"])["ideas"][0]["surah"] == 67
    with pytest.raises(ValueError, match="surah"):
        mc.add_idea(ch["id"], "something funny")
    mc.drop_idea(ch["id"], "Surah Ya-Sin")
    after = mc.get(ch["id"])
    assert all(i["surah"] != 36 for i in after["ideas"]) and "quran:36" in after["used"]
    assert all(i["id"] != "36" for i in qv.queue([u[6:] for u in after["used"] if u.startswith("quran:")]))


def test_a_long_surah_gets_its_own_playlist():
    import engage
    assert engage.PLAYLISTS[("quran", None)] and "quran" in engage.FIRST_COMMENTS and "quran" in engage.WHO
    assert "never explain" in engage.QURAN_EXTRA


def test_process_passes_the_passage_to_the_job(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    mc.add("quran")
    plan = {"segments": [[36, 1, 12]], "reciter": 7, "screen": "both", "voice": "urdu"}
    r = TestClient(app_module.app).post("/api/process", json={
        "genre": "quran", "channel": "quran", "quran_plan": plan, "acknowledged": True},
        headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 200, r.text
    env = app_module.jobs[r.json()["job_id"]]["env"]
    assert env["CONTENT_GENRE"] == "quran" and json.loads(env["QURAN_PLAN"])["segments"] == [[36, 1, 12]]


def test_uploads_are_long_videos_in_education():
    import youtube_account
    assert "quran" in youtube_account.LONG_GENRES and youtube_account.CATEGORY["quran"] == "27"
