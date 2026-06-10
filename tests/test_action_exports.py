from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from app.storage.action_exports import collect_open_action_rows, write_actions_csv, write_actions_digest
from app.storage.meeting_store import MeetingMetadata, MeetingStore


class ActionExportTests(TestCase):
    def test_exports_open_actions_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MeetingStore()
            store.meetings_root = Path(temp_dir)
            folder = store.meetings_root / "meeting"
            folder.mkdir()
            store.write_metadata(folder, MeetingMetadata(title="Ops", started_at="2026-06-09T10:00:00"))
            (folder / "notes.md").write_text(
                "## Action Items\n"
                "- Owner: Maya; Task: Send status update; Due: Friday; Confidence: High\n"
                "- Owner: Chad; Task: Done thing; Due: Monday; Confidence: High",
                encoding="utf-8",
            )
            (folder / "insights.json").write_text(
                '{"actions":[{"kind":"action","text":"Send status update","owner":"Maya","due_date":"Friday","normalized_date":"2026-06-12","source":"","confidence":"High","status":"open","context":""},{"kind":"action","text":"Done thing","owner":"Chad","due_date":"Monday","normalized_date":"2026-06-15","source":"","confidence":"High","status":"done","context":""}],"decisions":[],"dates":[],"warnings":[],"quality_warnings":[]}',
                encoding="utf-8",
            )

            rows = collect_open_action_rows(store)
            csv_path = write_actions_csv(store, folder / "actions.csv")
            digest_path = write_actions_digest(store, folder / "digest.md")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].owner, "Maya")
            self.assertIn("Friday (2026-06-12)", csv_path.read_text(encoding="utf-8"))
            self.assertIn("Send status update", digest_path.read_text(encoding="utf-8"))
            self.assertNotIn("Done thing", digest_path.read_text(encoding="utf-8"))
