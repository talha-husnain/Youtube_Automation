"""toon_shorts.py (owner, 5-nov-2026: cartoons, talking babies and talking animals with a strong script): the code
gates of the writers' room, the mouth patch found between two pictures, the mouth timing from the voice, the
render, and the channel card."""
import json
import os
import random
import subprocess
import wave

import numpy as np
import pytest

import my_channels as mc
import short_kit as kit
import toon_shorts as ts


def _episode(**kw):
    shots = [ts.Shot(place="lounge", who=["billo", "sheru"], framing="medium", picture="Billo glares at Sheru."),
             ts.Shot(place="lounge", who=["sheru"], framing="close", picture="Sheru licks his lips."),
             ts.Shot(place="kitchen", who=["billo", "mithu"], framing="medium", picture="Mithu on the fridge."),
             ts.Shot(place="kitchen", who=["guddu"], framing="close", picture="Guddu in his high chair, unimpressed.")]
    lines = [("billo", 0, "Kisi ne meri machhli chura li hai!", "angry"),
             ("sheru", 0, "Machhli? Kaunsi machhli? Main to so raha tha.", "confused"),
             ("billo", 0, "Teri moonchon pe masala laga hai, Sheru.", "sly"),
             ("sheru", 1, "Yeh masala nahi, yeh meri personality hai.", "proud"),
             ("ammi", 1, "Billo! Fridge kis ne khula chhoda?", "angry"),
             ("mithu", 2, "Billo ne! Billo ne! Raat ke do baje!", "excited"),
             ("billo", 2, "Mithu, tujhe kal se daana band.", "angry"),
             ("guddu", 3, "Aaj kal ke janwar, na sharam na haya.", "tired"),
             ("guddu", 3, "Waise machhli main ne khayi thi.", "sly")]
    data = {"title": "Machhli kis ne khayi? 😹", "hook_caption": "Machhli chori!", "premise": "Billo's fish is gone.",
            "shape": "secret", "shots": shots,
            "lines": [ts.Line(speaker=s, shot=k, text=t, emotion=e) for s, k, t, e in lines],
            "twist": "Baby Guddu ate it.", "question": "Ghalti kis ki? Ek naam!"}
    data.update(kw)
    return ts.tidy(ts.Episode(**data))


def test_a_good_episode_passes_and_each_gate_names_its_problem():
    ep = _episode()
    assert ts.problems(ep) == []
    # Ammi is never on screen: her line plays over a shot of someone else.
    assert ep.lines[4].speaker == "ammi" and "ammi" not in ep.shots[1].who
    bad = _episode()
    bad.lines[2].shot = 1                                  # Billo talks in Sheru's close-up
    assert any("billo speaks but is not in shot 1" in p for p in ts.problems(bad))
    long = _episode()
    long.lines[0].text = "Suno suno " * 8
    assert any("hook (line 1)" in p for p in ts.problems(long))
    script = _episode()
    script.lines[3].text = "Yeh " + chr(0x0645) + chr(0x0627) + " hai"
    assert any("Latin letters" in p for p in ts.problems(script))
    stale = _episode()
    stale.lines[1].text = "Doston aaj ki video mein machhli"
    assert any("stale phrases" in p for p in ts.problems(stale))
    nobody = _episode()
    nobody.shots[3].who = ["ammi"]
    assert any("only on-screen cast keys" in p for p in ts.problems(nobody))
    place = _episode()
    place.shots[0].place = "moon"
    assert any("place 'moon'" in p for p in ts.problems(place))


def test_tidy_lowercases_keys_and_defaults_unknown_framings_and_emotions():
    ep = ts.tidy(ts.Episode(title="t", hook_caption="h", premise="p", shape=" Secret ", twist="x", question="q",
                            shots=[ts.Shot(place=" Lounge", who=["Billo "], framing="extreme close", picture="p")],
                            lines=[ts.Line(speaker="BILLO", shot=0, text="  Haan   ji ", emotion="furious"),
                                   ts.Line(speaker="billo", shot=0, text="  ", emotion="sad")]))
    assert ep.shots[0].place == "lounge" and ep.shots[0].who == ["billo"] and ep.shots[0].framing == "medium"
    assert [(l.speaker, l.text, l.emotion) for l in ep.lines] == [("billo", "Haan ji", "neutral")]
    assert ep.shape == "secret"


