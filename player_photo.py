"""Free-licence photos of cricketers for the cricket Shorts.

Google Images results are mostly agency photos (Getty, AFP, the ICC's own),
and one of those in a Short invites a copyright strike. The lead photo of a
player's Wikipedia article is on Wikimedia Commons under a free licence that
allows reuse with credit (CC BY, CC BY-SA, CC0, public domain, India's GODL),
so that is the only source: anything else is refused and the Short is made
without a photo. The credit goes in the description, never on screen
(the owner's rule for credits, 12-oct-2026).

commons.wikimedia.org reset the connection from the owner's laptop
(14-oct-2026), so everything goes through en.wikipedia.org's API, which
serves the Commons file data too. Wikimedia answers 429 to bursts (five
lookups in a row did), so each player is looked up once and cached for
CACHE_DAYS in output/.player_photos.json, and a 429 waits and retries.
"""
import json
import os
import re
import threading
import time

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(ROOT, "output", ".player_photos.json")
CACHE_DAYS = 30
API = "https://en.wikipedia.org/w/api.php"
# Wikimedia's API policy asks for a User-Agent that says who is calling.
UA = "Shortkaar/1.0 (self-hosted Shorts maker; https://github.com/talha-husnain/Youtube_Automation)"
FREE = re.compile(r"^\s*(cc0|cc[ -]by(-sa)?([ -]\d(\.\d)?)?\b|public domain|pd\b|pd-|godl)", re.I)
THUMB_WIDTH = 900
_lock = threading.Lock()


def _read():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CACHE_FILE)


def _api(params, tries=4):
    wait = 3
    for attempt in range(tries):
        try:
            r = httpx.get(API, params={"format": "json", **params}, headers={"User-Agent": UA}, timeout=20)
            if r.status_code == 200 and r.text.strip().startswith("{"):
                return r.json()
        except (httpx.HTTPError, ValueError):
            pass
        if attempt < tries - 1:
            time.sleep(wait)
            wait *= 2
    return None


