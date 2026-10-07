"""One short built from the best moments of several YouTube videos.

The dashboard sends 2-5 links; app.py starts main.py with the first one and
puts the whole list in COMPILE_URLS, and main.py hands the job to ``run``
before anything of its own starts. Nothing here runs for a normal job.

Per video, in parallel: captions (youtube_captions) and the usual moment
pick (main.get_viral_clips). Then the best moments across all videos are
chosen to fill ``COMPILE_SECONDS`` (each video's best one first, then by
score), only those minutes are fetched (section_fetch), joined with short
crossfades into one 1920x1080 file, and that file goes through the same
framed render, captions and SEO copy as a normal clip. The job writes the
usual metadata with a single clip, so the dashboard shows it like any other.

YouTube Shorts can be at most 3 minutes, so the joined moments plus the end
card stay under 180 s.
"""
import json
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import used_moments

SHORTS_MAX_SECONDS = 180
FADE = 0.4  # crossfade between two moments, seconds
MAX_URLS = 5
DEFAULT_SECONDS = 170


def budget_seconds():
    """Seconds of joined moments, leaving room for the end card under 3 min."""
    import framed_layout
    cfg = framed_layout.settings()
    outro = cfg["outro_seconds"] if cfg["outro"] else 0
    ceiling = SHORTS_MAX_SECONDS - outro - 2
    try:
        want = float(os.environ.get("COMPILE_SECONDS") or DEFAULT_SECONDS)
    except ValueError:
        want = DEFAULT_SECONDS
    return max(20.0, min(want, ceiling))


def _score(clip):
    try:
        return float(clip.get("predicted_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def choose(candidates, budget, fade=FADE):
    """Pick moments to fill ``budget`` seconds of the joined video.

    ``candidates``: {video_index: [clip, ...]}. Each video's best moment goes
    in first (strongest video first) so every link is represented when it
    fits, then the rest by score. Returns [(video_index, clip)] in play
    order: the overall best moment opens the short (the first seconds decide
    whether a viewer stays), the others follow in link order and time.
    """
    def length(c):
        return float(c["end"]) - float(c["start"])

    ranked = {v: sorted(cs, key=_score, reverse=True) for v, cs in candidates.items() if cs}
    picked, used = [], 0.0

    def fits(c):
        extra = length(c) - (fade if picked else 0)
        return used + extra <= budget

    for v in sorted(ranked, key=lambda v: -_score(ranked[v][0])):
        best = next((c for c in ranked[v] if fits(c)), None)
        if best is not None:
            used += length(best) - (fade if picked else 0)
            picked.append((v, best))
    rest = sorted(((v, c) for v, cs in ranked.items() for c in cs
                   if not any(c is p for _, p in picked)),
                  key=lambda vc: -_score(vc[1]))
    for v, c in rest:
        if fits(c):
            used += length(c) - (fade if picked else 0)
            picked.append((v, c))
    if not picked:
        return []
    opener = max(picked, key=lambda vc: _score(vc[1]))
    others = sorted((vc for vc in picked if vc is not opener),
                    key=lambda vc: (vc[0], float(vc[1]["start"])))
    return [opener] + others


def merged_transcript(parts, language):
    """One transcript on the joined timeline.

    ``parts``: [(transcript, start, end, offset)]: the words a moment
    covers, moved to where that moment starts in the joined video."""
    segments = []
    for transcript, start, end, offset in parts:
        for seg in (transcript or {}).get("segments") or []:
            words = []
            for w in seg.get("words") or []:
                if start <= w["start"] < end:
                    nw = dict(w)
                    nw["start"] = round(w["start"] - start + offset, 3)
                    nw["end"] = round(min(w["end"], end) - start + offset, 3)
                    words.append(nw)
            if words:
                segments.append({"start": words[0]["start"], "end": words[-1]["end"],
                                 "text": "".join(w["word"] for w in words).strip(),
                                 "words": words})
    segments.sort(key=lambda s: s["start"])
    return {"language": language, "segments": segments,
            "text": " ".join(s["text"] for s in segments), "source": "compilation"}


def _duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        timeout=60).decode().strip()
    return float(out)


def join_command(files, durations, out_path, fade=FADE):
    """ffmpeg command: every moment scaled onto 1920x1080 at 30 fps, then
    chained with a short crossfade (video xfade, audio acrossfade)."""
    from ffmpeg_utils import video_encode_args, QUALITY_FAST
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for f in files:
        cmd += ["-i", f]
    chains = []
    for k in range(len(files)):
        chains.append(
            f"[{k}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p,"
            f"settb=AVTB,setpts=PTS-STARTPTS[v{k}]")
        chains.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                      f"asetpts=PTS-STARTPTS[a{k}]")
    v_last, a_last, offset = "v0", "a0", 0.0
    for k in range(1, len(files)):
        offset += durations[k - 1] - fade
        chains.append(f"[{v_last}][v{k}]xfade=transition=fade:duration={fade}:"
                      f"offset={offset:.3f}[x{k}]")
        chains.append(f"[{a_last}][a{k}]acrossfade=d={fade}[y{k}]")
        v_last, a_last = f"x{k}", f"y{k}"
    return cmd + ["-filter_complex", ";".join(chains), "-map", f"[{v_last}]", "-map", f"[{a_last}]",
                  *video_encode_args(QUALITY_FAST), "-pix_fmt", "yuv420p",
                  # Plain AAC: audio_encode_args adds -af loudnorm, which ffmpeg
                  # refuses next to -filter_complex, and every section was
                  # already normalised when section_fetch cut it.
                  "-c:a", "aac", "-b:a", "192k", out_path]


