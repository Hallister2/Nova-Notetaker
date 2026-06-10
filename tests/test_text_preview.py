from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from app.storage.text_preview import has_usable_transcript_preview, read_text_preview


class TextPreviewTests(TestCase):
    def test_preview_reads_bounded_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "large.md"
            path.write_text("abcdef", encoding="utf-8")

            self.assertEqual(read_text_preview(path, max_chars=3), "abc")

    def test_transcript_preview_detects_content_without_full_parse(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "transcript.md"
            path.write_text("# Transcript\n\n## Meeting\n\nUseful meeting text.", encoding="utf-8")

            self.assertTrue(has_usable_transcript_preview(path))
