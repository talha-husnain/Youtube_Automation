"""How the generated Shorts look (29-oct-2026): cricket footage that passes (the daily pool, its tags,
the relaxed rule, unused clips before repeats, full HD first), footage that shows (glass card panels
over a blur, sharpening only what was enlarged), and captions kept out of YouTube's own overlay
(one line inside x 192-888, glyphs ending by y 1440), with abbreviations and the pop fixed."""
import os
import subprocess

import numpy as np
import pytest

import broll
import cricket_shorts as cs
import short_kit as kit
import stock_media as sm
import subtitles


def _clip(cid, w=1080, h=1920, kind="video", tag=None):
    c = {"id": cid, "kind": kind, "thumb": f"t-{cid}", "url": f"u-{cid}", "provider": "Pixabay", "w": w, "h": h,
         "seconds": 10.0, "author": "", "page": ""}
    return {**c, "tag": tag} if tag else c


# ---------------------------------------------------------------- the pool

def test_the_pool_searches_once_a_day_tags_each_clip_once_and_keeps_a_week(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "xk")
    searched, tagged = [], []
    found = {"cricket": [_clip("a"), _clip("b"), {**_clip("bug"), "alt": "field cricket, insect, chirping"}],
             "cricket match": [_clip("c"), {**_clip("ball"), "alt": "football stadium, bundesliga"}]}

    def search(term, portrait=True, kind="video", crop=False):
        searched.append((term, kind, crop))
        return found.get(term, []) if kind == "video" else []
    monkeypatch.setattr(sm, "search", search)

    def tag_pool(client, kind, items, model=None):
        tagged.extend(c["id"] for c in items)
        return {"a": "cricket", "b": "reject", "c": "atmosphere"}
    monkeypatch.setattr(sm, "tag_pool", tag_pool)
    got = sm.pool("cricket", client=object(), log=lambda *a: None)
    assert sorted(c["id"] for c in got) == ["a", "c"]                        # the rejected one never comes back
    assert {t for t, _k, _c in searched} == set(sm.POOL_TERMS["cricket"])
    assert all(c for _t, k, c in searched if k == "video")                  # videos may be cropped 4K
    assert ("cricket", "photo", False) in searched                          # a thin term gets photos too
    n = len(searched)
    assert sorted(c["id"] for c in sm.pool("cricket", client=object(), log=lambda *a: None)) == ["a", "c"]
    assert len(searched) == n and sorted(tagged) == ["a", "b", "c"]           # same day: no search, no re-tag
    # Another sport or the insect, by the library's own tags: rejected before any vision call.
    assert sm._read(sm.POOL_FILE, {})["cricket"]["items"]["bug"]["tag"] == "reject"
    assert sm._read(sm.POOL_FILE, {})["cricket"]["items"]["ball"]["tag"] == "reject"
    data = sm._read(sm.POOL_FILE, {})
    data["cricket"]["day"] = "2000-01-01"
    data["cricket"]["items"]["a"]["at"] -= 8 * 86400                          # older than a week, not found again
    sm._write(sm.POOL_FILE, data)
    found["cricket"] = [_clip("b")]
    assert [c["id"] for c in sm.pool("cricket", client=object(), log=lambda *a: None)] == ["c"]
    assert sm.pool("quiz", client=object()) == [] and sm.pool("", client=object()) == []


def test_untagged_clips_wait_when_the_check_fails(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "xk")
    monkeypatch.setattr(sm, "search", lambda term, portrait=True, kind="video", crop=False:
                        [_clip("a")] if kind == "video" else [])

    def broken(*a, **k):
        raise RuntimeError("503 UNAVAILABLE")
    monkeypatch.setattr(sm, "tag_pool", broken)
    assert sm.pool("cricket", client=object(), log=lambda *a: None) == []
    monkeypatch.setattr(sm, "tag_pool", lambda client, kind, items, model=None: {"a": "atmosphere"})
    assert [c["id"] for c in sm.pool("cricket", client=object(), log=lambda *a: None)] == ["a"]


