"""Keep the laptop from going to sleep while a video is being made or uploaded.

The laptop sleeps when nobody touches it, and a sleeping laptop stops the
render and drops the network: a 10-minute video died half made on
15-oct-2026. Windows lets a program ask "stay awake while I work"
(SetThreadExecutionState, what video players use); the request ends when we
clear it or the process stops, and no power setting is changed. Only on the
charger: on battery the laptop may sleep as usual. Closing the lid still
sleeps it (that is a separate setting this does not touch).

``refresh`` must run on a thread that lives as long as the server (the event
loop's), because Windows ties the request to the calling thread.
``KEEP_AWAKE=0`` turns it off.

``KEEP_AWAKE=charger`` (4-nov-2026, set in the owner's .env): stay awake on
the charger whenever the server runs, not only during a job. The laptop has
Modern Standby only (S0 low-power idle, no S3) and wake timers are off, so
once it dozed between jobs every loop froze with it: first comments, claim
checks, the Facebook/Instagram posts timed to each YouTube slot, the next
job. The screen still turns off, battery and a closed lid still sleep. The
default (``1``) is unchanged for other self-host installs.
"""
import contextlib
import os
import sys
import threading

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

_busy = 0
_lock = threading.Lock()
_state = {"awake": False, "why": "idle"}


@contextlib.contextmanager
def task():
    """Work outside a job (an upload in an executor thread) that should keep
    the laptop awake until it ends."""
    global _busy
    with _lock:
        _busy += 1
    try:
        yield
    finally:
        with _lock:
            _busy -= 1


def busy():
    return _busy > 0


def on_charger():
    """True on mains power, or when Windows cannot tell (a desktop)."""
    if sys.platform != "win32":
        return True
    import ctypes

    class Status(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                    ("BatteryLifePercent", ctypes.c_byte), ("SystemStatusFlag", ctypes.c_byte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
    st = Status()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):
        return True
    return st.ACLineStatus != 0          # 1 = on mains, 255 = unknown, 0 = battery


def _set(flags):
    if sys.platform != "win32":
        return True
    import ctypes
    return bool(ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags)))


def refresh(working):
    """Ask Windows to stay awake while ``working`` (or an upload runs), else
    let it sleep again. Returns the state shown in the system check."""
    mode = os.environ.get("KEEP_AWAKE", "1").strip().lower()
    always = mode in ("charger", "always")
    if mode == "0":
        want, why = False, "off (KEEP_AWAKE=0)"
    elif not (working or busy() or always):
        want, why = False, "idle"
    elif not on_charger():
        want, why = False, "on battery, the laptop may sleep"
    elif always and not (working or busy()):
        want, why = True, "on the charger, the laptop stays awake for Autopilot"
    else:
        want, why = True, "working, the laptop stays awake"
    if want != _state["awake"] or why != _state["why"]:
        ok = _set(ES_CONTINUOUS | ES_SYSTEM_REQUIRED if want else ES_CONTINUOUS)
        _state.update(awake=want and ok, why=why if ok else "Windows refused the request")
    return dict(_state)


def state():
    return dict(_state)
