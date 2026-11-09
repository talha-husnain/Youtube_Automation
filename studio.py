"""Studio: open a finished channel video before (or after) it goes up and fix it (owner, 29-oct-2026: "add
studio to edit video"). The dashboard's Studio tab (StudioTab.jsx) shows the video, its captions and its
details; the edits are made here with ffmpeg.

Every edit follows the project's file conventions, so the upload step picks the edited file with no change
of its own: a trim writes ``recut_<ts>_<clip>.mp4``, captions are burned onto the newest clean cut as
``subtitled_<ts>_<...>.mp4``, and app._canonical_clip_file serves the newest derived file. The spoken words
live in the job metadata's "transcript" (clip time), the title, description and tags in its "shorts" entry.
After any edit the video's checks (video_qa, creative_qa) run again before it uploads.

Caption burns run ``python studio.py reburn <job dir>`` in a subprocess: main.auto_caption_clip is the one
caption path every Short already went through, and importing main.py into the server is heavy.
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(ROOT, "output")
JOB_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# A Studio id names ONE video: a job id (its first clip), or "<job id>.<n>" for the n-th clip of a job cut
# into several Shorts (the main comedy channel's jobs hold 3, 4-nov-2026). Routes, the dashboard and the
# phone's "ref" carry it as it is.
REF = re.compile(r"(" + JOB_ID.pattern + r")(?:\.([1-9][0-9]?))?")
TITLE_MAX = 100                  # YouTube's title limit, in characters
DESCRIPTION_MAX = 5000           # ...and description limit, in bytes
LIST_PER_CHANNEL = 30
MAIN_STATES = {"ready": "waiting", "posted": "uploaded", "skipped": "skipped"}


class StudioError(ValueError):
    """An edit that cannot be made, with a reason the owner can read."""


# Lines that open a credit block in a description: CC BY clips, Commons pictures, maps, stickers, stock
# footage, sources, the Quran's texts and audio. Reusing that material is allowed only with the credit, so an
# edited description (by hand or by the AI editor) keeps every block the old one had (29-oct-2026: a rewrite
# could drop them silently, and one licence strike puts every channel of the owner at risk).
CREDIT_START = re.compile(r"(Credit \(original|Sources:|Pictures:|Map data:|Animated emoji:|Stock footage and photos|"
                          r"Photo of |Flag of |Quran text, translations|Built with Higgs)", re.IGNORECASE)


def credit_blocks(text):
    """The credit blocks of a description: an opening line and the "- " lines under it."""
    blocks, cur = [], None
    for line in (text or "").splitlines():
        if CREDIT_START.match(line.strip()):
            cur = [line.rstrip()]
            blocks.append(cur)
        elif cur is not None and line.strip().startswith("- "):
            cur.append(line.rstrip())
        else:
            cur = None
    return ["\n".join(b) for b in blocks]


def keep_credits(old, new):
    """``new`` with every credit block of ``old`` that it lost put back, before its hashtag line; the body
    is shortened, never the credits, when that passes YouTube's 5,000 bytes."""
    new = (new or "").strip()
    missing = [b for b in credit_blocks(old) if b.splitlines()[0].strip()[:40].lower() not in new.lower()]
    if not missing:
        return new
    lines = new.splitlines()
    tags = lines.pop() if lines and re.fullmatch(r"(#\w+\s*)+", lines[-1].strip()) else ""
    tail = "\n\n" + "\n\n".join(missing) + (f"\n\n{tags}" if tags else "")
    body = "\n".join(lines).rstrip()
    room = DESCRIPTION_MAX - len(tail.encode("utf-8"))
    if len(body.encode("utf-8")) > room:
        body = body.encode("utf-8")[:max(0, room)].decode("utf-8", "ignore").rstrip()
    return (body + tail).strip()


