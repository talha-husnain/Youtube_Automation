"""What is holding a channel back, answered from its own numbers (owner, 5-nov-2026, sharing the REA repo:
"take all the good things that can make our system better and stronger").

REA's investigation method, applied to a channel instead of a program: turn the question into a checklist,
answer each item with the evidence it needs, keep what was observed apart from what is inferred, and say
plainly what is still unknown instead of guessing. Every check here returns

    {"key", "question", "status", "finding", "evidence": [str | {"label", "url"}], "next"}

with status "problem" (fix this), "tip" (a clear chance to do better), "unknown" (not enough data yet, and
how much is missing), "info" or "good". Problems come first. Observations come only from YouTube's own
numbers (the learn pass), our measurements (teardown.py) and the card itself; the system's own reaction to
each finding is named in "next", so the owner sees what is already being done about it.
"""
import statistics
import time

STATUS_ORDER = {"problem": 0, "tip": 1, "unknown": 2, "info": 3, "good": 4}
DAY = 86400
MIN_VIDEOS = 3


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _fmt(x):
    return f"{x:,.0f}" if isinstance(x, (int, float)) and abs(x) >= 10 else f"{x:g}"


def _check(key, question, status, finding, evidence=(), next_=""):
    return {"key": key, "question": question, "status": status, "finding": finding,
            "evidence": list(evidence), "next": next_}


def _main_videos(rows, extra):
    return [r for r in rows if r.get("status") == "done" and r.get("format") not in extra]


def posting(ch, rows, now, extra=(), started=None):
    """Did the videos it planned go up this week?"""
    q = "Is it posting what it plans?"
    started = started or ch.get("created") or now
    days = min(7.0, max(0.0, (now - started) / DAY))
    planned = int(round(int(ch.get("per_day") or 1) * days))
    if planned < 1:
        return _check("posting", q, "unknown", "Too new to judge: less than a day of posting.")
    made = sum(1 for r in _main_videos(rows, extra) if now - (r.get("created") or 0) <= 7 * DAY)
    failed = [j for j in ch.get("jobs") or [] if j.get("status") == "failed" and now - (j.get("at") or 0) <= 7 * DAY]
    share = made / planned
    finding = f"{made} of {planned} planned videos went up in the last {days:g} days" + (
        f"; {len(failed)} failed to make" if failed else "") + "."
    ev = [f"failed: {(j.get('label') or '')[:60]} ({(j.get('error') or 'no reason kept')[:80]})" for j in failed[:3]]
    if share >= 0.85:
        return _check("posting", q, "good", finding, ev)
    return _check("posting", q, "problem" if share < 0.6 else "tip", finding, ev,
                  "Each failed job on the card says why. Transient failures (quota, network) are made again by "
                  "themselves; others mean the planner skips that idea.")


def reach(rows, now, extra=()):
    """Is YouTube showing its videos to people, and is that growing?"""
    q = "Does YouTube show its videos to people?"
    vids = [r for r in _main_videos(rows, extra) if r.get("views") is not None]
    recent = [r for r in vids if 2 * DAY <= now - (r.get("created") or 0) <= 9 * DAY]
    before = [r for r in vids if 9 * DAY < now - (r.get("created") or 0) <= 23 * DAY]
    if len(recent) < MIN_VIDEOS:
        return _check("reach", q, "unknown", f"{len(recent)} videos are 2-9 days old; {MIN_VIDEOS} are needed to say.")

    def views(r):
        return r.get("views_48h", r.get("views"))
    a, b = _median([views(r) for r in recent]), _median([views(r) for r in before])
    finding = f"Its videos from the last week have a median of {_fmt(a)} views ({len(recent)} videos)" + (
        f"; the two weeks before, {_fmt(b)} ({len(before)})." if b is not None else ".")
    best = max(recent, key=lambda r: views(r) or 0)
    ev = [{"label": f"best this week: {(best.get('title') or '')[:60]} ({_fmt(views(best))} views)",
           "url": f"https://youtu.be/{best['video_id']}"}] if best.get("video_id") else []
    rising = b is not None and len(before) >= MIN_VIDEOS and a >= 1.5 * max(b, 1) and a >= 20
    if a >= 100 or rising:
        return _check("reach", q, "good", finding + (" Growing." if rising else ""), ev)
    if a < 10 and not rising:
        return _check("reach", q, "problem", finding, ev,
                      "YouTube tests each Short on a few viewers and spreads only those they keep watching: the "
                      "next check says where they leave, and the writers get those times.")
    return _check("reach", q, "info", finding, ev)


