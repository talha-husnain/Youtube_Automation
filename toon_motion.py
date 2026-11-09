"""Billo aur Gang as real animated episodes (owner, 9-nov-2026: "I want real cartoon ... proper lip sync and all just
like real cartoons. It's not just like voiceover over the picture ... there should be a proper storyline").

The picture episodes (toon_shorts: one still per shot, a mouth patch flapping, a slow zoom) are replaced by moving
scenes from Google's video model, Gemini Omni Flash, through the same Gemini key. Each scene is one continuous shot of
3-15 s in which the characters move and SPEAK their own lines (the model makes the voices, sounds and lip-sync
together); the character reference pictures (state/toons/cast) keep Billo, Sheru, Mithu and Guddu the same from scene
to scene. The model takes at most 2 characters with references per request, so a scene shows 1-2 of them.

Cost (owner chose 9-nov-2026: 360p, one episode a day): Omni bills per second of video, ~$0.03 at 360p (third-party
price pages, Nov 2026; $0.10 at 720p). An episode of ~30-40 s is ~$1-1.2; the 360x640 video is made 1080x1920 on this
laptop by Real-ESRGAN's anime model (upscale.py, free). TOON_VIDEO_SECONDS_PER_DAY caps the seconds made a day.

Language: Omni's docs (Nov 2026) call English "fully supported" and other languages "not evaluated", so the first
episodes are checked by the owner before the channel runs on its own.

Env: TOON_MOTION=0 goes back to the picture episodes; TOON_VIDEO_MODEL (gemini-omni-1.2-flash), TOON_VIDEO_RES
(360p), TOON_VIDEO_SECONDS_PER_DAY (60), TOON_UPSCALE=0 resizes without Real-ESRGAN.
"""
import base64
import json
import math
import os
import re
import shutil
import subprocess
import time
from types import SimpleNamespace
from typing import List

from pydantic import BaseModel

import short_kit as kit
import toon_shorts as ts

MODEL = os.environ.get("TOON_VIDEO_MODEL") or "gemini-omni-1.2-flash"
PRICE = {"360p": 0.03, "720p": 0.10, "1080p": 0.15}       # $ per second of video (estimates, see above)
SIZE = {"360p": (360, 640), "720p": (720, 1280), "1080p": (1080, 1920)}
MIN_SCENES, MAX_SCENES = 3, 5
MIN_SECONDS, MAX_SECONDS = 24, 44                           # the whole episode
SCENE_MIN, SCENE_MAX = 4, 12                                # one scene (Omni allows 3-15 s)
WORDS_PER_SECOND = 2.4                                      # everyday Urdu speech, a little brisk
SCENE_WORDS = 24
TRIES = 2

MOTION_STYLE = ("A 3D animated family-film scene: smooth, expressive character animation with real body movement, "
                "gestures and facial expressions; soft global illumination, warm colours, rounded friendly shapes, big "
                "expressive eyes; a middle-class Pakistani home and neighbourhood. Vertical 9:16 frame, the "
                "characters large and clearly visible. No text, letters, subtitles, captions, logos or watermarks.")
VOICES = {"billo": "a sassy, dramatic young woman's voice", "sheru": "a slow, deep, sleepy, goofy man's voice",
          "mithu": "a fast, squeaky, cheeky high voice", "guddu": "a cute toddler's voice that talks like a grumpy "
          "50-year-old uncle", "ammi": "a busy Pakistani mother's voice"}


def resolution():
    r = (os.environ.get("TOON_VIDEO_RES") or "360p").strip().lower()
    return r if r in PRICE else "360p"


def _int_env(name, default):
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


# ------------------------------------------------------------------ the script

class SceneLine(BaseModel):
    speaker: str
    text: str
    delivery: str


class Scene(BaseModel):
    place: str
    who: List[str]
    action: str
    lines: List[SceneLine]
    sound: str = ""


class MotionEpisode(BaseModel):
    title: str
    hook_caption: str
    premise: str
    point: str
    shape: str
    scenes: List[Scene]
    twist: str
    question: str


