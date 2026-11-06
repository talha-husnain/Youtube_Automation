"""YouTube Data API reads for research (owner, 28-oct-2026: "find the most viral content in each niche").

Why not yt-dlp: from this laptop's network YouTube answers every per-video yt-dlp read with "Sign in to
confirm you're not a bot" (28-oct-2026, yt-dlp 2026.08.19 and 2026.10.26 alike), so the captions the
viral study read and the licence the comedy research checks came back empty and were read as "no
captions" / "not Creative Commons". The Data API is not bot-checked and its ``order=viewCount`` is a real
view-count sort (the website's "views" sort is "popularity" since Jan 2026).

Cost, from the project's 10,000 units a day (shared with every channel, counted by youtube_account.spend):
search.list 100 units, videos.list / channels.list / playlistItems.list 1 unit per call (50 ids a call).
``BUDGET`` caps what research spends in a Pacific day and nothing is read past ``CEILING`` used in all,
so uploads, captions and replies always keep their share.
"""
import os
import re
import threading
from datetime import datetime, timedelta, timezone

import youtube_account as ya

API = "https://www.googleapis.com/youtube/v3"
BUDGET = int(os.environ.get("RESEARCH_QUOTA") or 2500)     # research units a Pacific day
# Project units used before research stops: engage.py stops at 6,000 (QUOTA_BUDGET) and captions at
# 9,000, so research never takes the last 1,000 units of the day from comments and replies.
CEILING = int(os.environ.get("RESEARCH_CEILING") or 5000)
COST = {"search": 100, "videos": 1, "channels": 1, "playlistItems": 1, "commentThreads": 1}
_ISO = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
_lock = threading.Lock()
_spent = {}     # {pacific day: units}


class OutOfQuota(RuntimeError):
    pass


def seconds(iso):
    m = _ISO.fullmatch(iso or "")
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def spent_today():
    return _spent.get(ya._quota_day(), 0)


def _call(endpoint, params):
    units = COST[endpoint]
    with _lock:
        day = ya._quota_day()
        if _spent.get(day, 0) + units > BUDGET or ya.quota_used() + units > CEILING:
            raise OutOfQuota(f"research quota for today is used ({_spent.get(day, 0)} units)")
        _spent[day] = _spent.get(day, 0) + units
    ya.spend(units)
    return ya._get(f"{API}/{endpoint}", params)


def _row(v):
    sn, st, cd = v.get("snippet") or {}, v.get("statistics") or {}, v.get("contentDetails") or {}
    cid = sn.get("channelId") or ""
    return {"id": v["id"], "url": f"https://www.youtube.com/watch?v={v['id']}",
            "title": sn.get("title") or "", "channel": sn.get("channelTitle") or "", "channel_id": cid,
            "channel_url": f"https://www.youtube.com/channel/{cid}" if cid else "",
            "seconds": seconds(cd.get("duration")), "views": int(st.get("viewCount") or 0),
            "likes": int(st.get("likeCount") or 0), "comments": int(st.get("commentCount") or 0),
            "published": sn.get("publishedAt") or "", "licence": (v.get("status") or {}).get("license") or "",
            "language": sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or "",
            "thumbnail": f"https://i.ytimg.com/vi/{v['id']}/mqdefault.jpg"}


def videos(ids):
    """[row] for up to any number of ids, 50 per call (1 unit each); unknown or private ids are left out."""
    ids = [i for i in dict.fromkeys(ids) if i]
    out = []
    for n in range(0, len(ids), 50):
        got = _call("videos", {"part": "snippet,statistics,contentDetails,status", "id": ",".join(ids[n:n + 50]),
                               "maxResults": 50})
        out += [_row(v) for v in got.get("items") or []]
    return out


def search(query, days=30, duration="short", region="PK", language="hi", licence=None, limit=25):
    """Most viewed videos for ``query`` published in the last ``days`` (0 = any time), with their stats:
    101 units (search + one videos call). ``duration``: short (<4 min), medium (4-20), long (>20), any.
    ``licence="creativeCommon"`` keeps only Creative Commons videos."""
    params = {"part": "id", "q": (query or "")[:200], "type": "video", "order": "viewCount",
              "maxResults": max(1, min(50, limit)), "safeSearch": "moderate"}
    if duration in ("short", "medium", "long"):
        params["videoDuration"] = duration
    if days:
        params["publishedAfter"] = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if region:
        params["regionCode"] = region
    if language:
        params["relevanceLanguage"] = language
    if licence:
        params["videoLicense"] = licence
    got = _call("search", params)
    ids = [(i.get("id") or {}).get("videoId") for i in got.get("items") or []]
    rows = videos([i for i in ids if i])
    return sorted(rows, key=lambda r: r["views"], reverse=True)


def channel_uploads(channel_id, limit=30):
    """The channel's latest uploads with stats (2 units): its uploads playlist is UU + the id's tail."""
    if not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", channel_id or ""):
        return []
    got = _call("playlistItems", {"part": "contentDetails", "playlistId": "UU" + channel_id[2:],
                                  "maxResults": max(1, min(50, limit))})
    ids = [(i.get("contentDetails") or {}).get("videoId") for i in got.get("items") or []]
    return videos([i for i in ids if i])


def comments(vid, limit=60):
    """The video's most relevant top-level comments [{"text", "likes"}] (1 unit), [] when comments are off
    or the video is gone. Text only: the authors are never kept."""
    try:
        got = _call("commentThreads", {"part": "snippet", "videoId": vid, "order": "relevance",
                                       "maxResults": max(1, min(100, limit)), "textFormat": "plainText"})
    except OutOfQuota:
        raise
    except RuntimeError:
        return []
    out = []
    for item in got.get("items") or []:
        top = ((item.get("snippet") or {}).get("topLevelComment") or {}).get("snippet") or {}
        text = re.sub(r"\s+", " ", top.get("textDisplay") or top.get("textOriginal") or "").strip()
        if text:
            out.append({"text": text[:300], "likes": int(top.get("likeCount") or 0)})
    return out


def licences(ids):
    """{id: "creativeCommon" | "youtube"} in one call per 50 ids."""
    return {r["id"]: r["licence"] for r in videos(ids)}
