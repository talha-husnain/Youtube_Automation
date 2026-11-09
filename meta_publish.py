"""Cross-posting our channels' Shorts to the owner's own Facebook Pages (as Reels) and Instagram
professional accounts (as Reels), through Meta's Graph API (owner, 22-oct-2026: "we can post on
Facebook and Instagram as well").

What the docs say (Graph API v26.0, researched 22-oct-2026):
- Facebook Login for Business with pages_show_list, pages_read_engagement, pages_manage_posts,
  instagram_basic, instagram_content_publish. An app in Development mode may ask these of people who
  have a role on the app, so the owner's own app needs no App Review for his own Pages.
- A long-lived user token (~60 days) gives Page tokens that do not expire; the Page token also drives
  the Instagram account linked to that Page.
- Instagram's resumable upload (a LOCAL file, no public URL: this laptop has none) exists only for
  Facebook Login for Business apps; Instagram Login needs a public video_url.
- Facebook Page Reels: 3-90 s, 9:16, 30 API posts a day; Instagram: 3 s-15 min, 50 a day (the doc says
  50 and 100 in two places). We keep DAILY_MAX far below both.
- is_ai_generated exists on both calls: every post sets it (our voices, songs and pictures are AI).
- Redirect: Meta wants HTTPS; http://localhost is allowed while the app is in Development (a 2018
  Meta note, not re-confirmed): META_REDIRECT overrides it.

Nothing is queued until the owner connects: a Short uploaded to YouTube is copied to
state/meta/outbox/ and posted at its YouTube publish time (``post_pass``), then the copy goes.
Tokens live in state/meta/token.json (gitignored) and never appear in a log line or an error.
"""
import json
import os
import secrets
import shutil
import subprocess
import threading
import time
import urllib.parse

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(ROOT, "state", "meta")
TOKEN_FILE = os.path.join(STATE_DIR, "token.json")
QUEUE_FILE = os.path.join(STATE_DIR, "queue.json")
OUTBOX = os.path.join(STATE_DIR, "outbox")
VERSION = "v26.0"
GRAPH = f"https://graph.facebook.com/{VERSION}"
RUPLOAD = "https://rupload.facebook.com"
DIALOG = f"https://www.facebook.com/{VERSION}/dialog/oauth"
SCOPES = "pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish"
FB_MAX_SECONDS = 90
# A vertical LONG video (the cartoon channel's weekly compilation, toon_mix.py) is not a Reel: YouTube only.
REEL_MAX_SECONDS = 180
DAILY_MAX = int(os.environ.get("META_DAILY_MAX") or 8)     # per account per platform; Meta allows 30 / 50
TRIES = 3
CAPTION_MAX = 2200
HASHTAGS_MAX = 5
POLL = 10
WAIT = 10 * 60
# Few Instagram accounts (owner, 5-nov-2026: new accounts need an email and verification "and sometimes they
# just blocked your account"). A fresh account that suddenly posts many Reels through an API looks like a bot,
# so each account starts slow: IG_RAMP Reels a day for its first weeks of our posting, then IG_DAILY. One
# account shared by several channels (my_channels.meta_ig_mode) takes only the Shorts that already won on
# YouTube: judged WIN_AFTER after their YouTube time, given up at WIN_UNTIL, the best first.
IG_RAMP = ((7, 1), (14, 2))        # (days since our first Reel on the account, Reels a day before then)
IG_DAILY = int(os.environ.get("META_IG_DAILY") or 3)
WIN_AFTER = 24 * 3600
WIN_UNTIL = 72 * 3600
WIN_RATIO = 1.5                    # views at least this times the channel's median...
WIN_MIN_VIEWS = 20                 # ...and never fewer than this
_lock = threading.RLock()
_states = {}


def redirect_uri():
    return os.environ.get("META_REDIRECT") or "http://localhost:8000/api/meta/callback"