STORY = """STORY FIRST (a pile of jokes is not an episode; the owner rejected those): before any line, know
- who WANTS what, and what stands in the way;
- how it ESCALATES (each scene bigger than the last);
- the TWIST nobody saw coming that still makes sense, and the PAYOFF line;
- the POINT: a small truth about desi family life everyone recognises (the guest who never leaves, the remote war,
  Ammi always knowing), shown through the comedy, never said as a moral.
Viewers decide in the first 2 seconds: scene 1 opens IN the trouble, its first line spoken at once.

SCENES: {lo}-{hi} scenes, each ONE continuous animated shot of 4-12 seconds, about {total} seconds in all.
- who: the 1-2 on-screen characters in the scene (cast keys; ammi is never on screen, only heard).
- action: 1-3 English sentences of what we SEE: how the characters move and react, props, where they look, the
  camera (close-up for a punchline, wider for a reveal). This is animation: show physical comedy, not talking heads.
- lines: 0-3 spoken lines, each: speaker (cast key; must be in who, or ammi off screen), text (Roman Urdu / Hinglish
  in Latin letters, everyday words Indians understand too, 12 words or fewer) and delivery (English: how it is said,
  e.g. "whispering, guilty", "outraged, loud"). At most {sw} words in a scene: a 10-second scene holds ~20 words.
  A silent scene of pure action is welcome when the picture is the joke.
- sound: the sound effects of the scene in English (a pressure-cooker whistle, a door creak); no music.
The LAST line of the last scene is the punchline: short, so the episode ends on the laugh and a replay feels natural.
No narrator, no greeting, no outro, no "like aur subscribe".
Comedy shape for this episode: {shape}
Never use these stale phrases: {banned}."""

WRITE_PROMPT = """You are the head writer of an original ANIMATED comedy series of YouTube Shorts and Instagram Reels for
Pakistani and Indian viewers: talking animals and a talking baby in one middle-class Lahore home. Real animation: the
characters move, act and speak with lip-sync. Episode {n}.

{bible}

Earlier episodes (for continuity; you may call back to one, never retell one):
{earlier}

THIS EPISODE'S PREMISE: {premise}

{story}

NEVER: {rules}.

Return: title (Roman Urdu, 4-9 words, the situation that makes people click, may end with one emoji), hook_caption
(2-6 words shown at the start for sound-off viewers), premise (one sentence), point (one sentence: the truth it shows),
shape (the key: {shape_key}), scenes, twist (one sentence), question (a comment question with a one-word answer people
will argue about, Roman Urdu).
{fixes}"""


def seconds_of(scene):
    words = sum(len(l.text.split()) for l in scene.lines)
    return max(SCENE_MIN, min(SCENE_MAX, math.ceil(words / WORDS_PER_SECOND + 2.5)))


def script_text(ep):
    out = [f"TITLE: {ep.title}", f"HOOK CAPTION: {ep.hook_caption}", f"PREMISE: {ep.premise}", f"POINT: {ep.point}",
           f"SHAPE: {ep.shape}"]
    for k, s in enumerate(ep.scenes):
        out.append(f"SCENE {k + 1} ({seconds_of(s)} s) [{s.place}; {', '.join(s.who)}]: {s.action}"
                   + (f" SOUND: {s.sound}" if s.sound else ""))
        out += [f"   {l.speaker} ({l.delivery}): {l.text}" for l in s.lines]
    out += [f"TWIST: {ep.twist}", f"QUESTION: {ep.question}"]
    return "\n".join(out)


def tidy(ep):
    for s in ep.scenes:
        s.place = (s.place or "").strip().lower()
        s.who = [w.strip().lower() for w in s.who if (w or "").strip()]
        lines = []
        for l in s.lines:
            l.speaker = (l.speaker or "").strip().lower()
            l.text = re.sub(r"\s+", " ", l.text or "").strip()
            l.delivery = re.sub(r"\s+", " ", l.delivery or "").strip()[:80]
            if l.text:
                lines.append(l)
        s.lines = lines
    ep.shape = (ep.shape or "").strip().lower()
    if ep.shape not in ts.SHAPES:
        ep.shape = next((k for k, v in ts.SHAPES.items()
                         if ep.shape.startswith(k) or ep.shape.startswith(v.split(":")[0].lower())), ep.shape[:20])
    return ep


