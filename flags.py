"""Country flags for the flag quiz (quiz_shorts, format ``flags``).

The picture is the flag itself, from the "Flag of <country>" article on
Wikipedia (its lead image, nearly always public domain on Commons; the
licence is checked like player photos). Flags do not change, so each is
fetched once into output/flags/ and reused.
"""
import os
import random
import re

import httpx

import player_photo

ROOT = os.path.dirname(os.path.abspath(__file__))
FLAGS_DIR = os.path.join(ROOT, "output", "flags")
REGIONS = {
    "asia": ["Pakistan", "India", "Bangladesh", "Sri Lanka", "Nepal", "Afghanistan", "China", "Japan",
             "South Korea", "Indonesia", "Malaysia", "Thailand", "Vietnam", "Philippines", "Singapore", "Bhutan",
             "Maldives", "Myanmar", "Kazakhstan", "Uzbekistan", "Mongolia"],
    "middle east": ["Iran", "Iraq", "Saudi Arabia", "United Arab Emirates", "Qatar", "Turkey", "Kuwait", "Oman",
                    "Jordan", "Bahrain", "Lebanon", "Syria"],
    "europe": ["United Kingdom", "France", "Germany", "Italy", "Spain", "Portugal", "Netherlands", "Belgium",
               "Switzerland", "Sweden", "Norway", "Denmark", "Finland", "Ireland", "Poland", "Greece", "Austria",
               "Russia", "Ukraine", "Romania", "Czech Republic", "Hungary"],
    "americas": ["United States", "Canada", "Mexico", "Brazil", "Argentina", "Chile", "Colombia", "Peru", "Cuba",
                 "Jamaica", "Venezuela", "Uruguay"],
    "africa": ["Egypt", "Nigeria", "South Africa", "Kenya", "Ethiopia", "Morocco", "Algeria", "Ghana", "Zimbabwe",
               "Tanzania", "Senegal", "Cameroon"],
    "oceania": ["Australia", "New Zealand", "Fiji", "Papua New Guinea"],
}
REGION_OF = {c: r for r, cs in REGIONS.items() for c in cs}


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def fetch(country):
    """Path of the country's flag PNG (cached), or None."""
    path = os.path.join(FLAGS_DIR, f"{_slug(country)}.png")
    if os.path.isfile(path) and os.path.getsize(path) > 500:
        return path
    res = player_photo._api({"action": "query", "titles": f"Flag of {country}", "prop": "pageimages",
                             "piprop": "name", "redirects": 1})
    page = next(iter(((res or {}).get("query") or {}).get("pages", {}).values()), {})
    file = page.get("pageimage")
    if not file:
        return None
    res = player_photo._api({"action": "query", "titles": f"File:{file}", "prop": "imageinfo",
                             "iiprop": "extmetadata|url", "iiurlwidth": 900})
    info = (next(iter(((res or {}).get("query") or {}).get("pages", {}).values()), {}).get("imageinfo") or [{}])[0]
    licence = player_photo._strip(((info.get("extmetadata") or {}).get("LicenseShortName") or {}).get("value"))
    if not info.get("thumburl") or not player_photo.FREE.match(licence or ""):
        return None
    r = httpx.get(info["thumburl"], headers={"User-Agent": player_photo.UA}, timeout=30, follow_redirects=True)
    if r.status_code != 200 or len(r.content) < 500:
        return None
    os.makedirs(FLAGS_DIR, exist_ok=True)
    with open(path, "wb") as f:
        f.write(r.content)
    return path


def card(src, out_path, box=(760, 440), border=14, radius=26):
    """The flag fitted inside ``box`` on a white rounded card with a shadow."""
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.open(src).convert("RGBA")
    scale = min(box[0] / im.width, box[1] / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    w, h = im.width + 2 * border, im.height + 2 * border
    pad = 36
    out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad, pad + 12, pad + w, pad + h + 12), radius, fill=(0, 0, 0, 160))
    out = Image.alpha_composite(out, shadow.filter(ImageFilter.GaussianBlur(14)))
    ImageDraw.Draw(out).rounded_rectangle((pad, pad, pad + w - 1, pad + h - 1), radius, fill=(255, 255, 255, 255))
    out.alpha_composite(im, (pad + border, pad + border))
    out.save(out_path)
    return out_path


def pick(count, avoid=(), rnd=random):
    """``count`` (country, [4 options], answer index): the wrong options come
    from the same region, so the flags look alike enough to make people think."""
    avoid = {a.lower() for a in avoid}
    pool = [c for c in REGION_OF if c.lower() not in avoid] or list(REGION_OF)
    rnd.shuffle(pool)
    out = []
    for country in pool[:count]:
        same = [c for c in REGIONS[REGION_OF[country]] if c != country]
        wrong = rnd.sample(same, 3) if len(same) >= 3 else rnd.sample([c for c in REGION_OF if c != country], 3)
        options = wrong + [country]
        rnd.shuffle(options)
        out.append((country, options, options.index(country)))
    return out