def configured():
    return bool(os.environ.get("META_APP_ID") and os.environ.get("META_APP_SECRET"))


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _token():
    return _read(TOKEN_FILE, None)


def status():
    tok = _token() or {}
    return {"configured": configured(), "connected": bool(tok.get("pages")),
            "config_id": bool(os.environ.get("META_CONFIG_ID", "").strip()),
            "app_id": os.environ.get("META_APP_ID", "") if configured() else "",
            "user_expires": tok.get("user_expires"),
            "connected_at": tok.get("connected_at"), "user": tok.get("user_name"),
            "pages": [{"id": p["id"], "name": p.get("name"), "instagram": p.get("ig_username"),
                       **({"ig_per_day": ig_cap(p["id"]), "ig_full_on": ig_full_on(p["id"])}
                          if p.get("ig_username") else {})}
                      for p in tok.get("pages") or []]}


def page(pid):
    return next((p for p in (_token() or {}).get("pages") or [] if p["id"] == pid), None)


# ------------------------------------------------------------------ connect

def auth_url(back=""):
    """Facebook's sign-in page. A Business app's "Facebook Login for Business" takes a configuration
    (META_CONFIG_ID, its permissions chosen there) in place of ``scope`` (Meta's docs, checked 5-nov-2026);
    without one the permissions are asked by name as before."""
    if not configured():
        raise RuntimeError("Paste the Meta app's App ID and App Secret in Shortkaar first (Channels tab).")
    state = secrets.token_urlsafe(24)
    now = time.time()
    with _lock:
        for k in [k for k, v in _states.items() if now - v[0] > 900]:
            _states.pop(k, None)
        _states[state] = (now, back)
    ask = ({"config_id": os.environ["META_CONFIG_ID"]} if os.environ.get("META_CONFIG_ID", "").strip()
           else {"scope": SCOPES})
    return DIALOG + "?" + urllib.parse.urlencode({
        "client_id": os.environ["META_APP_ID"], "redirect_uri": redirect_uri(), "state": state,
        **ask, "response_type": "code"})


# ------------------------------------------------------------------ the keys, from the dashboard

ENV_FILE = os.path.join(ROOT, ".env")
_REAL_ENV_FILE = ENV_FILE


def write_env(values, path=None):
    """Set KEY=value lines in .env (replaced where they are, else added at the end), atomically."""
    path = path or ENV_FILE
    if path == _REAL_ENV_FILE and os.environ.get("PYTEST_CURRENT_TEST"):
        raise RuntimeError("a test tried to write the real .env")
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    left = dict(values)
    for k, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in left:
            lines[k] = f"{key}={left.pop(key)}"
    lines += [f"{key}={v}" for key, v in left.items()]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, path)


def save_keys(app_id, app_secret, config_id="", http=httpx, env_file=None):
    """The owner pastes the Meta app's keys in the dashboard: no Notepad, no restart (owner, 5-nov-2026:
    "I just have to add key"). Checked with Meta first (an app token from the two), then written to .env and
    this process. Raises ValueError with what to fix; never says the secret back."""
    import re
    app_id, app_secret, config_id = (re.sub(r"\s+", "", str(x or "")) for x in (app_id, app_secret, config_id))
    if not re.fullmatch(r"\d{6,20}", app_id):
        raise ValueError("The App ID is the long number at the top of your app's page (App settings > Basic).")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", app_secret):
        raise ValueError("The App Secret is 32 letters and digits (App settings > Basic > App secret > Show).")
    if config_id and not re.fullmatch(r"\d{6,20}", config_id):
        raise ValueError("The Configuration ID is a long number (Facebook Login for Business > Configurations).")
    r = http.get(f"{GRAPH}/oauth/access_token", params={"client_id": app_id, "client_secret": app_secret,
                                                         "grant_type": "client_credentials"}, timeout=30)
    if r.status_code != 200:
        raise ValueError("Meta did not accept this App ID and App Secret together; copy both again. " + _err(r))
    values = {"META_APP_ID": app_id, "META_APP_SECRET": app_secret}
    if config_id:
        values["META_CONFIG_ID"] = config_id
    write_env(values, env_file)
    os.environ.update(values)
    return status()


