"""Funny Urdu dub of movie scenes (CONTENT_GENRE=movies).

YouTube's reused-content page lists "a scene from a movie where you've
rewritten the dialog and changed the voiceover" as something that can earn
(support.google.com/youtube/answer/1311392, read 8-oct-2026), while
"unedited clips from others' movies or TV shows" cannot (answer/12504220).
So this mode never posts a scene as it was: Gemini picks dialogue scenes,
looks at one frame per line to see who is talking, and rewrites every line as
a desi comedy in Roman Urdu; Gemini voices read the new lines in the
original timing, one voice per character; the original sound is muted
completely (dialogue and score). The picture is the framed look: cropped
scene on the brand colour, title above, the new lines as captions below.

Content ID still matches the picture, so a scene can still be claimed or
blocked; keep Shorts under a minute. Never names the movie, actors or
characters.

Env: CLIP_TARGET_MAX (scenes, default 2, max 3).
"""
import os
import re
import shutil
import subprocess
from typing import List

from pydantic import BaseModel

import short_kit as kit
import framed_layout as fl

DEFAULT_SCENES = 2
MIN_SCENE, MAX_SCENE = 18, 50
WORDS_PER_SECOND = 2.6
MAX_TEMPO = 1.3
_SOUND_TAG = re.compile(r"^\s*[\[(].*[\])]\s*$")


class Scene(BaseModel):
    start: float
    end: float
    why: str


class ScenePick(BaseModel):
    scenes: List[Scene]


class DubLine(BaseModel):
    index: int
    speaker: str
    gender: str
    emotion: str
    text: str


class Dub(BaseModel):
    premise: str
    title: str
    lines: List[DubLine]


PICK_PROMPT = """Below is the timed dialogue of a movie or show (seconds, then the line).
Pick the {n} scenes that would be funniest when re-dubbed with brand-new comic Urdu
dialogue: a clear back-and-forth conversation between 2-3 people, faces on screen,
drama or tension in the original, at least 5 lines. Each scene {lo}-{hi} seconds, starting
at the start of a line and ending after the end of a line, no two overlapping.

{lines}

Return {{"scenes": [{{"start": 0.0, "end": 0.0, "why": "..."}}]}}"""

DUB_PROMPT = """Re-dub this movie scene as a comedy for Pakistani and Indian viewers. The
frames are in line order: frame k shows the screen while line k is spoken; use them to
decide who says each line (speaker A, B or C, the same letter for the same person all
through) and their gender (male or female).

Write a brand-new funny premise that has nothing to do with the original plot, a desi
everyday situation (rishta aunty, biryani vs pulao, load-shedding, exam results, the
WhatsApp family group, cricket fights, salary day...), and new dialogue for EVERY line:
- Every line is a joke or sets up the next one, and the last line is the strongest
  punchline. Use desi exaggeration, taunts, sarcasm and filmy over-acting; the more
  serious the faces look, the sillier the words.
- Roman Urdu in Latin letters, everyday spoken words.
- Line k must fit its slot: at most {wps} words per second of the slot (the slot length
  is given), so short slots get short lines.
- Make the lines react to what the faces and actions in the frames show.
- Naughty, not dirty: double meaning and innuendo are fine, never a swear word, crude
  slang or an explicitly sexual word, never jokes about religion, caste, ethnicity or
  children.
- Never use the real names of the movie, the actors or the characters.
- emotion: one or two words for how the line is said (angry, shocked, sarcastic...).
Also return premise (one sentence in Roman Urdu) and title: max 45 characters, the on-screen hook in
Roman Urdu, no emoji.

Lines (index, slot seconds, original words for timing only):
{lines}"""

SEO_CONTEXT = ("IMPORTANT: this short is NOT stand-up comedy. It is a funny Urdu dub: a movie "
               "scene with brand-new comic dialogue written and voiced by the channel. New "
               "premise: {premise}. Ignore the stand-up phrases and hashtags above and use dub "
               "searches instead ('funny dubbing', 'urdu dubbing', 'funny dub', 'desi dub', "
               "'comedy dubbing', the premise's topic). Never name the movie, the actors or the "
               "characters (creator is \"\").")


