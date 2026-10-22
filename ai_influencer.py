"""The songs channel's AI singer: one fictional woman, the same face in every
video, dancing to the channel's own Lyria songs (owner, 22-oct-2026: "an AI
influencer ... a bold female character, it can dance").

How one dance background is made (music_shorts.run with MUSIC_DANCE=1):
1. A new still of her (Gemini image, her reference picture passed in, about
   $0.067 at 1K): full body, an outfit and place that fit the song, classy and
   fully clothed. YouTube removes "provocative dancing that is focused on the
   dancer's genitals, buttocks, or breasts" (answer/2802002) and limits ads on
   twerking or grinding (answer/6162278), so the stills and the dance clips
   stay stylish, never suggestive.
2. Free vertical dance clips (Pixabay / Pexels; both licences allow modifying)
   chosen by one vision call: one person, whole body in frame, a still camera.
3. fal.ai Wan 2.2 Animate "move" puts her into each clip's motion. Billed per
   16 frames ($0.04 a second at 480p, $0.06 at 580p, $0.08 at 720p, fal's
   model page 22-oct-2026), so the clips are cut to 16 fps before upload. The
   clips run in parallel and are joined, scaled to the 1080x1920 canvas.
No fal key, no chosen character, or today's DAILY_MAX reached: available()
is False and the channel makes its normal songs. Any failure inside returns
None and the song keeps its stock footage.

The character is made once (``python ai_influencer.py looks`` writes a few
candidate pictures, ``python ai_influencer.py pick <file> <name>`` keeps one)
and lives in state/influencer/ (gitignored).
"""
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(ROOT, "state", "influencer")
CHARACTER_FILE = os.path.join(STATE_DIR, "character.json")
SPEND_FILE = os.path.join(STATE_DIR, "spend.json")
MODEL = os.environ.get("INFLUENCER_MODEL") or "fal-ai/wan/v2.2-14b/animate/move"
RESOLUTION = os.environ.get("INFLUENCER_RESOLUTION") or "480p"
PRICE = {"480p": 0.04, "580p": 0.06, "720p": 0.08}       # $ per billed second (16 frames)
STILL_PRICE = 0.067
SECONDS = float(os.environ.get("INFLUENCER_SECONDS") or 15)
DAILY_MAX = int(os.environ.get("INFLUENCER_DAILY_MAX") or 2)
MIN_CLIP = 4.0           # a dance clip shorter than this is a pose, not a dance
MAX_CLIPS = 3
DRIVE_FPS = 16
POLL = 10
WAIT = 30 * 60
OUT_W, OUT_H, FPS = 1080, 1920, 30
QUEUE = "https://queue.fal.run/"
TOKEN_URL = "https://rest.fal.ai/storage/auth/token?storage_type=fal-cdn-v3"
UPLOAD_URL = "https://v3.fal.media/files/upload"
INITIATE_URL = "https://rest.fal.ai/storage/upload/initiate?storage_type=gcs"

DANCE_TERMS = ["woman dancing", "girl dancing", "dance choreography", "dancer studio",
               "hip hop dance woman", "contemporary dance woman", "woman dancing happy"]
DRIVE_RULE = ("This clip only drives the MOTION of an AI dancer, so judge the movement and framing, not the "
              "person: exactly ONE real filmed person (never a cartoon, drawing or animation: the first Pixabay "
              "picks were line-art girls, 22-oct-2026), the WHOLE body from head to feet inside the frame, a still camera "
              "(no pans, no cuts), real dancing that keeps going (not walking, posing or stretching). Never a "
              "suggestive dance (twerking, grinding, moves that focus on the body). Score 0 for anything else.")
LOOKS = [
    "a South Asian woman in her mid twenties, long dark wavy hair, warm brown eyes, a confident friendly smile",
    "a Latina woman in her mid twenties, long light-brown curly hair, hazel eyes, a playful smile",
    "an East Asian woman in her mid twenties, a sleek black bob, dark eyes, a cool confident look",
    "a European woman in her mid twenties, long honey-blonde hair, green eyes, a bright smile",
]
SHEET_PROMPT = ("A photorealistic full-body photo of a fictional pop singer, {look}. She stands facing the camera, "
                "relaxed, arms by her sides, the whole body from head to feet in frame, on a plain light studio "
                "background with soft even light. A stylish modern pop-star outfit: fitted jacket, top and "
                "trousers or a knee-length skirt, fashionable trainers. Classy and fully clothed, not suggestive. "
                "Vertical 9:16. No text, no logo, no watermark. Not a real or famous person.")