REDIRECT_HOSTS = ("localhost", "127.0.0.1")


def use_redirect_host(host, env_file=None):
    """Switch the sign-in return address between localhost and 127.0.0.1 (Facebook refuses localhost for some
    apps, community reports): one click in the dashboard instead of a line in .env. The address now used."""
    if host not in REDIRECT_HOSTS:
        raise ValueError("Use localhost or 127.0.0.1.")
    url = f"http://{host}:8000/api/meta/callback"
    write_env({"META_REDIRECT": url}, env_file)
    os.environ["META_REDIRECT"] = url
    return url


PAGE_FIELDS = ("id,name,access_token,instagram_business_account{id,username},"
               "connected_instagram_account{id,username}")


def _extra_file():
    return os.path.join(STATE_DIR, "extra_pages.json")


def _pages(user_id, user_token, http):
    """The Pages the sign-in may post to. /accounts leaves out a Page that sits in a business portfolio
    (7-nov-2026: Billo aur Gang, once its Instagram was linked through Business Suite), though the sign-in
    still reaches it by id; such Pages are listed by id in state/meta/extra_pages.json and read one by one."""
    got = _json(http.get(f"{GRAPH}/{user_id}/accounts", params={
        "fields": PAGE_FIELDS, "access_token": user_token, "limit": 100}, timeout=30))
    pages = [_page_row(p) for p in got.get("data") or []]
    seen = {p["id"] for p in pages}
    for pid in _read(_extra_file(), []):
        pid = str(pid)
        if pid in seen:
            continue
        r = http.get(f"{GRAPH}/{pid}", params={"fields": PAGE_FIELDS, "access_token": user_token}, timeout=30)
        if r.status_code == 200 and (r.json() or {}).get("access_token"):
            pages.append(_page_row(r.json()))
            seen.add(pid)
    return pages


def refresh_pages(http=httpx):
    """Read the Pages and their linked Instagram accounts again with the saved sign-in (an Instagram linked
    after connecting shows up without signing in again). The status."""
    tok = _token() or {}
    if not tok.get("user_token"):
        raise RuntimeError("Connect Facebook first.")
    tok["pages"] = _pages(tok["user_id"], tok["user_token"], http) or tok.get("pages") or []
    _write(TOKEN_FILE, tok)
    return status()


def _page_row(p):
    # An Instagram linked through Business Suite comes back as connected_instagram_account only (7-nov-2026,
    # @talkingcartons); the same id takes Reels (its content_publishing_limit answers with the Page token).
    ig = p.get("instagram_business_account") or p.get("connected_instagram_account") or {}
    return {"id": p["id"], "name": p.get("name"), "access_token": p["access_token"],
            "ig_id": ig.get("id"), "ig_username": ig.get("username")}


def check(http=httpx):
    """Each Page's token, and whether its Instagram may publish (content_publishing_limit), posting
    nothing: [{"id", "name", "facebook": "ok" | Meta's reason, "instagram": "ok" | reason | None}]."""
    out = []
    for p in (_token() or {}).get("pages") or []:
        row = {"id": p["id"], "name": p.get("name"), "facebook": "ok", "instagram": None,
               "username": p.get("ig_username")}
        r = http.get(f"{GRAPH}/{p['id']}", params={"fields": "name", "access_token": p["access_token"]}, timeout=30)
        if r.status_code != 200:
            row["facebook"] = _err(r)
        if p.get("ig_id"):
            r = http.get(f"{GRAPH}/{p['ig_id']}/content_publishing_limit",
                         params={"fields": "quota_usage", "access_token": p["access_token"]}, timeout=30)
            row["instagram"] = "ok" if r.status_code == 200 else _err(r)
        out.append(row)
    return out


