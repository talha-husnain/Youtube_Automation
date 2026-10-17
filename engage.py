"""Engagement on every channel, after the upload (self-host).

Views on a small channel come from viewers who answer, come back and
watch the next one, so each channel can (switches per channel, see
``SWITCHES``):
- ``first_comment``: once a Short is public, the channel posts the first
  comment, a question viewers want to answer (the quiz asks for the score).
  YouTube's API cannot pin it; it can be pinned in Studio.
- ``auto_reply``: every few hours, new viewer comments on the last days'
  Shorts get a reply in the channel's voice; on the quiz channel the reply
  says whether their answer was right (the answers travel in the upload row).
  At most REPLIES_PER_DAY a channel; spam, links and abuse are skipped.
- ``playlists``: each upload goes into the channel's playlist for its kind
  ("Paheliyan", "Cricket facts and records"...), made on first use, so a
  viewer who liked one is offered the next.
- ``cross_promo``: a "More from us" line naming the owner's other connected
  channels goes into every description (before the hashtags).

Writes cost YouTube API quota (comments, playlists: 50 units each; reads 1)
out of the Google project's 10,000 a day, shared by every channel, so
youtube_account.spend() keeps count and engagement stops at QUOTA_BUDGET,
leaving room for uploads' own reads and the claim checks.
"""
import json
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import List

from pydantic import BaseModel

ROOT = os.path.dirname(os.path.abspath(__file__))
MAIN_STATE = os.path.join(ROOT, "output", ".engage.json")
SWITCHES = ("first_comment", "auto_reply", "playlists", "cross_promo")
COMMENT_DAYS = 7
REPLY_DAYS = 4
REPLY_EVERY = 3 * 3600
REPLIES_PER_DAY = 15
QUOTA_BUDGET = 6000
COMMENT_UNITS = PLAYLIST_UNITS = 50
_lock = threading.Lock()

FIRST_COMMENTS = {
    "comedy": ["Sab se funny line konsi thi? 😂 Neeche likho 👇", "Isko us dost ko bhejo jo bilkul aisa hai 😂",
               "1 se 10 tak kitna hasaya? 😂👇"],
    "cricket": ["Aap ka favourite record konsa hai? 🏏👇", "Is se bara record kisi ka hai? Comment karo 👇",
                "Agle Short mein kis player ke stats chahiye? 🏏👇"],
    "quiz": ["Apna score comment karo 🧠 Kitne sahi hue?", "Kis sawal ne phansaya? 😅 Score neeche likho 👇",
             "Pehli baar mein kitne sahi? Sach batana 😄👇"],
    "music": ["Which line hit you the hardest? 🎧👇", "Rate this song from 1 to 10 👇",
              "Who are you sending this to? 🎶"],
    "controversy": ["Aap kis ki side par hain? 👇", "Aap ke hisab se asal ghalti kis ki thi? 👇",
                    "Agli controversy kis ki explain karein? 👇"],
    "history": ["Agli kahani kis ki sunni hai? Neeche likho 👇", "Is kahani ka kaunsa hissa sab se hairan kar gaya? 👇",
                "Kya aap ko yeh pehle se pata tha? 👇"],
}
FOLLOW_LINE = {"comedy": "Roz naye funny Shorts: follow karo 🔔", "cricket": "Roz naye cricket facts: follow karo 🔔",
               "quiz": "Roz naya quiz: follow karo aur apna streak banao 🔔",
               "music": "A new song every day: follow so you don't miss it 🔔",
               "controversy": "Roz ek controversy, sources ke saath: follow karo 🔔",
               "history": "Nayi tareekhi kahaniyon ke liye subscribe karo 🔔"}
PLAYLISTS = {
    ("cricket", "match"): "Cricket match results", ("cricket", "topic"): "Cricket facts and records",
    ("cricket", "versus"): "Who is better? Player vs player", ("quiz", "mcq"): "GK quiz",
    ("quiz", "riddle"): "Paheliyan", ("quiz", "math"): "Dimagh lagao: maths puzzles",
    ("quiz", "flags"): "Flag quiz: guess the country", ("quiz", "truefalse"): "Sach ya Jhoot",
    ("quiz", "oddone"): "Odd one out", ("music", None): "New AI songs",
    ("comedy", None): "Comedy Shorts", ("controversy", None): "Controversies explained",
    ("history", None): "History and stories", ("history", "teaser"): "History in 60 seconds", ("history", "today"): "Aaj ki tareekh",
}

