"""Talking characters (owner, 10-nov-2026: lifelike talking babies and animals, talking food and organs, and a script
with a hook, a well-organised story and a curiosity ending). The writers' room runs on a fake AI and the video on a
fake fal that returns small real mp4 files, so the checks, the revision loop, the joining and the budget run for real;
nothing is uploaded and nothing is paid."""
import json
import os
import subprocess

import pytest

import talkies as tk
import toon_shorts as ts


def _ep(**kw):
    def L(sp, text, how="annoyed"):
        return tk.Line(speaker=sp, text=text, delivery=how)
    chars = [tk.Character(key="billo", name="Billo", what="a real ginger tabby cat", look="orange fur", voice="sassy"),
             tk.Character(key="sheru", name="Sheru", what="a real desi dog", look="tan fur", voice="deep")]
    shots = [
        tk.Shot(who=["billo"], setting="a Lahore kitchen at night", action="Billo sits inside the open fridge "
                "holding a stolen egg, the fridge light on her face.", lines=[L("billo", "Aaj anda chor pakda jayega.")]),
        tk.Shot(who=["billo", "sheru"], setting="the lounge", action="Sheru walks in with yolk on his nose and "
                "freezes when Billo turns around slowly.", lines=[L("sheru", "Main to bas pehra de raha tha."),
                                                                  L("billo", "Naak pe anda leke?", "deadpan")]),
        tk.Shot(who=["sheru"], setting="the lounge", action="Sheru looks straight at the camera as footsteps come "
                "closer and the kitchen light switches on.", lines=[L("sheru", "Ab tum batao... asli chor kaun hai?", "whisper")]),
    ]
    data = dict(title="Fridge ka anda chor kaun?", hook_caption="ANDA CHOR!", premise="Eggs vanish from the fridge.",
                point="Every house has a snack thief.", characters=chars, shots=shots, twist="Sheru was the thief.",
                ending="verdict", ending_note="Who is the real thief?", question="Chor kaun? Billo ya Sheru?")
    data.update(kw)
    return tk.Talkie(**data)


def test_a_good_script_passes_and_broken_ones_are_named():
    ep = _ep()
    assert tk.problems(ep) == []
    assert tk.MIN_SECONDS <= tk.total_seconds(ep) <= tk.MAX_SECONDS
    bad = _ep(ending="moral")
    bad.shots[0].lines[0].text = "Assalam o alaikum dosto aaj main aap ko batati hoon ek baat"
    bad.shots[1].who = ["billo", "sheru", "mithu"]
    bad.shots[2].lines = []
    found = " | ".join(tk.problems(bad))
    for part in ("ending 'moral'", "hook line has 12 words", "stale phrases", "shot 2 shows 3 characters", "mithu",
                 "last shot has no line"):
        assert part in found


def test_the_shot_prompt_carries_references_dialogue_and_no_music():
    ep = _ep()
    p = tk.shot_prompt(ep, 1, "pet")
    assert p.index("picture 1 is Billo") < p.index("picture 2 is Sheru")
    assert '"Main to bas pehra de raha tha."' in p and "Hindi-Urdu" in p and "no background music" in p
    assert "Photorealistic" in p and "first second" not in p
    assert "first second" in tk.shot_prompt(ep, 0, "pet")
    assert "Hyper-realistic" in tk.shot_prompt(ep, 0, "organ")


def test_the_recurring_stars_keep_their_fixed_look():
    ep = _ep()
    ep.characters[0].look = "a purple cat"
    tk.tidy(ep, "pet")
    assert ep.characters[0].look == tk.RECURRING["billo"]["look"]


