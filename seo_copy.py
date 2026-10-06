"""Publishing copy per clip: SEO title, description, hashtags, tags, captions.

The detail pass writes one title and two short descriptions per clip as a side
product of picking it; they read as generic ("#viral #shorts") and say nothing
a search would match. This is one extra Gemini call per job, after the clips
and their caption language are final, that writes the copy a clip channel
posts with: a hook title with the main keyword up front, a description whose
first line works as the search snippet, a credit to the original creator, the
channel's call to action, and hashtags / YouTube tags mixing broad and niche
terms in the language the audience searches in.

Fields added to each clip: ``seo_title``, ``seo_description`` (hashtags line
included, ready to paste), ``hashtags`` (list), ``seo_tags`` (list). The
TikTok / Instagram descriptions are replaced with the new copy, so the posting
flow uses it unchanged. ``video_title_for_youtube_short`` (the title burned on
screen) becomes a short on-screen hook of at most 45 characters. Any failure
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


class ClipSEO(BaseModel):
    index: int
    on_screen_title: str
    hook: str
    summary: str
    youtube_title: str
    youtube_description: str
    hashtags: List[str]
    tags: List[str]
    tiktok_caption: str


class SEOResponse(BaseModel):
    clips: List[ClipSEO]


PROMPT = """You write publishing copy for a YouTube Shorts / TikTok / Reels clip channel.
Channel handle: {handle}
Source video title: "{source}"
Write everything in {style}.

For EACH clip below return:
- on_screen_title: max 45 characters, the punchy hook burned on top of the video.
  One language only, no hashtags, no emoji, no "|" separators.
- hook: max 60 characters, the opening line that stops the scroll.
- summary: one sentence, max 140 characters, why this moment works as a short.
- youtube_title: max 70 characters before hashtags, then 1-2 hashtags (always #shorts).
  Open with the main search keyword (topic, comedian or show name) or a strong hook,
  create curiosity, stay truthful to what happens in the clip. Sentence case, at most
  one emoji, no all-caps title.
- youtube_description: 4-6 short lines separated by \\n newline characters:
  line 1: a hook sentence under 120 characters (this is the search snippet);
  lines 2-3: what happens in the clip, using the keywords people search for naturally
  (comedian/creator name if the source title names one, topic, "stand up comedy" style
  phrases that fit);
  then "Credit: <original creator or channel>" when the source title names them;
  then a call to action that names the channel handle (e.g. "Follow {handle} for daily clips");
  then a blank line and a line with 4-5 hashtags (the first 3 show above the title).
- hashtags: 10-15 hashtags, each starting with #, no spaces, lowercase or camelCase.
  Start with #shorts, mix broad (#comedy #funny), niche (#standupcomedy style) and
  clip-specific ones, plus the creator's name if known. No unrelated trending tags.
- tags: 10-15 YouTube tag phrases (no #), the searches a viewer would type, mixing
  English and the audience's language.
- tiktok_caption: under 150 characters: a hook line plus 4-6 hashtags.

Clips (JSON): {clips}

Return JSON: {{"clips": [{{"index": 0, "youtube_title": "...", "youtube_description": "...",
"hashtags": ["#shorts", ...], "tags": ["..."], "tiktok_caption": "..."}}, ...]}}"""


def _clip_text(transcript, clip, limit=700):
    words = [w["word"] for s in (transcript or {}).get("segments") or []
             for w in s.get("words") or []
             if clip["start"] <= w["start"] <= clip["end"]]
    return "".join(words).strip()[:limit]


def format_description(text):
    """Put the description's parts on their own lines.

    The model sometimes returns it as one paragraph (seen on a real job,
    6-oct-2026), which YouTube shows as a wall of text: the hook sentence, the
    credit, the call to action and the hashtag line each get their own line.
    """
    text = re.sub(r"[ \t]+", " ", (text or "").strip())
    if "\n" not in text:
        text = re.sub(r"(?<=[.!?])\s+", "\n", text, count=1)
    text = re.sub(r"\s*(Credit:)", r"\n\n\1", text)
    text = re.sub(r"(?<!\n)\s+(Follow\s+@)", r"\n\1", text)
    text = re.sub(r"\s+((?:#\w+\s*){2,})$", lambda m: "\n\n" + m.group(1).strip(), text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


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


def apply(clips, transcript, source_title=""):
    """Add SEO copy to every clip in place. Returns the number of clips updated."""
    if not clips or os.environ.get("SEO_COPY", "1").strip() == "0":
        return 0
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("   ℹ️ SEO copy skipped (no Gemini key).")
        return 0
    style = LANGUAGE_STYLE.get((os.environ.get("CAPTION_SCRIPT") or "roman").lower(),
                               LANGUAGE_STYLE["roman"])
    handle = (os.environ.get("FRAME_HANDLE") or "").strip() or "this channel"
    items = [{"index": i,
              "on_screen_title": c.get("video_title_for_youtube_short") or "",
              "hook": c.get("viral_hook_text") or "",
              "seconds": round(float(c["end"]) - float(c["start"])),
              "what_is_said": _clip_text(transcript, c)}
             for i, c in enumerate(clips)]
    print(f"🏷️ Writing SEO titles, descriptions and hashtags for {len(clips)} clip(s)...")
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=key)
        model = os.environ.get("GEMINI_MODEL") or "gemini-3.1-flash-lite"
        resp = client.models.generate_content(
            model=model,
            contents=PROMPT.format(handle=handle, source=source_title.replace('"', "'"),
                                   style=style, clips=json.dumps(items, ensure_ascii=False)),
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=SEOResponse,
                temperature=0.8))
        parsed = SEOResponse.model_validate(json.loads(resp.text))
    except Exception as e:  # noqa: BLE001 — the old copy stays
        print(f"   ⚠️ SEO copy failed ({type(e).__name__}: {str(e)[:200]}) — keeping the generated copy.")
        return 0

    done = 0
    for item in parsed.clips:
        if not 0 <= item.index < len(clips):
            continue
        c = clips[item.index]
        tags = _clean_tags(item.hashtags, hashtag=True)
        c["seo_title"] = item.youtube_title.strip()[:100]
        # Shown on the dashboard card; they came from the detail pass in the
        # transcript's script (Devanagari for a Hindi source).
        if item.hook.strip():
            c["viral_hook_text"] = item.hook.strip()[:80]
        if item.summary.strip():
            c["why"] = item.summary.strip()
        short = re.sub(r"\s+", " ", item.on_screen_title or "").strip()
        if 0 < len(short) <= 60:
            # The burned top-band title (framed_layout); long two-language
            # titles from the detail pass shrank to 52 px over two lines.
            c["video_title_for_youtube_short"] = short
        c["seo_description"] = format_description(item.youtube_description)
        c["hashtags"] = tags
        c["seo_tags"] = _clean_tags(item.tags, hashtag=False)
        c["video_description_for_tiktok"] = item.tiktok_caption.strip()
        # Instagram takes the full hashtag list in place of the description's
        # own short hashtag line (no duplicates).
        body = re.sub(r"\n*(?:#\w+\s*)+$", "", c["seo_description"]).strip()
        c["video_description_for_instagram"] = (body + "\n\n" + " ".join(tags)).strip()
        done += 1
    print(f"   ✅ SEO copy ready for {done}/{len(clips)} clips")
    return done