def _pictures(seed=1):
    rnd = np.random.default_rng(seed)
    base = (rnd.integers(60, 200, (400, 240, 3))).astype(np.uint8)
    other = np.clip(base.astype(np.int16) + rnd.integers(-6, 7, base.shape), 0, 255).astype(np.uint8)
    return base, other


def test_the_mouth_patch_is_the_changed_blob_and_noise_elsewhere_is_ignored():
    base, other = _pictures()
    other[200:225, 60:100] = 10                            # the open mouth: a dark blob, left of centre
    other[30, 200] = 255                                   # a stray pixel the re-render changed
    mask, centre = ts.mask_of(base, other)
    assert mask is not None and mask.shape == base.shape[:2]
    assert 70 <= centre[0] <= 90 and 205 <= centre[1] <= 220
    assert mask[212, 80] > 0.9 and mask[30, 200] < 0.05 and mask[350, 200] == 0
    # The left character of two: fine; claimed as the right one: refused (the edit opened the wrong mouth).
    assert ts.mask_of(base, other, ts.expect_for(2, 0))[0] is not None
    assert ts.mask_of(base, other, ts.expect_for(2, 1)) == (None, None)


def test_a_redrawn_picture_or_an_unchanged_one_gives_no_mouth():
    base, _ = _pictures()
    redrawn = np.roll(base, 9, axis=1)                     # the model moved the camera
    assert ts.mask_of(base, redrawn) == (None, None)
    assert ts.mask_of(base, base.copy()) == (None, None)
    huge = base.copy()
    huge[50:350, 20:220] = 0                               # half the picture changed: not a mouth
    assert ts.mask_of(base, huge) == (None, None)


def _wav(path, pattern, sr=24000, on=0.15, off=0.1):
    t = np.arange(int(sr * on)) / sr
    tone = (0.5 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16)
    gap = np.zeros(int(sr * off), dtype=np.int16)
    data = np.concatenate([tone if p else gap for p in pattern] + [gap])
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
    return str(path)


def test_mouths_open_on_the_voice_and_close_in_its_dips(tmp_path):
    wav = _wav(tmp_path / "v.wav", [1, 0, 1, 0, 1])
    env = ts.envelope(wav)
    assert abs(len(env) - round(kit.wav_seconds(wav) * ts.FPS)) <= 1
    track = ts.flaps(env)
    assert any(track) and not all(track)
    assert track[0] is True                                # the voice starts at 0: so does the mouth
    assert track[int(0.08 * ts.FPS)] is True               # inside the first syllable
    assert track[int(0.20 * ts.FPS)] is False              # the gap after it
    runs, cur = [], None
    for v in track:
        if v == cur:
            runs[-1] += 1
        else:
            runs.append(1)
            cur = v
    assert min(runs[1:-1]) >= 2                            # never a one-frame flicker
    assert ts.flaps(np.zeros(20)) == [False] * 20


def test_lines_get_a_beat_before_the_punchline_and_shots_cover_the_whole_video():
    ep = _episode()
    said = [(f"/v{k}.wav", 2.0) for k in range(len(ep.lines))]
    rows, end = ts.timeline(ep.lines, said)
    gaps = [rows[k + 1][1] - rows[k][2] for k in range(len(rows) - 1)]
    assert rows[0][1] == ts.LEAD and abs(gaps[-1] - ts.BEAT) < 1e-9
    assert abs(gaps[0] - ts.GAP) < 1e-9
    same = _episode()
    same.lines[1].speaker, same.lines[1].shot = "billo", 0
    rows2, _e = ts.timeline(same.lines, said)
    assert abs(rows2[1][1] - rows2[0][2] - ts.SAME_GAP) < 1e-9               # Billo twice in a row
    assert abs(end - (rows[-1][2] + 0.5)) < 1e-9
    windows = ts.shot_windows(ep, rows, end + 1.5)
    assert [w[0] for w in windows] == [0, 1, 2, 3]
    assert windows[0][1] == 0.0 and windows[-1][2] == end + 1.5
    assert all(abs(windows[k][2] - windows[k + 1][1]) < 1e-9 for k in range(len(windows) - 1))
    back = _episode()
    back.lines[-1].shot = 0
    back.shots[0].who = ["billo", "guddu"]
    w2 = ts.shot_windows(back, rows, end)
    assert [w[0] for w in w2] == [0, 1, 2, 3, 0]          # a shot that comes back gets its own window


