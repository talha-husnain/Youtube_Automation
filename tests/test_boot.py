"""Boot and unattended running (4-nov-2026): autostart.bat's watchdog, the
restart/down/port-taken notices, KEEP_AWAKE=charger, the venv launcher fix."""
import os
import re
import shutil
import subprocess
import sys

import pytest

import keep_awake
import restart_notice

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAT = os.path.join(ROOT, "autostart.bat")


# ---------- keep_awake ----------

def _fresh(monkeypatch, charger=True):
    calls = []
    monkeypatch.setattr(keep_awake, "_set", lambda flags: calls.append(flags) or True)
    monkeypatch.setattr(keep_awake, "_state", {"awake": False, "why": "idle"})
    monkeypatch.setattr(keep_awake, "on_charger", lambda: charger)
    return calls


def test_charger_mode_keeps_the_laptop_awake_between_jobs(monkeypatch):
    calls = _fresh(monkeypatch)
    monkeypatch.setenv("KEEP_AWAKE", "charger")
    st = keep_awake.refresh(False)
    assert st["awake"] is True and "Autopilot" in st["why"]
    assert calls == [keep_awake.ES_CONTINUOUS | keep_awake.ES_SYSTEM_REQUIRED]
    assert keep_awake.refresh(True)["why"].startswith("working")      # a job says so


def test_charger_mode_still_lets_it_sleep_on_battery(monkeypatch):
    _fresh(monkeypatch, charger=False)
    monkeypatch.setenv("KEEP_AWAKE", "charger")
    assert keep_awake.refresh(False)["awake"] is False
    assert keep_awake.refresh(True)["awake"] is False


def test_default_mode_is_unchanged_for_other_installs(monkeypatch):
    _fresh(monkeypatch)
    monkeypatch.delenv("KEEP_AWAKE", raising=False)
    assert keep_awake.refresh(False)["awake"] is False
    assert keep_awake.refresh(True)["awake"] is True


# ---------- restart_notice ----------

LOG = """INFO:     Started server process [100]
INFO:     Application startup complete.
📝 [Job Output] ✅ Clip 1 ready
Traceback (most recent call last):
  File "app.py", line 9, in tick
RuntimeError: the disk said no
INFO:     Shutting down
INFO:     Started server process [200]
INFO:     Waiting for application startup.
ValueError: from the NEW run, must not be reported
"""


def test_last_error_reads_the_run_before_the_newest_start(tmp_path):
    p = tmp_path / "server.log"
    p.write_text(LOG, encoding="utf-8")
    assert restart_notice.last_error(str(p)) == "RuntimeError: the disk said no"
    p.write_text("INFO:     Started server process [1]\nplain line\nINFO:     Started server process [2]\n",
                 encoding="utf-8")
    assert restart_notice.last_error(str(p)) == "plain line"
    assert restart_notice.last_error(str(tmp_path / "missing.log")) == ""


def test_restart_notice_only_when_the_watchdog_started_it_and_once_an_hour(tmp_path, monkeypatch):
    log, state = tmp_path / "server.log", str(tmp_path / "st.json")
    log.write_text(LOG, encoding="utf-8")
    sent = []
    fake = lambda title, text: sent.append((title, text)) or ["toast"]
    monkeypatch.delenv("SHORTKAAR_RESTART", raising=False)
    assert restart_notice.announce_restart(1000.0, str(log), state, fake) is None and not sent
    monkeypatch.setenv("SHORTKAAR_RESTART", "watchdog")
    assert restart_notice.announce_restart(1000.0, str(log), state, fake) == ["toast"]
    assert sent[0][0] == "Shortkaar restarted" and "the disk said no" in sent[0][1]
    assert restart_notice.announce_restart(1000.0 + 600, str(log), state, fake) is None       # quiet hour
    assert restart_notice.announce_restart(1000.0 + 3700, str(log), state, fake) == ["toast"]


