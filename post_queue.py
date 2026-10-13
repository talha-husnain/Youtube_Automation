"""Ready to post: every finished Short waits here with a posting time, its
copy and a pinned comment until the user marks it posted (or skips it).

Built for posting by hand: YouTube keeps uploads from an unaudited API
project private (youtube_account.py), so for now a Short goes up from the
YouTube app or Studio. The state lives in ``output/.post_queue.json`` keyed
"<job_id>:<clip index>"; the Shorts themselves are read from the job folders
(app._queue_clips), and a job with a Short still waiting survives the
24 h retention sweep for up to ``KEEP_DAYS`` (app._sweep_expired_job_dirs).

A posted Short gets its public view count by matching its title on the
channel's Shorts tab (the title is pasted exactly as written here). That is
how "make part 2" knows which source video made a winner.
"""
import json
import os
import re
import threading
import time
import unicodedata
from typing import List

from pydantic import BaseModel

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "output", ".post_queue.json")
KEEP_DAYS = 7
STATUSES = ("ready", "posted", "skipped")
_lock = threading.Lock()

PINNED_PROMPT = """You run the comments of a Pakistani YouTube Shorts comedy channel ({handle}).
Write ONE pinned comment for the Short below, in everyday Roman Urdu (Latin letters only).
It must make viewers reply: a cheeky question, a "team A ya team B" choice, or a playful
challenge about THIS clip's situation, plus one emoji. 8 to 18 words. Naughty is fine,
dirty is not: no swear words, no explicit sexual words, nothing about religion, caste,
ethnicity or children. Never name the comedian, creator or show.

Title: {title}
On-screen hook: {hook}
What is said in the clip: {words}
Return only the comment."""


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


def since():
    """When the plan started: Shorts made before it (tests, old jobs) are not
    listed, so the plan opens empty instead of full of old work."""
    with _lock:
        data = _load()
        if "_since" not in data:
            data["_since"] = int(time.time())
            _save(data)
        return data["_since"]


def item_id(job_id, index):
    return f"{job_id}:{int(index)}"


def status_of(job_id, index, state=None):
    return ((state if state is not None else _load()).get(item_id(job_id, index)) or {}).get("status", "ready")


def update(iid, **fields):
    with _lock:
        data = _load()
        row = data.setdefault(iid, {})
        if fields.get("status") is not None and fields["status"] not in STATUSES:
            raise ValueError("bad status")
        row.update({k: v for k, v in fields.items() if v is not None})
        if fields.get("status") == "posted":
            row.setdefault("posted_at", int(time.time()))
        _save(data)
        return row


def keeps(job_id, n_clips, age_seconds):
    """Keep this job's folder past the retention sweep: a Short still waits."""
    if age_seconds > KEEP_DAYS * 86400 or n_clips <= 0:
        return False
    state = _load()
    return any(status_of(job_id, i, state) == "ready" for i in range(n_clips))


def plan(clips, post_times, slots_fn):
    """Merge the Shorts on disk with their state; ready ones get the next free
    posting times, oldest Short first."""
    state = _load()
    out = []
    for c in clips:
        row = dict(state.get(item_id(c["job_id"], c["index"])) or {})
        out.append({**c, "id": item_id(c["job_id"], c["index"]), "status": row.get("status", "ready"),
                    "pinned_comment": row.get("pinned_comment"), "posted_at": row.get("posted_at"),
                    "views": row.get("views"), "youtube_id": row.get("youtube_id"),
                    "telegram_sent": bool(row.get("telegram_sent")), "blocked": bool(row.get("blocked"))})
    ready = sorted((x for x in out if x["status"] == "ready"), key=lambda x: (x["created"], x["index"]))
    for x, slot in zip(ready, slots_fn(post_times, len(ready)) if ready else []):
        x["slot"] = slot.isoformat()
    return out


def _norm(title):
    t = re.sub(r"#\S+", " ", title or "")
    t = "".join(ch for ch in unicodedata.normalize("NFKC", t) if ch.isalnum() or ch.isspace())
    return " ".join(t.lower().split())


def match_views(posted, shorts):
    """Give each posted Short the views of the channel Short with its title."""
    by_title = {}
    for s in shorts:
        by_title.setdefault(_norm(s["title"]), s)
    found = 0
    for p in posted:
        key = _norm(p.get("title"))
        hit = by_title.get(key) or next((s for k, s in by_title.items()
                                         if key and len(key) > 12 and (k.startswith(key) or key.startswith(k))), None)
        if hit:
            update(p["id"], views=hit.get("views") or 0, youtube_id=hit["id"])
            found += 1
    return found


def pinned_comment(client, model, clip, handle):
    from google.genai import types
    words = (clip.get("words") or "")[:1500]
    r = client.models.generate_content(
        model=model, contents=PINNED_PROMPT.format(
            handle=handle or "this channel", title=clip.get("title", ""), hook=clip.get("hook", ""),
            words=words or "(not available)"),
        config=types.GenerateContentConfig(temperature=0.9))
    text = " ".join((r.text or "").strip().strip('"').split())
    if not text or re.search(r"[ऀ-ॿ؀-ۿ]", text):
        raise RuntimeError("The AI did not return a usable comment. Try again.")
    update(item_id(clip["job_id"], clip["index"]), pinned_comment=text)
    return text


RETITLE_PROMPT = """A Short on a Pakistani comedy channel ({handle}) is under-performing: {views} views.
Current title: "{title}"
What is said in the clip: {words}
{rules}{winners}
Write 3 NEW titles that would make more people tap it. Each one in everyday Roman Urdu (Latin
letters only), 45-70 characters, then " #shorts". Put the situation in the first 4 words. Use a
different proven pattern for each: a curiosity gap that sets up the punchline without giving it
away, a specific situation, a direct question to the viewer. Truthful to the clip, at most one
emoji before the hashtag, no swear words, never name the comedian or creator.
For each, say in one short English sentence why it should beat the current title."""


class Retitle(BaseModel):
    title: str
    why: str


class Retitles(BaseModel):
    titles: List[Retitle]


def retitle(client, model, clip, handle, rules="", winners=()):
    """3 better titles for a posted Short that is not getting views."""
    from google.genai import types
    win = ("\nThis channel's best titles so far:\n" + "\n".join(f"- {w}" for w in winners[:5])) if winners else ""
    r = client.models.generate_content(
        model=model, contents=RETITLE_PROMPT.format(
            handle=handle or "this channel", views=clip.get("views") if clip.get("views") is not None else "few",
            title=clip.get("title", ""), words=(clip.get("words") or "(not available)")[:1500],
            rules=f"\n{rules}\n" if rules else "", winners=win),
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=Retitles,
                                           temperature=0.9))
    got = [t for t in Retitles.model_validate_json(r.text).titles
           if t.title.strip() and not re.search(r"[\u0900-\u097F\u0600-\u06FF]", t.title)]
    if not got:
        raise RuntimeError("The AI did not return usable titles. Try again.")
    return [{"title": t.title.strip()[:100], "why": t.why.strip()} for t in got[:3]]
