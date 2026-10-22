"""Use the captions a YouTube video already has as the job's transcript.

Why: on a machine without an NVIDIA GPU, faster-whisper "small" ran slower
than real time (5 min of Hindi audio took over 10 min on an i7-1360P,
5-oct-2026), so a 1-hour source spent hours in transcription before a single
clip was picked. Almost every YouTube video carries an auto-generated caption
track, and its json3 form has per-word offsets, which is exactly what the
moment picker and the karaoke captions need. Reading it is one request.

Returns the same shape as transcribe_backends.transcribe_media:
``{"text", "language", "segments": [{"start", "end", "text", "words": [...]}]}``
or None when the video has no usable track (the caller transcribes instead).
"""
import json
import os
import re
import tempfile


def choose_track(info):
    """``(kind, key)`` of the track to use, or ``(None, None)``.

    A human track in the spoken language first, then YouTube's own speech
    recognition of it (``<lang>-orig``; every other automatic key is a machine
    translation), then any human track, English first. Same order as the
    free transcript tool (free_tools.choose_track), which pipeline code must
    not import: it pulls in cloud/ and its server secrets.
    """
    manual = {k: v for k, v in (info.get("subtitles") or {}).items() if k != "live_chat" and v}
    auto = info.get("automatic_captions") or {}
    lang = info.get("language") or ""
    base = lang.split("-")[0].lower()
    for k in manual:
        if lang and k.split("-")[0].lower() == base:
            return "manual", k
    orig = [k for k in auto if k.endswith("-orig")] or ([lang] if lang in auto else [])
    if orig:
        return "auto", orig[0]
    for k in manual:
        if k.split("-")[0].lower() == "en":
            return "manual", k
    if manual:
        return "manual", next(iter(manual))
    return None, None


def _event_words(ev, end_limit):
    """Words of one json3 event with absolute start/end seconds.

    Auto (ASR) tracks carry ``tOffsetMs`` per word. Human tracks carry one
    block of text per event, so its words share the event's time in
    proportion to their length (close enough for a caption highlight).
    """
    start = (ev.get("tStartMs") or 0) / 1000.0
    dur = (ev.get("dDurationMs") or 0) / 1000.0
    end = min(start + dur, end_limit) if dur else end_limit
    if end <= start:
        end = start + 0.3
    segs = [s for s in ev.get("segs") or [] if (s.get("utf8") or "").strip()]
    if not segs:
        return []

    words = []
    if len(segs) > 1 and any("tOffsetMs" in s for s in segs[1:]):
        for s in segs:
            text = re.sub(r"\s+", " ", s["utf8"].replace("\n", " ")).strip()
            if text:
                words.append({"word": " " + text,
                              "start": start + (s.get("tOffsetMs") or 0) / 1000.0})
        for a, b in zip(words, words[1:]):
            a["end"] = b["start"]
        if words:
            # The last word of an auto line has no successor inside the event;
            # give it a natural length rather than the whole tail of the line.
            words[-1]["end"] = min(end, words[-1]["start"] + 0.8)
    else:
        text = re.sub(r"\s+", " ", "".join(s["utf8"] for s in segs).replace("\n", " ")).strip()
        tokens = text.split(" ")
        total = sum(len(t) for t in tokens) or 1
        t = start
        for tok in tokens:
            d = (end - start) * len(tok) / total
            words.append({"word": " " + tok, "start": t, "end": t + d})
            t += d

    for w in words:
        w["start"] = round(w["start"], 3)
        w["end"] = round(max(w["end"], w["start"] + 0.05), 3)
    return words


def json3_to_transcript(data, language, max_seconds=None):
    """Convert a json3 caption document into the pipeline's transcript shape."""
    if isinstance(data, (bytes, str)):
        data = json.loads(data)
    events = [e for e in data.get("events") or []
              if any((s.get("utf8") or "").strip() for s in e.get("segs") or [])]
    events.sort(key=lambda e: e.get("tStartMs") or 0)

    segments = []
    for i, ev in enumerate(events):
        nxt = events[i + 1].get("tStartMs") / 1000.0 if i + 1 < len(events) else float("inf")
        words = _event_words(ev, nxt)
        if not words:
            continue
        if max_seconds and words[0]["start"] >= max_seconds:
            break
        segments.append({
            "start": words[0]["start"],
            "end": words[-1]["end"],
            "text": "".join(w["word"] for w in words).strip(),
            "words": words,
        })
    return {
        "text": " ".join(s["text"] for s in segments),
        "language": language,
        "segments": segments,
        "source": "youtube_captions",
    }


def fetch(url, max_seconds=None, info_out=None):
    """Blocking. The video's own captions as a transcript, or None.

    Never raises: any failure means "transcribe it the normal way".
    ``info_out`` (a dict) gets the video's title, views, channel and length from the
    same request (viral_remix needs them, and a second yt-dlp call is one more
    chance of a bot-check).
    """
    if os.environ.get("YT_CAPTIONS", "1").strip() == "0":
        return None
    import yt_dlp

    opts = {"skip_download": True, "quiet": True, "no_warnings": True,
            "noplaylist": True, "socket_timeout": 20,
            # Captions only: a SABR-only video still lists its tracks.
            "ignore_no_formats_error": True,
            "js_runtimes": {"node": {}}}
    ck_path = None
    cookies = os.environ.get("YOUTUBE_COOKIES")
    try:
        if cookies:
            fd, ck_path = tempfile.mkstemp(prefix="yt_caps_", suffix=".txt")
            with os.fdopen(fd, "w") as f:
                f.write(cookies)
            opts["cookiefile"] = ck_path
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info_out is not None:
                info_out.update({"id": info.get("id"), "title": info.get("title") or "",
                                 "views": info.get("view_count") or 0, "channel": info.get("channel") or
                                 info.get("uploader") or "", "seconds": info.get("duration") or 0})
            kind, key = choose_track(info)
            if not kind:
                print("   ℹ️ No YouTube captions on this video — transcribing the audio instead.")
                return None
            pool = (info.get("subtitles") if kind == "manual"
                    else info.get("automatic_captions")) or {}
            fmt = next((f for f in pool.get(key, []) if f.get("ext") == "json3"), None)
            if not fmt:
                return None
            raw = ydl.urlopen(fmt["url"]).read()
        language = key[:-5] if key.endswith("-orig") else key
        transcript = json3_to_transcript(raw, language.split("-")[0], max_seconds)
        transcript["duration"] = info.get("duration") or 0
        n_words = sum(len(s["words"]) for s in transcript["segments"])
        if not n_words:
            return None
        print(f"📝 Using YouTube's {kind} captions ({language}, {n_words} words) — "
              f"no transcription needed.")
        return transcript
    except Exception as e:  # noqa: BLE001 — any failure falls back to ASR
        print(f"   ℹ️ YouTube captions unavailable ({type(e).__name__}: {str(e)[:200]}) — "
              f"transcribing the audio instead.")
        return None
    finally:
        if ck_path:
            try:
                os.remove(ck_path)
            except OSError:
                pass
