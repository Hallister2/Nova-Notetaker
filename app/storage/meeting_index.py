from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.intelligence.insights import load_or_build_insights
from app.storage.meeting_store import MeetingStore
from app.workflows.meeting_processor import MeetingProcessor


INDEX_SCHEMA_VERSION = 1
CLOSED_ACTION_STATUSES = {"done", "closed"}


@dataclass(frozen=True)
class MeetingIndexRecord:
    folder: str
    title: str
    started_at: str
    status: str
    has_transcript: bool
    open_actions: int
    review_count: int
    dates: list[str]
    owners: list[str]
    searchable_text: str


def build_meeting_index(store: MeetingStore | None = None) -> dict:
    meeting_store = store or MeetingStore()
    records: list[MeetingIndexRecord] = []
    for folder in meeting_store.list_meetings():
        try:
            metadata = meeting_store.read_metadata(folder)
            insights = load_or_build_insights(folder)
        except Exception:
            continue

        notes_text = _read_text(folder / "notes.md")
        transcript_text = _read_text(folder / "transcript.md")
        usable_transcript = MeetingProcessor._usable_existing_transcript_text(transcript_text)
        open_actions = sum(1 for item in insights.actions if item.status.lower() not in CLOSED_ACTION_STATUSES)
        review_count = len(insights.quality_warnings) + len(insights.warnings)
        records.append(
            MeetingIndexRecord(
                folder=str(folder),
                title=metadata.title or folder.name,
                started_at=metadata.started_at,
                status=metadata.status,
                has_transcript=bool(usable_transcript.strip()),
                open_actions=open_actions,
                review_count=review_count,
                dates=[item.due_date or item.text for item in insights.dates],
                owners=sorted({item.owner for item in insights.actions if item.owner and item.owner.lower() != "unknown"}),
                searchable_text="\n".join([metadata.title or folder.name, notes_text, transcript_text]).lower(),
            )
        )

    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "records": [asdict(record) for record in records],
    }


def write_meeting_index(store: MeetingStore | None = None) -> Path:
    meeting_store = store or MeetingStore()
    index = build_meeting_index(meeting_store)
    path = meeting_store.meetings_root / "index.json"
    path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return path


def read_meeting_index(store: MeetingStore | None = None) -> dict:
    meeting_store = store or MeetingStore()
    path = meeting_store.meetings_root / "index.json"
    if not path.exists():
        return build_meeting_index(meeting_store)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return build_meeting_index(meeting_store)
    if data.get("schema_version") != INDEX_SCHEMA_VERSION:
        return build_meeting_index(meeting_store)
    return data


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")
