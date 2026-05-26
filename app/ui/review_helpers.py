from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.intelligence.insights import InsightItem
from app.storage.meeting_store import MeetingMetadata


def ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def safe_file_label(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-").lower() or "meeting"


@dataclass(frozen=True)
class CalendarCandidate:
    folder: Path
    metadata: MeetingMetadata
    item: InsightItem
    approved: bool
    date_text: str
    context: str


def candidate_key(item: InsightItem) -> str:
    raw = "|".join(
        [
            item.due_date.strip().lower(),
            item.text.strip().lower(),
            item.context.strip().lower(),
        ]
    )
    return re.sub(r"\s+", " ", raw)


def read_calendar_review(folder: Path) -> dict:
    path = folder / "calendar_review.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_calendar_review(folder: Path, review: dict) -> Path:
    path = folder / "calendar_review.json"
    path.write_text(json.dumps(review, indent=2), encoding="utf-8")
    return path


def read_speaker_aliases(folder: Path) -> dict[str, str]:
    path = folder / "speaker_aliases.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if str(value).strip()}


def write_speaker_aliases(folder: Path, aliases: dict[str, str]) -> Path:
    path = folder / "speaker_aliases.json"
    cleaned = {str(key): str(value).strip() for key, value in aliases.items() if str(value).strip()}
    path.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    return path


def apply_speaker_aliases_to_markdown(markdown: str, aliases: dict[str, str]) -> str:
    lines = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            speaker = line[3:].strip()
            if speaker in aliases:
                line = f"## {aliases[speaker]}"
        lines.append(line)
    return "\n".join(lines)


def transcript_speakers(markdown: str) -> list[str]:
    speakers: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## ") and line.strip().lower() != "## processing warnings":
            speaker = line[3:].strip()
            if speaker and speaker not in speakers:
                speakers.append(speaker)
    return speakers