LINE_GAP = 0.45     # a pause this long ends a spoken line
LINE_MAX = 4.5      # seconds
LINE_WORDS = 12


def _lines(transcript, start, end):
    """Spoken lines inside [start, end] as (start, end, text), sound tags dropped.

    Built from word times, split at pauses: a Whisper transcript (a video
    with no captions) comes in segments of up to 50 s, which hid every scene
    from the picker (first dub test, 8-oct-2026)."""
    words = [w for s in (transcript or {}).get("segments") or [] for w in s.get("words") or []
             if (w.get("word") or "").strip() and not _SOUND_TAG.match(w["word"])
             and start <= float(w["start"]) < end]
    out, cur = [], []
    for w in words:
        if cur and (float(w["start"]) - float(cur[-1]["end"]) >= LINE_GAP
                    or float(w["end"]) - float(cur[0]["start"]) > LINE_MAX or len(cur) >= LINE_WORDS):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return [(max(start, float(c[0]["start"])), min(end, float(c[-1]["end"])),
             "".join(w["word"] for w in c).strip()) for c in out
            if float(c[-1]["end"]) - float(c[0]["start"]) >= 0.4]


def pick_scenes(client, transcript, n, duration):
    rows = "\n".join(f"{s:.1f}-{e:.1f}: {t}" for s, e, t in _lines(transcript, 0, duration))
    pick = kit.ask_json(client, ScenePick, PICK_PROMPT.format(n=n, lo=MIN_SCENE, hi=MAX_SCENE,
                                                              lines=rows[:60000]))
    scenes = []
    for sc in sorted(pick.scenes, key=lambda s: s.start):
        a, b = max(0.0, float(sc.start)), min(duration, float(sc.end))
        if b - a < MIN_SCENE - 3 or any(a < o.end and b > o.start for o in scenes):
            continue
        sc.start, sc.end = a, min(b, a + MAX_SCENE + 5)
        if len(_lines(transcript, sc.start, sc.end)) >= 3:
            scenes.append(sc)
    return scenes[:n]


def _frames(video, times, out_dir):
    paths = []
    for k, t in enumerate(times):
        p = os.path.join(out_dir, f"f_{k + 1}.jpg")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", video,
                        "-frames:v", "1", "-vf", "scale=512:-2", "-q:v", "4", p], timeout=60)
        if os.path.exists(p):
            paths.append(p)
    return paths


def write_dub(client, video, lines, work):
    """The new dialogue for a scene's lines (times relative to the scene)."""
    from google.genai import types
    frames = _frames(video, [(a + b) / 2 for a, b, _ in lines], work)
    parts = []
    for p in frames:
        with open(p, "rb") as f:
            parts.append(types.Part.from_bytes(data=f.read(), mime_type="image/jpeg"))
    rows = "\n".join(f"{k}. slot {b - a:.1f}s: {t}" for k, (a, b, t) in enumerate(lines))
    dub = kit.ask_json(client, Dub, parts + [DUB_PROMPT.format(wps=WORDS_PER_SECOND, lines=rows)])
    by_index = {d.index: d for d in dub.lines if d.text.strip()}
    dub.lines = [by_index[k] for k in range(len(lines)) if k in by_index]
    return dub


def cast(lines):
    """A distinct voice per speaker, by gender."""
    voices, used = {}, {"male": 0, "female": 0}
    for d in lines:
        key = d.speaker.strip().upper()[:1] or "A"
        if key not in voices:
            g = "female" if d.gender.lower().startswith("f") else "male"
            pool = kit.FEMALE_VOICES if g == "female" else kit.MALE_VOICES
            voices[key] = pool[used[g] % len(pool)]
            used[g] += 1
    return voices


def schedule(slots, secs):
    """Start times: each line at its slot, never over the line before it."""
    out, prev_end = [], None
    for (a, _b), s in zip(slots, secs):
        start = a if prev_end is None else max(a, prev_end + 0.08)
        out.append(start)
        prev_end = start + s
    return out, prev_end


