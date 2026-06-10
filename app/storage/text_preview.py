from __future__ import annotations

from pathlib import Path


def read_text_preview(path: Path, max_chars: int = 6000) -> str:
    if not path.exists():
        return ""
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return handle.read(max_chars)


def has_usable_transcript_preview(path: Path, max_chars: int = 32768) -> bool:
    if not path.exists():
        return False
    ignored_prefixes = ("#", "_", "-")
    pending_markers = ("transcript pending", "no transcript", "skipping ")
    chars_seen = 0
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            chars_seen += len(raw_line)
            line = raw_line.strip()
            lowered = line.lower()
            if line and not line.startswith(ignored_prefixes) and not any(marker in lowered for marker in pending_markers):
                return True
            if chars_seen >= max_chars:
                return False
    return False