STILL_PROMPT = ("The same woman as in the reference photo: exactly the same face, hair, skin tone and body. A "
                "photorealistic full-body photo of her standing facing the camera, relaxed, arms by her sides, "
                "the whole body from head to feet in frame with some space around her. Her outfit and the place "
                "fit this song: \"{title}\", a {genre} song about {theme}. The scene: {scene}. A stylish outfit, "
                "classy and fully clothed, not suggestive. Natural light, sharp focus. Vertical 9:16. No text, no "
                "logo, no watermark, no other people.")


def key():
    """The fal.ai key: the environment, else .env read now (a key added while
    the server runs works without a restart)."""
    k = os.environ.get("FAL_KEY")
    if not k:
        try:
            from dotenv import dotenv_values
            k = dotenv_values(os.path.join(ROOT, ".env")).get("FAL_KEY")
        except Exception:  # noqa: BLE001 — no key then
            k = ""
    return (k or "").strip()


def character():
    """{"name", "look", "image"} of the chosen character, or None."""
    try:
        with open(CHARACTER_FILE, encoding="utf-8") as f:
            ch = json.load(f)
    except (OSError, ValueError):
        return None
    image = os.path.join(STATE_DIR, ch.get("image") or "")
    return {**ch, "image": image} if os.path.isfile(image) else None


def _spend():
    try:
        with open(SPEND_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def made_today(now=None):
    return int((_spend().get(f"{now or datetime.now():%Y-%m-%d}") or {}).get("count", 0))


def record(usd, now=None):
    data = _spend()
    day = f"{now or datetime.now():%Y-%m-%d}"
    row = data.get(day) or {"count": 0, "usd": 0.0}
    data[day] = {"count": row["count"] + 1, "usd": round(row["usd"] + usd, 3)}
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(SPEND_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(data.items())[-60:]), f, indent=1)


def available(now=None):
    """A dance Short can be made now: a fal key, a chosen character, room in today's budget."""
    return bool(key()) and character() is not None and made_today(now) < DAILY_MAX


def cost(seconds, resolution=RESOLUTION):
    return round(STILL_PRICE + seconds * PRICE.get(resolution, PRICE["480p"]), 2)


# ------------------------------------------------------------------ pictures

def _image(client, contents, out):
    from google.genai import types
    model = os.environ.get("GEMINI_IMAGE_MODEL") or "gemini-3.1-flash-image"
    r = client.models.generate_content(
        model=model, contents=contents,
        config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"],
                                           image_config=types.ImageConfig(aspect_ratio="9:16", image_size="1K")))
    for part in r.parts or []:
        if part.inline_data is not None and part.inline_data.data:
            with open(out, "wb") as f:
                f.write(part.inline_data.data)
            return out
    raise RuntimeError("the image model returned no picture")


def looks(client, out_dir, which=LOOKS):
    """One candidate picture per look, for the owner to choose from."""
    os.makedirs(out_dir, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(_image, client, [SHEET_PROMPT.format(look=look)],
                            os.path.join(out_dir, f"look_{k + 1}.png")) for k, look in enumerate(which)]
    out = []
    for k, j in enumerate(jobs):
        try:
            out.append(j.result())
        except Exception as e:  # noqa: BLE001 — the other looks still show
            print(f"   ⚠️ Look {k + 1} failed: {type(e).__name__}: {str(e)[:120]}")
    return out


def pick(path, name, look=""):
    """Keep ``path`` as the character's reference picture."""
    os.makedirs(STATE_DIR, exist_ok=True)
    shutil.copyfile(path, os.path.join(STATE_DIR, "character.png"))
    with open(CHARACTER_FILE, "w", encoding="utf-8") as f:
        json.dump({"name": name, "look": look, "image": "character.png", "since": int(time.time())}, f, indent=1)
    return character()