class _Answers:
    """kit.ask_json stand-in: answers by the prompt's first words, in order, and records what was asked."""

    def __init__(self, **by):
        self.by = {k: list(v) for k, v in by.items()}
        self.asked = []

    def __call__(self, client, schema, contents, **kw):
        text = contents if isinstance(contents, str) else contents[-1]
        for key, start in (("draft", "You are the head writer"), ("judge", "Two drafts"),
                           ("punch", "You punch up"), ("check", "You check an episode"), ("ideas", "Today is")):
            if text.startswith(start):
                self.asked.append(key)
                got = self.by[key].pop(0)
                if isinstance(got, Exception):
                    raise got
                return got.model_copy(deep=True) if hasattr(got, "model_copy") else got
        raise AssertionError(text[:80])


def test_the_writers_room_judges_two_drafts_punches_up_and_checks(monkeypatch):
    good, other = _episode(), _episode(shape="backfire")
    punched = _episode(title="Raat ke 2 baje machhli gayab 😹")
    room = _Answers(draft=[good, other], judge=[ts.Pick(better=2, notes=["Sharper last line"])], punch=[punched],
                    check=[ts.Check(ok=True, problems=[])])
    monkeypatch.setattr(kit, "ask_json", room)
    ep = ts.write(None, "Billo's fish is gone", shape="secret", rows=[], n=3, log=lambda m: None,
                  rnd=random.Random(1))
    assert room.asked == ["draft", "draft", "judge", "punch", "check"]
    assert ep.title.startswith("Raat ke 2 baje")


def test_a_bad_punch_up_is_dropped_and_a_failed_check_rewrites_once_then_refuses(monkeypatch):
    broken = _episode()
    broken.lines = broken.lines[:3]                       # too short: the code gate refuses it
    room = _Answers(draft=[_episode(), broken], punch=[broken], check=[ts.Check(ok=True, problems=[])])
    monkeypatch.setattr(kit, "ask_json", room)
    ep = ts.write(None, "p", rows=[], n=1, log=lambda m: None, rnd=random.Random(2))
    assert room.asked == ["draft", "draft", "punch", "check"] and len(ep.lines) == 9   # one good draft: no judge
    sad = ts.Check(ok=False, problems=["the dog is starving"])
    room = _Answers(draft=[_episode(), _episode(), _episode()], judge=[ts.Pick(better=1, notes=[])],
                    punch=[_episode()], check=[sad, sad])
    monkeypatch.setattr(kit, "ask_json", room)
    monkeypatch.setenv("TOON_PUNCH", "0")
    with pytest.raises(RuntimeError, match="did not pass the script check"):
        ts.write(None, "p", rows=[], n=1, log=lambda m: None)
    assert room.asked == ["draft", "draft", "judge", "check", "draft", "check"]


def test_ideas_skip_premises_too_close_to_old_episodes(monkeypatch):
    ts.record(_episode(premise="Billo hides the TV remote before the big cricket match"), 1)
    got = ts.Ideas(ideas=[ts.Idea(premise="Billo hides the TV remote before the big cricket match tonight",
                                  lead="billo", shape="secret"),
                          ts.Idea(premise="Guddu complains about the electricity bill like an uncle", lead="guddu",
                                  shape="uncle")])
    monkeypatch.setattr(kit, "ask_json", _Answers(ideas=[got]))
    ideas = ts.channel_ideas(None, 4)
    assert [i["text"] for i in ideas] == ["Guddu complains about the electricity bill like an uncle"]
    assert ideas[0]["shape"] == "uncle" and ideas[0]["kind"] == "toons"
    assert ts.next_number() == 2


def test_shapes_avoid_the_last_episodes_and_keep_the_planners_choice():
    rows = [{"shape": "secret"}, {"shape": "uncle"}, {"shape": "three"}]
    for seed in range(20):
        first, second = ts.pick_shapes(rows, rnd=random.Random(seed))
        assert first not in ("secret", "uncle", "three") and second not in ("secret", "uncle", "three")
    assert ts.pick_shapes(rows, "uncle", random.Random(0))[0] == "uncle"


