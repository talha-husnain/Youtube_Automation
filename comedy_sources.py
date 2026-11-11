"""Comedians whose own channels post Creative Commons videos: Punchline Bazaar's main source.

Owner, 11-nov-2026: "you are getting the video clips of the creator that nobody watches". Five fixed
Creative Commons searches kept handing back the same few small channels (THARKI Part 1 three days
running, a 2012 Qatar mushaira, Jan Rambo: 28 Shorts with a median of 0 views), while comedians with
millions of views post their own sets under Creative Commons (searches of 11-nov-2026: Rajat Chauhan's
crowd work 1.4-2.5M views a video, Naman Jain 3.2M, Daahab Chishti 1.1M). A channel is not all Creative
Commons (Rajat Chauhan's 7.2M "Parents on Shaadi.com" is not), so every video's own licence counts.

- remember(videos): a research find the vet kept (the creator's own comedy) makes its channel a known
  creator; SEEDS are the ones found by hand on 11-nov-2026.
- videos(log): each day the CREATORS_PER_DAY best known creators not read for CREATOR_REST are read
  whole through the Data API (uploads with views and licence, 2 units per 50 videos) and their
  Creative Commons videos join the day's candidates (autopilot_local.research_videos).
- queries_today(): QUERIES_PER_DAY searches of QUERY_BANK, a different slice each day, so new creators
  keep turning up.

State: state/comedy_creators.json {channel_url: {name, kept, best_views, read, cc, seed}}.
"""
import json
import os
import re
import time
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "state", "comedy_creators.json")
CREATORS_PER_DAY = 4
CREATOR_REST = 5 * 86400
UPLOADS_PER_CREATOR = 150
MAX_CREATORS = 80
QUERIES_PER_DAY = 4
# Searches that reach comedians with real audiences (11-nov-2026: "crowd work comedy" found Rajat Chauhan's
# 1.4-2.5M sets, "hindi stand up comedy" Naman Jain and Daahab Chishti, "mazahiya mushaira" Siasat Daily).
QUERY_BANK = ["crowd work comedy", "hindi stand up comedy", "stand up comedy crowd work hindi",
              "mazahiya mushaira", "punjabi comedy", "desi stand up comedy", "pakistani stand up comedian",
              "funny mushaira", "stand up comedy hindi audience", "comedy podcast hindi",
              "urdu comedy show", "roast comedy hindi"]
SEEDS = {
    "https://www.youtube.com/channel/UCxMDGaw3tMLHdH-ZUU4173A": "Rajat Chauhan",
    "https://www.youtube.com/channel/UCaiFduMjCfB7ILzL59nrHrw": "Naman Jain",
    "https://www.youtube.com/channel/UC-jIMF1EleqyK77TvFjVPCA": "Daahab Chishti",
    "https://www.youtube.com/channel/UC2livp-9nXvAhWUXdv08M6w": "Aakash Deep",
    "https://www.youtube.com/channel/UC8lVvurdhqV2-cTizQjh4wQ": "Siasat Daily",
    "https://www.youtube.com/channel/UC_XSbdzsl5mPgIoP5YawTeA": "Nav Lehal",
}
_CHANNEL_ID = re.compile(r"/channel/(UC[A-Za-z0-9_-]{22})")


def _load():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def _save(data):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)


def creators():
    """Known creators, the seeds included: {channel_url: row}."""
    data = _load()
    for url, name in SEEDS.items():
        data.setdefault(url, {"name": name, "kept": 0, "best_views": 0, "read": 0, "cc": 0, "seed": True})
    return data


def queries_today(today=None):
    """QUERIES_PER_DAY searches of the bank, a different slice each day."""
    day = (today or date.today()).toordinal()
    start = (day * QUERIES_PER_DAY) % len(QUERY_BANK)
    return [QUERY_BANK[(start + i) % len(QUERY_BANK)] for i in range(QUERIES_PER_DAY)]


def remember(kept, blocked=lambda url: False):
    """Every channel of a vetted find becomes (or stays) a known creator."""
    data = creators()
    for v in kept:
        url = v.get("channel_url") or ""
        if not _CHANNEL_ID.search(url) or blocked(url):
            continue
        row = data.setdefault(url, {"name": v.get("channel") or "", "kept": 0, "best_views": 0, "read": 0, "cc": 0})
        row["name"] = row.get("name") or v.get("channel") or ""
        row["kept"] = row.get("kept", 0) + 1
        row["best_views"] = max(row.get("best_views", 0), int(v.get("views") or 0))
    if len(data) > MAX_CREATORS:
        # The weakest non-seed creators go first.
        weak = sorted((u for u, r in data.items() if not r.get("seed")),
                      key=lambda u: (data[u].get("best_views", 0), data[u].get("kept", 0)))
        for u in weak[:len(data) - MAX_CREATORS]:
            data.pop(u)
    _save(data)


def due(data, now=None, n=CREATORS_PER_DAY, skip=lambda url: False):
    """The n creators to read today: never read first, then the biggest audiences, each at most once
    in CREATOR_REST."""
    now = now or time.time()
    rows = [(u, r) for u, r in data.items() if now - r.get("read", 0) >= CREATOR_REST and not skip(u)]
    rows.sort(key=lambda ur: (ur[1].get("read", 0) > 0, -ur[1].get("best_views", 0), -ur[1].get("kept", 0)))
    return [u for u, _ in rows[:n]]


def videos(log=print, skip=lambda url: False):
    """Creative Commons uploads of today's due creators: [{id, url, title, channel, channel_url,
    seconds, views}]. A creator whose list cannot be read is tried again on a later day."""
    import yt_api
    data = creators()
    out = []
    for url in due(data, skip=skip):
        row = data[url]
        m = _CHANNEL_ID.search(url)
        try:
            ups = yt_api.uploads(m.group(1), UPLOADS_PER_CREATOR) if m else []
        except Exception as e:  # noqa: BLE001 — out of quota, network: another day
            log(f"Could not read {row.get('name') or url}: {type(e).__name__}")
            break
        cc = [v for v in ups if v.get("licence") == "creativeCommon"]
        row["read"] = int(time.time())
        row["cc"] = len(cc)
        if cc:
            row["best_views"] = max(row.get("best_views", 0), max(v["views"] for v in cc))
        for v in cc:
            out.append({"id": v["id"], "url": v["url"], "title": v["title"], "channel": v["channel"] or row.get("name"),
                        "channel_url": url, "seconds": v.get("seconds"), "views": v.get("views") or 0,
                        "from_creator": True})
        log(f"Creator {row.get('name') or url}: {len(cc)} Creative Commons videos of {len(ups)}.")
    _save(data)
    return out


def summary():
    """For the dashboard and the report: [{name, url, cc, best_views, read}] by audience."""
    data = creators()
    return sorted(({"name": r.get("name"), "url": u, "cc": r.get("cc", 0), "best_views": r.get("best_views", 0),
                    "read": r.get("read", 0), "kept": r.get("kept", 0)} for u, r in data.items()),
                  key=lambda r: -r["best_views"])
