"""Retry behaviour of the Gemini scoring/detail stage.

Prod (22-jul-2026) lost 3 jobs to Gemini answering 200 with an empty body.
That raises while parsing, not while calling, so it used to escape the retry
loop and kill the job on the first blip.
"""
import types
import pytest

# main pulls in cv2/torch/mediapipe at import time; the minimal CI env lacks
# them, so skip there. Runs fully in the container/local where deps exist.
main = pytest.importorskip("main")


class _FakeResponse:
    def __init__(self, parsed=None):
        self.parsed = parsed
        self.candidates = []
        self.usage_metadata = None

    @property
    def text(self):
        return "" if self.parsed is None else "{}"


class _FakeModels:
    """Returns an empty body for the first `blips` calls, then a good one."""

    def __init__(self, blips, payload=None):
        self.blips = blips
        self.calls = 0
        self.payload = payload if payload is not None else {"windows": [{"id": "w0", "score": 90}]}

    def generate_content(self, **kwargs):
        self.calls += 1
        if self.calls <= self.blips:
            return _FakeResponse(parsed=None)
        return _FakeResponse(parsed=self.payload)


def _client(models):
    return types.SimpleNamespace(models=models)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(main.time, "sleep", lambda *_: None)


def test_recovers_from_a_single_empty_body(monkeypatch):
    models = _FakeModels(blips=1)
    parsed, _cost = main._run_gemini_stage(_client(models), "m", "prompt", object)
    assert models.calls == 2
    assert parsed["windows"][0]["score"] == 90


def test_recovers_from_two_consecutive_blips():
    models = _FakeModels(blips=2)
    parsed, _cost = main._run_gemini_stage(_client(models), "m", "prompt", object)
    assert models.calls == 3
    assert parsed["windows"]


def test_gives_up_after_three_attempts():
    models = _FakeModels(blips=99)
    with pytest.raises(Exception) as exc:
        main._run_gemini_stage(_client(models), "m", "prompt", object)
    assert models.calls == 3
    assert "empty response body" in str(exc.value)


def test_non_transient_errors_are_not_retried():
    class _Boom:
        calls = 0

        def generate_content(self, **kwargs):
            _Boom.calls += 1
            raise ValueError("400 INVALID_ARGUMENT: bad request")

    with pytest.raises(ValueError):
        main._run_gemini_stage(_client(_Boom()), "m", "prompt", object)
    assert _Boom.calls == 1


OUT_OF_CREDIT = ("402 RESOURCE_EXHAUSTED. {'error': {'code': 402, 'message': 'Your prepayment credits are "
                 "depleted. Please go to AI Studio at https://ai.studio/projects to manage your project and billing.'")


def test_out_of_credit_is_not_retried_and_the_check_says_so(monkeypatch):
    # 7-nov-2026: every channel stopped on this answer, and the system check called it a passing quota.
    class _Broke:
        calls = 0

        def generate_content(self, **kwargs):
            _Broke.calls += 1
            raise RuntimeError(OUT_OF_CREDIT)

    with pytest.raises(RuntimeError):
        main._run_gemini_stage(_client(_Broke()), "m", "prompt", object)
    assert _Broke.calls == 1

    import system_check
    from google import genai
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(genai, "Client", lambda **kw: _client(_Broke()))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    row = system_check.gemini()
    assert row["status"] == "error" and "credits" in str(row)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")                 # the backup stands in: a warning only
    row = system_check.gemini()
    assert row["status"] == "warn" and "OpenAI" in str(row)
    assert not system_check.out_of_credit("429 RESOURCE_EXHAUSTED: You exceeded your current quota")


def test_succeeds_without_retrying_when_the_first_call_is_fine():
    models = _FakeModels(blips=0)
    main._run_gemini_stage(_client(models), "m", "prompt", object)
    assert models.calls == 1


class _BlockedResponse:
    """Mimics the real prod shape: 200, empty candidates, block_reason set."""
    text = ""
    candidates = []
    usage_metadata = None

    class _PF:
        class _Reason:
            name = "PROHIBITED_CONTENT"
        block_reason = _Reason()

    prompt_feedback = _PF()


def test_policy_block_fails_fast_without_retrying():
    # Prod 23-jul-2026: PROHIBITED_CONTENT is deterministic — 3 retries just
    # burned quota and reported a misleading "empty response body".
    class _Models:
        calls = 0

        def generate_content(self, **kwargs):
            _Models.calls += 1
            return _BlockedResponse()

    import gemini_worker
    with pytest.raises(gemini_worker.GeminiBlockedError) as exc:
        main._run_gemini_stage(_client(_Models()), "m", "prompt", object)
    assert _Models.calls == 1
    assert "PROHIBITED_CONTENT" in str(exc.value)


def test_blocked_finish_reason_also_raises():
    import gemini_worker

    class _Cand:
        class _FR:
            name = "SAFETY"
        finish_reason = _FR()
        content = None

    class _Resp:
        prompt_feedback = None
        candidates = [_Cand()]

    with pytest.raises(gemini_worker.GeminiBlockedError):
        gemini_worker.raise_if_blocked(_Resp())


def test_clean_response_is_not_flagged_as_blocked():
    import gemini_worker

    class _Resp:
        prompt_feedback = None
        candidates = []

    gemini_worker.raise_if_blocked(_Resp())  # must not raise