def problems(ep):
    """What the code finds wrong: [] means it can be animated."""
    import script_craft as craft
    out = []
    if not MIN_SCENES <= len(ep.scenes) <= MAX_SCENES:
        out.append(f"it has {len(ep.scenes)} scenes: write {MIN_SCENES}-{MAX_SCENES}")
    total = sum(seconds_of(s) for s in ep.scenes)
    if not MIN_SECONDS <= total <= MAX_SECONDS:
        out.append(f"it runs ~{total} s: write {MIN_SECONDS + 4}-{MAX_SECONDS - 4} s of scenes")
    speakers = set()
    for k, s in enumerate(ep.scenes):
        tag = f"scene {k + 1}"
        if s.place not in ts.PLACES:
            out.append(f"{tag}: place '{s.place}' is not one of {', '.join(ts.PLACES)}")
        bad = [w for w in s.who if w not in ts.CAST or ts.CAST[w].get("onscreen") is False]
        if bad:
            out.append(f"{tag} shows {', '.join(bad)}: only on-screen cast keys")
        if not 1 <= len(s.who) <= 2 or len(set(s.who)) != len(s.who):
            out.append(f"{tag} has {len(s.who)} characters: 1 or 2 different ones (the video model keeps 2 at most)")
        if len(s.lines) > 3:
            out.append(f"{tag} has {len(s.lines)} lines: 3 at most")
        words = sum(len(l.text.split()) for l in s.lines)
        if words > SCENE_WORDS:
            out.append(f"{tag} has {words} words: {SCENE_WORDS} at most (it must fit 12 seconds)")
        if len((s.action or "").split()) < 6:
            out.append(f"{tag}: the action says too little of what we see")
        for l in s.lines:
            if l.speaker not in ts.CAST:
                out.append(f"{tag}: speaker '{l.speaker}' is not a cast key")
                continue
            speakers.add(l.speaker)
            if ts.CAST[l.speaker].get("onscreen") is not False and l.speaker not in s.who:
                out.append(f"{tag}: {l.speaker} speaks but is not in the scene")
            if len(l.text.split()) > 12:
                out.append(f"{tag}: a line has {len(l.text.split())} words: 12 or fewer")
            if ts.NON_LATIN.search(l.text):
                out.append(f"{tag}: a line is not in Latin letters")
            hits = craft.banned_hits(l.text)
            if hits:
                out.append(f"{tag}: stale phrases {', '.join(hits)}")
    if not ep.scenes or not ep.scenes[0].lines:
        out.append("scene 1 has no line: the hook is spoken at once")
    if not any(s.lines for s in ep.scenes[-1:]):
        out.append("the last scene has no line: it ends on the spoken punchline")
    if len(speakers) < 2:
        out.append("only one character speaks: it is a story between two or more")
    if ts.NON_LATIN.search(ep.title + " " + ep.hook_caption + " " + ep.question):
        out.append("the title, hook caption or question is not in Latin letters")
    return out


def _craft(shape):
    import script_craft as craft
    return STORY.format(lo=MIN_SCENES, hi=MAX_SCENES - 1, total="30-38", sw=SCENE_WORDS - 4,
                        shape=ts.SHAPES.get(shape, shape), banned=", ".join(craft.BANNED[:40]))


def draft(client, premise, shape, n, rows, fixes=""):
    import ai_fallback
    with ai_fallback.best_writer():
        ep = kit.ask_json(client, MotionEpisode, WRITE_PROMPT.format(
            n=n, bible=ts.bible(), earlier=ts._earlier(rows), premise=premise, story=_craft(shape),
            rules=ts.RULES, shape_key=shape, fixes=fixes), model=ts._model())
    return tidy(ep)