def test_the_tag_check_reads_one_vision_answer_and_rejects_what_it_cannot_see(monkeypatch):
    monkeypatch.setattr(sm, "_thumb_part", lambda url: None if url == "t-broken" else f"part:{url}")
    asked = {}

    def ask(client, schema, contents, model=None):
        asked["parts"], asked["prompt"] = contents[:-1], contents[-1]
        return sm.PoolTags(tags=[sm.PoolTag(clip=0, tag="Cricket"), sm.PoolTag(clip=1, tag="atmosphere"),
                                 sm.PoolTag(clip=2, tag="football"), sm.PoolTag(clip=9, tag="cricket")])
    monkeypatch.setattr(kit, "ask_json", ask)
    items = [_clip("a"), {**_clip("b"), "alt": "Muralitharan bowling to Adam Gilchrist.jpg"},
             {**_clip("broken"), "thumb": "t-broken"}, _clip("c")]
    got = sm.tag_pool(object(), "cricket", items)
    assert got == {"a": "cricket", "b": "atmosphere", "c": "reject", "broken": "reject"}
    assert asked["parts"] == ["part:t-a", "part:t-b", "part:t-c"]
    for word in ("football", "baseball", "hockey", "readable text", "atmosphere", "painting", "named player",
                 "1: video, Muralitharan bowling to Adam Gilchrist.jpg"):
        assert word in asked["prompt"]


def test_portrait_shorts_may_take_small_landscape_4k_files_cropped_but_never_upscaled():
    files = [(1920, 1080, "hd-landscape", 9_000_000), (3840, 2160, "4k-landscape", 20_000_000),
             (720, 1280, "720p-portrait", 2_000_000)]
    assert sm._rendition(files, True) == (720, 1280, "720p-portrait")           # the old rule: last resort
    assert sm._rendition(files, True, crop=True) == (3840, 2160, "4k-landscape")  # its 9:16 centre is 1215 wide
    assert sm._rendition(files + [(1080, 1920, "fhd-portrait", 4_000_000)], True, crop=True)[2] == "fhd-portrait"
    assert sm._rendition([(1920, 1080, "hd", 5_000_000)], True, crop=True) is None   # would be enlarged 1.8x
    assert sm._rendition([(3840, 2160, "huge", 60_000_000)], True, crop=True) is None  # over CROP_MAX_MB
    assert sm._rendition([(3840, 2160, "unknown")], True, crop=True) is None            # size unknown (Pexels)
    assert not broll.upscaled({"w": 3840, "h": 2160}, 1080, 1920)


def test_the_cricket_rule_takes_neutral_atmosphere_but_never_another_sport():
    rule = cs.CRICKET_FOOTAGE
    for word in ("stadium lights", "crowd", "grass", "trophy", "6-7"):
        assert word in rule
    assert "Never another sport" in rule and "football" in rule and "baseball" in rule


# ---------------------------------------------------------------- filling the lines

def test_lines_without_a_pick_get_unused_pool_clips_before_any_repeat(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "xk")
    own = {"x": [_clip("s1")], "y": [], "z": []}
    monkeypatch.setattr(sm, "search", lambda term, portrait=True, kind="video": own[term] if kind == "video" else [])
    sm.mark_used(["p-recent"])
    data = sm._read(sm.USED_FILE, {})
    data["p-old"] = 1000                                                      # used long ago
    sm._write(sm.USED_FILE, data)
    seen = {}

    def choose(client, topic, scenes, pools, model=None, rule="", general=()):
        seen["general"] = [c["id"] for c in general]
        return [pools[0][0], None, None]
    monkeypatch.setattr(sm, "choose", choose)
    monkeypatch.setattr(sm, "download", lambda item: f"/cache/{item['id']}.mp4")
    pool = [_clip("p-recent", tag="cricket"), _clip("p-old", tag="atmosphere"), _clip("p-new", tag="atmosphere"),
            _clip("s1", tag="cricket")]
    got = sm.for_scenes(object(), "t", ["one", "two", "three"], ["x", "y", "z"], log=lambda *a: None,
                        rule="r", pool=pool)
    assert [g["id"] for g in got] == ["s1", "p-new", "p-old"]              # never used, then used longest ago
    assert seen["general"] == ["p-new", "p-old", "p-recent"]              # the scene's own clip is not offered twice


