from __future__ import annotations

import tempfile
import wave
from pathlib import Path
from unittest import TestCase

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
