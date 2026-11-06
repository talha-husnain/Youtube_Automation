"""teardown.py (5-nov-2026, the owner's REA repo: "reverse engineer something and make our system better"):
the niche's winners and our own videos measured from their files the same way, the gaps as lines with their
numbers in every script prompt, and the footage cut pace tested against ours."""
import os
import subprocess

import pytest

import my_channels as mc
import niche_research as nr
import teardown as td
import viral_remix as vr
import youtube_account as ya


def _m(**kw):
    base = {"seconds": 30.0, "measured": 30.0, "cuts": 10, "first_cut": 1.0, "shot": 1.5, "cuts_10s": 3.3,
            "first_word": 0.1, "hook_words": 9, "wps": 3.4, "talk": 0.8, "first_luma": 120.0, "loop": True}
    base.update(kw)
    return base


def _data(theirs=5, ours=4, **our_kw):
    return {"anatomy": {f"t{i}": {"m": _m(), "at": i} for i in range(theirs)},
            "ours": {f"o{i}": {"m": _m(**{"seconds": 55.0, "first_cut": 4.0, "shot": 2.6, "loop": False,
                                          "first_word": 0.12, **our_kw}), "at": i} for i in range(ours)}}


def test_the_measures_from_cut_times_and_heard_words():
    a = td.anatomy(20.0, 20.0, [2.0, 5.0, 9.0, 25.0], [(0.4, 0.7), (0.8, 1.0), (2.9, 3.2), (6.0, 6.5)],
                   [100] * 4, [100] * 4)
    assert a["cuts"] == 3 and a["first_cut"] == 2.0 and a["shot"] == 3.5        # shots 2, 3, 4, 11
    assert a["cuts_10s"] == 1.5 and a["first_word"] == 0.4 and a["hook_words"] == 3
    assert a["wps"] == round(4 / 6.1, 2) and a["first_luma"] == 100 and a["loop"] is True
    piece = td.anatomy(600.0, 180.0, [], [], [10] * 4, [10] * 4)          # a long video's first 3 minutes
    assert piece["loop"] is None and piece["first_cut"] == 180.0 and piece["first_word"] is None
    assert piece["wps"] == 0.0 and piece["seconds"] == 600.0
    assert td.anatomy(10, 10, [], [], [0] * 4, [255] * 4)["loop"] is False


def test_gaps_need_enough_videos_a_real_difference_and_say_what_to_do():
    assert td.compare(_data(theirs=3)) == [] and td.compare(_data(ours=2)) == []
    rows = {r["key"]: r for r in td.compare(_data())}
    assert set(rows) == {"seconds", "first_cut", "shot", "loop"}        # first word 0.10 vs 0.12: noise
    assert rows["first_cut"]["theirs"] == 1.0 and rows["first_cut"]["ours"] == 4.0
    assert rows["first_cut"]["advice"] == "change the picture sooner" and rows["shot"]["advice"] == "cut faster"
    assert rows["seconds"]["advice"] == "make it shorter"
    assert rows["loop"]["theirs"] == 100.0 and rows["loop"]["ours"] == 0.0
    assert td.compare(_data())[0]["key"] in ("loop", "first_cut")         # the biggest gap first
    text = td.measured_text(_data())
    assert text.startswith("MEASURED ON THE VIDEO FILES")
    assert "- the first picture change: theirs 1 s, ours 4 s (of 5 winners and 4 of ours): change the picture sooner." in text
    assert "Shorts that loop back to their start: theirs 100%, ours 0%" in text
    assert td.measured_text({}) == ""


def test_the_winners_pace_scales_our_cut_and_stays_in_range():
    assert td.BASE_CUT == pytest.importorskip("broll").CUT
    assert td.pace_cut(_data(), 2.8) == round(2.8 * 1.5 / 2.6, 1)      # 1.6 s
    assert td.pace_cut(_data(shot=1.6), 2.8) is None                    # already within 15%
    assert td.pace_cut(_data(shot=10.0), 2.8) == td.PACE_RANGE[0]
    assert td.pace_cut(_data(ours=1), 2.8) is None


