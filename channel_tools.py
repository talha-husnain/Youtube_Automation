"""Find videos to clip and read YouTube channels, through yt-dlp with no API key.

- ``search``: YouTube search with the "Creative Commons" filter on, the same
  filter the YouTube website offers (the ``sp`` parameter is its protobuf).
  2-3 s per search, measured 8-oct-2026.
- ``licence``: what the video's own page says about reuse. yt-dlp reads it
  from the watch page: "Creative Commons Attribution license (reuse allowed)"
  on a CC video, nothing on the standard licence. ~10 s, so it is cached.
  A CC label proves only what the uploader claims: many CC results are
  re-uploads of stage shows by channels that do not own them.
- ``channel_videos`` / ``channel_shorts``: a channel's latest uploads (for
  Autopilot) and its Shorts with view counts (for the "what works" report).

Every channel link is rebuilt from its handle or id, so a pasted URL never
sends yt-dlp to another site.
"""
import base64
import re
import threading
import time
import urllib.parse

import yt_dlp

SORTS = {"relevance": None, "date": 2, "views": 3}
DURATIONS = {"any": None, "short": 1, "long": 2, "medium": 3}   # <4 min, >20 min, 4-20 min
DATES = {"any": None, "week": 3, "month": 4, "year": 5}
CC_LABEL = "creative commons"
LICENCE_TTL = 24 * 3600
_cache, _cache_lock = {}, threading.Lock()
_HANDLE = re.compile(r"^@?([A-Za-z0-9._-]{3,100})$")
_CHANNEL_ID = re.compile(r"(UC[A-Za-z0-9_-]{22})")
_URL_HANDLE = re.compile(r"youtube\.com/@([A-Za-z0-9._-]{3,100})")


def search_filter(cc=True, duration="any", date="any", sort="relevance"):
    """The ``sp`` value of a YouTube search: sort (field 1) + filters (field 2:
    upload date 1, type 2 = video, duration 3, Creative Commons 6)."""
    f = b""
    if DATES.get(date):
        f += bytes([0x08, DATES[date]])
    f += bytes([0x10, 0x01])
    if DURATIONS.get(duration):
        f += bytes([0x18, DURATIONS[duration]])
    if cc:
        f += bytes([0x30, 0x01])
    top = (bytes([0x08, SORTS[sort]]) if SORTS.get(sort) else b"") + bytes([0x12, len(f)]) + f
    return base64.b64encode(top).decode()


def _flat(url, limit):
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True,
            "playlistend": limit, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as y:
        return y.extract_info(url, download=False) or {}


