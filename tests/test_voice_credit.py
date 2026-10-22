"""The OmniVoice credit on the channel's About text (owner, 22-oct-2026): the whole brandingSettings goes
back with only the description changed, once per narrated channel, never on the songs channel."""
import youtube_account as ya
import my_channels as mc


class _R:
    def __init__(self, code, data):
        self.status_code, self._d = code, data
        self.text = str(data)

    def json(self):
        return self._d


def test_the_line_is_appended_and_every_other_branding_field_goes_back(monkeypatch):
    branding = {"channel": {"title": "T", "description": "Old about.", "keywords": "a b", "country": "PK"},
                "image": {"bannerExternalUrl": "https://x/banner"}}
    monkeypatch.setattr(ya, "_get", lambda url, params: {"items": [{"id": "UC1", "brandingSettings": branding}]})
    monkeypatch.setattr(ya, "_token", lambda: "tok")
    monkeypatch.setattr(ya, "quota_used", lambda: 0)
    monkeypatch.setattr(ya, "spend", lambda units: None)
    sent = []
    monkeypatch.setattr(ya.httpx, "put", lambda url, params, json, headers, timeout: sent.append(json) or _R(200, {}))
    assert ya.add_to_channel_about("Credit line.") is True
    body = sent[0]
    assert body["id"] == "UC1" and body["brandingSettings"]["image"] == branding["image"]
    assert body["brandingSettings"]["channel"] == {"title": "T", "description": "Old about.\n\nCredit line.",
                                                    "keywords": "a b", "country": "PK"}


def test_already_there_or_too_long_changes_nothing(monkeypatch):
    monkeypatch.setattr(ya, "quota_used", lambda: 0)
    monkeypatch.setattr(ya, "httpx", None)      # any write would fail
    monkeypatch.setattr(ya, "_get", lambda url, params: {"items": [{"id": "UC1", "brandingSettings": {
        "channel": {"description": "x Credit line."}}}]})
    assert ya.add_to_channel_about("Credit line.") is False
    monkeypatch.setattr(ya, "_get", lambda url, params: {"items": [{"id": "UC1", "brandingSettings": {
        "channel": {"description": "y" * 990}}}]})
    try:
        ya.add_to_channel_about("Credit line.")
        raise AssertionError("should refuse")
    except RuntimeError as e:
        assert "no room" in str(e)


def test_only_narrated_channels_get_it_and_only_once(monkeypatch):
    added = []
    monkeypatch.setattr(ya, "status", lambda: {"connected": True})
    monkeypatch.setattr(ya, "add_to_channel_about", lambda line, if_empty=None: added.append((line, if_empty)) or True)
    music = mc.add("music")
    assert mc.about_credit(mc.get(music["id"]), log=lambda *a: None) is False
    cricket = mc.add("cricket")
    assert mc.about_credit(mc.get(cricket["id"]), log=lambda *a: None) is True
    assert mc.about_credit(mc.get(cricket["id"]), log=lambda *a: None) is False
    assert added == [(mc.VOICE_CREDIT, mc.ABOUT["cricket"])]


def test_an_empty_about_gets_the_channel_text_before_the_credit(monkeypatch):
    monkeypatch.setattr(ya, "_get", lambda url, params: {"items": [{"id": "UC1", "brandingSettings": {"channel": {}}}]})
    monkeypatch.setattr(ya, "_token", lambda: "tok")
    monkeypatch.setattr(ya, "quota_used", lambda: 0)
    monkeypatch.setattr(ya, "spend", lambda units: None)
    sent = []
    monkeypatch.setattr(ya.httpx, "put", lambda url, params, json, headers, timeout: sent.append(json) or _R(200, {}))
    ya.add_to_channel_about("Credit.", if_empty="About us.")
    assert sent[0]["brandingSettings"]["channel"]["description"] == "About us.\n\nCredit."
    assert all(len(mc.ABOUT[k]) + len(mc.VOICE_CREDIT) + 2 <= ya.CHANNEL_DESCRIPTION_MAX for k in mc.ABOUT)
