from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.settings import APP_ROOT, load_settings


def _migrate_metadata(data: dict[str, Any]) -> dict[str, Any]:
    """Bring older metadata.json dicts up to the current schema version."""
    version = int(data.get("schema_version") or 1)

    if version < 2:
        # v1 → v2: capture_profile moved from audio settings into metadata directly.
        # If missing, leave as None so the processor falls back to the app default.
        data.setdefault("capture_profile", None)
        # meeting_context was not always present
        data.setdefault("meeting_context", "")
        data["schema_version"] = 2

    return data


METADATA_SCHEMA_VERSION = 2


@dataclass
class MeetingMetadata:
    title: str
    started_at: str
    ended_at: str | None = None
    mic_device_name: str | None = None
    system_device_name: str | None = None
    capture_mic: bool = True
    capture_profile: str | None = None
    meeting_profile: dict[str, Any] = field(default_factory=dict)
    note_template: dict[str, Any] = field(default_factory=dict)
    meeting_context: str = ""
    status: str = "created"
    audio_files: dict[str, Any] = field(default_factory=dict)
    processing: dict[str, Any] = field(default_factory=dict)
    schema_version: int = METADATA_SCHEMA_VERSION


class MeetingStore:
    def __init__(self) -> None:
        settings = load_settings()
        relative_dir = settings["storage"].get("meetings_dir", "meetings")
        self.meetings_root = APP_ROOT / relative_dir
        self.meetings_root.mkdir(parents=True, exist_ok=True)

    def create_meeting_folder(self, title: str) -> Path:
        now = datetime.now()
        slug = self._slugify(title or "untitled-meeting")
        folder = self.meetings_root / f"{now:%Y-%m-%d_%H%M%S}_{slug}"
        folder.mkdir(parents=True, exist_ok=False)
        return folder

    def write_metadata(self, folder: Path, metadata: MeetingMetadata) -> None:
        path = folder / "metadata.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(asdict(metadata), handle, indent=2)

    def append_marker(self, folder: Path, marker: dict[str, Any]) -> Path:
        markers = self.read_markers(folder)
        markers.append(marker)
        return self.write_markers(folder, markers)

    def read_markers(self, folder: Path) -> list[dict[str, Any]]:
        path = folder / "markers.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def write_markers(self, folder: Path, markers: list[dict[str, Any]]) -> Path:
        path = folder / "markers.json"
        path.write_text(json.dumps(markers, indent=2), encoding="utf-8")
        return path

    def list_meetings(self) -> list[Path]:
        if not self.meetings_root.exists():
            return []
        folders = [path for path in self.meetings_root.iterdir() if path.is_dir()]
        return sorted(folders, key=lambda path: path.stat().st_mtime, reverse=True)

    def read_metadata(self, folder: Path) -> MeetingMetadata:
        path = folder / "metadata.json"
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        data = _migrate_metadata(data)
        fields = MeetingMetadata.__dataclass_fields__
        filtered = {key: value for key, value in data.items() if key in fields}
        return MeetingMetadata(**filtered)

    def write_transcript(self, folder: Path, transcript: str) -> Path:
        path = folder / "transcript.md"
        path.write_text(transcript, encoding="utf-8")
        return path

    def write_notes(self, folder: Path, metadata: MeetingMetadata, notes: str, transcript_path: Path, warnings: list[str]) -> Path:
        path = folder / "notes.md"
        warning_block = self._format_warnings(warnings)
        notes = self._remove_source_fields(notes)
        notes = self._highlight_notes(notes.strip())
        path.write_text(
            f"# {metadata.title or 'Untitled Meeting'}\n\n"
            f"Started: {metadata.started_at}\n\n"
            f"Transcript: `{transcript_path.name}`\n\n"
            f"{notes}\n"
            f"{warning_block}",
            encoding="utf-8",
        )
        return path

    def write_notes_stub(
        self,
        folder: Path,
        metadata: MeetingMetadata,
        transcript_path: Path | None = None,
        warnings: list[str] | None = None,
    ) -> Path:
        path = folder / "notes.md"
        title = metadata.title or "Untitled Meeting"
        transcript_line = f"Transcript: `{transcript_path.name}`\n\n" if transcript_path else ""
        path.write_text(
            f"# {title}\n\n"
            f"Started: {metadata.started_at}\n\n"
            f"{transcript_line}"
            "## Summary\n\n"
            "_Summary generation is pending transcription and AI processing._\n\n"
            "## Action Items\n\n"
            "- _Pending transcription and AI processing._\n\n"
            "## Important Dates\n\n"
            "- _Pending extraction._\n"
            f"{self._format_warnings(warnings or [])}",
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _format_warnings(warnings: list[str]) -> str:
        if not warnings:
            return ""
        lines = ["\n## Processing Warnings\n"]
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
        return "\n".join(lines)

    @classmethod
    def _highlight_notes(cls, notes: str) -> str:
        highlighted_lines = []
        for line in notes.splitlines():
            highlighted_lines.append(cls._highlight_note_line(line))
        return "\n".join(highlighted_lines).strip()

    @staticmethod
    def _remove_source_fields(notes: str) -> str:
        notes = re.sub(r";\s*Source:\s*[^;\n]+", "", notes)
        notes = re.sub(r"\bSource:\s*[^;\n]+;?\s*", "", notes)
        return notes

    @classmethod
    def _highlight_note_line(cls, line: str) -> str:
        line = re.sub(r"\bSource:\s*([^;]+)", lambda match: f"Source: {cls._source_badge(match.group(1).strip())}", line)
        line = re.sub(r"\bConfidence:\s*(High|Medium|Low)\b", lambda match: f"Confidence: {cls._confidence_badge(match.group(1))}", line, flags=re.IGNORECASE)
        line = re.sub(r"\bDue:\s*([^;]+)", lambda match: f"Due: {cls._date_badge(match.group(1).strip())}", line)
        line = re.sub(r"\bDate:\s*([^;]+)", lambda match: f"Date: {cls._date_badge(match.group(1).strip())}", line)
        return line

    @staticmethod
    def _source_badge(value: str) -> str:
        color = "#7dd3fc" if value.lower().startswith("meeting") else "#c4b5fd"
        return f'<span style="color:{color};font-weight:700;">{value}</span>'

    @staticmethod
    def _confidence_badge(value: str) -> str:
        colors = {
            "high": ("#0f2f1f", "#4ade80"),
            "medium": ("#3a2a05", "#facc15"),
            "low": ("#3b1111", "#fb7185"),
        }
        background, foreground = colors.get(value.lower(), ("#262626", "#e5e7eb"))
        return f'<span style="background-color:{background};color:{foreground};font-weight:700;padding:1px 6px;border-radius:6px;">{value}</span>'

    @staticmethod
    def _date_badge(value: str) -> str:
        return f'<span style="background-color:#3b2a00;color:#ffcf70;font-weight:700;padding:1px 6px;border-radius:6px;">{value}</span>'

    @staticmethod
    def _slugify(text: str) -> str:
        text = text.strip().lower()
        text = re.sub(r"[^a-z0-9]+", "-", text)
        return text.strip("-")[:64] or "untitled-meeting"
