from __future__ import annotations

import tempfile
import wave
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from app.transcription.whisperlive_client import WhisperLiveClient


class WhisperLiveClientTests(TestCase):
    def test_splits_long_wav_into_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            wav_path = root / "input.wav"
            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(10)
                wav_file.writeframes(b"\x00\x00" * 35)

            chunks_dir = root / "chunks"
            chunks_dir.mkdir()
            chunks = WhisperLiveClient._split_wav(wav_path, chunks_dir, chunk_seconds=1)

            self.assertEqual(len(chunks), 4)
            self.assertAlmostEqual(WhisperLiveClient._wav_duration_seconds(wav_path), 3.5)
            with wave.open(str(chunks[0]), "rb") as first:
                self.assertEqual(first.getnframes(), 10)

    def test_file_streaming_uses_configured_delay_instead_of_realtime_sleep(self) -> None:
        client = WhisperLiveClient(
            {
                "transcription": {
                    "enabled": True,
                    "websocket_chunk_delay_seconds": 0.01,
                }
            }
        )

        with patch("app.transcription.whisperlive_client.time.sleep") as sleep:
            client._sleep_between_file_chunks(180.0)

        sleep.assert_called_once_with(0.01)

    def test_file_streaming_delay_can_be_disabled(self) -> None:
        client = WhisperLiveClient(
            {
                "transcription": {
                    "enabled": True,
                    "websocket_chunk_delay_seconds": 0,
                }
            }
        )

        with patch("app.transcription.whisperlive_client.time.sleep") as sleep:
            client._sleep_between_file_chunks(180.0)

        sleep.assert_not_called()

    def test_hotwords_can_be_configured(self) -> None:
        client = WhisperLiveClient(
            {
                "transcription": {
                    "enabled": True,
                    "hotwords": "OneDrive, GPO",
                }
            }
        )

        self.assertEqual(client.hotwords, "OneDrive, GPO")

    def test_long_wav_reuses_previous_successful_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            wav_path = root / "input.wav"
            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(10)
                wav_file.writeframes(b"\x00\x00" * 25)

            client = WhisperLiveClient(
                {
                    "transcription": {
                        "enabled": True,
                        "long_audio_chunk_seconds": 1,
                    }
                }
            )
            statuses: list[str] = []

            with patch.object(client, "_transcribe_wav_with_retries", side_effect=["new chunk 2", "new chunk 3"]) as transcribe:
                text, warnings, details = client._transcribe_long_wav(
                    wav_path,
                    duration_seconds=2.5,
                    source="Meeting",
                    on_status=statuses.append,
                    previous_chunks={1: "old chunk 1"},
                )

            self.assertEqual(text, "old chunk 1 new chunk 2 new chunk 3")
            self.assertEqual(transcribe.call_count, 2)
            self.assertEqual(details["reused_chunks"], 1)
            self.assertEqual(details["successful_chunks"], 3)
            self.assertIn("Reusing Meeting chunk 1/3", statuses)

    def test_long_wav_keeps_partial_text_when_one_chunk_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            wav_path = root / "input.wav"
            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(10)
                wav_file.writeframes(b"\x00\x00" * 25)

            client = WhisperLiveClient(
                {
                    "transcription": {
                        "enabled": True,
                        "long_audio_chunk_seconds": 1,
                    }
                }
            )

            with patch.object(client, "_transcribe_wav_with_retries", side_effect=["chunk 1", RuntimeError("boom"), "chunk 3"]):
                text, warnings, details = client._transcribe_long_wav(wav_path, 2.5, "Meeting")

            self.assertEqual(text, "chunk 1 chunk 3")
            self.assertEqual(details["failed_chunks"], 1)
            self.assertTrue(any("failed for chunk 2/3" in warning for warning in warnings))
