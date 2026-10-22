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
import contextvars
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.environ.get("YT_TOKEN_FILE") or os.path.join(ROOT, "output", ".youtube_token.json")
UPLOADS_FILE = os.path.join(ROOT, "output", ".uploads.json")
REDIRECT_URI = os.environ.get("YT_REDIRECT_URI") or "http://127.0.0.1:8000/api/youtube/callback"
DASHBOARD_URL = os.environ.get("YT_DASHBOARD_URL") or "http://localhost:5180"
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
# Comedy, Sports, Film, Music, Education, Music
CATEGORY = {"comedy": "23", "cricket": "17", "movies": "1", "songs": "10", "quiz": "27", "music": "10",
            "controversy": "24", "history": "27", "history_teaser": "27", "quran": "27"}
LONG_GENRES = ("history", "quran")    # 16:9 videos, not Shorts
THUMB_API = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
TITLE_MAX, DESCRIPTION_MAX, TAGS_MAX = 100, 4900, 480
_states = {}          # OAuth state -> (time, dashboard origin, account): a callback we did not start is refused
_lock = threading.Lock()
# Which channel the calls act on. None is the main channel (TOKEN_FILE and
# UPLOADS_FILE); my_channels.py runs its channels inside use(), each with its
# own token and uploads log, so every function below works on any of them.
_account = contextvars.ContextVar("youtube_account", default=None)


@contextmanager
def use(account):
    """Calls inside act on ``account`` ({"id", "token", "uploads"}); None = main."""
    tok = _account.set(account)
    try:
        yield
    finally:
        _account.reset(tok)


def token_file():
    a = _account.get()
    return a["token"] if a else TOKEN_FILE


def uploads_file():
    a = _account.get()
    return a["uploads"] if a else UPLOADS_FILE


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

def back_url(origin, query, tab="channel"):
    """Where the browser returns after Google: the dashboard it came from when
    that is a local address, else DASHBOARD_URL."""
    base = origin if _LOOPBACK.match(origin or "") else DASHBOARD_URL
    return f"{base}/#app?tab={tab}&{query}"


def auth_url(origin="", account=None, chain=None):
    """Google's sign-in page; ``account`` is the channel the token is for
    (None = main). The state remembers it, so one callback URL serves all.
    ``chain``: started by "connect all" (the ids skipped so far), so the
    callback goes on to the next channel."""
    if not configured():
        raise RuntimeError("Add YT_CLIENT_ID and YT_CLIENT_SECRET to .env first.")
    state = secrets.token_urlsafe(24)
    now = time.time()
    with _lock:
        for k in [k for k, v in _states.items() if now - v[0] > 900]:
            _states.pop(k, None)
        _states[state] = (now, origin if _LOOPBACK.match(origin or "") else "", account,
                          None if chain is None else tuple(chain))
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"], "redirect_uri": REDIRECT_URI,
        "response_type": "code", "scope": " ".join(SCOPES), "state": state,
        # offline + consent: Google sends a refresh token, so the connection
        # lasts. select_account: the picker shows every time, so a second
        # channel (a Brand Account) can be chosen instead of the last one.
        "access_type": "offline", "prompt": "select_account consent", "include_granted_scopes": "true"})


def origin_for(state):
    with _lock:
        got = _states.get(state or "")
    return got[1] if got else ""


def chain_for(state):
    """None, or the ids "connect all" skipped so far."""
    with _lock:
        got = _states.get(state or "")
    return got[3] if got and len(got) > 3 else None


def account_for(state):
    """The channel a sign-in was started for (None = main)."""
    with _lock:
        got = _states.get(state or "")
    return got[2] if got else None


def finish_connect(code, state, refuse=None):
    """Swap the code for a token and save it for the channel the sign-in was
    started for. ``refuse(me, account)`` may return a reason to drop it (the
    same YouTube channel already connected elsewhere)."""
    with _lock:
        started = _states.pop(state or "", None)
    if not started or time.time() - started[0] > 900:
        raise RuntimeError("This sign-in link expired. Press Connect again.")
    with use(started[2]):
        return _finish_connect(code, started[2], refuse)


