"""The money channel (money_shorts.py, motion_scenes.py): every number on screen or in the voice must be in
the research, comparisons never cross currencies, code computes ratios, and every template draws."""
import json
import re
import types

import pytest

import money_shorts as mo
import motion_scenes as ms
import my_channels as mc

FACTS = """Petrol cost Rs 56 per litre in Pakistan in 2005 (OGRA).
Petrol cost Rs 265.45 per litre in October 2025 (OGRA).
Pakistan's remittances were $38.3 billion in FY2025 (State Bank of Pakistan).
A driver in Dubai earns AED 2,500 a month (Bayt, 2025); in Karachi Rs 45,000 a month (Rozee, 2025).
Gold was Rs 4,32,000 per tola in 2025 and Rs 9,500 in 2005 (All Pakistan Gems Association).
21 percent of adults have a bank account and 34 percent use a mobile wallet (SBP, 2024)."""


def _item(name, value, shown, country=""):
    return mo.Item(name=name, value=value, shown=shown, country=country)


def _beat(template, items, line="Yeh number dekho", headline="Headline", better="higher"):
    return mo.Beat(template=template, headline=headline, unit="", better=better, items=items, note="OGRA, 2025",
                   line=line)


def _script(beats, **kw):
    base = dict(found=True, allowed=True, reason="", title="Petrol kitna mehnga hua?", kicker="PRICE CHECK",
                hook_line="2005 mein 56 rupay, aaj 265 rupay!", hook_number="Rs 265", beats=beats,
                payoff_label="Gold since 2005", payoff_shown="Rs 4,32,000",
                verdict_line="Sona 4,32,000 rupay tola ho gaya.", question="Aap ke shehar mein kitna? Comment mein batao")
    return mo.Script(**{**base, **kw})


def test_numbers_are_read_with_their_scale_and_rounding():
    have = mo._known(FACTS)
    assert 38.3e9 in have and 265.45 in have and 432000 in have
    assert mo.unsupported("38.3 arab dollar aaye", have) == []          # the scale word counts
    assert mo.unsupported("$38.3B", have) == [] and mo.unsupported("$38B", have) == []   # 38.3 rounded is 38
    assert mo.unsupported("$39B", have) == ["39B"] and mo.unsupported("39 arab", have) == ["39 arab"]
    assert mo.unsupported("Rs 265", have) == []                          # 265.45 written rounded
    assert mo.unsupported("23 crore log", have) == ["23 crore"]          # a scaled number matches only as scaled
    assert mo.unsupported("2005 mein", have) == [] and mo.unsupported("1999 mein", have) == ["1999"]
    assert mo.unsupported("5 mulk", have) == [] and mo.unsupported("Rs 5", have) == ["5"]   # counts are free, money is not
    assert [f[0] for f in mo.figures("4.7x mehnga")] == [4.7]
    extra = mo.derived([265.45, 56], years=[2005, 2025])
    assert mo.unsupported("4.7 guna mehnga, 20 saal mein", have, extra) == []      # code's ratio, the years' gap
    assert mo.unsupported("47 guna mehnga", have, extra) == ["47"]


def test_scenes_without_research_numbers_or_in_two_currencies_are_dropped():
    beats = [
        _beat("big_number", [_item("Petrol 2025", 265.45, "Rs 265.45"), _item("2005", 56, "Rs 56")],
              line="Aaj petrol 265 rupay ka hai"),
        _beat("versus", [_item("Karachi", 45000, "Rs 45,000", "Pakistan"), _item("Dubai", 2500, "AED 2,500", "UAE")]),
        _beat("big_number", [_item("Driver, Karachi", 45000, "Rs 45,000"), _item("Dubai", 2500, "AED 2,500")]),
        _beat("timeline", [_item("2005", 9500, "Rs 9,500"), _item("2015", 47000, "Rs 47,000"),
                           _item("2025", 432000, "Rs 4,32,000")]),
        _beat("grid", [_item("bank account", 21, "21%"), _item("mobile wallet", 34, "34%")]),
        _beat("bars", [_item("A", 1.2, "$1.2"), _item("B", 2.4, "$2.4"), _item("C", 3.1, "$3.1")]),
        _beat("fact", [], line="Remittances 99 arab dollar"),
    ]
    script = _script(beats, hook_number="Rs 999")
    kept, problems = mo.validate(script, FACTS)
    assert [b.template for b in kept] == ["big_number", "big_number", "grid"]
    assert len(kept[1].items) == 1                                 # the dirham comparison went, the number stays
    joined = " ".join(problems)
    assert "one measure in one currency" in joined and "15,000" not in joined
    assert "timeline" not in [b.template for b in kept] and "47,000" in joined   # a price the research lacks
    assert script.hook_number == ""                                # the poster falls back to words