def split_ref(ref):
    """(job id, clip index) of a Studio id."""
    m = REF.fullmatch(ref or "")
    if not m:
        raise StudioError("Not a video id.")
    return m.group(1), int(m.group(2) or 1) - 1


def ref_of(job_id, index=0):
    return job_id if not index else f"{job_id}.{int(index) + 1}"


def job_dir(ref):
    """The job folder of a Studio id (a job id or "<job id>.<n>")."""
    job_id, _index = split_ref(ref)
    path = os.path.join(OUTPUT_DIR, job_id)
    if not os.path.isdir(path):
        raise StudioError("That video is no longer on this computer (finished videos are kept for a while).")
    return path


def clip_of(data, index):
    """The ``shorts`` entry of clip ``index``."""
    shorts = data.get("shorts") or []
    if not 0 <= index < len(shorts):
        raise StudioError("That clip is not in this video.")
    return shorts[index]


def _words_of(transcript):
    return [w for s in (transcript or {}).get("segments") or [] for w in s.get("words") or []
            if (w.get("word") or "").strip()]


def shares_transcript(data, index=0):
    """True when the metadata's transcript is the whole SOURCE's (source seconds), shared by the job's clips:
    the comedy pipeline cuts several Shorts from one long show. A channel Short or an upload keeps its own
    words in clip time, so no word ends far past the clip's length."""
    words = _words_of(data.get("transcript"))
    shorts = data.get("shorts") or []
    if not words or not 0 <= index < len(shorts):
        return len(shorts) > 1
    short = shorts[index]
    length = float(short.get("end") or 0) - float(short.get("start") or 0)
    return len(shorts) > 1 or max(float(w.get("end") or 0) for w in words) > length + 3


def clip_transcript(data, index=0):
    """Clip ``index``'s words in clip seconds: the transcript itself for a job with its own words, else the
    slice of the source's words its captions were made from (the words that overlap the clip, as
    subtitles._collect_word_blocks takes them, moved to start at 0)."""
    tr = data.get("transcript")
    if not shares_transcript(data, index):
        return tr
    short = clip_of(data, index)
    a, b = float(short.get("start") or 0), float(short.get("end") or 0)
    segs = []
    for s in (tr or {}).get("segments") or []:
        words = [{"word": w["word"], "start": round(max(0.0, float(w["start"]) - a), 3),
                  "end": round(max(0.0, float(w["end"]) - a), 3)}
                 for w in s.get("words") or []
                 if (w.get("word") or "").strip() and float(w.get("end", 0)) > a and float(w.get("start", 0)) < b]
        if words:
            segs.append({"start": words[0]["start"], "end": words[-1]["end"],
                         "text": " ".join(w["word"].strip() for w in words), "words": words})
    return {"language": (tr or {}).get("language"), "segments": segs}


