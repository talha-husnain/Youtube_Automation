"""The cartoon channel's weekly compilation: the week's episodes back to back as ONE long video (5-nov-2026).

Why: from 1-feb-2027 a new YouTube Partner Program applicant needs 8,000 watch hours in a year or 20M Shorts views
in 90 days (announced 10-aug-2026; vidIQ, RouteNote). Shorts views never count as watch hours, and our Shorts
channels are far from 20M, so watch hours are the reachable bar. Cartoon channels live on compilations of their own
episodes; ours are already made, so a compilation costs no Gemini at all, only the laptop's time.

Each episode is kept (``keep``) when it is made: its captioned file cut before the end card, and its first picture
for the thumbnail. When MIN_EPISODES new ones are waiting and the last compilation is EVERY_DAYS old, the channel's
next job is the compilation (my_channels._toon_mix_payload): the episodes joined in order with a title over the
first seconds, chapters in the description ("0:00 EP 12: ..."), a 1280x720 thumbnail of three episodes' pictures,
uploaded as a long video (youtube_account "toons_mix", Comedy) on top of the day's Shorts.
"""
import json
import os
import re
import subprocess
import time

import short_kit as kit

MIN_EPISODES = int(os.environ.get("TOON_MIX_MIN") or 7)
MAX_EPISODES = 16
EVERY_DAYS = 6
KEEP = 60                       # kept episode files; the oldest compiled ones go first


def _dir():
    import toon_shorts
    return os.path.join(toon_shorts.STATE_DIR, "episodes")


def _mixes_file():
    return os.path.join(_dir(), "mixes.json")


def mixes():
    try:
        with open(_mixes_file(), encoding="utf-8") as f:
            data = json.load(f)
        return [m for m in data.get("mixes") or [] if isinstance(m, dict)]
    except (OSError, ValueError, AttributeError):
        return []


def _save_mixes(rows):
    os.makedirs(_dir(), exist_ok=True)
    tmp = _mixes_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"mixes": rows[-100:]}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _mixes_file())


def kept():
    """[{"n", "title", "seconds", "file", "picture", "at"}] of the episodes on disk, oldest first."""
    out = []
    d = _dir()
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if not re.fullmatch(r"ep_\d{4}\.json", name):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as f:
                row = json.load(f)
        except (OSError, ValueError):
            continue
        row["file"] = os.path.join(d, name[:-5] + ".mp4")
        pic = os.path.join(d, name[:-5] + ".jpg")
        row["picture"] = pic if os.path.isfile(pic) else None
        if os.path.isfile(row["file"]):
            out.append(row)
    return sorted(out, key=lambda r: int(r.get("n") or 0))


def pending():
    done = {int(n) for m in mixes() for n in m.get("episodes") or []}
    return [r for r in kept() if int(r.get("n") or 0) not in done]


def keep(served, seconds, n, title, picture=None, log=print, focus=None):
    """Save episode ``n`` for the compilation: ``served`` cut at ``seconds`` (before the end card), re-encoded so
    the cut is exact; ``picture`` (its best close-up) for the thumbnail, ``focus`` = where across it (0-1) the
    speaking face is, so the thumbnail's narrow slice shows the face, not a tail. Never raises."""
    if os.environ.get("TOON_MIX", "1") == "0" or not served or not os.path.isfile(served):
        return None
    try:
        os.makedirs(_dir(), exist_ok=True)
        base = os.path.join(_dir(), f"ep_{int(n):04d}")
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", served, "-t", f"{seconds:.3f}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", base + ".mp4"],
                       check=True, capture_output=True, timeout=600)
        if picture and os.path.isfile(picture):
            from PIL import Image
            with Image.open(picture) as im:
                im.convert("RGB").save(base + ".jpg", "JPEG", quality=88)
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump({"n": int(n), "title": title, "seconds": round(seconds, 2), "at": int(time.time()),
                       **({"focus": round(min(1.0, max(0.0, float(focus))), 3)} if focus is not None else {})}, f,
                      ensure_ascii=False)
        _prune()
        return base + ".mp4"
    except Exception as e:  # noqa: BLE001 — the Short is what matters
        log(f"   ⚠️ Episode not kept for the compilation ({type(e).__name__}: {str(e)[:120]}).")
        return None


def _prune():
    rows = kept()
    done = {int(n) for m in mixes() for n in m.get("episodes") or []}
    extra = len(rows) - KEEP
    for r in rows:
        if extra <= 0:
            break
        if int(r["n"]) in done:
            for ext in (".mp4", ".jpg", ".json"):
                p = r["file"][:-4] + ext
                if os.path.exists(p):
                    os.remove(p)
            extra -= 1


def due(jobs=(), now=None):
    """True when the next compilation should be made: enough new episodes, the last one old enough, none today."""
    if os.environ.get("TOON_MIX", "1") == "0":
        return False
    now = now or time.time()
    if len(pending()) < MIN_EPISODES:
        return False
    last = max([int(m.get("at") or 0) for m in mixes()] + [0])
    if now - last < EVERY_DAYS * 86400:
        return False
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    return not any(j.get("format") == "mix" and j.get("day") == day for j in jobs or [])


def clock(seconds):
    s = int(seconds)                 # down: a chapter mark is never after its episode starts
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def chapters(rows, lead=0.0):
    """[(at, "EP n: title")]: YouTube makes chapters of "0:00 ..." lines when the first is at 0:00, there are three
    or more, and each is at least 10 seconds."""
    out, t = [], lead
    for k, r in enumerate(rows):
        name = re.sub(r"\s+", " ", re.sub(r"#\w+|[<>]", "", r.get("title") or "")).strip()
        out.append((0.0 if k == 0 else t, f"EP {r['n']}: {name}"[:90]))
        t += float(r.get("seconds") or 0)
    return out


