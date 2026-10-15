"""Reminders and the daily summary on the laptop's screen (notify.toast).

Twice a day (SLOTS) the server looks for what only the owner can do: a
Google connection about to stop (Testing-mode tokens die 7 days after the
sign-in), one that already stopped, a channel still waiting to be
connected. One notification covers all of it, and clicking it opens the
Today tab with the steps. ``snooze_until`` holds them back: the owner asked
on 15-oct-2026 to be reminded on Friday or Saturday, when there is time.
At SUMMARY_AT the day's numbers go up as one more notification.
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
EXPIRY_WARN_DAYS = 5
DEFAULTS = {"reminders": True, "summary": True, "snooze_until": 0, "sent": {}, "views_at": {}}
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
        for key in ("reminders", "summary"):
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
    for c in today["channels"]:
        if c.get("enabled", True) and c.get("failed_today", 0) >= FAILS_WARN:
            why = f" The latest reason: {c['fail_reason']}" if c.get("fail_reason") else ""
            out.append(f"{c['name']}: {c['failed_today']} videos failed today.{why}")
    return out


FAILS_WARN = 3


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


def tick(today_fn, toast, now=None):
    """Called every minute by the channel loop. ``today_fn()`` -> app._today()."""
    now_dt = datetime.fromtimestamp(now) if now else datetime.now()
    ts = now_dt.timestamp()
    st = load()
    sent = []
    key = _slot_due(st, now_dt) if st["reminders"] and ts >= st.get("snooze_until", 0) else None
    want_summary = (st["summary"] and now_dt.strftime("%H:%M") >= SUMMARY_AT
                    and f"{now_dt:%Y-%m-%d} summary" not in st["sent"])
    if not key and not want_summary:
        return sent
    today = today_fn()
    if key:
        todo = things_to_do(today, ts)
        if todo:
            toast("Shortkaar needs you (15 minutes)", " ".join(todo), "today")
            sent.append("reminder")
    if want_summary:
        toast("Shortkaar today", summary_text(today), "today")
        sent.append("summary")
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
