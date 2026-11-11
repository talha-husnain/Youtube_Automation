"""Weekly mood mixes (5-nov-2026): the song archive, which mix is due, the mix job's wiring, and a real (short)
mix rendered from archived songs with timed lyrics."""
import json
import os
import shutil
import subprocess
import time

import pytest

import music_moods as mm

HAVE_FFMPEG = bool(shutil.which("ffmpeg"))


@pytest.fixture
def archive(tmp_path, monkeypatch):
    root = tmp_path / "songs"
    monkeypatch.setattr(mm, "ARCHIVE_DIR", str(root))
    return root


def _song(path, seconds=4.0, freq=330):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"sine=frequency={freq}:duration={seconds}", "-ac", "2", "-b:a", "128k", str(path)], check=True)
    return str(path)


def _keep(tmp_path, job, mood="sad", seconds=4.0, freq=330, picture=True):
    from PIL import Image
    src = _song(tmp_path / f"{job}.mp3", seconds, freq)
    pic = None
    if picture:
        pic = str(tmp_path / f"{job}.png")
        Image.new("RGB", (540, 960), (90, 30, 60)).save(pic)
    return mm.archive_song(job, src, {"title": f"Song {job}", "mood": mood, "lines": [["first line", 0.5, 2.0],
                                                                                    ["second line", 2.0, 3.6]],
                                      "colors": ["#2A0B2E", "#05040A"], "seconds": seconds}, pic)


# ---------- the archive ----------

@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_a_song_is_kept_whole_with_its_lines_and_picture(tmp_path, archive):
    d = _keep(tmp_path, "job-1")
    assert os.path.isfile(os.path.join(d, "song.mp3")) and os.path.isfile(os.path.join(d, "picture.jpg"))
    rows = mm.archived()
    assert len(rows) == 1 and rows[0]["job_id"] == "job-1" and rows[0]["picture"] and rows[0]["lines"][0][0] == "first line"
    mm.mark_mixed([d], "mix-9")
    assert mm.archived()[0]["mixed"] == "mix-9"
    # Old ones go: past ARCHIVE_DAYS they are removed.
    assert mm.archived(now=time.time() + (mm.ARCHIVE_DAYS + 1) * 86400) == [] and not os.path.isdir(d)
    assert mm.archive_song("x", str(tmp_path / "missing.mp3"), {}) is None      # never raises


# ---------- which mix is due ----------

def _rows(n, mood="sad", mixed=False):
    return [{"job_id": f"j{k}", "mood": mood, "dir": f"/a/j{k}", "at": k, "seconds": 60, **({"mixed": "m"} if mixed else {})}
            for k in range(n)]


def test_a_song_mood_mixes_its_uploaded_unmixed_songs_once_a_week():
    jobs = [{"job_id": f"j{k}", "status": "uploaded"} for k in range(10)]
    s = mm.settings_of({})
    key, dirs = mm.next_mix(s, jobs, songs=_rows(9), now=1e9)
    # Study/sleep are always "ready" (they make their tracks); sad has 9 songs: the one mixed longest ago first,
    # ties go to the mood with more songs.
    assert key == "sad" and len(dirs) == 9
    # Not uploaded songs (skipped, waiting) never go in.
    assert mm.mix_songs("sad", {"j1", "j2"}, _rows(9)) == _rows(9)[1:3]
    assert len(mm.mix_songs("sad", {f"j{k}" for k in range(9)}, _rows(9, mixed=True))) == 0
    # A mix this week: the next waits; 2 a week allows another.
    week = jobs + [{"format": "mix", "mood": "sad", "status": "uploaded", "at": 1e9 - 3 * 86400}]
    assert mm.next_mix(s, week, songs=_rows(9), now=1e9) is None
    nxt = mm.next_mix(mm.settings_of({"mixes": 2}), week, songs=_rows(9), now=1e9)
    assert nxt[0] in ("study", "sleep")                                     # sad was mixed: the others come first
    assert mm.next_mix(mm.settings_of({"mixes": 0}), jobs, songs=_rows(9), now=1e9) is None
    # A failed try waits a day; one running blocks any other.
    assert mm.next_mix(s, jobs + [{"format": "mix", "status": "failed", "at": 1e9 - 3600}], songs=_rows(9), now=1e9) is None
    assert mm.next_mix(s, jobs + [{"format": "mix", "status": "running", "at": 1}], songs=_rows(9), now=1e9) is None


