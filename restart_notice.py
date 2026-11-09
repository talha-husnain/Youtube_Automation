"""Tell the owner when the server had stopped and the watchdog started it again.

autostart.bat's watchdog checks port 8000 every 5 minutes and starts the
server when nothing answers. That brings it back, but silently: a server that
crashes every hour (or cannot start at all after a bad edit) looked exactly
like a healthy one from the owner's side, while Autopilot made nothing.

Two ways in, both rate-limited to one message per ``QUIET_SECONDS``:

- ``announce_restart()`` from the server's lifespan when the watchdog started
  it (autostart.bat sets ``SHORTKAAR_RESTART=watchdog`` for that start only):
  "it had stopped, it is back", with the last error line of the run before.
- ``python restart_notice.py down <n>`` from the watchdog itself after ``n``
  checks in a row found nothing on the port: the server is not coming back
  (an import error, a port taken), so the lifespan above never runs.

Only the standard library, python-dotenv and httpx (through telegram_notify)
are imported, so the "down" path works when app.py itself is broken.
``SHORTKAAR_NOTIFY=0`` turns the toast off as everywhere else.
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "output", "server.log")
STATE = os.path.join(ROOT, "output", ".restart_notice.json")
QUIET_SECONDS = 3600
TAIL_BYTES = 256 * 1024
_START = "Started server process"
_ERRORISH = re.compile(r"(Traceback|\w+Error\b|\w+Exception\b|Killed|MemoryError|Fatal)")


def last_error(log_path=LOG):
    """The last error-looking line of the run before the newest start, else
    its last non-empty line, else ''. Reads only the log's tail."""
    try:
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - TAIL_BYTES))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return ""
    before = text.rsplit(_START, 1)[0] if _START in text else text
    lines = [ln.strip() for ln in before.splitlines() if ln.strip() and not ln.startswith("INFO:")]
    for ln in reversed(lines[-400:]):
        if _ERRORISH.search(ln):
            return ln[:300]
    return lines[-1][:300] if lines else ""


def _quiet(now, state_path=STATE):
    try:
        with open(state_path, encoding="utf-8") as f:
            last = float(json.load(f)["at"])
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return False                      # never sent (or unreadable): not quiet
    return 0 <= now - last < QUIET_SECONDS


def _remember(now, state_path=STATE):
    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"at": now}, f)
    except OSError:
        pass


def send(title, text):
    """Toast + Telegram (when connected). Never raises."""
    sent = []
    try:
        import notify
        if notify.toast(title, text):
            sent.append("toast")
    except Exception:  # noqa: BLE001 — a notice is never worth a crash
        pass
    try:
        import telegram_notify
        if telegram_notify.status().get("connected"):
            telegram_notify.send_text(f"{title}\n{text}")
            sent.append("telegram")
    except Exception:  # noqa: BLE001
        pass
    return sent


def announce_restart(now=None, log_path=LOG, state_path=STATE, send_fn=send):
    """From the lifespan: say the server is back if the watchdog started it."""
    if os.environ.get("SHORTKAAR_RESTART", "").strip().lower() != "watchdog":
        return None
    now = time.time() if now is None else now
    if _quiet(now, state_path):
        return None
    err = last_error(log_path)
    text = "The server had stopped and the watchdog started it again at " + time.strftime("%H:%M", time.localtime(now)) + "."
    if err:
        text += f"\nLast line before it stopped: {err}"
    _remember(now, state_path)
    return send_fn("Shortkaar restarted", text)


def announce_down(misses, now=None, log_path=LOG, state_path=STATE, send_fn=send):
    """From the watchdog: the server is still not answering after ``misses`` checks."""
    now = time.time() if now is None else now
    if _quiet(now, state_path):
        return None
    err = last_error(log_path)
    mins = int(misses) * 5
    text = (f"The server has not answered for about {mins} minutes; Autopilot is stopped."
            " Open output\\server.log on the laptop.")
    if err:
        text += f"\nLast line: {err}"
    _remember(now, state_path)
    return send_fn("Shortkaar is down", text)


def announce_taken(owner, port=8000, now=None, state_path=STATE, send_fn=send):
    """From the watchdog: another program (a Docker container, another app)
    holds the server's port, so Shortkaar cannot start there."""
    now = time.time() if now is None else now
    if _quiet(now, state_path):
        return None
    owner = re.sub(r"[^\w .-]", "", str(owner or "another program"))[:60] or "another program"
    text = (f"Port {port} is held by {owner}, so Shortkaar's server cannot start and Autopilot is stopped."
            " If it is Docker, stop that container (docker compose down in the project folder).")
    _remember(now, state_path)
    return send_fn("Shortkaar cannot start", text)


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except Exception:  # noqa: BLE001 — without dotenv only the toast goes out
        pass
    if len(sys.argv) >= 2 and sys.argv[1] == "down":
        n = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2].isdigit() else "3"
        print(announce_down(int(n)))
    elif len(sys.argv) >= 2 and sys.argv[1] == "taken":
        print(announce_taken(" ".join(sys.argv[2:])))
    else:
        print("usage: python restart_notice.py down <checks missed> | taken <program>")