def still(client, ch, song, out):
    """Her, full body, in an outfit and place that fit ``song`` (title, genre, theme, scene)."""
    from PIL import Image
    with Image.open(ch["image"]) as ref:
        ref.load()
        return _image(client, [ref.convert("RGB"), STILL_PROMPT.format(**song)], out)


# ------------------------------------------------------------------ dance clips

def dance_clips(client, seconds, log=print):
    """Downloaded stock dance clips adding up to ``seconds`` (at most MAX_CLIPS):
    [{"path", "use", ...candidate}], or [] when too few pass the check."""
    import stock_media
    pool, seen = [], set()
    used = stock_media.recently_used()
    for term in DANCE_TERMS:
        for c in stock_media.search(term, portrait=True, kind="video"):
            if c["id"] not in seen and c["id"] not in used and c.get("seconds", 0) >= MIN_CLIP:
                seen.add(c["id"])
                pool.append(c)
    if not pool:
        return []
    scenes = [f"dance clip {k + 1}: one person dancing, whole body in frame" for k in range(MAX_CLIPS)]
    picks = [c for c in stock_media.choose(client, "an AI pop singer dancing to her song", scenes,
                                           [pool] * MAX_CLIPS, rule=DRIVE_RULE) if c]
    out, total = [], 0.0
    for c in picks:
        path = stock_media.download(c)
        if not path:
            continue
        use = min(c["seconds"] - 0.2, seconds - total)
        if use < MIN_CLIP and out:
            break
        out.append({**c, "path": path, "use": round(use, 2)})
        total += use
        if total >= seconds - 0.5:
            break
    if total < min(seconds, 8.0):
        log(f"   ℹ️ Only {total:.0f}s of usable dance clips.")
        return []
    stock_media.mark_used([c["id"] for c in out])
    return out


def driving(src, seconds, out):
    """The clip cut to ``seconds`` at 16 fps, 540x960, no sound: fal bills per 16 frames."""
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", src, "-t", f"{seconds:.2f}",
                    "-vf", f"scale=540:960:force_original_aspect_ratio=increase,crop=540:960,fps={DRIVE_FPS}",
                    "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out],
                   check=True, capture_output=True, timeout=300)
    return out


# ------------------------------------------------------------------ fal.ai

def _auth():
    return {"Authorization": f"Key {key()}"}


def upload(path, content_type):
    """A URL fal can read for a local file (fal's own storage, the fal_client steps)."""
    with open(path, "rb") as f:
        data = f.read()
    name = os.path.basename(path)
    try:
        t = httpx.post(TOKEN_URL, headers={**_auth(), "Content-Type": "application/json"}, json={}, timeout=30)
        t.raise_for_status()
        tok = t.json()
        r = httpx.post(UPLOAD_URL, content=data, timeout=300,
                       headers={"Authorization": f"{tok['token_type']} {tok['token']}",
                                "Content-Type": content_type, "X-Fal-File-Name": name})
        r.raise_for_status()
        return r.json()["access_url"]
    except (httpx.HTTPError, KeyError, ValueError):
        r = httpx.post(INITIATE_URL, headers={**_auth(), "Content-Type": "application/json"},
                       json={"file_name": name, "content_type": content_type}, timeout=30)
        r.raise_for_status()
        up = r.json()
        httpx.put(up["upload_url"], content=data, headers={"Content-Type": content_type},
                  timeout=300).raise_for_status()
        return up["file_url"]


def animate(image_url, video_url, out, resolution=RESOLUTION, sleep=time.sleep):
    """Her (``image_url``) doing the moves of ``video_url``; the result saved at ``out``."""
    r = httpx.post(QUEUE + MODEL, headers={**_auth(), "Content-Type": "application/json"}, timeout=60,
                   json={"image_url": image_url, "video_url": video_url, "resolution": resolution})
    r.raise_for_status()
    job = r.json()
    # Use the URLs fal returns: they name only owner/app, the full model path answers 405.
    status_url, response_url = job["status_url"], job["response_url"]
    waited = 0
    while True:
        s = httpx.get(status_url, headers=_auth(), timeout=60)
        s.raise_for_status()
        state = s.json()
        if state.get("status") == "COMPLETED":
            break
        if waited >= WAIT:
            httpx.put(job.get("cancel_url") or status_url, headers=_auth(), timeout=30)
            raise TimeoutError(f"fal did not finish in {WAIT // 60} min")
        sleep(POLL)
        waited += POLL
    res = httpx.get(response_url, headers=_auth(), timeout=60)
    body = res.json() if res.content else {}
    # A failed job also says COMPLETED; the error is in the result.
    if res.status_code >= 400 or state.get("error") or not (body.get("video") or {}).get("url"):
        raise RuntimeError(f"fal failed: {str(state.get('error') or body.get('detail') or body)[:200]}")
    with httpx.stream("GET", body["video"]["url"], timeout=300, follow_redirects=True) as v:
        v.raise_for_status()
        with open(out, "wb") as f:
            for block in v.iter_bytes(1 << 20):
                f.write(block)
    return out


