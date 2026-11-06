"""Quality pass 3 (29-oct-2026): stuck jobs are stopped, Gemini calls time out, see-through stock
photos are flattened, on-screen text is cut between words, the quiz countdown drains."""
import os
import subprocess
import sys
import time

import cricket_shorts as ck
import my_channels as mc
import quiz_shorts as qz
import short_kit as kit
import stock_media


def test_background_music_rotates_by_least_used(tmp_path):
    folder = os.path.join(kit.MUSIC_DIR, "quiz")
    os.makedirs(folder)
    for n in ("a.mp3", "b.mp3", "c.mp3"):
        open(os.path.join(folder, n), "wb").close()
    picks = [os.path.basename(kit.music_track("quiz")) for _ in range(3)]
    assert sorted(picks) == ["a.mp3", "b.mp3", "c.mp3"]                   # each once before any repeats
    assert os.path.basename(kit.music_track("quiz")) == picks[0]          # then the one used longest ago


def test_a_kinds_music_pool_grows_one_bed_a_day_up_to_its_target(monkeypatch):
    import music_beds
    folder = os.path.join(kit.MUSIC_DIR, "cricket")
    os.makedirs(folder)
    old = os.path.join(folder, "lyria_cricket_01.mp3")
    open(old, "wb").close()
    os.utime(old, (time.time() - 2 * 86400, time.time() - 2 * 86400))
    made = []

    def make(kind, client=None, prompt=None):
        made.append(prompt)
        path = os.path.join(folder, f"lyria_{kind}_{len(made) + 1:02d}.mp3")
        open(path, "wb").close()
        return path
    monkeypatch.setattr(music_beds, "make", make)
    assert music_beds.grow("cricket", target=3)                             # a day since the last one
    assert music_beds.grow("cricket", target=3) is None                     # not twice a day
    assert music_beds.grow("cricket", target=2, now=time.time() + 2 * 86400) is None   # target reached
    assert len(made) == 1 and music_beds.VARIANTS[1] in made[0]


def test_scripts_never_pose_as_a_person_and_ai_pictures_stay_paintings():
    import script_craft
    import history_videos
    assert script_craft.PERSONA in script_craft.short_rules() and script_craft.PERSONA in script_craft.long_rules()
    assert "never a photograph" in history_videos.AI_STYLE and "no blood" in history_videos.AI_STYLE


def test_a_job_past_its_time_is_stopped_not_only_marked(monkeypatch):
    stopped = []
    monkeypatch.setattr(mc, "cancel_job", lambda job_id, why="": stopped.append(job_id) or True)
    ch = mc.add("history")
    mc._change(ch["id"], lambda c: c.update(jobs=[{"job_id": "j1", "status": "running", "at": 1000, "day": "d"}]))
    mc.refresh_jobs(mc.get(ch["id"]), lambda j: ("running", []), "out", now=1000 + 2 * 3600)
    assert stopped == []
    ch = mc.refresh_jobs(mc.get(ch["id"]), lambda j: ("running", []), "out", now=1000 + 4 * 3600)
    assert stopped == ["j1"] and ch["jobs"][0]["error"] == "took too long"


def _alive(pid):
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def test_cancel_job_stops_the_job_and_the_process_it_started():
    import app
    # A parent that starts a child, like the venv launcher starting main.py on Windows.
    code = ("import subprocess, sys, time; "
            "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']); "
            "print(c.pid, flush=True); time.sleep(120)")
    p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    child = int(p.stdout.readline())
    app._procs["t1"] = p
    app.jobs["t1"] = {"logs": []}
    try:
        assert app._cancel_job("t1", "stopped: it took too long")
        p.wait(timeout=20)
        deadline = time.time() + 10
        while _alive(child) and time.time() < deadline:
            time.sleep(0.3)
        assert not _alive(child)
        assert "took too long" in app.jobs["t1"]["logs"][-1]
        assert not app._cancel_job("t1")                      # already ended: nothing to stop
    finally:
        app._procs.pop("t1", None)
        app.jobs.pop("t1", None)
        if p.poll() is None:
            p.kill()


def test_gemini_calls_have_a_timeout(monkeypatch):
    monkeypatch.delenv("GEMINI_TIMEOUT", raising=False)
    assert kit.http_options().timeout == 600_000
    monkeypatch.setenv("GEMINI_TIMEOUT", "30")
    assert kit.http_options().timeout == 30_000
    monkeypatch.setenv("GEMINI_TIMEOUT", "soon")
    assert kit.http_options().timeout == 600_000


