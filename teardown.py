"""Reverse-engineer what wins, by measuring it (owner, 5-nov-2026, sharing the REA repo, "reverse engineer
anything": "see how we can reverse engineer something and make our system better").

REA takes software apart and shows the evidence behind every conclusion. Our rivals are videos, so this takes
videos apart the same way. niche_research has Gemini watch the niche's most viewed videos and describe them
in words (hook, beats, visuals), and words can be wrong ("fast cuts"). This measures the files instead, the
same way for theirs and ours, so every rule comes with its numbers: "the first picture change: theirs 1.1 s,
ours 3.6 s (medians of 9 winners and 6 of ours)".

Measured on the first MEASURE_SECONDS at 360p, on this laptop, free:
- pictures: the cut times (PySceneDetect's ContentDetector), so the first cut, the median shot, cuts per 10 s
- speech: faster-whisper's words, so the first word, words per second, words in the first 3 s, time talking
- the first frame's brightness and, for a whole Short, whether its last frame is its first again (a loop)
- the length

Rivals' videos (the niche's studied winners) are fetched one at a time as a small 360p file and deleted right
after; ours are measured from their job folder while it is still there (about a day). Every measurement runs
in its own process (``python teardown.py measure <file>``), so Whisper's model never stays in the server.
State: state/research/<niche>.json, under "anatomy" (theirs) and "ours" (niche_research owns the file).

pace_cut() is what the numbers change by themselves: the footage cut length the "pace" test
(my_channels.EXPERIMENTS) tries against our usual broll.CUT.
"""
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
MEASURE_SECONDS = 180          # a long video's first three minutes: where its viewers decide
PER_RUN = 2                    # rivals' files fetched per research pass (one at a time)
OURS_PER_RUN = 3
KEEP = 60                      # measurements kept per side
MIN_THEIRS, MIN_OURS = 4, 3    # fewer and a median says nothing
CUT_THRESHOLD = 27.0           # PySceneDetect's default for ContentDetector
LOOP_SIMILAR = 0.92            # last frame vs first (1 = the same picture)
MEASURE_TIMEOUT = 600
FETCH_TIMEOUT = 300

# What each measure is, its unit, the smallest gap worth a line, and what to do on each side of it:
# (key, name, unit, floor, (advice when theirs is lower, advice when theirs is higher)).
MEASURES = (
    ("seconds", "length", "s", 5.0, ("make it shorter", "make it longer")),
    ("first_word", "the first word", "s", 0.3, ("start talking at once", "let the opening breathe first")),
    ("hook_words", "words in the first 3 s", "", 2.0, ("say less in the first 3 seconds",
                                                       "say more in the first 3 seconds")),
    ("wps", "words per second", "", 0.4, ("talk slower, with pauses", "talk faster, fewer pauses")),
    ("first_cut", "the first picture change", "s", 0.4, ("change the picture sooner", "hold the first picture longer")),
    ("shot", "a shot (median)", "s", 0.4, ("cut faster", "let each shot run longer")),
    ("first_luma", "first-frame brightness (0-255)", "", 20.0, ("a darker first frame", "a brighter first frame")),
    ("loop", "Shorts that loop back to their start", "%", 25.0, ("loop less", "end on a line that leads back into the start")),
)


def enabled():
    return os.environ.get("TEARDOWN", "1") != "0"


# ------------------------------------------------------------------ measuring one file

def _run(cmd, timeout=300):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def duration(path):
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], 60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _frame(video, at, out):
    """A 64x36 grey thumbnail of the frame at ``at``, as a list of pixels, or None."""
    _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, at):.2f}", "-i", video, "-frames:v", "1",
          "-vf", "scale=64:36,format=gray", out], 60)
    try:
        from PIL import Image
        with Image.open(out) as im:
            return list(im.convert("L").getdata())
    except Exception:  # noqa: BLE001 — no frame there
        return None


