"""Hindi and Urdu-script titles and descriptions on every upload (owner, 22-oct-2026: more views).

Our titles are Roman Urdu. Indian viewers whose YouTube is in Hindi search and read in Devanagari,
Pakistani viewers on an Urdu UI in Nastaliq. YouTube shows a translated title and description to
viewers in that language and lets them find the video by searching in it (YouTube Help answer/6289575
and answer/6300772; a discovery chance, not a ranking promise). Sent with videos.insert itself
(``localizations``), so it costs no extra quota.

- ``snippet.defaultLanguage`` is "en": the Roman Urdu title is Latin script, and it stays what everyone
  else sees (most Pakistani phones run YouTube in English), so the hook we wrote is not replaced.
- Each translated description is a translated hook paragraph ABOVE the full original description, so
  the credits CC BY licences require, the sources and the links are never lost.
- One cheap text call per upload; any failure uploads without translations. ``LOCALIZE=0`` turns it off.
"""
import os
import re
from typing import List

from pydantic import BaseModel

import short_kit as kit

LANGS = {"hi": "Hindi in Devanagari script", "ur": "Urdu in Urdu (Nastaliq/Arabic) script"}
DEFAULT_LANGUAGE = "en"
KINDS = ("cricket", "quiz", "controversy", "history")   # not songs (English) or the Quran channel
MAX_BYTES = 4900                                        # YouTube's description limit is 5,000 bytes


class Item(BaseModel):
    lang: str
    title: str
    hook: str


class Out(BaseModel):
    items: List[Item]


PROMPT = """Translate a YouTube video's title and the first lines of its description for viewers whose YouTube
is in {langs}. The original is Roman Urdu / Hinglish (or English).
Rules: keep every name, number, team and date exactly; add no claim; keep the curiosity of the title; natural,
everyday wording people type into search (not bookish); keep hashtags like #shorts as they are, in Latin
letters. Title max 95 characters. hook = the description's first 1-2 sentences translated, max 300 characters.
Return one item per language code: {codes}.

TITLE: {title}

DESCRIPTION START:
{start}"""


def available(kind):
    return os.environ.get("LOCALIZE", "1") != "0" and kind in KINDS


def _start(description):
    """The description's first paragraph (the hook), without hashtags."""
    first = (description or "").strip().split("\n\n")[0]
    return re.sub(r"(^|\s)#\w+", "", first).strip()[:600]


def build(client, title, description, kind, log=print):
    """{lang: {"title", "description"}} or {} (off, or any failure)."""
    if not available(kind) or not (title or "").strip():
        return {}
    try:
        got = kit.ask_json(client, Out, PROMPT.format(
            langs=" and ".join(LANGS.values()), codes=", ".join(LANGS), title=title.strip(),
            start=_start(description)))
    except Exception as e:  # noqa: BLE001 — an upload without translations is still an upload
        log(f"   ℹ️ No translated titles ({type(e).__name__}).")
        return {}
    out = {}
    for it in got.items:
        lang = (it.lang or "").strip().lower()
        t = re.sub(r"\s+", " ", (it.title or "").replace("<", "").replace(">", "")).strip()[:100]
        if lang not in LANGS or lang in out or not t or re.fullmatch(r"[\x00-\x7F]*", t):
            continue        # unknown code, a duplicate, or not translated at all (still Latin only)
        hook = (it.hook or "").strip()[:300]
        desc = (hook + "\n\n" + (description or "")).strip() if hook else (description or "")
        if len(desc.encode("utf-8")) > MAX_BYTES:
            desc = description or ""
        out[lang] = {"title": t, "description": desc.replace("<", "").replace(">", "")}
    if out:
        log(f"   🌐 Titles in {', '.join(sorted(out))}: " + " | ".join(out[k]["title"][:40] for k in sorted(out)))
    return out
