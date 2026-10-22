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
# No test searches Pexels/Pixabay for real once the owner's keys are in .env
# (broll.background_for); footage tests turn it back on with fakes.
os.environ["STOCK_FOOTAGE"] = "0"
os.environ["OPENVERSE"] = "0"      # keyless, so it would answer from a test for real
os.environ["WIKIPEDIA_PHOTOS"] = "0"   # the same for Wikipedia's lead pictures
os.environ["TRENDS"] = "0"         # trends.py searches YouTube for real
os.environ["VIDEO_QA"] = "0"       # upload tests pass fake paths; test_video_qa turns it on
# Caption timing from the voice's pauses only: no Whisper model load per test.
os.environ["EXACT_CAPTIONS"] = "pauses"
os.environ["VOICE_ENGINE"] = "gemini"   # the free voice is a network service: tests fake ai_take.speak
os.environ["LOCAL_VOICE"] = "0"         # OmniVoice is installed on this laptop: a test would load the real model
os.environ["PARALLAX"] = "0"            # so is the depth model: history render tests would run it for real

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
    import my_channels
    import player_photo
    monkeypatch.setattr(my_channels, "STATE_FILE", str(tmp_path / "my_channels.json"))
    monkeypatch.setattr(my_channels, "CHANNELS_DIR", str(tmp_path / "channels"))
    monkeypatch.setattr(player_photo, "CACHE_FILE", str(tmp_path / "player_photos.json"))
    import engage
    monkeypatch.setattr(engage, "MAIN_STATE", str(tmp_path / "engage.json"))
    monkeypatch.setattr(youtube_account, "QUOTA_FILE", str(tmp_path / "yt_quota.json"))
    import reminders
    monkeypatch.setattr(reminders, "STATE_FILE", str(tmp_path / "reminders.json"))
    import stock_media
    monkeypatch.setattr(stock_media, "SEARCH_FILE", str(tmp_path / "stock_search.json"))
    monkeypatch.setattr(stock_media, "USED_FILE", str(tmp_path / "stock_used.json"))
    monkeypatch.setattr(stock_media, "CACHE_DIR", str(tmp_path / "stock_cache"))
    monkeypatch.setattr(stock_media, "OPENVERSE_FILE", str(tmp_path / "openverse_calls.json"))
    monkeypatch.setattr(stock_media, "LIMITS_FILE", str(tmp_path / "stock_limits.json"))
    import free_voice
    monkeypatch.setattr(free_voice, "STATE_FILE", str(tmp_path / "free_voice.json"))
    monkeypatch.setattr(free_voice, "PAUSE", 0)