def _finish_connect(code, account, refuse):
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
    tok["granted_at"] = int(time.time())
    path = token_file()
    old = _read(path, None)
    _write(path, tok)
    try:
        me = channel()
        why = refuse(me, account) if refuse else None
    except Exception:
        _restore(path, old)
        raise
    if why:
        _restore(path, old)
        raise RuntimeError(why)
    tok["channel"] = me
    _write(path, tok)
    return me


def _restore(path, old):
    """Put back the token a refused sign-in replaced. No revoke: when the same
    Google identity is connected elsewhere, revoking would cut that one too."""
    if old:
        _write(path, old)
        return
    try:
        os.remove(path)
    except OSError:
        pass


def disconnect(revoke=True):
    tok = _read(token_file(), None)
    if revoke and tok and tok.get("refresh_token"):
        try:
            httpx.post("https://oauth2.googleapis.com/revoke", data={"token": tok["refresh_token"]}, timeout=15)
        except httpx.HTTPError:
            pass
    try:
        os.remove(token_file())
    except OSError:
        pass


# app.py sets it: called once when Google says a connection is cancelled
# (the owner is told at once, not when an upload fails hours later).
on_dead = None


def _token():
    tok = _read(token_file(), None)
    if not tok:
        raise RuntimeError("YouTube is not connected.")
    if time.time() < tok.get("expires_at", 0):
        return tok["access_token"]
    r = httpx.post(TOKEN_URL, data={
        "client_id": os.environ.get("YT_CLIENT_ID", ""), "client_secret": os.environ.get("YT_CLIENT_SECRET", ""),
        "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"}, timeout=30)
    if r.status_code != 200:
        # invalid_grant: revoked, or a "Testing" consent screen's 7-day token expired.
        # Only that answer marks the connection dead: a network drop or a 5xx
        # is tried again on the next call.
        try:
            dead = r.json().get("error") == "invalid_grant"
        except ValueError:
            dead = False
        if dead and not tok.get("dead"):
            tok["dead"] = int(time.time())
            _write(token_file(), tok)
            if on_dead:
                try:
                    on_dead((tok.get("channel") or {}).get("title") or "A channel")
                except Exception:  # noqa: BLE001 — the mark is what matters
                    pass
        raise RuntimeError("YouTube connection expired. Connect again.")
    fresh = r.json()
    tok["access_token"] = fresh["access_token"]
    tok["expires_at"] = time.time() + int(fresh.get("expires_in", 3600)) - 60
    _write(token_file(), tok)
    return tok["access_token"]