def similarity(a, b):
    """1 - mean absolute difference of two grey thumbnails, 0..1."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return 1 - sum(abs(x - y) for x, y in zip(a, b)) / (255.0 * len(a))


def cut_times(video):
    """Seconds of every cut PySceneDetect finds."""
    from scenedetect import SceneManager, open_video
    from scenedetect.detectors import ContentDetector
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=CUT_THRESHOLD, min_scene_len=6))
    sm.detect_scenes(open_video(video))
    return [round(s[0].get_seconds(), 2) for s in sm.get_scene_list()[1:]]


def heard_words(wav):
    """[(start, end)] of every word faster-whisper hears (any language), or []."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return []
    # "small": the model the captions already keep on disk (short_kit.whisper_words), nothing new to fetch.
    model = WhisperModel(os.environ.get("TEARDOWN_WHISPER") or "small", device="cpu", compute_type="int8",
                         cpu_threads=4)
    segs, _info = model.transcribe(wav, word_timestamps=True, vad_filter=True, beam_size=1,
                                   condition_on_previous_text=False)
    return [(float(w.start), float(w.end)) for s in segs for w in (s.words or []) if (w.word or "").strip()]


def anatomy(total, span, cuts, words, first, last):
    """The measures from the raw facts (pure: the tests feed it numbers)."""
    cuts = sorted(c for c in cuts if 0 < c < span)
    edges = [0.0] + cuts + [span]
    shots = [b - a for a, b in zip(edges, edges[1:]) if b - a > 0]
    out = {"seconds": round(total, 2), "measured": round(span, 2), "cuts": len(cuts),
           "first_cut": round(cuts[0], 2) if cuts else round(span, 2),
           "shot": round(statistics.median(shots), 2) if shots else round(span, 2),
           "cuts_10s": round(len(cuts) / span * 10, 2) if span else 0.0}
    words = sorted(w for w in words if w[0] < span)
    if words:
        talk = words[-1][1] - words[0][0]
        out.update(first_word=round(words[0][0], 2), hook_words=sum(1 for w in words if w[0] < 3.0),
                   wps=round(len(words) / talk, 2) if talk > 0.5 else 0.0,
                   talk=round(min(1.0, sum(max(0.0, b - a) for a, b in words) / span), 2))
    else:
        out.update(first_word=None, hook_words=0, wps=0.0, talk=0.0)
    out["first_luma"] = round(sum(first) / len(first), 1) if first else None
    # A loop only means something for a video measured to its end.
    out["loop"] = (similarity(first, last) >= LOOP_SIMILAR) if first and last and span >= total - 0.5 else None
    return out


def measure(path, seconds=MEASURE_SECONDS):
    """The measures of one video file (in this process)."""
    total = duration(path)
    if total <= 0:
        raise ValueError("not a video")
    span = min(total, seconds)
    tmp = tempfile.mkdtemp(prefix="teardown_")
    try:
        proxy, wav = os.path.join(tmp, "p.mp4"), os.path.join(tmp, "a.wav")
        r = _run(["ffmpeg", "-v", "error", "-y", "-i", path, "-t", f"{span:.2f}", "-an",
                  "-vf", "scale=-2:360,fps=15", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", proxy])
        if r.returncode != 0 or not os.path.isfile(proxy):
            raise RuntimeError(f"ffmpeg could not read it: {r.stderr[-200:]}")
        _run(["ffmpeg", "-v", "error", "-y", "-i", path, "-t", f"{span:.2f}", "-vn", "-ac", "1", "-ar", "16000", wav])
        words = heard_words(wav) if os.path.isfile(wav) and os.path.getsize(wav) > 1000 else []
        first = _frame(proxy, 0.05, os.path.join(tmp, "f.png"))
        last = _frame(proxy, span - 0.2, os.path.join(tmp, "l.png"))
        return anatomy(total, span, cut_times(proxy), words, first, last)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class Busy(Exception):
    """The laptop was too busy to finish a measurement in time (a long video rendering): says nothing about
    the video, so it is not kept as failed and the next pass measures it."""


def measure_file(path, seconds=MEASURE_SECONDS, timeout=MEASURE_TIMEOUT):
    """measure() in its own process at below-normal priority (Whisper's memory goes with it, and a render
    running beside it keeps the CPU); raises with the reason, Busy on a timeout."""
    low = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "teardown.py"), "measure", path, str(seconds)],
                           capture_output=True, text=True, timeout=timeout, cwd=ROOT, creationflags=low)
    except subprocess.TimeoutExpired:
        raise Busy(f"no result in {timeout // 60} min")
    lines = [x for x in r.stdout.splitlines() if x.startswith("{")]
    if r.returncode != 0 or not lines:
        raise RuntimeError((r.stderr or r.stdout or "no output").strip().splitlines()[-1][:200])
    return json.loads(lines[-1])