class FakeRoom:
    """Answers the writers' room by schema; the critic is harsh on the first two drafts."""

    def __init__(self, check_ok=True):
        self.prompts, self.critic_calls, self.check_ok = [], 0, check_ok

    def __call__(self, client, schema, prompt, best=True):
        self.prompts.append((schema.__name__, prompt))
        if schema is tk.Pitches:
            return tk.Pitches(pitches=[tk.Pitch(premise=f"story {i}", hook_line="Fridge se anda ghaib!",
                                                hook_picture="a cat in a fridge", twist="the dog did it",
                                                ending="verdict", ending_line="Chor kaun?") for i in range(1, 4)])
        if schema is tk.Rank:
            return tk.Rank(order=[2, 1, 3], why="best hook")
        if schema is tk.Talkie:
            return _ep()
        if schema is tk.Scores:
            self.critic_calls += 1
            low = self.critic_calls <= 2
            return tk.Scores(hook=6 if low else 9, clarity=8, story=8, dialogue=8, ending=7 if low else 9,
                             originality=8, visual=8, weakest="the hook is soft", fixes=["shot 1 line: sharper"])
        if schema is tk.Check:
            ok = self.check_ok.pop(0) if isinstance(self.check_ok, list) else self.check_ok
            return tk.Check(ok=ok, problems=[] if ok else ["a brand is named"])
        raise AssertionError(schema)


def test_the_writers_room_ranks_writes_two_and_revises_the_best_to_the_bar(monkeypatch):
    room = FakeRoom()
    monkeypatch.setattr(tk, "_ask", room)
    ep, sc = tk.write(object(), "pet", log=lambda s: None)
    names = [n for n, _ in room.prompts]
    # Two drafts, one revision to the bar, then the dialogue polish.
    assert names[:2] == ["Pitches", "Rank"] and names.count("Talkie") == 4 and names[-1] == "Check"
    first_draft = next(p for n, p in room.prompts if n == "Talkie")
    assert "story 2" in first_draft                       # the editor's first pick is written first
    assert "COMEDY CRAFT" in first_draft and "THE SERIES CAST" in first_draft
    revision, polish = [p for n, p in room.prompts if n == "Talkie"][-2:]
    assert "REVISE THE LAST VERSION" in revision and "the hook is soft" in revision and "sharper" in revision
    assert "dialogue doctor" in polish and "LOCKED" in polish
    assert tk.passes(sc) and sc.hook == 9


def test_the_dialogue_polish_changes_only_the_lines(monkeypatch):
    ep = _ep()
    polished = _ep(title="something else")
    polished.shots[1].action = "a different action"
    polished.shots[1].lines[0].text = "Pehra? Main to sirf soongh raha tha."
    monkeypatch.setattr(tk, "_ask", lambda *a, **k: polished.model_copy(deep=True))
    out = tk.punch_up(object(), "pet", ep)
    assert out.shots[1].lines[0].text == "Pehra? Main to sirf soongh raha tha."
    assert out.title == ep.title and out.shots[1].action == ep.shots[1].action
    reshaped = _ep()
    reshaped.shots[1].lines.pop()
    monkeypatch.setattr(tk, "_ask", lambda *a, **k: reshaped)
    assert tk.punch_up(object(), "pet", ep) is None


def test_a_script_that_fails_the_safety_check_is_never_filmed(monkeypatch):
    monkeypatch.setattr(tk, "_ask", FakeRoom(check_ok=False))
    with pytest.raises(RuntimeError, match="a brand is named"):
        tk.write(object(), "pet", log=lambda s: None)


def test_a_safety_note_gets_one_revision_before_the_script_is_dropped(monkeypatch):
    room = FakeRoom(check_ok=[False, True])
    monkeypatch.setattr(tk, "_ask", room)
    ep, _sc = tk.write(object(), "pet", log=lambda s: None)
    revision = [p for n, p in room.prompts if n == "Talkie"][-1]
    assert "SAFETY (must be fixed): a brand is named" in revision
    assert "guddu = Guddu" in revision or "THE SERIES CAST" in revision
    assert [n for n, _ in room.prompts].count("Check") == 2