def test_each_character_gets_its_own_pitched_voice():
    import free_voice
    items = ts.voice_items(_episode())
    assert items[0]["edge_voice"] == "ur-PK-UzmaNeural" and items[0]["pitch"] == "+14Hz"
    assert items[0]["rate"] == "+14%"                      # Billo is angry: 6 points faster
    assert items[7]["rate"] == "-4%"                       # Guddu is tired: 6 points slower
    got = free_voice.voice_items(None, [{**items[0], "language": "English"}, {"text": "x", "voice": "Puck"}])
    assert got[1] is None or len(got[1]) == 3              # an ordinary line keeps the 3-tuple


def test_free_voice_reads_a_character_with_its_own_voice_and_pitch(monkeypatch):
    import free_voice
    monkeypatch.setattr(free_voice, "to_urdu_script", lambda client, lines: [f"U{k}" for k in range(len(lines))])
    items = ts.voice_items(_episode())[:2] + [{"text": "Haan", "voice": "Charon", "style": "calm"}]
    got = free_voice.voice_items(None, items)
    assert got[0] == ("U0", "ur-PK-UzmaNeural", "+14%", "+14Hz")
    assert got[1] == ("U1", "ur-PK-AsadNeural", "-6%", "-8Hz")
    assert got[2] == ("U2", "ur-PK-AsadNeural", "-4%")
    said = []

    async def fake_say(text, voice, rate, mp3, pitch="+0Hz"):
        said.append((voice, rate, pitch))
        raise ValueError("offline")
    monkeypatch.setattr(free_voice, "_say", fake_say)
    monkeypatch.setattr(free_voice, "TRIES", 1)
    assert free_voice.speak("x", "out.wav", "ur-IN-GulNeural", "+2%", "+28Hz") is None
    assert said == [("ur-IN-GulNeural", "+2%", "+28Hz")]


def test_the_shot_art_lays_only_the_mouth_over_the_closed_picture():
    base, other = _pictures(3)
    other[200:225, 60:100] = 10
    mask, centre = ts.mask_of(base, other)
    art = ts.ShotArt(base, {"billo": (other, mask, centre)})
    shut, talk = art.picture(), art.picture("billo")
    assert shut.shape == (round(ts.H * ts.MARGIN), round(ts.W * ts.MARGIN), 3)
    diff = np.abs(shut.astype(int) - talk.astype(int)).max(axis=2) > 30
    ys, xs = np.nonzero(diff)
    fx, fy = art.focus("billo")
    assert abs(xs.mean() - fx) < 40 and abs(ys.mean() - fy) < 40
    assert diff.mean() < 0.05
    assert art.picture("nobody") is shut                   # a voice from off screen: the closed picture


def test_the_camera_pushes_in_leans_to_the_speaker_and_never_leaves_the_canvas():
    cw, ch = round(ts.W * ts.MARGIN), round(ts.H * ts.MARGIN)
    z0, cx0, cy0 = ts.camera(0.0, 0.0, 4.0)
    assert z0 == 1.0 and (cx0, cy0) == (cw / 2, ch / 2)
    z1, cx1, _ = ts.camera(3.9, 0.0, 4.0, focus=(0, 0))
    assert 1.0 < z1 <= 1.0 + ts.PUSH and cx1 < cw / 2
    hw = ts.W / 2 / (z1 / ts.MARGIN)
    assert cx1 >= hw - 1e-6
    z2, _, _ = ts.camera(3.9, 0.0, 4.0, punch_at=3.0)
    assert abs(z2 - z1 - ts.PUNCH) < 1e-6 and z2 <= ts.MARGIN