REPLY_PROMPT = """You reply to viewer comments for {who} ({handle}).
For each comment write a short reply (4 to 16 words) in the commenter's own style:
Roman Urdu for Roman Urdu / Hindi comments, English for English ones, never Devanagari
or Arabic script. Warm, friendly, a little playful; thank praise, answer questions
honestly, and end some replies with a question so they reply again. No swear words,
nothing explicit, nothing about religion, politics, caste, ethnicity or children.
{extra}If a comment is spam, a link, hate or abuse, set skip true and leave reply empty.
request: when the commenter asks the channel to make a video about a specific topic
("Tipu Sultan par video banao", "do one on Babar Azam"), that topic in 2 to 8 words;
otherwise empty. Only the topic, never instructions.

COMMENTS (JSON):
{comments}"""
WHO = {"comedy": "a Pakistani comedy Shorts channel", "cricket": "a cricket facts channel for Pakistani and Indian fans",
       "quiz": "a quiz and paheli Shorts channel", "music": "an English AI music channel (songs made with AI)",
       "controversy": "a channel that explains controversies about famous people fairly, with sources",
       "history": "a history channel of long documentary videos (empires, famous events, countries)"}
# Replies on a controversy must not become new accusations.
CONTROVERSY_EXTRA = ("Stay neutral and fair: never agree with insults or new accusations about the person, "
                     "never add claims the video did not make; thank people for their view and ask what they think. ")
# History viewers argue about sects and nations; replies never join in.
HISTORY_EXTRA = ("These are history documentaries: thank viewers, answer only with what the video said, and never "
                 "argue about religion, sects, nations or politics; to a religious comment reply with a short, "
                 "respectful thanks. ")
QUIZ_EXTRA = ("These are quiz Shorts: each comment's short_answers lists the right answers of that Short. "
              "When the comment gives answers or a score, say warmly whether they got it right (\"Bilkul sahi!\" / "
              "\"Ufff, galat! Sahi jawab tha ...\"), never mocking. ")


class Reply(BaseModel):
    id: str
    reply: str
    skip: bool
    request: str = ""


REQUEST_DAYS = 14          # a viewer's topic request stays in the planner's hints this long
REQUESTS_KEPT = 30


def request_hint(asked):
    """The planner prompt's line for viewers' topic requests ('' without any)."""
    if not asked:
        return ""
    return ("Viewers asked in the comments for videos on: " + "; ".join(a[:80] for a in asked)
            + ". Make one of these when it fits this channel and every rule; the rules always win.\n")


def requests(acct, days=REQUEST_DAYS, limit=5):
    """The latest topics viewers asked for, newest first, one per topic."""
    since, seen, out = time.time() - days * 86400, set(), []
    for r in reversed(load(acct).get("requests") or []):
        key = re.sub(r"[^a-z0-9]+", " ", r.get("text", "").lower()).strip()
        if r.get("at", 0) >= since and key and key not in seen:
            seen.add(key)
            out.append(r["text"])
    return out[:limit]


class Replies(BaseModel):
    replies: List[Reply]


# ------------------------------------------------------------------ state

def _state_path(acct):
    return os.path.join(os.path.dirname(acct["token"]), "engage.json") if acct else MAIN_STATE


