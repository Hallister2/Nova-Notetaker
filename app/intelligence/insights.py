from __future__ import annotations

import html
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


InsightKind = Literal["action", "decision", "date", "warning"]


@dataclass
class InsightItem:
    kind: InsightKind
    text: str
    owner: str = ""
    due_date: str = ""
    source: str = ""
    confidence: str = ""
    status: str = "open"
    context: str = ""

    @property
    def stable_key(self) -> str:
        return "|".join(
            [
                self.kind.lower(),
                self.owner.strip().lower(),
                self.due_date.strip().lower(),
                re.sub(r"\s+", " ", self.text.strip().lower()),
            ]
        )

    @property
    def display_text(self) -> str:
        if self.kind == "action":
            owner = self.owner or "Unknown"
            due = f" | {self.due_date}" if self.due_date and self.due_date.lower() != "unknown" else ""
            return f"{owner}: {self.text}{due}"
        if self.kind == "date":
            label = self.due_date or self.text
            return f"{label}: {self.context or self.text}"
        return self.text


@dataclass
class MeetingInsights:
    actions: list[InsightItem] = field(default_factory=list)
    decisions: list[InsightItem] = field(default_factory=list)
    dates: list[InsightItem] = field(default_factory=list)
    warnings: list[InsightItem] = field(default_factory=list)
    quality_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [asdict(item) for item in self.actions],
            "decisions": [asdict(item) for item in self.decisions],
            "dates": [asdict(item) for item in self.dates],
            "warnings": [asdict(item) for item in self.warnings],
            "quality_warnings": self.quality_warnings,
        }


def build_insights_from_notes(notes_path: Path) -> MeetingInsights:
    insights = MeetingInsights()
    if not notes_path.exists():
        insights.quality_warnings.append("No notes file found.")
        return insights

    section = ""
    for raw_line in notes_path.read_text(encoding="utf-8").splitlines():
        line = _plain_note_text(raw_line).strip()
        lower = line.lower()
        if lower.startswith("## "):
            if "action" in lower:
                section = "actions"
            elif "decision" in lower:
                section = "decisions"
            elif "date" in lower:
                section = "dates"
            elif "warning" in lower:
                section = "warnings"
            else:
                section = ""
            continue

        if not section or not line.startswith("-"):
            continue

        item_text = line.lstrip("- ").strip()
        if not item_text or item_text.startswith("_"):
            continue
        if item_text.lower().rstrip(".") in {"none captured", "none"}:
            continue

        if section == "actions":
            insights.actions.append(_parse_action(item_text))
        elif section == "decisions":
            decision = _parse_decision(item_text)
            if decision:
                insights.decisions.append(decision)
        elif section == "dates":
            insights.dates.append(_parse_date(item_text))
        elif section == "warnings":
            insights.warnings.append(InsightItem(kind="warning", text=item_text))

    insights.quality_warnings = _quality_warnings(insights)
    return insights


def write_insights_json(folder: Path, insights: MeetingInsights) -> Path:
    path = folder / "insights.json"
    path.write_text(json.dumps(insights.to_dict(), indent=2), encoding="utf-8")
    return path


def write_insights_preserving_statuses(folder: Path, insights: MeetingInsights) -> Path:
    existing_path = folder / "insights.json"
    if existing_path.exists():
        try:
            previous = read_insights_json(existing_path)
            status_by_key = {item.stable_key: item.status for item in previous.actions}
            for item in insights.actions:
                if item.stable_key in status_by_key:
                    item.status = status_by_key[item.stable_key]
        except Exception:
            pass
    return write_insights_json(folder, insights)


def read_insights_json(path: Path) -> MeetingInsights:
    data = json.loads(path.read_text(encoding="utf-8"))
    return MeetingInsights(
        actions=[InsightItem(**item) for item in data.get("actions", [])],
        decisions=[InsightItem(**item) for item in data.get("decisions", [])],
        dates=[InsightItem(**item) for item in data.get("dates", [])],
        warnings=[InsightItem(**item) for item in data.get("warnings", [])],
        quality_warnings=list(data.get("quality_warnings", [])),
    )