def test_the_picture_track_has_every_frame(tmp_path):
    base, other = _pictures(4)
    other[200:225, 60:100] = 10
    mask, centre = ts.mask_of(base, other)
    art = ts.ShotArt(base, {"billo": (other, mask, centre)})
    plan = [{"art": art, "a": 0.0, "b": 0.5, "talk": [(0.1, 0.4, "billo", [True, False] * 6)], "blinks": [],
             "punch": None, "shake": 0.2, "focus": "billo"},
            {"art": ts.ShotArt(other), "a": 0.5, "b": 1.0, "talk": [], "blinks": [(0.6, 0.7)], "punch": 0.6,
             "shake": None, "focus": None}]
    out = ts.render_track(plan, 1.0, str(tmp_path / "track.mp4"))
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames,width,height", "-of", "json", out], capture_output=True, text=True)
    s = json.loads(probe.stdout)["streams"][0]
    assert (s["width"], s["height"], int(s["nb_read_frames"])) == (ts.W, ts.H, ts.FPS)


def test_text_names_each_speaker_once_and_marks_the_voice_off_screen():
    ep = _episode()
    rows, end = ts.timeline(ep.lines, [(None, 2.0)] * len(ep.lines))
    ev = ts.text_events(ep, rows, 7, end)
    names = [e for e in ev if ",TnName," in e]
    assert len(names) == 5 and any("AMMI (AWAAZ)" in e for e in names)
    assert any("EP 7" in e for e in ev) and any("MACHHLI CHORI!" in e for e in ev)


def test_sounds_put_a_boing_after_the_punchline():
    ep = _episode()
    rows, end = ts.timeline(ep.lines, [(None, 2.0)] * len(ep.lines))
    sfx = ts.sounds(ep, rows, ts.shot_windows(ep, rows, end))
    assert (ts.BOING, 0.5, rows[-1][2] + 0.05) in sfx and any(s[0] == ts.DING for s in sfx)


def test_a_toons_card_plans_and_sends_one_premise(monkeypatch):
    import toon_shorts
    monkeypatch.setattr(toon_shorts, "channel_ideas", lambda client, count, **kw: [
        {"text": "Guddu runs the house during load-shedding", "shape": "uncle", "kind": "toons", "lead": "guddu"}])
    ch = mc.add("toons")
    assert mc.KINDS["toons"]["genre"] == "toons" and mc.PLANNERS["toons"] == "toon_shorts"
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert payload["genre"] == "toons" and payload["toon_premise"].startswith("Guddu")
    assert payload["toon_shape"] == "uncle" and payload["bg_music"] is True
    assert meta["format"] == "toons"


