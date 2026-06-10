from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import TestCase

from app.storage.meeting_store import MeetingMetadata, MeetingStore
from app.storage.privacy import apply_meeting_privacy, apply_retention_policy


class PrivacyTests(TestCase):
    def test_notes_only_archive_removes_audio_and_keeps_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            for name in ("metadata.json", "notes.md", "transcript.md", "mic.wav", "system.flac", "debug.tmp"):
                (folder / name).write_text("x", encoding="utf-8")

            result = apply_meeting_privacy(folder, {"storage": {"notes_only_archive": True}})

            self.assertFalse((folder / "mic.wav").exists())
            self.assertFalse((folder / "system.flac").exists())
            self.assertFalse((folder / "debug.tmp").exists())
            self.assertTrue((folder / "notes.md").exists())
            self.assertTrue((folder / "transcript.md").exists())
            self.assertEqual(result.files_removed, 3)

    def test_retention_policy_removes_old_meetings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MeetingStore()
            store.meetings_root = Path(temp_dir)
            old_folder = store.meetings_root / "old"
            old_folder.mkdir()
            store.write_metadata(old_folder, MeetingMetadata(title="Old", started_at=(datetime.now() - timedelta(days=40)).isoformat(timespec="seconds")))
            new_folder = store.meetings_root / "new"
            new_folder.mkdir()
            store.write_metadata(new_folder, MeetingMetadata(title="New", started_at=datetime.now().isoformat(timespec="seconds")))

            result = apply_retention_policy(store, {"storage": {"retention_days": 30}})

            self.assertEqual(result.meetings_removed, 1)
            self.assertFalse(old_folder.exists())
            self.assertTrue(new_folder.exists())
