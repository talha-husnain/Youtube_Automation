"""A launch kit for each new channel: names, About text, keywords, banner and
profile picture, and one call that puts the text and banner on YouTube.

The owner creates the channels by hand (no API can create one); everything
after that is filled in here. The images are drawn with PIL in the channel's
own colour (free), the copy is one Gemini text call. YouTube's Data API can
set the description, keywords (channels.update, brandingSettings) and the
banner (channelBanners.insert, then the banner URL in brandingSettings), 50
units each; it has no call for the profile picture, so that one is a file
the owner uploads in YouTube Studio (Customization > Branding).

Banner: 2560x1440 (YouTube's recommendation; at least 2048x1152, 16:9, under
6 MB), the text inside the 1546x423 middle that every device shows.
"""
import json
import os
import re
from typing import List

import httpx
from pydantic import BaseModel

import my_channels
import short_kit as kit

ROOT = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(ROOT, "fonts")
BANNER = (2560, 1440)
SAFE = (1546, 423)                 # the part of the banner every device shows
PROFILE = 800
GOLD = (242, 193, 78)


class Kit(BaseModel):
    names: List[str]
    handles: List[str]
    tagline: str
    description: str
    keywords: List[str]
    initials: str


KIT_PROMPT = """You name and describe a new YouTube channel for Pakistani and Indian viewers.
What it posts: {about}
Kind: {label}. Language of the videos: {lang}. Posting: {schedule}.
{notes}
Return:
- names: 3 channel names, short (max 22 characters), catchy, easy to say and to search, not already a famous
  brand, no emoji.
- handles: 3 handle ideas matching the names (letters and digits only, max 20 characters, no @).
- tagline: max 34 characters, in {lang_rule}, what the viewer gets.
- description: the channel's About text, 600-900 characters, in {lang_rule}: what the channel is, what the
  viewer gets, how often new videos come, a line asking to subscribe. Main search words early. Honest: no fake
  promises, no claim the videos are made by a person on camera.
- keywords: 10-14 search keywords people type to find such videos (English and Roman Urdu mixed).
- initials: 1 or 2 letters for the profile picture, from the first name."""

LANG_RULE = {"urdu": "everyday Roman Urdu with common English words (Latin letters only)",
             "english": "simple English"}


def folder(cid):
    return os.path.join(my_channels.folder(cid), "kit")


def _font(name, size):
    from PIL import ImageFont
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def _rgb(hex_color, fallback=(20, 20, 43)):
    try:
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return fallback


def _mix(a, b, share):
    return tuple(round(x * share + y * (1 - share)) for x, y in zip(a, b))


def _fit(draw, text, font_name, max_w, max_h, start):
    size = start
    while size > 20:
        font = _font(font_name, size)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_w and box[3] - box[1] <= max_h:
            return font, box
        size = int(size * 0.92)
    font = _font(font_name, size)
    return font, draw.textbbox((0, 0), text, font=font)


