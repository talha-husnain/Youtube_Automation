"""YouTube's own numbers beyond views (owner, 5-nov-2026: "find where viewers leave", "real search words per
video", "a weekly line on the 2027 targets", "thumbnail click-rate learning").

All calls run inside youtube_account.use(<channel account>) like every other per-channel call, with the scopes
the channels already granted (yt-analytics.readonly):

- ``retention(video_id)``: the audience-retention curve (YouTube Analytics, dimension elapsedVideoTimeRatio,
  metrics audienceWatchRatio + relativeRetentionPerformance, one video per request); ``curve_summary`` turns it
  into where viewers leave in seconds. It comes back empty for a video with very few views (22-oct-2026).
- ``search_terms``: what people typed into YouTube search before watching (insightTrafficSourceDetail with
  insightTrafficSourceType==YT_SEARCH, sort -views, at most 25 rows), per video or for the whole channel.
- ``ypp_numbers``: the YPP terms of 1-feb-2027 (Google blog, 11-aug-2026): to keep Shorts pay, 10M qualified
  Shorts views in 90 days; to join, 1,000 subscribers and 8,000 watch hours in 365 days or 20M Shorts views in 90
  days. "Qualified" views are closest to engagedViews (inference); watch hours are long-form minutes
  (creatorContentType VIDEO_ON_DEMAND + LIVE_STREAM).
- ``reach``: thumbnail impressions and click-through rate, the only API source of which is the YouTube Reporting
  API's reach reports (channel_reach_basic_a1, since 15-jan-2026, daily files 2-3 days late). It needs the
  "YouTube Reporting API" switched on in the Google Cloud project; ``reach`` says so when it is not.
"""
import csv
import io
import json
import os
import time
from datetime import datetime, timedelta, timezone

REPORTING_API = "https://youtubereporting.googleapis.com/v1"
REACH_REPORT = "channel_reach_basic_a1"
YPP_SHORTS_KEEP = 10_000_000          # qualified Shorts views in 90 days to keep Shorts revenue (existing partners)
YPP_SHORTS_JOIN = 20_000_000          # ...or to join with Shorts
YPP_HOURS_JOIN = 8_000                # long-form watch hours in 365 days to join
YPP_SUBS = 1_000
ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "state", "insights.json")


def _ya():
    import youtube_account
    return youtube_account


def _day(days_ago=0):
    return str((datetime.now(timezone.utc) - timedelta(days=days_ago)).date())


def _report(params):
    ya = _ya()
    res = ya._get(ya.ANALYTICS_API, {"ids": "channel==MINE", **params})
    names = [h.get("name") for h in res.get("columnHeaders") or []]
    return [dict(zip(names, row)) for row in res.get("rows") or []]


# ------------------------------------------------------------------ where viewers leave

def retention(video_id, since="2020-01-01"):
    """[(time ratio 0-1, audienceWatchRatio, relativeRetentionPerformance)] of one video, or []."""
    rows = _report({"startDate": since, "endDate": _day(), "dimensions": "elapsedVideoTimeRatio",
                    "metrics": "audienceWatchRatio,relativeRetentionPerformance", "filters": f"video=={video_id}"})
    out = []
    for r in rows:
        try:
            out.append((float(r["elapsedVideoTimeRatio"]), float(r["audienceWatchRatio"]),
                        float(r.get("relativeRetentionPerformance") or 0)))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out)


