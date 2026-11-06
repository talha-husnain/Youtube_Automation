"""Reminders and the daily summary on the laptop's screen (notify.toast).

Twice a day (SLOTS) the server looks for what only the owner can do: a
Google connection about to stop (Testing-mode tokens die 7 days after the
sign-in), one that already stopped, a channel still waiting to be
connected. One notification covers all of it, and clicking it opens the
Today tab with the steps. ``snooze_until`` holds them back: the owner asked
on 15-oct-2026 to be reminded on Friday or Saturday, when there is time.
At SUMMARY_AT the day's numbers go up as one more notification, and on
Sundays the week's (videos, views, best video per channel). With Telegram
connected the same messages go to the owner's phone too.
"""
import json
import os
import threading
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "output", ".reminders.json")
SLOTS = ("11:00", "19:00")
SUMMARY_AT = "21:30"
WEEKLY_DAY = 6            # Sunday (datetime.weekday)
EXPIRY_WARN_DAYS = 5
DEFAULTS = {"reminders": True, "summary": True, "phone": True, "snooze_until": 0, "sent": {}, "views_at": {}}
_lock = threading.Lock()


def load():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {**DEFAULTS, **(data if isinstance(data, dict) else {})}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def _save(st):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)


def update(patch):
    with _lock:
        st = load()
        for key in ("reminders", "summary", "phone"):
            if key in patch:
                st[key] = bool(patch[key])
        if "snooze_until" in patch:
            try:
                st["snooze_until"] = max(0, int(patch["snooze_until"]))
            except (TypeError, ValueError):
                pass
        _save(st)
        return st


def _when(ts):
    return datetime.fromtimestamp(ts).strftime("%a %d %b, %I:%M %p").replace(" 0", " ")


def things_to_do(today, now=None):
    """The owner's to-do lines from the Today data (app._today)."""
    now = now or time.time()
    out = []
    expiring = [c for c in today["channels"] if c.get("connected") and c.get("expires")]
    soonest = min((c["expires"] for c in expiring), default=0)
    if soonest and soonest <= now:
        out.append(f"Your YouTube connection stopped on {_when(soonest)}. Uploads wait until you reconnect "
                   "(Today tab, 15 minutes).")
    elif soonest and soonest - now <= EXPIRY_WARN_DAYS * 86400:
        out.append(f"Your YouTube connection stops on {_when(soonest)}. Fix it once in 15 minutes: open the "
                   "Today tab and follow the steps.")
    waiting = [c["name"] for c in today["channels"] if not c.get("connected")]
    if waiting:
        out.append(f"Waiting to be connected: {', '.join(waiting)}.")
    # A channel that keeps failing (a key, a quota, a source that is gone)
    # makes nothing all day and nobody is watching the runs.
    free = (today.get("totals") or {}).get("disk_free_gb")
    if free is not None and free < DISK_WARN_GB:
        out.append(f"The disk has only {free:.1f} GB free, so new videos wait. Emptying the Recycle Bin or "
                   "deleting old files in Downloads makes room.")
    for c in today["channels"]:
        for v in c.get("elsewhere") or []:
            out.append(f"\"{v['title'][:70]}\" was made for {c['name']} but went up on {v['on']}. "
                       f"Open https://studio.youtube.com/video/{v['video_id']}/edit and set it to Private "
                       "or delete it.")
        if c.get("enabled", True) and c.get("failed_today", 0) >= FAILS_WARN:
            why = f" The latest reason: {c['fail_reason']}" if c.get("fail_reason") else ""
            out.append(f"{c['name']}: {c['failed_today']} videos failed today.{why}")
    return out


FAILS_WARN = 3
DISK_WARN_GB = 5          # my_channels.MIN_FREE_GB: below it no new video starts


def _slot_due(st, now_dt):
    """The first of today's SLOTS that has passed and was not used yet."""
    day = now_dt.strftime("%Y-%m-%d")
    for slot in SLOTS:
        key = f"{day} {slot}"
        if now_dt.strftime("%H:%M") >= slot and key not in st["sent"]:
            return key
    return None


def summary_text(today):
    t = today["totals"]
    parts = [f"{t['made_today']} Shorts made and {t['uploaded_today']} uploaded on {len(today['channels'])} channels"]
    if t.get("views") is not None:
        parts.append(f"{t['views']:,} views so far" + (f" (+{t['views_gain']:,} since yesterday)"
                                                         if t.get("views_gain") else ""))
    return ". ".join(parts) + "."