def _video(e):
    vid = e.get("id")
    return {"id": vid, "url": f"https://www.youtube.com/watch?v={vid}",
            "title": e.get("title") or "", "channel": e.get("channel") or e.get("uploader") or "",
            "channel_url": e.get("channel_url") or "",
            "seconds": int(e["duration"]) if e.get("duration") else None,
            "views": e.get("view_count"),
            "thumbnail": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"}


def search(query, cc=True, duration="any", date="any", sort="relevance", limit=20):
    q = (query or "").strip()[:200]
    if not q:
        return []
    url = "https://www.youtube.com/results?" + urllib.parse.urlencode(
        {"search_query": q, "sp": search_filter(cc, duration, date, sort)})
    info = _flat(url, limit)
    return [_video(e) for e in (info.get("entries") or [])
            if e.get("id") and len(e["id"]) == 11 and e.get("live_status") not in ("is_live", "is_upcoming")]


def licence(url):
    """{"licence": "creative_commons" | "standard" | "unknown", "label", "title",
    "channel", "channel_url", "seconds"} for one video link."""
    import section_fetch
    import used_moments
    vid = used_moments.video_id(url)
    if not vid:
        return {"licence": "unknown", "label": "Not a YouTube video link"}
    with _cache_lock:
        hit = _cache.get(vid)
        if hit and time.time() - hit[0] < LICENCE_TTL:
            return hit[1]
    # The Data API first (1 unit, no bot check): from this laptop's network every yt-dlp read was
    # "Sign in to confirm you're not a bot" on 28-oct-2026 and each video read as "not CC".
    out = _api_licence(vid)
    if out:
        with _cache_lock:
            _cache[vid] = (time.time(), out)
        return out
    try:
        info = section_fetch.video_info(f"https://www.youtube.com/watch?v={vid}")
    except Exception as e:  # noqa: BLE001 — the check is advice, never a blocker
        return {"licence": "unknown", "label": f"Could not read the video ({type(e).__name__})"}
    label = info.get("license") or ""
    out = {"licence": "creative_commons" if CC_LABEL in label.lower() else "standard",
           "label": label or "Standard YouTube licence",
           "title": info.get("title") or "", "channel": info.get("channel") or info.get("uploader") or "",
           "channel_url": info.get("channel_url") or "",
           "seconds": int(info["duration"]) if info.get("duration") else None}
    with _cache_lock:
        _cache[vid] = (time.time(), out)
    return out


def _api_licence(vid):
    """licence()'s answer from the Data API, or None when it cannot answer (not connected, out of
    research quota, a private video)."""
    try:
        import yt_api
        rows = yt_api.videos([vid])
    except Exception:  # noqa: BLE001 — yt-dlp is the fallback
        return None
    if not rows or not rows[0].get("licence"):
        return None
    r = rows[0]
    cc = r["licence"] == "creativeCommon"
    return {"licence": "creative_commons" if cc else "standard",
            "label": "Creative Commons Attribution license (reuse allowed)" if cc else "Standard YouTube licence",
            "title": r["title"], "channel": r["channel"], "channel_url": r["channel_url"], "seconds": r["seconds"]}


def channel_url(channel):
    """Canonical https://www.youtube.com/@handle or /channel/UC... for what the
    user typed (a link, @handle or channel id); None if it is neither."""
    c = (channel or "").strip()
    on_youtube = bool(re.match(r"^(https?://)?(www\.|m\.)?youtube\.com/", c))
    m = _CHANNEL_ID.search(c)
    if m and (c == m.group(1) or (on_youtube and "/channel/" in c)):
        return f"https://www.youtube.com/channel/{m.group(1)}"
    m = _URL_HANDLE.search(c) if on_youtube else (_HANDLE.match(c) if "/" not in c else None)
    if m:
        return f"https://www.youtube.com/@{m.group(1)}"
    return None


def why_not(e):
    """A channel error in plain words. yt-dlp's text was shown as the class
    name only ("DownloadError"), which told the user nothing: @JanRambo is a
    real channel with no videos tab, a mistyped handle is a 404."""
    text = str(e).lower()
    if "does not have a videos tab" in text or "does not have a shorts tab" in text:
        return "That channel has no videos to clip. Check it is the creator's main channel."
    if "404" in text or "not found" in text or "does not exist" in text:
        return "No YouTube channel by that name. Check the @handle or paste the channel link."
    if "private" in text or "terminated" in text or "unavailable" in text:
        return "That channel is private or no longer available."
    return "YouTube did not answer. Try again in a minute."


def channel_videos(channel, limit=15):
    """Latest uploads, newest first: [{id, url, title, seconds, views, ...}]."""
    base = channel_url(channel)
    if not base:
        raise ValueError("Not a YouTube channel")
    info = _flat(base + "/videos", limit)
    name = info.get("channel") or info.get("uploader") or ""
    out = []
    for e in info.get("entries") or []:
        if e.get("id") and e.get("live_status") not in ("is_live", "is_upcoming"):
            v = _video(e)
            v["channel"] = v["channel"] or name
            out.append(v)
    return out


def channel_info(channel):
    base = channel_url(channel)
    if not base:
        raise ValueError("Not a YouTube channel")
    info = _flat(base + "/videos", 1)
    return {"url": info.get("channel_url") or base, "name": info.get("channel") or info.get("uploader") or "",
            "handle": info.get("uploader_id") or "", "followers": info.get("channel_follower_count")}


def channel_shorts(channel, limit=60):
    """The channel's Shorts, newest first: [{id, url, title, views}]."""
    base = channel_url(channel)
    if not base:
        raise ValueError("Not a YouTube channel")
    info = _flat(base + "/shorts", limit)
    return [{"id": e["id"], "url": f"https://www.youtube.com/shorts/{e['id']}",
             "title": e.get("title") or "", "views": e.get("view_count")}
            for e in info.get("entries") or [] if e.get("id")]
