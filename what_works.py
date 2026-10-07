""""What works" on the channel: which Shorts and titles win, in plain words,
and a few title rules the SEO writer follows from then on (seo_copy.apply).

Numbers come from YouTube Analytics when the channel is connected
(youtube_account.py: views, % watched, likes, comments, subscribers per
Short) and otherwise from the public Shorts tab (titles and views only,
channel_tools.channel_shorts). The comparisons are counted here, in code;
Gemini only turns them into lessons, so a lesson can cite a real number.
The report is kept in ``output/.what_works.json``; ``use`` false stops the
title rules from reaching the prompt.
"""
import json
import os
import re
import statistics
import time
from typing import List

from pydantic import BaseModel

ROOT = os.path.dirname(os.path.abspath(__file__))
REPORT_FILE = os.path.join(ROOT, "output", ".what_works.json")
SHORT_MAX_SECONDS = 180
MIN_SHORTS = 5
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_ARABIC = re.compile(r"[؀-ۿ]")
_EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")


class Lesson(BaseModel):
    text: str
    evidence: str


class Learnings(BaseModel):
    summary: str
    lessons: List[Lesson]
    title_rules: List[str]
    do_more: List[str]
    avoid: List[str]


PROMPT = """You coach a small YouTube Shorts channel ({channel}) that posts Pakistani / Indian
stand-up comedy clips and cricket facts with Roman Urdu titles. Below are its Shorts with
their numbers, and comparisons counted from them. Data source: {source}.

Write for the channel owner in short, plain English sentences (no jargon, no em dashes):
- summary: 2 sentences on how the channel is doing and the single biggest pattern.
- lessons: 3 to 6 patterns that separate the winners from the rest. Each one names the
  evidence from the numbers below (for example "question titles: median 340 views vs 90").
  Only claim what the numbers show. {early}
- title_rules: 3 to 5 short rules for the AI that writes the next titles (Roman Urdu),
  each one concrete ("Start with the situation, not the person"), from the winners.
- do_more: up to 4 topics or angles to make more of. avoid: up to 4 things to stop.
Every title rule, do_more and avoid item must follow from a lesson above. A comparison
whose two medians are close is "no clear difference": never turn it into a rule.

COMPARISONS
{groups}

SHORTS (newest first)
{rows}
"""


def _script(title):
    if _DEVANAGARI.search(title):
        return "Hindi script"
    if _ARABIC.search(title):
        return "Urdu script"
    return "Roman letters"


def _median(xs):
    return round(statistics.median(xs)) if xs else 0


def groups(rows):
    """Median views per feature, counted from the rows (no AI)."""
    def split(name, test):
        yes = [r["views"] for r in rows if test(r)]
        no = [r["views"] for r in rows if not test(r)]
        if yes and no:
            return {"name": name, "yes": len(yes), "yes_median": _median(yes),
                    "no": len(no), "no_median": _median(no)}
        return None

    out = [
        split("Title asks a question (?)", lambda r: "?" in r["title"]),
        split("Title has an emoji", lambda r: bool(_EMOJI.search(r["title"]))),
        split("Title in Roman letters (not Hindi/Urdu script)", lambda r: _script(r["title"]) == "Roman letters"),
        split("Title under 45 characters", lambda r: len(re.sub(r"#\S+", "", r["title"]).strip()) < 45),
        split("Cricket Short", lambda r: r.get("genre") == "cricket" or "cricket" in r["title"].lower()),
    ]
    if any(r.get("avg_percent") is not None for r in rows):
        out.append(split("Watched past 70% on average", lambda r: (r.get("avg_percent") or 0) >= 70))
    if any(r.get("seconds") for r in rows):
        out.append(split("Shorter than 40 seconds", lambda r: 0 < (r.get("seconds") or 0) < 40))
    if any(r.get("hour") is not None for r in rows):
        out.append(split("Posted 17:00-23:00", lambda r: 17 <= (r.get("hour") or 0) <= 23))
    return [g for g in out if g]


def collect(handle=""):
    """[{id, title, views, ...}] of the channel's Shorts and where they came from."""
    import youtube_account
    if youtube_account.status()["connected"]:
        rows = [r for r in youtube_account.recent_videos(150) if 0 < r["seconds"] <= SHORT_MAX_SECONDS]
        try:
            stats = youtube_account.video_analytics(180)
        except Exception as e:  # noqa: BLE001 — public numbers still make a report
            print(f"   ℹ️ Analytics unavailable ({e}); using public numbers.")
            stats = {}
        made = {u.get("video_id"): u.get("genre") for u in youtube_account.uploads() if u.get("video_id")}
        tz = __import__("datetime").datetime.now().astimezone().tzinfo
        for r in rows:
            r.update(stats.get(r["id"], {}))
            r["genre"] = made.get(r["id"])
            try:
                from datetime import datetime
                r["hour"] = datetime.fromisoformat(r["published"].replace("Z", "+00:00")).astimezone(tz).hour
            except (KeyError, ValueError):
                r["hour"] = None
        return rows, "YouTube Analytics (connected channel)"
    import channel_tools
    if not handle:
        raise RuntimeError("Connect your YouTube channel, or set your channel handle.")
    return channel_tools.channel_shorts(handle, 80), "public view counts (connect YouTube for watch time)"


def _row_line(r):
    bits = [f'"{r["title"][:90]}"', f'{r["views"] or 0} views']
    if r.get("avg_percent") is not None:
        bits.append(f'{r["avg_percent"]}% watched')
    for k in ("likes", "comments", "subs"):
        if r.get(k):
            bits.append(f"{r[k]} {k}")
    if r.get("seconds"):
        bits.append(f'{r["seconds"]}s')
    return " | ".join(bits)


def build(handle=""):
    rows, source = collect(handle)
    rows = [r for r in rows if r.get("views") is not None]
    report = {"at": int(time.time()), "source": source, "count": len(rows), "use": _current_use()}
    if len(rows) < MIN_SHORTS:
        report.update(enough=False, rows=rows)
        _save(report)
        return report
    ranked = sorted(rows, key=lambda r: r["views"], reverse=True)
    g = groups(rows)
    import short_kit
    views = [r["views"] for r in rows]
    early = ("This is little data (few Shorts or few views): say the patterns are early signs."
             if len(rows) < 30 or _median(views) < 50 else "")
    learned = short_kit.ask_json(short_kit.gemini(), Learnings, PROMPT.format(
        channel=handle or "this channel", source=source, early=early,
        groups="\n".join(f'- {x["name"]}: {x["yes"]} Shorts, median {x["yes_median"]} views; '
                         f'others {x["no"]}, median {x["no_median"]}' for x in g),
        rows="\n".join(_row_line(r) for r in rows[:120])))
    report.update(enough=True, total_views=sum(r["views"] for r in rows),
                  median_views=_median([r["views"] for r in rows]),
                  top=ranked[:5], bottom=ranked[-5:][::-1], groups=g, rows=rows,
                  **learned.model_dump())
    _save(report)
    return report


def _save(report):
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False)


def load():
    try:
        with open(REPORT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _current_use():
    r = load()
    return True if r is None else bool(r.get("use", True))


def set_use(on):
    r = load() or {}
    r["use"] = bool(on)
    _save(r)
    return r


def guidance():
    """The title rules for seo_copy's prompt, or "" (no report, or switched off)."""
    r = load()
    if not r or not r.get("use", True) or not r.get("title_rules"):
        return ""
    rules = "\n".join(f"- {x}" for x in r["title_rules"][:5])
    return ("What has worked on THIS channel so far (from its own numbers); follow it when it "
            f"fits the clip:\n{rules}")
