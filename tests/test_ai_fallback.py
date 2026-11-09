"""Gemini, then OpenAI, then Ollama (owner, 7-nov-2026). Nothing here reaches the network: Gemini is a fake and
OpenAI / Ollama answer through a fake httpx."""
import base64
import io
import json
import types as pytypes

import pytest
from pydantic import BaseModel

import ai_fallback as af

BROKE = RuntimeError("402 RESOURCE_EXHAUSTED. {'error': {'code': 402, 'message': 'Your prepayment credits are "
                     "depleted. Please go to AI Studio.'}}")


class Idea(BaseModel):
    title: str
    score: int


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(af, "STATE_FILE", str(tmp_path / "ai_fallback.json"))
    monkeypatch.setattr(af, "_said", set())
    monkeypatch.setenv("AI_FALLBACK_TEST", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("AI_FALLBACK", raising=False)
    return tmp_path


class FakeGemini:
    def __init__(self, error=None):
        self.error, self.calls = error, 0
        self.models = self
        self.files = "gemini files"

    def generate_content(self, model=None, contents=None, config=None):
        self.calls += 1
        if self.error:
            raise self.error
        return pytypes.SimpleNamespace(text="from gemini", parsed=None)


class _R:
    def __init__(self, data, code=200):
        self.status_code, self._d = code, data
        self.text = json.dumps(data)

    def json(self):
        return self._d


def _png(w=1024, h=1536):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


class FakeNet:
    def __init__(self, openai_ok=True, ollama=False):
        self.posts, self.openai_ok, self.ollama = [], openai_ok, ollama

    def post(self, url, json=None, headers=None, timeout=None, files=None, data=None):
        self.posts.append((url, json, files, data))
        if "openai.com" in url and not self.openai_ok:
            return _R({"error": {"message": "insufficient_quota"}}, 429)
        if url.endswith("/responses"):
            return _R({"status": "completed", "output": [{"type": "reasoning"}, {"type": "message", "content": [
                {"type": "output_text", "text": '```json\n{"title": "Billo ki biryani", "score": 9}\n```'}]}]})
        if "/images/" in url:
            return _R({"data": [{"b64_json": base64.b64encode(_png()).decode()}]})
        if url.endswith("/api/chat"):
            assert json["options"]["num_ctx"] >= 16384 and json["format"]["type"] == "object"
            return _R({"message": {"content": '{"title": "local", "score": 3}'}})
        return _R({}, 404)

    def get(self, url, timeout=None, headers=None):
        return _R({"models": []}, 200 if self.ollama else 500)


def _cfg(**kw):
    from google.genai import types
    return types.GenerateContentConfig(**kw)


def test_gemini_answers_when_it_can(monkeypatch):
    net = FakeNet()
    monkeypatch.setattr(af, "httpx", net)
    c = af.wrap(FakeGemini())
    assert c.models.generate_content(model="m", contents="hi").text == "from gemini"
    assert c.files == "gemini files" and not net.posts


def test_out_of_credit_goes_to_openai_and_gemini_rests(monkeypatch):
    net = FakeNet()
    monkeypatch.setattr(af, "httpx", net)
    g = FakeGemini(BROKE)
    c = af.wrap(g)
    import short_kit
    got = short_kit.ask_json(c, Idea, "An idea for the cartoon channel")
    assert got == Idea(title="Billo ki biryani", score=9)
    url, body, _f, _d = net.posts[0]
    assert url.endswith("/responses") and body["model"] == "gpt-5-mini" and body["text"]["format"]["type"] == "json_object"
    assert "JSON Schema" in json.dumps(body["input"]) and af.status()["gemini_down"]
    short_kit.ask_json(c, Idea, "another")                      # Gemini is not asked again while it rests
    assert g.calls == 1 and af.status()["last_backup"]["provider"] == "openai"


def test_other_gemini_errors_are_not_hidden(monkeypatch):
    monkeypatch.setattr(af, "httpx", FakeNet())
    c = af.wrap(FakeGemini(ValueError("400 INVALID_ARGUMENT")))
    with pytest.raises(ValueError):
        c.models.generate_content(model="m", contents="x")


def test_pictures_go_to_openai_images_cropped_and_capped(monkeypatch):
    net = FakeNet()
    monkeypatch.setattr(af, "httpx", net)
    monkeypatch.setenv("OPENAI_IMAGES_PER_DAY", "1")
    from google.genai import types
    from PIL import Image
    c = af.wrap(FakeGemini(BROKE))
    ref = types.Part.from_bytes(data=_png(64, 64), mime_type="image/png")
    cfg = _cfg(response_modalities=["TEXT", "IMAGE"], image_config=types.ImageConfig(aspect_ratio="9:16"))
    with pytest.raises(RuntimeError, match="prepayment"):         # not the cartoon channel: no paid picture
        c.models.generate_content(model="img", contents=["a history painting"], config=cfg)
    assert not net.posts
    with af.allow_images():
        r = c.models.generate_content(model="img", contents=[ref, "Billo the cat waves"], config=cfg)
    img = Image.open(io.BytesIO(r.parts[0].inline_data.data))
    assert abs(img.size[0] / img.size[1] - 9 / 16) < 0.01
    url, _b, files, data = net.posts[0]
    assert url.endswith("/images/edits") and len(files) == 1 and data["size"] == "1024x1536"
    assert data["model"] == "gpt-image-1-mini"
    with pytest.raises(RuntimeError, match="OPENAI_IMAGES_PER_DAY"), af.allow_images():
        c.models.generate_content(model="img", contents=["again"], config=cfg)


def test_ollama_after_openai_and_video_stays_with_gemini(monkeypatch):
    net = FakeNet(openai_ok=False, ollama=True)
    monkeypatch.setattr(af, "httpx", net)
    c = af.wrap(FakeGemini(BROKE))
    r = c.models.generate_content(model="m", contents="plan", config=_cfg(response_schema=Idea,
                                                                          response_mime_type="application/json"))
    assert json.loads(r.text)["title"] == "local" and af.status()["last_backup"]["provider"] == "ollama"
    from google.genai import types
    video = types.Part(file_data=types.FileData(file_uri="https://x/v.mp4", mime_type="video/mp4"))
    with pytest.raises(RuntimeError, match="prepayment"):
        c.models.generate_content(model="m", contents=[video, "watch"])


def test_no_backup_left_keeps_gemini_reason(monkeypatch):
    monkeypatch.setattr(af, "httpx", FakeNet(openai_ok=False, ollama=False))
    c = af.wrap(FakeGemini(BROKE))
    with pytest.raises(RuntimeError) as e:
        c.models.generate_content(model="m", contents="x")
    assert "prepayment" in str(e.value) and "OpenAI" in str(e.value) and "sk-test" not in str(e.value)


def test_tests_never_wrap_without_opting_in(monkeypatch):
    monkeypatch.delenv("AI_FALLBACK_TEST")
    g = FakeGemini()
    assert af.wrap(g) is g
