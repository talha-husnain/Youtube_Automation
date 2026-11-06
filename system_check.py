"""System check for a local install: is everything Shortkaar needs working?

Each check returns {"name", "status": ok | warn | error, "detail", "fix"} in
plain words, so the owner can see why a job fails without reading logs.
Cheap on purpose: one tiny Gemini call, one PyPI version lookup, the rest
is local.
"""
import os
import shutil
import subprocess
from datetime import datetime, timedelta

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))


def _row(name, status, detail, fix=""):
    return {"name": name, "status": status, "detail": detail, "fix": fix}


def gemini():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return _row("AI (Gemini)", "error", "No GEMINI_API_KEY in .env.", "Add your Gemini key to the .env file.")
    try:
        from google import genai
        # Keep the client in a name: a temporary one is closed before the call
        # returns ("Cannot send a request, as the client has been closed").
        client = genai.Client(api_key=key)
        r = client.models.generate_content(
            model=os.environ.get("GEMINI_MODEL") or "gemini-3.1-flash-lite", contents="Reply with: ok")
        return _row("AI (Gemini)", "ok", f"The key works ({(r.text or '').strip()[:10] or 'answered'}).")
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            return _row("AI (Gemini)", "warn", "The key works but the quota is used up for now.",
                        "Wait a while, or raise the quota in Google AI Studio.")
        return _row("AI (Gemini)", "error", f"The key was refused: {msg[:120]}", "Check the key in .env.")


def _ver(v):
    # PyPI says 2026.8.19 where yt-dlp itself says 2026.08.19.
    return tuple(int(x) for x in str(v).split(".") if x.isdigit())


def downloader():
    rows = []
    try:
        import yt_dlp.version
        have = yt_dlp.version.__version__
    except Exception:  # noqa: BLE001
        return [_row("Downloader (yt-dlp)", "error", "yt-dlp is not installed.", "Run: pip install -r requirements.txt")]
    try:
        latest = httpx.get("https://pypi.org/pypi/yt-dlp/json", timeout=10).json()["info"]["version"]
    except Exception:  # noqa: BLE001
        latest = None
    if latest and _ver(latest) > _ver(have):
        rows.append(_row("Downloader (yt-dlp)", "warn", f"Version {have}; {latest} is out.",
                         "YouTube changes often and old versions start failing. Update: "
                         ".venv\\Scripts\\python.exe -m pip install -U yt-dlp yt-dlp-ejs"))
    else:
        rows.append(_row("Downloader (yt-dlp)", "ok", f"Version {have}" + (" (latest)" if latest else "")))
    try:
        import importlib.metadata as md
        md.version("yt-dlp-ejs")
        ejs = True
    except Exception:  # noqa: BLE001
        ejs = False
    node = shutil.which("node")
    if not ejs or not node:
        rows.append(_row("YouTube challenge solver", "error",
                         "Missing " + " and ".join(x for x, ok in (("yt-dlp-ejs", ejs), ("Node.js", node)) if not ok) + ".",
                         "Without it downloads fail with HTTP 403. Install Node.js and run: pip install yt-dlp-ejs"))
    else:
        rows.append(_row("YouTube challenge solver", "ok", "yt-dlp-ejs and Node.js are installed."))
    return rows


def ffmpeg():
    exe = shutil.which("ffmpeg")
    if not exe or not shutil.which("ffprobe"):
        return _row("Video tools (ffmpeg)", "error", "ffmpeg or ffprobe is missing.", "Install ffmpeg and add it to PATH.")
    try:
        line = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=10).stdout.splitlines()[0]
    except Exception:  # noqa: BLE001
        line = "installed"
    return _row("Video tools (ffmpeg)", "ok", line[:80])


def disk(output_dir, cap_gb):
    total, used, free = shutil.disk_usage(output_dir)
    size = 0
    for base, _dirs, files in os.walk(output_dir):
        for f in files:
            try:
                size += os.path.getsize(os.path.join(base, f))
            except OSError:
                pass
    free_gb, size_gb = free / 1e9, size / 1e9
    detail = f"{free_gb:.0f} GB free; Shortkaar uses {size_gb:.1f} GB of its {cap_gb} GB limit."
    if free_gb < 5:
        return _row("Disk space", "error", detail, "Free some space: a long source video needs 1-2 GB while it is cut.")
    if free_gb < 20 or size_gb > cap_gb * 0.9:
        return _row("Disk space", "warn", detail, "Old jobs are deleted on their own; download what you want to keep.")
    return _row("Disk space", "ok", detail)


