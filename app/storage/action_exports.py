from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.intelligence.insights import InsightItem, load_or_build_insights
from app.storage.meeting_store import MeetingMetadata, MeetingStore
from app.ui.constants import CLOSED_ACTION_STATUSES


@dataclass(frozen=True)
class ActionExportRow:
    meeting: str
    started_at: str
    owner: str
    action: str
    due: str
    normalized_due: str
    status: str
    confidence: str
    folder: str


def collect_open_action_rows(store: MeetingStore) -> list[ActionExportRow]:
    rows: list[ActionExportRow] = []
    for folder in store.list_meetings():
        try:
            metadata = store.read_metadata(folder)
            insights = load_or_build_insights(folder)
        except Exception:
            continue
        for action in insights.actions:
            if action.status.lower() in CLOSED_ACTION_STATUSES:
                continue
            rows.append(_row_from_action(folder, metadata, action))
    return sorted(rows, key=lambda row: (row.normalized_due or "9999-99-99", row.owner.lower(), row.meeting.lower()))


def write_actions_csv(store: MeetingStore, output_path: Path | None = None) -> Path:
    rows = collect_open_action_rows(store)
    path = output_path or store.meetings_root / f"nova_open_actions_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["meeting", "started_at", "owner", "action", "due", "normalized_due", "status", "confidence", "folder"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)
    return path


def write_actions_digest(store: MeetingStore, output_path: Path | None = None) -> Path:
    rows = collect_open_action_rows(store)
    path = output_path or store.meetings_root / f"nova_action_digest_{datetime.now():%Y%m%d_%H%M%S}.md"
    lines = ["# Nova Action Digest", "", f"Generated: {datetime.now().isoformat(timespec='seconds')}", ""]
    if not rows:
        lines.append("No open actions found.")
    else:
        current_owner = ""
        for row in rows:
            owner = row.owner or "Unknown"
            if owner != current_owner:
                current_owner = owner
                lines.extend(["", f"## {owner}", ""])
            due = f"; Due: {row.due}" if row.due and row.due.lower() != "unknown" else ""
            status = f"; Status: {row.status}" if row.status else ""
            lines.append(f"- {row.action} ({row.meeting}{due}{status})")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path


def _row_from_action(folder: Path, metadata: MeetingMetadata, action: InsightItem) -> ActionExportRow:
    return ActionExportRow(
        meeting=metadata.title or folder.name,
        started_at=metadata.started_at,
        owner=action.owner or "Unknown",
        action=action.text,
        due=action.date_label or action.due_date or "Unknown",
        normalized_due=action.normalized_date or "",
        status=action.status or "open",
        confidence=action.confidence or "",
        folder=str(folder),
    )