def test_down_and_taken_notices(tmp_path):
    state = str(tmp_path / "st.json")
    sent = []
    fake = lambda title, text: sent.append((title, text)) or []
    restart_notice.announce_down(3, 0.0, str(tmp_path / "none.log"), state, fake)
    assert sent[-1][0] == "Shortkaar is down" and "15 minutes" in sent[-1][1]
    restart_notice.announce_taken("com.docker.backend", 8000, 5000.0, state, fake)
    assert sent[-1][0] == "Shortkaar cannot start" and "com.docker.backend" in sent[-1][1] and "Docker" in sent[-1][1]
    restart_notice.announce_taken("<script>&", 8000, 9000.0, state, fake)
    assert "<" not in sent[-1][1] and "&" not in sent[-1][1]


def test_send_never_raises(monkeypatch):
    import notify
    import telegram_notify
    monkeypatch.setattr(notify, "toast", lambda *a, **k: (_ for _ in ()).throw(OSError("no shell")))
    monkeypatch.setattr(telegram_notify, "status", lambda: {"connected": True})
    monkeypatch.setattr(telegram_notify, "send_text", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert restart_notice.send("t", "x") == []


# ---------- heartbeat ----------

def test_heartbeat_is_off_without_a_url(monkeypatch):
    import heartbeat
    monkeypatch.delenv("HEALTHCHECK_URL", raising=False)
    assert heartbeat.ping({"Autopilot": 0}, get=lambda u: 1 / 0, post=lambda u, b: 1 / 0) == "off"
    monkeypatch.setenv("HEALTHCHECK_URL", "not a url")
    assert heartbeat.url() == ""


def test_heartbeat_pings_when_ticking_and_fails_once_when_stuck(monkeypatch):
    import heartbeat
    monkeypatch.setenv("HEALTHCHECK_URL", "https://hc-ping.com/abc")
    monkeypatch.setattr(heartbeat, "_state", {"last_fail": 0.0, "last": None})
    got, posted = [], []
    get, post = got.append, (lambda u, body: posted.append((u, body)))
    now = 10_000_000.0
    assert heartbeat.ping({"Autopilot": now - 60, "Channels": None}, now, get, post) == "ok"   # not ticked yet = fine
    assert got == ["https://hc-ping.com/abc"]
    stuck = {"Autopilot": now - 60, "Channels": now - 50 * 60}
    assert heartbeat.ping(stuck, now, get, post) == "fail"
    assert posted == [("https://hc-ping.com/abc/fail", "Channels has not ticked for 50 min")]
    assert heartbeat.ping(stuck, now + 60, get, post) == "quiet"                                # said it already
    assert heartbeat.ping({"Autopilot": now, "Channels": now}, now + 120, get, post) == "ok"


def test_heartbeat_offline_is_silent(monkeypatch):
    import heartbeat
    monkeypatch.setenv("HEALTHCHECK_URL", "https://hc-ping.com/abc")

    def boom(u):
        raise OSError("no network")
    assert heartbeat.ping({"Autopilot": None}, 1.0, boom, boom) == "unreachable"


def test_both_loops_stamp_their_ticks():
    import autopilot_local
    import my_channels
    for mod in (autopilot_local, my_channels):
        src = open(mod.__file__, encoding="utf-8").read()
        body = src.split("async def loop_forever", 1)[1].split("try:", 1)[0]
        assert "last_tick = time.time()" in body, mod.__name__


# ---------- system check rows ----------

def test_system_check_rows_for_stay_awake_encoder_and_heartbeat(monkeypatch):
    import ffmpeg_utils
    import heartbeat
    import system_check as sc
    monkeypatch.setattr(keep_awake, "on_charger", lambda: True)
    monkeypatch.setenv("KEEP_AWAKE", "charger")
    monkeypatch.setattr(keep_awake, "_state", {"awake": True, "why": "on the charger, the laptop stays awake for Autopilot"})
    assert "all the time" in sc.stay_awake()["detail"]                  # not "Working now" around the clock
    monkeypatch.setattr(keep_awake, "_state", {"awake": True, "why": "working, the laptop stays awake"})
    assert sc.stay_awake()["detail"].startswith("Working now")
    monkeypatch.setenv("FFMPEG_ENCODER", "qsv")
    monkeypatch.setattr(ffmpeg_utils, "encoder_name", lambda: "h264_qsv")
    assert "Quick Sync" in sc.encoder()["detail"] and sc.encoder()["status"] == "ok"
    monkeypatch.setattr(ffmpeg_utils, "encoder_name", lambda: "libx264")
    assert sc.encoder()["status"] == "warn"
    monkeypatch.delenv("HEALTHCHECK_URL", raising=False)
    assert sc.heartbeat()["status"] == "warn" and "healthchecks.io" in sc.heartbeat()["fix"]
    monkeypatch.setenv("HEALTHCHECK_URL", "https://hc-ping.com/x")
    monkeypatch.setattr(heartbeat, "_state", {"last_fail": 0.0, "last": "ok"})
    assert sc.heartbeat() == {**sc.heartbeat(), "status": "ok"} and "Last ping: ok" in sc.heartbeat()["detail"]


# ---------- autostart.bat ----------

def test_autostart_bat_is_crlf_and_guards_its_pieces():
    raw = open(BAT, "rb").read()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b""), "cmd mis-parses labels in LF-only batch files"
    t = raw.decode("ascii")
    assert t.count('call :port_state 8000 python') == 1 and "ops\\port_check.ps1" in t
    assert 'if not exist "%~1" exit /b 0' in t, "a missing log made the size comparison a syntax error"
    assert re.search(r'set "SHORTKAAR_RESTART=watchdog"[\s\S]*start "Shortkaar server"[\s\S]*set "SHORTKAAR_RESTART="', t)
    assert "restart_notice.py down" in t and "restart_notice.py taken" in t
    assert "-m uvicorn app:app --host 127.0.0.1 --port 8000" in t        # never the stale uvicorn.exe launcher


