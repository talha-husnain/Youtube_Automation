"""Caption and title language: Roman Urdu / Hinglish, English, or as spoken.

YouTube's auto captions for a Hindi or Urdu video come in Devanagari or
Arabic script, and so does the title Gemini writes from them. The audience
these clips are made for reads Roman Urdu ("main ne kaha, kya hua") or
English, so before rendering, each clip's caption words and title go through
one Gemini call:

- ``roman``: every word is transliterated one-for-one, so each keeps its own
  timing and the karaoke highlight still lands on the spoken word. Scripts
  that are already Latin are left alone (no call).
- ``english``: each caption line is translated; the English words of a line
  share that line's time, since word order changes in translation.
- ``original``: nothing changes.

CAPTION_SCRIPT selects it (default roman). Any failure keeps the original
words for that clip: a caption problem must never cost the clip.
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

MODES = ("roman", "english", "original")
_NON_LATIN = re.compile(r"[؀-ۿऀ-෿฀-๿Ѐ-ӿ一-鿿]")


def mode():
    m = (os.environ.get("CAPTION_SCRIPT") or "roman").strip().lower()
    return m if m in MODES else "roman"


def _needs_work(texts, language, m):
    if m == "original":
        return False
    if m == "english":
        return (language or "").split("-")[0].lower() != "en"
    joined = " ".join(texts)
    letters = [c for c in joined if c.isalpha()]
    return bool(letters) and len(_NON_LATIN.findall(joined)) / len(letters) > 0.3


def _client():
    from google import genai
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None, None
    import ai_fallback
    import short_kit
    return (ai_fallback.wrap(genai.Client(api_key=key, http_options=short_kit.http_options())),
            os.environ.get("GEMINI_MODEL") or "gemini-3.1-flash-lite")


def _ask(client, model, prompt):
    from google.genai import types
    cfg = {"response_mime_type": "application/json", "temperature": 0.2}
    if model.startswith("gemini-2.5"):
        # Transliteration needs no reasoning; 2.5's default thinking only adds latency.
        cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    resp = client.models.generate_content(model=model, contents=prompt,
                                          config=types.GenerateContentConfig(**cfg))
    return json.loads(resp.text)


ROMAN_PROMPT = """You convert spoken Hindi/Urdu captions into Roman Urdu (Hinglish), the way
people in Pakistan and India type it in WhatsApp and YouTube comments:
"main ne kaha", "kya hua yaar", "bohat acha", "tum log". Rules:
- Return EXACTLY {n} items in "words", one per input item, same order.
- Transliterate each item on its own. Do not translate, merge, split or drop items.
- English words keep their English spelling ("date", "police", "sorry").
- Keep slang and swear words as spoken; do not censor or soften them.
Also return "title": the title below written in the same Roman Urdu style.

Title: {title}
Items (JSON): {items}

Return JSON: {{"words": [...], "title": "..."}}"""

ROMAN_LINES_PROMPT = """Write these spoken Hindi/Urdu caption lines in Roman Urdu (Hinglish), the
way people type it in WhatsApp and YouTube comments ("main ne kaha", "kya hua yaar").
- Return EXACTLY {n} items in "lines", one per input line, same order.
- Transliterate, do not translate. English words keep their English spelling.
- Keep slang and swear words as spoken; do not censor them.
Also return "title": the title below in the same Roman Urdu style.

Title: {title}
Lines (JSON): {items}

Return JSON: {{"lines": [...], "title": "..."}}"""

ENGLISH_PROMPT = """Translate these spoken caption lines into natural, casual English as a
viewer would read it on a short video. Rules:
- Return EXACTLY {n} items in "lines", one per input line, same order.
- Keep each line short; keep jokes, slang and swearing in spirit; do not censor.
Also return "title": the title below translated into catchy English.

Title: {title}
Lines (JSON): {items}