def test_the_cut_length_of_a_job_follows_the_pace_test(monkeypatch):
    broll = pytest.importorskip("broll")
    items = [{"seconds": 30}]
    monkeypatch.delenv("BROLL_CUT", raising=False)
    usual = broll.plan_shots([(0.0, 12.0, "a")], items)
    monkeypatch.setenv("BROLL_CUT", "1.6")
    fast = broll.plan_shots([(0.0, 12.0, "a")], items)
    assert len(usual) == 4 and len(fast) == 8 and sum(s[0] for s in fast) == sum(s[0] for s in usual)
    monkeypatch.setenv("BROLL_CUT", "0.2")
    assert broll.cut_seconds() == broll.MIN_SHOT
    monkeypatch.setenv("BROLL_CUT", "fast")
    assert broll.cut_seconds() == broll.CUT


def test_measure_some_fetches_one_at_a_time_keeps_failures_and_measures_ours_from_disk(tmp_path):
    got, data = [], {}

    def fetch(vid, out_dir, seconds=None):
        got.append((vid, seconds))
        if vid == "bad":
            raise RuntimeError("Sign in to confirm")
        path = os.path.join(out_dir, f"{vid}.mp4")
        open(path, "w").close()
        return path

    def measure(path):
        assert os.path.isfile(path)
        return _m(seconds=180.0)
    theirs = [{"id": "bad", "title": "x"}, {"id": "long", "seconds": 1500, "views": 9}, {"id": "third"}]
    mine = tmp_path / "ours.mp4"
    mine.write_text("x")
    ours = [{"id": "o1", "path": str(mine)}, {"id": "gone", "path": str(tmp_path / "nope.mp4")}]
    n = td.measure_some(data, theirs, ours, log=lambda m: None, now=5, fetch_fn=fetch, measure_fn=measure)
    assert n == 2 and [g[0] for g in got] == ["bad", "long"]               # PER_RUN, in order
    assert got[1][1] == td.MEASURE_SECONDS                                  # only a long video's start
    assert "Sign in" in data["anatomy"]["bad"]["failed"] and "m" not in data["anatomy"]["bad"]
    assert data["anatomy"]["long"]["m"]["seconds"] == 1500 and data["anatomy"]["long"]["m"]["loop"] is None
    assert set(data["ours"]) == {"o1"}
    td.measure_some(data, theirs, ours, log=lambda m: None, now=6, fetch_fn=fetch, measure_fn=measure)
    assert got[-1][0] == "third" and len(got) == 3                         # the failure is not tried again
    assert td.measure_some({}, theirs, ours) == 0                           # TEARDOWN=0: the tests fetch nothing


def test_a_real_measurement_of_a_made_up_short(tmp_path):
    path = str(tmp_path / "s.mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error",
                    "-f", "lavfi", "-i", "color=c=red:s=180x320:d=2:r=15",
                    "-f", "lavfi", "-i", "color=c=blue:s=180x320:d=2:r=15",
                    "-f", "lavfi", "-i", "color=c=red:s=180x320:d=2:r=15",
                    "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0", "-pix_fmt", "yuv420p", path],
                   check=True, capture_output=True)
    m = td.measure(path)
    assert m["cuts"] == 2 and abs(m["first_cut"] - 2.0) < 0.2 and m["first_word"] is None
    assert m["loop"] is True and abs(m["seconds"] - 6.0) < 0.2


