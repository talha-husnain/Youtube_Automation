"""Cross-posting our channels' Shorts to the owner's own Facebook Pages (as Reels) and Instagram
professional accounts (as Reels), through Meta's Graph API (owner, 22-oct-2026: "we can post on
Facebook and Instagram as well").

What the docs say (Graph API v26.0, researched 22-oct-2026):
- Facebook Login for Business with pages_show_list, pages_read_engagement, pages_manage_posts,
  instagram_basic, instagram_content_publish. An app in Development mode may ask these of people who
  have a role on the app, so the owner's own app needs no App Review for his own Pages.
- A long-lived user token (~60 days) gives Page tokens that do not expire; the Page token also drives
  the Instagram account linked to that Page.
- Instagram's resumable upload (a LOCAL file, no public URL: this laptop has none) exists only for
  Facebook Login for Business apps; Instagram Login needs a public video_url.
- Facebook Page Reels: 3-90 s, 9:16, 30 API posts a day; Instagram: 3 s-15 min, 50 a day (the doc says
  50 and 100 in two places). We keep DAILY_MAX far below both.
- is_ai_generated exists on both calls: every post sets it (our voices, songs and pictures are AI).
- Redirect: Meta wants HTTPS; http://localhost is allowed while the app is in Development (a 2018
  Meta note, not re-confirmed): META_REDIRECT overrides it.

Nothing is queued until the owner connects: a Short uploaded to YouTube is copied to
state/meta/outbox/ and posted at its YouTube publish time (``post_pass``), then the copy goes.
Tokens live in state/meta/token.json (gitignored) and never appear in a log line or an error.
"""
import json
import os
import secrets
import shutil
import subprocess
import threading
import time
import urllib.parse

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(ROOT, "state", "meta")
TOKEN_FILE = os.path.join(STATE_DIR, "token.json")
QUEUE_FILE = os.path.join(STATE_DIR, "queue.json")
OUTBOX = os.path.join(STATE_DIR, "outbox")
VERSION = "v26.0"
GRAPH = f"https://graph.facebook.com/{VERSION}"
RUPLOAD = "https://rupload.facebook.com"
DIALOG = f"https://www.facebook.com/{VERSION}/dialog/oauth"
SCOPES = "pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish"
FB_MAX_SECONDS = 90
DAILY_MAX = int(os.environ.get("META_DAILY_MAX") or 8)     # per account per platform; Meta allows 30 / 50
TRIES = 3
CAPTION_MAX = 2200
HASHTAGS_MAX = 5
POLL = 10
WAIT = 10 * 60
_lock = threading.RLock()
_states = {}


def redirect_uri():
    return os.environ.get("META_REDIRECT") or "http://localhost:8000/api/meta/callback"


def configured():
    return bool(os.environ.get("META_APP_ID") and os.environ.get("META_APP_SECRET"))


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _token():
    return _read(TOKEN_FILE, None)


def status():
    tok = _token() or {}
    return {"configured": configured(), "connected": bool(tok.get("pages")),
            "connected_at": tok.get("connected_at"), "user": tok.get("user_name"),
            "pages": [{"id": p["id"], "name": p.get("name"), "instagram": p.get("ig_username")}
                      for p in tok.get("pages") or []]}


def page(pid):
    return next((p for p in (_token() or {}).get("pages") or [] if p["id"] == pid), None)


# ------------------------------------------------------------------ connect

def auth_url(back=""):
    if not configured():
        raise RuntimeError("Add META_APP_ID and META_APP_SECRET to .env first.")
    state = secrets.token_urlsafe(24)
    now = time.time()
    with _lock:
        for k in [k for k, v in _states.items() if now - v[0] > 900]:
            _states.pop(k, None)
        _states[state] = (now, back)
    return DIALOG + "?" + urllib.parse.urlencode({
        "client_id": os.environ["META_APP_ID"], "redirect_uri": redirect_uri(), "state": state,
        "scope": SCOPES, "response_type": "code"})


def back_for(state):
    with _lock:
        got = _states.get(state)
    return got[1] if got else ""


def _err(r):
    """Meta's own message for a failed call; never the URL (it can carry a token)."""
    try:
        e = r.json().get("error") or {}
        return f"Meta said {r.status_code}: {e.get('message') or e}"[:300]
    except ValueError:
        return f"Meta said {r.status_code}"


def _json(r):
    if r.status_code != 200:
        raise RuntimeError(_err(r))
    return r.json()


