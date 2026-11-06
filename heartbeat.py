"""An outside heartbeat: something OFF the laptop notices when Shortkaar stops.

Toasts and Telegram notes come from the laptop itself, so the failures that
matter most (the laptop off, asleep, out of network, the server dead) are the
ones nobody hears about. A heartbeat inverts that: the server pings a URL
every ``EVERY`` seconds while its loops are ticking, and the service on the
other end alerts the owner when the pings STOP.

Set ``HEALTHCHECK_URL`` in .env to a check's ping URL, e.g. a free
healthchecks.io check (Hobbyist plan: 20 checks, Telegram/email/ntfy alerts;
period 5 min, grace 15-20 min). Unset = off, nothing is sent.

- Healthy (both Autopilot loops ticked within ``STUCK_SECONDS``): GET <url>.
- A loop stuck (a hung call holding it past ``STUCK_SECONDS``): POST
  <url>/fail with the reason, at most every ``FAIL_EVERY`` seconds, so the
  owner hears "stuck" at once instead of waiting out the grace period.
The ping carries no data about the channels: only "ok" or the stuck reason.
"""
import asyncio
import os
import time

EVERY = 300
STUCK_SECONDS = 45 * 60        # a long upload may hold a tick for many minutes; never that long
FAIL_EVERY = 30 * 60
_state = {"last_fail": 0.0, "last": None}


def url():
    u = (os.environ.get("HEALTHCHECK_URL") or "").strip()
    return u if u.startswith(("https://", "http://")) else ""


def verdict(ticks, now=None):
    """(ok, reason) from {"name": last tick time or None}. A loop that has not
    ticked yet (server just started) counts as fine for its first STUCK_SECONDS."""
    now = time.time() if now is None else now
    stuck = [f"{name} has not ticked for {int((now - t) // 60)} min"
             for name, t in ticks.items() if t is not None and now - t > STUCK_SECONDS]
    return (not stuck, "; ".join(stuck))


def ping(ticks, now=None, get=None, post=None):
    """One heartbeat. Returns "ok", "fail", "quiet" (stuck, already said so) or "off"."""
    u = url()
    if not u:
        return "off"
    now = time.time() if now is None else now
    ok, why = verdict(ticks, now)
    if get is None or post is None:
        import httpx
        get = get or (lambda x: httpx.get(x, timeout=10))
        post = post or (lambda x, body: httpx.post(x, content=body.encode("utf-8"), timeout=10))
    try:
        if ok:
            get(u)
            _state["last"] = "ok"
            return "ok"
        if now - _state["last_fail"] < FAIL_EVERY:
            return "quiet"
        post(u.rstrip("/") + "/fail", why)
        _state.update(last_fail=now, last="fail")
        return "fail"
    except Exception as e:  # noqa: BLE001 — offline is exactly when this fails; the silence is the alert
        _state["last"] = f"unreachable ({type(e).__name__})"
        return "unreachable"


def state():
    return {"on": bool(url()), "last": _state["last"]}


async def loop_forever(ticks_fn):
    """``ticks_fn()`` -> {"name": last tick time}. Runs on the event loop; the
    HTTP call goes to a thread."""
    while True:
        await asyncio.sleep(EVERY)
        if not url():
            continue
        try:
            ticks = ticks_fn()
            await asyncio.get_running_loop().run_in_executor(None, ping, ticks)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ Heartbeat error: {type(e).__name__}: {e}")
