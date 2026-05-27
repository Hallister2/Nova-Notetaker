from __future__ import annotations

from unittest import TestCase

from app.audio.capture_service import CaptureService


class CaptureServiceTests(TestCase):
    def test_loopback_channel_candidates_try_requested_then_safe_fallbacks(self) -> None:
        self.assertEqual(CaptureService._loopback_channel_candidates(8), [8, 2, 1])
        self.assertEqual(CaptureService._loopback_channel_candidates(2), [2, 1])
        self.assertEqual(CaptureService._loopback_channel_candidates(1), [1, 2])
        self.assertEqual(CaptureService._loopback_channel_candidates(0), [2, 1])