def write(client, premise, shape=None, rows=None, n=None, log=print):
    """Two drafts on two comic shapes, the judge's pick, then the safety check; raises when none passes."""
    import ai_fallback
    rows = ts.episodes() if rows is None else rows
    n = n or ts.next_number()
    drafts = []
    for s in ts.pick_shapes(rows, shape):
        d = ts._safe(lambda s=s: draft(client, premise, s, n, rows))
        if d is not None and problems(d):
            log(f"   ✏️ Draft ({s}) has {len(problems(d))} problem(s); fixing it.")
            d = ts._safe(lambda s=s, d=d: draft(client, premise, s, n, rows, fixes=(
                "\nFix these problems of the last version:\n- " + "\n- ".join(problems(d)[:12]))))
        if d is not None and not problems(d):
            drafts.append(d)
    if not drafts:
        raise RuntimeError("No script passed the checks (or the AI is down); made again later.")
    chosen = drafts[0]
    if len(drafts) == 2:
        try:
            with ai_fallback.best_writer():
                pick = kit.ask_json(client, ts.Pick, ts.JUDGE_PROMPT.format(one=script_text(drafts[0]),
                                                                           two=script_text(drafts[1])),
                                    model=ts._model())
            chosen = drafts[1] if pick.better == 2 else drafts[0]
        except Exception as e:  # noqa: BLE001 — draft 1 goes on
            log(f"   ⚠️ The draft judge failed ({type(e).__name__}); keeping draft 1.")
    with ai_fallback.best_writer():
        check = kit.ask_json(client, ts.Check, ts.CHECK_PROMPT.format(rules=ts.RULES, episode=script_text(chosen)),
                             model=ts._model())
    if not check.ok:
        raise RuntimeError("The script check found: " + "; ".join(check.problems[:3])[:300])
    return chosen


# ------------------------------------------------------------------ the video

def _spend_file():
    return os.path.join(ts.STATE_DIR, "video_spend.json")


def _spend():
    try:
        with open(_spend_file(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def spent_today():
    return float((_spend().get(time.strftime("%Y-%m-%d")) or {}).get("seconds", 0))


def _add_spend(seconds):
    d = _spend()
    day = time.strftime("%Y-%m-%d")
    row = d.get(day) or {"seconds": 0, "usd": 0.0, "clips": 0}
    row = {"seconds": row["seconds"] + seconds, "clips": row.get("clips", 0) + 1,
           "usd": round(row["usd"] + seconds * PRICE[resolution()], 3)}
    d[day] = row
    d = {k: d[k] for k in sorted(d)[-60:]}
    os.makedirs(ts.STATE_DIR, exist_ok=True)
    tmp = _spend_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, _spend_file())


def clip_prompt(ep, k):
    """The text of scene ``k``: its references are passed as pictures, in the order of ``s.who``."""
    s = ep.scenes[k]
    secs = seconds_of(s)
    refs = "; ".join(f"picture {i + 1} is {ts.CAST[w]['name']} the {ts.CAST[w]['what']} ({ts.CAST[w]['look']})"
                     for i, w in enumerate(s.who))
    talk = []
    for l in s.lines:
        c = ts.CAST[l.speaker]
        where = " from off screen (another room, never seen)" if c.get("onscreen") is False else ""
        talk.append(f'- {c["name"]}{where}, in {VOICES.get(l.speaker, "a natural voice")}, {l.delivery}: "{l.text}"')
    speech = ("\nDialogue, spoken aloud in Hindi-Urdu (Hindustani) with a natural Lahore accent, in this order, each "
              "character's mouth moving in sync with their own words only, the others listening and reacting:\n"
              + "\n".join(talk) if talk else "\nNo one speaks in this scene.")
    first = "\nThe first words are spoken at once, in the first second." if k == 0 and s.lines else ""
    return (f"{MOTION_STYLE}\nThe reference pictures show the characters; keep each exactly as drawn there (same "
            f"colours, shape and clothes): {refs}.\nPlace: {ts.PLACES.get(s.place, s.place)}.\n"
            f"One continuous shot of {secs} seconds: {s.action}{speech}{first}\n"
            f"Sound: the room's natural sound{', ' + s.sound if s.sound else ''}; no background music, no narrator.")


def make_clip(client, ep, k, refs, out, log=print):
    """Scene ``k`` as an mp4 (video and its sound) at ``out``; raises after TRIES."""
    s = ep.scenes[k]
    secs = seconds_of(s)
    parts = []
    for w in s.who:
        with open(refs[w], "rb") as f:
            parts.append({"type": "image", "data": base64.b64encode(f.read()).decode(), "mime_type": "image/png"})
    parts.append({"type": "text", "text": clip_prompt(ep, k)})
    last = None
    for attempt in range(TRIES):
        try:
            it = client.interactions.create(model=MODEL, input=parts, response_format={
                "type": "video", "resolution": resolution(), "aspect_ratio": "9:16", "duration": f"{secs}s"})
            video = getattr(it, "output_video", None)
            data = getattr(video, "data", None) if video else None
            if not data:
                raise RuntimeError("the video model returned no video")
            with open(out, "wb") as f:
                f.write(base64.b64decode(data))
            _add_spend(secs)
            return out
        except Exception as e:  # noqa: BLE001
            last = e
            msg = f"{type(e).__name__} {e}"
            if "credits are depleted" in msg or "'code': 402" in msg:
                raise RuntimeError("Gemini has no credit: the cartoon's video needs it (top up in Google AI Studio "
                                   "> Billing).") from e
            log(f"   ⚠️ Scene {k + 1} failed ({str(e)[:120]}); {'trying again' if attempt + 1 < TRIES else 'giving up'}.")
            time.sleep(5)
    raise RuntimeError(f"Scene {k + 1} could not be animated: {str(last)[:200]}")


def _has_audio(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of",
                        "csv=p=0", path], capture_output=True, text=True, timeout=60)
    return bool(r.stdout.strip())


