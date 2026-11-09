"""Lyria first, ACE-Step on this PC when Lyria cannot sing (owner, 7-nov-2026). No network: the
ACE-Step API answers through a fake httpx and nothing is started."""
import base64
import json
import types as pytypes

import pytest

import ai_fallback as af
import free_song
import music_shorts as ms


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(af, "STATE_FILE", str(tmp_path / "ai_fallback.json"))
    monkeypatch.setattr(free_song.time, "sleep", lambda s: None)
    monkeypatch.setattr(free_song, "installed", lambda: True)
    monkeypatch.delenv("ACESTEP", raising=False)
    return tmp_path


class _R:
    def __init__(self, data=None, content=b"", code=200):
        self.status_code, self._d, self.content = code, data, content
        self.text = json.dumps(data) if data is not None else ""

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeAce:
    def __init__(self, fail=False, busy=0):
        self.fail, self.task, self.polls, self.busy = fail, None, 0, busy

    def get(self, u, timeout=None):
        if u.endswith("/health"):
            return _R({"data": {"status": "ok"}})
        if u.endswith("/v1/stats"):
            assert self.task is None, "asked for a song while older ones were still queued"
            n, self.busy = self.busy, max(0, self.busy - 1)
            return _R({"data": {"jobs": {"queued": n, "running": 0}}})
        assert "/v1/audio?path=" in u
        return _R(content=b"ID3" + b"\0" * 20000)

    def post(self, u, json=None, timeout=None):
        if u.endswith("/release_task"):
            self.task = json
            return _R({"data": {"task_id": "t1"}})
        self.polls += 1
        if self.polls < 2:
            return _R({"data": [{"status": 0}]})
        if self.fail:
            return _R({"data": [{"status": 2, "result": "out of memory"}]})
        return _R({"data": [{"status": 1, "result": '[{"file": "/v1/audio?path=x.mp3"}]'}]})


def _plan():
    return pytypes.SimpleNamespace(lyria_style="Lo-fi chill pop, 80 BPM, soft female vocal", title="Two A.M.",
                                   verse=["Rain on the window", "City lights so low"], pre_chorus=["Hold on"],
                                   chorus=["Two a.m. and I think of you", "Every street turns blue"])


class Lyria:
    def __init__(self, error=None):
        self.error, self.calls = error, 0
        self.interactions = self

    def create(self, model=None, input=None):
        self.calls += 1
        if self.error:
            raise self.error
        return pytypes.SimpleNamespace(output_audio=pytypes.SimpleNamespace(data=base64.b64encode(b"lyria").decode()))


def test_lyria_sings_when_it_can(tmp_path, monkeypatch):
    ace = FakeAce()
    monkeypatch.setattr(free_song, "httpx", ace)
    out = ms.sing(Lyria(), _plan(), str(tmp_path / "s.mp3"))
    assert open(out, "rb").read() == b"lyria" and ace.task is None


def test_out_of_credit_goes_to_ace_step_with_the_lyrics(tmp_path, monkeypatch):
    ace = FakeAce()
    monkeypatch.setattr(free_song, "httpx", ace)
    broke = RuntimeError("402 Your prepayment credits are depleted")
    out = ms.sing(Lyria(broke), _plan(), str(tmp_path / "s.mp3"))
    assert open(out, "rb").read().startswith(b"ID3")
    t = ace.task
    assert t["prompt"].startswith("Lo-fi chill pop") and t["audio_duration"] == 70 and t["thinking"] is False
    assert t["lyrics"].index("[Verse]") < t["lyrics"].index("[Pre-Chorus]") < t["lyrics"].index("[Chorus]")
    assert "Every street turns blue" in t["lyrics"] and t["inference_steps"] == 8


def test_older_queued_songs_are_waited_for_first(tmp_path, monkeypatch):
    ace = FakeAce(busy=3)
    monkeypatch.setattr(free_song, "httpx", ace)
    said = []
    free_song.make("pop", "[Verse]\nla", str(tmp_path / "s.mp3"), log=said.append)
    assert ace.busy == 0 and ace.task and any("older song" in s for s in said)


def test_gemini_known_down_skips_the_paid_call(tmp_path, monkeypatch):
    monkeypatch.setattr(free_song, "httpx", FakeAce())
    af._update(lambda d: d.update(gemini_down_until=int(af.time.time()) + 600))
    lyria = Lyria()
    ms.sing(lyria, _plan(), str(tmp_path / "s.mp3"))
    assert lyria.calls == 0


def test_a_policy_refusal_still_writes_another_song(tmp_path, monkeypatch):
    ace = FakeAce()
    monkeypatch.setattr(free_song, "httpx", ace)
    with pytest.raises(RuntimeError, match="policy"):
        ms.sing(Lyria(RuntimeError("Request blocked for an unspecified policy reason")), _plan(),
                str(tmp_path / "s.mp3"))
    assert ace.task is None


def test_both_failing_keeps_both_reasons_and_off_switch(tmp_path, monkeypatch):
    monkeypatch.setattr(free_song, "httpx", FakeAce(fail=True))
    with pytest.raises(RuntimeError) as e:
        ms.sing(Lyria(RuntimeError("503 UNAVAILABLE")), _plan(), str(tmp_path / "s.mp3"))
    assert "503" in str(e.value) and "out of memory" in str(e.value)
    monkeypatch.setenv("ACESTEP", "0")
    with pytest.raises(RuntimeError, match="503"):
        ms.sing(Lyria(RuntimeError("503 UNAVAILABLE")), _plan(), str(tmp_path / "s.mp3"))


def test_the_api_gets_no_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("META_TOKEN", "tok")
    env = free_song._child_env()
    assert "OPENAI_API_KEY" not in env and "META_TOKEN" not in env
    assert env["ACESTEP_DEVICE"] == "cpu" and env["ACESTEP_API_PORT"] == "8001"