# ------------------------------------------------------------------ rivals' files

def fetch(video_id, out_dir, seconds=None):
    """A small 360p copy of a YouTube video (only its first ``seconds`` when given); the path."""
    import yt_dlp
    from yt_clients import fallback_extractor_args       # the main downloader's clients and PO-token provider
    args = fallback_extractor_args(os.environ.get("BGUTIL_BASE_URL", "").strip(),
                                   os.environ.get("BGUTIL_SCRIPT_PATH", "").strip())
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True, "socket_timeout": 30,
            "retries": 5,
            "js_runtimes": {"node": {}}, "extractor_args": args,
            # Separate small streams joined by ffmpeg: a winner on 5-nov-2026 had no single 360p file ("18").
            "format": "bv*[height<=360][ext=mp4]+ba[ext=m4a]/bv*[height<=480]+ba/b[height<=480]/18/b",
            "merge_output_format": "mp4", "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s")}
    if seconds:
        opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [(0, seconds)])
    ck = None
    if os.environ.get("YOUTUBE_COOKIES"):
        fd, ck = tempfile.mkstemp(prefix="yt_td_", suffix=".txt")
        with os.fdopen(fd, "w") as f:
            f.write(os.environ["YOUTUBE_COOKIES"])
        opts["cookiefile"] = ck
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([f"https://www.youtube.com/watch?v={video_id}"])
    finally:
        if ck:
            try:
                os.remove(ck)
            except OSError:
                pass
    got = [os.path.join(out_dir, n) for n in os.listdir(out_dir) if n.startswith(video_id)]
    if not got:
        raise RuntimeError("nothing downloaded")
    return got[0]


# ------------------------------------------------------------------ the research pass

def measure_some(data, theirs, ours, log=print, now=None, fetch_fn=None, measure_fn=None):
    """Measure up to PER_RUN of ``theirs`` (studied winners: {"id", "title", "views", "seconds", "channel"})
    and OURS_PER_RUN of ``ours`` ({"id", "path", "title", "views"}) not measured yet, into ``data``
    ("anatomy", "ours"). One at a time; a failure is kept, so it is not tried every day. Returns how many.
    TEARDOWN=0 (the tests) measures nothing unless the caller brings its own fetch and measure."""
    if not enabled() and (fetch_fn is None or measure_fn is None):
        return 0
    now, fetch_fn, measure_fn = now or time.time(), fetch_fn or fetch, measure_fn or measure_file
    done = 0
    side = data.setdefault("anatomy", {})

    def todo(v, kept):
        # A timeout said nothing about the video (a busy laptop, before Busy existed): measured again.
        rec = kept.get(v.get("id"))
        return bool(v.get("id")) and (rec is None or str(rec.get("failed", "")).startswith("TimeoutExpired"))
    for v in [v for v in theirs if todo(v, side)][:PER_RUN]:
        tmp = tempfile.mkdtemp(prefix="teardown_dl_")
        rec = {k: v.get(k) for k in ("title", "views", "channel", "seconds")}
        try:
            long = (v.get("seconds") or 0) > MEASURE_SECONDS
            path = fetch_fn(v["id"], tmp, MEASURE_SECONDS if long else None)
            rec["m"] = measure_fn(path)
            if long:
                # The whole video's length, not the piece's; and the piece's end is not the video's end.
                rec["m"].update(seconds=v.get("seconds"), loop=None)
            done += 1
        except Busy as e:
            log(f"   ℹ️ Measuring waits for a quieter moment ({e}).")
            shutil.rmtree(tmp, ignore_errors=True)
            break                                   # the laptop is busy: the rest wait for the next pass too
        except Exception as e:  # noqa: BLE001 — kept as failed: tomorrow's pass takes the next one
            rec["failed"] = f"{type(e).__name__}: {str(e)[:120]}"
            log(f"   ℹ️ Could not measure \"{(v.get('title') or '')[:40]}\" ({rec['failed'][:80]}).")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        side[v["id"]] = {**rec, "at": int(now)}
    mine = data.setdefault("ours", {})
    for v in [v for v in ours if todo(v, mine) and os.path.isfile(v.get("path") or "")][:OURS_PER_RUN]:
        rec = {k: v.get(k) for k in ("title", "views", "channel")}
        try:
            rec["m"] = measure_fn(v["path"])
            done += 1
        except Busy:
            break
        except Exception as e:  # noqa: BLE001
            rec["failed"] = f"{type(e).__name__}: {str(e)[:120]}"
        mine[v["id"]] = {**rec, "at": int(now)}
    for key in ("anatomy", "ours"):
        data[key] = dict(sorted(data[key].items(), key=lambda kv: kv[1].get("at", 0))[-KEEP:])
    return done