def channel():
    import youtube_account
    st = youtube_account.status()
    rows = []
    if st["connected"]:
        rows.append(_row("YouTube channel", "ok", f"Connected: {(st.get('channel') or {}).get('title', '')}."))
    elif st["configured"]:
        rows.append(_row("YouTube channel", "warn", "Set up but not connected.", "Open My channel and press Connect."))
    else:
        rows.append(_row("YouTube channel", "warn", "Not connected (uploads and watch-time numbers need it).",
                         "Optional: follow the steps in My channel."))
    if not os.environ.get("YOUTUBE_COOKIES"):
        rows.append(_row("YouTube sign-in cookies", "ok", "Not set; most videos download without them.",
                         "Only needed if downloads keep saying 'Sign in to confirm you're not a bot'."))
    else:
        rows.append(_row("YouTube sign-in cookies", "ok", "Set."))
    return rows


def autopilot():
    import autopilot_local
    cfg = autopilot_local.settings()
    if not cfg["enabled"]:
        return _row("Autopilot", "warn", "Off.", "Switch it on in Autopilot to get Shorts every day.")
    now = datetime.now()
    h, m = (int(x) for x in cfg["run_at"].split(":"))
    nxt = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if cfg.get("last_run") == now.strftime("%Y-%m-%d") or nxt <= now:
        nxt += timedelta(days=1)
    if cfg["comedy_per_day"] and not cfg["channels"]:
        return _row("Autopilot", "warn", "On, but no source channel for comedy.", "Add channels in Autopilot.")
    return _row("Autopilot", "ok", f"On. Next run {nxt.strftime('%a %d %b, %H:%M')}; "
                                   f"{cfg['comedy_per_day']} comedy + {cfg['cricket_per_day']} cricket a day. "
                                   "This computer must be on with Shortkaar running.")


def _env():
    """.env as each job reads it: keys added there work without a restart."""
    from dotenv import dotenv_values
    return {**os.environ, **{k: v for k, v in dotenv_values(os.path.join(ROOT, ".env")).items() if v}}


def free_voice():
    import free_voice as fv
    if fv.engine() != "edge":
        return _row("Free voice", "ok", "Off: the Gemini voice reads everything.")
    rest = fv.rest_info()
    if rest:
        until = datetime.fromtimestamp(rest["until"]).strftime("%H:%M")
        return _row("Free voice", "warn", f"Resting until {until} ({rest.get('reason') or 'refused'}); "
                                          "the Gemini voice reads lines until then.", "Nothing to do: it comes back by itself.")
    return _row("Free voice", "ok", "Ready (Microsoft's read-aloud voice, no cost).")


def stock():
    import stock_media
    env = _env()
    have = [n for n, k in (("Pexels", "PEXELS_API_KEY"), ("Pixabay", "PIXABAY_API_KEY")) if (env.get(k) or "").strip()]
    resting = [p for p in ("pexels", "pixabay", "openverse") if stock_media._resting(p)]
    detail = (f"Keys: {', '.join(have)}." if have else "No Pexels or Pixabay key yet: only Openverse photos.")
    if resting:
        detail += f" Resting now (too many requests or not answering): {', '.join(resting)}."
    return _row("Free stock footage", "ok" if len(have) == 2 and not resting else "warn", detail,
                "" if len(have) == 2 else "Add PEXELS_API_KEY and PIXABAY_API_KEY to .env (both free; steps on Today).")


def quota():
    import youtube_account
    used = youtube_account.quota_used()
    return _row("YouTube API quota today", "ok" if used < 8000 else "warn",
                f"{used:,} of 10,000 units used (resets at midnight Pacific time).",
                "" if used < 8000 else "Engagement pauses near the limit; uploads keep going.")