def load_or_build_insights(folder: Path) -> MeetingInsights:
    json_path = folder / "insights.json"
    notes_path = folder / "notes.md"
    if json_path.exists():
        try:
            if not notes_path.exists() or json_path.stat().st_mtime >= notes_path.stat().st_mtime:
                return read_insights_json(json_path)
        except Exception:
            pass
    insights = build_insights_from_notes(notes_path)
    try:
        write_insights_preserving_statuses(folder, insights)
    except Exception:
        pass
    return insights


def _parse_action(text: str) -> InsightItem:
    fields = _field_map(text)
    task = fields.get("task") or _strip_known_fields(text)
    return InsightItem(
        kind="action",
        text=task,
        owner=fields.get("owner", "Unknown"),
        due_date=fields.get("due", ""),
        source=fields.get("source", ""),
        confidence=_normalize_confidence(fields.get("confidence", "")),
    )


def _parse_decision(text: str) -> InsightItem | None:
    fields = _field_map(text)
    decision_text = fields.get("decision") or fields.get("context") or _strip_known_fields(text)
    if _looks_like_assignment(decision_text):
        return None
    return InsightItem(
        kind="decision",
        text=decision_text,
        source=fields.get("source", ""),
        confidence=_normalize_confidence(fields.get("confidence", "")),
    )


def _parse_date(text: str) -> InsightItem:
    fields = _field_map(text)
    date = fields.get("date") or fields.get("due") or ""
    context = fields.get("context") or _strip_known_fields(text)
    return InsightItem(
        kind="date",
        text=context,
        due_date=date,
        context=context,
        source=fields.get("source", ""),
        confidence=_normalize_confidence(fields.get("confidence", "")),
    )


def _field_map(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in [part.strip() for part in text.split(";") if part.strip()]:
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        fields[key.strip().lower()] = value.strip()
    return fields


def _strip_known_fields(text: str) -> str:
    text = re.sub(r"\b(Owner|Task|Due|Date|Context|Source|Confidence|Decision):\s*", "", text, flags=re.IGNORECASE)
    return " ".join(part.strip() for part in text.split(";") if part.strip())


def _looks_like_assignment(text: str) -> bool:
    lowered = text.lower()
    decision_markers = ("decided", "decision", "agreed", "approved", "rejected", "keep ", "remain ", "not switching")
    if any(marker in lowered for marker in decision_markers):
        return False
    assignment_markers = (
        r"\b[A-Z][a-z]+\s+to\s+\w+",
        r"\bby\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|may|june|july|august|september|october|november|december)\b",
        r"\bwill own\b",
        r"\bplease\b",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in assignment_markers)


def _plain_note_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).replace("\xa0", " ")


def _normalize_confidence(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"high", "medium", "low"}:
        return lowered.title()
    return value.strip()


def _quality_warnings(insights: MeetingInsights) -> list[str]:
    warnings: list[str] = []
    if not insights.actions:
        warnings.append("No action items detected.")
    if not insights.dates:
        warnings.append("No important dates detected.")
    unknown_owner_count = sum(1 for item in insights.actions if not item.owner or item.owner.lower() == "unknown")
    unknown_due_count = sum(1 for item in insights.actions if not item.due_date or item.due_date.lower() == "unknown")
    low_confidence_count = sum(
        1
        for item in [*insights.actions, *insights.decisions, *insights.dates]
        if item.confidence.lower() == "low"
    )
    if unknown_owner_count:
        warnings.append(f"{unknown_owner_count} action item(s) need an owner.")
    if unknown_due_count:
        warnings.append(f"{unknown_due_count} action item(s) do not have a due date.")
    if low_confidence_count:
        warnings.append(f"{low_confidence_count} insight(s) have low confidence.")
    for warning in insights.warnings:
        if "system audio" in warning.text.lower() or "invalid" in warning.text.lower():
            warnings.append(warning.text)
    return warnings
