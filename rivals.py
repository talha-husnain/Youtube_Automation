"""Similar channels: what is working for other comedy Shorts channels.

Their latest Shorts and view counts come from each channel's public Shorts
tab (channel_tools.channel_shorts, no API key). The numbers are ranked here;
Gemini only says what the winners have in common and turns it into ideas,
each with a YouTube search that finds reusable source videos for it (Find
videos). Their titles are never copied: ideas are angles, not their words.
State in ``output/.rivals.json``.
"""
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

from pydantic import BaseModel

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "output", ".rivals.json")
MAX_CHANNELS = 10
SHORTS_PER_CHANNEL = 30


class Idea(BaseModel):
    idea: str
    search: str


class Insights(BaseModel):
    summary: str
    patterns: List[str]
    ideas: List[Idea]


PROMPT = """You study similar YouTube Shorts channels for a Pakistani comedy Shorts channel ({handle})
that posts stand-up comedy clips with Roman Urdu titles. Below are their latest Shorts with views.

Write in short, plain English sentences (no em dashes):
- summary: 2 sentences: which channel and which kind of Short is winning right now.
- patterns: 3 to 5 things the most-viewed Shorts have in common (topics, situations, comedians'
  styles, title styles, length), each citing the numbers, e.g. "family fights: 4 of the top 10".
- ideas: 5 concrete Short ideas for {handle} built on those patterns, each with "search": a short
  YouTube search (2-5 words) that would find a full stand-up or podcast video to clip it from.
Never copy their titles word for word. Never suggest re-uploading their Shorts.

SHORTS (views | channel | title)
{rows}"""


def load():
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


def save_channels(channels):
    data = load()
    data["channels"] = [c for c in channels if isinstance(c, dict) and c.get("url")][:MAX_CHANNELS]
    _save(data)
    return data


def scan(channels, per_channel=SHORTS_PER_CHANNEL):
    """[{id, url, title, views, channel}] of every channel, most viewed first."""
    import channel_tools

    def one(ch):
        try:
            return [{**s, "channel": ch.get("name") or ch["url"]}
                    for s in channel_tools.channel_shorts(ch["url"], per_channel)]
        except Exception as e:  # noqa: BLE001 — one dead channel must not hide the rest
            print(f"   ℹ️ Could not read {ch.get('name') or ch['url']}: {type(e).__name__}")
            return []

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = [r for batch in pool.map(one, channels) for r in batch]
    return sorted((r for r in rows if r.get("views") is not None), key=lambda r: r["views"], reverse=True)


def per_channel(rows):
    out = {}
    for r in rows:
        out.setdefault(r["channel"], []).append(r["views"])
    return [{"channel": k, "shorts": len(v), "median": round(statistics.median(v)), "best": max(v)}
            for k, v in sorted(out.items(), key=lambda kv: -statistics.median(kv[1]))]


def build(client, model, handle):
    from google.genai import types
    data = load()
    channels = data.get("channels") or []
    if not channels:
        raise ValueError("Add at least one channel first.")
    rows = scan(channels)
    report = {"at": int(time.time()), "count": len(rows), "channels": per_channel(rows), "top": rows[:40]}
    if len(rows) >= 5:
        r = client.models.generate_content(
            model=model, contents=PROMPT.format(
                handle=handle or "this channel",
                rows="\n".join(f'{x["views"]} | {x["channel"]} | {x["title"][:100]}' for x in rows[:80])),
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=Insights,
                                               temperature=0.6))
        report.update(Insights.model_validate_json(r.text).model_dump())
    data["report"] = report
    _save(data)
    return report