def test_a_see_through_stock_photo_is_flattened_on_a_dark_ground(tmp_path):
    from PIL import Image
    cut = Image.new("RGBA", (40, 40), (255, 0, 255, 0))      # magenta under the transparent part
    cut.paste((200, 150, 50, 255), (10, 10, 30, 30))
    path = str(tmp_path / "statue.jpg")                      # a PNG cut-out cached under .jpg
    cut.save(path, "PNG")
    stock_media._flatten(path)
    with Image.open(path) as im:
        assert im.format == "JPEG" and im.mode == "RGB"
        corner, middle = im.getpixel((2, 2)), im.getpixel((20, 20))
    assert max(corner) < 40 and middle[0] > 150              # dark ground, the picture kept
    plain = str(tmp_path / "plain.jpg")
    Image.new("RGB", (20, 20), (90, 90, 90)).save(plain, "JPEG")
    before = open(plain, "rb").read()
    stock_media._flatten(plain)
    assert open(plain, "rb").read() == before                 # an opaque photo is left alone


def test_on_screen_text_is_cut_between_words_and_stats_fit():
    q = "Rohit ya Maxwell, T20I ka sabse khatarnak batsman kaun? Comment mein batao"
    cut = ck._txt(q, 60)
    assert q.startswith(cut) and q[len(cut)] == " " and len(cut) <= 60
    assert ck._txt(q, 120) == q
    assert ck._txt("x" * 30, 10) == "x" * 10                 # no space to cut at: a hard cut
    fact = ck.Fact(headline="Fashion Week Scuffle", stat="7 SEPT 2018", detail="d", line="x")
    ev = " ".join(ck.fact_events(1, 4, fact, 2.0, 6.0))
    assert "}7 SEPT 2018" in ev and f"\\fs{ck.stat_size('7 SEPT 2018')}" in ev
    assert ck.stat_size("97") == ck.STAT_PX and ck.stat_size("OCTOBER 2018") < 180


def _question(options=("Diaphragm", "Lungs", "Heart", "Stomach")):
    return qz.Question(question="Hichki mein kaun sa muscle contract hota hai?", options=list(options),
                       answer=0, answer_text="Diaphragm", explain="Diaphragm achanak sikudta hai.")


def test_the_quiz_countdown_bar_drains_from_full_to_empty():
    text = " ".join(qz.question_events(1, 3, "SAWAL", _question(), 0.0, 5.0, 9.0, 12.0))
    x0, y0 = qz.BAR_X, qz.BAR_Y
    assert f"\\clip({x0},{y0 - 4},{x0 + qz.BAR_W},{y0 + 18})" in text
    assert f"\\t(0,4000,\\clip({x0},{y0 - 4},{x0},{y0 + 18}))" in text
    pictured = " ".join(qz.question_events(1, 3, "SAWAL", _question(), 0.0, 5.0, 9.0, 12.0, picture=True))
    assert "\\clip(" not in pictured                          # no room under a flag or a star's photo
    assert "3-7 words" in qz.PROMPT


def _ranking(items=5, title="Top 5 sixers: #1 kaun?"):
    return ck.Ranking(found=True, title=title, label="MOST T20I SIXES", unit="SIXES", hook_line="Top 5 sixers!",
                      question="Aapka No. 1 kaun? Comment mein batao",
                      items=[ck.RankItem(rank=r, name=f"Player {chr(64 + r)}", team="PAK", value=str(200 - 20 * r),
                                         line="x") for r in range(items, 0, -1)])


def test_the_ranking_board_is_full_on_frame_zero_and_fills_from_number_5_up():
    story = _ranking()
    windows = [(k, 0.15 + 3 * k, 3.15 + 3 * k) for k in range(7)]       # hook, #5..#1, question
    ev = ck.ranking_events(story, windows, 21.0, "@x", [None] * 5)
    opening = [e for e in ev if e.split(",")[1] == "0:00:00.00"]
    first = " ".join(opening)
    assert "Top 5 sixers" in first and all(f"}}{r}" in first for r in range(1, 6)) and first.count("}?") == 5
    assert not any(e.endswith(("}180", "}100")) for e in opening)        # no value before its reveal
    start = {e.rsplit("}", 1)[-1]: e.split(",")[1] for e in ev if e.startswith("Dialogue: 5,")}
    assert start["100"] < start["180"]                                    # #5 (100) before #1 (180)