def test_process_accepts_a_toons_job_and_passes_the_premise(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    ch = mc.add("toons")
    r = TestClient(app_module.app).post("/api/process", json={
        "genre": "toons", "channel": ch["id"], "toon_premise": "Billo  hides the remote", "toon_shape": "Secret!",
        "acknowledged": True, "bg_music": True}, headers={"X-Shortkaar-Autopilot": "1"})
    assert r.status_code == 200, r.text
    src = json.loads((tmp_path / r.json()["job_id"] / ".source.json").read_text())
    assert src["genre"] == "toons"
    env = app_module.jobs[r.json()["job_id"]]["env"]
    assert env["TOON_PREMISE"] == "Billo hides the remote" and env["TOON_SHAPE"] == "secret" and env["BG_MUSIC"] == "1"


def test_uploads_are_comedy_and_the_kinds_tables_know_toons():
    import engage
    import music_beds
    import niche_research
    import viral_remix
    import youtube_account
    assert youtube_account.CATEGORY["toons"] == "23"
    assert "toons" in engage.FOLLOW_LINE and ("toons", None) in engage.PLAYLISTS and "toons" in engage.WHO
    assert len(music_beds.PROMPTS["toons"]) >= 3
    assert "toons" in niche_research.NICHES and "toons" in viral_remix.WHAT and "toons" in viral_remix.TOPIC_RULE
    assert viral_remix._rules("toons") == ts.RULES
    assert mc.IG_GROUPS["toons"] == "toons" and "toons" in mc.ABOUT and "toons" in mc.VOICE_KINDS


def test_cast_references_are_drawn_once_and_kept(monkeypatch, tmp_path):
    calls = []

    def fake_image(client, contents, out, size="1K"):
        calls.append(contents[-1])
        from PIL import Image
        Image.new("RGB", (48, 86), (200, 120, 40)).save(out)
        return out
    monkeypatch.setattr(ts, "_image", fake_image)
    first = ts.cast_ref(None, "billo")
    assert os.path.isfile(first) and ts.cast_ref(None, "billo") == first and len(calls) == 1
    assert "orange tabby" in calls[0] and "mouth closed" in calls[0]


def test_a_two_part_idea_becomes_two_queued_parts_and_is_never_cut_in_half(monkeypatch):
    got = ts.Ideas(ideas=[ts.Idea(premise="Billo opens the fridge at midnight and finds someone inside", lead="billo",
                                  shape="secret", parts=2, series="Fridge Ka Raaz!"),
                          ts.Idea(premise="Guddu complains about the gas bill like an uncle", lead="guddu",
                                  shape="uncle")])
    monkeypatch.setattr(kit, "ask_json", _Answers(ideas=[got]))
    ideas = ts.channel_ideas(None, 1)
    assert [(i.get("series"), i.get("part")) for i in ideas] == [("Fridge Ka Raaz", 1), ("Fridge Ka Raaz", 2)]
    assert ideas[1]["text"].endswith("(part 2)") and ideas[1]["parts"] == 2


def test_part_two_opens_on_part_ones_cliffhanger():
    ep = _episode()
    ts.record(ep, 5, series_name="Fridge Ka Raaz", part=1)
    part = ts.series_part("Fridge Ka Raaz", 2, 2)
    assert part[:2] == (2, 2) and part[2][-1] == "Guddu: Waise machhli main ne khayi thi."
    note = ts.part_note(part)
    assert "PART 2 OF 2" in note and "Guddu: Waise machhli" in note and "(Part 2)" in note
    assert "CLIFFHANGER" in ts.part_note((1, 2, []))
    assert ts.part_note(None) == "" and ts.series_part("", 1, 1) is None


def test_the_writer_and_the_check_hear_which_part_it_is(monkeypatch):
    room = _Answers(draft=[_episode(), _episode()], judge=[ts.Pick(better=1, notes=[])], punch=[_episode()],
                    check=[ts.Check(ok=True, problems=[])])
    prompts = []

    def spy(client, schema, contents, **kw):
        prompts.append(contents if isinstance(contents, str) else contents[-1])
        return room(client, schema, contents, **kw)
    monkeypatch.setattr(kit, "ask_json", spy)
    ts.write(None, "p", rows=[], n=2, log=lambda m: None, part=(1, 2, []))
    assert "THIS IS PART 1 OF 2" in prompts[0] and "cliffhanger ending IS its payoff" in prompts[-1]


def test_a_cartoon_part_is_queued_with_its_series_for_the_upload_links(monkeypatch):
    import toon_shorts
    monkeypatch.setattr(toon_shorts, "channel_ideas", lambda client, count, **kw: [
        {"text": "Fridge mystery", "shape": "secret", "kind": "toons", "series": "Fridge Ka Raaz", "part": 1,
         "parts": 2}])
    ch = mc.add("toons")
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert (payload["toon_series"], payload["toon_part"], payload["toon_parts"]) == ("Fridge Ka Raaz", 1, 2)
    assert meta["series"] == "Fridge Ka Raaz" and meta["series_part"] == 1 and meta["label"].startswith("Part 1")


def test_part_two_links_part_one_in_its_description():
    import history_videos
    ups = [{"genre": "toons", "status": "done", "video_id": "AAAAAAAAAAA", "series": "Fridge Ka Raaz",
            "series_part": 1}]
    desc = history_videos.series_links("Hello\n\n#cartoon", ups, "Fridge Ka Raaz", 2, "urdu", genres=("toons",))
    assert "https://youtu.be/AAAAAAAAAAA" in desc and desc.index("youtu.be") < desc.index("#cartoon")
    assert history_videos.series_links("Hello", ups, "Fridge Ka Raaz", 2) == "Hello"   # a long series is not it


def test_part_one_says_part_two_is_coming():
    ep = _episode()
    rows, end = ts.timeline(ep.lines, [(None, 2.0)] * len(ep.lines))
    assert any("PART 2 JALD" in e for e in ts.text_events(ep, rows, 3, end, more=True))
    assert not any("PART 2 JALD" in e for e in ts.text_events(ep, rows, 3, end))


def test_an_open_mouth_is_closed_by_an_edit_and_other_problems_are_redrawn():
    assert ts.only_mouths("Guddu's mouth is open")
    assert not ts.only_mouths("Billo is missing and Sheru's mouth is open")
    assert not ts.only_mouths("there is text on the wall")


def test_close_mouths_keeps_the_picture_when_the_edit_redrew_it(monkeypatch, tmp_path):
    from PIL import Image
    base, other = _pictures(5)
    path = str(tmp_path / "shot.png")
    Image.fromarray(base).save(path)
    shut = other.copy()
    shut[200:225, 60:100] = 10

    def edit(client, contents, out, size="1K"):
        Image.fromarray(shut).save(out)
        return out
    monkeypatch.setattr(ts, "_image", edit)
    assert ts.close_mouths(None, _episode(), 0, path) == path
    assert np.abs(ts._load(path).astype(int) - shut.astype(int)).max() == 0
    Image.fromarray(base).save(path)
    shut = np.roll(base, 9, axis=1)                        # a redrawn picture: the original stays
    assert ts.close_mouths(None, _episode(), 0, path) is None
    assert np.abs(ts._load(path).astype(int) - base.astype(int)).max() == 0


def test_a_line_read_by_another_voice_gets_the_characters_voice_again(monkeypatch, tmp_path):
    import free_voice
    edge = tmp_path / "a.wav"
    edge.write_bytes(b"edge")
    (tmp_path / "a.wav.words.json").write_text("[]")
    other = tmp_path / "b.wav"
    other.write_bytes(b"local")
    monkeypatch.setattr(free_voice, "engine", lambda: "edge")
    monkeypatch.setattr(free_voice, "voice_items", lambda client, items: [("U", "ur-PK-AsadNeural", "-6%", "-8Hz")])
    spoken = []

    def speak(text, path, voice, rate="+0%", pitch="+0Hz"):
        spoken.append((voice, rate, pitch))
        open(path, "wb").write(b"edge again")
        open(path + ".words.json", "w").write("[]")
        return 3.5
    monkeypatch.setattr(free_voice, "speak", speak)
    items = ts.voice_items(_episode())[:2]
    said = ts.same_voices(None, items, [(str(edge), 2.0), (str(other), 3.0)], log=lambda m: None, wait=0)
    assert spoken == [("ur-PK-AsadNeural", "-6%", "-8Hz")] and said[1] == (str(other), 3.5)
    assert other.read_bytes() == b"edge again" and (tmp_path / "b.wav.words.json").exists()


def test_the_picture_track_can_move_with_depth(tmp_path):
    import time as _t
    base, other = _pictures(6)
    art = ts.ShotArt(base)
    calls = []

    def depth(bgr):
        calls.append(bgr.shape)
        return np.tile(np.linspace(0, 1, bgr.shape[1], dtype=np.float32), (bgr.shape[0], 1))
    plan = [{"art": art, "a": 0.0, "b": 1.0, "talk": [], "blinks": [], "punch": None, "shake": None, "focus": None}]
    t0 = _t.time()
    out = ts.render_track(plan, 1.0, str(tmp_path / "depth.mp4"), depth_fn=depth)
    assert calls == [art.base.shape] and art.depth is not None and art.depth is not False
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames", "-of", "json", out], capture_output=True, text=True)
    assert int(json.loads(probe.stdout)["streams"][0]["nb_read_frames"]) == ts.FPS
    assert _t.time() - t0 < 30                             # 30 frames: well under a second each
    art2 = ts.ShotArt(base)
    ts.render_track([{**plan[0], "art": art2}], 0.2, str(tmp_path / "broken.mp4"),
                    depth_fn=lambda bgr: (_ for _ in ()).throw(RuntimeError("no model")), log=lambda m: None)
    assert art2.depth is False                             # a failed depth: the plain camera


def test_a_part_keeps_its_number_in_the_final_title():
    assert ts.with_part("Raat 2 baje Billo ki chori ulti parh gayi #shorts #funny", 1) == \
        "Raat 2 baje Billo ki chori ulti parh gayi (Part 1) #shorts #funny"
    assert ts.with_part("Fridge ka raaz (Part 1)", 2) == "Fridge ka raaz (Part 2)"
    assert len(ts.with_part("x" * 150 + " #shorts", 2)) <= 100


def test_a_shape_given_as_its_description_becomes_its_key():
    ep = _episode(shape="SECRET OUT: someone hides something; it comes out at the worst moment")
    assert ep.shape == "secret"
    assert _episode(shape="plan backfires: a character").shape == "backfire"
    assert _episode(shape="something else entirely long").shape == "something else entir"


def test_the_episode_length_is_an_ab_test(monkeypatch):
    import toon_shorts
    monkeypatch.setattr(toon_shorts, "channel_ideas", lambda client, count, **kw: [
        {"text": "Guddu runs the house during load-shedding", "shape": "uncle", "kind": "toons"}])
    ch = mc.add("toons")
    payload, meta = mc.next_payload(mc.get(ch["id"]), lambda: None)
    assert meta["toonlen"] in ("long", "short") and payload["toon_length"] == meta["toonlen"]
    monkeypatch.setenv("TOON_LENGTH", "short")
    assert ts.limits() == ((6, 10), (42, 82))
    nine = _episode()                                      # 9 lines, ~70 words: fits both sides
    assert ts.problems(nine) == []
    assert "(25-32 seconds)" in ts._craft("secret") and "6-9 lines" in ts._craft("secret")
    monkeypatch.setenv("TOON_LENGTH", "long")
    assert "(30-42 seconds)" in ts._craft("secret") and ts.limits()[0] == (8, 13)


def test_process_passes_the_length_side_and_the_compilation_flag(monkeypatch, tmp_path):
    app_module = pytest.importorskip("app")
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "BILLING_ENABLED", False)
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "_enqueue_job", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    ch = mc.add("toons")
    client = TestClient(app_module.app)
    r = client.post("/api/process", json={"genre": "toons", "channel": ch["id"], "toon_premise": "Remote war",
                                          "toon_length": "short", "toon_series": "Remote War!", "toon_part": 2,
                                          "toon_parts": 2, "acknowledged": True},
                    headers={"X-Shortkaar-Autopilot": "1"})
    env = app_module.jobs[r.json()["job_id"]]["env"]
    assert (env["TOON_LENGTH"], env["TOON_SERIES"], env["TOON_PART"], env["TOON_PARTS"]) == ("short", "Remote War",
                                                                                            "2", "2")
    r = client.post("/api/process", json={"genre": "toons", "channel": ch["id"], "toon_mix": True,
                                          "acknowledged": True}, headers={"X-Shortkaar-Autopilot": "1"})
    env = app_module.jobs[r.json()["job_id"]]["env"]
    assert env["TOON_MIX_JOB"] == "1" and "TOON_LENGTH" not in env