def _channel_rows(cid):
    """(uploads.json rows, views of a row) of one channel. The main channel's
    rows carry no views; learning.py keeps them per video id."""
    import youtube_account
    if cid == "main":
        try:
            import learning
            stats = learning.load().get("stats") or {}
        except Exception:  # noqa: BLE001
            stats = {}
        return youtube_account.uploads(), lambda r: int((stats.get(r.get("video_id")) or {}).get("views") or 0)
    import my_channels
    with youtube_account.use(my_channels.account(cid)):
        rows = youtube_account.uploads()
    return rows, lambda r: int(r.get("views") or 0)


MATURE = 48 * 3600   # a Short's views count after two days, as in my_channels.learn


def craft_line(rows, views_of, now, since=None, least=3):
    """ "New scripts: median N views, X% watched (k Shorts) vs M, Y% in the month before" once both
    sides have ``least`` counted Shorts, else "". A before/after split, not an A/B test: the season
    and the channel's age move too, so it is a hint for the owner, not proof."""
    import statistics
    import script_craft
    since = since or script_craft.SINCE

    def side(rs):
        rs = [r for r in rs if r.get("video_id") and r.get("status") == "done" and not r.get("blocked")
              and now - r.get("created", 0) >= MATURE and (r.get("seconds") or 0) <= 180
              and r.get("format") != "history"]      # long videos: their views are another scale
        kept = [r["retention"] for r in rs if r.get("retention") is not None]
        return (len(rs), statistics.median([views_of(r) for r in rs]) if rs else 0,
                statistics.median(kept) if kept else None)
    after = side([r for r in rows if r.get("created", 0) >= since])
    before = side([r for r in rows if since - 30 * 86400 <= r.get("created", 0) < since])
    if min(after[0], before[0]) < least:
        return ""

    def say(s):
        return f"median {s[1]:,.0f} views" + (f", {s[2]:.0f}% watched" if s[2] is not None else "") + f" ({s[0]} Shorts)"
    return f"  New scripts: {say(after)}; the month before: {say(before)}."


def look_line(kind):
    """The week's visual check of this kind of channel (creative_qa): average scores and the defect
    seen most, or ""."""
    try:
        import creative_qa
        d = creative_qa.digest().get(kind or "")
    except Exception:  # noqa: BLE001 — a bonus line
        return ""
    if not d or not d.get("videos"):
        return ""
    line = (f"  Looks ({d['videos']} checked): first frame {d['first_frame']}/10, polish {d['polish']}/10")
    if d["issues"]:
        worst = max(d["issues"], key=d["issues"].get)
        line += f"; seen most: {worst.replace('_', ' ')} ({d['issues'][worst]}x)"
    return line + "."


def _ypp(cid):
    """The channel's numbers against the YPP terms of 1-feb-2027 (yt_insights.ypp_numbers), or None."""
    import my_channels
    import youtube_account as ya
    import yt_insights
    with ya.use(None if cid == "main" else my_channels.account(cid)):
        if not ya.status().get("connected"):
            return None
        return yt_insights.ypp_numbers()


def ypp_lines(today, ypp_fn=_ypp):
    """One line per connected channel on the 2027 targets ([] when none could be read)."""
    import yt_insights
    out = []
    for ch in today.get("channels") or []:
        try:
            n = ypp_fn(ch["id"])
        except Exception:  # noqa: BLE001 — one unreadable channel does not stop the report
            continue
        if n:
            out.append(yt_insights.ypp_line(ch.get("name") or ch["id"], n))
    return out


def week_text(today, now=None, rows_fn=_channel_rows, ypp_fn=_ypp):
    """The last 7 days per channel: videos up, their views, the best one; then the 2027 YPP targets."""
    text = _week_videos(today, now, rows_fn)
    ypp = ypp_lines(today, ypp_fn) if ypp_fn else []
    if ypp:
        text += ("\nYouTube's new money rules from 1 Feb 2027 (sign the new terms in YouTube Studio before then):\n"
                 + "\n".join(ypp))
    return text