def _backdrop(size, colour):
    """A diagonal gradient from the channel colour to a deep shade of it, with
    a soft glow in the middle."""
    from PIL import Image, ImageDraw, ImageFilter
    w, h = size
    base, deep = _rgb(colour), _mix(_rgb(colour), (0, 0, 0), 0.35)
    img = Image.new("RGB", (w // 8, h // 8))
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            t = (x / img.width + y / img.height) / 2
            px[x, y] = _mix(deep, base, t)
    img = img.resize(size, Image.BICUBIC)
    glow = Image.new("L", size, 0)
    ImageDraw.Draw(glow).ellipse((w * 0.2, h * 0.15, w * 0.8, h * 0.85), fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(min(w, h) // 6))
    light = Image.new("RGB", size, _mix((255, 255, 255), base, 0.35))
    return Image.composite(light, img, glow)


def banner(path, name, tagline, colour, motif, schedule):
    """The 2560x1440 banner: name, tagline and a schedule pill inside the safe middle."""
    from PIL import Image, ImageDraw
    w, h = BANNER
    base = _backdrop(BANNER, colour).convert("RGBA")
    # Everything goes on a clear layer composited at the end: see-through text
    # drawn straight onto the RGB backdrop came out solid white.
    img = Image.new("RGBA", BANNER, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # A huge faint word of what the channel is about, behind everything.
    mfont, mbox = _fit(draw, motif.upper(), "Anton-Regular.ttf", int(w * 0.95), int(h * 0.7), 700)
    draw.text(((w - (mbox[2] - mbox[0])) // 2 - mbox[0], (h - (mbox[3] - mbox[1])) // 2 - mbox[1]),
              motif.upper(), font=mfont, fill=(255, 255, 255, 18))
    sx, sy = (w - SAFE[0]) // 2, (h - SAFE[1]) // 2
    nfont, nbox = _fit(draw, name.upper(), "Anton-Regular.ttf", SAFE[0] - 80, 200, 240)
    nw, nh = nbox[2] - nbox[0], nbox[3] - nbox[1]
    ny = sy + 20
    draw.text(((w - nw) // 2 - nbox[0] + 6, ny - nbox[1] + 8), name.upper(), font=nfont, fill=(0, 0, 0, 110))
    draw.text(((w - nw) // 2 - nbox[0], ny - nbox[1]), name.upper(), font=nfont, fill=(255, 255, 255, 255))
    tfont, tbox = _fit(draw, tagline, "Montserrat-ExtraBold.ttf", SAFE[0] - 200, 70, 64)
    ty = ny + nh + 28
    draw.text(((w - (tbox[2] - tbox[0])) // 2 - tbox[0], ty - tbox[1]), tagline, font=tfont, fill=GOLD + (255,))
    pfont = _font("Montserrat-ExtraBold.ttf", 34)
    pb = draw.textbbox((0, 0), schedule.upper(), font=pfont)
    pw, ph = pb[2] - pb[0] + 70, 64
    px, py = (w - pw) // 2, min(sy + SAFE[1] - ph, ty + (tbox[3] - tbox[1]) + 34)
    draw.rounded_rectangle((px, py, px + pw, py + ph), radius=ph // 2, fill=GOLD + (255,))
    draw.text((px + 35 - pb[0], py + (ph - (pb[3] - pb[1])) // 2 - pb[1]), schedule.upper(), font=pfont,
              fill=(20, 20, 43, 255))
    Image.alpha_composite(base, img).convert("RGB").save(path, "PNG", optimize=True)
    return path


def profile(path, initials, colour):
    """The 800x800 profile picture; YouTube shows it as a circle, so the
    letters and the gold ring stay inside one."""
    from PIL import Image, ImageDraw
    base = _backdrop((PROFILE, PROFILE), colour).convert("RGBA")
    img = Image.new("RGBA", (PROFILE, PROFILE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = 46
    draw.ellipse((pad, pad, PROFILE - pad, PROFILE - pad), outline=GOLD + (255,), width=26)
    text = (initials or "?").upper()[:2]
    font, box = _fit(draw, text, "Anton-Regular.ttf", 470, 400, 420)
    tw, th = box[2] - box[0], box[3] - box[1]
    draw.text(((PROFILE - tw) // 2 - box[0] + 6, (PROFILE - th) // 2 - box[1] + 8), text, font=font,
              fill=(0, 0, 0, 120))
    draw.text(((PROFILE - tw) // 2 - box[0], (PROFILE - th) // 2 - box[1]), text, font=font,
              fill=(255, 255, 255, 255))
    Image.alpha_composite(base, img).convert("RGB").save(path, "PNG", optimize=True)
    return path


SCHEDULE = {"long": {"urdu": "nayi kahani har shaam", "english": "a new story every evening"},
            "shorts": {"urdu": "naye shorts roz", "english": "new shorts every day"}}
MOTIF = {"cricket": "cricket", "quiz": "quiz", "controversy": "story", "music": "music", "history": "history"}


def make(cid, client=None):
    """Write the channel's kit (kit.json, banner.png, profile.png) and return it."""
    ch = my_channels.get(cid)
    if not ch:
        raise ValueError("Unknown channel.")
    k = my_channels.KINDS[ch["kind"]]
    lang = ch.get("lang", "english" if ch["kind"] == "music" else "urdu")
    long_kind = bool(k.get("long"))
    schedule = (f"{ch['per_day']} long videos a day" if long_kind else f"{ch['per_day']} Shorts a day")
    client = client or kit.gemini()
    from quiz_shorts import quiz_model
    got = kit.ask_json(client, Kit, KIT_PROMPT.format(
        about=k["about"], label=k["label"], lang="Urdu (Roman)" if lang == "urdu" else "English",
        schedule=schedule, lang_rule=LANG_RULE.get(lang, LANG_RULE["urdu"]),
        notes=f"The owner's notes: {ch['notes']}" if ch.get("notes") else ""), model=quiz_model())
    out = folder(cid)
    os.makedirs(out, exist_ok=True)
    name = (got.names or [ch["name"]])[0][:30]
    pill = SCHEDULE["long" if long_kind else "shorts"]["english" if lang == "english" else "urdu"]
    banner(os.path.join(out, "banner.png"), name, got.tagline[:40], ch.get("color") or k["color"],
           MOTIF.get(ch["kind"], ch["kind"]), pill)
    profile(os.path.join(out, "profile.png"), got.initials or name[:1], ch.get("color") or k["color"])
    data = {**got.model_dump(), "description": got.description[:1000],
            "keywords": [re.sub(r"[\"<>]", "", w).strip()[:40] for w in got.keywords if w.strip()][:15],
            "made_for": name}
    with open(os.path.join(out, "kit.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


def load(cid):
    try:
        with open(os.path.join(folder(cid), "kit.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def keyword_string(words):
    """YouTube's keyword field: space separated, a phrase in double quotes, 500 characters at most."""
    out = ""
    for w in words:
        part = f'"{w}"' if " " in w else w
        if len(out) + len(part) + 1 > 500:
            break
        out = f"{out} {part}".strip()
    return out


def apply(cid):
    """Put the kit's About text, keywords and banner on the connected channel
    (about 150 quota units). Returns what was set; raises with YouTube's
    reason when a call is refused."""
    import youtube_account as ya
    data = load(cid)
    if not data:
        raise ValueError("Make the channel kit first.")
    with ya.use(my_channels.account(cid)):
        if not ya.status()["connected"]:
            raise ValueError("Connect the YouTube channel first.")
        token = ya._token()
        auth = {"Authorization": f"Bearer {token}"}
        cur = ya._get(f"{ya.API}/channels", {"part": "brandingSettings", "mine": "true"})
        ya.spend(1)
        items = cur.get("items") or []
        if not items:
            raise RuntimeError("YouTube did not return the channel.")
        chan = items[0]
        branding = chan.get("brandingSettings") or {}
        done = []
        banner_path = os.path.join(folder(cid), "banner.png")
        if os.path.isfile(banner_path):
            with open(banner_path, "rb") as f:
                up = httpx.post("https://www.googleapis.com/upload/youtube/v3/channelBanners/insert",
                                params={"uploadType": "media"}, content=f.read(),
                                headers={**auth, "Content-Type": "image/png"}, timeout=120)
            ya.spend(50)
            if up.status_code != 200:
                raise RuntimeError(ya._google_error(up))
            branding.setdefault("image", {})["bannerExternalUrl"] = up.json()["url"]
            done.append("banner")
        settings = branding.setdefault("channel", {})
        settings["description"] = data["description"][:1000]
        settings["keywords"] = keyword_string(data["keywords"])
        r = httpx.put(f"{ya.API}/channels", params={"part": "brandingSettings"},
                      json={"id": chan["id"], "brandingSettings": branding},
                      headers={**auth, "Content-Type": "application/json"}, timeout=60)
        ya.spend(50)
        if r.status_code != 200:
            raise RuntimeError(ya._google_error(r))
        done += ["description", "keywords"]
    return {"set": done, "left_for_you": ["profile picture (YouTube Studio > Customization > Branding)"]}
