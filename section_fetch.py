"""Fetch only the picked clips from YouTube instead of the whole source.

When the video's captions are the transcript (youtube_captions.py), the clips
are known before a single byte of video is downloaded. Downloading the whole
source then costs far more than the clips need: 1.32 GB for a 1 h 49 min
video took ~15 min on a home line (~1.5 MB/s, 5-oct-2026), while ffmpeg read
and cut a 40 s stretch straight from the stream URLs in 28 s. Each section is
cut and encoded exactly like ffmpeg_utils.cut_clip (accurate input seek,
same encoder args), so it replaces the cut step and everything after it is
unchanged.

The cost: the job has no full source on disk, so the clip editor can only
trim inside the delivered clips (it already handles a missing source).
DOWNLOAD_SECTIONS=0 restores the full download.
"""
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

from ffmpeg_utils import video_encode_args, audio_encode_args, QUALITY_FAST, MIN_CUT_BYTES

FORMAT = ('bestvideo[vcodec^=avc1][height<=1080][ext=mp4]+bestaudio[ext=m4a]/'
          'bestvideo[vcodec^=avc1][height<=1080]+bestaudio/'
          'best[height<=1080][ext=mp4]/best[ext=mp4]/best')
# Parallel section fetches. Each one is network-bound plus one encode; three
# keeps a laptop CPU usable and a home line busy.
WORKERS = int(os.environ.get("SECTION_WORKERS", "3"))
# Fresh stream-URL resolves before falling back to the full download.
RESOLVE_ROUNDS = 3


def enabled():
    return os.environ.get("DOWNLOAD_SECTIONS", "1").strip() != "0"


def resolve(url):
    """(title, [stream formats]) for the job's format spec, or raises."""
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
            "socket_timeout": 30, "js_runtimes": {"node": {}},
            "extractor_args": {"youtube": {"player_client": ["default", "mweb"]}},
            "format": FORMAT}
    ck_path = None
    cookies = os.environ.get("YOUTUBE_COOKIES")
    try:
        if cookies:
            fd, ck_path = tempfile.mkstemp(prefix="yt_sect_", suffix=".txt")
            with os.fdopen(fd, "w") as f:
                f.write(cookies)
            opts["cookiefile"] = ck_path
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    finally:
        if ck_path:
            try:
                os.remove(ck_path)
            except OSError:
                pass
    fmts = info.get("requested_formats") or [info]
    if not all(f.get("url") for f in fmts):
        raise RuntimeError("no stream URL in the resolved formats")
    return info.get("title") or "youtube_video", fmts


def fetch_audio(url, output_dir):
    """The whole audio track only (song_shorts.py): (title, duration, path).

    A song is a few MB as audio against 60-100 MB as a 1080p music video, and
    the picture is never used. Same clients and cookies as resolve()."""
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
            "socket_timeout": 30, "js_runtimes": {"node": {}},
            "extractor_args": {"youtube": {"player_client": ["default", "mweb"]}},
            "format": "bestaudio[ext=m4a]/bestaudio/best", "retries": 10,
            "outtmpl": os.path.join(output_dir, "song_audio.%(ext)s")}
    ck_path = None
    cookies = os.environ.get("YOUTUBE_COOKIES")
    try:
        if cookies:
            fd, ck_path = tempfile.mkstemp(prefix="yt_sect_", suffix=".txt")
            with os.fdopen(fd, "w") as f:
                f.write(cookies)
            opts["cookiefile"] = ck_path
        # Fresh links each round: YouTube now and then 403s one set (see fetch).
        for round_no in range(1, RESOLVE_ROUNDS + 1):
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    path = ydl.prepare_filename(info)
                break
            except Exception as e:  # noqa: BLE001 — retried, then raised
                if round_no == RESOLVE_ROUNDS:
                    raise
                print(f"   🔁 Audio download failed ({str(e)[-80:]}), retrying with fresh links...")
    finally:
        if ck_path:
            try:
                os.remove(ck_path)
            except OSError:
                pass
    if not os.path.exists(path):
        raise RuntimeError("the audio download produced no file")
    return info.get("title") or "song", float(info.get("duration") or 0), path


def _ffmpeg_cmd(fmts, start, end, out_path):
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for f in fmts:
        headers = "".join(f"{k}: {v}\r\n" for k, v in (f.get("http_headers") or {}).items())
        if headers:
            cmd += ["-headers", headers]
        cmd += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
                "-ss", f"{start:.3f}", "-i", f["url"]]
    cmd += ["-t", f"{end - start:.3f}"]
    if len(fmts) > 1:
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]
    return cmd + [*video_encode_args(QUALITY_FAST), "-pix_fmt", "yuv420p",
                  *audio_encode_args(), out_path]


def fetch(url, ranges, output_dir):
    """Cut each (start, end) straight from the stream into its own file.

    Returns (title, {index: path}) when every section came out, or None, in
    which case the caller downloads the whole source as before. All or
    nothing on purpose: a partial set would mix two cut paths in one job.
    """
    if not enabled() or not ranges:
        return None

    print(f"✂️ Fetching only the {len(ranges)} picked clip(s) "
          f"({sum(e - s for s, e in ranges):.0f}s of video) instead of the whole source...")

    def _one(i, fmts):
        start, end = ranges[i]
        out = os.path.join(output_dir, f"section_{i + 1}.mp4")
        r = subprocess.run(_ffmpeg_cmd(fmts, start, end, out), stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE, text=True, errors="replace", timeout=1800)
        size = os.path.getsize(out) if os.path.exists(out) else 0
        if r.returncode == 0 and size >= MIN_CUT_BYTES:
            print(f"   ✅ Section {i + 1} fetched ({start:.0f}s-{end:.0f}s, {size / 1e6:.1f} MB)")
            return i, out
        print(f"   ⚠️ Section {i + 1} failed: {(r.stderr or '').strip()[-160:]}")
        return i, None

    # Each round resolves FRESH stream URLs. YouTube now and then answers 403
    # to every request on one set of URLs (all 3 sections of a job, both
    # retries, 6-oct-2026) while a new resolve minutes earlier and later
    # worked, so retrying the same URLs was wasted; a new set is the retry.
    title, results, pending = None, {}, list(range(len(ranges)))
    for round_no in range(1, RESOLVE_ROUNDS + 1):
        try:
            title, fmts = resolve(url)
        except Exception as e:  # noqa: BLE001 — any failure means full download
            print(f"   ℹ️ Stream links unavailable ({type(e).__name__}: {str(e)[:200]})")
            break
        with ThreadPoolExecutor(max_workers=max(1, WORKERS)) as pool:
            results.update(pool.map(lambda i: _one(i, fmts), pending))
        pending = [i for i in pending if not results.get(i)]
        if not pending:
            break
        if round_no < RESOLVE_ROUNDS:
            print(f"   🔁 Retrying {len(pending)} section(s) with fresh stream links...")
    if pending or len(results) < len(ranges):
        for p in results.values():
            if p and os.path.exists(p):
                os.remove(p)
        print("   ℹ️ Some sections failed — downloading the whole video instead.")
        return None
    return title, results