def _week_videos(today, now=None, rows_fn=_channel_rows):
    ts = now or time.time()
    since = ts - 7 * 86400
    lines, total_n, total_v = [], 0, 0
    for ch in today.get("channels") or []:
        try:
            rows, views_of = rows_fn(ch["id"])
        except Exception:  # noqa: BLE001 — one unreadable channel does not stop the report
            continue
        week = [r for r in rows if r.get("video_id") and r.get("status") == "done"
                and since <= r.get("created", 0) <= ts and not r.get("blocked")]
        if not week:
            continue
        views = sum(views_of(r) for r in week)
        best = max(week, key=views_of)
        total_n += len(week)
        total_v += views
        line = f"{ch['name']}: {len(week)} videos, {views:,} views"
        if views_of(best):
            line += f". Best: {(best.get('title') or '').split(' #')[0][:60]} ({views_of(best):,})"
        lines.append(line + ".")
        compare = craft_line(rows, views_of, ts)
        if compare:
            lines.append(compare)
        try:
            import my_channels
            lines += my_channels.ab_line(my_channels.get(ch["id"]) or {})
        except Exception:  # noqa: BLE001 — the tests' state is a bonus line
            pass
        look = look_line(ch.get("kind"))
        if look:
            lines.append(look)
    if not lines:
        return "No videos went up this week."
    head = f"This week: {total_n} videos, {total_v:,} views on them so far."
    return "\n".join([head] + lines)


def connection_lost(name):
    """youtube_account.on_dead: told at once, on the laptop and the phone."""
    import notify
    title = f"{name.strip()} needs reconnecting"
    text = ("Google cancelled its connection, so nothing uploads there. Open Shortkaar, "
            "Today tab, and press connect all channels.")
    notify.toast(title, text)
    _phone(load(), title, text)


def _phone(st, title, text):
    """The same message on Telegram when it is connected; never fails the tick."""
    if not st.get("phone"):
        return False
    try:
        import telegram_notify
        if not telegram_notify.status().get("connected"):
            return False
        telegram_notify.send_text(f"{title}\n{text}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ Telegram reminder failed: {type(e).__name__}")
        return False


def tick(today_fn, toast, now=None):
    """Called every minute by the channel loop. ``today_fn()`` -> app._today()."""
    now_dt = datetime.fromtimestamp(now) if now else datetime.now()
    ts = now_dt.timestamp()
    st = load()
    sent = []
    key = _slot_due(st, now_dt) if st["reminders"] and ts >= st.get("snooze_until", 0) else None
    want_summary = (st["summary"] and now_dt.strftime("%H:%M") >= SUMMARY_AT
                    and f"{now_dt:%Y-%m-%d} summary" not in st["sent"])
    want_week = want_summary and now_dt.weekday() == WEEKLY_DAY
    if not key and not want_summary:
        return sent
    today = today_fn()
    if key:
        todo = things_to_do(today, ts)
        if todo:
            toast("Shortkaar needs you (15 minutes)", " ".join(todo), "today")
            _phone(st, "Shortkaar needs you (15 minutes)", " ".join(todo))
            sent.append("reminder")
    if want_summary:
        toast("Shortkaar today", summary_text(today), "today")
        _phone(st, "Shortkaar today", summary_text(today))
        sent.append("summary")
    if want_week:
        text = week_text(today, ts)
        toast("Shortkaar this week", text, "today")
        _phone(st, "Shortkaar this week", text)
        sent.append("week")
    with _lock:
        st = load()
        if key:
            st["sent"][key] = int(ts)
        if want_summary:
            st["sent"][f"{now_dt:%Y-%m-%d} summary"] = int(ts)
            views = (today.get("totals") or {}).get("views")
            if views is not None:
                st["views_at"][f"{now_dt:%Y-%m-%d}"] = views
        # Keep the last two weeks of marks.
        st["sent"] = dict(sorted(st["sent"].items())[-60:])
        st["views_at"] = dict(sorted(st["views_at"].items())[-14:])
        _save(st)
    return sent


def views_gain(views, now=None):
    """Views added since the last summary of an earlier day."""
    day = (datetime.fromtimestamp(now) if now else datetime.now()).strftime("%Y-%m-%d")
    past = [v for d, v in sorted(load()["views_at"].items()) if d < day]
    return max(0, views - past[-1]) if past and views is not None else 0
