from __future__ import annotations

from pathlib import Path
from unittest import TestCase

from app.audio.capture_service import CaptureConfig, CaptureService
from app.audio.device_manager import AudioDevice
from app.ui.tabs.capture_tab import CaptureTabMixin


class CaptureServiceTests(TestCase):
    def test_loopback_channel_candidates_try_requested_then_safe_fallbacks(self) -> None:
        self.assertEqual(CaptureService._loopback_channel_candidates(8), [8, 2, 1])
        self.assertEqual(CaptureService._loopback_channel_candidates(2), [2, 1])
        self.assertEqual(CaptureService._loopback_channel_candidates(1), [1, 2])
        self.assertEqual(CaptureService._loopback_channel_candidates(0), [2, 1])

    def test_capture_channels_preserve_loopback_device_channels(self) -> None:
        loopback = AudioDevice(
            name="SteelSeries Sonar - Gaming [Loopback]",
            index=58,
            kind="loopback",
            channels=8,
            sample_rate=96000,
        )
        self.assertEqual(CaptureTabMixin._capture_channels(loopback, default=2, max_channels=None), 8)
        self.assertEqual(CaptureTabMixin._capture_channels(loopback, default=2, max_channels=2), 2)

    def test_emit_level_initializes_throttle_state(self) -> None:
        levels: list[tuple[str, float]] = []
        service = CaptureService(
            config=CaptureConfig(
                meeting_folder=Path("."),
                mic_device_index=None,
                loopback_device_index=None,
            ),
            on_status=lambda _message: None,
            on_level=lambda source, level: levels.append((source, level)),
        )
        service._emit_level("mic", 0.5)
        self.assertEqual(levels, [("mic", 0.5)])
        self.assertIn("mic", service.last_level_emit)