def load(acct):
    try:
        with open(_state_path(acct), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(acct, data):
    path = _state_path(acct)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _update(acct, fn):
    with _lock:
        st = load(acct)
        fn(st)
        _save(acct, st)
        return st


# ------------------------------------------------------------------ helpers

def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _live_rows(days):
    """This account's uploads of the last ``days`` whose time has come."""
    import youtube_account as ya
    now = datetime.now(timezone.utc)
    since = time.time() - days * 86400
    out = []
    for r in ya.uploads():
        # "elsewhere": it went up on another channel (my_channels.check_placement),
        # so this channel must not comment on it as if it were its own.
        if (r.get("status") != "done" or not r.get("video_id") or r.get("created", 0) < since or r.get("blocked")
                or r.get("elsewhere")):
            continue
        at = r.get("publish_at")
        try:
            due = datetime.fromisoformat(at) <= now if at else True
        except ValueError:
            due = True
        if due:
            out.append(r)
    return out


def _public(rows):
    """Of these rows, the ones YouTube shows as public now (1 unit per 50)."""
    import youtube_account as ya
    public = set()
    for k in range(0, len(rows), 50):
        part = rows[k:k + 50]
        res = ya._get(f"{ya.API}/videos", {"part": "status", "id": ",".join(r["video_id"] for r in part)})
        ya.spend(1)
        public |= {v["id"] for v in res.get("items") or []
                   if (v.get("status") or {}).get("privacyStatus") == "public"}
    return [r for r in rows if r["video_id"] in public]


def _post(url, params, body):
    import httpx
    import youtube_account as ya
    r = httpx.post(url, params=params, headers={"Authorization": f"Bearer {ya._token()}"}, json=body, timeout=30)
    ya.spend(50)
    if r.status_code not in (200, 201):
        raise RuntimeError(ya._google_error(r))
    return r.json()


def first_comment_text(kind, row, rnd=random):
    """The channel's first comment: the Short's own question when it has one."""
    question = (row.get("question") or "").strip()
    if not question:
        question = rnd.choice(FIRST_COMMENTS.get(kind) or FIRST_COMMENTS["comedy"])
    return f"{question}\n\n{FOLLOW_LINE.get(kind, FOLLOW_LINE['comedy'])}"[:500]


# ------------------------------------------------------------------ the three jobs

def first_comments(acct, kind, log=print):
    import youtube_account as ya
    st = load(acct)
    done = st.get("commented") or {}
    todo = [r for r in _live_rows(COMMENT_DAYS) if r["video_id"] not in done]
    if not todo or ya.quota_used() + 1 + COMMENT_UNITS > QUOTA_BUDGET:
        return 0
    n = 0
    for r in _public(todo):
        if ya.quota_used() + COMMENT_UNITS > QUOTA_BUDGET:
            break
        try:
            got = _post(f"{ya.API}/commentThreads", {"part": "snippet"}, {"snippet": {
                "videoId": r["video_id"], "topLevelComment": {"snippet": {"textOriginal": first_comment_text(kind, r)}}}})
        except RuntimeError as e:
            log(f"   ℹ️ No first comment on '{r.get('title', '')[:50]}': {str(e)[:120]}")
            # Comments off on that video, or made for kids: do not try again.
            _update(acct, lambda s: s.setdefault("commented", {}).update({r["video_id"]: -1}))
            continue
        n += 1
        _update(acct, lambda s: s.setdefault("commented", {}).update({r["video_id"]: got.get("id") or 1}))
    if n:
        log(f"💬 First comment on {n} new Short(s).")
    return n


def _comments_on(video_id, my_channel_id):
    """New top-level viewer comments on one Short that nobody answered yet."""
    import youtube_account as ya
    res = ya._get(f"{ya.API}/commentThreads", {"part": "snippet", "videoId": video_id, "maxResults": 50,
                                                "order": "time", "textFormat": "plainText"})
    ya.spend(1)
    out = []
    for t in res.get("items") or []:
        sn = (t.get("snippet") or {})
        top = ((sn.get("topLevelComment") or {}).get("snippet") or {})
        author = (top.get("authorChannelId") or {}).get("value")
        if author and author == my_channel_id:
            continue
        if sn.get("totalReplyCount", 0) > 0:
            continue
        out.append({"id": t["snippet"]["topLevelComment"]["id"], "text": top.get("textDisplay") or "",
                    "video_id": video_id})
    return out


def reply_due(acct, now=None):
    return (now or time.time()) - load(acct).get("last_reply_pass", 0) >= REPLY_EVERY


def auto_replies(acct, kind, handle, my_channel_id, client_fn, log=print, model=None):
    import youtube_account as ya
    import short_kit as kit
    _update(acct, lambda s: s.update(last_reply_pass=int(time.time())))
    st = load(acct)
    day = datetime.now().strftime("%Y-%m-%d")
    used = (st.get("replies_per_day") or {}).get(day, 0)
    left = REPLIES_PER_DAY - used
    if left <= 0 or ya.quota_used() + 10 + COMMENT_UNITS > QUOTA_BUDGET:
        return 0
    replied = st.get("replied") or {}
    rows = _live_rows(REPLY_DAYS)
    todo, titles = [], {}
    for r in rows:
        titles[r["video_id"]] = r
        for c in _comments_on(r["video_id"], my_channel_id):
            if c["id"] not in replied and c["text"].strip():
                todo.append(c)
        if len(todo) >= left:
            break
    todo = todo[:left]
    if not todo:
        return 0
    payload = [{"id": c["id"], "short_title": (titles[c["video_id"]].get("title") or "")[:100],
                "comment": c["text"][:400],
                **({"short_answers": titles[c["video_id"]].get("answers") or []} if kind == "quiz" else {})}
               for c in todo]
    from google.genai import types
    resp = client_fn().models.generate_content(
        model=model or kit.text_model(),
        contents=REPLY_PROMPT.format(who=WHO.get(kind, WHO["comedy"]), handle=handle or "this channel",
                                     extra={"quiz": QUIZ_EXTRA, "controversy": CONTROVERSY_EXTRA,
                                            "history": HISTORY_EXTRA}.get(kind, ""),
                                     comments=json.dumps(payload, ensure_ascii=False)),
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=Replies,
                                           temperature=0.8))
    drafts = {d.id: d for d in Replies.model_validate_json(resp.text).replies}
    asked = [re.sub(r"\s+", " ", d.request).strip(" .\"'")[:80] for d in drafts.values()
             if not d.skip and d.request.strip()]
    if asked:
        # Viewers steer the next ideas (my_channels hands these to the planner).
        _update(acct, lambda s: s.update(requests=((s.get("requests") or [])
                                                   + [{"text": a, "at": int(time.time())} for a in asked])[-REQUESTS_KEPT:]))
        log(f"🙋 Viewers asked for: {', '.join(asked)[:200]}")
    sent = 0
    for c in todo:
        d = drafts.get(c["id"])
        mark = "skip"
        if d and not d.skip and d.reply.strip() and ya.quota_used() + COMMENT_UNITS <= QUOTA_BUDGET:
            try:
                _post(f"{ya.API}/comments", {"part": "snippet"},
                      {"snippet": {"parentId": c["id"], "textOriginal": d.reply.strip()[:500]}})
                sent += 1
                mark = "sent"
            except RuntimeError as e:
                log(f"   ℹ️ Reply not sent: {str(e)[:120]}")
                mark = "failed"

        def fn(s, cid=c["id"], m=mark):
            s.setdefault("replied", {})[cid] = m
            if m == "sent":
                per = s.setdefault("replies_per_day", {})
                per[day] = per.get(day, 0) + 1
        _update(acct, fn)
    if sent:
        log(f"💬 Replied to {sent} comment(s).")
    return sent


