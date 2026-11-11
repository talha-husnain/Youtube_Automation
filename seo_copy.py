"""Publishing copy per clip: SEO title, description, hashtags, tags, captions.

The detail pass writes one title and two short descriptions per clip as a side
product of picking it; they read as generic ("#viral #shorts") and say nothing
a search would match. This is one extra Gemini call per job, after the clips
and their caption language are final, that writes the copy a clip channel
posts with: a hook title with the main keyword up front, a description whose
first line works as the search snippet, the channel's call to action, and hashtags / YouTube tags mixing broad and niche
terms in the language the audience searches in. The original creator is never
named anywhere (the channel owner's rule): the model reports the name only so
the code can check for it.

Fields added to each clip: ``seo_title``, ``seo_description`` (hashtags line
included, ready to paste), ``hashtags`` (list), ``seo_tags`` (list). The
TikTok / Instagram descriptions are replaced with the new copy, so the posting
flow uses it unchanged. ``video_title_for_youtube_short`` (the title burned on
screen) becomes a short on-screen hook of at most 6 words that never spoils the punchline
(research 11-nov-2026: the first 2 seconds decide the swipe). Any failure
keeps the old copy.
"""
import json
import os
import re
from typing import List

from pydantic import BaseModel

LANGUAGE_STYLE = {
    "roman": ("Roman Urdu / Hinglish written in Latin letters, the way Pakistani and Indian "
              "viewers type and search (\"comedy\", \"funny\" and other English search words "
              "stay English)"),
    "english": "English",
    "original": "the same language and script as the clip's transcript",
}


# A description under ~150 words gives YouTube search little to match and
# reads as auto-generated; the first jobs' came back at 40-60 words.
MIN_DESCRIPTION_WORDS = 150


class ClipSEO(BaseModel):
    index: int
    on_screen_title: str
    hook: str
    summary: str
    youtube_title: str
    description_hook: str
    description_body: str
    creator: str
    hashtags: List[str]
    tags: List[str]
    tiktok_caption: str


class SEOResponse(BaseModel):
    clips: List[ClipSEO]


PROMPT = """You are the growth writer for a YouTube Shorts / TikTok / Reels clip channel.
Channel handle: {handle}
Source video title: "{source}"
Write everything in {style}.
Use everyday spoken words, the way people comment and search. Never formal or bookish
Hindi / Urdu: write "unexpected", "ending", "funny", "kahani", "scene", "secret",
"opinion", not "apratyashit", "ant", "haasya", "vrittant", "rahasya".
{script_rule}
NEVER name the original creator, comedian, speaker, channel or show anywhere: not in
titles, descriptions, hashtags, tags or captions, not even as a hashtag. If you must refer
to the speaker, say "comedian" or "yeh banda". Build titles from the situation instead.
Every clip of this job is posted on the same channel, so make them different from each
other: no two youtube_titles may share the same opening words or the same pattern, and
no sentence may be reused across clips.

For EACH clip below return:
- on_screen_title: the hook burned on top of the video, read in the first second: at most 6
  words and 40 characters. Set up the situation and make them want the payoff, NEVER give
  away the punchline or the comeback ("Uncle ne comedian ko chup kara diya" teases; the
  joke's own last line spoils it). One language only, no hashtags, no emoji, no "|".
- hook: max 60 characters, the opening line that stops the scroll.
- summary: one sentence, max 140 characters, why this moment works as a short.
- youtube_title: 45-70 characters before hashtags, then " #shorts" and optionally one
  more relevant hashtag. Put the main search keyword (the topic or situation) in the
  first 4 words. Use ONE proven viral pattern: a curiosity gap that sets up the punchline
  without giving it away ("Jab dost ne police ke saamne..."), a specific situation
  ("Goa mein police checking ka sabse funny kissa"), or a direct question to the viewer.
  Specific beats generic: name the situation, not just "funny moment". Truthful to the
  clip, sentence case, no all-caps, at most one emoji placed before the hashtags.
- No swear words, slurs or censored swear words ("g*nd") in youtube_title,
  on_screen_title, hook or tiktok_caption: YouTube limits the reach of those.
- description_hook: one line under 120 characters. This is the search snippet: name the
  topic and tease the payoff.
- description_body: AT LEAST 160 words and at most 230, in exactly 3 paragraphs separated
  by a blank line:
  1) tell the story of the clip in a conversational, storytelling tone (who, what
     situation, how it builds) without spoiling the final punchline;
  2) why THIS clip is funny or relatable (its specific joke, line or situation, never a
     generic sentence that would fit any clip), weaving in 6-8 search phrases naturally
     ("stand up comedy", "hindi comedy", "desi comedy", "funny story", the clip's topic
     words);
  3) a question the viewer will want to answer in the comments, then ask them to like,
     share with the friend this reminds them of, and subscribe.
  No hashtags and no channel handle in the body: those are added after it.
- creator: the name of the original creator / comedian / channel if the source title or
  the clip names one, else "". This field is only used to check the copy; it is never
  published, so the name must not appear in any other field.
- hashtags: 12-15 hashtags, each starting with #, no spaces, lowercase or camelCase.
  Start with #shorts, mix broad (#comedy #funny), niche (#standupcomedy style),
  clip-specific ones. No names of people or channels. No unrelated trending tags.
- tags: 12-15 YouTube tag phrases (no #), the searches a viewer would type, mixing
  English and the audience's language.
- tiktok_caption: under 150 characters: a hook line plus 4-6 hashtags.
{extra}
Clips (JSON): {clips}

Return JSON: {{"clips": [{{"index": 0, "youtube_title": "...", "description_hook": "...",
"description_body": "...", "creator": "...", "hashtags": ["#shorts", ...], ...}}, ...]}}"""