def finish_connect(code, state, http=httpx):
    with _lock:
        if state not in _states:
            raise RuntimeError("This sign-in link is old; start again from the dashboard.")
        _states.pop(state, None)
    app = {"client_id": os.environ["META_APP_ID"], "client_secret": os.environ["META_APP_SECRET"]}
    short = _json(http.get(f"{GRAPH}/oauth/access_token", params={**app, "redirect_uri": redirect_uri(),
                                                                 "code": code}, timeout=30))["access_token"]
    long = _json(http.get(f"{GRAPH}/oauth/access_token", params={
        **app, "grant_type": "fb_exchange_token", "fb_exchange_token": short}, timeout=30))
    user_token = long["access_token"]
    me = _json(http.get(f"{GRAPH}/me", params={"fields": "id,name", "access_token": user_token}, timeout=30))
    got = _json(http.get(f"{GRAPH}/{me['id']}/accounts", params={
        "fields": "id,name,access_token,instagram_business_account{id,username}", "access_token": user_token,
        "limit": 100}, timeout=30))
    pages = []
    for p in got.get("data") or []:
        ig = p.get("instagram_business_account") or {}
        pages.append({"id": p["id"], "name": p.get("name"), "access_token": p["access_token"],
                      "ig_id": ig.get("id"), "ig_username": ig.get("username")})
    if not pages:
        raise RuntimeError("Facebook gave no Pages. Create a Page (and link Instagram to it), then connect again.")
    _write(TOKEN_FILE, {"user_id": me["id"], "user_name": me.get("name"), "user_token": user_token,
                        "user_expires": int(time.time()) + int(long.get("expires_in") or 60 * 86400),
                        "pages": pages, "connected_at": int(time.time())})
    return status()


def disconnect():
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)


# ------------------------------------------------------------------ queue

def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", path],
                         capture_output=True, text=True, timeout=60).stdout
    d = json.loads(out or "{}")
    s = (d.get("streams") or [{}])[0]
    return int(s.get("width") or 0), int(s.get("height") or 0), float((d.get("format") or {}).get("duration") or 0)


def caption_for(title, description):
    """Title, the description's first paragraph, a few hashtags: YouTube's links and follow lines do not
    belong on Facebook or Instagram."""
    paras = [p.strip() for p in (description or "").split("\n\n") if p.strip()]
    body = next((p for p in paras if "http" not in p and not p.startswith("#")), "")
    tags = []
    for p in paras:
        for w in p.split():
            if w.startswith("#") and len(w) > 2 and w.lower() not in {t.lower() for t in tags} \
                    and w.lower() != "#shorts":
                tags.append(w)
    text = "\n\n".join(x for x in (title.strip(), body[:600], " ".join(tags[:HASHTAGS_MAX])) if x)
    return text[:CAPTION_MAX]


def targets(ch):
    """(page dict, post to Facebook?, post to Instagram?) for a channel card, or None."""
    pid = (ch or {}).get("meta_page")
    p = page(pid) if pid else None
    if not p:
        return None
    fb, ig = bool(ch.get("meta_fb", True)), bool(ch.get("meta_ig", True)) and bool(p.get("ig_id"))
    return (p, fb, ig) if fb or ig else None


def enqueue(ch, row, path, publish_at=None, ai=True):
    """Queue an uploaded Short for the channel's Page and Instagram. None when nothing is set up, the
    file is gone, or it is not a vertical Short (long videos stay on YouTube)."""
    t = targets(ch)
    if not t or not path or not os.path.isfile(path):
        return None
    w, h, secs = _probe(path)
    if not (h > w and secs >= 3):
        return None
    p, fb, ig = t
    qid = f"{ch['id']}_{row.get('video_id') or row.get('id') or int(time.time())}"
    os.makedirs(OUTBOX, exist_ok=True)
    dst = os.path.join(OUTBOX, f"{qid}.mp4")
    shutil.copyfile(path, dst)
    at = int(publish_at.timestamp()) if hasattr(publish_at, "timestamp") else int(publish_at or time.time())
    item = {"id": qid, "channel": ch["id"], "page": p["id"], "file": dst, "seconds": round(secs, 2),
            "caption": caption_for(row.get("title") or "", row.get("description") or ""), "at": at, "ai": ai,
            "created": int(time.time()),
            "fb": {"status": "pending" if fb and secs <= FB_MAX_SECONDS else ("skipped" if fb else "off")},
            "ig": {"status": "pending" if ig else "off"}}
    with _lock:
        q = _read(QUEUE_FILE, [])
        q = [x for x in q if x["id"] != qid] + [item]
        _write(QUEUE_FILE, q)
    return item


def queue():
    return _read(QUEUE_FILE, [])


