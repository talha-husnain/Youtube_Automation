"""Gemini first, then OpenAI, then a free local Ollama (owner, 7-nov-2026: "first gemini then openai then
ollama free").

On 6-nov-2026 the Gemini account's prepaid credits ran out (402 RESOURCE_EXHAUSTED, "Your prepayment credits
are depleted") and every channel stopped: no ideas, no scripts, no cartoon pictures. ``wrap(genai_client)``
returns a drop-in client whose ``models.generate_content`` asks Gemini as before and, only when Gemini says it is
out of credit or out of quota, asks OpenAI instead (and Ollama after that, text only). Every other attribute
(``files``, ``interactions`` for the songs, ...) is Gemini's own, untouched.

What the backups can do:
- text and JSON answers (ask_json, plans, scripts, titles): OpenAI's Responses API, pictures in the prompt
  included, Google Search grounding becomes OpenAI's web_search; Ollama's /v1/chat/completions, text only.
- pictures (response_modalities IMAGE, the cartoons and thumbnails): OpenAI's image API, reference pictures
  through /images/edits, cropped to the asked aspect. At most OPENAI_IMAGES_PER_DAY a day (they cost money).
- a video or audio file in the prompt, songs (Lyria): Gemini only; the original Gemini error is raised.

Gemini is asked again every GEMINI_RECHECK seconds (one call), so a top-up takes over by itself. The state
(Gemini down until, pictures made today, the last backup used) is in state/ai_fallback.json, shared by the
server and its job processes. Keys never appear in a log line or an error.
"""
import base64
import contextlib
import contextvars
import io
import json
import os
import threading
import time

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "state", "ai_fallback.json")
OPENAI = "https://api.openai.com/v1"
_lock = threading.Lock()
_said = set()


def openai_model():
    if _best_writer.get():
        return (os.environ.get("OPENAI_WRITER_MODEL") or "gpt-5").strip()
    return (os.environ.get("OPENAI_MODEL") or "gpt-5-mini").strip()


# The cartoon's story is written by the full model (owner, 9-nov-2026: "the overall script of those videos is super
# bad ... there should be a proper storyline"): text costs cents next to the episode's video.
_best_writer = contextvars.ContextVar("ai_fallback_best_writer", default=False)


@contextlib.contextmanager
def best_writer():
    token = _best_writer.set(True)
    try:
        yield
    finally:
        _best_writer.reset(token)


def openai_image_model():
    # The mini model: about a quarter of gpt-image-1.5's price a picture (owner, 7-nov-2026: "keep cost minimum").
    return (os.environ.get("OPENAI_IMAGE_MODEL") or "gpt-image-1-mini").strip()


# OpenAI pictures cost money, so only the cartoon channel may ask the backup to draw (owner, 7-nov-2026: "use
# mainly for cartoon generation only"). Other channels' pictures keep Gemini's error and their own fallbacks
# (archive paintings, stock footage, no cover). OPENAI_IMAGES_ALL=1 lets every channel draw.
_images_ok = contextvars.ContextVar("ai_fallback_images_ok", default=False)


@contextlib.contextmanager
def allow_images():
    token = _images_ok.set(True)
    try:
        yield
    finally:
        _images_ok.reset(token)


def images_allowed():
    return _images_ok.get() or os.environ.get("OPENAI_IMAGES_ALL", "").strip() == "1"


def ollama_url():
    return (os.environ.get("OLLAMA_URL") or "http://127.0.0.1:11434").strip().rstrip("/")


def ollama_model():
    return (os.environ.get("OLLAMA_MODEL") or "qwen2.5:7b").strip()


def _int_env(name, default):
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


def openai_key():
    return (os.environ.get("OPENAI_API_KEY") or "").strip().strip('"').strip("'")


# ------------------------------------------------------------------ state

def _read():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write(d):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = f"{STATE_FILE}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, STATE_FILE)


def _update(fn):
    with _lock:
        d = _read()
        fn(d)
        _write(d)
        return d


def status():
    d = _read()
    now = time.time()
    return {"gemini_down": d.get("gemini_down_until", 0) > now, "gemini_down_until": d.get("gemini_down_until", 0),
            "reason": d.get("reason", ""), "last_backup": d.get("last_backup"),
            "images_today": (d.get("images") or {}).get(time.strftime("%Y-%m-%d"), 0),
            "openai": bool(openai_key())}


def _say(key, text):
    if key not in _said:
        _said.add(key)
        print(text)


# ------------------------------------------------------------------ when to switch

def out_of_credit(e):
    msg = str(e)
    return "credits are depleted" in msg or "'code': 402" in msg or '"code": 402' in msg