def black_bars(video):
    """ffmpeg crop that removes a letterbox (movie scenes come 2.39:1 inside
    16:9 and the bars showed inside the frame), or None."""
    r = subprocess.run(["ffmpeg", "-v", "info", "-ss", "2", "-t", "8", "-i", video,
                        "-vf", "cropdetect=limit=24:round=2:reset=0", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace", timeout=120)
    found = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", r.stderr)
    if not found:
        return None
    w, h, x, y = (int(v) for v in found[-1])
    full_w, full_h, _ = fl._probe(video)
    if h >= full_h * 0.96 and w >= full_w * 0.96 or h < full_h * 0.5 or w < full_w * 0.5:
        return None
    return f"crop={w}:{h}:{x}:{y}"


def dub_scene(client, section, lines, work, stem_k):
    """Voice the new lines over the muted scene. Returns (dubbed file, dub, timed lines)."""
    dub = write_dub(client, section, lines, work)
    if len(dub.lines) < max(3, len(lines) // 2):
        raise RuntimeError("the new dialogue came back incomplete")
    slots = {k: (a, b) for k, (a, b, _) in enumerate(lines)}
    voices = cast(dub.lines)
    said = kit.voice_lines(client, [
        {"text": d.text, "voice": voices[d.speaker.strip().upper()[:1] or "A"],
         "style": f"as a {d.emotion or 'dramatic'} character in a funny Pakistani movie dub, "
                  "natural Urdu accent, expressive"} for d in dub.lines], work, stem_k)
    keep = [(d, p, s) for d, (p, s) in zip(dub.lines, said) if p]
    if len(keep) < max(3, len(dub.lines) // 2):
        raise RuntimeError("the AI voice failed for too many lines")
    secs = []
    for d, p, s in keep:
        a, b = slots[d.index]
        room = (b - a) + 0.4
        if s > room:
            s = kit.speed_up(p, min(MAX_TEMPO, s / room))
        secs.append(s)
    starts, end = schedule([slots[d.index] for d, _, _ in keep], secs)
    scene_len = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", section],
        timeout=60).decode().strip())
    total = max(scene_len, end + 0.4)
    out = os.path.join(work, "dubbed.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", section,
           "-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
    graph, mix = [], ["[1:a]"]
    for k, ((d, p, _), at) in enumerate(zip(keep, starts)):
        cmd += ["-i", p]
        ms = int(at * 1000)
        from ffmpeg_utils import LOUDNORM_FILTER
        graph.append(f"[{k + 2}:a]{LOUDNORM_FILTER},aresample=48000,aformat=channel_layouts=stereo,"
                     f"adelay={ms}|{ms}[d{k}]")
        mix.append(f"[d{k}]")
    pad = max(0.0, total - scene_len)
    bars = black_bars(section)
    video = f"[0:v]{bars}," if bars else "[0:v]"
    graph.append(f"{video}tpad=stop_mode=clone:stop_duration={pad:.3f}[v]" if pad > 0.05
                 else f"{video}null[v]")
    graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0[a]")
    from ffmpeg_utils import video_encode_args, QUALITY_FAST
    subprocess.run(cmd + ["-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
                          "-t", f"{total:.3f}", *video_encode_args(QUALITY_FAST), "-pix_fmt", "yuv420p",
                          "-c:a", "aac", "-b:a", "192k", out], check=True, capture_output=True, timeout=900)
    timed = [(d.text, at, at + s) for (d, _, _), at, s in zip(keep, starts, secs)]
    return out, dub, timed, total


def run(urls, output_dir, pipeline):
    import youtube_captions
    import section_fetch
    import seo_copy
    url = urls[0]
    n = min(3, max(1, int(float(os.environ.get("CLIP_TARGET_MAX") or DEFAULT_SCENES))))
    client = kit.gemini()
    print(f"🎬 Funny dub: finding {n} scene(s) to re-dub...")
    transcript = youtube_captions.fetch(url)
    local = None
    if not transcript:
        print("   ℹ️ No captions on this video: downloading it to transcribe (slower).")
        vdir = os.path.join(output_dir, ".movie")
        os.makedirs(vdir, exist_ok=True)
        local, _ = pipeline.download_youtube_video(url, vdir)
        transcript = pipeline.transcribe_video(local)
    segs = transcript.get("segments") or []
    duration = transcript.get("duration") or (segs[-1]["end"] if segs else 0)
    if not segs:
        raise RuntimeError("This video has no dialogue to re-dub.")
    scenes = pick_scenes(client, transcript, n, duration)
    if not scenes:
        raise RuntimeError("No dialogue scene in this video suits a dub (needs a back-and-forth "
                           "conversation of 20-50 seconds).")
    print("   🎯 Scenes: " + ", ".join(f"{s.start:.0f}-{s.end:.0f}s" for s in scenes))

    ranges = [(s.start, s.end) for s in scenes]
    got = None if local else section_fetch.fetch(url, ranges, output_dir)
    if got:
        sections = got[1]
    else:
        if not local:
            vdir = os.path.join(output_dir, ".movie")
            os.makedirs(vdir, exist_ok=True)
            local, _ = pipeline.download_youtube_video(url, vdir)
        sections = {}
        for k, (a, b) in enumerate(ranges):
            sections[k] = os.path.join(output_dir, f"section_{k + 1}.mp4")
            pipeline.cut_clip(local, sections[k], a, b, k + 1)

    stem = kit.neutral_stem("Dub")
    cfg = fl.settings()
    clips, titles = [], {}
    for k, sc in enumerate(scenes):
        work = os.path.join(output_dir, f".dub_{k + 1}")
        os.makedirs(work, exist_ok=True)
        lines = [(a - sc.start, b - sc.start, t) for a, b, t in _lines(transcript, sc.start, sc.end)]
        print(f"✍️ Scene {k + 1}: writing and voicing {len(lines)} new lines...")
        try:
            dubbed, dub, timed, total = dub_scene(client, sections[k], lines, work, f"{stem}_{k + 1}")
        except Exception as e:  # noqa: BLE001 — the other scenes still ship
            print(f"   ⚠️ Scene {k + 1} skipped ({type(e).__name__}: {str(e)[:160]})")
            continue
        print(f"   😂 {dub.premise}")
        name = f"{stem}_clip_{len(clips) + 1}.mp4"
        titles[name] = fl.clean_title(dub.title)
        clips.append({"start": sc.start, "end": sc.end, "seconds": total, "file": os.path.join(output_dir, name),
                      "video_title_for_youtube_short": fl.clean_title(dub.title),
                      "viral_hook_text": dub.premise[:80], "why": dub.premise,
                      "predicted_score": 90 - k, "genre": "movies", "dub_premise": dub.premise,
                      "dub_lines": [t for t, _, _ in timed], "captions": kit.timed_transcript(timed),
                      "ai_voice": "AI voices, rewritten dialogue", "_dubbed": dubbed})
    if not clips:
        raise RuntimeError("No scene could be dubbed this time; try again or another video.")

    # Captions hang under the picture; its size is the dubbed (bars cropped) one.
    w, h, _ = fl._probe(clips[0]["_dubbed"])
    margin = fl.caption_margin_units(fl.geometry(w, h, cfg["crop"], cfg["zoom"]))
    fl.write_job(output_dir, cfg, margin, titles)
    for clip in clips:
        print(f"🎬 Rendering {os.path.basename(clip['file'])}...")
        fl.render(clip.pop("_dubbed"), clip["file"], title=clip["video_title_for_youtube_short"])
        clip["seconds"] = round(clip["seconds"] + (cfg["outro_seconds"] if cfg["outro"] else 0), 3)
    dub_text = {"language": "ur", "segments": [
        {"start": c["start"], "end": c["end"], "text": " ".join(c["dub_lines"]),
         "words": [{"word": " " + w, "start": c["start"], "end": c["start"]}
                   for w in " ".join(c["dub_lines"]).split()]} for c in clips]}
    seo_copy.apply(clips, dub_text, source_title="",
                   context=SEO_CONTEXT.format(premise="; ".join(c["dub_premise"] for c in clips)))
    kit.finish(output_dir, stem, clips, None, pipeline, extra={"genre": "movies"}, margin=margin)
    for path in [os.path.join(output_dir, ".movie")] + [
            os.path.join(output_dir, f".dub_{k + 1}") for k in range(len(scenes))]:
        shutil.rmtree(path, ignore_errors=True)
    for p in sections.values():
        if p and os.path.exists(p):
            os.remove(p)