def watchdog():
    """Is autostart's watchdog running (it restarts a stopped server)?"""
    if os.name != "nt":
        return _row("Watchdog", "ok", "Only used on Windows.")
    try:
        # No double quotes inside: Python's argument quoting turned the -Filter
        # string into something that matched nothing.
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "@(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'cmd.exe' -and "
                            "$_.CommandLine -like '*autostart.bat*watch*' }).Count"],
                           capture_output=True, text=True, timeout=30)
        on = (r.stdout or "").strip() not in ("", "0")
    except (OSError, subprocess.SubprocessError):
        return _row("Watchdog", "warn", "Could not check.")
    return (_row("Watchdog", "ok", "Running: a stopped server restarts within 5 minutes.") if on else
            _row("Watchdog", "warn", "Not running.", "Run autostart.bat once (it starts at every login)."))


def stay_awake():
    """Does the laptop stay awake while a video is made (keep_awake.py)?"""
    import keep_awake
    if os.environ.get("KEEP_AWAKE", "1").strip() == "0":
        return _row("Stay awake", "warn", "Off (KEEP_AWAKE=0): the laptop may sleep in the middle of a video.")
    if not keep_awake.on_charger():
        return _row("Stay awake", "warn", "On battery: the laptop may sleep in the middle of a video.",
                    "Keep the charger in while the channels work.")
    st = keep_awake.state()
    if st["awake"] and str(st.get("why", "")).startswith("working"):
        return _row("Stay awake", "ok", "Working now: the laptop stays awake until it is done.")
    if os.environ.get("KEEP_AWAKE", "1").strip().lower() in ("charger", "always"):
        return _row("Stay awake", "ok", "On the charger the laptop stays awake all the time, so Autopilot never "
                    "freezes between videos (KEEP_AWAKE=charger; the screen still turns off, closing the lid still sleeps).")
    return _row("Stay awake", "ok", "On the charger: while a video is made or uploaded the laptop does not go to sleep "
                "(closing the lid still does).")


def encoder():
    """Which video encoder renders use (ffmpeg_utils: x264, Intel Quick Sync or NVENC)."""
    import ffmpeg_utils
    mode = os.environ.get("FFMPEG_ENCODER", "x264").strip().lower()
    name = ffmpeg_utils.encoder_name()
    label = {"h264_qsv": "Intel Quick Sync (the laptop's graphics chip)", "h264_nvenc": "NVIDIA NVENC",
             "libx264": "x264 on the CPU"}[name]
    if mode in ("qsv", "nvenc") and name == "libx264":
        return _row("Video encoder", "warn", f"FFMPEG_ENCODER={mode} but it does not work here; x264 on the CPU instead.",
                    "Update the graphics driver, or set FFMPEG_ENCODER=x264 in .env.")
    return _row("Video encoder", "ok", f"{label} (FFMPEG_ENCODER={mode}).")


def heartbeat():
    """The outside heartbeat (heartbeat.py): something off the laptop that notices when it stops."""
    import heartbeat as hb
    st = hb.state()
    if not st["on"]:
        return _row("Outside heartbeat", "warn", "Off: nobody hears about it when the laptop is off, asleep or offline.",
                    "Make a free check at healthchecks.io (period 5 min, grace 20 min, add Telegram), put its ping URL "
                    "in .env as HEALTHCHECK_URL and restart Shortkaar.")
    last = st["last"] or "no ping yet (the first goes 5 minutes after the start)"
    return _row("Outside heartbeat", "ok" if st["last"] in (None, "ok") else "warn", f"On. Last ping: {last}.")


def run_all(output_dir, cap_gb, retention_seconds):
    rows = [gemini(), *downloader(), ffmpeg(), disk(output_dir, cap_gb), *channel(), autopilot(),
            free_voice(), stock(), quota(), watchdog(), stay_awake(), encoder(), heartbeat()]
    import short_kit
    n = len(short_kit.music_tracks())
    rows.append(_row("Background music", "ok" if n else "warn", f"{n} track(s) in the music folder.",
                     "" if n else "Add royalty-free tracks to the music folder for cricket Shorts (optional)."))
    rows.append(_row("Keeping files", "ok", f"Finished jobs are kept {retention_seconds // 3600} hours; "
                                            "Shorts waiting in Ready to post and long videos for 7 days."))
    return rows
