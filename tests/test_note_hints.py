from __future__ import annotations

from unittest import TestCase

from app.intelligence.note_hints import build_note_hints


class NoteHintTests(TestCase):
    def test_ignores_noisy_action_fragments(self) -> None:
        transcript = "Bethes will say, okay, WS does a match. Chad will test the OneDrive policy."

        hints = build_note_hints(transcript)

        self.assertNotIn("Bethes", hints)
        self.assertIn("Chad", hints)
        self.assertIn("test the OneDrive policy", hints)
