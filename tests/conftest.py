import os
import sys

# Make the repo root importable so tests can import the app modules directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Tests always run the app in self-host (BYOK) mode. app.py freezes
# BILLING_ENABLED at import time and load_dotenv never overrides an existing
# variable, so this must be set here — before any test module imports app — or
# the suite's behavior would depend on the developer's personal .env.
os.environ["BILLING_ENABLED"] = "0"
# No test, and no app a test starts as a subprocess (test_mcp_stdio), may run
# the local Autopilot loop: it acts on the real output/ files and YouTube token.
os.environ["AUTOPILOT_LOCAL"] = "0"

import pytest


@pytest.fixture(autouse=True)
def _private_channel_files(tmp_path, monkeypatch):
    """The never-repeat record, Autopilot settings, YouTube token and report
    live in output/ for the real app; a test that posts a job (or records a
    moment) must never write the developer's own copies (one run saved an
    empty Autopilot look over the real one, 8-oct-2026)."""
    import autopilot_local
    import used_moments
    import what_works
    import youtube_account
    monkeypatch.setattr(used_moments, "PATH", str(tmp_path / "used_moments.json"))
    monkeypatch.setattr(autopilot_local, "SETTINGS_FILE", str(tmp_path / "autopilot.json"))
    monkeypatch.setattr(autopilot_local, "LAST_SETTINGS_FILE", str(tmp_path / "last_settings.json"))
    monkeypatch.setattr(what_works, "REPORT_FILE", str(tmp_path / "what_works.json"))
    monkeypatch.setattr(youtube_account, "TOKEN_FILE", str(tmp_path / "youtube_token.json"))
    monkeypatch.setattr(youtube_account, "UPLOADS_FILE", str(tmp_path / "uploads.json"))
    import comment_replies
    import post_queue
    monkeypatch.setattr(post_queue, "STATE_FILE", str(tmp_path / "post_queue.json"))
    monkeypatch.setattr(comment_replies, "STATE_FILE", str(tmp_path / "comments.json"))
    import rivals
    monkeypatch.setattr(rivals, "STATE_FILE", str(tmp_path / "rivals.json"))
    import telegram_notify
    monkeypatch.setattr(telegram_notify, "STATE_FILE", str(tmp_path / "telegram.json"))
    import learning
    monkeypatch.setattr(learning, "STATE_FILE", str(tmp_path / "learning.json"))