def test_find_ranking_orders_the_rows_and_refuses_a_thin_one(monkeypatch):
    monkeypatch.setattr(ck, "grounded", lambda client, prompt: ("top sixes facts", []))
    monkeypatch.setattr(ck, "remix_note", lambda topic: "")
    monkeypatch.setattr(ck, "remix_guard", lambda topic, story: None)
    monkeypatch.setattr(kit, "ask_json", lambda *a, **k: _ranking())
    story, _f, _s = ck.find_ranking(None, "Most T20I sixes", "@x")
    assert [i.rank for i in story.items] == [1, 2, 3, 4, 5] and "#" not in story.title and "No. 1" in story.title
    monkeypatch.setattr(kit, "ask_json", lambda *a, **k: _ranking(items=2))
    import pytest
    with pytest.raises(RuntimeError, match="thin"):
        ck.find_ranking(None, "Most T20I sixes", "@x")


def test_a_countdown_never_gives_its_number_1_away(monkeypatch):
    top = ck.RankItem(rank=1, name="Shahid Afridi", team="PAK", value="351", line="x")
    assert ck._spoils("Afridi ke 351 ODI chhakke, number do par bas 144!", top)        # the first live run
    assert ck._spoils("Sabse zyada 351 chhakke kis ne maare?", top)                    # the number alone
    assert not ck._spoils("Pakistan ke top 5 six hitters, number 1 pe hairan honge", top)
    assert not ck._spoils("1351 runs", top) and ck._spoils("11,739 runs", ck.RankItem(
        rank=1, name="Inzamam-ul-Haq", team="PAK", value="11,739", line="x"))
    assert not ck._spoils("Mohammad Rizwan bhi list mein", ck.RankItem(
        rank=1, name="Mohammad Yousuf", team="PAK", value="9,720", line="x"))
    story = ck.Ranking(found=True, title="Shahid Afridi ke 351 sixes", label="MOST ODI SIXES", unit="SIXES",
                       hook_line="Pakistan ke top 5 six hitters kaun?", question="Aapka No. 1 kaun?",
                       items=[ck.RankItem(rank=r, name=n, team="PAK", value=v, line="x") for r, n, v in
                              ((1, "Shahid Afridi", "351"), (2, "Inzamam-ul-Haq", "144"), (3, "Abdul Razzaq", "124"))])
    monkeypatch.setattr(ck, "grounded", lambda client, prompt: ("sixes facts", []))
    monkeypatch.setattr(ck, "remix_note", lambda topic: "")
    monkeypatch.setattr(ck, "remix_guard", lambda topic, s: None)
    monkeypatch.setattr(kit, "ask_json", lambda *a, **k: story)
    monkeypatch.setattr(ck.craft, "polish", lambda client, s, facts, **k: setattr(s, "hook_line", "Afridi ke 351 chhakke!"))
    got, _f, _s = ck.find_ranking(None, "Most ODI sixes", "@x")
    assert got.hook_line == "Pakistan ke top 5 six hitters kaun?"                  # the writer's hook is back
    assert got.title == "Top 3 Most Odi Sixes: No. 1 kaun?"                         # a spoiling title is replaced


def test_ranking_ideas_are_read_and_routed(monkeypatch):
    assert ck._idea_lines("ranking: Most T20I sixes by Pakistanis") == [
        {"kind": "ranking", "text": "Most T20I sixes by Pakistanis"}]
    assert mc._owner_idea("cricket", "Top 5 fastest ODI fifties")["kind"] == "ranking"
    assert mc._owner_idea("cricket", "Babar vs Kohli")["kind"] == "versus"
    ran = []
    monkeypatch.setattr(ck, "run_ranking", lambda topic, out, pipe: ran.append(topic))
    monkeypatch.setenv("CRICKET_MODE", "ranking")
    ck.run("Most T20I sixes", "out", None)
    assert ran == ["Most T20I sixes"]


def test_the_opening_question_shows_its_options_on_frame_zero():
    opening = [e for e in qz.question_events(1, 3, "SAWAL", _question(), 0.0, 5.0, 9.0, 12.0)
               if e.startswith("Dialogue: 4,") and e.endswith(("Diaphragm", "Lungs", "Heart", "Stomach"))]
    assert len(opening) == 4 and all(e.split(",")[1] == "0:00:00.00" and "\\move(" not in e for e in opening)
    later = [e for e in qz.question_events(2, 3, "SAWAL", _question(), 14.0, 19.0, 23.0, 26.0)
             if e.endswith("Lungs")]
    assert later and all("\\move(" in e for e in later)          # later questions still swipe in