def _seconds(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True, timeout=60)
    return float(r.stdout.strip() or 0)


def join(clips, out):
    """The scenes one after another at one size, 30 fps, 48 kHz stereo (a clip without sound gets silence).
    Returns [(start, end)] of each scene in the joined video."""
    w, h = SIZE[resolution()]
    cmd, graph, cat, times, t = ["ffmpeg", "-nostdin", "-y", "-v", "error"], [], "", [], 0.0
    for i, c in enumerate(clips):
        secs = _seconds(c)
        cmd += ["-i", c]
        graph.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={kit.FPS},"
                     f"setsar=1,format=yuv420p,trim=duration={secs:.3f},setpts=PTS-STARTPTS[v{i}]")
        if _has_audio(c):
            graph.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=duration={secs:.3f},"
                         f"apad=whole_dur={secs:.3f},asetpts=PTS-STARTPTS[a{i}]")
        else:
            graph.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={secs:.3f}[a{i}]")
        cat += f"[v{i}][a{i}]"
        times.append((round(t, 3), round(t + secs, 3)))
        t += secs
    graph.append(f"{cat}concat=n={len(clips)}:v=1:a=1[v][a]")
    cmd += ["-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium",
            "-crf", "16", "-c:a", "aac", "-b:a", "192k", out]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"joining the scenes failed: {r.stderr.strip()[-300:]}")
    return times


def to_canvas(src, out, log=print):
    """``src`` at 1080x1920: Real-ESRGAN's anime model when installed (360p x3 is exactly the canvas), then a
    lanczos resize to the canvas whatever came out."""
    big = src
    if os.environ.get("TOON_UPSCALE", "1") != "0":
        try:
            import upscale
            if upscale.available():
                scale = max(2, min(4, round(kit.OUT_W / SIZE[resolution()][0])))
                big = upscale.video(src, src[:-4] + "_up.mp4", scale)
        except Exception as e:  # noqa: BLE001 — resized instead
            log(f"   ⚠️ Upscaling skipped ({type(e).__name__}: {str(e)[:100]}).")
            big = src
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", big, "-vf",
                        f"scale={kit.OUT_W}:{kit.OUT_H}:flags=lanczos,setsar=1,fps={kit.FPS}", "-c:v", "libx264",
                        "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "copy", out],
                       capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"resizing failed: {r.stderr.strip()[-300:]}")
    return out


def wav_of(src, out, start=None, end=None):
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}", "-to", f"{end:.3f}"]
    cmd += ["-i", src, "-vn", "-ar", "48000", "-ac", "2", out]
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    return out