def _strip(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _page_image(title):
    """(article title, lead image file name, short description) of a page."""
    res = _api({"action": "query", "titles": title, "prop": "pageimages|description",
                "piprop": "name", "redirects": 1})
    pages = ((res or {}).get("query") or {}).get("pages") or {}
    page = next(iter(pages.values()), {}) if pages else {}
    if not page or "missing" in page:
        return None, None, ""
    return page.get("title"), page.get("pageimage"), page.get("description") or ""


# kind "person" (the controversy channel): anyone famous, so the article's
# short description must say what they are, or a namesake gets their photo.
PERSON = re.compile(r"actor|actress|singer|cricketer|footballer|player|athlete|businessman|businesswoman|"
                    r"entrepreneur|youtuber|influencer|presenter|host|model|rapper|musician|director|"
                    r"producer|comedian|journalist|television|film|personality|boxer|wrestler|author|chef",
                    re.I)


# kind "star" (the actress quiz): the photo IS the answer, so only an article
# that says the person acts, models or sings, and only under their own name.
STAR = re.compile(r"actress|actor|model|singer|entertainer|television personality", re.I)


def _fits(desc, kind):
    if kind == "cricket":
        return "cricket" in desc.lower()
    return bool((STAR if kind == "star" else PERSON).search(desc or ""))


def lookup(name, kind="cricket"):
    """{"player", "file", "url", "licence", "artist", "page"} for a cricketer's
    (kind "person": anyone famous's) free photo, or None. Cached (a miss too,
    so a player without one is not asked again every Short)."""
    key = " ".join((name or "").split()).lower()
    if len(key) < 3:
        return None
    if kind != "cricket":
        key = f"{key}|{kind}"
    with _lock:
        hit = _read().get(key)
    if hit and time.time() - hit.get("at", 0) < CACHE_DAYS * 86400:
        return hit.get("photo")
    photo = _lookup(name, kind)
    with _lock:
        data = _read()
        data[key] = {"at": int(time.time()), "photo": photo}
        _write(data)
    return photo


def _lookup(name, kind="cricket"):
    title, file, desc = _page_image(name)
    # The article must be the cricketer, not a namesake ("Shoaib Malik" the
    # politician): its short description says "cricketer".
    if not title or not _fits(desc, kind):
        res = _api({"action": "query", "list": "search", "srlimit": 1,
                    "srsearch": f"{name} cricketer" if kind == "cricket" else f"{name} actress" if kind == "star"
                    else name})
        hits = ((res or {}).get("query") or {}).get("search") or []
        if not hits:
            return None
        title, file, desc = _page_image(hits[0]["title"])
        if not title or not _fits(desc, kind):
            return None
    if not file:
        return None
    res = _api({"action": "query", "titles": f"File:{file}", "prop": "imageinfo",
                "iiprop": "extmetadata|url|size", "iiurlwidth": THUMB_WIDTH})
    pages = ((res or {}).get("query") or {}).get("pages") or {}
    info = ((next(iter(pages.values()), {}) if pages else {}).get("imageinfo") or [{}])[0]
    meta = info.get("extmetadata") or {}
    licence = _strip((meta.get("LicenseShortName") or {}).get("value"))
    nonfree = str((meta.get("NonFree") or {}).get("value") or "").lower() == "true"
    if nonfree or not FREE.match(licence or "") or not info.get("thumburl"):
        return None
    if min(info.get("width") or 0, info.get("height") or 0) < 300:
        return None   # too small to fill a card without looking blurred
    return {"player": title, "file": file, "url": info["thumburl"], "licence": licence,
            "artist": _strip((meta.get("Artist") or {}).get("value"))[:80] or "unknown",
            "page": f"https://commons.wikimedia.org/wiki/File:{file.replace(' ', '_')}"}


MONTHS = {m: k for k, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
# "(born 15 October 1994)" or "(born October 15, 1994)" in the article's first lines.
BORN = re.compile(r"\bborn\s+(?:(\d{1,2})\s+([A-Za-z]+)|([A-Za-z]+)\s+(\d{1,2}),?)\s+(\d{4})")


def born(name, kind="cricket"):
    """(day, month, year) the player's Wikipedia article gives, or None."""
    res = _api({"action": "query", "list": "search", "srlimit": 1,
                "srsearch": f"{name} cricketer" if kind == "cricket" else name})
    hits = ((res or {}).get("query") or {}).get("search") or []
    if not hits:
        return None
    res = _api({"action": "query", "titles": hits[0]["title"], "prop": "extracts", "exintro": 1,
                "explaintext": 1, "redirects": 1})
    pages = ((res or {}).get("query") or {}).get("pages") or {}
    text = (next(iter(pages.values()), {}) if pages else {}).get("extract") or ""
    m = BORN.search(text[:600])
    if not m:
        return None
    day, month = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
    month = MONTHS.get(month.lower())
    return (int(day), month, int(m.group(5))) if month else None


def credit_line(photo):
    return (f"Photo of {photo['player']}: {photo['artist']}, {photo['licence']}, "
            f"via Wikimedia Commons ({photo['page']})")


def fetch(name, out_dir, size=(700, 760), kind="cricket"):
    """{"card", "avatar", "badge", "info"} for a player, or None. The card is
    the photo cover-cropped (face kept: the crop leans to the top), rounded,
    with a gold frame and a soft shadow; avatar (300 px) and badge (150 px)
    are round. All ready for short_kit.render(images=)."""
    photo = lookup(name, kind)
    if not photo:
        return None
    try:
        r = httpx.get(photo["url"], headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
        if r.status_code != 200 or len(r.content) < 5000:
            return None
        slug = re.sub(r"[^a-z0-9]+", "_", photo["player"].lower()).strip("_")[:40] or "player"
        raw = os.path.join(out_dir, f".photo_{slug}")
        with open(raw, "wb") as f:
            f.write(r.content)
        out = {"info": photo}
        card_path = os.path.join(out_dir, f".photo_{slug}_card.png")
        # Cricket only: the stars quiz and the controversy photos are of real women and other public
        # figures, whose photos the owner wants left as they are (no AI edits of real women).
        out["card"] = (kind == "cricket" and cutout_card(raw, card_path, size)) or card(raw, card_path, size)
        out["avatar"] = round_photo(raw, os.path.join(out_dir, f".photo_{slug}_avatar.png"), 300)
        out["badge"] = round_photo(raw, os.path.join(out_dir, f".photo_{slug}_badge.png"), 150, ring=6)
        return out
    except Exception as e:  # noqa: BLE001 — a photo is a bonus, the Short goes on without it
        print(f"   ℹ️ No player photo ({type(e).__name__}).")
        return None


def _cover(src, w, h, lean=0.18):
    from PIL import Image
    im = Image.open(src).convert("RGB")
    scale = max(w / im.width, h / im.height)
    im = im.resize((max(w, round(im.width * scale)), max(h, round(im.height * scale))), Image.LANCZOS)
    x = (im.width - w) // 2
    y = round((im.height - h) * lean)   # faces sit in the upper part of a portrait
    return im.crop((x, y, x + w, y + h))


def round_photo(src, out_path, size, ring=10, gold=(255, 210, 63)):
    """The face in a circle with a gold ring and a soft shadow."""
    from PIL import Image, ImageDraw, ImageFilter
    pad = max(12, size // 10)
    out = Image.new("RGBA", (size + 2 * pad, size + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((pad, pad + size // 25, pad + size, pad + size + size // 25), fill=(0, 0, 0, 150))
    out = Image.alpha_composite(out, shadow.filter(ImageFilter.GaussianBlur(max(4, size // 20))))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out.paste(_cover(src, size, size, 0.12), (pad, pad), mask)
    ImageDraw.Draw(out).ellipse((pad, pad, pad + size - 1, pad + size - 1), outline=gold + (255,), width=ring)
    out.save(out_path)
    return out_path


# Quality pass 2 (22-oct-2026): the person cut out of the photo's background, with a white outline and a
# soft shadow, reads like a sports-channel graphic instead of a framed photo. IS-Net (DIS, Apache-2.0;
# rembg's isnet-general-use.onnx) through onnxruntime on the CPU; never rembg's default model, BRIA
# RMBG, which is non-commercial. Kept only when the mask looks like a person: a sensible share of the
# picture and reaching the bottom edge (a bust); otherwise the framed card as before. CUTOUT=0: never.
CUTOUT_MODEL = os.environ.get("CUTOUT_MODEL") or r"D:\youtube\oss\models\isnet\isnet-general-use.onnx"
_cut_session = []


def cutout_available():
    return os.environ.get("CUTOUT", "1").strip() != "0" and os.path.isfile(CUTOUT_MODEL)


def person_mask(src):
    """0..255 mask (PIL "L", the photo's size) of the main subject."""
    import numpy as np
    from PIL import Image
    if not _cut_session:
        import onnxruntime as ort
        _cut_session.append(ort.InferenceSession(CUTOUT_MODEL, providers=["CPUExecutionProvider"]))
    sess = _cut_session[0]
    im = Image.open(src).convert("RGB")
    x = np.asarray(im.resize((1024, 1024), Image.LANCZOS), dtype=np.float32)
    x = x / max(float(x.max()), 1e-6) - np.array([0.485, 0.456, 0.406], dtype=np.float32)
    pred = sess.run(None, {sess.get_inputs()[0].name: x.transpose(2, 0, 1)[None].astype(np.float32)})[0][0, 0]
    pred = (pred - pred.min()) / max(float(pred.max() - pred.min()), 1e-6)
    return Image.fromarray((pred * 255).astype(np.uint8)).resize(im.size, Image.LANCZOS)


def cutout_card(src, out_path, size=(700, 760), outline=10):
    """The person on transparency at the card's size and padding, or None when the cut looks wrong."""
    import numpy as np
    from PIL import Image, ImageFilter
    if not cutout_available():
        return None
    try:
        w, h = size
        mask = person_mask(src)
        m = np.asarray(mask, dtype=np.float32) / 255
        share = float((m > 0.5).mean())
        bottom = float((m[-max(2, m.shape[0] // 40):] > 0.5).mean())
        if not (0.08 <= share <= 0.75 and bottom >= 0.12):
            return None
        photo = Image.open(src).convert("RGB")
        rgba = photo.copy()
        rgba.putalpha(mask)
        im = _cover_rgba(rgba, w, h)
        pad = 40
        out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        alpha = im.getchannel("A")
        # Outline: the alpha grown by ``outline`` px, white; shadow: the grown alpha blurred, offset down.
        grown = alpha.filter(ImageFilter.MaxFilter(outline * 2 + 1))
        shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
        shadow.paste((0, 0, 0, 170), (pad, pad + 16), grown)
        out = Image.alpha_composite(out, shadow.filter(ImageFilter.GaussianBlur(14)))
        ring = Image.new("RGBA", out.size, (0, 0, 0, 0))
        ring.paste((255, 255, 255, 255), (pad, pad), grown)
        out = Image.alpha_composite(out, ring)
        layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
        layer.paste(im, (pad, pad), im)
        out = Image.alpha_composite(out, layer)
        if not _clean_cut(out):
            return None
        out.save(out_path)
        return out_path
    except Exception as e:  # noqa: BLE001 — the framed card is the fallback
        print(f"   ℹ️ No cut-out ({type(e).__name__}); framed card instead.")
        return None


CLEAN_PROMPT = ("This is a cut-out sticker of a person on a plain green background. Answer true only if it shows "
                "exactly one person, cleanly cut out, with no leftover part of another person (a second head, a "
                "shoulder, a blurred figure behind) and no stray chunk of background.")


def _clean_cut(rgba):
    """One yes/no vision call on the finished cut-out: on Babar Azam's Wikipedia photo the mask kept a
    blurred man standing behind him, one shape with Babar that no mask rule or YOLO separated
    (22-oct-2026). Any doubt or failure: False, and the framed card is used."""
    try:
        import io
        from google.genai import types
        from PIL import Image
        from pydantic import BaseModel

        import short_kit as kit

        class Clean(BaseModel):
            clean: bool

        bg = Image.new("RGBA", rgba.size, (40, 120, 70, 255))
        im = Image.alpha_composite(bg, rgba).convert("RGB")
        im.thumbnail((512, 512))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
        return bool(kit.ask_json(kit.gemini(), Clean, [part, CLEAN_PROMPT]).clean)
    except Exception:  # noqa: BLE001
        return False


def _cover_rgba(img, w, h, lean=0.18):
    from PIL import Image
    s = max(w / img.width, h / img.height)
    img = img.resize((max(w, round(img.width * s)), max(h, round(img.height * s))), Image.LANCZOS)
    x, y = (img.width - w) // 2, round((img.height - h) * lean)
    return img.crop((x, y, x + w, y + h))


def card(src, out_path, size=(700, 760), radius=44, border=10, gold=(255, 210, 63)):
    from PIL import Image, ImageDraw, ImageFilter
    w, h = size
    im = _cover(src, w, h)
    pad = 40
    out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad, pad + 14, pad + w, pad + h + 14), radius, fill=(0, 0, 0, 150))
    out = Image.alpha_composite(out, shadow.filter(ImageFilter.GaussianBlur(16)))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    out.paste(im, (pad, pad), mask)
    ImageDraw.Draw(out).rounded_rectangle((pad, pad, pad + w - 1, pad + h - 1), radius,
                                          outline=gold + (255,), width=border)
    out.save(out_path)
    return out_path