def _clip_text(transcript, clip, limit=1200):
    words = [w["word"] for s in (transcript or {}).get("segments") or []
             for w in s.get("words") or []
             if clip["start"] <= w["start"] <= clip["end"]]
    return "".join(words).strip()[:limit]


def word_count(text):
    return len(re.findall(r"[^\W_]+(?:['\u2019][^\W_]+)?", text or ""))


def _paragraphs(text):
    """Body text as clean paragraphs; a hashtag line the model adds anyway is
    dropped (the description ends with its own)."""
    text = re.sub(r"[ \t]+", " ", (text or "").replace("\\n", "\n")).strip()
    text = re.sub(r"\s*(?:#\w+\s*){2,}$", "", text).strip()
    paras = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    if len(paras) == 1 and word_count(text) > 60:
        # Asked for 3 paragraphs, it sometimes sends one block: cut it into
        # three at sentence ends, as even by length as the sentences allow.
        sents = re.split(r"(?<=[.!?])\s+", text)
        if len(sents) >= 3:
            paras, cur, seen = [], [], 0
            for s in sents:
                cur.append(s)
                seen += len(s) + 1
                if len(paras) < 2 and seen >= len(text) * (len(paras) + 1) / 3:
                    paras.append(" ".join(cur))
                    cur = []
            if cur:
                paras.append(" ".join(cur))
    return "\n\n".join(paras)


def build_description(hook, body, handle, hashtags):
    """The YouTube description, assembled here so its layout never depends on
    the model keeping line breaks (it returned one paragraph on a real job,
    6-oct-2026): hook line, story paragraphs, follow line, hashtags."""
    parts = [re.sub(r"\s+", " ", hook or "").strip(), _paragraphs(body)]
    parts.append(f"Follow {handle} for daily clips" if handle.startswith("@")
                 else "Follow for daily clips")
    if hashtags:
        parts.append(" ".join(hashtags[:5]))
    return "\n\n".join(p for p in parts if p)


def _clean_tags(tags, hashtag):
    out, seen = [], set()
    for t in tags or []:
        t = re.sub(r"\s+", "" if hashtag else " ", str(t)).strip()
        if hashtag:
            t = "#" + t.lstrip("#")
            if len(t) < 2:
                continue
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    if hashtag and "#shorts" not in seen:
        out.insert(0, "#shorts")
    return out[:15]


def _ask(client, model, items, handle, source, style, latin, extra=""):
    from google.genai import types
    script_rule = ("Latin letters only in every field: never Devanagari or Arabic script, "
                   "not even for a single word." if latin else "")
    resp = client.models.generate_content(
        model=model,
        contents=PROMPT.format(handle=handle, source=source, style=style, extra=extra,
                               script_rule=script_rule,
                               clips=json.dumps(items, ensure_ascii=False)),
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=SEOResponse,
            temperature=0.8))
    return {c.index: c for c in SEOResponse.model_validate(json.loads(resp.text)).clips}


def _body_words(item):
    return word_count(item.description_hook) + word_count(item.description_body)