def test_organ_scripts_are_checked_for_mainstream_health_facts(monkeypatch):
    room = FakeRoom()
    monkeypatch.setattr(tk, "_ask", room)
    tk.write(object(), "organ", log=lambda s: None)
    check = room.prompts[-1][1]
    assert "mainstream advice" in check and "medicine" in check


def _mp4(path, secs=2):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"testsrc=size=360x640:rate=24:d={secs}", "-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", path], check=True, capture_output=True)
    return path


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setattr(tk, "STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("TALKIES_UPSCALE", "0")
    monkeypatch.delenv("TALKIES_SECONDS_PER_DAY", raising=False)
    monkeypatch.delenv("TALKIES_VIDEO_RES", raising=False)
    from PIL import Image

    def image(client, prompt, out, **kw):
        Image.new("RGB", (64, 64), (240, 140, 40)).save(out)
        return out
    monkeypatch.setattr(ts, "_image", image)
    calls = []

    def video(endpoint, payload, out, sleep=None):
        calls.append((endpoint, payload))
        return _mp4(out)
    monkeypatch.setattr(tk, "fal_video", video)
    monkeypatch.setattr(tk, "fal_upload", lambda path: "https://fal.media/" + os.path.basename(path))
    work = tmp_path / "work"
    work.mkdir()
    return calls, work


def test_shots_are_filmed_joined_and_made_1080x1920_within_the_budget(studio):
    calls, work = studio
    ep = _ep()
    canvas, sound, times, wavs = tk.make_video(object(), "pet", ep, str(work), log=lambda s: None)
    assert len(calls) == 3 and len(times) == 3 and len(wavs) == 3
    endpoint, payload = calls[1]
    assert endpoint == tk.VIDEO_MODEL and payload["resolution"] == "360p" and payload["aspect_ratio"] == "9:16"
    assert payload["image_urls"] == ["https://fal.media/billo.png", "https://fal.media/sheru.png"]
    assert payload["duration"] == tk.seconds_of(ep.shots[1])
    size = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", canvas], capture_output=True, text=True).stdout.strip()
    assert size == "1080,1920" and os.path.isfile(sound)
    day = next(iter(json.load(open(tk._spend_file())).values()))
    assert day["clips"] == 3 and day["seconds"] == tk.total_seconds(ep)
    assert abs(day["usd"] - day["seconds"] * tk.PRICE["360p"]) < 0.001
    # The recurring stars' pictures are kept for the next video.
    assert os.path.isfile(os.path.join(tk.cast_dir(), "billo.png"))


def test_the_daily_cap_stops_before_anything_is_paid(studio, monkeypatch):
    calls, work = studio
    monkeypatch.setenv("TALKIES_SECONDS_PER_DAY", "10")
    with pytest.raises(RuntimeError, match="budget"):
        tk.make_video(object(), "pet", _ep(), str(work), log=lambda s: None)
    assert calls == []


def test_an_empty_fal_account_is_said_plainly():
    e = tk._fal_error(403, '{"detail": "User is locked. Reason: Exhausted balance."}')
    assert "no credit" in str(e)
    assert "no credit" not in str(tk._fal_error(422, "bad prompt"))


def test_a_part2_promise_is_kept_next_with_the_same_characters(monkeypatch, tmp_path):
    monkeypatch.setattr(tk, "STATE_DIR", str(tmp_path / "state"))
    part1 = _ep(ending="part2", ending_note="Who ate the eggs?")
    tk.record(part1, "pet", 1)
    row = tk.open_part2(tk.history())
    assert row and row["n"] == 1
    room = FakeRoom()
    monkeypatch.setattr(tk, "_ask", room)

    def changed(*a, **k):
        ep = _ep(ending="part2")
        ep.characters[1].look = "a purple dog"         # the writer drifted: part 1's look must win
        return ep
    room_talkie = changed
    monkeypatch.setattr(tk, "draft", lambda client, fmt, p, revise="": room_talkie())
    ep, _sc = tk.write(object(), "pet", follow=tk.Talkie(**row["script"]), log=lambda s: None)
    pitch_prompt = room.prompts[0][1]
    assert "PART 2 of the last episode" in pitch_prompt and "Who ate the eggs?" in pitch_prompt
    assert ep.characters[1].look == "tan fur" and ep.ending != "part2" and "(Part 2)" in ep.title
    tk.record(ep, "pet", 2, follows=1)
    assert tk.open_part2(tk.history()) is None


def test_a_sentence_in_the_ending_field_becomes_the_pitchs_key(monkeypatch):
    monkeypatch.setattr(tk, "_ask", lambda *a, **k: _ep(ending="part 2: billo batayegi chooze kahan mile",
                                                       ending_note=""))
    p = tk.Pitch(premise="x", hook_line="y", hook_picture="z", twist="t", ending="cliffhanger", ending_line="e")
    ep = tk.draft(object(), "pet", p)
    assert ep.ending == "part2" and "chooze" in ep.ending_note
    monkeypatch.setattr(tk, "_ask", lambda *a, **k: _ep(ending="as billo wins, a cloud dims the sun"))
    assert tk.draft(object(), "pet", p).ending == "cliffhanger"


def test_a_hook_copied_from_the_brief_is_sent_back():
    ep = _ep()
    ep.shots[0].lines[0].text = "Tum roz raat do baje mujhe jagate ho."
    assert any("copies an example" in p for p in tk.problems(ep))
    assert "Tum roz raat" not in tk.HOOKS and '"' not in tk.HOOKS


def test_a_refused_picture_is_drawn_on_fal_with_gentler_words(monkeypatch, tmp_path):
    monkeypatch.setattr(tk, "STATE_DIR", str(tmp_path / "state"))

    def refuse(client, prompt, out, **kw):
        raise RuntimeError('OpenAI images 400: {"code": "moderation_block"}')
    monkeypatch.setattr(ts, "_image", refuse)
    asked = []

    def fal_image(prompt, out, sleep=None):
        asked.append(prompt)
        open(out, "wb").write(b"png")
        return out
    monkeypatch.setattr(tk, "fal_image", fal_image)
    c = tk.Character(key="eyes", name="Aankhen", what="a giant cartoon eye", look="red bags", voice="dramatic")
    path = tk.ref_picture(object(), "organ", c, str(tmp_path))
    assert os.path.isfile(path) and "no blood" in asked[0] and "giant cartoon eye" in asked[0]


def test_each_series_has_its_own_shapes_and_lengths():
    joke = tk.Talkie(**{**_ep().model_dump(), "shape": "joke"})
    found = " | ".join(tk.problems(joke))
    assert "the joke shape takes 1-1" in found
    one = tk.Talkie(**{**_ep().model_dump(), "shape": "joke"})
    one.shots = [tk.Shot(who=["billo", "sheru"], setting="a kitchen", action="Sheru asks Billo something with a "
                         "straight face while she licks her paw.", lines=[
                             tk.Line(speaker="sheru", text="Billo, anda kahan gaya?", delivery="calm"),
                             tk.Line(speaker="billo", text="Murgi se poocho, main to vegetarian hoon.",
                                     delivery="deadpan")])]
    assert tk.problems(one) == []
    assert tk.shape_of("baby", "nope")[0] == "joke" and tk.shape_of("food", "court")[0] == "court"
    assert "interview" in tk.shapes_text("baby") and "office" in tk.shapes_text("organ")


def test_rishta_comedy_is_allowed_and_food_romance_is_the_owners_switch(monkeypatch):
    assert "rishta" in tk.rules_for("baby") and "love affairs" in tk.rules_for("baby")
    monkeypatch.delenv("TALKIES_FOOD_ROMANCE", raising=False)
    assert "love affairs" in tk.rules_for("food")
    monkeypatch.setenv("TALKIES_FOOD_ROMANCE", "1")
    assert "innocent filmi romance" in tk.rules_for("food") and "love affairs" not in tk.rules_for("food")
    assert "love affairs" in tk.rules_for("baby")


def test_baby_jokes_come_from_a_bank_and_the_editor_picks_the_best(monkeypatch):
    jokes = [tk.Joke(asker="ammi", setup=f"Setup {i}?", punchline=f"Punch {i}", mechanism="m") for i in range(1, 13)]
    asked = []

    def ask(client, schema, prompt, best=True):
        asked.append(schema.__name__)
        if schema is tk.Jokes:
            assert "12 DIFFERENT" in prompt and "grown-up worry" in prompt
            return tk.Jokes(jokes=jokes)
        if schema is tk.JokePick:
            return tk.JokePick(best=[7, 2, 9], why="funniest")
        raise AssertionError(schema)
    monkeypatch.setattr(tk, "_ask", ask)
    one = tk.joke_pitch(object(), "baby", "joke", log=lambda s: None)
    assert one.shape == "joke" and one.hook_line == "Setup 7?" and one.ending_line == "Punch 7"
    three = tk.joke_pitch(object(), "baby", "interview", log=lambda s: None)
    # The best answer goes last: it ends the video.
    assert three.hook_line == "Setup 2?" and three.ending_line == "Punch 7" and "word for word" in three.premise
    assert asked == ["Jokes", "JokePick", "Jokes", "JokePick"]


def test_the_picked_jokes_go_into_the_script_word_for_word(monkeypatch):
    jokes = [tk.Joke(asker="Abbu", setup="Beta, remote kahan hai?", punchline="Kiraye pe diya hai, Abbu.",
                     mechanism="savage")]
    jp = tk.JokePitch(shape="joke", premise="p", hook_line=jokes[0].setup, hook_picture="x", twist="t",
                      ending="reveal", ending_line=jokes[0].punchline, jokes=jokes)
    scene = tk.Talkie(**{**_ep().model_dump(), "shape": "joke"})
    scene.characters = [tk.Character(key="guddu", name="Guddu", what="a baby", look="kurta", voice="v"),
                        tk.Character(key="abbu", name="Abbu", what="a father", look="glasses", voice="v")]
    scene.shots = [tk.Shot(who=["abbu"], setting="a lounge", action="Abbu searches the sofa cushions while Guddu "
                           "sits calmly holding two remotes.", lines=[
                               tk.Line(speaker="abbu", text="Something else", delivery="annoyed"),
                               tk.Line(speaker="guddu", text="Writer's own line", delivery="smug")])]
    out = tk.with_jokes(scene, jp)
    assert [(l.speaker, l.text) for l in out.shots[0].lines] == [("abbu", "Beta, remote kahan hai?"),
                                                                ("guddu", "Kiraye pe diya hai, Abbu.")]
    assert out.shots[0].who == ["abbu", "guddu"] and out.shots[0].lines[1].delivery == "smug"
    assert tk.problems(out) == []
    # A scene with the wrong number of shots cannot carry the jokes.
    assert tk.with_jokes(_ep(), jp) is None
    # A caption that tells the joke before it is told is sent back.
    out.hook_caption = "Remote kiraye pe?"
    assert any("gives away the punchline" in p for p in tk.problems(out))


def test_formats_take_turns():
    rows = [{"format": "pet"}, {"format": "baby"}, {"format": "food"}]
    # Pet is off by default (owner, 10-nov-2026); it comes back only when TALKIES_FORMATS names it.
    assert tk.next_format(rows) == "organ"
    assert tk.next_format(rows + [{"format": "organ"}]) == "baby"
    assert tk.next_format([]) == "baby"


def test_name_tags_hook_caption_and_part2_promise():
    ep = _ep(ending="part2")
    ev = "\n".join(tk.text_events(ep, [(0.0, 6.0), (6.0, 13.0), (13.0, 19.0)], 19.0))
    assert "ANDA CHOR!" in ev and "BILLO" in ev and "SHERU" in ev and "PART 2 KAL!" in ev
