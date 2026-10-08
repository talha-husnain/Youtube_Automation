"""The user's own YouTube channel: connect with Google, upload / schedule Shorts,
read the channel's analytics. Self-host only (app.py refuses it in cloud mode).

Setup is one Google Cloud project the user owns: YouTube Data API v3 and
YouTube Analytics API enabled, an OAuth client of type "Web application" with
``REDIRECT_URI`` as its redirect URI, and its id / secret in ``.env`` as
``YT_CLIENT_ID`` / ``YT_CLIENT_SECRET``. The refresh token is kept in
``output/.youtube_token.json`` (gitignored, never sent anywhere but Google).

**Uploads stay private until the project passes YouTube's API audit**: every
video that videos.insert receives from an unaudited project created after
28-jul-2020 is locked as private, whatever ``privacyStatus`` asks for
(developers.google.com/youtube/v3/docs/videos/insert). Reading analytics
needs no audit. ``upload`` reports ``locked_private`` when YouTube kept a
video private that was asked to be public or scheduled.
"""
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.environ.get("YT_TOKEN_FILE") or os.path.join(ROOT, "output", ".youtube_token.json")
UPLOADS_FILE = os.path.join(ROOT, "output", ".uploads.json")
REDIRECT_URI = os.environ.get("YT_REDIRECT_URI") or "http://127.0.0.1:8000/api/youtube/callback"
DASHBOARD_URL = os.environ.get("YT_DASHBOARD_URL") or "http://localhost:5173"
_LOOPBACK = re.compile(r"^http://(localhost|127\.0\.0\.1|\[::1\]):\d{2,5}$")
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    # Replying to comments (comment_replies.py) needs the full-access scope.
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3/videos"
ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2/reports"
CATEGORY = {"comedy": "23", "cricket": "17", "movies": "1", "songs": "10"}   # Comedy, Sports, Film, Music
TITLE_MAX, DESCRIPTION_MAX, TAGS_MAX = 100, 4900, 480
_states = {}          # OAuth state -> (time, dashboard origin): a callback we did not start is refused
_lock = threading.Lock()


def configured():
    return bool(os.environ.get("YT_CLIENT_ID") and os.environ.get("YT_CLIENT_SECRET"))


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ------------------------------------------------------------------ connect

def back_url(origin, query):
    """Where the browser returns after Google: the dashboard it came from when
    that is a local address, else DASHBOARD_URL."""
    base = origin if _LOOPBACK.match(origin or "") else DASHBOARD_URL
    return f"{base}/#app?tab=channel&{query}"


def auth_url(origin=""):
    if not configured():
        raise RuntimeError("Add YT_CLIENT_ID and YT_CLIENT_SECRET to .env first.")
    state = secrets.token_urlsafe(24)
    now = time.time()
    with _lock:
        for k in [k for k, (t, _o) in _states.items() if now - t > 900]:
            _states.pop(k, None)
        _states[state] = (now, origin if _LOOPBACK.match(origin or "") else "")
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"], "redirect_uri": REDIRECT_URI,
        "response_type": "code", "scope": " ".join(SCOPES), "state": state,
        # offline + consent: Google sends a refresh token, so the connection lasts.
        "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"})


def origin_for(state):
    with _lock:
        got = _states.get(state or "")
    return got[1] if got else ""


def finish_connect(code, state):
    with _lock:
        started = _states.pop(state or "", None)
    if not started or time.time() - started[0] > 900:
        raise RuntimeError("This sign-in link expired. Press Connect again.")
    r = httpx.post(TOKEN_URL, data={
        "code": code, "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"], "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Google refused the sign-in ({r.status_code}).")
    tok = r.json()
    if not tok.get("refresh_token"):
        raise RuntimeError("Google sent no refresh token. Remove the app's access in your Google "
                           "account (Security > Third-party access) and connect again.")
    tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 60
    _write(TOKEN_FILE, tok)
    me = channel()
    tok["channel"] = me
    _write(TOKEN_FILE, tok)
    return me


def disconnect():
    tok = _read(TOKEN_FILE, None)
    if tok and tok.get("refresh_token"):
        try:
            httpx.post("https://oauth2.googleapis.com/revoke", data={"token": tok["refresh_token"]}, timeout=15)
        except httpx.HTTPError:
            pass
    try:
        os.remove(TOKEN_FILE)
    except OSError:
        pass