def _variant(tmp, misses0=0):
    os.makedirs(os.path.join(tmp, "ops"))
    os.makedirs(os.path.join(tmp, "output"))
    shutil.copy(os.path.join(ROOT, "ops", "port_check.ps1"), os.path.join(tmp, "ops"))
    out = []
    for ln in open(BAT, encoding="ascii").read().replace("8000", "18000").replace("5180", "15180").splitlines():
        s = ln.strip()
        if s.startswith('start "Shortkaar server"'):
            ln = "echo START_SERVER restart=[!SHORTKAAR_RESTART!] misses=!misses!"
        elif s.startswith('start "Shortkaar dashboard"'):
            ln = "echo START_DASHBOARD"
        elif "restart_notice.py" in s and s.startswith(".venv"):
            ln = "echo NOTICE " + s.split("restart_notice.py", 1)[1].split(">>")[0].strip()
        elif s.startswith('powershell -NoProfile -Command "if (Get-CimInstance'):
            ln = "echo WATCHDOG_SPAWN_CHECK"
        elif s == "timeout /t 300 /nobreak >nul":
            ln = "    exit /b 0"
        elif s == "set /a misses=0" and misses0:
            ln = f"set /a misses={misses0}"
        out.append(ln)
    with open(os.path.join(tmp, "autostart.bat"), "w", encoding="ascii", newline="\r\n") as f:
        f.write("\n".join(out) + "\n")
    return os.path.join(tmp, "autostart.bat")


