from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from app.intelligence.insights import build_insights_from_notes, read_insights_json, write_insights_json


class InsightsTests(TestCase):
    def test_builds_structured_insights_from_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            notes_path = Path(temp_dir) / "notes.md"
            notes_path.write_text(
                "\n".join(
                    [
                        "## Action Items",
                        "- Owner: Maya; Task: Send status update; Due: Friday; Source: Meeting Audio; Confidence: High",
                        "- Owner: Unknown; Task: Check export styling; Due: Unknown; Source: Meeting Audio; Confidence: Low",
                        "## Key Decisions",
                        "- Keep orange accent for this release",
                        "## Important Dates",
                        "- Date: Friday; Context: Status update due; Source: Meeting Audio; Confidence: High",
                    ]
                ),
                encoding="utf-8",
            )

            insights = build_insights_from_notes(notes_path)

            self.assertEqual(len(insights.actions), 2)
            self.assertEqual(insights.actions[0].owner, "Maya")
            self.assertEqual(insights.actions[0].text, "Send status update")
            self.assertEqual(insights.actions[0].confidence, "High")
            self.assertEqual(insights.dates[0].due_date, "Friday")
            self.assertIn("1 action item(s) need an owner.", insights.quality_warnings)
            self.assertIn("1 insight(s) have low confidence.", insights.quality_warnings)

    def test_round_trips_insights_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            notes_path = folder / "notes.md"
            notes_path.write_text(
                "## Action Items\n- Owner: Chad; Task: Verify memory limit; Due: Monday; Confidence: Medium",
                encoding="utf-8",
            )
            insights = build_insights_from_notes(notes_path)
            json_path = write_insights_json(folder, insights)

            loaded = read_insights_json(json_path)

            self.assertEqual(loaded.actions[0].owner, "Chad")
            self.assertEqual(loaded.actions[0].status, "open")