def test_rupees_of_two_countries_never_compare_and_ratios_come_from_code():
    pk, ind = _item("Pakistan", 265, "Rs 265", "Pakistan"), _item("India", 95, "Rs 95", "India")
    assert not ms.comparable([pk, ind])
    assert ms.comparable([_item("2005", 56, "Rs 56"), _item("2025", 265, "Rs 265")])
    assert not ms.comparable([_item("a", 1, "$1"), _item("b", 1, "AED 1")])
    assert ms.change(265.45, 56) == "4.7x" and ms.change(120, 100) == "+20%" and ms.change(30, 100) == "-70%"
    assert ms.change(5, 0) == ""


def test_count_ups_keep_the_way_a_number_is_written():
    steps = ms.counting("Rs 4,32,000")
    assert steps[-1] == "Rs 4,32,000" and all(s.startswith("Rs ") for s in steps)
    assert re.fullmatch(r"Rs \d,\d\d,\d{3}", steps[-2])                 # lakh grouping while it counts
    assert ms.counting("$2.3B")[-1] == "$2.3B" and re.fullmatch(r"\$\d\.\dB", ms.counting("$2.3B")[3])
    assert ms.counting("no number") == ["no number"]
    assert ms._wrap("The deal Yahoo said no to", 24).count(r"\N") == 1
    assert ms._wrap("The deal Yahoo said no to", 24).split(r"\N")[1] != "to"


def test_every_template_draws_inside_the_board():
    beats = [
        _beat("big_number", [_item("Petrol 2025", 265.45, "Rs 265.45"), _item("2005", 56, "Rs 56")]),
        _beat("versus", [_item("2005", 56, "Rs 56"), _item("2025", 265.45, "Rs 265.45")]),
        _beat("bars", [_item("A", 1.2, "$1.2", "Pakistan"), _item("B", 2.4, "$2.4"), _item("C", 3.1, "$3.1")]),
        _beat("timeline", [_item("2005", 9500, "Rs 9,500"), _item("2025", 432000, "Rs 4,32,000"),
                           _item("2015", 47000, "Rs 47,000")]),
        _beat("list", [_item("A", 1, "$1T"), _item("B", 3, "$3T"), _item("C", 2, "$2T")], better="higher"),
        _beat("grid", [_item("bank", 21, "21%"), _item("wallet", 34, "34%")]),
        _beat("fact", [_item("offer", 44.6, "$44.6B")]),
        _beat("fact", []),
    ]
    script = _script(beats)
    windows = [(k, k * 4.0, k * 4.0 + 4.0) for k in range(len(beats) + 3)]
    flags = {"pakistan": {36: "f36.png", 40: "f40.png", 44: "f44.png", 64: "f64.png"}}
    ev, images, sfx = ms.events(script, windows, windows[-1][2], "@h", ms.palette_for("x"), flags)
    assert images and images[0]["path"] == "f36.png" and sfx
    for e in ev:
        assert e.startswith("Dialogue: ")
        for x, y in re.findall(r"\\pos\((\-?\d+),(\-?\d+)\)", e):
            if int(y) > 470:                            # under the title band: the board, never the caption band
                assert int(y) <= ms.cs.BOARD_END + 1, e
    ranked = [e for e in ev if "CkBadgeDark" in e and r"\fs52" in e]
    assert len(ranked) == 3                            # the list's ranks are drawn, best first after sorting
    # A cheaper price can "win", but the ratio always names the bigger value.
    cheap = _beat("versus", [_item("Jan 2005", 40.39, "Rs 40.39"), _item("Oct 2026", 377.91, "Rs 377.91")],
                  better="lower")
    got, _i, _s = ms.versus(cheap, 0.0, 4.0, ms.palette_for("x"), {})
    assert any("OCT 2026: 9.4x" in e for e in got) and not any("JAN 2005: 9.4x" in e for e in got)


