"""history_maps: a tiny made-up Cliopatria (two polities, two periods) and one land polygon,
built through history_maps.build into a temp dir. Never the real data."""

import json
import subprocess

import numpy as np
import pytest

import history_maps as hm


def _square(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def _row(name, a, b, coords, kind="POLITY", wiki=""):
    return {"type": "Feature",
            "properties": {"Name": name, "FromYear": a, "ToYear": b, "Area": 1000.0, "Type": kind,
                           "Wikipedia": wiki, "Wikidata": "", "SeshatID": "", "Components": "", "MemberOf": ""},
            "geometry": {"type": "Polygon", "coordinates": coords}}


@pytest.fixture
def maps(tmp_path, monkeypatch):
    clio = {"type": "FeatureCollection", "features": [
        _row("Testland Empire", 1000, 1049, [_square(10, 10, 20, 20)], wiki="Testland Empire"),
        _row("Testland Empire", 1050, 1100, [_square(10, 10, 30, 25), _square(22, 12, 26, 16)[::-1]]),
        _row("Fakeria Sultanate", 900, 1100, [_square(32, 5, 38, 12)]),
        _row("(Allegiance of Fakeria Sultanate to Testland Empire)", 1000, 1100, [_square(32, 5, 38, 12)],
             kind="RELATION"),
    ]}
    land = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [_square(0, 0, 40, 30)]}}]}
    (tmp_path / "clio.geojson").write_text(json.dumps(clio), encoding="utf-8")
    (tmp_path / "land.geojson").write_text(json.dumps(land), encoding="utf-8")
    data = tmp_path / "data"
    hm.build(str(tmp_path / "clio.geojson"), str(tmp_path / "land.geojson"), out_dir=str(data))
    monkeypatch.setenv("HISTORY_MAPS_DIR", str(data))
    monkeypatch.delenv("HISTORY_MAPS", raising=False)
    return tmp_path


def _probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,nb_read_frames,pix_fmt", "-of", "json", str(path)],
                       capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout)["streams"][0]


def test_find_matches_names_loosely(maps):
    assert hm.available()
    assert hm.find("Testland Empire") == "Testland Empire"
    assert hm.find("testlands") == "Testland Empire"
    assert hm.find("Testlnd Empire") == "Testland Empire"        # a typo
    assert hm.find("Fakeria") == "Fakeria Sultanate"
    assert hm.find("Fakeria Caliphate") == "Fakeria Sultanate"   # the polity word may differ
    assert hm.find("Nowhere Kingdom") is None
    assert hm.find("") is None
    assert hm.find("Empire") is None
    # RELATION rows (allegiances, vassalage) are not polities and never in the cache.
    assert hm.find("Allegiance of Fakeria Sultanate to Testland Empire") is None
    assert hm.span("Testland Empire") == (1000, 1100)


def test_render_frame_count_and_size(maps):
    out = maps / "map.mp4"
    assert hm.render("Testland Empire", 1000, 1100, str(out), seconds=1.0, size=(320, 180), fps=30) == str(out)
    s = _probe(out)
    assert (s["width"], s["height"], int(s["nb_read_frames"]), s["pix_fmt"]) == (320, 180, 30, "yuv420p")


def test_render_relative_out_with_cwd_and_urdu_title(maps):
    # An Urdu title goes through libass (Pillow here has no raqm to join the letters).
    out = hm.render("testland", 990, 1060, "rel.mp4", seconds=0.5, size=(320, 180), fps=30, cwd=str(maps),
                    title="مغلیہ سلطنت")
    assert out == "rel.mp4"
    assert int(_probe(maps / "rel.mp4")["nb_read_frames"]) == 15
    assert not list(maps.glob("_map_title_*.ass"))     # the temporary title file is gone


def test_available_and_render_off_by_env(maps, monkeypatch):
    monkeypatch.setenv("HISTORY_MAPS", "0")
    assert hm.available() is False
    assert hm.render("Testland Empire", 1000, 1100, str(maps / "off.mp4"), seconds=0.5, size=(320, 180)) is None
    assert not (maps / "off.mp4").exists()


def test_render_missing_polity_or_years_returns_none(maps):
    assert hm.render("Atlantis", 1000, 1100, str(maps / "a.mp4"), seconds=0.5, size=(320, 180)) is None
    assert not (maps / "a.mp4").exists()
    # Testland has no rows before 1000: 500-800 is not a map of it.
    assert hm.render("Testland Empire", 500, 800, str(maps / "b.mp4"), seconds=0.5, size=(320, 180)) is None


def test_available_without_data(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_MAPS_DIR", str(tmp_path / "nothing"))
    monkeypatch.delenv("HISTORY_MAPS", raising=False)
    assert hm.available() is False
    assert hm.render("Testland Empire", 1000, 1100, str(tmp_path / "x.mp4"), seconds=0.5) is None


def test_nonzero_fill_is_the_union_of_polygons():
    sq = lambda x0, y0, x1, y1: np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64)  # noqa: E731
    # A square with a hole, and a second polygon sitting in that hole: the hole is filled.
    m = hm._nonzero((20, 20), [(sq(0, 0, 20, 20), False), (sq(5, 5, 15, 15), True)])
    assert m[10, 10] == False and m[2, 2] == True  # noqa: E712
    m = hm._nonzero((20, 20), [(sq(0, 0, 20, 20), False), (sq(5, 5, 15, 15), True), (sq(8, 8, 12, 12), False)])
    assert m[10, 10] == True and m[6, 6] == False  # noqa: E712
    # Two squares sharing an edge leave no seam.
    m = hm._nonzero((10, 20), [(sq(0, 0, 10, 10), False), (sq(10, 0, 20, 10), False)])
    assert m.all()
