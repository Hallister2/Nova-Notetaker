from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.storage.meeting_store import MeetingStore

RAW_AUDIO_NAMES = ("mic.wav", "system.wav", "mic.flac", "system.flac")
NOTES_ONLY_KEEP = {"metadata.json", "notes.md", "insights.json", "markers.json", "review.json"}


@dataclass(frozen=True)
class PrivacyCleanupResult:
    raw_audio_deleted: int = 0
    meetings_removed: int = 0
    files_removed: int = 0
    warnings: tuple[str, ...] = ()


def apply_meeting_privacy(folder: Path, settings: dict[str, Any]) -> PrivacyCleanupResult:
    storage = settings.get("storage", {}) if isinstance(settings, dict) else {}
    warnings: list[str] = []
    raw_deleted = 0
    files_removed = 0

    if storage.get("delete_raw_audio_after_processing", False):
        deleted, delete_warnings = delete_raw_audio(folder)
        raw_deleted += deleted
        warnings.extend(delete_warnings)

    if storage.get("notes_only_archive", False):
        removed, archive_warnings = make_notes_only_archive(folder)
        files_removed += removed
        warnings.extend(archive_warnings)

    return PrivacyCleanupResult(raw_audio_deleted=raw_deleted, files_removed=files_removed, warnings=tuple(warnings))


def apply_retention_policy(store: MeetingStore, settings: dict[str, Any]) -> PrivacyCleanupResult:
    storage = settings.get("storage", {}) if isinstance(settings, dict) else {}
    retention_days = int(storage.get("retention_days", 0) or 0)
    if retention_days <= 0:
        return PrivacyCleanupResult()

    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0
    warnings: list[str] = []
    for folder in store.list_meetings():
        try:
            metadata = store.read_metadata(folder)
            started_at = datetime.fromisoformat(metadata.started_at) if metadata.started_at else datetime.fromtimestamp(folder.stat().st_mtime)
        except Exception:
            started_at = datetime.fromtimestamp(folder.stat().st_mtime)
        if started_at >= cutoff:
            continue
        try:
            shutil.rmtree(folder)
            removed += 1
        except Exception as error:
            warnings.append(f"Could not remove expired meeting {folder.name}: {error}")
    return PrivacyCleanupResult(meetings_removed=removed, warnings=tuple(warnings))


def delete_raw_audio(folder: Path) -> tuple[int, list[str]]:
    deleted = 0
    warnings: list[str] = []
    for name in RAW_AUDIO_NAMES:
        path = folder / name
        if not path.exists():
            continue
        try:
            path.unlink()
            deleted += 1
        except Exception as error:
            warnings.append(f"Could not delete {name}: {error}")
    return deleted, warnings


def make_notes_only_archive(folder: Path) -> tuple[int, list[str]]:
    removed = 0
    warnings: list[str] = []
    for path in folder.iterdir():
        if path.name in NOTES_ONLY_KEEP:
            continue
        if path.name == "transcript.md":
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed += 1
        except Exception as error:
            warnings.append(f"Could not remove {path.name}: {error}")
    return removed, warnings
