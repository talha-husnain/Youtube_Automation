"""Reply to comments: new comments on the channel's latest Shorts, each with
a reply drafted in the channel's voice.

Comments are read through yt-dlp with no API key (``getcomments`` needs the
full extraction, not ``process=False``; ~15 s per Short for 30 comments,
measured 8-oct-2026). A comment already answered by the channel, or written
by it, is left out. Replies are drafted in one Gemini call; the user copies
one, or, when the channel is connected (youtube_account.reply), sends it.
State (drafts, sent, hidden) lives in ``output/.comments.json``.
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

from pydantic import BaseModel

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "output", ".comments.json")
SHORTS_TO_READ = 8
COMMENTS_PER_SHORT = 30
MAX_ROWS = 40
_lock = threading.Lock()

REPLY_PROMPT = """You reply to comments for a Pakistani YouTube Shorts comedy channel ({handle}).
For each comment below write a short reply (4 to 18 words) in the commenter's own style:
Roman Urdu for Roman Urdu / Hindi comments, English for English ones, never Devanagari or
Arabic script. Be warm, witty and a little cheeky, like a friend in the comments; keep the
joke of the Short going, thank people who praise, answer questions honestly, and end some
replies with a question so they reply again. Naughty is fine, dirty is not: no swear
words, no explicit sexual words, nothing about religion, caste, ethnicity or children.
Never name the comedian or the original creator of the clip.
If a comment is spam, a link, hate or abuse, set skip true and leave reply empty.

COMMENTS (JSON):
{comments}"""


class Draft(BaseModel):
    id: str
    reply: str
    skip: bool


class Drafts(BaseModel):
    replies: List[Draft]


def _load():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def mark(comment_id, **fields):
    with _lock:
        data = _load()
        data.setdefault(comment_id, {}).update(fields)
        _save(data)


def _video_comments(video):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "getcomments": True,
            "ignore_no_formats_error": True, "js_runtimes": {"node": {}},
            "extractor_args": {"youtube": {"max_comments": [str(COMMENTS_PER_SHORT), str(COMMENTS_PER_SHORT), "60", "5"],
                                           "comment_sort": ["new"], "player_client": ["default", "mweb"]}}}
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(f"https://www.youtube.com/shorts/{video['id']}", download=False)
    except Exception as e:  # noqa: BLE001 — one unreadable Short must not hide the rest
        print(f"   ℹ️ Comments of {video['id']} unreadable: {type(e).__name__}")
        return []
    return [{**c, "video_id": video["id"], "video_title": video.get("title", "")}
            for c in info.get("comments") or []]


def unanswered(comments):
    """Top-level comments by viewers that the channel has not answered yet."""
    answered = {c.get("parent") for c in comments if c.get("author_is_uploader") and c.get("parent") != "root"}
    return [c for c in comments
            if c.get("parent") == "root" and not c.get("author_is_uploader") and c.get("id") not in answered
            and (c.get("text") or "").strip()]


def fetch(handle):
    """New comments to answer, newest first, with the stored drafts."""
    import channel_tools
    shorts = channel_tools.channel_shorts(handle, SHORTS_TO_READ)
    with ThreadPoolExecutor(max_workers=4) as pool:
        found = [c for batch in pool.map(_video_comments, shorts) for c in batch]
    state = _load()
    rows = []
    for c in unanswered(found):
        st = state.get(c["id"]) or {}
        if st.get("status") in ("sent", "hidden"):
            continue
        rows.append({"id": c["id"], "video_id": c["video_id"], "video_title": c["video_title"],
                     "author": c.get("author") or "", "text": c.get("text") or "",
                     "likes": c.get("like_count") or 0, "when": c.get("_time_text") or "",
                     "timestamp": c.get("timestamp") or 0, "draft": st.get("draft"), "skip": st.get("skip", False),
                     "link": f"https://www.youtube.com/watch?v={c['video_id']}&lc={c['id']}"})
    rows.sort(key=lambda r: r["timestamp"], reverse=True)
    # The newest MAX_ROWS: one AI call drafts them all, and a busy channel's
    # 8 Shorts gave 238 (8-oct-2026), more than anyone answers in a sitting.
    return {"at": int(time.time()), "shorts_read": len(shorts), "comments": rows[:MAX_ROWS],
            "more": max(0, len(rows) - MAX_ROWS)}


def draft(client, model, rows, handle):
    """Draft a reply for every row without one; stores and returns them."""
    todo = [r for r in rows if not r.get("draft") and not r.get("skip")][:40]
    if not todo:
        return rows
    from google.genai import types
    payload = [{"id": r["id"], "short_title": r["video_title"][:100], "comment": r["text"][:500]} for r in todo]
    resp = client.models.generate_content(
        model=model, contents=REPLY_PROMPT.format(handle=handle or "this channel",
                                                  comments=json.dumps(payload, ensure_ascii=False)),
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=Drafts,
                                           temperature=0.9))
    got = {d.id: d for d in Drafts.model_validate_json(resp.text).replies}
    with _lock:
        data = _load()
        for r in todo:
            d = got.get(r["id"])
            if not d:
                continue
            r["draft"], r["skip"] = d.reply.strip(), bool(d.skip)
            data.setdefault(r["id"], {}).update(draft=r["draft"], skip=r["skip"])
        _save(data)
    return rows