def back_for(state):
    with _lock:
        got = _states.get(state)
    return got[1] if got else ""


def _err(r):
    """Meta's own message for a failed call; never the URL (it can carry a token)."""
    # Instagram's own reason is in the codes and error_user_msg: a bare "Fatal" (code -1, subcode 2207001 is its
    # anti-spam) or "{}" (rupload answers with debug_info, not error) told nothing on 7/8-nov-2026.
    try:
        body = r.json()
    except ValueError:
        return f"Meta said {r.status_code}"
    e = body.get("error") or body.get("debug_info") or {}
    if not isinstance(e, dict):
        return f"Meta said {r.status_code}: {str(e)[:250]}"
    codes = "/".join(str(e[k]) for k in ("code", "error_subcode") if e.get(k) is not None)
    user = e.get("error_user_msg") or e.get("error_user_title") or ""
    kind = e.get("type") if e.get("type") not in (None, "OAuthException") else ""
    text = " ".join(x for x in (e.get("message") or "", kind, f"({codes})" if codes else "", user) if x)
    return f"Meta said {r.status_code}: {text or body}"[:300]


def _json(r):
    if r.status_code != 200:
        raise RuntimeError(_err(r))
    return r.json()


def finish_connect(code, state, http=httpx):
    with _lock:
        if state not in _states:
            raise RuntimeError("This sign-in link is old; start again from the dashboard.")
        _states.pop(state, None)
    app = {"client_id": os.environ["META_APP_ID"], "client_secret": os.environ["META_APP_SECRET"]}
    short = _json(http.get(f"{GRAPH}/oauth/access_token", params={**app, "redirect_uri": redirect_uri(),
                                                                 "code": code}, timeout=30))["access_token"]
    long = _json(http.get(f"{GRAPH}/oauth/access_token", params={
        **app, "grant_type": "fb_exchange_token", "fb_exchange_token": short}, timeout=30))
    user_token = long["access_token"]
    me = _json(http.get(f"{GRAPH}/me", params={"fields": "id,name", "access_token": user_token}, timeout=30))
    pages = _pages(me["id"], user_token, http)
    if not pages:
        raise RuntimeError("Facebook gave no Pages. Create a Page (and link Instagram to it), then connect again.")
    _write(TOKEN_FILE, {"user_id": me["id"], "user_name": me.get("name"), "user_token": user_token,
                        "user_expires": int(time.time()) + int(long.get("expires_in") or 60 * 86400),
                        "pages": pages, "connected_at": int(time.time())})
    return status()


def disconnect():
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)


# ------------------------------------------------------------------ queue

def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", path],
                         capture_output=True, text=True, timeout=60).stdout
    d = json.loads(out or "{}")
    s = (d.get("streams") or [{}])[0]
    return int(s.get("width") or 0), int(s.get("height") or 0), float((d.get("format") or {}).get("duration") or 0)


# One line asking viewers to SEND the Reel (5-nov-2026: sends per reach and watch time are the signals Instagram
# names first; likes count least). Per kind, the same line for the same video; kinds without one get none.
SHARE_LINES = {
    "toons": ["Yeh us dost ko bhejo jo bilkul Sheru jaisa hai 😂", "Apne ghar ke Billo ko yeh zaroor bhejo 😹",
              "Jis ke ghar mein bhi aisa Guddu hai, usay bhejo 👶😂"],
    "quiz": ["Yeh quiz us dost ko bhejo jo khud ko sab se smart samajhta hai 🧠"],
    "cricket": ["Yeh us dost ko bhejo jis se cricket par bahas hoti hai 🏏"],
    "money": ["Yeh us dost ko bhejo jo har mahine poochta hai paise kahan gaye 💸"],
}


def share_line(kind, key=""):
    lines = SHARE_LINES.get(kind or "") or []
    if not lines:
        return ""
    import zlib
    return lines[zlib.crc32(str(key).encode()) % len(lines)]


