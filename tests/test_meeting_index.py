from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from app.storage.meeting_index import build_meeting_index, search_meeting_index, write_meeting_index
from app.storage.meeting_store import MeetingMetadata, MeetingStore
from app.ui.review_helpers import apply_speaker_aliases_to_markdown, candidate_key, ics_escape, transcript_speakers


class MeetingIndexTests(TestCase):
    def test_builds_lightweight_index_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MeetingStore()
            store.meetings_root = Path(temp_dir)
            folder = store.meetings_root / "2026-05-26_100000_test"
            folder.mkdir()
            store.write_metadata(
                folder,
                MeetingMetadata(
                    title="Test Meeting",
                    started_at="2026-05-26T10:00:00",
                    status="processed",
                ),
            )
            (folder / "notes.md").write_text(
                "\n".join(
                    [
                        "## Action Items",
                        "- Owner: Chad; Task: Review export; Due: Friday; Confidence: High",
                        "## Important Dates",
                        "- Date: Friday; Context: Export review; Confidence: High",
                    ]
                ),
                encoding="utf-8",
            )
            (folder / "transcript.md").write_text("## Meeting Audio\nUseful transcript text.", encoding="utf-8")

            index = build_meeting_index(store)

            self.assertEqual(index["schema_version"], 2)
            self.assertEqual(len(index["records"]), 1)
            record = index["records"][0]
            self.assertEqual(record["title"], "Test Meeting")
            self.assertTrue(record["has_transcript"])
            self.assertEqual(record["open_actions"], 1)
            self.assertTrue(record["dates"])


    def test_search_uses_sqlite_fts_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MeetingStore()
            store.meetings_root = Path(temp_dir)
            folder = store.meetings_root / "2026-05-26_100000_search"
            folder.mkdir()
            store.write_metadata(
                folder,
                MeetingMetadata(
                    title="Waypoint Planning",
                    started_at="2026-05-26T10:00:00",
                    status="processed",
                ),
            )
            (folder / "notes.md").write_text("## Summary\nDiscussed utility account rollout.", encoding="utf-8")
            (folder / "transcript.md").write_text("## Meeting\nWaypoint access needs validation.", encoding="utf-8")

            write_meeting_index(store)
            results = search_meeting_index("Waypoint", store)

            self.assertTrue(results)
            self.assertIn("Waypoint Planning", {result.title for result in results})
            self.assertTrue({result.file_name for result in results} & {"notes.md", "transcript.md", "metadata"})

    def test_meeting_markers_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MeetingStore()
            folder = Path(temp_dir)

            store.append_marker(folder, {"type": "important", "text": "Decision point"})

            self.assertEqual(store.read_markers(folder)[0]["text"], "Decision point")

    def test_closed_actions_do_not_count_as_open(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MeetingStore()
            store.meetings_root = Path(temp_dir)
            folder = store.meetings_root / "2026-05-26_100000_test"
            folder.mkdir()
            store.write_metadata(
                folder,
                MeetingMetadata(
                    title="Test Meeting",
                    started_at="2026-05-26T10:00:00",
                    status="processed",
                ),
            )
            (folder / "insights.json").write_text(
                """
{
  "actions": [
    {"kind": "action", "text": "Old item", "owner": "Chad", "due_date": "Unknown", "source": "", "confidence": "High", "status": "closed", "context": ""}
  ],
  "decisions": [],
  "dates": [],
  "warnings": [],
  "quality_warnings": []
}
""".strip(),
                encoding="utf-8",
            )

            index = build_meeting_index(store)

            self.assertEqual(index["records"][0]["open_actions"], 0)

    def test_review_helpers_apply_speaker_aliases(self) -> None:
        transcript = "# Transcript\n\n## Meeting\n\nHello\n\n## You\n\nYes"

        renamed = apply_speaker_aliases_to_markdown(transcript, {"Meeting": "Alex"})

        self.assertIn("## Alex", renamed)
        self.assertEqual(transcript_speakers(transcript), ["Meeting", "You"])

    def test_ics_escape_and_candidate_key_are_stable(self) -> None:
        self.assertEqual(ics_escape("A, B; C"), "A\\, B\\; C")
        self.assertIn("friday", candidate_key(type("Item", (), {"due_date": "Friday", "text": "Review", "context": "Review"})()))