def _get(url, params):
    r = httpx.get(url, params=params, headers={"Authorization": f"Bearer {_token()}"}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(_google_error(r))
    return r.json()


# The channel's own daily upload cap (reason uploadLimitExceeded). YouTube
# publishes no number: it is per channel, lower for new ones, and it let a
# 2-subscriber channel upload 10 on 14-oct-2026 before refusing the 11th.
UPLOAD_LIMIT_TEXT = "YouTube's daily upload limit for your channel is reached."


def upload_limit_hit(text):
    t = (text or "").lower()
    return "uploadlimitexceeded" in t or "exceeded the number of videos" in t or UPLOAD_LIMIT_TEXT.lower() in t


# The Google project's daily API quota (10,000 units, reset at midnight
# Pacific time) is shared by every channel's token. engage.py spends it on
# comments and playlists (50 units a write), so it is counted here, per
# Pacific day, in one file for the whole project. videos.insert has its own
# 100-a-day quota and is not counted.
QUOTA_FILE = os.path.join(ROOT, "output", ".yt_quota.json")
QUOTA_DAILY = 10_000


def _quota_day():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001 — no tz database: UTC-8 is close enough
        return (datetime.now(timezone.utc) - timedelta(hours=8)).strftime("%Y-%m-%d")


def spend(units):
    with _lock:
        data = _read(QUOTA_FILE, {})
        day = _quota_day()
        data = {day: int(data.get(day, 0)) + int(units)}
        _write(QUOTA_FILE, data)


def quota_used():
    return int(_read(QUOTA_FILE, {}).get(_quota_day(), 0))


def _google_error(r):
    try:
        err = r.json().get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else str(err)
        reasons = [e.get("reason", "") for e in (err.get("errors") or [])] if isinstance(err, dict) else []
    except ValueError:
        msg, reasons = r.text[:200], []
    if "uploadLimitExceeded" in reasons or upload_limit_hit(msg):
        return UPLOAD_LIMIT_TEXT
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


def long_uploads():
    """YouTube's own answer on videos over 15 minutes for this channel:
    "allowed" (verified), "eligible" or "disallowed" (channels.list status,
    1 unit). Lets a history video be capped before it is rendered, not
    refused after a 1 GB upload."""
    items = _get(f"{API}/channels", {"part": "status", "mine": "true"}).get("items") or []
    return ((items[0].get("status") or {}).get("longUploadsStatus") or "unknown") if items else "unknown"


def status():
    tok = _read(token_file(), None)
    # A connection Google cancelled reads as not connected: Today, the
    # reminders and "connect all channels" then pick it up.
    return {"configured": configured(), "connected": bool(tok and tok.get("refresh_token") and not tok.get("dead")),
            "channel": (tok or {}).get("channel"), "redirect_uri": REDIRECT_URI,
            "expires": refresh_expiry(tok), "granted_at": (tok or {}).get("granted_at") or 0}


def refresh_expiry(tok):
    """When the connection stops working, or None when it lasts. Google sends
    refresh_token_expires_in only while the OAuth consent screen is in
    "Testing", where the token dies 7 days after the sign-in (the owner's
    token carried 604799 s on 14-oct-2026). A token from before granted_at
    was saved dates from its channel's first upload at the latest."""
    if not tok or not tok.get("refresh_token_expires_in"):
        return None
    granted = tok.get("granted_at") or min((r.get("created", 0) for r in uploads() if r.get("created")),
                                           default=0)
    return int(granted + int(tok["refresh_token_expires_in"])) if granted else 0


# ------------------------------------------------------------------ upload

def _clean(text, limit):
    # YouTube rejects < and > in titles and descriptions.
    return (text or "").replace("<", "").replace(">", "").strip()[:limit]


def _clean_title(text):
    # A title is one line: YouTube kept "...reh gaye \n#shorts" as written on
    # 12 Punchline Bazaar Shorts and a cricket one (checked 18-oct-2026).
    return _clean(" ".join((text or "").split()), TITLE_MAX)


def _clean_description(text):
    # The description's limit is 5,000 BYTES (videos resource docs), not
    # characters: an emoji is 4 bytes and Urdu letters 2, so a 4,900-character
    # description can still be refused. Cut at a whole character.
    text = _clean(text, DESCRIPTION_MAX)
    raw = text.encode("utf-8")
    if len(raw) <= DESCRIPTION_MAX:
        return text
    return raw[:DESCRIPTION_MAX].decode("utf-8", "ignore").rstrip()


def _tags(tags):
    out, used = [], 0
    for t in tags or []:
        t = _clean(str(t).lstrip("#").replace(",", " "), 60)
        # The 500-character tag limit counts a tag with a space as quoted (+2).
        size = len(t) + 1 + (2 if " " in t else 0)
        if t and used + size <= TAGS_MAX:
            out.append(t)
            used += size
    return out


def uploads():
    # The upload log is what stops a Short going up twice: a damaged file
    # falls back to its hourly backup (safe_json). Tokens get no backup copy.
    import safe_json
    return safe_json.read(uploads_file(), [])


def _save_upload(row):
    with _lock:
        rows = uploads()
        rows = [r for r in rows if r["id"] != row["id"]] + [row]
        import safe_json
        safe_json.write(uploads_file(), rows[-500:])


def _mark_uploads(marks):
    """Set fields on rows in place, by row id ({id: {field: value or None}};
    None removes it), keeping the log's order."""
    import safe_json
    with _lock:
        rows = uploads()
        for r in rows:
            for k, v in (marks.get(r.get("id")) or {}).items():
                if v is None:
                    r.pop(k, None)
                else:
                    r[k] = v
        safe_json.write(uploads_file(), rows)


# A dropped connection mid-upload resumes where YouTube stopped receiving
# (resumable upload protocol: ask with "Content-Range: bytes */size", get 308
# and the Range received), instead of sending a 1 GB long video again from
# the start. This laptop's network drops for minutes at a time (15-oct-2026).
RESUME_WAITS = (5, 20, 60, 120, 300)


def _send_from(location, path, size, offset):
    with open(path, "rb") as f:
        f.seek(offset)

        # Streamed in 8 MB pieces: a long video is hundreds of MB. The
        # explicit Content-Length keeps httpx from switching to chunked.
        def pieces():
            while True:
                block = f.read(8 << 20)
                if not block:
                    return
                yield block
        headers = {"Content-Type": "video/mp4", "Content-Length": str(size - offset)}
        if offset:
            headers["Content-Range"] = f"bytes {offset}-{size - 1}/{size}"
        return httpx.put(location, content=pieces(), headers=headers, timeout=1800)


class _Busy(RuntimeError):
    """YouTube answered the status check with a 5xx or 429: ask again later."""


def _received(location, size):
    """(bytes YouTube has, or None when the upload is complete, final response)."""
    r = httpx.put(location, headers={"Content-Range": f"bytes */{size}", "Content-Length": "0"}, timeout=60)
    if r.status_code in (200, 201):
        return None, r
    if r.status_code == 429 or r.status_code >= 500:
        raise _Busy(_google_error(r))
    if r.status_code != 308:
        raise RuntimeError(_google_error(r))         # 404/410: the upload session expired
    got = r.headers.get("range") or ""
    return (int(got.rsplit("-", 1)[1]) + 1 if "-" in got else 0), r


def _send_resuming(location, path, size, sleep=None):
    sleep = sleep or time.sleep
    offset, last = 0, None
    for attempt in range(len(RESUME_WAITS) + 1):
        if offset is not None:
            try:
                done = _send_from(location, path, size, offset)
                if done.status_code in (200, 201) or not (done.status_code >= 500 or done.status_code in (308, 429)):
                    return done
                last = done
            except httpx.TransportError as e:
                last = e
        if attempt == len(RESUME_WAITS):
            break
        sleep(RESUME_WAITS[attempt])
        try:
            got, final = _received(location, size)
        except (httpx.TransportError, _Busy) as e:
            offset, last = None, e        # where YouTube stopped is unknown: send nothing, ask again
            continue
        if got is None:
            return final
        offset = got
    if isinstance(last, Exception):
        raise last
    return last


def upload(path, title, description, tags=(), genre="comedy", publish_at=None,
           privacy="public", ai_made=False, meta=None, localizations=None):
    """Upload one file. ``publish_at``: aware datetime to schedule it (the video
    is private until then, YouTube publishes it). ``localizations``: localize.build()
    output, translated titles/descriptions sent with the insert (no extra quota).
    Returns the uploads.json row."""
    row = {"id": secrets.token_hex(6), "file": os.path.basename(path), "title": _clean_title(title),
           "genre": genre, "publish_at": publish_at.astimezone(timezone.utc).isoformat() if publish_at else None,
           "asked": "scheduled" if publish_at else privacy, "status": "uploading",
           # Which YouTube channel it went to: a card reconnected to another
           # channel must not count it as its own (moved_uploads).
           "yt_channel": (status().get("channel") or {}).get("id"),
           "created": int(time.time()), **(meta or {})}
    _save_upload(row)
    body = {"snippet": {"title": row["title"] or "Short", "description": _clean_description(description),
                        "tags": _tags(tags), "categoryId": CATEGORY.get(genre, "24")},
            "status": {"privacyStatus": "private" if publish_at else privacy,
                       "selfDeclaredMadeForKids": False,
                       # YouTube's own label for realistic AI-made or altered media.
                       "containsSyntheticMedia": bool(ai_made)}}
    if publish_at:
        body["status"]["publishAt"] = row["publish_at"].replace("+00:00", "Z")
    parts = "snippet,status"
    if localizations:
        import localize
        body["snippet"]["defaultLanguage"] = localize.DEFAULT_LANGUAGE
        body["localizations"] = {k: {"title": _clean_title(v["title"]) or row["title"],
                                     "description": _clean_description(v["description"])}
                                 for k, v in localizations.items()}
        parts += ",localizations"
        row["localized"] = sorted(localizations)
    try:
        size = os.path.getsize(path)
        start = httpx.post(UPLOAD_API, params={"uploadType": "resumable", "part": parts},
                           headers={"Authorization": f"Bearer {_token()}",
                                    "Content-Type": "application/json; charset=UTF-8",
                                    "X-Upload-Content-Length": str(size),
                                    "X-Upload-Content-Type": "video/mp4"},
                           json=body, timeout=60)
        if start.status_code != 200 or "location" not in start.headers:
            raise RuntimeError(_google_error(start))
        done = _send_resuming(start.headers["location"], path, size)
        if done.status_code not in (200, 201):
            raise RuntimeError(_google_error(done))
        video = done.json()
        got = (video.get("status") or {}).get("privacyStatus")
        row.update(status="done", video_id=video["id"], privacy=got,
                   url=(f"https://youtube.com/watch?v={video['id']}" if genre in LONG_GENRES
                        else f"https://youtube.com/shorts/{video['id']}"),
                   locked_private=(got == "private" and not publish_at and privacy != "private"))
    except Exception as e:  # noqa: BLE001 — the row says what went wrong
        row.update(status="failed", error=str(e)[:300])
    _save_upload(row)
    return row


def set_thumbnail(video_id, path):
    """Our own thumbnail on a video (50 units). YouTube allows custom
    thumbnails only on a phone-verified channel (youtube.com/verify)."""
    with open(path, "rb") as f:
        data = f.read()
    spend(50)
    r = httpx.post(THUMB_API, params={"videoId": video_id, "uploadType": "media"},
                   headers={"Authorization": f"Bearer {_token()}", "Content-Type": "image/jpeg"},
                   content=data, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(_google_error(r))
    return True


def add_thumbnail(row, path):
    """set_thumbnail for an uploads.json row, which records how it went."""
    try:
        set_thumbnail(row["video_id"], path)
        row.update(thumbnail="set")
    except Exception as e:  # noqa: BLE001 — the video is up either way
        row.update(thumbnail="failed", thumbnail_error=str(e)[:200])
    _save_upload(row)
    return row


UPDATE_UNITS = 51          # videos.list (1) + videos.update (50)


def add_to_description(video_id, line):
    """Put ``line`` into an uploaded video's description, before its hashtag
    line. videos.update replaces the whole snippet, so the title, category
    and tags are sent back as they are. True when it was added."""
    import credits
    if quota_used() + UPDATE_UNITS > 9000:
        raise RuntimeError("the day's API quota is nearly used")
    items = _get(f"{API}/videos", {"part": "snippet", "id": video_id}).get("items") or []
    if not items:
        raise RuntimeError("that video is not on the channel any more")
    sn = items[0]["snippet"]
    old = sn.get("description") or ""
    if line in old:
        return False
    new = credits.insert(old, line)
    if len(new.encode("utf-8")) > DESCRIPTION_MAX:
        raise RuntimeError("the description has no room left")
    snippet = {k: sn[k] for k in ("title", "categoryId", "tags", "defaultLanguage", "defaultAudioLanguage")
               if sn.get(k)}
    spend(UPDATE_UNITS)
    r = httpx.put(f"{API}/videos", params={"part": "snippet"}, json={"id": video_id, "snippet": {
        **snippet, "description": new}}, headers={"Authorization": f"Bearer {_token()}"}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(_google_error(r))
    return True


CHANNEL_DESCRIPTION_MAX = 1000   # YouTube's limit for a channel's About text (characters)


def add_to_channel_about(line, if_empty=None):
    """Append ``line`` to the connected channel's About text (owner, 22-oct-2026: the OmniVoice credit);
    an empty About gets ``if_empty`` before it.
    channels.update with part=brandingSettings deletes every branding field it is not sent, so the whole
    brandingSettings object goes back with only the description changed. True when it was added."""
    if quota_used() + UPDATE_UNITS > 9000:
        raise RuntimeError("the day's API quota is nearly used")
    items = _get(f"{API}/channels", {"part": "brandingSettings", "mine": "true"}).get("items") or []
    if not items:
        raise RuntimeError("This Google account has no YouTube channel.")
    cid, branding = items[0]["id"], items[0].get("brandingSettings") or {}
    chan = dict(branding.get("channel") or {})
    old = chan.get("description") or ""
    if line in old:
        return False
    new = f"{old.rstrip()}\n\n{line}" if old.strip() else (f"{if_empty.strip()}\n\n{line}" if if_empty else line)
    if len(new) > CHANNEL_DESCRIPTION_MAX:
        raise RuntimeError("the channel's About text has no room left")
    chan["description"] = new
    spend(UPDATE_UNITS)
    r = httpx.put(f"{API}/channels", params={"part": "brandingSettings"},
                  json={"id": cid, "brandingSettings": {**branding, "channel": chan}},
                  headers={"Authorization": f"Bearer {_token()}"}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(_google_error(r))
    return True


def unschedule(video_id):
    """Keep a scheduled video private for good: it never goes public at its
    time (51 units). videos.update replaces the whole status, so every other
    field goes back as it is. Reversible in Studio; nothing is deleted.
    False when the video is not on this channel."""
    items = _get(f"{API}/videos", {"part": "status", "id": video_id}).get("items") or []
    if not items:
        return False
    st = {k: v for k, v in items[0]["status"].items()
          if k in ("embeddable", "license", "publicStatsViewable", "selfDeclaredMadeForKids",
                   "containsSyntheticMedia")}
    spend(UPDATE_UNITS)
    r = httpx.put(f"{API}/videos", params={"part": "status"},
                  json={"id": video_id, "status": {**st, "privacyStatus": "private"}},
                  headers={"Authorization": f"Bearer {_token()}"}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(_google_error(r))
    return not r.json().get("status", {}).get("publishAt")


CAPTIONS_API = "https://www.googleapis.com/upload/youtube/v3/captions"
CAPTION_UNITS = 400       # captions.insert (Google's quota calculator, 15-oct-2026)
CAPTION_NAMES = {"ur": "Urdu", "en": "English"}


def add_captions(row, path, language="ur", key="captions"):
    """Upload an SRT as the video's caption track (400 units, only when the
    day's quota has room); the uploads.json row records how it went. YouTube's
    own automatic captions handle Urdu badly; these are the script's words at
    the voice's times."""
    if quota_used() + CAPTION_UNITS > 9000:
        row.update({key: "skipped", f"{key}_error": "the day's API quota is nearly used"})
        _save_upload(row)
        return row
    try:
        with open(path, "rb") as f:
            srt = f.read()
        meta = {"snippet": {"videoId": row["video_id"], "language": language,
                            "name": CAPTION_NAMES.get(language, language), "isDraft": False}}
        boundary = "shortkaar" + secrets.token_hex(8)
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(meta)}\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
        body += srt + f"\r\n--{boundary}--\r\n".encode()
        spend(CAPTION_UNITS)
        r = httpx.post(CAPTIONS_API, params={"uploadType": "multipart", "part": "snippet"}, content=body,
                       headers={"Authorization": f"Bearer {_token()}",
                                "Content-Type": f"multipart/related; boundary={boundary}"}, timeout=120)
        if r.status_code != 200:
            raise RuntimeError(_google_error(r))
        row.update({key: "set"})
    except Exception as e:  # noqa: BLE001 — the video is up either way
        row.update({key: "failed", f"{key}_error": str(e)[:200]})
    _save_upload(row)
    return row


CLAIM_LOOKBACK_DAYS = 7


def claim_check():
    """Uploads of the last week that a copyright claim blocked: YouTube lists
    the blocked countries in contentDetails.regionRestriction (on 14-oct-2026
    the two claimed Shorts listed ~250, the clean eight none). Marks the
    uploads.json rows; returns the rows newly found blocked."""
    since = time.time() - CLAIM_LOOKBACK_DAYS * 86400
    rows = [r for r in uploads() if r.get("video_id") and r.get("status") == "done"
            and r.get("created", 0) >= since and not r.get("blocked")]
    found = []
    for k in range(0, len(rows), 50):
        part = rows[k:k + 50]
        items = _get(f"{API}/videos", {"part": "contentDetails,status",
                                       "id": ",".join(r["video_id"] for r in part)}).get("items") or []
        by_id = {v["id"]: v for v in items}
        for r in part:
            v = by_id.get(r["video_id"])
            if not v:
                continue
            blocked = ((v.get("contentDetails") or {}).get("regionRestriction") or {}).get("blocked") or []
            rejected = (v.get("status") or {}).get("uploadStatus") == "rejected"
            # Worldwide (the claim case seen) or in Pakistan, where the audience is.
            if len(blocked) >= 100 or "PK" in blocked or rejected:
                r.update(blocked=len(blocked) or True,
                         block_reason=(v.get("status") or {}).get("rejectionReason") or "copyright claim")
                _save_upload(r)
                found.append(r)
    return found


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


ANALYTICS_METRICS = "views,averageViewDuration,averageViewPercentage,shares,subscribersGained"


def video_analytics(days=90):
    """{video_id: {avg_percent, avg_seconds, shares, subs, a_views, engaged}} from YouTube Analytics.
    ``engaged`` is engagedViews: since 31-mar-2025 a Short's view counts the moment it starts, an engaged
    view only past its first seconds, so engaged/views is the share who did not swipe away. It came back
    per Short even at 1-60 views (22-oct-2026), where the retention curve came back empty."""
    end = datetime.now(timezone.utc).date()
    params = {"ids": "channel==MINE", "startDate": str(end - timedelta(days=days)), "endDate": str(end),
              "metrics": ANALYTICS_METRICS + ",engagedViews", "dimensions": "video", "sort": "-views",
              "maxResults": 200}
    try:
        res = _get(ANALYTICS_API, params)
    except Exception:  # noqa: BLE001 — a refused metric must not cost the rest
        res = _get(ANALYTICS_API, {**params, "metrics": ANALYTICS_METRICS})
    names = [h.get("name") for h in res.get("columnHeaders") or []] or (
        ["video"] + ANALYTICS_METRICS.split(","))
    out = {}
    for row in res.get("rows") or []:
        v = dict(zip(names, row))
        out[v["video"]] = {"avg_seconds": round(float(v.get("averageViewDuration") or 0), 1),
                           "avg_percent": round(float(v.get("averageViewPercentage") or 0), 1),
                           "shares": int(v.get("shares") or 0), "subs": int(v.get("subscribersGained") or 0),
                           "a_views": int(v.get("views") or 0),   # not "views": what_works merges these rows
                           **({"engaged": int(v["engagedViews"])} if v.get("engagedViews") is not None else {})}
    return out
