"""Shortkaar learns from its own Shorts (owner's ask, 14-oct-2026: "iterative
learning": see what works, keep changing what does not).

Every ``LEARN_EVERY`` the Autopilot loop calls ``run``:

1. **Numbers.** Every Short Shortkaar uploaded in the last 30 days gets its
   YouTube numbers (views, likes, comments; watch % and subscribers from
   YouTube Analytics when it answers). A Short counts once it has been public
   ``MATURE_HOURS``: Shorts collect most of their views in the first two
   days, so a younger one would read as a loser.
2. **Sources.** Each source channel gets a score: the median views of its
   Shorts against the channel's overall median (needs 2 counted Shorts,
   clamped 0.3-3). Research ranks videos by views x score
   (``source_factor``), and a channel scoring under ``REST_BELOW`` with 3+
   Shorts rests for ``REST_DAYS``.
3. **Experiments.** One change at a time is tested on Autopilot's comedy
   jobs, alternating per job (``next_arm``): end card, AI take, short clips.
   With ``MIN_PER_ARM`` counted Shorts on each side, the other side wins only
   with median views ``WIN_RATIO`` times the current look and ``WIN_MIN_GAP``
   more; otherwise "no clear difference" and the current look stays. Then the
   next test starts. Kept changes (``adopted``) apply to every Autopilot
   comedy job.
4. **Titles.** The "what works" report (what_works.py, whose title rules
   seo_copy follows) is rebuilt once ``REPORT_NEW`` more Shorts are counted.

Every change is written to ``history`` and shown on My channel. With
``learn`` off it keeps measuring and changes nothing.
"""
import json
import os
import statistics
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "output", ".learning.json")
LEARN_EVERY = 6 * 3600
LOOKBACK_DAYS = 30
MATURE_HOURS = 48
MIN_PER_ARM = 8
WIN_RATIO = 1.3
WIN_MIN_GAP = 5
EXPERIMENT_MAX_DAYS = 21
REST_BELOW = 0.5
REST_DAYS = 14
REPORT_NEW = 5
EXPERIMENTS = [
    {"key": "end_card", "label": "FOLLOW end card at the end", "base": "on",
     "arms": {"on": {}, "off": {"frame_outro": False}}},
    {"key": "ai_take", "label": "AI voice take after the clip", "base": "on",
     "arms": {"on": {}, "off": {"ai_take": False}}},
    {"key": "length", "label": "clip length", "base": "normal",
     "arms": {"normal": {}, "short": {"clip_max_seconds": 35}}},
]
_BY_KEY = {e["key"]: e for e in EXPERIMENTS}
_lock = threading.Lock()


def _default():
    return {"learn": True, "last_run": 0, "stats": {}, "source_channel": {}, "sources": {},
            "experiment": None, "done": [], "adopted": {}, "kept": [], "history": [],
            "report_counted": 0, "locked": 0}


def load():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {**_default(), **data} if isinstance(data, dict) else _default()
    except (OSError, ValueError):
        return _default()


def _save(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)


def set_learn(on):
    with _lock:
        st = load()
        st["learn"] = bool(on)
        _save(st)
    return st


def _note(st, text):
    st["history"] = (st["history"] + [{"at": int(time.time()), "text": text}])[-60:]


def _median(xs):
    return round(statistics.median(xs), 1) if xs else 0


# ------------------------------------------------------------------ experiments

def _start_next(st):
    left = [e for e in EXPERIMENTS if e["key"] not in st["done"]]
    if not left:
        st["experiment"] = None
        return None
    e = left[0]
    st["experiment"] = {"key": e["key"], "started": int(time.time()), "assigned": {a: 0 for a in e["arms"]}}
    _note(st, f"Started a test: {e['label']} ({' vs '.join(e['arms'])}).")
    return st["experiment"]


def next_arm():
    """{"exp", "arm", "overrides"} for the next Autopilot comedy job: the kept
    changes plus this job's side of the running test (fewest Shorts first)."""
    with _lock:
        st = load()
        adopted = dict(st["adopted"])
        if not st["learn"]:
            return {"exp": None, "arm": None, "overrides": adopted}
        exp = st["experiment"] or _start_next(st)
        if not exp:
            _save(st)
            return {"exp": None, "arm": None, "overrides": adopted}
        arms = _BY_KEY[exp["key"]]["arms"]
        arm = min(arms, key=lambda a: (exp["assigned"].get(a, 0), list(arms).index(a)))
        exp["assigned"][arm] = exp["assigned"].get(arm, 0) + 1
        _save(st)
        return {"exp": exp["key"], "arm": arm, "overrides": {**adopted, **arms[arm]}}


