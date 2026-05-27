from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest import TestCase

from app.intelligence.insights import build_insights_from_notes, load_or_build_insights, read_insights_json, write_insights_json


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

    def test_parses_asterisk_bullets_and_html_badges(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            notes_path = Path(temp_dir) / "notes.md"
            notes_path.write_text(
                "\n".join(
                    [
                        "## Action Items",
                        '* Owner: Maya; Task: Review switch logs; Due: <span style="color:red">Thursday afternoon</span>; Confidence: <span>High</span>',
                        "## Key Decisions",
                        "* Backup schedule should not change until a formal change request is created.",
                        "## Important Dates",
                        '* Date: <span>Friday, May 29</span>; Context: IT Team submits change request; Confidence: <span>High</span>',
                    ]
                ),
                encoding="utf-8",
            )

            insights = build_insights_from_notes(notes_path)

            self.assertEqual(len(insights.actions), 1)
            self.assertEqual(insights.actions[0].owner, "Maya")
            self.assertEqual(insights.actions[0].due_date, "Thursday afternoon")
            self.assertEqual(insights.actions[0].confidence, "High")
            self.assertEqual(len(insights.decisions), 1)
            self.assertEqual(insights.dates[0].due_date, "Friday, May 29")

    def test_extracts_confidence_from_parenthetical_due_and_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            notes_path = Path(temp_dir) / "notes.md"
            notes_path.write_text(
                "\n".join(
                    [
                        "## Action Items",
                        "* Owner: IT Team; Task: Create change request; Due: Friday (High)",
                        "## Important Dates",
                        "* Date: Monday, June 1st; Context: next full operations review (Medium)",
                    ]
                ),
                encoding="utf-8",
            )

            insights = build_insights_from_notes(notes_path)

            self.assertEqual(insights.actions[0].due_date, "Friday")
            self.assertEqual(insights.actions[0].confidence, "High")
            self.assertEqual(insights.dates[0].context, "next full operations review")
            self.assertEqual(insights.dates[0].confidence, "Medium")

    def test_rebuilds_when_notes_are_newer_than_insights_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            notes_path = folder / "notes.md"
            notes_path.write_text(
                "## Action Items\n- Owner: Chad; Task: Old task; Due: Monday; Confidence: Medium",
                encoding="utf-8",
            )
            write_insights_json(folder, build_insights_from_notes(notes_path))
            notes_path.write_text(
                "## Action Items\n- Owner: Maya; Task: New task; Due: Friday; Confidence: High",
                encoding="utf-8",
            )
            newer_time = time.time() + 5
            os.utime(notes_path, (newer_time, newer_time))

            loaded = load_or_build_insights(folder)

            self.assertEqual(loaded.actions[0].owner, "Maya")
            self.assertEqual(loaded.actions[0].text, "New task")

    def test_rebuild_preserves_action_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            notes_path = folder / "notes.md"
            notes_path.write_text(
                "## Action Items\n- Owner: Chad; Task: Verify memory limit; Due: Monday; Confidence: Medium",
                encoding="utf-8",
            )
            insights = build_insights_from_notes(notes_path)
            insights.actions[0].status = "done"
            write_insights_json(folder, insights)
            newer_time = time.time() + 5
            os.utime(notes_path, (newer_time, newer_time))

            loaded = load_or_build_insights(folder)

            self.assertEqual(loaded.actions[0].status, "done")

    def test_decision_parser_skips_assignment_bullets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            notes_path = Path(temp_dir) / "notes.md"
            notes_path.write_text(
                "\n".join(
                    [
                        "## Key Decisions",
                        "- Product dashboard: Maya to update log by Thursday, May 28th.",
                        "- Decision: Keep current orange accent for this release.",
                    ]
                ),
                encoding="utf-8",
            )

            insights = build_insights_from_notes(notes_path)

            self.assertEqual(len(insights.decisions), 1)
            self.assertIn("orange accent", insights.decisions[0].text)

    def test_none_captured_does_not_create_fake_insights(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            notes_path = Path(temp_dir) / "notes.md"
            notes_path.write_text(
                "\n".join(
                    [
                        "## Key Decisions",
                        "- None captured.",
                        "## Action Items",
                        "- None captured.",
                        "## Important Dates",
                        "- None captured.",
                    ]
                ),
                encoding="utf-8",
            )

            insights = build_insights_from_notes(notes_path)

            self.assertEqual(insights.actions, [])
            self.assertEqual(insights.decisions, [])
            self.assertEqual(insights.dates, [])