def describe(rows, vol, handle=""):
    import toon_shorts
    lines = [f"Billo, Sheru, Mithu aur baby Guddu ki {len(rows)} episodes ek saath (vol. {vol}). Har episode mein "
             "ek naya kaand aur aakhir mein ek twist: aap ka favourite kaun sa hai? Comment mein episode number "
             "likho! 😹", ""]
    lines += [f"{clock(at)} {name}" for at, name in chapters(rows)]
    lines += ["", toon_shorts.SERIES_NOTE]
    if handle:
        lines += ["", f"Roz nayi episode: {handle} ko subscribe karo 🔔"]
    lines += ["", "#cartoon #funny #billoandgang"]
    return "\n".join(lines)


def title(rows, vol):
    return f"Billo aur Gang: {len(rows)} mazedaar episodes ek saath 😹 | Talking Animals Cartoon Comedy Vol {vol}"[:100]


def thumb(rows, vol, out):
    """1280x720: three episodes' pictures side by side, the compilation's name on top."""
    try:
        from PIL import Image
        import thumbnail as th
        pics = [r["picture"] for r in rows if r.get("picture")][:3]
        canvas = Image.new("RGB", (th.THUMB_W, th.THUMB_H), (59, 31, 92))
        if pics:
            w = th.THUMB_W // len(pics)
            for k, p in enumerate(pics):
                with Image.open(p) as im:
                    im = im.convert("RGB")
                    s = max(w / im.width, th.THUMB_H / im.height)
                    im = im.resize((max(w, round(im.width * s)), max(th.THUMB_H, round(im.height * s))))
                    x, y = (im.width - w) // 2, int((im.height - th.THUMB_H) * 0.35)
                    canvas.paste(im.crop((x, y, x + w, y + th.THUMB_H)), (k * w, 0))
        th.burn_thumbnail_text(canvas.convert("RGBA"), f"{len(rows)} EPISODES EK SAATH", "left",
                               "yellow").convert("RGB").save(out, "JPEG", quality=90)
        return out
    except Exception as e:  # noqa: BLE001 — YouTube picks a frame
        print(f"   ℹ️ No compilation thumbnail ({type(e).__name__}: {str(e)[:80]}).")
        return None


def join(rows, out, work):
    """The episodes back to back (re-encoded once, so files made weeks apart still join), the title over the first
    4 seconds."""
    lst = os.path.join(work, ".mix_list.txt")
    with open(lst, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write("file '" + r["file"].replace("\\", "/").replace("'", "'\\''") + "'\n")
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                        "-vf", f"scale={kit.OUT_W}:{kit.OUT_H}:force_original_aspect_ratio=decrease,"
                               f"pad={kit.OUT_W}:{kit.OUT_H}:(ow-iw)/2:(oh-ih)/2,fps={kit.FPS},format=yuv420p",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-c:a", "aac", "-b:a", "160k",
                        "-ar", "48000", "-ac", "2", "-movflags", "+faststart", out],
                       capture_output=True, text=True, errors="replace", timeout=3 * 3600)
    if r.returncode != 0:
        raise RuntimeError(f"compilation join failed: {r.stderr.strip()[-300:]}")
    return out


def run(output_dir, pipeline):
    import framed_layout as fl
    rows = pending()[:MAX_EPISODES]
    if len(rows) < 3:
        raise RuntimeError(f"Only {len(rows)} new episodes for a compilation; it waits for more.")
    vol = len(mixes()) + 1
    cfg = fl.settings()
    started = time.time()
    total = sum(float(r.get("seconds") or 0) for r in rows)
    print(f"📺 Cartoon compilation vol. {vol}: {len(rows)} episodes ({clock(total)})...")
    stem = kit.neutral_stem("ToonMix")
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    join(rows, final, output_dir)
    kit.level(final)
    seconds = total
    try:
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                "default=nw=1:nk=1", final], capture_output=True, text=True, timeout=60)
        seconds = float(probe.stdout.strip() or total)
    except (ValueError, subprocess.SubprocessError):
        pass
    pic = thumb(rows, vol, os.path.join(output_dir, "thumbnail.jpg"))
    name = title(rows, vol)
    clip = {"start": 0.0, "end": round(seconds, 3), "seconds": round(seconds, 3), "file": final,
            "video_title_for_youtube_short": name, "seo_title": name,
            "seo_description": describe(rows, vol, cfg.get("handle") or ""),
            "seo_tags": ["cartoon", "funny cartoon", "talking animals", "billi ki kahani", "cartoon comedy",
                         "urdu cartoon", "hindi cartoon", "billo and gang", "funny cat", "compilation"],
            "why": f"Cartoon compilation vol. {vol}", "predicted_score": 80, "genre": "toons",
            "ai_voice": "AI voices and pictures", "ai_made": True,
            "comment_question": "Sab se mazedaar episode kaunsi thi? Number likho 👇",
            "thumbnail_file": os.path.basename(pic) if pic else None,
            "chapters": [{"title": t, "at": round(a, 2)} for a, t in chapters(rows)],
            "toon_mix": {"vol": vol, "episodes": [int(r["n"]) for r in rows]}}
    kit.finish(output_dir, stem, [clip], None, pipeline, extra={"genre": "toons", "format": "9:16 long"})
    data = mixes()
    data.append({"vol": vol, "episodes": [int(r["n"]) for r in rows], "at": int(time.time()),
                 "job": os.path.basename(os.path.normpath(output_dir))})
    _save_mixes(data)
    print(f"   ⏱️ Compilation made in {(time.time() - started) / 60:.1f} min.")
    return final