def test_too_few_songs_wait_and_the_owner_can_ask_for_a_mix_now():
    jobs = [{"job_id": f"j{k}", "status": "uploaded"} for k in range(3)]
    s = mm.settings_of({"off": ["study", "sleep"]})
    assert mm.next_mix(s, jobs, songs=_rows(3), now=1e9) is None                # 3 < MIX_MIN_SONGS
    key, dirs = mm.next_mix(s, jobs, songs=_rows(3), now=1e9, wanted="sad")
    assert key == "sad" and len(dirs) == 3
    # The budget at 0 turns the instrumental mixes off.
    assert mm.next_mix(mm.settings_of({"mix_budget": 0}), [], songs=[], now=1e9) is None
    summary = mm.mix_summary(s, jobs, songs=_rows(3))
    assert summary["sad"] == "3 of 8 songs for its next mix" and summary["study"].startswith("mix only")


def test_mix_only_moods_never_become_shorts():
    s = mm.settings_of({})
    assert "study" in mm.active(s) and "study" not in mm.song_moods(s)
    picks = {mm.pick(s, []) for _ in range(200)}
    assert not picks & {"study", "sleep"}
    rows = {r["key"]: r for r in mm.summary(s, [{"status": "uploaded", "format": "mix", "mood": "sleep"}])}
    assert rows["sleep"]["mix_only"] and rows["sleep"]["mixes"] == 1 and rows["sleep"]["songs"] == 0


# ---------- the channel's mix job ----------

def test_the_song_channel_makes_its_due_mix_as_an_extra_long_video(monkeypatch):
    import my_channels as mc
    import youtube_account as ya
    ch = mc.add("music")
    mc.update(ch["id"], {"moods": {"off": ["study", "sleep"]}})
    jobs = [{"job_id": f"j{k}", "status": "uploaded", "mood": "sad", "at": k} for k in range(9)]
    mc._change(ch["id"], lambda c: c.update(jobs=jobs))
    monkeypatch.setattr(mm, "archived", lambda root=None, now=None: _rows(9))
    ch = mc.get(ch["id"])
    assert mc.mix_due(ch)
    payload, meta = mc.next_payload(ch, lambda: None)
    assert payload["music_mix"] == "sad" and len(payload["music_mix_songs"]) == 9 and payload["music_mix_vol"] == 1
    assert payload["music_mix_mood"]["name"] == "Sad songs" and meta["format"] == "mix" and meta["mood"] == "sad"
    # On top of the day's Shorts, uploaded as a long Music video, judged as a long video.
    assert "mix" in mc.EXTRA_FORMATS and mc.upload_genre(ch, {"format": "mix"}) == "music_mix"
    assert ya.CATEGORY["music_mix"] == "10" and "music_mix" in ya.LONG_GENRES
    assert mc.MIX_TIMEOUT > mc.JOB_TIMEOUT