def staying(ch, rows, long):
    """How much of each video people watch, and where half of them are gone."""
    q = "Do viewers stay past the start?"
    st = ch.get("stats") or {}
    w = st.get("watched")
    kept = [r for r in rows if r.get("retention") is not None]
    if w is None or len(kept) < MIN_VIDEOS:
        return _check("staying", q, "unknown",
                      f"YouTube gave watch numbers for {len(kept)} videos so far; {MIN_VIDEOS} are needed.")
    half = _median([(r.get("curve") or {}).get("half_at") for r in rows if (r.get("curve") or {}).get("half_at")])
    finding = f"Viewers watch {_fmt(w)}% of each video (median of {len(kept)})" + (
        f"; half of them are gone by {int(half // 60)}:{int(half % 60):02d}." if half else ".")
    ev = [st["retention_lesson"][:300]] if st.get("retention_lesson") else []
    good, bad = (40, 25) if long else (70, 45)
    if w >= good:
        return _check("staying", q, "good", finding, ev)
    return _check("staying", q, "problem" if w < bad else "tip", finding, ev,
                  "The writers and the AI editor get these leave times (retention lesson), and the opening is "
                  "being matched to the niche's winners (the teardown check below).")


def formats(ch, score):
    """Which of its formats wins."""
    q = "Which kind of video works best on it?"
    fm = {k: v for k, v in ((ch.get("stats") or {}).get("formats") or {}).items() if v.get("shorts", 0) >= MIN_VIDEOS}
    if len(fm) < 2:
        return _check("formats", q, "unknown", f"{len(fm)} format(s) have {MIN_VIDEOS}+ videos; two are needed to compare.")
    ranked = sorted(fm.items(), key=lambda kv: score(kv[1]), reverse=True)
    (bk, bv), (wk, wv) = ranked[0], ranked[-1]
    finding = (f"Best: {bk} (median {_fmt(bv['median'])} views over {bv['shorts']}); weakest: {wk} "
               f"(median {_fmt(wv['median'])} over {wv['shorts']}).")
    ev = [f"{k}: median {_fmt(v['median'])} views, {v['shorts']} videos"
          + (f", {_fmt(v['watched'])}% watched" if v.get("watched") is not None else "") for k, v in ranked]
    return _check("formats", q, "info", finding, ev, "The planner already makes the best ones most often.")


def timing(ch, tip):
    q = "Is it posting at its best hours?"
    hours = (ch.get("stats") or {}).get("hours") or {}
    if tip:
        return _check("timing", q, "tip", tip["text"],
                      [f"{h}:00: median {_fmt(v['median'])} views over {v['shorts']}" for h, v in sorted(hours.items())],
                      "Change it in the card's posting times (one click on Today).")
    if not hours:
        return _check("timing", q, "unknown", "No counted videos by posting hour yet.")
    return _check("timing", q, "good", "No posting hour clearly beats the others yet.")


def tests(ch, experiments, winner, ab_min):
    q = "What have its A/B tests found?"
    seen = (ch.get("stats") or {}).get("ab") or {}
    lines, won = [], False
    for key, exp in experiments.items():
        if ch.get("kind") not in exp["kinds"]:
            continue
        res = seen.get(key) or {}
        sides = [(name, res.get(str(arm).lower()) or {}) for arm, name in zip(exp["arms"], exp["names"])]
        w = winner(res, key) if res else None
        if w is not None:
            won = True
            lines.append(f"{exp['label']}: '{exp['names'][exp['arms'].index(w)]}' won "
                         + " vs ".join(f"{n} median {_fmt(s.get('median', 0))}" for n, s in sides) + ".")
        elif res:
            lines.append(f"{exp['label']}: no winner yet ("
                         + ", ".join(f"{n} {s.get('shorts', 0)} of {ab_min}" for n, s in sides) + ").")
    if not lines:
        return _check("tests", q, "unknown", "No test has counted videos yet.")
    return _check("tests", q, "good" if won else "unknown", " ".join(lines[:2]), lines,
                  "A winning side is used most of the time from then on; the rest keep alternating.")


def niche(research, compare, winners, need):
    q = "How far is it from the niche's winners?"
    research = research or {}
    rows = compare(research)
    theirs = sum(1 for r in (research.get("anatomy") or {}).values() if r.get("m"))
    ours = sum(1 for r in (research.get("ours") or {}).values() if r.get("m"))
    ev = [{"label": f"measured winner: {(w.get('title') or '')[:60]} ({_fmt(w.get('views') or 0)} views)",
           "url": f"https://youtu.be/{w['id']}"} for w in winners(research)]
    if not rows:
        if theirs < need[0] or ours < need[1]:
            return _check("niche", q, "unknown", f"{theirs} of {need[0]} winners and {ours} of {need[1]} of ours are "
                          "measured; the research pass measures a few more each day.", ev)
        return _check("niche", q, "good", f"Measured against {theirs} winners: no clear gap.", ev)
    top = rows[0]
    unit = top["unit"] if top["unit"] in ("s", "%") else ""
    finding = (f"{len(rows)} measured gap(s). Biggest: {top['name']}, theirs {_fmt(top['theirs'])}{unit}, ours "
               f"{_fmt(top['ours'])}{unit}: {top['advice']}.")
    lines = [f"{r['name']}: theirs {_fmt(r['theirs'])}, ours {_fmt(r['ours'])} ({r['n_theirs']} winners, "
             f"{r['n_ours']} of ours): {r['advice']}" for r in rows]
    return _check("niche", q, "tip", finding, lines + ev,
                  "These lines go into every script prompt of the niche; the cut pace is tested against ours.")