def _evaluate(st, log):
    exp = st["experiment"]
    if not exp:
        return
    e = _BY_KEY[exp["key"]]
    counted = {a: [s for s in st["stats"].values() if s.get("counted") and s.get("exp") == e["key"] and s.get("arm") == a]
               for a in e["arms"]}
    ready = all(len(v) >= MIN_PER_ARM for v in counted.values())
    too_long = time.time() - exp["started"] > EXPERIMENT_MAX_DAYS * 86400
    if not ready and not too_long:
        return
    med = {a: _median([s["views"] for s in v]) for a, v in counted.items()}
    base = e["base"]
    other = next(a for a in e["arms"] if a != base)
    if ready and med[other] >= WIN_RATIO * max(med[base], 1) and med[other] - med[base] >= WIN_MIN_GAP:
        st["adopted"].update(e["arms"][other])
        st["kept"] = st.get("kept", []) + [f"{e['label']}: {other}"]
        text = (f"Test finished: {e['label']}: '{other}' won ({med[other]} vs {med[base]} median views). "
                f"Autopilot now uses '{other}'.")
    elif ready:
        text = (f"Test finished: {e['label']}: no clear difference ({med[other]} vs {med[base]} median views). "
                f"Kept '{base}'.")
    else:
        text = f"Test stopped after {EXPERIMENT_MAX_DAYS} days without enough views: {e['label']}. Kept '{base}'."
    st["done"].append(e["key"])
    _note(st, text)
    log(text)
    _start_next(st)


# ------------------------------------------------------------------ sources

def source_factor(channel_url, state=None):
    """Research weight for a source channel: 1.0 when unknown, 0 while resting."""
    s = ((state or load())["sources"]).get(channel_url or "")
    if not s:
        return 1.0
    if s.get("rest_until", 0) > time.time():
        return 0.0
    return s.get("score", 1.0)


def _channel_of(st, url):
    import channel_tools
    import used_moments
    vid = used_moments.video_id(url or "")
    if not vid:
        return None
    if vid not in st["source_channel"]:
        try:
            info = channel_tools.licence(url)
        except Exception:  # noqa: BLE001
            return None
        if not info.get("channel_url"):
            return None
        st["source_channel"][vid] = {"url": info["channel_url"], "name": info.get("channel") or ""}
    return st["source_channel"][vid]


def _score_sources(st, log):
    counted = [s for s in st["stats"].values() if s.get("counted") and s.get("source")]
    overall = _median([s["views"] for s in st["stats"].values() if s.get("counted")])
    by = {}
    for s in counted:
        ch = _channel_of(st, s["source"])
        if ch:
            by.setdefault(ch["url"], {"name": ch["name"], "views": []})["views"].append(s["views"])
    for url, g in by.items():
        if len(g["views"]) < 2:
            continue
        med = _median(g["views"])
        score = round(max(0.3, min(3.0, (med + 1) / (overall + 1))), 2)
        old = st["sources"].get(url, {})
        row = {"name": g["name"], "shorts": len(g["views"]), "median": med, "score": score,
               "rest_until": old.get("rest_until", 0)}
        if st["learn"] and score < REST_BELOW and len(g["views"]) >= 3 and old.get("rest_until", 0) < time.time():
            row["rest_until"] = int(time.time() + REST_DAYS * 86400)
            _note(st, f"Resting {g['name']} for {REST_DAYS} days: its Shorts get {med} median views against {overall}.")
            log(f"Learning: resting {g['name']}.")
        st["sources"][url] = row


# ------------------------------------------------------------------ numbers

def _arm_of(job_id):
    import autopilot_local
    for run in autopilot_local.settings().get("runs") or []:
        for j in run.get("jobs") or []:
            if j.get("job_id") == job_id:
                return j.get("exp"), j.get("arm")
    return None, None