def test_process_passes_the_mix_and_keeps_only_archive_folders(monkeypatch, tmp_path, archive):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    inside = os.path.join(str(archive), "job-1")
    r = TestClient(app_module.app).post("/api/process", json={
        "genre": "music", "music_mix": "sad", "music_mix_songs": [inside, "C:/Windows/System32", "../../etc"],
        "music_mix_mood": {"name": "Sad songs"}, "music_mix_minutes": 999, "music_mix_budget": 99,
        "acknowledged": True}, headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 200, r.text
    env = app_module.jobs[r.json()["job_id"]]["env"]
    assert env["MUSIC_MIX"] == "sad" and json.loads(env["MUSIC_MIX_SONGS"]) == [inside]
    assert env["MUSIC_MIX_MINUTES"] == "60" and env["MUSIC_MIX_BUDGET"] == "5.0"
    assert json.loads(env["MUSIC_MIX_MOOD"]) == {"name": "Sad songs"}


def test_make_a_mix_now_says_when_there_is_not_enough(monkeypatch, archive):
    app_module = pytest.importorskip("app")
    import my_channels as mc
    from fastapi.testclient import TestClient
    ch = mc.add("music")
    client = TestClient(app_module.app)
    r = client.post(f"/api/my-channels/{ch['id']}/make", json={"mix": "sad"})
    assert r.status_code == 400 and "a mix needs 8 minutes" in r.json()["detail"]
    mc.update(ch["id"], {"moods": {"mix_budget": 0}})
    r = client.post(f"/api/my-channels/{ch['id']}/make", json={"mix": "sleep"})
    assert r.status_code == 400 and "budget" in r.json()["detail"]
    mc.update(ch["id"], {"moods": {"mix_budget": 1.5}})
    monkeypatch.setattr(mc, "running", lambda c: True)
    r = client.post(f"/api/my-channels/{ch['id']}/make", json={"mix": "sleep"})
    assert r.status_code == 200 and r.json()["queued"] and mc.get(ch["id"])["next_mix"] == "sleep"


# ---------- a real mix ----------

@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")
def test_a_song_mix_renders_one_chapter_per_song_with_its_lyrics(tmp_path, archive, monkeypatch):
    import mood_mix
    import short_kit as kit
    dirs = [_keep(tmp_path, "a1", freq=330), _keep(tmp_path, "a2", freq=440, picture=False)]
    out = tmp_path / "job"
    out.mkdir()
    monkeypatch.setattr(mood_mix, "MIX_MIN_SECONDS", 5)
    monkeypatch.setattr(mood_mix, "MIN_TRACK_SECONDS", 1)
    monkeypatch.setattr(kit, "gemini", lambda: None)
    monkeypatch.setattr(kit, "level", lambda path: None)
    monkeypatch.setenv("FFMPEG_ENCODER", "libx264")
    finished = {}
    monkeypatch.setattr(kit, "finish", lambda output_dir, stem, clips, transcript, pipeline, extra=None:
                        finished.update(clip=clips[0], extra=extra))
    monkeypatch.setenv("MUSIC_MIX", "sad")
    monkeypatch.setenv("MUSIC_MIX_SONGS", json.dumps(dirs + [str(tmp_path)]))       # the last one is not in the archive
    monkeypatch.setenv("MUSIC_MIX_VOL", "3")
    # A relative job folder, as the server passes it ("output/<id>"): the first live mix (5-nov-2026) failed
    # with "Could not create a libass track" because each chapter's ffmpeg ran inside it on relative paths.
    monkeypatch.chdir(tmp_path)
    mood_mix.run("job", None)
    clip = finished["clip"]
    secs = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 clip["file"]], capture_output=True, text=True).stdout)
    assert secs == pytest.approx(2 * (4.0 + mood_mix.GAP), abs=0.3)
    assert [c["at"] for c in clip["chapters"]] == [0.0, round(4.0 + mood_mix.GAP, 2)]
    assert clip["seo_title"].startswith("Sad songs Mix") and "Vol. 3" in clip["seo_title"]
    assert "0:00 Song a1" in clip["seo_description"] and "Google Lyria" in clip["seo_description"]
    assert clip["ai_made"] is True and finished["extra"]["format"] == "16:9" and clip["mix"]["tracks"] == 2
    assert os.path.isfile(os.path.join(str(out), "thumbnail.jpg"))
    assert all(r.get("mixed") == "job" for r in mm.archived())                # never in a second mix


def test_without_gemini_credit_the_instrumental_tracks_come_through_fal(tmp_path, monkeypatch):
    # Every sleep/study mix failed with "Only 0:00 of music" from 6-nov-2026: Lyria on the Gemini API had no credit.
    import ai_fallback
    import mood_mix
    import music_shorts as ms
    import talkies
    monkeypatch.setattr(ai_fallback, "status", lambda: {"gemini_down": True})
    monkeypatch.setattr(ms, "fal_enabled", lambda: True)
    asked = []
    monkeypatch.setattr(talkies, "fal_job", lambda endpoint, payload: asked.append(payload["prompt"]) or
                        {"audio": {"url": "https://fal.media/t.mp3"}})
    monkeypatch.setattr(talkies, "_download", lambda url, out: open(out, "wb").write(b"ID3") and out)
    monkeypatch.setattr(ms, "media_seconds", lambda path: 150.0)
    mood = {"name": "Sleep music", "sound": ["slow ambient piano"]}
    tracks = mood_mix.make_tracks(None, mood, 30, 0.35, str(tmp_path), log=lambda m: None)
    assert len(tracks) == 3 and len(asked) == 3                 # $0.35 buys three $0.10 tracks
    assert all(p.startswith("Instrumental only") for p in asked)
