from __future__ import annotations

import unittest

from app.transcription.transcript_cleanup import reduce_cross_bleed, reduce_cross_bleed_for_profile
from app.transcription.whisperlive_client import TranscriptionResult


class TranscriptCleanupTests(unittest.TestCase):
    def test_reduce_cross_bleed_removes_meeting_audio_from_you_track(self) -> None:
        results = [
            TranscriptionResult(
                source="You",
                text=(
                    "In today's video, I'm going to teach you how to make a test call in Microsoft Teams. "
                    "So am I hearing this right? You need that report by June 5th."
                ),
                success=True,
            ),
            TranscriptionResult(
                source="Meeting",
                text="In today's video, I'm going to teach you how to make a test call in Microsoft Teams.",
                success=True,
            ),
        ]

        cleaned, warnings = reduce_cross_bleed(results)

        you_text = next(result.text for result in cleaned if result.source == "You")
        self.assertNotIn("today's video", you_text)
        self.assertIn("report by June 5th", you_text)
        self.assertTrue(warnings)

    def test_reduce_cross_bleed_removes_partial_overlapping_phrase(self) -> None:
        results = [
            TranscriptionResult(
                source="You",
                text=(
                    "The authentication process is acting up. "
                    "I will send the report by March 31st."
                ),
                success=True,
            ),
            TranscriptionResult(
                source="Meeting",
                text=(
                    "Yes, we are making progress, but there are pressing issues. "
                    "The authentication process is acting up and users are experiencing logon failures."
                ),
                success=True,
            ),
        ]

        cleaned, warnings = reduce_cross_bleed(results)

        you_text = next(result.text for result in cleaned if result.source == "You")
        self.assertNotIn("authentication process", you_text)
        self.assertIn("report by March 31st", you_text)
        self.assertTrue(warnings)

    def test_debug_raw_profile_skips_cleanup(self) -> None:
        results = [
            TranscriptionResult("You", "The authentication process is acting up.", True),
            TranscriptionResult("Meeting", "The authentication process is acting up.", True),
        ]

        cleaned, warnings = reduce_cross_bleed_for_profile(results, "debug_raw")

        self.assertEqual(cleaned[0].text, results[0].text)
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