# Devanagari / Arabic letters. A Roman Urdu answer still slipped one Devanagari
# word into a description on a real job (6-oct-2026).
_NON_LATIN = re.compile("[؀-ۿऀ-ॿ]")


# Sanskritised words the model reaches for and nobody types in a comment or a
# search ("Ladai ka sabse apratyashit ant" on a real title, 6-oct-2026).
_BOOKISH = re.compile(r"\b(apratyashit|ant|haasya|hasya|vrittant|rahasya)\b", re.I)


def _published_text(item):
    return " ".join([item.on_screen_title, item.hook, item.summary, item.youtube_title,
                     item.description_hook, item.description_body, item.tiktok_caption,
                     *item.hashtags, *item.tags])


def name_pattern(names, handle=""):
    """Regex for the creator names the model reported, or None.

    Matches the full name with or without spaces ("Naman Jain", "#NamanJain")
    and the first name alone ("Naman ne bataya"), never a lone surname: a
    "Khan" or "Jain" on its own is too common to remove from a sentence.
    The channel's own name is never treated as the creator's."""
    own = re.sub(r"[^a-z0-9]", "", handle.lower())
    alts = set()
    for n in names:
        toks = re.findall(r"[^\W_]+", n or "")
        if not toks or (own and re.sub(r"[^a-z0-9]", "", "".join(toks).lower()) == own):
            continue
        alts.add(r"\s*".join(map(re.escape, toks)))
        if len(toks) > 1 and len(toks[0]) >= 4:
            alts.add(re.escape(toks[0]))
    if not alts:
        return None
    return re.compile(r"(?<![^\W_])(?:" + "|".join(sorted(alts, key=len, reverse=True))
                      + r")(?![^\W_])", re.I)


def _balance_quotes(text):
    """Drop double quotes when they do not pair up (a title came back as
    'awaaz badal di "🤣 #shorts', 6-oct-2026)."""
    return text.replace('"', "") if text.count('"') % 2 else text


def _by_names(source_title):
    """'... STAND UP COMEDY BY NAMAN JAIN' -> ['NAMAN JAIN'], in case the model
    leaves the creator field empty."""
    m = re.search(r"\bby\s+([^|\-–()\[\]#,]+)", (source_title or "").replace("_", " "), re.I)
    return [m.group(1).strip()] if m else []


def _wrong_words(item, latin, names=None):
    text = _published_text(item)
    return bool((latin and (_NON_LATIN.search(text) or _BOOKISH.search(text)))
                or (names and names.search(text)))


def _quality(item, latin, names=None):
    """Higher is better: right words first, then long enough, then length."""
    words = _body_words(item)
    return (not _wrong_words(item, latin, names), words >= MIN_DESCRIPTION_WORDS, words)


