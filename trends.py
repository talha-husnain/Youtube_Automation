"""What is getting views on YouTube right now, per channel niche.

The idea planners already use Google Search for the news; this adds the
other half of "research the viral topics first": a YouTube search (yt-dlp,
no key, channel_tools.search) for short videos in the niche, uploaded this
week, sorted by views. The top titles go into the planner's prompt as topics
to learn from, never to copy. Cached 12 h so a day of planning costs a few
searches. Any failure means no hint, never no ideas.
"""
import json
import os
import time
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


def hint(kind, limit=15):
    """The prompt lines for a planner, or ""."""
    rows = top(kind, limit)
    if not rows:
        return ""
    return ("Short videos like these got the most views on YouTube this week (learn what people want to watch; "
            "never copy a title or a claim from them):\n" + "\n".join(f"{t} ({v:,} views)" for t, v in rows) + "\n")