def make_video(client, ep, work, log=print):
    """(canvas video, its sound as wav, [(start, end)] per scene, [scene wav])."""
    planned = sum(seconds_of(s) for s in ep.scenes)
    cap = _int_env("TOON_VIDEO_SECONDS_PER_DAY", 60)
    if spent_today() + planned > cap:
        raise RuntimeError(f"Today's cartoon video budget is used ({spent_today():.0f} of {cap} s made today; this "
                           f"episode needs {planned} s). The next one is made tomorrow.")
    refs = {w: ts.cast_ref(client, w) for w in sorted({w for s in ep.scenes for w in s.who})}
    clips = []
    for k in range(len(ep.scenes)):
        log(f"   🎬 Scene {k + 1}/{len(ep.scenes)} ({seconds_of(ep.scenes[k])} s, "
            f"{', '.join(ts.CAST[w]['name'] for w in ep.scenes[k].who)})...")
        clips.append(make_clip(client, ep, k, refs, os.path.join(work, f"scene{k + 1}.mp4"), log))
    joined = os.path.join(work, "joined.mp4")
    times = join(clips, joined)
    log(f"   🔍 Sharpening {times[-1][1]:.0f} s of video to 1080x1920 on this PC...")
    canvas = to_canvas(joined, os.path.join(work, "canvas.mp4"), log)
    sound = wav_of(joined, os.path.join(work, "sound.wav"))
    scene_wavs = [wav_of(joined, os.path.join(work, f"scene{k + 1}.wav"), a, b) for k, (a, b) in enumerate(times)]
    return canvas, sound, times, scene_wavs


# ------------------------------------------------------------------ on screen

def text_events(ep, times, n, body_end):
    """The hook caption (sound-off viewers), the episode tag and each speaker's name the first time they talk."""
    W = kit.OUT_W
    ev = []
    hook = re.sub(r"[{}\\]", "", ep.hook_caption or "").strip()[:48].upper()
    if hook:
        ev.append(kit.dialogue(5, 0.0, min(body_end, 2.6), "TnHook",
                               rf"{{\an5\pos({W // 2},330)\fscx92\fscy92\t(0,180,\fscx100\fscy100)\fad(0,200)}}{hook}"))
    ev.append(kit.dialogue(4, 0.0, body_end, "TnEp", rf"{{\an5\pos({W // 2},170)\alpha&H30&}}EP {n}"))
    seen = set()
    for s, (a, b) in zip(ep.scenes, times):
        span = (b - a) / max(1, len(s.lines))
        for i, l in enumerate(s.lines):
            if l.speaker in seen or l.speaker not in ts.CAST:
                continue
            seen.add(l.speaker)
            c = ts.CAST[l.speaker]
            t0 = a + 0.3 + i * span
            name = c["name"].upper() + (" (AWAAZ)" if c.get("onscreen") is False else "")
            ev.append(kit.dialogue(6, t0, min(b, t0 + 1.8), "TnName",
                                   rf"{{\an5\pos({W // 2},{ts.NAME_Y})\3c{ts._ass(c['colour'])}"
                                   rf"\fscx70\fscy70\t(0,140,\fscx100\fscy100)\fad(60,160)}}{name}"))
    return ev


def captions(ep, times, scene_wavs):
    """Each scene's lines spread over the moments its sound is speech (kit.timed_transcript)."""
    rows = []
    for s, (a, b), wav in zip(ep.scenes, times, scene_wavs):
        text = " ".join(l.text for l in s.lines)
        if text:
            rows.append((text, a + 0.15, max(a + 0.5, b - 0.1), wav))
    return kit.timed_transcript(rows)


def frame_at(video, t, out):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1",
                    "-q:v", "2", out], capture_output=True, timeout=120)
    return out if os.path.isfile(out) else None


# ------------------------------------------------------------------ the job

