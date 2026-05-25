from __future__ import annotations

import unittest

from app.intelligence.note_hints import build_note_hints


class NoteHintsTests(unittest.TestCase):
    def test_build_note_hints_extracts_direct_requests_and_dates(self) -> None:
        transcript = (
            "## Meeting\n\n"
            "Chad, please confirm whether rollback steps are included. "
            "Maya will post an update by next Tuesday. "
            "The review is Monday, June 17."
        )

        hints = build_note_hints(transcript)

        self.assertIn("Owner: Chad", hints)
        self.assertIn("Owner: Maya", hints)
        self.assertIn("next Tuesday", hints)
        self.assertIn("Monday, June 17", hints)


if __name__ == "__main__":
    unittest.main()