def switchable(e):
    """Gemini's answers that a backup can help with: no credit, or quota/rate used up."""
    msg = f"{type(e).__name__} {e}"
    return out_of_credit(e) or "429" in msg or "RESOURCE_EXHAUSTED" in msg


def _gemini_down():
    return _read().get("gemini_down_until", 0) > time.time()


def _mark_down(e):
    secs = _int_env("GEMINI_RECHECK", 1800) if out_of_credit(e) else 600
    why = "out of prepaid credit" if out_of_credit(e) else "quota used up"
    _update(lambda d: d.update(gemini_down_until=int(time.time()) + secs, reason=why))
    _say("down", f"   ⚠️ Gemini is {why}; asking the backup AI instead (Gemini is tried again in {secs // 60} min).")


def _used(name):
    _update(lambda d: d.update(last_backup={"provider": name, "at": int(time.time())}))


class Unsupported(RuntimeError):
    """The request needs Gemini (a video or audio file, or an unknown part)."""


# ------------------------------------------------------------------ reading a Gemini request

def _get(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _image_bytes(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def _parts(contents):
    """Gemini ``contents`` as [("text", str) | ("image", bytes, mime)]; Unsupported for video/audio/files."""
    out = []

    def add(x):
        if x is None:
            return
        if isinstance(x, str):
            out.append(("text", x))
            return
        if isinstance(x, (list, tuple)):
            for y in x:
                add(y)
            return
        if hasattr(x, "save") and hasattr(x, "convert"):          # a PIL picture
            out.append(("image", _image_bytes(x), "image/png"))
            return
        parts = _get(x, "parts")
        if parts is not None and not _get(x, "inline_data") and not _get(x, "text"):   # a Content
            add(list(parts))
            return
        text = _get(x, "text")
        if text:
            out.append(("text", text))
            return
        blob = _get(x, "inline_data")
        if blob is not None and _get(blob, "data"):
            mime = _get(blob, "mime_type") or "image/png"
            if not mime.startswith("image/"):
                raise Unsupported(f"a {mime} part needs Gemini")
            out.append(("image", _get(blob, "data"), mime))
            return
        raise Unsupported(f"a {type(x).__name__} part needs Gemini")

    add(contents)
    return out


def _schema_json(s):
    if s is None:
        return None
    try:
        from pydantic import BaseModel, TypeAdapter
        if isinstance(s, dict):
            return s
        if isinstance(s, type) and issubclass(s, BaseModel):
            return s.model_json_schema()
        if hasattr(s, "model_dump"):                               # a google.genai types.Schema
            return s.model_dump(exclude_none=True, mode="json")
        return TypeAdapter(s).json_schema()
    except Exception:  # noqa: BLE001 — the prompt then just asks for JSON
        return {}


def _wants_search(tools):
    for t in tools or []:
        if _get(t, "google_search") is not None or _get(t, "google_search_retrieval") is not None:
            return True
    return False


def _system_text(cfg):
    si = _get(cfg, "system_instruction")
    if not si:
        return ""
    try:
        return "\n".join(p[1] for p in _parts(si) if p[0] == "text")
    except Unsupported:
        return ""


def _json_text(text):
    """The first JSON value in a model's answer, re-dumped (code fences and chatter dropped)."""
    text = (text or "").strip()
    dec = json.JSONDecoder()
    for k, ch in enumerate(text):
        if ch in "{[":
            try:
                val, _end = dec.raw_decode(text[k:])
                return json.dumps(val, ensure_ascii=False)
            except ValueError:
                continue
    return text


# ------------------------------------------------------------------ the answer, shaped like Gemini's

class Response:
    def __init__(self, text=None, image=None, provider=""):
        self.text = text
        self.parsed = None
        self.candidates = []
        self.prompt_feedback = None
        self.usage_metadata = None
        self.provider = provider
        self.parts = []
        if image is not None:
            from google.genai import types
            self.parts = [types.Part.from_bytes(data=image, mime_type="image/png")]


# ------------------------------------------------------------------ OpenAI

def _openai_text(parts, cfg, json_schema, search):
    key = openai_key()
    if not key:
        raise RuntimeError("no OPENAI_API_KEY")
    model = openai_model()
    content = []
    for p in parts:
        if p[0] == "text":
            content.append({"type": "input_text", "text": p[1]})
        else:
            content.append({"type": "input_image",
                            "image_url": f"data:{p[2]};base64,{base64.b64encode(p[1]).decode()}"})
    want_json = json_schema is not None
    top_object = want_json and (json_schema or {}).get("type", "object") == "object"
    if want_json:
        content.append({"type": "input_text", "text": "\n\nAnswer with JSON only (no code fences, no prose)"
                        + (f" that follows this JSON Schema:\n{json.dumps(json_schema)}" if json_schema else ".")})
    body = {"model": model, "input": [{"role": "user", "content": content}], "store": False}
    system = _system_text(cfg)
    if system:
        body["instructions"] = system
    if search:
        body["tools"] = [{"type": "web_search"}]
    elif top_object:
        body["text"] = {"format": {"type": "json_object"}}
    if model.startswith(("gpt-5", "o")):
        # "low" misread a channel's script gate on 7-nov-2026 (a fine horror premise came back allowed=false with
        # the instructions pasted as the reason); "medium" costs a fraction of a cent more a call.
        body["reasoning"] = {"effort": os.environ.get("OPENAI_REASONING") or "medium"}
    cap = _get(cfg, "max_output_tokens")
    if cap:
        body["max_output_tokens"] = int(cap) + 8000             # room for the model's reasoning
    r = httpx.post(f"{OPENAI}/responses", json=body, timeout=_int_env("OPENAI_TIMEOUT", 600),
                   headers={"Authorization": f"Bearer {key}"})
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    data = r.json()
    text = ""
    for item in data.get("output") or []:
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if c.get("type") == "output_text":
                    text += c.get("text") or ""
    if not text.strip():
        raise RuntimeError(f"OpenAI gave no text ({data.get('status')})")
    return _json_text(text) if want_json else text


SIZES = {"portrait": "1024x1536", "landscape": "1536x1024", "square": "1024x1024"}


def _aspect(cfg):
    ar = str(_get(_get(cfg, "image_config"), "aspect_ratio") or "1:1")
    try:
        w, h = (float(x) for x in ar.split(":"))
    except ValueError:
        w, h = 1.0, 1.0
    return w / h


def _crop(png, ratio):
    from PIL import Image
    img = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = img.size
    if abs(w / h - ratio) > 0.01:
        if w / h > ratio:
            nw = round(h * ratio)
            img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = round(w / ratio)
            img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return _image_bytes(img)


def _openai_image(parts, cfg):
    key = openai_key()
    if not key:
        raise RuntimeError("no OPENAI_API_KEY")
    cap = _int_env("OPENAI_IMAGES_PER_DAY", 80)
    day = time.strftime("%Y-%m-%d")
    if (_read().get("images") or {}).get(day, 0) >= cap:
        raise RuntimeError(f"the backup's {cap} pictures for today are made (OPENAI_IMAGES_PER_DAY)")
    ratio = _aspect(cfg)
    size = SIZES["portrait" if ratio < 0.9 else "landscape" if ratio > 1.1 else "square"]
    prompt = "\n".join(p[1] for p in parts if p[0] == "text")[:30000]
    refs = [p for p in parts if p[0] == "image"][:16]
    model = openai_image_model()
    quality = os.environ.get("OPENAI_IMAGE_QUALITY") or "medium"
    auth = {"Authorization": f"Bearer {key}"}
    timeout = _int_env("OPENAI_TIMEOUT", 600)
    if refs:
        files = [("image[]", (f"ref{k}.png", data, mime)) for k, (_t, data, mime) in enumerate(refs)]
        r = httpx.post(f"{OPENAI}/images/edits", headers=auth, timeout=timeout, files=files,
                       data={"model": model, "prompt": prompt, "size": size, "quality": quality, "n": "1"})
    else:
        r = httpx.post(f"{OPENAI}/images/generations", headers=auth, timeout=timeout,
                       json={"model": model, "prompt": prompt, "size": size, "quality": quality, "n": 1})
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI images {r.status_code}: {r.text[:300]}")
    b64 = ((r.json().get("data") or [{}])[0]).get("b64_json")
    if not b64:
        raise RuntimeError("OpenAI gave no picture")

    def count(d):
        imgs = {k: v for k, v in (d.get("images") or {}).items() if k == day}
        imgs[day] = imgs.get(day, 0) + 1
        d["images"] = imgs
    _update(count)
    return _crop(base64.b64decode(b64), ratio)


# ------------------------------------------------------------------ Ollama (free, local, text only)

def ollama_up():
    try:
        return httpx.get(f"{ollama_url()}/api/tags", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


def _ollama_text(parts, cfg, json_schema):
    if any(p[0] != "text" for p in parts):
        raise Unsupported("pictures need Gemini or OpenAI")
    if not ollama_up():
        raise RuntimeError("Ollama is not running")
    prompt = "\n".join(p[1] for p in parts)
    if json_schema is not None:
        prompt += ("\n\nAnswer with JSON only" + (f" that follows this JSON Schema:\n{json.dumps(json_schema)}"
                                                  if json_schema else "."))
    msgs = ([{"role": "system", "content": _system_text(cfg)}] if _system_text(cfg) else []) + \
        [{"role": "user", "content": prompt}]
    # Ollama's own /api/chat: num_ctx per request (its 4096 default cuts our long prompts) without a Windows
    # setting; "format" takes the JSON Schema itself.
    body = {"model": ollama_model(), "messages": msgs, "stream": False,
            "options": {"temperature": 0.4, "num_ctx": _int_env("OLLAMA_NUM_CTX", 16384)}}
    if json_schema is not None:
        body["format"] = json_schema if (json_schema or {}).get("type") else "json"
    r = httpx.post(f"{ollama_url()}/api/chat", json=body, timeout=_int_env("LLM_TIMEOUT", 900))
    if r.status_code != 200:
        raise RuntimeError(f"Ollama {r.status_code}: {r.text[:200]}")
    text = (r.json().get("message") or {}).get("content") or ""
    if not text.strip():
        raise RuntimeError("Ollama gave no text")
    return _json_text(text) if json_schema is not None else text


# ------------------------------------------------------------------ the backups in order

def backup(contents, config=None):
    """OpenAI, then Ollama, for one Gemini request. Raises Unsupported or the last backup's error."""
    parts = _parts(contents)
    modalities = [str(m).upper() for m in (_get(config, "response_modalities") or [])]
    if any("IMAGE" in m for m in modalities):
        if not images_allowed():
            raise Unsupported("backup pictures are for the cartoon channel only")
        img = _openai_image(parts, config)
        _used("openai-image")
        return Response(image=img, provider="openai")
    schema = _get(config, "response_schema")
    js = _schema_json(schema) if schema is not None else (
        {} if str(_get(config, "response_mime_type") or "").endswith("json") else None)
    errors = []
    if openai_key():
        try:
            text = _openai_text(parts, config, js, _wants_search(_get(config, "tools")))
            _used("openai")
            return Response(text=text, provider="openai")
        except Exception as e:  # noqa: BLE001 — Ollama next
            errors.append(f"OpenAI: {str(e)[:200]}")
            _say("openai-failed:" + str(e)[:40], f"   ⚠️ The OpenAI backup failed ({str(e)[:120]}); trying Ollama.")
    try:
        text = _ollama_text(parts, config, js)
        _used("ollama")
        return Response(text=text, provider="ollama")
    except Exception as e:  # noqa: BLE001
        errors.append(f"Ollama: {str(e)[:200]}")
    raise RuntimeError("; ".join(errors))


class _Models:
    def __init__(self, gemini_models):
        self._g = gemini_models

    def __getattr__(self, name):
        return getattr(self._g, name)

    def generate_content(self, *args, **kw):
        model = kw.pop("model", None) if "model" in kw else (args[0] if args else None)
        contents = kw.pop("contents", None) if "contents" in kw else (args[1] if len(args) > 1 else None)
        config = kw.pop("config", None) if "config" in kw else (args[2] if len(args) > 2 else None)
        gemini_error = None
        if self._g is not None and not _gemini_down():
            try:
                return self._g.generate_content(model=model, contents=contents, config=config, **kw)
            except Exception as e:  # noqa: BLE001
                if not switchable(e):
                    raise
                _mark_down(e)
                gemini_error = e
        try:
            return backup(contents, config)
        except Unsupported:
            if gemini_error is not None:
                raise gemini_error
            if self._g is None:
                raise
            # Gemini was marked down by another call: this request can only go to Gemini, so ask it anyway.
            return self._g.generate_content(model=model, contents=contents, config=config, **kw)
        except Exception as e:  # noqa: BLE001
            if gemini_error is not None:
                raise RuntimeError(f"{gemini_error} | backups: {e}") from gemini_error
            raise


class Client:
    """``genai.Client`` with the backups behind ``models.generate_content``."""

    def __init__(self, gemini_client):
        self._g = gemini_client
        self.models = _Models(getattr(gemini_client, "models", None))

    def __getattr__(self, name):
        if self._g is None:
            raise AttributeError(name)
        return getattr(self._g, name)


def wrap(gemini_client):
    if os.environ.get("AI_FALLBACK", "1").strip() == "0" or isinstance(gemini_client, Client):
        return gemini_client
    # Never a real OpenAI call from a test whose fake Gemini says 429 (this module's own tests opt in).
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("AI_FALLBACK_TEST"):
        return gemini_client
    return Client(gemini_client)