def test_a_pool_clip_that_will_not_download_is_replaced(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "xk")
    monkeypatch.setattr(sm, "search", lambda term, portrait=True, kind="video": [])
    monkeypatch.setattr(sm, "choose", lambda client, topic, scenes, pools, model=None, rule="", general=(): [None])
    monkeypatch.setattr(sm, "download", lambda item: None if item["id"] == "bad" else f"/c/{item['id']}")
    got = sm.for_scenes(object(), "t", ["one"], ["x"], log=lambda *a: None,
                        pool=[_clip("bad", tag="cricket"), _clip("good", tag="cricket")])
    assert got[0]["id"] == "good"


def test_full_hd_candidates_come_before_720p_ones(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "xk")
    low, hd = _clip("low", 720, 1280), _clip("hd", 1080, 1920)
    monkeypatch.setattr(sm, "search", lambda term, portrait=True, kind="video": [low, hd] if kind == "video" else [])
    seen = {}

    def choose(client, topic, scenes, pools, model=None, rule=""):
        seen["pools"] = [[c["id"] for c in p] for p in pools]
        return [None]
    monkeypatch.setattr(sm, "choose", choose)
    sm.for_scenes(object(), "t", ["one"], ["x"], log=lambda *a: None)
    assert seen["pools"] == [["hd", "low"]]
    assert sm.full_hd(hd) and not sm.full_hd(low)


def test_a_line_without_a_clip_borrows_the_least_used_one_not_its_neighbour():
    a, b = {"kind": "video", "seconds": 9.0, "path": "a"}, {"kind": "video", "seconds": 9.0, "path": "b"}
    windows = [(k * 3.0, k * 3.0 + 3.0, str(k)) for k in range(5)]
    shots = broll.plan_shots(windows, [a, None, None, b, None])
    used = [s[1]["path"] for s in shots]
    assert used == ["a", "b", "a", "b", "a"]                       # was a, a, a, b, b
    assert sum(f for f, *_r in shots) == round(15.0 * broll.FPS)
    assert [s[1]["path"] for s in broll.plan_shots(windows, [a, b, a, b, a])] == used


# ---------------------------------------------------------------- footage that shows

def test_only_enlarged_clips_are_sharpened(monkeypatch, tmp_path):
    assert not broll.upscaled({"w": 1080, "h": 1920}, 1080, 1920)
    assert broll.upscaled({"w": 720, "h": 1280}, 1080, 1920)
    assert broll.upscaled({}, 1080, 1920)                          # size unknown: sharpened as before
    assert broll.upscaled({"w": 1080, "h": 1920}, 1080, 1920, slow=True)    # a RIFE copy is 1280 at most
    assert broll.DIM.startswith("eq=brightness=-0.04")
    seen = []

    def run(cmd, **k):
        seen.append(cmd[cmd.index("-vf") + 1])
        return type("R", (), {"returncode": 0, "stderr": ""})()
    monkeypatch.setattr(broll.subprocess, "run", run)
    broll._shot(str(tmp_path), 0, 30, {"kind": "video", "path": "a.mp4", "w": 1080, "h": 1920}, 0.0, False, 1080, 1920)
    broll._shot(str(tmp_path), 1, 30, {"kind": "video", "path": "b.mp4", "w": 720, "h": 1280}, 0.0, False, 1080, 1920)
    assert broll.SHARPEN not in seen[0] and broll.SHARPEN in seen[1]


def test_card_panels_turn_to_glass_only_over_footage():
    fact = cs.Fact(headline="Debut Par 5 Wickets", stat="5/32", detail="Pehle Pakistani bowler.", line="x")
    ev = cs.fact_events(1, 3, fact, 2.0, 6.5)
    boxes = cs.frost_boxes(ev)
    assert boxes == [(cs.CARD_X, cs.CARD_Y, cs.CARD_W, cs.CARD_H, 48, 2.0, 6.5)]
    glassy = cs.glass(ev)
    panel = [e for e in glassy if ",Shape,frost " in e]
    assert len(panel) == 1 and rf"\1a&H{cs.GLASS_ALPHA}&" in panel[0]
    assert [e for e in glassy if ",Shape,frost " not in e] == [e for e in ev if ",Shape,frost " not in e]
    # On the gradient the panel is drawn exactly as before: only the event's name differs.
    plain = [e for e in ev if ",Shape,frost " in e][0]
    name = f",Shape,frost {cs.CARD_X} {cs.CARD_Y} {cs.CARD_W} {cs.CARD_H} 48,"
    assert r"\1a&H30&" in plain and plain.replace(name, ",Shape,,") == cs._shape(
        2, 2.0, 6.5, cs.fl._round_rect(cs.CARD_W, cs.CARD_H, 48), "&H2B140E&", alpha="30",
        move=(cs.CARD_X + cs.SWIPE, cs.CARD_Y, cs.CARD_X, cs.CARD_Y, 0, cs.SWIPE_MS), extra=r"\fad(0,200)")