def run(output_dir, pipeline):
    import credits
    import framed_layout as fl
    import toon_mix
    premise = re.sub(r"\s+", " ", os.environ.get("TOON_PREMISE") or "").strip()[:240]
    shape = (os.environ.get("TOON_SHAPE") or "").strip().lower() or None
    os.environ["STOCK_FOOTAGE"] = "0"
    cfg = fl.settings()
    client = kit.gemini()
    rows_before = ts.episodes()
    if len(premise) < 10:
        import ai_fallback
        with ai_fallback.best_writer():
            ideas = ts.channel_ideas(client, 1, notes=(
                "About half the ideas are led by baby Guddu (the talking-baby trend: a baby with a grown-up's "
                "opinions on family life). Every idea is a real little story with a twist, not a sketch."))
        if not ideas:
            raise RuntimeError("No new episode idea came back; made again later.")
        premise, shape = ideas[0]["text"], ideas[0].get("shape")
    n = ts.next_number()
    print(f"🐱 Animated episode {n}: \"{premise}\"")
    ep = write(client, premise, shape, rows_before, n)
    print(f"   ✅ {ep.title} | {len(ep.scenes)} scenes, ~{sum(seconds_of(s) for s in ep.scenes)} s ({ep.shape}); "
          f"point: {ep.point[:100]}")
    stem = kit.neutral_stem("Toon")
    work = os.path.join(output_dir, f".{stem}_scenes")
    os.makedirs(work, exist_ok=True)
    print(f"🎞️ Animating {len(ep.scenes)} scenes with {MODEL} at {resolution()}...")
    canvas, sound, times, scene_wavs = make_video(client, ep, work)
    body_end = times[-1][1]
    outro_s = kit.outro_seconds(cfg)
    card_ev, card_sfx = kit.end_card(body_end, outro_s)
    total = body_end + (outro_s if card_ev else 0.0)
    if total > body_end:
        # The end card sits on the last frame held still.
        held = os.path.join(work, "canvas_held.mp4")
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", canvas, "-vf",
                        f"tpad=stop_mode=clone:stop_duration={total - body_end + 0.2:.3f}", "-an", "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", held], check=True,
                       capture_output=True, timeout=900)
        canvas = held
    final = os.path.join(output_dir, f"{stem}_clip_1.mp4")
    transcript = captions(ep, times, scene_wavs)
    kit.render(final, total, [cfg["bg"], cfg["bg"]], text_events(ep, times, n, body_end) + card_ev, ts.STYLES,
               voices=[(sound, 0.0)], sfx=card_sfx, bg_video=canvas, fast=True)
    lines = [l for s in ep.scenes for l in s.lines]
    cast = sorted({l.speaker for l in lines})
    clip = {"start": 0.0, "end": round(total, 3), "seconds": round(total, 3), "file": final,
            "video_title_for_youtube_short": ep.title, "viral_hook_text": lines[0].text if lines else ep.hook_caption,
            "why": f"Animated cartoon episode {n}: {ep.premise}", "predicted_score": 90, "captions": transcript,
            "genre": "toons", "ai_voice": "AI voice", "comment_question": ep.question,
            "toon": ep.model_dump(), "episode": n, "background_music": None}
    kit.seo_or_fail([clip], transcript, source_title=ep.title,
                    context=ts.SEO_CONTEXT.format(n=n, cast=", ".join(f"{ts.CAST[c]['name']} the {ts.CAST[c]['what']}"
                                                                       for c in cast),
                                                  premise=ep.premise, twist=ep.twist), text_limit=3000)
    for field in ("seo_description", "video_description_for_instagram"):
        if clip.get(field):
            clip[field] = credits.insert(clip[field], ts.SERIES_NOTE.replace("pictures and voices",
                                                                             "animation and voices"))
    kit.finish(output_dir, stem, [clip], transcript, pipeline, extra={"genre": "toons"})
    ts.record(SimpleNamespace(premise=ep.premise, title=ep.title, twist=ep.twist, shape=ep.shape, lines=lines), n)
    a, b = times[0]
    toon_mix.keep(clip.get("served") or final, body_end, n, clip.get("seo_title") or ep.title,
                  frame_at(canvas, (a + b) / 2, os.path.join(work, "thumb.jpg")))
    if os.environ.get("TOON_KEEP_ART", "0") != "1":
        shutil.rmtree(work, ignore_errors=True)
