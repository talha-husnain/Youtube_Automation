"""What is getting views on YouTube right now, per channel niche.

The idea planners already use Google Search for the news; this adds the
other half of "research the viral topics first": a YouTube search (yt-dlp,
no key, channel_tools.search) for short videos in the niche, uploaded this
week, sorted by views. The top titles go into the planner's prompt as topics
to learn from, never to copy. Cached 12 h so a day of planning costs a few
searches. Any failure means no hint, never no ideas.
"""
import html
import json
import os
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(ROOT, "output", ".trends.json")
CACHE_SECONDS = 12 * 3600
QUERIES = {
    "cricket": ["cricket facts shorts", "cricket records shorts", "cricket shorts urdu hindi", "babar azam shorts",
                "virat kohli shorts"],
    "controversy": ["controversy explained shorts", "celebrity controversy shorts hindi",
                    "pakistani celebrity controversy shorts", "cricketer controversy shorts"],
}


def _read():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def top(kind, limit=20):
    """[(title, views)] of this week's most viewed short videos for ``kind``."""
    queries = QUERIES.get(kind)
    if not queries or os.environ.get("TRENDS", "1") == "0":
        return []
    hit = _read().get(kind)
    if hit and time.time() - hit.get("at", 0) < CACHE_SECONDS:
        return [tuple(r) for r in hit["rows"]][:limit]
    import channel_tools

    def one(q):
        try:
            return channel_tools.search(q, cc=False, duration="short", date="week", sort="views", limit=12)
        except Exception:  # noqa: BLE001 — a hint, never needed
            return []
    with ThreadPoolExecutor(max_workers=3) as ex:
        found = [v for got in ex.map(one, queries) for v in got]
    seen, rows = set(), []
    for v in sorted(found, key=lambda v: v.get("views") or 0, reverse=True):
        if v["id"] in seen or not v.get("views"):
            continue
        seen.add(v["id"])
        rows.append((v["title"][:100], int(v["views"])))
    if rows:
        data = _read()
        data[kind] = {"at": int(time.time()), "rows": rows[:40]}
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)
    return rows[:limit]


RSS = "https://trends.google.com/trending/rss?geo={geo}"
RSS_FILE = os.path.join(ROOT, "output", ".trends_rss.json")
RSS_SECONDS = 3600
HT = "{https://trends.google.com/trending/rss}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Shortkaar/1.0"


def searches(geos=("PK", "IN"), get=None, now=None):
    """What people in Pakistan and India search on Google right now, with the
    day's headlines: Google Trends' daily-trends RSS (free, no key). Tested
    22-oct-2026: "tri series 200+" with the PCB, BBC and Cricinfo stories of
    Pakistan's win. [{"geo", "query", "traffic", "news": [headline]}], cached
    an hour; any failure means no rows."""
    if os.environ.get("TRENDS", "1") == "0":
        return []
    now = now or time.time()
    try:
        with open(RSS_FILE, encoding="utf-8") as f:
            cached = json.load(f)
        if now - cached.get("at", 0) < RSS_SECONDS:
            return cached.get("rows") or []
    except (OSError, ValueError):
        pass
    import httpx
    get = get or httpx.get
    rows = []
    for geo in geos:
        try:
            root = ET.fromstring(get(RSS.format(geo=geo), timeout=15, headers={"User-Agent": UA}).text)
        except Exception:  # noqa: BLE001 — one country's feed failing leaves the other
            continue
        for item in root.iter("item"):
            news = [html.unescape(n.findtext(f"{HT}news_item_title") or "").strip()
                    for n in item.findall(f"{HT}news_item")][:2]
            rows.append({"geo": geo, "query": html.unescape(item.findtext("title") or "").strip(),
                         "traffic": (item.findtext(f"{HT}approx_traffic") or "").strip(),
                         "news": [n for n in news if n]})
    rows = [r for r in rows if r["query"]]
    if rows:
        os.makedirs(os.path.dirname(RSS_FILE), exist_ok=True)
        with open(RSS_FILE, "w", encoding="utf-8") as f:
            json.dump({"at": int(now), "rows": rows}, f, ensure_ascii=False)
    return rows


def searches_hint(limit=24):
    """The prompt lines for a planner, or "": today's Google searches with
    their headlines, and the rule that a same-day story comes first. The
    Shorts that broke out in our niches were made the day of the event
    (cricket results, celebrity stories; research 22-oct-2026)."""
    rows = searches()[:limit]
    if not rows:
        return ""
    lines = [f"- {r['query']} ({r['geo']}, {r['traffic'] or '?'} searches)"
             + (f": {' / '.join(r['news'])}" if r["news"] else "") for r in rows]
    return ("TRENDING ON GOOGLE RIGHT NOW in Pakistan (PK) and India (IN), with today's headlines. If one of "
            "these is a story for this channel from the last 24 hours, make it the FIRST idea: same-day stories "
            "are what get views. Ignore the ones that do not fit the channel or its rules.\n"
            + "\n".join(lines) + "\n")


def hint(kind, limit=15):
    """The prompt lines for a planner, or ""."""
    rows = top(kind, limit)
    if not rows:
        return ""
    return ("Short videos like these got the most views on YouTube this week (learn what people want to watch; "
            "never copy a title or a claim from them):\n" + "\n".join(f"{t} ({v:,} views)" for t, v in rows) + "\n")
