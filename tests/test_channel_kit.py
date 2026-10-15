"""The channel kit: copy and images made, and only the About text, keywords
and banner sent to YouTube, keeping the channel's other branding."""
import json
import os
import types

import pytest

import channel_kit as ck
import my_channels as mc
import youtube_account as ya


def _kit():
    return ck.Kit(names=["Tareekh Kahani", "Purani Baatein", "Waqt Ki Kahani"],
                  handles=["TareekhKahani", "PuraniBaatein", "WaqtKiKahani"], tagline="Roz ek nayi kahani",
                  description="Tareekh ki asal kahaniyan... subscribe karein!", keywords=["history in urdu", "tareekh",
                                                                                         'say "hi"', " "],
                  initials="TK")


def test_a_kit_is_written_with_its_images(monkeypatch):
    import short_kit
    monkeypatch.setattr(short_kit, "ask_json", lambda c, schema, prompt, model=None: _kit())
    ch = mc.add("history")
    data = ck.make(ch["id"], client=object())
    assert data["made_for"] == "Tareekh Kahani" and data["keywords"] == ["history in urdu", "tareekh", "say hi"]
    from PIL import Image
    with Image.open(os.path.join(ck.folder(ch["id"]), "banner.png")) as b:
        assert b.size == (2560, 1440)
    with Image.open(os.path.join(ck.folder(ch["id"]), "profile.png")) as p:
        assert p.size == (800, 800)
    assert os.path.getsize(os.path.join(ck.folder(ch["id"]), "banner.png")) < 6 * 1024 * 1024
    assert ck.load(ch["id"])["tagline"] == "Roz ek nayi kahani"


def test_keywords_follow_youtubes_format():
    assert ck.keyword_string(["history in urdu", "tareekh"]) == '"history in urdu" tareekh'
    assert len(ck.keyword_string([f"word{k} long phrase" for k in range(80)])) <= 500


def test_apply_sets_about_text_keywords_and_banner_only(monkeypatch):
    import short_kit
    monkeypatch.setattr(short_kit, "ask_json", lambda c, schema, prompt, model=None: _kit())
    ch = mc.add("history")
    with pytest.raises(ValueError, match="kit first"):
        ck.apply(ch["id"])
    ck.make(ch["id"], client=object())
    monkeypatch.setattr(ya, "status", lambda: {"connected": False})
    with pytest.raises(ValueError, match="Connect"):
        ck.apply(ch["id"])
    monkeypatch.setattr(ya, "status", lambda: {"connected": True})
    monkeypatch.setattr(ya, "_token", lambda: "tok")
    monkeypatch.setattr(ya, "_get", lambda url, params: {"items": [{"id": "UC1", "brandingSettings": {
        "channel": {"title": "Old", "country": "PK", "description": "old"}, "image": {}}}]})
    sent = {}

    def post(url, params=None, content=None, headers=None, timeout=None):
        sent["banner"] = (url, len(content), headers["Content-Type"])
        return types.SimpleNamespace(status_code=200, json=lambda: {"url": "https://yt3.example/banner"})

    def put(url, params=None, json=None, headers=None, timeout=None):
        sent["update"] = (params, json)
        return types.SimpleNamespace(status_code=200, json=lambda: {})
    monkeypatch.setattr(ck.httpx, "post", post)
    monkeypatch.setattr(ck.httpx, "put", put)
    got = ck.apply(ch["id"])
    assert got["set"] == ["banner", "description", "keywords"] and "profile picture" in got["left_for_you"][0]
    assert sent["banner"][0].endswith("/channelBanners/insert") and sent["banner"][2] == "image/png"
    params, body = sent["update"]
    assert params == {"part": "brandingSettings"} and body["id"] == "UC1"
    b = body["brandingSettings"]
    assert b["channel"]["country"] == "PK" and b["channel"]["title"] == "Old"        # the rest is kept
    assert b["channel"]["description"].startswith("Tareekh ki asal") and b["channel"]["keywords"].startswith('"history')
    assert b["image"]["bannerExternalUrl"] == "https://yt3.example/banner"


def test_the_kit_endpoints(monkeypatch):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    import short_kit
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(short_kit, "ask_json", lambda c, schema, prompt, model=None: _kit())
    monkeypatch.setattr(short_kit, "gemini", lambda: object())
    ch = mc.add("quiz")
    client = TestClient(app_module.app)
    assert client.get(f"/api/my-channels/{ch['id']}/kit").json() == {"kit": None}
    r = client.post(f"/api/my-channels/{ch['id']}/kit")
    assert r.status_code == 200, r.text
    kit = r.json()["kit"]
    assert kit["names"][0] == "Tareekh Kahani" and kit["banner"].startswith(f"/api/my-channels/{ch['id']}/kit/banner.png")
    img = client.get(kit["profile"].split("?")[0])
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert client.get(f"/api/my-channels/{ch['id']}/kit/secret.json").status_code == 404
    r = client.post(f"/api/my-channels/{ch['id']}/kit/apply")
    assert r.status_code == 400 and "Connect" in r.json()["detail"]