def _values(recs, key):
    out = []
    for r in recs:
        x = (r.get("m") or {}).get(key)
        if x is None:
            continue
        out.append(100.0 if x is True else 0.0 if x is False else float(x))
    return out


def compare(data):
    """[{key, name, unit, theirs, ours, n_theirs, n_ours, advice}] where their winners and our videos differ
    by more than the measure's floor and by a quarter or more, the biggest gap first."""
    theirs = [r for r in (data.get("anatomy") or {}).values() if r.get("m")]
    ours = [r for r in (data.get("ours") or {}).values() if r.get("m")]
    rows = []
    for key, name, unit, floor, (lower, higher) in MEASURES:
        a, b = _values(theirs, key), _values(ours, key)
        if len(a) < MIN_THEIRS or len(b) < MIN_OURS:
            continue
        if key == "loop":                       # a share, not a median
            ta, tb = sum(a) / len(a), sum(b) / len(b)
        else:
            ta, tb = statistics.median(a), statistics.median(b)
        gap = abs(ta - tb)
        if gap < floor or gap < 0.25 * max(abs(ta), abs(tb), 1e-9):
            continue
        rows.append({"key": key, "name": name, "unit": unit, "theirs": round(ta, 1), "ours": round(tb, 1),
                     "n_theirs": len(a), "n_ours": len(b), "advice": lower if ta < tb else higher,
                     "size": gap / max(abs(ta), abs(tb), 1e-9)})
    rows.sort(key=lambda r: -r["size"])
    return [{k: v for k, v in r.items() if k != "size"} for r in rows]


def winners(data, n=5):
    """The measured winners behind the gaps, most viewed first: [{"id", "title", "views"}] (the evidence)."""
    got = [{"id": k, "title": r.get("title"), "views": r.get("views")}
           for k, r in (data.get("anatomy") or {}).items() if r.get("m")]
    return sorted(got, key=lambda w: -(w.get("views") or 0))[:n]


def _num(x, unit):
    return f"{x:g}{'%' if unit == '%' else ' s' if unit == 's' else ''}"


def lines(data):
    """compare() as plain lines for a prompt or the dashboard."""
    return [f"{r['name']}: theirs {_num(r['theirs'], r['unit'])}, ours {_num(r['ours'], r['unit'])} "
            f"(of {r['n_theirs']} winners and {r['n_ours']} of ours): {r['advice']}." for r in compare(data)]


def measured_text(data, limit=700):
    """The block niche_research.playbook_text puts on top of the playbook, or ""."""
    got = lines(data)
    if not got:
        return ""
    text = ("MEASURED ON THE VIDEO FILES (this niche's winners against our own videos, medians; do what each "
            "line says where the script can):\n" + "\n".join(f"- {x}" for x in got))
    return text[:limit]


PACE_RANGE = (1.5, 4.0)
BASE_CUT = 2.8                 # broll.CUT (not imported: broll loads the face models; a test keeps them equal)


def pace_cut(data, base):
    """The footage cut length (seconds) that should give our videos the winners' median shot: ``base`` (our
    broll.CUT) scaled by theirs / ours, within PACE_RANGE; None while either side has too few measured or
    the two are already within 15%."""
    a = _values([r for r in (data.get("anatomy") or {}).values() if r.get("m")], "shot")
    b = _values([r for r in (data.get("ours") or {}).values() if r.get("m")], "shot")
    if len(a) < MIN_THEIRS or len(b) < MIN_OURS:
        return None
    ta, tb = statistics.median(a), statistics.median(b)
    if tb <= 0 or abs(ta / tb - 1) < 0.15:
        return None
    return round(max(PACE_RANGE[0], min(PACE_RANGE[1], base * ta / tb)), 1)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "measure":
        print(json.dumps(measure(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else MEASURE_SECONDS)))
    else:
        print("python teardown.py measure <video file> [seconds]")
        sys.exit(2)
