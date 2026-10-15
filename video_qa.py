"""A last look at a finished video before it goes up unattended.

The channels upload on their own, so a broken render would go public with no
one watching: a voice that never made it into the mix, a background that came
out black, a picture that froze for half the video. One ffmpeg pass at 5 fps
and 320 px (a few seconds even for a long video) checks the file for:

- a video and an audio stream, the right shape (Shorts vertical, at most 3 min);
- sound: mean volume above SILENT_DB (a muted mix reads about -91 dB);
- no black stretch of BLACK_SECONDS or more;
- no frozen picture of FREEZE_SECONDS or more (the countdowns, particles and
  slow zooms of our Shorts keep every frame moving; a stalled render does not).

check() returns the problems in plain words; an empty list means it may go up.
"""

import json
import re
import subprocess

SILENT_DB = -45.0
BLACK_SECONDS = 3.0
FREEZE_SECONDS = 15.0
SHORT_MAX = 180.0
SHORT_MIN = 8.0
LONG_MIN = 60.0


def _probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height:format=duration", "-of", "json", path],
                       capture_output=True, text=True, timeout=60)
    if r.returncode:
        return None
    return json.loads(r.stdout or "{}")


def _scan(path, has_audio):
    graph = (f"[0:v]fps=5,scale=320:-2,blackdetect=d={BLACK_SECONDS}:pix_th=0.10,"
             f"freezedetect=n=0.001:d={FREEZE_SECONDS}[v]")
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-filter_complex"]
    if has_audio:
        cmd += [graph + ";[0:a]volumedetect[a]", "-map", "[v]", "-map", "[a]"]
    else:
        cmd += [graph, "-map", "[v]"]
    r = subprocess.run(cmd + ["-f", "null", "-"], capture_output=True, text=True, timeout=1800,
                       stdin=subprocess.DEVNULL)
    return r.stderr or ""


def check(path, long=False, silent_ok=False):
    """Plain-words problems with the finished video at ``path`` ([] = fine)."""
    try:
        info = _probe(path)
    except (OSError, subprocess.SubprocessError, ValueError):
        info = None
    if not info:
        return ["the file cannot be read"]
    streams = info.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = any(s.get("codec_type") == "audio" for s in streams)
    try:
        seconds = float((info.get("format") or {}).get("duration") or 0)
    except ValueError:
        seconds = 0.0
    problems = []
    if not video:
        return ["it has no picture"]
    if not audio and not silent_ok:
        problems.append("it has no sound track")
    w, h = int(video.get("width") or 0), int(video.get("height") or 0)
    if long:
        if seconds < LONG_MIN:
            problems.append(f"it is only {seconds:.0f} s long")
    else:
        if h <= w:
            problems.append(f"it is not vertical ({w}x{h})")
        if seconds > SHORT_MAX:
            problems.append(f"it is {seconds:.0f} s, past the 3 minutes a Short may be")
        if seconds < SHORT_MIN:
            problems.append(f"it is only {seconds:.1f} s long")
    try:
        log = _scan(path, audio)
    except (OSError, subprocess.SubprocessError):
        return problems + ["the picture could not be checked"]
    vol = re.search(r"mean_volume:\s*(-?[\d.]+|-inf) dB", log)
    if audio and not silent_ok and vol and (vol.group(1) == "-inf" or float(vol.group(1)) < SILENT_DB):
        problems.append(f"it is silent (mean volume {vol.group(1)} dB)")
    blacks = [float(d) for d in re.findall(r"black_duration:\s*([\d.]+)", log)]
    if blacks:
        problems.append(f"{max(blacks):.0f} s of black picture")
    freezes = [float(d) for d in re.findall(r"lavfi\.freezedetect\.freeze_duration:\s*([\d.]+)", log)]
    if not freezes and re.search(r"freeze_start", log) and not re.search(r"freeze_end", log):
        freezes = [FREEZE_SECONDS]      # frozen through to the end
    if freezes:
        problems.append(f"the picture freezes for {max(freezes):.0f} s")
    return problems