Return JSON: {{"lines": [...], "title": "..."}}"""


def _clip_segments(transcript, start, end):
    return [s for s in transcript.get("segments") or []
            if s.get("words") and s["end"] > start and s["start"] < end]


def _roman_clip(client, model, transcript, clip):
    segs = _clip_segments(transcript, clip["start"], clip["end"])
    # Every word the captions will show: subtitles._collect_word_blocks takes each word that OVERLAPS the
    # clip. Words were picked by their start (within 1 s) and a long word running into the clip from before
    # stayed in Devanagari on a Roman caption (2 of 15 caption files on disk, 4-nov-2026: "कि", "मुझे").
    words = [w for s in segs for w in s["words"]
             if not w.get("_script") and float(w.get("end", w["start"])) > clip["start"] - 1
             and w["start"] < clip["end"] + 1]
    items = [w["word"].strip() for w in words]
    title = clip.get("video_title_for_youtube_short") or ""
    for _ in range(2):
        out = _ask(client, model, ROMAN_PROMPT.format(
            n=len(items), title=title, items=json.dumps(items, ensure_ascii=False)))
        new = out.get("words") or []
        if len(new) == len(items):
            for w, t in zip(words, new):
                t = str(t).strip()
                if t:
                    w["word"] = " " + t
                    w["_script"] = "roman"
            if (out.get("title") or "").strip():
                clip["video_title_for_youtube_short"] = out["title"].strip()
            return True
    # Word-for-word failed twice (1 clip in 10 on a real job, 6-oct-2026).
    # Lines always align, so convert line by line and let each line's Roman
    # words share its time: the highlight is a little less exact, but no clip
    # is left in a script the audience cannot read.
    if _lines_clip(client, model, transcript, clip, ROMAN_LINES_PROMPT, "roman"):
        return True
    print(f"   ⚠️ Roman captions failed on the clip at {clip['start']:.0f}s — "
          f"keeping the original script.")
    return False


def _english_clip(client, model, transcript, clip):
    if _lines_clip(client, model, transcript, clip, ENGLISH_PROMPT, "english"):
        return True
    print(f"   ⚠️ English captions: line count mismatch on the clip at "
          f"{clip['start']:.0f}s — keeping the original language.")
    return False


def _lines_clip(client, model, transcript, clip, prompt, label):
    """Convert the clip's caption LINES; each line's new words share its time."""
    segs = [s for s in _clip_segments(transcript, clip["start"], clip["end"])
            if not s.get("_script") and not any(w.get("_script") for w in s["words"])]
    lines = [s["text"] for s in segs]
    title = clip.get("video_title_for_youtube_short") or ""
    new = []
    for _ in range(2):
        out = _ask(client, model, prompt.format(
            n=len(lines), title=title, items=json.dumps(lines, ensure_ascii=False)))
        new = out.get("lines") or []
        if len(new) == len(lines):
            break
    if len(new) != len(lines):
        return False
    for seg, line in zip(segs, new):
        tokens = str(line).split()
        if not tokens:
            continue
        a, b = seg["words"][0]["start"], seg["words"][-1]["end"]
        total = sum(len(t) for t in tokens) or 1
        t, words = a, []
        for tok in tokens:
            d = (b - a) * len(tok) / total
            words.append({"word": " " + tok, "start": round(t, 3), "end": round(t + d, 3)})
            t += d
        seg["words"], seg["text"], seg["_script"] = words, " ".join(tokens), label
    if (out.get("title") or "").strip():
        clip["video_title_for_youtube_short"] = out["title"].strip()
    return True


def apply(transcript, clips):
    """Rewrite the clips' caption words and titles in place. Returns the mode used."""
    m = mode()
    if not transcript or not clips:
        return "original"
    texts = [s.get("text") or "" for s in (transcript.get("segments") or [])[:200]]
    texts += [c.get("video_title_for_youtube_short") or "" for c in clips]
    if not _needs_work(texts, transcript.get("language"), m):
        return "original"
    client, model = _client()
    if client is None:
        print("   ℹ️ Caption language unchanged (no Gemini key).")
        return "original"
    work = _roman_clip if m == "roman" else _english_clip
    label = "Roman Urdu / Hinglish" if m == "roman" else "English"
    print(f"🔤 Writing captions and titles in {label}...")

    # Overlapping clips share words, and the "_script" mark that stops a word
    # being converted twice is only safe when they run one after another. The
    # usual case, clips that do not overlap, runs in parallel.
    def _safe(clip):
        try:
            return work(client, model, transcript, clip)
        except Exception as e:  # noqa: BLE001 — keep the clip, lose only the script
            print(f"   ⚠️ Caption language failed on the clip at {clip['start']:.0f}s "
                  f"({type(e).__name__}: {str(e)[:150]})")
            return False

    ordered = sorted(clips, key=lambda c: c["start"])
    disjoint = all(a["end"] <= b["start"] for a, b in zip(ordered, ordered[1:]))
    if disjoint:
        with ThreadPoolExecutor(max_workers=5) as pool:
            done = sum(pool.map(_safe, ordered))
    else:
        done = sum(_safe(c) for c in ordered)
    print(f"   ✅ {done}/{len(clips)} clips in {label}")
    return m