def _offsets(durations, fade=FADE):
    """Where each moment starts in the joined video."""
    out, t = [], 0.0
    for d in durations:
        out.append(t)
        t += d - fade
    return out


def run(urls, output_dir, pipeline):
    """Build the compilation. ``pipeline`` is main.py's module (its picker,
    downloader, renderer and caption burner). Raises on a failed job."""
    import youtube_captions
    import section_fetch
    import caption_script
    import framed_layout
    import seo_copy
    import ai_take
    from ffmpeg_utils import mark_ai_generated

    urls = list(dict.fromkeys(u.strip() for u in urls if u and u.strip()))[:MAX_URLS]
    budget = budget_seconds()
    print(f"🧩 Compilation: best moments from {len(urls)} videos, up to {budget:.0f}s in one short.")

    # 1. Captions and the moment pick, every video at once.
    def _pick(i):
        url = urls[i]
        t = youtube_captions.fetch(url)
        local = None
        if not t:
            print(f"   ℹ️ Video {i + 1} has no captions: downloading it to transcribe (slower).")
            vdir = os.path.join(output_dir, f".video_{i + 1}")
            os.makedirs(vdir, exist_ok=True)
            local, _ = pipeline.download_youtube_video(url, vdir)
            t = pipeline.transcribe_video(local)
        dur = t.get("duration") or (t["segments"][-1]["end"] if t.get("segments") else 0)
        if not dur or pipeline.speech_is_sparse(t, dur):
            print(f"   ⚠️ Video {i + 1} has too little speech to pick moments from; skipping it.")
            return i, t, [], local, None
        found = pipeline.trim_to_speech(
            pipeline.cap_clip_lengths(pipeline.get_viral_clips(
                t, dur, used=used_moments.ranges(url))), t) or {}
        clips = found.get("shorts") or []
        print(f"   ✅ Video {i + 1}: {len(clips)} candidate moments")
        return i, t, clips, local, found.get("cost_analysis")

    with ThreadPoolExecutor(max_workers=min(3, len(urls))) as pool:
        picks = list(pool.map(_pick, range(len(urls))))
    transcripts = {i: t for i, t, _, _, _ in picks}
    locals_ = {i: p for i, _, _, p, _ in picks if p}
    costs = [c for *_, c in picks if c]

    # 2. The moments that make the short.
    chosen = choose({i: cs for i, _, cs, _, _ in picks}, budget)
    if not chosen:
        raise RuntimeError("No usable moments were found in these videos.")
    used_videos = sorted({v for v, _ in chosen})
    print(f"🎯 Picked {len(chosen)} moments from {len(used_videos)} of {len(urls)} videos.")

    # 3. Caption language per video, before any word is moved.
    for v in used_videos:
        caption_script.apply(transcripts[v], [c for vv, c in chosen if vv == v])

    # 4. Only those minutes, per video.
    files, titles = {}, {}

    def _fetch(v):
        mine = [(k, c) for k, (vv, c) in enumerate(chosen) if vv == v]
        ranges = [(float(c["start"]), float(c["end"])) for _, c in mine]
        vdir = os.path.join(output_dir, f".video_{v + 1}")
        os.makedirs(vdir, exist_ok=True)
        got = None if v in locals_ else section_fetch.fetch(urls[v], ranges, vdir)
        if got:
            title, sections = got
            return v, title, {k: sections[j] for j, (k, _) in enumerate(mine)}
        src = locals_.get(v)
        if not src:
            src, title = pipeline.download_youtube_video(urls[v], vdir)
        else:
            title = os.path.splitext(os.path.basename(src))[0]
        out = {}
        for j, (k, c) in enumerate(mine):
            path = os.path.join(vdir, f"cut_{j + 1}.mp4")
            pipeline.cut_clip(src, path, float(c["start"]), float(c["end"]), k + 1)
            out[k] = path
        return v, title, out

    with ThreadPoolExecutor(max_workers=min(3, len(used_videos))) as pool:
        for v, title, out in pool.map(_fetch, used_videos):
            titles[v] = (title or "").replace("_", " ")
            files.update(out)

    # 5. One file, then the normal framed render, captions and copy.
    order = list(range(len(chosen)))
    durations = [_duration(files[k]) for k in order]
    offsets = _offsets(durations)
    total = offsets[-1] + durations[-1]
    # Neutral file name: a source title carries the creator's name, which the
    # channel keeps out of everything it publishes (seo_copy.py).
    stem = time.strftime("Compilation_%Y-%m-%d_%H%M")
    joined = os.path.join(output_dir, f"temp_{stem}_joined.mp4")
    if len(order) == 1:
        shutil.copyfile(files[0], joined)
    else:
        print(f"🔗 Joining {len(order)} moments ({total:.0f}s)...")
        r = subprocess.run(join_command([files[k] for k in order], durations, joined),
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                           errors="replace", timeout=1800)
        if r.returncode != 0:
            raise RuntimeError(f"Joining the moments failed: {(r.stderr or '').strip()[-300:]}")

    transcript = merged_transcript(
        [(transcripts[v], float(c["start"]), float(c["start"]) + durations[k], offsets[k])
         for k, (v, c) in enumerate(chosen)],
        (transcripts[chosen[0][0]] or {}).get("language") or "en")
    best = chosen[0][1]
    clip = {
        "start": 0.0, "end": round(total, 3),
        "video_title_for_youtube_short": best.get("video_title_for_youtube_short") or "",
        "viral_hook_text": best.get("viral_hook_text") or "",
        "why": f"{len(chosen)} best moments from {len(used_videos)} videos in one short.",
        "predicted_score": max(_score(c) for _, c in chosen),
        "compilation_parts": [
            {"video": v + 1, "url": urls[v], "source_title": titles.get(v, ""),
             "start": float(c["start"]), "end": float(c["start"]) + durations[k],
             "at": round(offsets[k], 3)}
            for k, (v, c) in enumerate(chosen)],
    }
    seo_copy.apply([clip], transcript, source_title=" | ".join(titles[v] for v in used_videos),
                   context=(f"This short is a compilation: {len(chosen)} of the best moments "
                            f"from {len(used_videos)} different videos, joined back to back. "
                            "Write the copy for the whole compilation, not one moment."),
                   text_limit=4000)
    clip_name = f"{stem}_clip_1.mp4"
    look = framed_layout.settings()
    # The channel's take (ai_take.py): skipped by itself when the compilation
    # is too long to fit it under Shorts' 3 minutes.
    takes = ai_take.apply([clip], transcript, output_dir, [clip_name],
                          outro_seconds=look["outro_seconds"] if look["outro"] else 0.0,
                          source_title=" | ".join(titles[v] for v in used_videos))

    cost = {"input_tokens": sum(c.get("input_tokens", 0) for c in costs),
            "output_tokens": sum(c.get("output_tokens", 0) for c in costs),
            "total_cost": sum(float(c.get("total_cost", 0) or 0) for c in costs)}
    clips_data = {"shorts": [clip], "cost_analysis": cost, "transcript": transcript,
                  "source_video": None, "output_format": "framed", "compilation": True}
    metadata_file = os.path.join(output_dir, f"{stem}_metadata.json")
    with open(metadata_file, "w") as f:
        json.dump(clips_data, f, indent=2)
    cfg = look
    framed_layout.write_job(
        output_dir, cfg,
        framed_layout.caption_margin_units(framed_layout.geometry(1920, 1080, cfg["crop"], cfg["zoom"])),
        {clip_name: clip["video_title_for_youtube_short"]}, takes)
    print(f"   Saved metadata to {metadata_file}")

    final = os.path.join(output_dir, clip_name)
    print(f"\n🎬 Rendering the compilation ({total:.0f}s)")
    if not pipeline.render_clip(joined, final, "framed", title=clip["video_title_for_youtube_short"]):
        raise RuntimeError("Rendering the compilation failed.")
    captioned = pipeline.auto_caption_clip(final, transcript, 0.0, total)
    served = captioned or final
    if (takes.get(clip_name) or {}).get("audio"):
        mark_ai_generated(served, "AI voice take after the clip")
    print(f"   ✅ Clip 1 ready: {final}")
    print(f"CLIP_READY 0 {os.path.basename(served)}")
    for v in used_videos:   # never repeat a moment (used_moments.py)
        used_moments.record(urls[v], [(c["start"], c["end"]) for vv, c in chosen if vv == v],
                            os.path.basename(output_dir))

    for path in [joined] + [os.path.join(output_dir, f".video_{i + 1}") for i in range(len(urls))]:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)
    return metadata_file