def test_a_failed_fact_check_gets_one_rewrite_then_no_video(monkeypatch):
    monkeypatch.setattr(mo, "research", lambda c, t: (FACTS, [(str(k), "u") for k in range(4)]))
    good = [_beat("big_number", [_item("Petrol 2025", 265.45, "Rs 265.45")], line="Aaj petrol 265 rupay")] * 4
    calls = []

    def ask(client, schema, prompt, model=None):
        calls.append((schema.__name__, prompt))
        if schema is mo.Script:
            return _script(list(good))
        return mo.Check(ok=False, problems=["net worth told as income"])
    monkeypatch.setattr(mo.kit, "ask_json", ask)
    with pytest.raises(RuntimeError, match="checks twice"):
        mo.write(None, "Petrol prices", "@h", log=lambda *a: None)
    assert [c[0] for c in calls] == ["Script", "Check", "Script", "Check"]
    assert "net worth told as income" in calls[2][1]
    monkeypatch.setattr(mo.kit, "ask_json", lambda c, schema, p, model=None:
                        _script(list(good)) if schema is mo.Script else mo.Check(ok=True, problems=[]))
    script, facts, sources = mo.write(None, "Petrol prices", "@h", log=lambda *a: None)
    assert len(script.beats) == 4 and len(sources) == 4
    monkeypatch.setattr(mo, "research", lambda c, t: ("NOT ALLOWED: investment advice", [("a", "u")] * 5))
    with pytest.raises(RuntimeError, match="Not covered"):
        mo.write(None, "Which stock to buy", "@h")


def test_videos_and_social_posts_are_not_sources():
    def chunk(title):
        return types.SimpleNamespace(web=types.SimpleNamespace(title=title, uri=f"https://redirect/{title}"))
    gm = types.SimpleNamespace(grounding_chunks=[chunk("dawn.com"), chunk("youtube.com"), chunk("www.facebook.com"),
                                                 chunk("sbp.org.pk"), chunk("dawn.com"), chunk("x.com")])

    class Models:
        def generate_content(self, model, contents, config=None):
            return types.SimpleNamespace(text="FACT", candidates=[types.SimpleNamespace(grounding_metadata=gm)])
    facts, sources = mo.research(types.SimpleNamespace(models=Models()), "Petrol prices")
    assert [name for name, _u in sources] == ["dawn.com", "sbp.org.pk"]


def test_the_money_channel_plans_and_sends_one_topic(monkeypatch):
    import cricket_shorts
    monkeypatch.setattr(cricket_shorts, "grounded", lambda client, prompt: (
        "topic: How much costlier has petrol got in Pakistan since 2005?\ntopic: Old one", []))
    got = mo.channel_ideas(None, 4, avoid=["Old one"])
    assert got == [{"kind": "topic", "text": "How much costlier has petrol got in Pakistan since 2005?"}]
    ch = mc.add("money")
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["genre"] == "money" and payload["money_topic"].startswith("How much")
    assert meta["format"] == "money" and meta["idea"]["text"].startswith("How much")


def test_process_accepts_a_money_job(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    mc.add("money")
    r = TestClient(app_module.app).post("/api/process", json={
        "genre": "money", "channel": "money", "money_topic": "Petrol since 2005", "acknowledged": True,
        "bg_music": True}, headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 200, r.text
    src = json.loads((tmp_path / r.json()["job_id"] / ".source.json").read_text())
    assert src["genre"] == "money"
