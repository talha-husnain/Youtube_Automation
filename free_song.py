"""Free songs when Lyria cannot sing (owner, 7-nov-2026: "find any free opensource for it").

ACE-Step 1.5 (MIT licence, code and weights; songs may be used commercially) runs on this PC's
CPU through its own small web API in D:\\Shortkaar\\tools\\ACE-Step-1.5. Nothing starts it at
boot: the first song that needs it starts the API in the background (models load on its first
request, a few minutes), and it then stays up for the next songs.

Env: ACESTEP=0 turns it off; ACESTEP_URL (default http://127.0.0.1:8001); ACESTEP_DIR (the
install); ACESTEP_STEPS (default 8, the turbo model's own); ACESTEP_TIMEOUT (seconds a song may
take, default 2400 on the CPU).
"""
import json
import os
import subprocess
import time
import urllib.parse

import httpx

DEFAULT_DIR = r"D:\Shortkaar\tools\ACE-Step-1.5"


def enabled():
    return os.environ.get("ACESTEP", "1") != "0"


def url():
    return (os.environ.get("ACESTEP_URL") or "http://127.0.0.1:8001").rstrip("/")


def home():
    return os.environ.get("ACESTEP_DIR") or DEFAULT_DIR


def _int_env(name, default):
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


def _exe():
    return os.path.join(home(), ".venv-cpu", "Scripts", "acestep-api.exe")


def installed():
    return os.path.isfile(_exe())


def up(timeout=5):
    try:
        return httpx.get(url() + "/health", timeout=timeout).status_code == 200
    except Exception:  # noqa: BLE001 — not running
        return False


def _child_env():
    """The API needs no Shortkaar secret: keys and tokens stay out of its environment."""
    port = urllib.parse.urlparse(url()).port or 8001
    env = {k: v for k, v in os.environ.items()
           if not any(s in k.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
    env.update(ACESTEP_DEVICE="cpu", ACESTEP_INIT_LLM="false", ACESTEP_API_HOST="127.0.0.1",
               ACESTEP_API_PORT=str(port), ACESTEP_OFFLOAD_TO_CPU="false", PYTHONIOENCODING="utf-8")
    return env


def start(wait=240, log=print):
    """Start the API in the background if it is not up; True once it answers."""
    if up():
        return True
    if not installed():
        return False
    log("   🎛️ Starting the free song maker (ACE-Step) on this PC...")
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    logfile = open(os.path.join(os.path.dirname(home()), "acestep_api.log"), "ab")  # noqa: SIM115 — the child keeps it
    subprocess.Popen([_exe()], cwd=home(), env=_child_env(), stdin=subprocess.DEVNULL, stdout=logfile,
                     stderr=subprocess.STDOUT, creationflags=flags, close_fds=True)
    end = time.time() + wait
    while time.time() < end:
        time.sleep(5)
        if up():
            return True
    return False


def busy():
    """Songs queued or being made right now (the API cannot cancel one), or 0 when unknown."""
    try:
        jobs = (httpx.get(url() + "/v1/stats", timeout=10).json().get("data") or {}).get("jobs") or {}
        return int(jobs.get("queued") or 0) + int(jobs.get("running") or 0)
    except Exception:  # noqa: BLE001
        return 0


def _wait_turn(log):
    """Wait while older songs are made, so ours starts at once and its time limit is fair. The first ever
    song also waited ~2 h for the 8 GB model download (7-nov-2026): jobs that gave up then left songs queued."""
    end = time.time() + _int_env("ACESTEP_QUEUE_WAIT", 3600)
    said = False
    while busy() and time.time() < end:
        if not said:
            log(f"   ⏳ The free song maker is busy with {busy()} older song(s); waiting for its turn...")
            said = True
        time.sleep(20)


def lyrics_text(sections):
    """[("Verse", [lines]), ...] -> ACE-Step's tagged lyrics."""
    out = []
    for tag, lines in sections:
        if lines:
            out += [f"[{tag}]", *lines, ""]
    return "\n".join(out).strip() or "[Instrumental]"


def make(style, lyrics, out_path, seconds=50, log=print):
    """One song (or instrumental, lyrics "[Instrumental]") as mp3 at ``out_path``; returns the path."""
    if not enabled():
        raise RuntimeError("The free song maker is off (ACESTEP=0).")
    if not start(log=log):
        raise RuntimeError("The free song maker (ACE-Step) is not installed or did not start; "
                           f"see {os.path.join(os.path.dirname(home()), 'acestep_api.log')}.")
    _wait_turn(log)
    t0 = time.time()
    r = httpx.post(url() + "/release_task", json={
        "prompt": style[:500], "lyrics": lyrics, "vocal_language": "en", "audio_duration": int(seconds),
        "thinking": False, "inference_steps": _int_env("ACESTEP_STEPS", 8), "batch_size": 1,
        "audio_format": "mp3"}, timeout=60)
    r.raise_for_status()
    task = (r.json().get("data") or {}).get("task_id")
    if not task:
        raise RuntimeError(f"ACE-Step took no task: {r.text[:200]}")
    limit = _int_env("ACESTEP_TIMEOUT", 2400)
    while True:
        time.sleep(10)
        q = httpx.post(url() + "/query_result", json={"task_id_list": [task]}, timeout=60).json()
        row = (q.get("data") or [{}])[0]
        if row.get("status") == 1:
            break
        if row.get("status") == 2:
            raise RuntimeError(f"ACE-Step could not make it: {str(row.get('result') or row)[:200]}")
        if time.time() - t0 > limit:
            raise RuntimeError(f"ACE-Step took over {limit // 60} min; giving up on this one.")
    res = json.loads(row["result"])[0] if isinstance(row.get("result"), str) else row["result"][0]
    path = res["file"] if res["file"].startswith("/") else "/" + res["file"]
    audio = httpx.get(url() + path, timeout=300)
    audio.raise_for_status()
    if len(audio.content) < 10_000:
        raise RuntimeError("ACE-Step returned an empty song.")
    with open(out_path, "wb") as f:
        f.write(audio.content)
    log(f"   ✅ Made free by ACE-Step in {(time.time() - t0) / 60:.1f} min.")
    return out_path