def test_the_research_pass_measures_and_the_prompt_leads_with_the_numbers(monkeypatch, tmp_path):
    monkeypatch.setenv("VIRAL_WATCH", "1")
    for i in range(5):
        vid = f"w{i:010d}"
        vr.study(object(), vid, "cricket",
                 meta={"id": vid, "url": f"https://www.youtube.com/watch?v={vid}", "title": f"Hit {i}",
                       "channel": f"C{i}", "channel_id": "UC" + str(i) * 22, "views": 10 ** 6, "seconds": 30},
                 watcher=lambda *a, n=i: vr.Study(
                     fits=True, reason="", topic=f"Topic {n}", kind="versus", angle="a", hook_pattern="h",
                     beats=["b"], devices=["d"], why="w", first_frame="f", visuals="v", text_style="t",
                     audio="a", cta="c", length_seconds=30, transcript=""))
    assert len(nr.studies_of("cricket")) == 5
    nr._save("cricket", {**_data(theirs=0, ours=4), "last_run": 0})

    class Api:
        def search(self, q, **kw):
            return []

        def channel_uploads(self, cid, n):
            return []
    monkeypatch.setattr(td, "PER_RUN", 5)
    monkeypatch.setattr(nr.kit, "ask_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    out = nr.run("cricket", object(), log=lambda m: None, now=1793184000, api=Api(),
                 fetch_fn=lambda vid, d, s=None: (open(os.path.join(d, "f.mp4"), "w").close(),
                                                  os.path.join(d, "f.mp4"))[1],
                 measure_fn=lambda p: _m())
    assert out["measured"] == 5
    text = nr.playbook_text("cricket")
    assert text.startswith("MEASURED ON THE VIDEO FILES") and "change the picture sooner" in text
    s = nr.summary("cricket")["measured"]
    assert s["theirs"] == 5 and s["ours"] == 4 and any("cut faster" in x for x in s["lines"])


def test_our_files_still_on_disk_are_offered_and_a_long_channels_shorts_are_not(tmp_path):
    ch = mc.add("cricket")
    out = tmp_path / "output"
    for vid, job, fmt in (("y1", "j1", "topic"), ("y2", "j2", "teaser"), ("y3", "j3", "topic")):
        if job != "j3":
            (out / job).mkdir(parents=True)
            (out / job / "c.mp4").write_text("x")
        with ya.use(mc.account(ch["id"])):
            ya._save_upload({"id": f"row{job}", "video_id": vid, "status": "done", "job_id": job, "file": "c.mp4", "format": fmt,
                             "title": vid, "views": 4})
    got = mc.recent_files("cricket", output_dir=str(out))
    assert [g["id"] for g in got] == ["y1"] and got[0]["path"] == str(out / "j1" / "c.mp4")
    assert mc.recent_files("music", output_dir=str(out)) == []


def test_the_pace_test_runs_only_once_the_niche_is_measured():
    ch = mc.add("cricket")
    assert mc.pace_now(ch) is None
    nr._save("cricket", _data())
    assert mc.pace_now(mc.get(ch["id"])) == td.pace_cut(_data(), td.BASE_CUT)
    assert "pace" in mc.EXPERIMENTS and set(mc.EXPERIMENTS["pace"]["arms"]) == {"ours", "rivals"}


def test_a_busy_laptop_never_marks_a_video_as_failed(tmp_path):
    data = {"anatomy": {"old": {"failed": "TimeoutExpired: Command ...", "at": 1}}}
    calls = []

    def fetch(vid, out_dir, seconds=None):
        calls.append(vid)
        p = os.path.join(out_dir, f"{vid}.mp4")
        open(p, "w").close()
        return p

    def busy(path):
        raise td.Busy("no result in 10 min")
    n = td.measure_some(data, [{"id": "old"}, {"id": "new1"}], [], log=lambda m: None, now=5, fetch_fn=fetch,
                        measure_fn=busy)
    assert n == 0 and calls == ["old"]                       # retried; the busy laptop stops the pass
    assert data["anatomy"]["old"]["failed"].startswith("TimeoutExpired") and "new1" not in data["anatomy"]
    td.measure_some(data, [{"id": "old"}, {"id": "new1"}], [], log=lambda m: None, now=6, fetch_fn=fetch,
                    measure_fn=lambda p: {"seconds": 30})
    assert data["anatomy"]["old"]["m"] == {"seconds": 30} and "m" in data["anatomy"]["new1"]