def join(parts, seconds, out):
    """The animated clips one after another on the 1080x1920 canvas at 30 fps, ``seconds`` long."""
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error"]
    for p in parts:
        cmd += ["-i", p]
    chains = [f"[{k}:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase:flags=lanczos,"
              f"crop={OUT_W}:{OUT_H},fps={FPS},setsar=1,format=yuv420p[v{k}]" for k in range(len(parts))]
    graph = ";".join(chains) + ";" + "".join(f"[v{k}]" for k in range(len(parts))) + \
        f"concat=n={len(parts)}:v=1:a=0[out]"
    subprocess.run(cmd + ["-filter_complex", graph, "-map", "[out]", "-t", f"{seconds:.3f}", "-an",
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", out],
                   check=True, capture_output=True, timeout=900)
    return out


def dance_background(client, song, seconds, job_dir, log=print, animate_fn=None, upload_fn=None):
    """(video path, footage credits, $ spent) of her dancing for ``seconds``, or
    (None, [], 0). ``song``: title, genre, theme, scene. Never raises."""
    ch = character()
    if not ch or not key():
        return None, [], 0.0
    animate_fn, upload_fn = animate_fn or animate, upload_fn or upload
    spent = 0.0
    try:
        log(f"💃 {ch['name']} dances: picture and dance clips...")
        with ThreadPoolExecutor(max_workers=2) as pool:
            pic_later = pool.submit(still, client, ch, song, os.path.join(job_dir, ".dance_still.png"))
            clips = dance_clips(client, seconds, log)
            pic = pic_later.result()
        spent += STILL_PRICE
        if not clips:
            log("   ℹ️ No good dance clip this time; the song keeps its footage.")
            return None, [], spent
        image_url = upload_fn(pic, "image/png")
        drives = [driving(c["path"], c["use"], os.path.join(job_dir, f".dance_drive_{k}.mp4"))
                  for k, c in enumerate(clips)]
        log(f"   🪄 fal.ai animates {len(drives)} clip(s), {sum(c['use'] for c in clips):.0f}s at {RESOLUTION}...")
        with ThreadPoolExecutor(max_workers=MAX_CLIPS) as pool:
            parts = list(pool.map(lambda k: animate_fn(image_url, upload_fn(drives[k], "video/mp4"),
                                                       os.path.join(job_dir, f".dance_part_{k}.mp4")),
                                  range(len(drives))))
        spent += sum(c["use"] for c in clips) * PRICE.get(RESOLUTION, PRICE["480p"])
        total = sum(c["use"] for c in clips)
        path = join(parts, min(seconds, total), os.path.join(job_dir, ".dance_bg.mp4"))
        log(f"   ✅ Dance background: {min(seconds, total):.0f}s (about ${spent:.2f}).")
        return path, clips, round(spent, 3)
    except Exception as e:  # noqa: BLE001 — a song without her is still a song
        log(f"   ⚠️ No dance this time ({type(e).__name__}: {str(e)[:160]}); the song keeps its footage.")
        return None, [], round(spent, 3)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    if len(sys.argv) > 1 and sys.argv[1] == "looks":
        import short_kit as kit
        folder = sys.argv[2] if len(sys.argv) > 2 else os.path.join(STATE_DIR, "looks")
        for p in looks(kit.gemini(), folder):
            print(p)
    elif len(sys.argv) > 3 and sys.argv[1] == "pick":
        print(pick(sys.argv[2], sys.argv[3], " ".join(sys.argv[4:])))
    else:
        print("usage: python ai_influencer.py looks [folder] | pick <picture> <name> [look]")
