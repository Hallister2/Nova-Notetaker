from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from app.audio.device_manager import AudioDevice
from app.core import audio_profiles
from app.core.preflight import run_capture_preflight_checks, summarize_preflight


class AudioProfilesTests(TestCase):
    def test_save_and_find_audio_profile(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "audio_profiles.json"
            with patch.object(audio_profiles, "AUDIO_PROFILES_PATH", path):
                profile = audio_profiles.save_audio_profile("Device A", 96000, 8)
                self.assertEqual(profile.detail, "96000 Hz / 8 ch")
                loaded = audio_profiles.find_audio_profile("device a")
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded.sample_rate, 96000)
                self.assertEqual(loaded.channels, 8)


class PreflightTests(TestCase):
    def test_preflight_allows_muted_mic_and_disabled_whisper(self) -> None:
        with TemporaryDirectory() as temp_dir:
            checks = run_capture_preflight_checks(
                settings={"audio": {}, "transcription": {"enabled": False}, "ai": {"provider": "unknown"}},
                meetings_root=Path(temp_dir),
                mic_device=None,
                loopback_device=AudioDevice("Loop", 1, "loopback", channels=2, sample_rate=48000),
                capture_mic=False,
                mic_channels=1,
                loopback_channels=2,
                check_ai=False,
            )
        passed, lines = summarize_preflight(checks)
        self.assertTrue(any("WhisperLive: Disabled" in line for line in lines))
        self.assertTrue(passed)
        self.assertTrue(any(check.name == "Mic open" and check.passed for check in checks))