def refresh(st):
    """Fresh YouTube numbers for the last 30 days of Shortkaar uploads."""
    from datetime import datetime
    import youtube_account as ya
    now = time.time()
    rows = [r for r in ya.uploads() if r.get("video_id") and r.get("status") == "done"
            and r.get("created", 0) >= now - LOOKBACK_DAYS * 86400]
    try:
        extra = ya.video_analytics(LOOKBACK_DAYS)
    except Exception:  # noqa: BLE001 — public numbers still count
        extra = {}
    locked = 0
    for k in range(0, len(rows), 50):
        part = rows[k:k + 50]
        items = ya._get(f"{ya.API}/videos", {"part": "statistics,status,contentDetails",
                                             "id": ",".join(r["video_id"] for r in part)}).get("items") or []
        got = {v["id"]: v for v in items}
        for r in part:
            v = got.get(r["video_id"])
            if not v:
                st["stats"].pop(r["video_id"], None)      # deleted on YouTube
                continue
            sv, status = v.get("statistics") or {}, v.get("status") or {}
            planned = r.get("publish_at")
            public_at = datetime.fromisoformat(planned).timestamp() if planned else r.get("created", now)
            blocked = bool(r.get("blocked")) or bool(((v.get("contentDetails") or {}).get("regionRestriction") or {}).get("blocked"))
            public = status.get("privacyStatus") == "public"
            if not public and not blocked and now - public_at > 3600:
                locked += 1                                # past its time and still private
            exp, arm = (r.get("exp"), r.get("arm")) if r.get("exp") else _arm_of(r.get("job_id"))
            st["stats"][r["video_id"]] = {
                "title": r.get("title", "")[:100], "genre": r.get("genre"), "source": r.get("source"),
                "job_id": r.get("job_id"), "exp": exp, "arm": arm, "public_at": int(public_at),
                "views": int(sv.get("viewCount") or 0), "likes": int(sv.get("likeCount") or 0),
                "comments": int(sv.get("commentCount") or 0),
                "seconds": ya._iso_seconds((v.get("contentDetails") or {}).get("duration", "")),
                "avg_percent": (extra.get(r["video_id"]) or {}).get("avg_percent"),
                "subs": (extra.get(r["video_id"]) or {}).get("subs"),
                "blocked": blocked, "public": public,
                "counted": public and not blocked and now - public_at >= MATURE_HOURS * 3600}
    st["locked"] = locked


def due(now=None):
    return (now or time.time()) - load().get("last_run", 0) >= LEARN_EVERY


def run(log=print, handle=""):
    """One learning pass (Autopilot loop, or "learn now")."""
    import youtube_account
    if not youtube_account.status()["connected"]:
        return None
    with _lock:
        st = load()
        st["last_run"] = int(time.time())
        _save(st)
    refresh(st)
    _score_sources(st, log)
    if st["learn"]:
        _evaluate(st, log)
    counted = sum(1 for s in st["stats"].values() if s.get("counted"))
    if st["learn"] and counted - st.get("report_counted", 0) >= REPORT_NEW:
        try:
            import what_works
            what_works.build(handle)
            st["report_counted"] = counted
            _note(st, f"Rebuilt the title rules from {counted} counted Shorts.")
        except Exception as e:  # noqa: BLE001 — the next pass tries again
            log(f"Learning: report failed ({type(e).__name__}).")
    with _lock:
        fresh = load()
        # Assignments made by Autopilot during this pass stay.
        if fresh.get("experiment") and st.get("experiment") and fresh["experiment"]["key"] == st["experiment"]["key"]:
            st["experiment"]["assigned"] = fresh["experiment"]["assigned"]
        st["learn"] = fresh["learn"]
        _save(st)
    return summary(st)


def summary(st=None):
    st = st or load()
    stats = list(st["stats"].values())
    counted = [s for s in stats if s.get("counted")]
    exp = None
    if st["experiment"]:
        e = _BY_KEY[st["experiment"]["key"]]
        exp = {"key": e["key"], "label": e["label"], "base": e["base"], "started": st["experiment"]["started"],
               "need": MIN_PER_ARM, "arms": {}}
        for a in e["arms"]:
            mine = [s for s in counted if s.get("exp") == e["key"] and s.get("arm") == a]
            exp["arms"][a] = {"made": st["experiment"]["assigned"].get(a, 0), "counted": len(mine),
                              "median_views": _median([s["views"] for s in mine])}
    sources = sorted(st["sources"].values(), key=lambda s: s["score"], reverse=True)
    genres = {}
    for s in counted:
        genres.setdefault(s.get("genre") or "comedy", []).append(s["views"])
    return {"learn": st["learn"], "last_run": st["last_run"], "tracked": len(stats), "counted": len(counted),
            "public": sum(1 for s in stats if s.get("public")), "blocked": sum(1 for s in stats if s.get("blocked")),
            "locked": st.get("locked", 0), "median_views": _median([s["views"] for s in counted]),
            "total_views": sum(s["views"] for s in stats), "mature_hours": MATURE_HOURS,
            "genres": {g: {"shorts": len(v), "median_views": _median(v)} for g, v in genres.items()},
            "experiment": exp, "kept": st.get("kept", []), "sources": sources[:12],
            "history": st["history"][-12:][::-1]}