def search(ch):
    q = "Do people find it by searching?"
    terms = (ch.get("stats") or {}).get("search") or []
    terms = [t for t in terms if t and t[0] and t[0].lower() not in ("shorts", "short")]
    if not terms:
        return _check("search", q, "unknown", "No views from YouTube search yet.")
    return _check("search", q, "info", "People found it by searching: " + ", ".join(
        f"\"{t[0]}\" ({t[1]})" for t in terms[:3]) + ".", [f"\"{t[0]}\": {t[1]} views" for t in terms[:10]],
                  "These words go into the next titles and tags.")


def clicks(ch, rows):
    q = "Do people click its long videos?"
    seen = [r for r in rows if r.get("ctr") is not None and (r.get("impressions") or 0) >= 100]
    if len(seen) < 2:
        err = (ch.get("stats") or {}).get("reach_error")
        return _check("clicks", q, "unknown", "YouTube's click-rate report has no numbers for its videos yet"
                      + (f" ({err[:80]})." if err else " (it starts 2-3 days after a video goes up)."))
    c = _median([r["ctr"] for r in seen])
    finding = f"{_fmt(c)}% of the people shown a thumbnail click it (median of {len(seen)} videos)."
    if c >= 5:
        return _check("clicks", q, "good", finding)
    return _check("clicks", q, "problem" if c < 2 else "tip", finding,
                  [f"{(r.get('title') or '')[:60]}: {r['ctr']}% of {r['impressions']:,}" for r in seen[:5]],
                  "The thumbnail test (text left or right) is judged by this click rate.")


def length(ch, tip):
    q = "Is the video length right?"
    if tip:
        return _check("length", q, "tip", tip["text"], [], "Change the minutes on the card.")
    return _check("length", q, "unknown" if not ((ch.get("stats") or {}).get("formats")) else "good",
                  "Not enough watched long videos to say yet." if not ((ch.get("stats") or {}).get("formats"))
                  else "People watch a normal share of each video for its length.")


def verified(ch, cap_minutes):
    q = "Can it upload long videos?"
    st = (ch.get("long_uploads") or {}).get("status")
    if st in ("eligible", "disallowed"):
        return _check("verified", q, "problem", f"YouTube has not phone-verified this channel, so its videos stop at "
                      f"{cap_minutes} minutes (the card asks for {ch.get('minutes')}).", [],
                      "Verify the channel at youtube.com/verify (a code by SMS); the next video is longer by itself.")
    if st == "allowed":
        return _check("verified", q, "good", "Verified: long videos of any length go up.")
    return _check("verified", q, "unknown", "Not asked yet (YouTube is asked every 6 hours).")


def connection(yt):
    q = "Is it connected to its YouTube channel?"
    if not (yt or {}).get("connected"):
        return _check("connection", q, "problem", "Not connected: it makes nothing until it is.", [],
                      "Press connect on the card (or use the channel of a card you no longer need).")
    return None


def run(ch, rows, research=None, yt=None, now=None):
    """Every check for one card, problems first; [] for the main channel."""
    import my_channels as mc
    import teardown
    if not ch or ch.get("id") == "main":
        return []
    now = now or time.time()
    kind = mc.KINDS.get(ch.get("kind"), {})
    long = bool(kind.get("long"))
    started = (ch.get("took_over") or {}).get("at") or ch.get("created")
    out = [connection(yt) if yt is not None else None,
           posting(ch, rows, now, mc.EXTRA_FORMATS, started),
           reach(rows, now, mc.EXTRA_FORMATS),
           staying(ch, rows, long),
           formats(ch, mc.format_score),
           timing(ch, mc.time_tip(ch)) if not long else None,
           tests(ch, mc.EXPERIMENTS, mc.ab_winner, mc.AB_MIN),
           niche(research, teardown.compare, teardown.winners, (teardown.MIN_THEIRS, teardown.MIN_OURS)),
           search(ch)]
    if long:
        out += [clicks(ch, rows), length(ch, mc.length_tip(ch)), verified(ch, mc.UNVERIFIED_MINUTES)]
    out = [c for c in out if c]
    return sorted(out, key=lambda c: STATUS_ORDER.get(c["status"], 9))