def caption_for(title, description, kind=None, key=""):
    """Title, the description's first paragraph, a send-it line for the kind (SHARE_LINES), a few hashtags:
    YouTube's links and follow lines do not belong on Facebook or Instagram."""
    paras = [p.strip() for p in (description or "").split("\n\n") if p.strip()]
    body = next((p for p in paras if "http" not in p and not p.startswith("#")), "")
    tags = []
    for p in paras:
        for w in p.split():
            if w.startswith("#") and len(w) > 2 and w.lower() not in {t.lower() for t in tags} \
                    and w.lower() != "#shorts":
                tags.append(w)
    text = "\n\n".join(x for x in (title.strip(), body[:600], share_line(kind, key or title),
                                    " ".join(tags[:HASHTAGS_MAX])) if x)
    return text[:CAPTION_MAX]


def targets(ch):
    """(Facebook Page or None, Page whose Instagram it posts to or None) for a channel card, or None.
    Facebook links one Instagram to one Page and one Page to one Instagram, so a channel without its own
    Instagram (few accounts, 5-nov-2026) posts its Reels through another Page's: ``meta_ig_page``."""
    ch = ch or {}
    fb = page(ch["meta_page"]) if ch.get("meta_page") else None
    ig = page(ch.get("meta_ig_page") or ch.get("meta_page") or "") if ch.get("meta_ig", True) else None
    fb = fb if fb and ch.get("meta_fb", True) else None
    ig = ig if ig and ig.get("ig_id") else None
    return (fb, ig) if fb or ig else None


def enqueue(ch, row, path, publish_at=None, ai=True, ig_wait=False):
    """Queue an uploaded Short for the channel's Page and Instagram. None when nothing is set up, the
    file is gone, or it is not a vertical Short (long videos stay on YouTube). ``ig_wait``: Instagram
    takes it only if it wins on YouTube first (a shared account, see IG_RAMP)."""
    t = targets(ch)
    if not t or not path or not os.path.isfile(path):
        return None
    w, h, secs = _probe(path)
    if not (h > w and 3 <= secs <= REEL_MAX_SECONDS):
        return None
    fbp, igp = t
    fb, ig = bool(fbp), bool(igp)
    qid = f"{ch['id']}_{row.get('video_id') or row.get('id') or int(time.time())}"
    os.makedirs(OUTBOX, exist_ok=True)
    dst = os.path.join(OUTBOX, f"{qid}.mp4")
    shutil.copyfile(path, dst)
    at = int(publish_at.timestamp()) if hasattr(publish_at, "timestamp") else int(publish_at or time.time())
    item = {"id": qid, "channel": ch["id"], "page": (fbp or igp)["id"], "ig_page": igp["id"] if igp else "",
            "file": dst, "seconds": round(secs, 2),
            "video_id": row.get("video_id") or row.get("id") or "",
            "caption": caption_for(row.get("title") or "", row.get("description") or "", ch.get("kind"),
                                   row.get("video_id") or ""), "at": at, "ai": ai,
            "created": int(time.time()),
            "fb": {"status": "pending" if fb and secs <= FB_MAX_SECONDS else ("skipped" if fb else "off")},
            "ig": {"status": "pending", "wait": "winner"} if ig and ig_wait else {"status": "pending" if ig else "off"}}
    with _lock:
        q = _read(QUEUE_FILE, [])
        q = [x for x in q if x["id"] != qid] + [item]
        _write(QUEUE_FILE, q)
    return item


def queue():
    return _read(QUEUE_FILE, [])


def _page_of(item, platform):
    """The Page an item posts through on ``platform`` (Instagram goes through ``ig_page``)."""
    return (item.get("ig_page") or item["page"]) if platform == "ig" else item["page"]


def _posted_today(q, page_id, platform, now):
    return sum(1 for x in q if _page_of(x, platform) == page_id and x[platform].get("status") == "posted"
               and now - x[platform].get("at", 0) < 86400)


