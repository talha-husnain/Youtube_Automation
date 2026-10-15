"""Shorts to the owner's phone through their own Telegram bot.

Posting happens on the phone, the Shorts are made on the laptop. A Telegram
bot (free, made in 2 minutes with @BotFather) carries each Short with its
posting time and title as the caption, then its description and pinned
comment as a message to copy. Nothing leaves for anyone else: the bot only
talks to the chat that sent it a message first.

``TELEGRAM_BOT_TOKEN`` lives in .env (a credential, never in the repo); the
chat id is found with getUpdates after the owner says "hi" to the bot and is
kept in ``output/.telegram.json``. Bots may send files up to 50 MB.
"""
import json
import os
import time

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "output", ".telegram.json")
API = "https://api.telegram.org/bot{token}/{method}"
CAPTION_MAX, TEXT_MAX, FILE_MAX = 1000, 4000, 49 * 1024 * 1024


def _token():
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def _load():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


def status():
    st = _load()
    return {"configured": bool(_token()), "connected": bool(_token() and st.get("chat_id")),
            "name": st.get("name")}


def _call(method, timeout=30, **kw):
    r = httpx.post(API.format(token=_token(), method=method), timeout=timeout, **kw)
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code != 200 or not body.get("ok"):
        # The token is in the URL: never echo the request, only Telegram's reason.
        raise RuntimeError(f"Telegram said: {body.get('description') or r.status_code}")
    return body.get("result")


def connect():
    """Find the chat that wrote to the bot and remember it."""
    if not _token():
        raise RuntimeError("Add TELEGRAM_BOT_TOKEN to .env and restart Shortkaar first.")
    # allowed_updates is remembered by Telegram: poll() asks for button
    # presses too, so both name the same list.
    updates = _call("getUpdates", timeout=20, data={"allowed_updates": UPDATES}) or []
    chats = [u.get("message", {}).get("chat") for u in updates if u.get("message")]
    chats = [c for c in chats if c and c.get("type") == "private"]
    if not chats:
        raise RuntimeError("Open your bot in Telegram, send it any message (like hi), then press Connect again.")
    chat = chats[-1]
    name = chat.get("first_name") or chat.get("username") or "you"
    _save({"chat_id": chat["id"], "name": name, "at": int(time.time())})
    send_text(f"Shortkaar is connected. Your Shorts will arrive here, {name}.")
    return status()


def disconnect():
    try:
        os.remove(STATE_FILE)
    except OSError:
        pass


def _chat():
    chat = _load().get("chat_id")
    if not chat or not _token():
        raise RuntimeError("Telegram is not connected.")
    return chat


def send_text(text, buttons=None):
    """``buttons``: [(label, data)] shown under the message; a press comes
    back through poll()."""
    data = {"chat_id": _chat(), "text": text[:TEXT_MAX], "disable_web_page_preview": "true"}
    if buttons:
        data["reply_markup"] = json.dumps({"inline_keyboard": [[{"text": t, "callback_data": d[:64]}
                                                                for t, d in buttons]]})
    return _call("sendMessage", data=data)


UPDATES = json.dumps(["message", "callback_query"])


def poll(handle):
    """Button presses since the last poll: ``handle(data)`` -> the answer
    shown to the owner. Presses from any other chat are ignored. Returns how
    many were handled."""
    st = _load()
    chat = st.get("chat_id")
    if not chat or not _token():
        return 0
    updates = _call("getUpdates", timeout=15, data={"offset": int(st.get("offset", 0)), "timeout": 0,
                                                     "allowed_updates": UPDATES}) or []
    done = 0
    for u in updates:
        st["offset"] = max(int(st.get("offset", 0)), int(u.get("update_id", 0)) + 1)
        q = u.get("callback_query")
        if not q or (q.get("message") or {}).get("chat", {}).get("id") != chat:
            continue
        try:
            answer = handle(q.get("data") or "")
        except Exception as e:  # noqa: BLE001 — a bad press must not stop the poll
            answer = f"That did not work: {type(e).__name__}"
        try:
            _call("answerCallbackQuery", data={"callback_query_id": q["id"], "text": (answer or "")[:190]})
        except Exception:  # noqa: BLE001 — "query is too old" after a minute: the message below still says it
            pass
        if answer:
            try:
                send_text(answer)
            except Exception:  # noqa: BLE001
                pass
        done += 1
    _save({**_load(), "offset": st.get("offset", 0)})
    return done


def send_short(path, title, description="", pinned="", when="", tiktok=""):
    """The video with its time + title as caption, then the copy to paste."""
    chat = _chat()
    if os.path.getsize(path) > FILE_MAX:
        raise RuntimeError("This Short is over Telegram's 50 MB limit; download it from Shortkaar instead.")
    caption = "\n".join(x for x in [f"Post at: {when}" if when else "", title] if x)[:CAPTION_MAX]
    with open(path, "rb") as f:
        _call("sendVideo", timeout=300, data={"chat_id": chat, "caption": caption, "supports_streaming": "true"},
              files={"video": (os.path.basename(path), f, "video/mp4")})
    parts = [("TITLE", title), ("DESCRIPTION", description), ("PINNED COMMENT", pinned), ("TIKTOK", tiktok)]
    text = "\n\n".join(f"{k}:\n{v}" for k, v in parts if v)
    if text:
        send_text(text)
    return True