def test_the_compilation_picture_is_a_talking_close_up():
    ep = _episode()
    art = {k: {"base": f"s{k}.png", "mouths": {}, "blink": None} for k in range(4)}
    assert ts.thumb_shot(ep, art) == 0
    art[2]["mouths"] = {"billo": "m.png"}
    assert ts.thumb_shot(ep, art) == 2                    # medium, but someone talks
    art[3]["mouths"] = {"guddu": "m.png"}
    assert ts.thumb_shot(ep, art) == 3                    # Guddu's close-up wins


def test_a_shot_the_model_will_not_draw_gets_a_simpler_picture(monkeypatch, tmp_path):
    from PIL import Image
    ref = tmp_path / "ref.png"
    Image.new("RGB", (40, 70), (200, 100, 30)).save(ref)
    asked = []

    def image(client, contents, out, size="1K", aspect="9:16"):
        asked.append(contents[-1])
        if len(asked) == 1:
            raise RuntimeError("the image model returned no picture: I can't draw that")
        Image.new("RGB", (40, 70)).save(out)
        return out
    monkeypatch.setattr(ts, "_image", image)
    ep = _episode()
    out = ts.draw_shot(None, ep, 3, {"guddu": str(ref)}, str(tmp_path / "s.png"))
    assert out and ep.shots[3].picture in asked[0] and ts.SIMPLE_PICTURE in asked[1]
    monkeypatch.setattr(ts, "_image", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("quota exhausted 429")))
    with pytest.raises(RuntimeError, match="429"):
        ts.draw_shot(None, ep, 3, {"guddu": str(ref)}, str(tmp_path / "s2.png"))