def _sharpness(img):
    lap = np.abs(np.diff(img.astype(float), 2, axis=0))[:, 1:-1] + np.abs(np.diff(img.astype(float), 2, axis=1))[1:-1, :]
    return float(lap.mean())


def test_the_footage_under_a_glass_panel_is_blurred(tmp_path):
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=360x640:d=3:r=30",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    item = {"kind": "video", "seconds": 3.0, "path": str(clip), "w": 360, "h": 640}
    shots = broll.plan_shots([(0.0, 2.0, "a")], [item])
    # A card from 0.5 s on, on the 1080x1920 canvas: scaled to this 360x640 background.
    out = broll.build(str(tmp_path), shots, size=(360, 640), frost=[(150, 600, 780, 600, 48, 0.5, 2.0)])
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "1.5", "-i", out, "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    img = np.frombuffer(raw, np.uint8).reshape(640, 360)
    inside, outside = img[220:380, 70:290], img[20:180, 70:290]
    assert _sharpness(inside) < 0.5 * _sharpness(outside)


# ---------------------------------------------------------------- captions

def _transcript(text, step=0.32):
    words, t = [], 0.0
    for w in text.split():
        words.append({"word": " " + w, "start": round(t, 2), "end": round(t + step - 0.02, 2)})
        t += step
    return {"segments": [{"start": 0.0, "end": t, "text": text, "words": words}]}, t


def test_generated_shorts_get_the_safe_caption_style_and_comedy_keeps_its_own(monkeypatch):
    monkeypatch.delenv("CAPTION_SAFE", raising=False)
    monkeypatch.setenv("CAPTION_EMPHASIS", "1")
    assert subtitles.auto_caption_style()["box"] == subtitles.SAFE_BOX
    monkeypatch.setenv("CAPTION_SAFE", "0")
    assert subtitles.auto_caption_style() is subtitles.AUTO_CAPTION_STYLE
    monkeypatch.delenv("CAPTION_SAFE")
    monkeypatch.setenv("CAPTION_EMPHASIS", "0")
    assert subtitles.auto_caption_style() is subtitles.AUTO_CAPTION_STYLE


def test_generated_captions_stay_out_of_youtubes_overlay(tmp_path, monkeypatch):
    """Every frame of a long caption track drawn by libass: the lit pixels (text and its black outline
    on a grey canvas) never pass y 1446 (YouTube's title and channel row cover the bottom quarter) nor
    leave x 48-888 (the like/comment column is right of 888), no caption wraps onto a second line, and
    one that fits in 192-888 stays centred on the frame."""
    monkeypatch.setenv("CAPTION_EMPHASIS", "1")
    st = subtitles.auto_caption_style()
    tr, secs = _transcript("Babar Azam ne sirf 31 balls par century bana di, kya baat hai Dr. Shoaib vs. Kohli "
                           "SABSE AAGE HAI. Responsibilities Internationally 35 balls par Muhammad Rizwan wicketkeeper "
                           "Champions Trophy 2025 mein Pakistan ki shandaar batting dekhne ko mili")
    ass = tmp_path / "c.ass"
    assert subtitles.generate_ass(tr, 0.0, secs, str(ass), max_chars=st["max_chars"], max_duration=st["max_duration"],
                                  fontsize=st["font_size"], alignment="top", margin_v=kit.caption_margin(),
                                  font_name=st["font_name"], border_width=st["border_width"],
                                  highlight_color=st["highlight_color"], effect=st["effect"],
                                  uppercase=st["uppercase"], box=st["box"])
    fonts = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=0x404040:s=1080x1920:d={secs:.2f}:r=12",
                          "-vf", f"ass=filename='{subtitles.escape_filter_value(str(ass))}'"
                                 f":fontsdir='{subtitles.escape_filter_value(fonts)}'",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, 1920, 1080)
    lit = (np.abs(frames.astype(int) - 64) > 24)
    ys, xs = np.nonzero(lit.any(axis=0))
    # 1446: a comma's outline at the top of a pop (measured 1433 at font 38; 1445 at font 40).
    assert ys.max() <= 1446 and ys.min() > cs.BOARD_END
    assert xs.min() >= 46 and xs.max() <= 890
    heights = [np.ptp(np.nonzero(f.any(axis=1))[0]) for f in lit if f.any()]
    assert max(heights) < 230                                        # one line (two would be ~420 px)
    narrow = [np.nonzero(f.any(axis=0))[0] for f in lit if f.any()]
    narrow = [c for c in narrow if c.max() - c.min() < 600]
    assert narrow and all(abs((c.min() + c.max()) / 2 - 540) < 12 for c in narrow)