def _source(path):
    try:
        with open(os.path.join(path, ".source.json"), encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def main_clip(job_id, index=0, path=None):
    """The main channel's post-queue row of a clip ({"status", "youtube_id", ...}), or None when the job is
    not the main channel's (a channel's Short, a long video, the owner's upload)."""
    path = path or os.path.join(OUTPUT_DIR, job_id)
    src = _source(path)
    if not src or src.get("genre") in ("long", "studio_upload") or src.get("channel") not in (None, "", "main"):
        return None
    import post_queue
    row = dict(post_queue._load().get(post_queue.item_id(job_id, index)) or {})
    row.setdefault("status", "ready")
    return row


def main_state(row):
    return MAIN_STATES.get((row or {}).get("status"), "waiting")


def _meta_path(path):
    metas = glob.glob(os.path.join(path, "*_metadata.json"))
    if not metas:
        raise StudioError("That video has no details file (it may not have finished).")
    return metas[0]


def _read(path):
    with open(_meta_path(path), encoding="utf-8") as f:
        return json.load(f)


def _write(path, data):
    meta = _meta_path(path)
    with open(meta + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(meta + ".tmp", meta)


def _base(path):
    return os.path.basename(_meta_path(path)).replace("_metadata.json", "")


def clean_source(path, index=0):
    """The newest clean cut of the clip (a trim's recut_ file, else the render), without captions."""
    clean = f"{_base(path)}_clip_{index + 1}.mp4"
    recuts = glob.glob(os.path.join(path, f"recut_*_{clean}"))
    if recuts:
        return max(recuts, key=os.path.getmtime)
    if not os.path.isfile(os.path.join(path, clean)):
        raise StudioError("The clean render of this video is gone, so it cannot be edited.")
    return os.path.join(path, clean)


def served(path, index=0):
    """The file the dashboard plays and the upload sends: the newest derived file, else the clean one."""
    clean = f"{_base(path)}_clip_{index + 1}.mp4"
    # The same files app._canonical_clip_file picks for the upload (hooked_: a hook burned without captions).
    derived = (glob.glob(os.path.join(path, f"subtitled_*_{clean}")) + glob.glob(os.path.join(path, f"recut_*_{clean}"))
               + glob.glob(os.path.join(path, f"hooked_*_{clean}")))
    return max(derived, key=os.path.getmtime) if derived else os.path.join(path, clean)


def duration(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                         capture_output=True, text=True, timeout=60).stdout.strip()
    try:
        return round(float(out), 3)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------- reading

def _find_job(job_id, channels):
    m = REF.fullmatch(job_id or "")
    if m and m.group(2) not in (None, "1"):
        return None, None               # a channel's job is one clip: "<id>.2" is never one
    job_id = m.group(1) if m else job_id
    for ch in channels:
        for j in ch.get("jobs") or []:
            if j.get("job_id") == job_id:
                return ch, j
    return None, None


def state_of(ch, j, now=None):
    """What the owner sees: waiting / held for review / uploaded / failed / skipped / making."""
    import my_channels
    s = j.get("status")
    if s == "done":
        return "held for review" if my_channels.held_for_review(ch, j, now) and not j.get("approved") else "waiting"
    return {"running": "making", "uploaded": "uploaded"}.get(s, s or "unknown")


def videos(channels, now=None, main=None, main_name="Main channel"):
    """Every channel's recent videos still on this computer, newest first. ``main``: the main channel's
    clips (app._queue_clips rows: job_id, index, created), one Studio video per clip."""
    rows = []
    for c in sorted(main or [], key=lambda c: (-(c.get("created") or 0), c.get("index") or 0))[:LIST_PER_CHANNEL]:
        jid, index = c.get("job_id") or "", int(c.get("index") or 0)
        path = os.path.join(OUTPUT_DIR, jid)
        if not JOB_ID.fullmatch(jid) or not os.path.isdir(path):
            continue
        try:
            name = os.path.basename(served(path, index))
        except Exception:  # noqa: BLE001 — a half-written job is left out
            continue
        if not os.path.isfile(os.path.join(path, name)):
            continue
        row = main_clip(jid, index, path) or {}
        rows.append({"job_id": ref_of(jid, index), "channel": "main", "channel_name": main_name, "kind": "comedy",
                     "state": main_state(row), "label": c.get("title") or "", "format": "comedy",
                     "at": c.get("created"), "done_at": c.get("created"), "video_id": row.get("youtube_id"),
                     "look": None, "error": "A copyright claim blocked it." if row.get("blocked") else None,
                     "url": f"/videos/{jid}/{name}"})
    for ch in channels:
        for j in sorted(ch.get("jobs") or [], key=lambda j: -j.get("at", 0))[:LIST_PER_CHANNEL]:
            jid = j.get("job_id") or ""
            path = os.path.join(OUTPUT_DIR, jid)
            if not JOB_ID.fullmatch(jid) or not os.path.isdir(path) or not glob.glob(os.path.join(path, "*_metadata.json")):
                continue
            try:
                name = os.path.basename(served(path))
            except Exception:  # noqa: BLE001 — a half-written job is left out
                continue
            if not os.path.isfile(os.path.join(path, name)):
                continue
            rows.append({"job_id": jid, "channel": ch["id"], "channel_name": ch.get("name") or ch["id"],
                         "kind": ch.get("kind"), "state": state_of(ch, j, now), "label": j.get("label") or j.get("topic") or "",
                         "format": j.get("format") or "", "at": j.get("at"), "done_at": j.get("done_at"),
                         "video_id": j.get("video_id"), "look": j.get("look"), "error": j.get("error"),
                         "url": f"/videos/{jid}/{name}"})
    # The owner's own videos, uploaded into the Studio to edit by prompt (ai_editor.py).
    import ai_editor
    for u in ai_editor.uploads():
        jid = u.get("job_id") or ""
        path = os.path.join(OUTPUT_DIR, jid)
        if not JOB_ID.fullmatch(jid) or not glob.glob(os.path.join(path, "*_metadata.json")):
            continue
        try:
            name = os.path.basename(served(path))
        except Exception:  # noqa: BLE001
            continue
        rows.append({"job_id": jid, "channel": "uploads", "channel_name": "Your uploads", "kind": "upload",
                     "state": upload_state(path), "label": u.get("name") or "My video", "format": "upload",
                     "at": u.get("at"), "done_at": u.get("at"), "video_id": None, "look": None, "error": None,
                     "url": f"/videos/{jid}/{name}"})
    return sorted(rows, key=lambda r: -(r.get("done_at") or r.get("at") or 0))


def upload_state(path):
    return "transcribing" if os.path.exists(os.path.join(path, ".transcribing")) else "your upload"


def detail(job_id, channels, main_name="Main channel"):
    path = job_dir(job_id)
    jid, index = split_ref(job_id)
    data = _read(path)
    short = clip_of(data, index)
    ch, j = _find_job(job_id, channels)
    video = served(path, index)
    segments = [{"start": round(float(s.get("start", 0)), 3), "end": round(float(s.get("end", 0)), 3),
                 "text": (s.get("text") or "").strip()}
                for s in (clip_transcript(data, index) or {}).get("segments") or [] if (s.get("text") or "").strip()]
    upload = data.get("genre") == "studio_upload"
    main = None if ch or upload else main_clip(jid, index, path)
    # A clip that shares its words file with the job's other clips is changed through the AI editor only:
    # the manual caption save and trim rewrite the shared transcript, and their re-burn clears every
    # captioned file of the folder, the other clips' too.
    manual = not shares_transcript(data, index)
    if main is not None:
        state = main_state(main)
    else:
        state = state_of(ch, j) if ch else (upload_state(path) if upload else "not on a channel")
    return {"job_id": ref_of(jid, index), "channel": ch["id"] if ch else ("uploads" if upload else ("main" if main is not None else None)),
            "channel_name": (ch or {}).get("name") or ("Your uploads" if upload else (main_name if main is not None else None)),
            "kind": (ch or {}).get("kind") or ("upload" if upload else ("comedy" if main is not None else None)),
            "state": state, "upload": upload, "main": main is not None, "clip": index + 1,
            "clips": len(data.get("shorts") or []), "manual": manual,
            "video_id": (j or {}).get("video_id") or (main or {}).get("youtube_id"), "look": (j or {}).get("look"),
            "error": (j or {}).get("error") or ("A copyright claim blocked it." if (main or {}).get("blocked") else None),
            "url": f"/videos/{jid}/{os.path.basename(video)}", "seconds": duration(video),
            "vertical": _vertical(video),
            "title": short.get("seo_title") or short.get("video_title_for_youtube_short") or "",
            "description": short.get("seo_description") or "", "tags": short.get("seo_tags") or [],
            "on_screen_title": short.get("video_title_for_youtube_short") or "",
            "captions": segments,
            "captions_editable": manual and bool(segments) and data.get("output_format") == "framed",
            "visual_check": _last_look(video)}


def _account_of(job_id, channels):
    """(youtube_account account, video id) of an uploaded Studio video, or (None, None)."""
    jid, index = split_ref(job_id)
    ch, j = _find_job(job_id, channels)
    if ch and j and j.get("video_id"):
        import my_channels
        return my_channels.account(ch["id"]), j["video_id"]
    main = None if ch else main_clip(jid, index)
    if main and main.get("status") == "posted" and main.get("youtube_id"):
        return None, main["youtube_id"]                 # the main channel is the default account
    return None, None


def insights(job_id, channels, fetch=True):
    """An uploaded video's numbers from YouTube (yt_insights): its retention curve with the words said at each big
    drop, and the search terms that found it (read once a day). {"on_youtube": False} before it is up."""
    import youtube_account as ya
    import yt_insights
    acct, vid = _account_of(job_id, channels)
    if not vid:
        return {"on_youtube": False}
    path = job_dir(job_id)
    _jid, index = split_ref(job_id)
    words = []
    try:
        words = _words_of(clip_transcript(_read(path), index))
    except StudioError:
        pass
    with ya.use(acct):
        row = next((r for r in ya.uploads() if r.get("video_id") == vid), None) or {}
        if fetch and ya.status().get("connected") and time.time() - row.get("search_at", 0) > 20 * 3600:
            try:
                row["search"] = yt_insights.search_terms(vid, days=365)
                row["search_at"] = int(time.time())
                if row.get("id"):
                    ya._save_upload(row)
            except Exception as e:  # noqa: BLE001 — shown as "not yet"
                row.setdefault("search_error", str(e)[:160])
    curve = row.get("curve") or None
    if curve:
        curve = {**curve, "drops": [{**d, "said": yt_insights.words_at(words, d["at"], d["to"])}
                                    for d in curve.get("drops") or []]}
    return {"on_youtube": True, "video_id": vid, "views": row.get("views"), "retention": row.get("retention"),
            "stayed": row.get("stayed"), "curve": curve, "ctr": row.get("ctr"), "impressions": row.get("impressions"),
            "search": [list(t) for t in row.get("search") or []], "seconds": row.get("seconds")}


def _vertical(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", video], capture_output=True, text=True, timeout=60).stdout.strip()
    try:
        w, h = (int(x) for x in out.split(",")[:2])
        return h > w
    except ValueError:
        return True


def _last_look(video):
    """The latest creative_qa verdict recorded for this file's job, or None."""
    try:
        import creative_qa
        folder = os.path.dirname(video)
        with open(creative_qa.LOG, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        rows = [r for r in rows if r.get("path") and os.path.dirname(r["path"]) == folder and "polish" in r]
        return rows[-1] if rows else None
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- edits

def _not_uploaded(job_id, channels):
    _ch, j = _find_job(job_id, channels)
    jid, index = split_ref(job_id)
    if (j and j.get("status") == "uploaded") or (not j and (main_clip(jid, index) or {}).get("status") == "posted"):
        raise StudioError("This video is already on YouTube, which keeps the file it was sent; edit its title and "
                          "description here, or remove it in YouTube Studio.")


def _own_words_only(data, index):
    clip_of(data, index)
    if shares_transcript(data, index):
        raise StudioError("This clip shares its words with the other clips cut from the same show, so change it "
                          "in the AI box above instead: e.g. \"pehle 2 second kaato\" or \"caption mein 'X' ko "
                          "'Y' karo\".")


def _recheck(job_id, channels):
    """The file changed: its checks run again before it uploads."""
    import my_channels
    ch, j = _find_job(job_id, channels)
    if ch and j:
        my_channels._set_job(ch["id"], job_id, qa=None, look=None, qa_tries=0, edited=int(time.time()))


def save_details(job_id, channels, title=None, description=None, tags=None, push=False):
    """New title / description / tags for the upload (and, with ``push``, for the video already on YouTube:
    videos.update, 50 units of the day's quota). Returns {"saved": True, "pushed": bool}."""
    path = job_dir(job_id)
    jid, index = split_ref(job_id)
    data = _read(path)
    short = clip_of(data, index)
    if title is not None:
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            raise StudioError("The title cannot be empty.")
        if len(title) > TITLE_MAX:
            raise StudioError(f"The title is {len(title)} characters; YouTube allows {TITLE_MAX}.")
        short["seo_title"] = title
    if description is not None:
        description = keep_credits(short.get("seo_description"), description)
        if len(description.encode("utf-8")) > DESCRIPTION_MAX:
            raise StudioError(f"The description is over YouTube's {DESCRIPTION_MAX:,} bytes.")
        short["seo_description"] = description.strip()
    if tags is not None:
        short["seo_tags"] = [t.strip() for t in tags if t and t.strip()][:40]
    _write(path, data)
    pushed = False
    ch, j = _find_job(job_id, channels)
    if push and j and j.get("video_id"):
        import my_channels
        import youtube_account as ya
        with ya.use(my_channels.account(ch["id"])):
            ya.update_video(j["video_id"], title=short.get("seo_title"), description=short.get("seo_description"),
                            tags=short.get("seo_tags"))
        pushed = True
    elif push and not j:
        main = main_clip(jid, index, path) or {}
        if main.get("status") == "posted" and main.get("youtube_id"):
            import youtube_account as ya        # the main channel is the default account
            ya.update_video(main["youtube_id"], title=short.get("seo_title"),
                            description=short.get("seo_description"), tags=short.get("seo_tags"))
            pushed = True
    return {"saved": True, "pushed": pushed}


def title_options(job_id, channels, client=None, suggest=None):
    """For the Studio's title chips: other titles (the title tournament's contenders that pass its checks,
    so none brings a number or name the video does not have) and what people type into YouTube search
    about it (its autocomplete, the first 2 and 4 words of the topic). Nothing is saved."""
    import script_craft
    path = job_dir(job_id)
    _jid, index = split_ref(job_id)
    data = _read(path)
    short = clip_of(data, index)
    title = short.get("seo_title") or short.get("video_title_for_youtube_short") or ""
    if not title.strip():
        raise StudioError("This video has no title to start from yet.")
    facts = " ".join(s.get("text") or "" for s in (clip_transcript(data, index) or {}).get("segments") or [])
    facts = (facts + "\n" + (short.get("seo_description") or ""))[:6000]
    ch, j = _find_job(job_id, channels)
    english = (ch or {}).get("kind") == "music" or (ch or {}).get("lang") == "english"
    what = "long YouTube video" if duration(served(path, index)) > 180 else "YouTube Short"
    if client is None:
        import short_kit as kit
        client = kit.gemini()
    try:
        head, tail, alive, _n = script_craft.title_options(client, title, facts, what,
                                                           "English" if english else script_craft.ROMAN)
    except Exception as e:  # noqa: BLE001 — the owner can ask again
        raise StudioError(f"No title ideas this time ({type(e).__name__}); try again in a minute.")
    if suggest is None:
        import trend_explainer
        suggest = trend_explainer.suggestions
    words = re.sub(r"'s\b|[^\w\s]", " ", ((j or {}).get("topic") or head).lower()).split()
    # The topic's first 4 words first: the first 2 alone ("nicki minaj") brought "nicki minaj cartoon" on a
    # controversy Short (first live call, 29-oct-2026); the longer phrase is the video's own subject.
    searches = []
    for q in dict.fromkeys((" ".join(words[:4]), " ".join(words[:2]))):
        if len(q) >= 4:
            searches += [s for s in suggest(q)[:8] if s not in searches]
    return {"current": title, "options": [f"{t} {tail}".strip() for t in alive], "searches": searches[:10]}


def _respread(seg, text):
    """The segment's words for edited ``text``: the old timings when the word count is unchanged (a spelling
    fix), else spread over the segment by word length."""
    words = text.split()
    old = seg.get("words") or []
    if len(old) == len(words):
        return [{**w, "word": " " + n} for w, n in zip(old, words)]
    start = float(old[0]["start"]) if old else float(seg.get("start", 0))
    end = float(old[-1]["end"]) if old else float(seg.get("end", start + 1))
    weights = [len(w) + 2 for w in words] or [1]
    total, t, out = sum(weights), start, []
    for w, wt in zip(words, weights):
        d = (end - start) * wt / total
        out.append({"word": " " + w, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return out


def save_captions(job_id, channels, segments, reburn_fn=None):
    """Edited caption texts ([{"index"?, "text"}] in the order shown), burned onto the clean cut.
    Returns the new file's URL."""
    path = job_dir(job_id)
    _not_uploaded(job_id, channels)
    data = _read(path)
    _own_words_only(data, split_ref(job_id)[1])
    if data.get("output_format") != "framed":
        raise StudioError("This kind of video keeps its captions another way; they cannot be edited here.")
    segs = [s for s in (data.get("transcript") or {}).get("segments") or [] if (s.get("text") or "").strip()]
    if len(segments) != len(segs):
        raise StudioError("The captions changed since they were opened; open the video again.")
    for seg, new in zip(segs, segments):
        text = re.sub(r"\s+", " ", (new.get("text") or "")).strip()
        if text and text != (seg.get("text") or "").strip():
            seg["words"] = _respread(seg, text)
            seg["text"] = text
        elif not text:
            seg["words"], seg["text"] = [], ""        # an emptied caption is not shown
    _write(path, data)
    (reburn_fn or reburn)(path)
    _recheck(job_id, channels)
    return f"/videos/{job_id}/{os.path.basename(served(path))}"


def trim(job_id, channels, start, end, reburn_fn=None):
    """Keep ``start``..``end`` seconds of the clean cut, move the captions with it and burn them again."""
    path = job_dir(job_id)
    _not_uploaded(job_id, channels)
    _own_words_only(_read(path), split_ref(job_id)[1])
    src = clean_source(path)
    length = duration(src)
    start, end = max(0.0, float(start)), min(float(end), length) if length else float(end)
    if end - start < 3:
        raise StudioError("Keep at least 3 seconds.")
    if start < 0.05 and length and end > length - 0.05:
        raise StudioError("That keeps the whole video; nothing to trim.")
    clean = f"{_base(path)}_clip_1.mp4"
    out = os.path.join(path, f"recut_{int(time.time())}_{clean}")
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                        "-i", src, "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out],
                       capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not os.path.isfile(out):
        raise StudioError(f"The trim failed: {r.stderr.strip()[-200:]}")
    data = _read(path)
    kept = []
    for seg in (data.get("transcript") or {}).get("segments") or []:
        words = [{**w, "start": round(float(w["start"]) - start, 3), "end": round(float(w["end"]) - start, 3)}
                 for w in seg.get("words") or [] if float(w["start"]) >= start - 0.05 and float(w["end"]) <= end + 0.05]
        if words:
            kept.append({**seg, "words": words, "start": words[0]["start"], "end": words[-1]["end"],
                         "text": " ".join(w["word"].strip() for w in words)})
    if data.get("transcript"):
        data["transcript"]["segments"] = kept
    short = data["shorts"][0]
    short["end"] = round(float(short.get("start", 0)) + (end - start), 3)
    short["seconds"] = round(end - start, 3)
    _write(path, data)
    if kept and data.get("output_format") == "framed":
        (reburn_fn or reburn)(path)
    _recheck(job_id, channels)
    return f"/videos/{job_id}/{os.path.basename(served(path))}"


def act(job_id, channels, action):
    """approve (the review hold ends: it uploads into its next posting time), skip (never uploaded; the
    channel makes another), remake (skip, and its topic goes back to the front of the ideas)."""
    import my_channels
    ch, j = _find_job(job_id, channels)
    if not ch:
        return _act_main(job_id, action)
    if action == "approve":
        if j.get("status") != "done":
            raise StudioError("Only a finished video that has not gone up can be approved.")
        my_channels._set_job(ch["id"], job_id, approved=True)
        return "Approved: it goes up at the channel's next posting time."
    if action in ("skip", "remake"):
        if not my_channels.skip(ch["id"], job_id):
            raise StudioError("Only a finished video that has not gone up can be skipped.")
        if action == "remake":
            my_channels._remake(ch["id"], j)
            return "Skipped; its topic is made again next."
        return "Skipped: it will not go up, and the channel makes another in its place."
    raise StudioError("Unknown action.")


def _act_main(ref, action):
    """The main channel's clips post from Ready to post: skip takes one out, approve puts a skipped one back.
    A comedy clip has no topic to make again (Autopilot cuts new ones from new shows)."""
    import post_queue
    jid, index = split_ref(ref)
    row = main_clip(jid, index)
    if row is None:
        raise StudioError("That video does not belong to a channel.")
    if action == "skip":
        if row["status"] != "ready":
            raise StudioError("Only a clip still waiting to post can be skipped.")
        post_queue.update(post_queue.item_id(jid, index), status="skipped")
        return "Skipped: this clip will not be posted."
    if action == "approve":
        if row["status"] != "skipped":
            raise StudioError("This clip is already waiting to post.")
        post_queue.update(post_queue.item_id(jid, index), status="ready")
        return "Back in Ready to post: it goes up at the next free posting time."
    if action == "remake":
        raise StudioError("A comedy clip cannot be made again; skip it and Autopilot cuts new ones.")
    raise StudioError("Unknown action.")


def poster(job_id):
    """A JPEG of the video's first frame (cached until the video changes)."""
    path = job_dir(job_id)
    _jid, index = split_ref(job_id)
    video = served(path, index)
    out = os.path.join(path, ".studio_poster.jpg" if not index else f".studio_poster_{index + 1}.jpg")
    if not os.path.isfile(out) or os.path.getmtime(out) < os.path.getmtime(video):
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", "0.2", "-i", video, "-frames:v", "1",
                        "-vf", "scale=360:-2", out], capture_output=True, timeout=60)
    if not os.path.isfile(out):
        raise StudioError("No picture for that video.")
    return out


# ---------------------------------------------------------------- captions burn (subprocess)

def reburn(path, timeout=1800):
    """Burn the metadata's captions onto the newest clean cut, in a subprocess (see the module note)."""
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "reburn", path], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if r.returncode != 0 or "BURNED " not in r.stdout:
        raise StudioError("The captions could not be burned: "
                          + ((r.stderr or r.stdout).strip().splitlines() or ["no output"])[-1][-200:])


def _reburn_here(path):
    import main
    data = _read(path)
    src = clean_source(path)
    # Generated Shorts colour their numbers and names (subtitles._emphasised), as short_kit.finish set it.
    if (data.get("genre") or "") != "comedy":
        os.environ.setdefault("CAPTION_EMPHASIS", "1")
    before = set(glob.glob(os.path.join(path, "subtitled_*")))
    out = main.auto_caption_clip(src, data.get("transcript"), 0.0, duration(src))
    if not out:
        raise SystemExit("no captions were burned")
    for old in before:                      # superseded captioned copies
        if os.path.abspath(old) != os.path.abspath(out):
            try:
                os.remove(old)
            except OSError:
                pass
    print("BURNED " + os.path.basename(out))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "reburn":
        _reburn_here(sys.argv[2])
    else:
        raise SystemExit("usage: studio.py reburn <job dir>")