def curve_summary(curve, seconds, points=20, drops=3):
    """The curve for the dashboard and the lessons: {"points": [[s, %]...], "drops": [{"at", "to", "lost"}],
    "half_at", "end", "vs_others"} with times in seconds. A Short's watch ratio passes 100% when it loops."""
    if not curve or not seconds:
        return None
    pts = [(round(r * seconds, 1), round(w * 100, 1)) for r, w, _p in curve]
    step = max(1, len(pts) // points)
    out_pts = [list(p) for p in pts[::step]]
    if out_pts[-1] != list(pts[-1]):
        out_pts.append(list(pts[-1]))
    # The steepest falls over a short window (~3% of the video), not counting the loop's rise.
    win = max(1, len(pts) // 33)
    falls = []
    for k in range(len(pts) - win):
        lost = pts[k][1] - pts[k + win][1]
        if lost > 0:
            falls.append((lost, k))
    chosen = []
    for lost, k in sorted(falls, reverse=True):
        if all(abs(k - j) > win * 2 for _l, j in chosen):
            chosen.append((lost, k))
        if len(chosen) >= drops:
            break
    start = pts[0][1] or 100.0
    half = next((s for s, w in pts if w <= start / 2), None)
    rel = [p for _r, _w, p in curve if p]
    return {"points": out_pts,
            "drops": [{"at": pts[k][0], "to": pts[k + win][0], "lost": round(lost, 1)}
                      for lost, k in sorted(chosen, key=lambda c: c[1])],
            "half_at": half, "end": pts[-1][1],
            # relativeRetentionPerformance: 0.5 = as YouTube videos of that length usually do.
            "vs_others": round(sum(rel) / len(rel), 2) if rel else None}


def words_at(transcript_words, at, to, pad=0.6):
    """The words said in a drop (clip seconds), for "viewers left while it said ..."."""
    said = [w["word"].strip() for w in transcript_words or []
            if float(w.get("end", 0)) >= at - pad and float(w.get("start", 0)) <= to + pad]
    return " ".join(said)[:120]


def retention_lesson(rows, long=False):
    """One prompt line from a channel's summarised curves ("" with fewer than 3): when half the viewers are gone,
    and where the biggest drops sit."""
    curves = [r["curve"] for r in rows if (r.get("curve") or {}).get("points")]
    if len(curves) < 3:
        return ""
    halves = sorted(c["half_at"] for c in curves if c.get("half_at") is not None)
    first = sorted(c["drops"][0]["at"] for c in curves if c.get("drops"))
    parts = []
    if halves:
        parts.append(f"half the viewers are gone by {_mmss(halves[len(halves) // 2])} (median of {len(halves)})")
    if first:
        parts.append(f"the first big drop comes at {_mmss(first[len(first) // 2])}")
    ends = sorted(c["end"] for c in curves if c.get("end") is not None)
    if ends and not long:
        parts.append(f"{ends[len(ends) // 2]:.0f}% are still there at the end")
    if not parts:
        return ""
    return ("WHERE THIS CHANNEL'S VIEWERS LEAVE (YouTube's retention curves of its own videos): " + "; ".join(parts)
            + ". Make the moments before those times the strongest; never a slow start or a pause there.")


def _mmss(s):
    s = int(round(s or 0))
    return f"{s // 60}:{s % 60:02d}"


# ------------------------------------------------------------------ what viewers searched

def search_terms(video_id=None, days=90, limit=12):
    """[(term, views)] that found the channel (or one video) through YouTube search, most views first."""
    filters = "insightTrafficSourceType==YT_SEARCH" + (f";video=={video_id}" if video_id else "")
    rows = _report({"startDate": _day(days), "endDate": _day(), "dimensions": "insightTrafficSourceDetail",
                    "metrics": "views", "filters": filters, "sort": "-views", "maxResults": 25})
    out = []
    for r in rows:
        term = (r.get("insightTrafficSourceDetail") or "").strip()
        if term:
            out.append((term[:80], int(r.get("views") or 0)))
    return out[:limit]


def search_hint(terms):
    """The channel's real search words as a prompt line for titles and tags ("" without any)."""
    if not terms:
        return ""
    return ("Viewers found this channel on YouTube by searching: " + ", ".join(f'"{t}"' for t, _v in terms[:10])
            + ". Use these words in titles and tags where they truly fit the video.")


# ------------------------------------------------------------------ the 2027 YPP targets

def _kind(row):
    """creatorContentType as one spelling: the docs say SHORTS / VIDEO_ON_DEMAND, the API answers "shorts" (live,
    5-nov-2026) and presumably "videoOnDemand" / "liveStream"."""
    return str(row.get("creatorContentType") or "").replace("_", "").lower()


def ypp_numbers():
    """{"shorts_views", "shorts_engaged", "long_hours", "subscribers", "at"} of the connected channel."""
    ya = _ya()
    out = {"shorts_views": 0, "shorts_engaged": 0, "long_hours": 0.0, "subscribers": None, "at": int(time.time())}
    try:
        rows = _report({"startDate": _day(90), "endDate": _day(), "dimensions": "creatorContentType",
                        "metrics": "views,engagedViews"})
    except RuntimeError:
        rows = _report({"startDate": _day(90), "endDate": _day(), "dimensions": "creatorContentType",
                        "metrics": "views"})
    for r in rows:
        if _kind(r) == "shorts":
            out["shorts_views"] = int(r.get("views") or 0)
            out["shorts_engaged"] = int(r.get("engagedViews") or r.get("views") or 0)
    for r in _report({"startDate": _day(365), "endDate": _day(), "dimensions": "creatorContentType",
                      "metrics": "estimatedMinutesWatched"}):
        if _kind(r) in ("videoondemand", "livestream"):
            out["long_hours"] += float(r.get("estimatedMinutesWatched") or 0) / 60
    out["long_hours"] = round(out["long_hours"], 1)
    try:
        items = ya._get(f"{ya.API}/channels", {"part": "statistics", "mine": "true"}).get("items") or []
        stats = (items[0] if items else {}).get("statistics") or {}
        if not stats.get("hiddenSubscriberCount"):
            out["subscribers"] = int(stats.get("subscriberCount") or 0)
    except Exception:  # noqa: BLE001 — the rest still says a lot
        pass
    return out


def ypp_line(name, n):
    """The week report's line: how far the channel is from each 2027 target."""
    def pct(a, b):
        return f"{min(999, 100 * a / b):.1f}%" if b else "?"
    subs = n.get("subscribers")
    parts = [f"Shorts {n.get('shorts_engaged', 0):,} engaged views in 90 days "
             f"({pct(n.get('shorts_engaged', 0), YPP_SHORTS_KEEP)} of the 10M that keeps Shorts pay)",
             f"{n.get('long_hours', 0):,.{1 if n.get('long_hours', 0) < 10 else 0}f} long-video watch hours in a year "
             f"({pct(n.get('long_hours', 0), YPP_HOURS_JOIN)} of 8,000)"]
    if subs is not None:
        parts.append(f"{subs:,} subscribers ({pct(subs, YPP_SUBS)} of 1,000)")
    return f"  YPP 2027, {name}: " + "; ".join(parts) + "."


# ------------------------------------------------------------------ thumbnail impressions and click rate

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
        json.dump(data, f)
    os.replace(tmp, STATE_FILE)


def _auth():
    return {"Authorization": f"Bearer {_ya()._token()}"}


def _reporting(method, path, **kw):
    import httpx
    r = httpx.request(method, f"{REPORTING_API}{path}", headers=_auth(), timeout=60, **kw)
    if r.status_code >= 300:
        raise RuntimeError(_ya()._google_error(r))
    return r.json() if r.content else {}


def reach_job(key):
    """The channel's reach reporting job id (made once; reports start the day after)."""
    data = _load()
    jobs = data.setdefault("reach_jobs", {})
    if jobs.get(key):
        return jobs[key]
    have = [j for j in (_reporting("GET", "/jobs").get("jobs") or []) if j.get("reportTypeId") == REACH_REPORT]
    jid = have[0]["id"] if have else _reporting("POST", "/jobs", json={"reportTypeId": REACH_REPORT,
                                                                         "name": "Shortkaar thumbnail reach"})["id"]
    data = _load()
    data.setdefault("reach_jobs", {})[key] = jid
    _save(data)
    return jid


def parse_reach(text):
    """{video_id: [impressions, clicks]} from one reach report (CSV)."""
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        vid = row.get("video_id")
        try:
            imp = float(row.get("video_thumbnail_impressions") or 0)
            ctr = float(row.get("video_thumbnail_impressions_ctr") or 0)
        except ValueError:
            continue
        if not vid or imp <= 0:
            continue
        cur = out.setdefault(vid, [0.0, 0.0])
        cur[0] += imp
        cur[1] += imp * (ctr / 100 if ctr > 1 else ctr)       # the CTR may come as a share or a percent
    return out


def reach(key, now=None):
    """Totals per video since the job started ({video_id: {"impressions", "ctr"}}), reading the reports not read
    before. Raises RuntimeError with Google's reason (the API switched off in the project...)."""
    import httpx
    jid = reach_job(key)
    data = _load()
    seen = set(data.get("reach_seen", {}).get(key) or [])
    totals = data.get("reach_totals", {}).get(key) or {}
    reports = _reporting("GET", f"/jobs/{jid}/reports").get("reports") or []
    for rep in sorted(reports, key=lambda r: r.get("startTime") or ""):
        if rep.get("id") in seen or not rep.get("downloadUrl"):
            continue
        r = httpx.get(rep["downloadUrl"], headers=_auth(), timeout=120, follow_redirects=True)
        if r.status_code != 200:
            continue
        for vid, (imp, clicks) in parse_reach(r.text).items():
            t = totals.setdefault(vid, [0.0, 0.0])
            t[0] += imp
            t[1] += clicks
        seen.add(rep["id"])
    data = _load()
    data.setdefault("reach_seen", {})[key] = sorted(seen)[-400:]
    data.setdefault("reach_totals", {})[key] = totals
    _save(data)
    return {v: {"impressions": int(i), "ctr": round(100 * c / i, 2) if i else 0.0} for v, (i, c) in totals.items()}