def _posted_today(q, page_id, platform, now):
    return sum(1 for x in q if x["page"] == page_id and x[platform].get("status") == "posted"
               and now - x[platform].get("at", 0) < 86400)


def post_pass(log=print, now=None, http=httpx, sleep=time.sleep):
    """Post every queued Short whose YouTube time has come. Returns how many went out."""
    now = now or time.time()
    with _lock:
        q = _read(QUEUE_FILE, [])
    sent = 0
    for item in q:
        if item["at"] > now:
            continue
        p = page(item["page"])
        for platform, fn in (("fb", post_facebook), ("ig", post_instagram)):
            st = item[platform]
            if st.get("status") != "pending":
                continue
            if not p or _posted_today(q, item["page"], platform, now) >= DAILY_MAX:
                continue
            try:
                got = fn(p, item["file"], item["caption"], item.get("ai", True), http=http, sleep=sleep)
                st.update(status="posted", id=got, at=int(now))
                sent += 1
                log(f"📤 {'Facebook' if platform == 'fb' else 'Instagram'}: posted '{item['caption'][:50]}'.")
            except Exception as e:  # noqa: BLE001 — tried again on the next pass, TRIES times
                st["tries"] = st.get("tries", 0) + 1
                st["error"] = str(e)[:200]
                if st["tries"] >= TRIES:
                    st["status"] = "failed"
                log(f"⚠️ {'Facebook' if platform == 'fb' else 'Instagram'}: {str(e)[:120]}")
    keep = []
    for item in q:
        if all(item[k].get("status") in ("posted", "failed", "skipped", "off") for k in ("fb", "ig")):
            if os.path.exists(item["file"]):
                os.remove(item["file"])
            item["done"] = int(now)
        if not item.get("done") or now - item["done"] < 30 * 86400:   # a month of history for the dashboard
            keep.append(item)
    with _lock:
        _write(QUEUE_FILE, keep)
    return sent


# ------------------------------------------------------------------ posting

def _upload(url, token, path, http):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        r = http.post(url, headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size),
                                    "Content-Type": "application/octet-stream"}, content=f.read(), timeout=600)
    got = _json(r)
    if got.get("success") is False:
        raise RuntimeError("Meta refused the upload: " + str(got.get("debug_info") or got)[:200])


def post_facebook(p, path, caption, ai=True, http=httpx, sleep=time.sleep):
    """A Page Reel, published at once. Returns the video id."""
    tok = p["access_token"]
    start = _json(http.post(f"{GRAPH}/{p['id']}/video_reels", data={"upload_phase": "start", "access_token": tok},
                            timeout=60))
    vid = start["video_id"]
    _upload(f"{RUPLOAD}/video-upload/{VERSION}/{vid}", tok, path, http)
    waited = 0
    while True:
        st = _json(http.get(f"{GRAPH}/{vid}", params={"fields": "status", "access_token": tok}, timeout=60))
        phase = (st.get("status") or {}).get("video_status")
        if phase in ("upload_complete", "processing", "ready"):
            break
        if phase in ("upload_failed", "expired", "error"):
            raise RuntimeError(f"Facebook could not take the video ({phase}).")
        if waited >= WAIT:
            raise RuntimeError("Facebook took too long to receive the video.")
        sleep(POLL)
        waited += POLL
    _json(http.post(f"{GRAPH}/{p['id']}/video_reels", data={
        "upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED", "description": caption,
        "is_ai_generated": "true" if ai else "false", "access_token": tok}, timeout=60))
    return vid


def post_instagram(p, path, caption, ai=True, http=httpx, sleep=time.sleep):
    """An Instagram Reel from the local file (resumable upload). Returns the media id."""
    if not p.get("ig_id"):
        raise RuntimeError("No Instagram account is linked to this Page.")
    tok = p["access_token"]
    box = _json(http.post(f"{GRAPH}/{p['ig_id']}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true",
        "is_ai_generated": "true" if ai else "false", "access_token": tok}, timeout=60))
    _upload(box.get("uri") or f"{RUPLOAD}/ig-api-upload/{VERSION}/{box['id']}", tok, path, http)
    waited = 0
    while True:
        st = _json(http.get(f"{GRAPH}/{box['id']}", params={"fields": "status_code,status", "access_token": tok},
                            timeout=60))
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram could not process the video ({st.get('status') or code}).")
        if waited >= WAIT:
            raise RuntimeError("Instagram took too long to process the video.")
        sleep(POLL * 3)
        waited += POLL * 3
    done = _json(http.post(f"{GRAPH}/{p['ig_id']}/media_publish", data={"creation_id": box["id"], "access_token": tok},
                           timeout=60))
    return done.get("id")
