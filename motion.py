"""Real motion for a painted shot: Alibaba's Wan 2.2 image-to-video (open weights, Apache 2.0) through fal.

Owner, 11-nov-2026: "the video quality is pretty shit ... Chinese models are very famous, use their features".
This laptop has no NVIDIA card, so no open video model runs here (docs/research-2026-11-11/open-models.md);
fal sells Wan 2.2 A14B Turbo image-to-video at $0.05 a clip at 480p and $0.10 at 720p (fal's model page,
11-nov-2026), about 5 s a clip. The horror channel's opening painting becomes a moving shot (mist, a lantern's
flicker, a slow push), which is what makes the niche's videos feel made rather than a slideshow.

fal removes its Wan 2.2 endpoints on 4 Jan 2027 (research note); MOTION_ENDPOINT then points at the successor.
MOTION=0 turns it off; MOTION_PER_DAY (default 6) caps the clips a day. Any failure keeps the still picture.
"""
import json
import os
import subprocess
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "state", "motion.json")
ENDPOINT = "fal-ai/wan/v2.2-a14b/image-to-video/turbo"
PRICE = {"480p": 0.05, "580p": 0.075, "720p": 0.10}
# What the model is asked to do with a still painting: small, believable movement, never a new scene.
MOTION_RULE = ("Slow cinematic camera push-in. Subtle natural movement only: drifting mist, flickering lantern "
               "light, moving leaves or water. Keep the painting's composition, style and colours exactly; no new "
               "objects, no people appearing, no text.")


def enabled():
    if os.environ.get("MOTION", "1").strip() == "0":
        return False
    try:
        import ai_influencer
        return bool(ai_influencer.key())
    except Exception:  # noqa: BLE001
        return False


def _read():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def made_today():
    return int((_read().get("days") or {}).get(time.strftime("%Y-%m-%d"), 0))


def room_today():
    return max(0, int(os.environ.get("MOTION_PER_DAY") or 6) - made_today())


def _count(price):
    data = _read()
    day = time.strftime("%Y-%m-%d")
    days = data.get("days") or {}
    days = {d: n for d, n in days.items() if d >= time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))}
    days[day] = days.get(day, 0) + 1
    data["days"] = days
    data["usd"] = round(float(data.get("usd") or 0) + price, 3)
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, STATE_FILE)


def moved(path):
    """True when the clip really moves: a still returned as video would freeze the shot it replaces."""
    try:
        out = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-vf", "freezedetect=n=0.003:d=2", "-an",
                              "-f", "null", "-"], capture_output=True, text=True, timeout=120)
        return "freeze_start" not in (out.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return True


def pingpong(path):
    """The clip forward then backward (~10 s, no jump): a long video's shot loops a short clip, and a 5 s clip
    jumped back to its first frame mid-shot. Kept as it was when ffmpeg fails."""
    tmp = path + ".pp.mp4"
    try:
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", path, "-filter_complex",
                        "[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-an",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", tmp],
                       check=True, capture_output=True, timeout=300)
        os.replace(tmp, path)
    except (OSError, subprocess.SubprocessError):
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def animate(picture, scene, out, resolution="720p", log=print):
    """``picture`` (a painting) moving for ~5 s, saved at ``out``; returns ``out`` or None. ``scene`` says what is
    in it, so the movement fits (water flows, the lantern flickers)."""
    if not enabled() or room_today() <= 0:
        return None
    try:
        import talkies
        url = talkies.fal_upload(picture)
        body = talkies.fal_job(os.environ.get("MOTION_ENDPOINT") or ENDPOINT,
                               {"image_url": url, "prompt": f"{MOTION_RULE} The scene: {scene}"[:1500],
                                "resolution": resolution, "aspect_ratio": "auto",
                                "enable_safety_checker": True})
        video = (body.get("video") or {}).get("url") if isinstance(body, dict) else None
        if not video:
            raise RuntimeError(f"no video in the answer: {str(body)[:160]}")
        talkies._download(video, out)
        _count(PRICE.get(resolution, 0.10))
        if not moved(out):
            log("   ℹ️ The moving shot came back still; the painting stays.")
            return None
        pingpong(out)
        log(f"   🎥 Moving shot made (Wan 2.2, {resolution}, ${PRICE.get(resolution, 0.10):.2f}).")
        return out
    except Exception as e:  # noqa: BLE001 — the still painting is kept
        log(f"   ℹ️ No moving shot ({type(e).__name__}: {str(e)[:120]}); the painting stays.")
        if os.path.exists(out):
            try:
                os.remove(out)
            except OSError:
                pass
        return None