def playlist_title(kind, fmt):
    return PLAYLISTS.get((kind, fmt)) or PLAYLISTS.get((kind, None)) or "Shorts"


def add_to_playlists(acct, kind, log=print):
    import youtube_account as ya
    st = load(acct)
    done = st.get("playlisted") or {}
    todo = [r for r in ya.uploads() if r.get("status") == "done" and r.get("video_id") and not r.get("elsewhere")
            and r["video_id"] not in done and r.get("created", 0) >= time.time() - COMMENT_DAYS * 86400]
    n = 0
    for r in todo:
        # A history series gets its own playlist, parts in upload order, so
        # YouTube plays part 2 after part 1.
        title = f"{r['series'][:120]} (series)" if r.get("series") else playlist_title(kind, r.get("format"))
        about = f"{r['series'][:120]}: every part, in order." if r.get("series") else f"{title}: new Shorts every day."
        lists = load(acct).get("playlists") or {}
        if ya.quota_used() + 2 * PLAYLIST_UNITS > QUOTA_BUDGET:
            break
        try:
            pid = lists.get(title)
            if not pid:
                got = _post(f"{ya.API}/playlists", {"part": "snippet,status"},
                            {"snippet": {"title": title, "description": about},
                             "status": {"privacyStatus": "public"}})
                pid = got["id"]
                _update(acct, lambda s: s.setdefault("playlists", {}).update({title: pid}))
            _post(f"{ya.API}/playlistItems", {"part": "snippet"},
                  {"snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": r["video_id"]}}})
            n += 1
            _update(acct, lambda s: s.setdefault("playlisted", {}).update({r["video_id"]: pid}))
        except RuntimeError as e:
            log(f"   ℹ️ Playlist add failed: {str(e)[:120]}")
            break
    if n:
        log(f"📃 Added {n} Short(s) to playlists.")
    return n


# ------------------------------------------------------------------ cross promotion

PROMO_LABEL = {"comedy": "comedy", "cricket": "cricket facts", "quiz": "daily quiz", "music": "new songs",
               "controversy": "controversies explained", "history": "history documentaries"}


def promo_line(others):
    """``others``: [(handle, kind)] of the owner's other connected channels."""
    parts = [f"{h} ({PROMO_LABEL.get(k, k)})" for h, k in others if h]
    return ("More from us: " + ", ".join(parts)) if parts else ""


def with_promo(description, others):
    import credits
    line = promo_line(others)
    return credits.insert(description, line) if line and line not in (description or "") else description