def _token():
    tok = _read(TOKEN_FILE, None)
    if not tok:
        raise RuntimeError("YouTube is not connected.")
    if time.time() < tok.get("expires_at", 0):
        return tok["access_token"]
    r = httpx.post(TOKEN_URL, data={
        "client_id": os.environ.get("YT_CLIENT_ID", ""), "client_secret": os.environ.get("YT_CLIENT_SECRET", ""),
        "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"}, timeout=30)
    if r.status_code != 200:
        # invalid_grant: revoked, or a "Testing" consent screen's 7-day token expired.
        raise RuntimeError("YouTube connection expired. Connect again.")
    fresh = r.json()
    tok["access_token"] = fresh["access_token"]
    tok["expires_at"] = time.time() + int(fresh.get("expires_in", 3600)) - 60
    _write(TOKEN_FILE, tok)
    return tok["access_token"]


def _get(url, params):
    r = httpx.get(url, params=params, headers={"Authorization": f"Bearer {_token()}"}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(_google_error(r))
    return r.json()


def _google_error(r):
    try:
        err = r.json().get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else str(err)
    except ValueError:
        msg = r.text[:200]
    return f"YouTube said {r.status_code}: {msg}"


def channel():
    items = _get(f"{API}/channels", {"part": "snippet,statistics,contentDetails", "mine": "true"}).get("items") or []
    if not items:
        raise RuntimeError("This Google account has no YouTube channel.")
    c = items[0]
    return {"id": c["id"], "title": c["snippet"]["title"],
            "handle": c["snippet"].get("customUrl") or "",
            "thumbnail": ((c["snippet"].get("thumbnails") or {}).get("default") or {}).get("url"),
            "subscribers": int(c.get("statistics", {}).get("subscriberCount") or 0),
            "uploads_playlist": c["contentDetails"]["relatedPlaylists"]["uploads"]}


def status():
    tok = _read(TOKEN_FILE, None)
    return {"configured": configured(), "connected": bool(tok and tok.get("refresh_token")),
            "channel": (tok or {}).get("channel"), "redirect_uri": REDIRECT_URI}


# ------------------------------------------------------------------ upload

def _clean(text, limit):
    # YouTube rejects < and > in titles and descriptions.
    return (text or "").replace("<", "").replace(">", "").strip()[:limit]


def _tags(tags):
    out, used = [], 0
    for t in tags or []:
        t = _clean(str(t).lstrip("#"), 60)
        if t and used + len(t) + 1 <= TAGS_MAX:
            out.append(t)
            used += len(t) + 1
    return out


def uploads():
    return _read(UPLOADS_FILE, [])


def _save_upload(row):
    with _lock:
        rows = uploads()
        rows = [r for r in rows if r["id"] != row["id"]] + [row]
        _write(UPLOADS_FILE, rows[-500:])


def upload(path, title, description, tags=(), genre="comedy", publish_at=None,
           privacy="public", ai_made=False, meta=None):
    """Upload one file. ``publish_at``: aware datetime to schedule it (the video
    is private until then, YouTube publishes it). Returns the uploads.json row."""
    row = {"id": secrets.token_hex(6), "file": os.path.basename(path), "title": _clean(title, TITLE_MAX),
           "genre": genre, "publish_at": publish_at.astimezone(timezone.utc).isoformat() if publish_at else None,
           "asked": "scheduled" if publish_at else privacy, "status": "uploading",
           "created": int(time.time()), **(meta or {})}
    _save_upload(row)
    body = {"snippet": {"title": row["title"] or "Short", "description": _clean(description, DESCRIPTION_MAX),
                        "tags": _tags(tags), "categoryId": CATEGORY.get(genre, "24")},
            "status": {"privacyStatus": "private" if publish_at else privacy,
                       "selfDeclaredMadeForKids": False,
                       # YouTube's own label for realistic AI-made or altered media.
                       "containsSyntheticMedia": bool(ai_made)}}
    if publish_at:
        body["status"]["publishAt"] = row["publish_at"].replace("+00:00", "Z")
    try:
        size = os.path.getsize(path)
        start = httpx.post(UPLOAD_API, params={"uploadType": "resumable", "part": "snippet,status"},
                           headers={"Authorization": f"Bearer {_token()}",
                                    "Content-Type": "application/json; charset=UTF-8",
                                    "X-Upload-Content-Length": str(size),
                                    "X-Upload-Content-Type": "video/mp4"},
                           json=body, timeout=60)
        if start.status_code != 200 or "location" not in start.headers:
            raise RuntimeError(_google_error(start))
        with open(path, "rb") as f:
            done = httpx.put(start.headers["location"], content=f.read(),
                             headers={"Content-Type": "video/mp4"}, timeout=1800)
        if done.status_code not in (200, 201):
            raise RuntimeError(_google_error(done))
        video = done.json()
        got = (video.get("status") or {}).get("privacyStatus")
        row.update(status="done", video_id=video["id"], privacy=got,
                   url=f"https://youtube.com/shorts/{video['id']}",
                   locked_private=(got == "private" and not publish_at and privacy != "private"))
    except Exception as e:  # noqa: BLE001 — the row says what went wrong
        row.update(status="failed", error=str(e)[:300])
    _save_upload(row)
    return row


def upload_and_mark(*args, **kwargs):
    """upload(), then take the Short out of Ready to post once YouTube has it,
    so its posting time is not handed out twice."""
    row = upload(*args, **kwargs)
    meta = kwargs.get("meta") or (args[8] if len(args) > 8 else None) or {}
    if row.get("status") == "done" and meta.get("job_id") is not None:
        import post_queue
        post_queue.update(post_queue.item_id(meta["job_id"], meta["clip_index"]), status="posted",
                          youtube_id=row.get("video_id"))
    return row


def next_slots(times, count=1, tz=None, after=None):
    """The next ``count`` free posting times: ``times`` is ["13:00", "19:00"]
    in local time; a slot an earlier upload already holds is skipped."""
    tz = tz or datetime.now().astimezone().tzinfo
    taken = {r.get("publish_at") for r in uploads() if r.get("status") != "failed"}
    day = (after or datetime.now(tz) + timedelta(minutes=20))
    out, d = [], 0
    clock = sorted(t for t in (times or ["13:00", "19:00"]) if len(t) == 5 and t[2] == ":")
    while len(out) < count and d < 120:
        date = (day + timedelta(days=d)).date()
        for t in clock:
            slot = datetime(date.year, date.month, date.day, int(t[:2]), int(t[3:]), tzinfo=tz)
            iso = slot.astimezone(timezone.utc).isoformat()
            if slot > day and iso not in taken and slot not in out:
                out.append(slot)
                if len(out) == count:
                    break
        d += 1
    return out


def reply(comment_id, text):
    """Answer one comment as the channel (comments.insert)."""
    r = httpx.post(f"{API}/comments", params={"part": "snippet"},
                   headers={"Authorization": f"Bearer {_token()}"},
                   json={"snippet": {"parentId": comment_id, "textOriginal": text}}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(_google_error(r))
    return r.json().get("id")


# ------------------------------------------------------------------ analytics

def recent_videos(limit=100):
    """The channel's latest uploads with public numbers and length."""
    me = channel()
    ids, page = [], None
    while len(ids) < limit:
        p = {"part": "contentDetails", "playlistId": me["uploads_playlist"], "maxResults": 50}
        if page:
            p["pageToken"] = page
        res = _get(f"{API}/playlistItems", p)
        ids += [i["contentDetails"]["videoId"] for i in res.get("items") or []]
        page = res.get("nextPageToken")
        if not page:
            break
    rows = []
    for k in range(0, len(ids[:limit]), 50):
        res = _get(f"{API}/videos", {"part": "snippet,statistics,contentDetails",
                                     "id": ",".join(ids[k:k + 50])})
        for v in res.get("items") or []:
            st = v.get("statistics") or {}
            rows.append({"id": v["id"], "title": v["snippet"]["title"],
                         "published": v["snippet"]["publishedAt"],
                         "seconds": _iso_seconds(v["contentDetails"].get("duration", "")),
                         "views": int(st.get("viewCount") or 0), "likes": int(st.get("likeCount") or 0),
                         "comments": int(st.get("commentCount") or 0)})
    return rows


def _iso_seconds(d):
    import re
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    dd, h, mi, s = (int(x or 0) for x in m.groups())
    return dd * 86400 + h * 3600 + mi * 60 + s


def video_analytics(days=90):
    """{video_id: {avg_percent, avg_seconds, shares, subs}} from YouTube Analytics."""
    end = datetime.now(timezone.utc).date()
    res = _get(ANALYTICS_API, {
        "ids": "channel==MINE", "startDate": str(end - timedelta(days=days)), "endDate": str(end),
        "metrics": "views,averageViewDuration,averageViewPercentage,shares,subscribersGained",
        "dimensions": "video", "sort": "-views", "maxResults": 200})
    out = {}
    for row in res.get("rows") or []:
        vid, views, secs, pct, shares, subs = row
        out[vid] = {"avg_seconds": round(float(secs), 1), "avg_percent": round(float(pct), 1),
                    "shares": int(shares), "subs": int(subs)}
    return out