def _accounts_file():
    return os.path.join(STATE_DIR, "accounts.json")      # beside the queue (a test's STATE_DIR covers it)


def ig_cap(page_id, now=None):
    """Reels a day the Instagram account of ``page_id`` may post now: IG_RAMP from our first Reel on it."""
    now = now or time.time()
    first = (_read(_accounts_file(), {}).get(page_id) or {}).get("ig_first")
    days = (now - first) / 86400 if first else 0
    for until, n in IG_RAMP:
        if days < until:
            return min(n, IG_DAILY, DAILY_MAX)
    return min(IG_DAILY, DAILY_MAX)


def ig_full_on(page_id):
    """When the account of ``page_id`` reaches IG_DAILY, or None before its first Reel."""
    first = (_read(_accounts_file(), {}).get(page_id) or {}).get("ig_first")
    return int(first + IG_RAMP[-1][0] * 86400) if first and IG_RAMP else (int(first) if first else None)


def _first_reel(page_id, now):
    with _lock:
        acc = _read(_accounts_file(), {})
        if not (acc.get(page_id) or {}).get("ig_first"):
            acc.setdefault(page_id, {})["ig_first"] = int(now)
            _write(_accounts_file(), acc)


def _ig_ready(item, now, score, log):
    """True when Instagram may take the item now. A Short waiting to win (``wait``) is judged on its YouTube
    numbers, ``score(item)`` -> (views, channel median) or None, between WIN_AFTER and WIN_UNTIL."""
    st = item["ig"]
    if st.get("wait") != "winner" or score is None:
        return True
    if now < item["at"] + WIN_AFTER:
        return False
    got = score(item)
    if got and got[0] is not None and got[0] >= max(WIN_MIN_VIEWS, WIN_RATIO * (got[1] or 0)):
        st["ratio"] = round(got[0] / max(got[1] or 0, 1), 2)
        return True
    if now >= item["at"] + WIN_UNTIL:
        st.update(status="skipped", why=(f"{got[0]} views on YouTube, its channel's median {got[1]}" if got
                                         else "no YouTube numbers"))
        log(f"ℹ️ Instagram: '{item['caption'][:40]}' did not win on YouTube, so it stays off Instagram.")
    return False


def post_pass(log=print, now=None, http=httpx, sleep=time.sleep, score=None):
    """Post every queued Short whose YouTube time has come. Returns how many went out. Instagram keeps to
    each account's ig_cap, the Shorts that won most on YouTube first (``score``, see _ig_ready)."""
    now = now or time.time()
    with _lock:
        q = _read(QUEUE_FILE, [])
    sent = 0
    for platform, fn in (("fb", post_facebook), ("ig", post_instagram)):
        items = [x for x in q if x["at"] <= now and x[platform].get("status") == "pending"]
        if platform == "ig":
            items = sorted((x for x in items if _ig_ready(x, now, score, log)),
                           key=lambda x: -(x["ig"].get("ratio") or 0))
        for item in items:
            pid = _page_of(item, platform)
            st, p = item[platform], page(pid)
            cap = DAILY_MAX if platform == "fb" else ig_cap(pid, now)
            if not p or _posted_today(q, pid, platform, now) >= cap:
                continue
            try:
                got = fn(p, item["file"], item["caption"], item.get("ai", True), http=http, sleep=sleep)
                st.update(status="posted", id=got, at=int(now))
                sent += 1
                if platform == "ig":
                    _first_reel(pid, now)
                log(f"📤 {'Facebook' if platform == 'fb' else 'Instagram'}: posted '{item['caption'][:50]}'.")
            except Exception as e:  # noqa: BLE001 — tried again on the next pass, TRIES times
                st["tries"] = st.get("tries", 0) + 1
                st["error"] = str(e)[:200]
                if st["tries"] >= TRIES:
                    st["status"] = "failed"
                log(f"⚠️ {'Facebook' if platform == 'fb' else 'Instagram'}: {str(e)[:120]}")
    keep = []
    for item in q:
        if all(item[k].get("status") in ("posted", "failed", "skipped", "off") for k in ("fb", "ig")):
            if os.path.exists(item["file"]):
                os.remove(item["file"])
            item.setdefault("done", int(now))       # set once: rewritten each pass, nothing ever left the queue
        if not item.get("done") or now - item["done"] < 30 * 86400:   # a month of history for the dashboard
            keep.append(item)
    with _lock:
        # A Short queued while this pass was posting (minutes of uploads) is in the file, not in ``q``.
        mine = {x["id"] for x in q}
        keep += [x for x in _read(QUEUE_FILE, []) if x["id"] not in mine]
        _write(QUEUE_FILE, keep)
    return sent