def _scrub(text, names):
    """Last resort when a retry still named the creator."""
    if not names:
        return text
    text = names.sub("comedian", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def apply(clips, transcript, source_title="", context="", text_limit=1200):
    """Add SEO copy to every clip in place. Returns the number of clips updated."""
    if not clips or os.environ.get("SEO_COPY", "1").strip() == "0":
        return 0
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("   ℹ️ SEO copy skipped (no Gemini key).")
        return 0
    # Always Roman Urdu, whatever the subtitles are in (owner's rule,
    # 8-oct-2026: a Devanagari title came out of an "as spoken" job).
    # SEO_SCRIPT=english|original overrides it.
    script = (os.environ.get("SEO_SCRIPT") or "roman").lower()
    style = LANGUAGE_STYLE.get(script, LANGUAGE_STYLE["roman"])
    latin = script != "original"
    handle = (os.environ.get("FRAME_HANDLE") or "").strip() or "this channel"
    # Only the clip's own words go in: given the detail pass's title, the model
    # kept its bookish wording ("apratyashit ant") despite the rules.
    items = [{"index": i,
              "seconds": round(float(c["end"]) - float(c["start"])),
              "what_is_said": _clip_text(transcript, c, text_limit)}
             for i, c in enumerate(clips)]
    print(f"🏷️ Writing SEO titles, descriptions and hashtags for {len(clips)} clip(s)...")
    source = source_title.replace('"', "'")
    # Extra context for a special clip (compilation.py); empty for a normal
    # job, which keeps its prompt exactly as before.
    note = f"\n{context}\n" if context else ""
    # Title rules learned from the channel's own numbers (what_works.py);
    # empty until the user builds a "what works" report.
    import what_works
    learned = what_works.guidance()
    if learned:
        note += f"\n{learned}\n"
    # Title and hook shapes of the niche's most viewed videos now (niche_research, NICHE_PLAYBOOK).
    niche = [l for l in (os.environ.get("NICHE_PLAYBOOK") or "").splitlines()
             if l.startswith(("- Titles", "- Hooks", "- Avoid"))]
    if niche:
        note += "\nIn this niche the most viewed videos now use (shapes only, write your own words):\n" + \
                "\n".join(niche) + "\n"
    try:
        from google import genai
        import ai_fallback
        import short_kit
        client = ai_fallback.wrap(genai.Client(api_key=key, http_options=short_kit.http_options()))
        model = os.environ.get("GEMINI_MODEL") or "gemini-3.1-flash-lite"
        got = _ask(client, model, items, handle, source, style, latin, note)
    except Exception as e:  # noqa: BLE001 — the old copy stays
        print(f"   ⚠️ SEO copy failed ({type(e).__name__}: {str(e)[:200]}) — keeping the generated copy.")
        return 0

    names = name_pattern([it.creator for it in got.values()] + _by_names(source_title), handle)

    # One more call for the clips that came back missing, short, in the wrong
    # script or naming the creator.
    redo = [it for it in items
            if it["index"] not in got or not all(_quality(got[it["index"]], latin, names)[:2])]
    if redo:
        print(f"   🔁 Rewriting {len(redo)} clip(s) whose copy came back short "
              f"(under {MIN_DESCRIPTION_WORDS} words), named the creator or used the wrong words...")
        extra = ("\nIMPORTANT: the last answer for these clips was rejected. Every "
                 "description_body must be at least 180 words in 3 full paragraphs, "
                 "no field may contain the creator's or channel's name (not even as a "
                 "hashtag), and every field must use Latin letters and everyday words only "
                 "(never \"ant\", \"apratyashit\", \"rahasya\").\n")
        try:
            for i, it in _ask(client, model, redo, handle, source, style, latin,
                              note + extra).items():
                if i not in got or _quality(it, latin, names) > _quality(got[i], latin, names):
                    got[i] = it
        except Exception as e:  # noqa: BLE001 — keep the first answer
            print(f"   ⚠️ Retry failed ({type(e).__name__}) — keeping the first answer.")

    done = 0
    for item in got.values():
        if not 0 <= item.index < len(clips):
            continue
        c = clips[item.index]
        if names and names.search(_published_text(item)):
            # Still named after the retry: drop those tags, swap the name in prose.
            item.hashtags = [h for h in item.hashtags if not names.search(h)]
            item.tags = [t for t in item.tags if not names.search(t)]
            for f in ("on_screen_title", "hook", "summary", "youtube_title",
                      "description_hook", "description_body", "tiktok_caption"):
                setattr(item, f, _scrub(getattr(item, f), names))
        tags = _clean_tags(item.hashtags, hashtag=True)
        c["seo_title"] = _balance_quotes(item.youtube_title.strip())[:100]
        # Shown on the dashboard card; they came from the detail pass in the
        # transcript's script (Devanagari for a Hindi source).
        if item.hook.strip():
            c["viral_hook_text"] = item.hook.strip()[:80]
        if item.summary.strip():
            c["why"] = item.summary.strip()
        short = _balance_quotes(re.sub(r"\s+", " ", item.on_screen_title or "").strip())
        if 0 < len(short) <= 60:
            # The burned top-band title (framed_layout); long two-language
            # titles from the detail pass shrank to 52 px over two lines.
            c["video_title_for_youtube_short"] = short
        c["seo_description"] = build_description(item.description_hook, item.description_body,
                                                 handle, tags)
        c["hashtags"] = tags
        c["seo_tags"] = _clean_tags(item.tags, hashtag=False)
        c["video_description_for_tiktok"] = item.tiktok_caption.strip()
        # Instagram takes the full hashtag list in place of the description's
        # own short hashtag line (no duplicates).
        body = re.sub(r"\n*(?:#\w+\s*)+$", "", c["seo_description"]).strip()
        c["video_description_for_instagram"] = (body + "\n\n" + " ".join(tags)).strip()
        done += 1
    words = [word_count(c["seo_description"]) for c in clips if c.get("seo_description")]
    print(f"   ✅ SEO copy ready for {done}/{len(clips)} clips"
          + (f" (descriptions {min(words)}-{max(words)} words)" if words else ""))
    return done
