from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from app.audio.audio_validation import inspect_wav
from app.storage.meeting_store import MeetingMetadata, MeetingStore
from app.workflows.meeting_processor import MeetingProcessor


class MeetingProcessorTests(unittest.TestCase):
    def test_inspect_wav_reads_basic_audio_info(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mic.wav"
            self._write_silent_wav(path)

            info = inspect_wav(path)

            self.assertTrue(info.valid)
            self.assertEqual(info.sample_rate, 48000)
            self.assertEqual(info.channels, 2)
            self.assertGreater(info.duration_seconds, 0)

    def test_processor_writes_transcript_notes_and_metadata_without_transcription(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            self._write_silent_wav(folder / "mic.wav")
            self._write_silent_wav(folder / "system.wav")
            metadata = MeetingMetadata(title="Test Meeting", started_at="2026-05-25T09:00:00")

            settings = {
                "transcription": {"enabled": False},
                "ai": {"provider": "ollama"},
                "storage": {"meetings_dir": "meetings"},
            }

            result = MeetingProcessor(MeetingStore(), settings=settings).process(folder, metadata, lambda message: None)

            self.assertTrue(result.transcript_path.exists())
            self.assertTrue(result.notes_path.exists())
            self.assertEqual(metadata.status, "processed_with_warnings")
            self.assertIn("mic", metadata.audio_files)
            self.assertIn("transcript_path", metadata.processing)

    def test_processor_does_not_warn_when_mic_capture_is_muted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            self._write_silent_wav(folder / "system.wav")
            metadata = MeetingMetadata(
                title="System Only Meeting",
                started_at="2026-05-25T09:00:00",
                capture_mic=False,
            )
            messages: list[str] = []
            settings = {
                "transcription": {"enabled": False, "cross_bleed_cleanup": True},
                "ai": {"provider": "ollama"},
                "storage": {"meetings_dir": "meetings"},
            }

            MeetingProcessor(MeetingStore(), settings=settings).process(folder, metadata, messages.append)

            self.assertIn("mic.wav skipped because microphone capture was muted", messages)
            self.assertNotIn("mic.wav is not valid: File does not exist", metadata.processing["warnings"])

    def test_note_highlights_are_inline_markdown_html(self) -> None:
        notes = (
            "- Owner: Chad; Task: Send checklist; Due: Friday, June 5; "
            "Source: Meeting; Confidence: High\n"
            "- Date: Monday, June 17; Context: Review; Source: Meeting; Confidence: Low"
        )

        highlighted = MeetingStore._highlight_notes(notes)

        self.assertIn("<span", highlighted)
        self.assertIn("Friday, June 5", highlighted)
        self.assertIn("Meeting</span>", highlighted)
        self.assertIn("High</span>", highlighted)
        self.assertIn("Low</span>", highlighted)

    def test_notes_only_mode_uses_existing_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "transcript.md").write_text("# Transcript\n\n## Meeting\n\nExisting transcript text.", encoding="utf-8")
            metadata = MeetingMetadata(title="Notes Only", started_at="2026-05-25T09:00:00", capture_mic=False)
            settings = {
                "transcription": {"enabled": False, "cross_bleed_cleanup": True},
                "ai": {"provider": "none"},
                "storage": {"meetings_dir": "meetings"},
            }

            result = MeetingProcessor(MeetingStore(), settings=settings).process(folder, metadata, lambda message: None, mode="notes_only")

            self.assertTrue(result.notes_path.exists())
            self.assertEqual(metadata.processing["mode"], "notes_only")

    def test_notes_only_mode_allows_one_pending_source_when_other_source_has_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "transcript.md").write_text(
                "# Transcript\n\n"
                "## You\n\n"
                "_Transcript pending._\n\n"
                "## Meeting\n\n"
                "Existing meeting audio transcript text.\n",
                encoding="utf-8",
            )
            metadata = MeetingMetadata(title="System Audio Only", started_at="2026-05-25T09:00:00", capture_mic=False)
            settings = {
                "transcription": {"enabled": False, "cross_bleed_cleanup": True},
                "ai": {"provider": "none"},
                "storage": {"meetings_dir": "meetings"},
            }

            MeetingProcessor(MeetingStore(), settings=settings).process(folder, metadata, lambda message: None, mode="notes_only")

            self.assertNotIn("Skipping AI notes because no transcript text is available yet.", metadata.processing["warnings"])

    @staticmethod
    def _write_silent_wav(path: Path) -> None:
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(2)
            wav_file.setsampwidth(2)
            wav_file.setframerate(48000)
            wav_file.writeframes(b"\x00\x00" * 2 * 4800)


if __name__ == "__main__":
    unittest.main()