def _run(bat, *args):
    r = subprocess.run(["cmd", "/c", bat, *args], capture_output=True, text=True, timeout=120)
    wl = os.path.join(os.path.dirname(bat), "output", "watchdog.log")
    return r.stdout, r.stderr, (open(wl).read() if os.path.exists(wl) else "")


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe")
def test_autostart_paths_on_spare_ports(tmp_path):
    o, e, log = _run(_variant(str(tmp_path / "a")))
    assert "START_SERVER restart=[]" in o and "START_DASHBOARD" in o and "WATCHDOG_SPAWN_CHECK" in o, (o, e)
    assert not log and not e.strip()
    o, e, log = _run(_variant(str(tmp_path / "b")), "watch")
    assert "START_SERVER restart=[watchdog] misses=1" in o and "check 1 in a row" in log and "NOTICE" not in o, (o, e)
    o, e, log = _run(_variant(str(tmp_path / "c"), misses0=2), "watch")
    assert "NOTICE down 3" in o, (o, e)


# ---------- ops/fix_venv_paths.py ----------

def test_venv_launchers_name_this_venv():
    """Every Scripts\\*.exe of the project venv starts THIS venv's python."""
    scripts = os.path.join(ROOT, ".venv", "Scripts")
    if not os.path.isdir(scripts):
        pytest.skip("no project venv")
    me = os.path.normcase(os.path.join(ROOT, ".venv", "Scripts", "python.exe"))
    bad = []
    for name in os.listdir(scripts):
        if not name.lower().endswith(".exe") or name.lower() in ("python.exe", "pythonw.exe"):
            continue
        m = re.search(rb"#!([^\r\n]*python[w]?\.exe)", open(os.path.join(scripts, name), "rb").read(), re.I)
        if m and os.path.normcase(m.group(1).decode("utf-8", "replace").strip('"')) != me:
            bad.append(name)
    assert not bad, f"stale launchers (run .venv\\Scripts\\python.exe ops\\fix_venv_paths.py): {bad[:5]}"


# ---------- Windows text encoding of job files (4-nov-2026) ----------

def test_a_job_with_urdu_and_emoji_metadata_is_recovered_after_a_restart(tmp_path, monkeypatch):
    """server.log had 15 'Could not recover job ...: charmap codec can't decode': studio._write keeps Urdu and
    emoji as UTF-8 while app.py read job files with Windows' code page."""
    import json
    import uuid
    import app
    job_id = str(uuid.uuid4())
    job = tmp_path / job_id
    job.mkdir()
    (job / "Clip_clip_1.mp4").write_bytes(b"x")
    meta = {"shorts": [{"seo_title": "Jan Rambo ki 😂 comedy | ہنسی", "seo_description": "हिंदी"}]}
    (job / "Clip_metadata.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(app, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app, "jobs", {})
    app._recover_jobs_from_disk()
    assert job_id in app.jobs and app.jobs[job_id]["status"] == "completed"


def test_app_reads_and_writes_job_files_as_utf8():
    import re
    src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    bad = [ln.strip() for ln in src.splitlines()
           if re.search(r"with open\((json_files\[0\]|meta_files\[0\]|meta_path|metas\[0\]|target_json)\b", ln)
           and "encoding" not in ln]
    assert not bad, bad


def test_footage_paths_relative_to_the_project_are_found_from_the_job_folder(tmp_path, monkeypatch):
    """History teasers passed output\<long id>\.hv_pics\c007_full.jpg; broll runs ffmpeg inside the
    teaser's folder, where that path does not exist."""
    import broll
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output" / "long" / ".hv_pics").mkdir(parents=True)
    (tmp_path / "output" / "teaser").mkdir()
    pic = os.path.join("output", "long", ".hv_pics", "c007_full.jpg")
    open(pic, "wb").close()
    job = os.path.join("output", "teaser")
    got = broll._located(job, {"kind": "photo", "path": pic})
    assert os.path.isabs(got["path"]) and os.path.isfile(got["path"])
    own = {"kind": "photo", "path": ".broll/x.jpg"}
    os.makedirs(os.path.join(job, ".broll"))
    open(os.path.join(job, ".broll", "x.jpg"), "wb").close()
    assert broll._located(job, own) == own                       # a job-relative path stays as it was