def test_boards_cards_and_labels_end_above_the_captions():
    import music_shorts as ms
    import stickers
    caption_top = kit.CAPTION_TOP_PX + 41      # the first lit row (outline) of a caption line, measured
    assert cs.CARD_Y + cs.CARD_H <= cs.BOARD_END < caption_top
    assert cs.CARD_Y + cs.DOTS_DY + 11 <= cs.BOARD_END
    assert cs.ROW_Y0 + (cs.VS_ROWS - 1) * cs.ROW_GAP + cs.ROW_H // 2 <= cs.BOARD_END
    assert cs.RANK_Y0 + 4 * cs.RANK_GAP + cs.RANK_H // 2 <= cs.BOARD_END
    assert cs.RANK_ASK_Y + 39 < cs.RANK_Y0 - cs.RANK_H // 2          # the closing pill above row #1
    assert cs.RANK_VALUE_X <= 888 and cs.RANK_BAR_X + cs.RANK_BAR_W <= 900   # numbers left of the buttons
    assert cs.LABEL_Y + 39 <= cs.BOARD_END
    assert cs.PHOTO_Y + 840 * cs.PHOTO_SCALE / 2 * 1.06 <= cs.BOARD_END    # the card PNG, zoomed 6% by its end
    assert cs.CARD_Y + cs.CARD_H - 39 + 39 <= cs.BOARD_END                 # the name revealed on a card
    assert ms.FOLLOW_Y + 40 <= 1440 and ms.NEXT_Y < 1440
    assert stickers.Y + stickers.SIZE / 2 <= 1440


def test_lyrics_wrap_inside_the_safe_area():
    import music_shorts as ms
    ev = ms.lyric_events([("A long lyric line that would reach the buttons on the right", 1.0, 3.0),
                          ("Next line", 3.5, 5.0)], 6.0, "Title", "pop", "@h")
    lyric = [e for e in ev if ",MuLine," in e or ",MuNext," in e]
    assert lyric and all(",192,192,0,," in e for e in lyric)


def test_abbreviations_and_initials_do_not_end_a_caption():
    ends = subtitles._ends_sentence
    for word, nxt in (("Dr.", "Shoaib"), ("vs.", "Kohli"), ("M.S.", "Dhoni"), ("A.", "B."), ("No.", "1"),
                      ("etc.", "aur"), ("(Mr.", "Khan")):
        assert not ends(word, nxt), word
    for word, nxt in (("hai.", "Phir"), ("kya?", "Haan"), ("wah!", "Ab"), ("2018.", "Phir"), ("No.", "Phir")):
        assert ends(word, nxt), word
    tr, secs = _transcript("Kya baat hai Dr. Shoaib vs. Kohli kaun? Phir aage", step=0.2)
    blocks = [" ".join(w["word"] for w in b) for b in subtitles._collect_word_blocks(tr, 0, secs, 16, 1.4)]
    assert not any(b.endswith("Dr.") or b.endswith("vs.") for b in blocks), blocks
    assert any("Dr. Shoaib" in b for b in blocks) and any("vs. Kohli" in b for b in blocks)
    assert 1 in subtitles._emphasised(["Dr.", "Shoaib"])             # the name after "Dr." is a name


def test_the_active_word_pops_and_settles_back(tmp_path):
    tr, secs = _transcript("pop goes the word")
    out = tmp_path / "p.ass"
    assert subtitles.generate_ass(tr, 0, secs, str(out), effect="pop")
    text = out.read_text(encoding="utf-8-sig")
    assert "\\fscx90\\fscy90\\t(0,110,\\fscx108\\fscy108)\\t(110,200,\\fscx100\\fscy100)" in text