# ------------------------------------------------------------------ posting

def _upload(url, token, path, http):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        r = http.post(url, headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size),
                                    "Content-Type": "application/octet-stream"}, content=f.read(), timeout=600)
    got = _json(r)
    if got.get("success") is False:
        raise RuntimeError("Meta refused the upload: " + str(got.get("debug_info") or got)[:200])


def post_facebook(p, path, caption, ai=True, http=httpx, sleep=time.sleep):
    """A Page Reel, published at once. Returns the video id."""
    tok = p["access_token"]
    start = _json(http.post(f"{GRAPH}/{p['id']}/video_reels", data={"upload_phase": "start", "access_token": tok},
                            timeout=60))
    vid = start["video_id"]
    _upload(f"{RUPLOAD}/video-upload/{VERSION}/{vid}", tok, path, http)
    waited = 0
    while True:
        st = _json(http.get(f"{GRAPH}/{vid}", params={"fields": "status", "access_token": tok}, timeout=60))
        phase = (st.get("status") or {}).get("video_status")
        if phase in ("upload_complete", "processing", "ready"):
            break
        if phase in ("upload_failed", "expired", "error"):
            raise RuntimeError(f"Facebook could not take the video ({phase}).")
        if waited >= WAIT:
            raise RuntimeError("Facebook took too long to receive the video.")
        sleep(POLL)
        waited += POLL
    _json(http.post(f"{GRAPH}/{p['id']}/video_reels", data={
        "upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED", "description": caption,
        "is_ai_generated": "true" if ai else "false", "access_token": tok}, timeout=60))
    return vid


def post_instagram(p, path, caption, ai=True, http=httpx, sleep=time.sleep):
    """An Instagram Reel from the local file (resumable upload). Returns the media id."""
    if not p.get("ig_id"):
        raise RuntimeError("No Instagram account is linked to this Page.")
    tok = p["access_token"]
    try:
        box = _json(http.post(f"{GRAPH}/{p['ig_id']}/media", data={
            "media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true",
            "is_ai_generated": "true" if ai else "false", "access_token": tok}, timeout=60))
    except RuntimeError as e:
        raise RuntimeError(f"creating the Reel: {e}") from e
    try:
        _upload(box.get("uri") or f"{RUPLOAD}/ig-api-upload/{VERSION}/{box['id']}", tok, path, http)
    except RuntimeError as e:
        raise RuntimeError(f"uploading the video: {e}") from e
    waited = 0
    while True:
        st = _json(http.get(f"{GRAPH}/{box['id']}", params={"fields": "status_code,status", "access_token": tok},
                            timeout=60))
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram could not process the video ({st.get('status') or code}).")
        if waited >= WAIT:
            raise RuntimeError("Instagram took too long to process the video.")
        sleep(POLL * 3)
        waited += POLL * 3
    try:
        done = _json(http.post(f"{GRAPH}/{p['ig_id']}/media_publish", data={"creation_id": box["id"],
                                                                         "access_token": tok}, timeout=60))
    except RuntimeError as e:
        raise RuntimeError(f"publishing: {e}") from e
    return done.get("id")
