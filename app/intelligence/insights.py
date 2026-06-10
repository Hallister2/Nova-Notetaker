from __future__ import annotations

import html
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal


InsightKind = Literal["action", "decision", "date", "warning"]


@dataclass
class InsightItem:
    kind: InsightKind
    text: str
    owner: str = ""
    due_date: str = ""
    normalized_date: str = ""
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
            due_label = self.date_label
            due = f" | {due_label}" if due_label and due_label.lower() != "unknown" else ""
            return f"{owner}: {self.text}{due}"
        if self.kind == "date":
            label = self.date_label or self.text
            return f"{label}: {self.context or self.text}"
        return self.text

    @property
    def date_label(self) -> str:
        display = self.due_date or ""
        normalized = self.normalized_date or ""
        if display and normalized and display != normalized:
            return f"{display} ({normalized})"
        return display or normalized


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


def build_insights_from_notes(notes_path: Path, meeting_date: datetime | None = None) -> MeetingInsights:
    insights = MeetingInsights()
    if not notes_path.exists():
        insights.quality_warnings.append("No notes file found.")
        return insights

    section = ""
    for raw_line in notes_path.read_text(encoding="utf-8").splitlines():
        line = _plain_note_text(raw_line).strip()
        lower = line.lower()
        if lower.startswith("## "):
            section = _section_to_category(lower)
            continue

        if not section or not line.startswith(("-", "*")):
            continue

        item_text = line.lstrip("-* ").strip()
        if not item_text or item_text.startswith("_"):
            continue
        if item_text.lower().rstrip(".") in {"none captured", "none"}:
            continue

        if section == "actions":
            insights.actions.append(_parse_action(item_text, meeting_date))
        elif section == "decisions":
            decision = _parse_decision(item_text)
            if decision:
                insights.decisions.append(decision)
        elif section == "dates":
            insights.dates.append(_parse_date(item_text, meeting_date))
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


def _parse_action(text: str, meeting_date: datetime | None = None) -> InsightItem:
    fields = _field_map(text)
    task = fields.get("task") or _strip_known_fields(text)
    raw_due = fields.get("due", "")
    due_date, inferred_confidence = _extract_trailing_confidence(raw_due)
    normalized_date = _normalize_date_string(due_date, meeting_date)
    owner, owner_confidence = _extract_trailing_confidence(fields.get("owner", "Unknown"))
    task, task_confidence = _extract_trailing_confidence(task)
    return InsightItem(
        kind="action",
        text=task,
        owner=_normalize_owner(owner),
        due_date=due_date,
        normalized_date=normalized_date if normalized_date != due_date else "",
        source=fields.get("source", ""),
        confidence=_normalize_confidence(fields.get("confidence", "") or inferred_confidence or owner_confidence or task_confidence),
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


def _parse_date(text: str, meeting_date: datetime | None = None) -> InsightItem:
    fields = _field_map(text)
    raw_date = fields.get("date") or fields.get("due") or ""
    normalized_date = _normalize_date_string(raw_date, meeting_date)
    context, inferred_confidence = _extract_trailing_confidence(fields.get("context") or _strip_known_fields(text))
    return InsightItem(
        kind="date",
        text=context,
        due_date=raw_date,
        normalized_date=normalized_date if normalized_date != raw_date else "",
        context=context,
        source=fields.get("source", ""),
        confidence=_normalize_confidence(fields.get("confidence", "") or inferred_confidence),
    )


def _field_map(text: str) -> dict[str, str]:
    # Strip bold markdown (**Key:** → Key:) before splitting
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    fields: dict[str, str] = {}
    # Accept ; or | or newline as field delimiters
    for part in re.split(r"[;|\n]+", text):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = key.strip().lstrip("-* ").lower()
        if key:
            fields[key] = value.strip()
    return fields


def _strip_known_fields(text: str) -> str:
    text = re.sub(r"\b(Owner|Task|Due|Date|Context|Source|Confidence|Decision):\s*", "", text, flags=re.IGNORECASE)
    return " ".join(part.strip() for part in text.split(";") if part.strip())


def _looks_like_assignment(text: str) -> bool:
    lowered = text.lower()
    decision_markers = ("decided", "decision", "agreed", "approved", "rejected", "keep ", "remain ", "not switching")
    if any(marker in lowered for marker in decision_markers):
        return False
    if re.search(r"\b[A-Z][a-z]+\s+to\s+\w+", text):
        return True
    assignment_markers = (
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


def _normalize_owner(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return "Unknown"
    if cleaned.lower() in {"nova", "nova notetaker", "system", "dashboard", "tool", "app"}:
        return "Unknown"
    return cleaned


def _extract_trailing_confidence(value: str) -> tuple[str, str]:
    match = re.search(r"\s*\((High|Medium|Low|Unknown)\)\s*$", value.strip(), flags=re.IGNORECASE)
    if not match:
        return value.strip(), ""
    cleaned = value[: match.start()].strip()
    confidence = "" if match.group(1).lower() == "unknown" else match.group(1)
    return cleaned, confidence


_WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _normalize_date_string(value: str, meeting_date: datetime | None) -> str:
    """Resolve relative date strings to ISO 8601 (YYYY-MM-DD) when possible."""
    if not value or not value.strip():
        return value
    cleaned = value.strip()
    lower = cleaned.lower()

    # Already absolute ISO date — leave it
    if re.match(r"^\d{4}-\d{2}-\d{2}", cleaned):
        return cleaned

    base = meeting_date or datetime.now()

    # "tomorrow"
    if lower == "tomorrow":
        return (base + timedelta(days=1)).strftime("%Y-%m-%d")

    # "today"
    if lower == "today":
        return base.strftime("%Y-%m-%d")

    # "end of week" / "end of month"
    if re.search(r"\bend of (this )?week\b", lower):
        days_until_friday = (4 - base.weekday()) % 7
        return (base + timedelta(days=days_until_friday or 7)).strftime("%Y-%m-%d")
    if re.search(r"\bend of (this )?month\b", lower):
        import calendar
        last_day = calendar.monthrange(base.year, base.month)[1]
        return base.replace(day=last_day).strftime("%Y-%m-%d")

    # "next Monday" / "next Friday"
    next_match = re.match(r"next\s+(\w+)", lower)
    if next_match:
        day_name = next_match.group(1).lower()
        if day_name in _WEEKDAY_NAMES:
            target_weekday = _WEEKDAY_NAMES.index(day_name)
            days_ahead = (target_weekday - base.weekday()) % 7
            days_ahead = days_ahead or 7  # "next" always means at least one week out
            return (base + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    # "this Friday" / standalone weekday name
    this_match = re.match(r"(?:this\s+)?(\w+day)$", lower)
    if this_match:
        day_name = this_match.group(1).lower()
        if day_name in _WEEKDAY_NAMES:
            target_weekday = _WEEKDAY_NAMES.index(day_name)
            days_ahead = (target_weekday - base.weekday()) % 7
            return (base + timedelta(days=days_ahead or 7)).strftime("%Y-%m-%d")

    # "June 14" / "June 14th" / "June 14, 2025"
    month_day = re.match(
        r"(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?", cleaned, re.IGNORECASE
    )
    if month_day:
        month_name = month_day.group(1).lower()
        month_num = _MONTH_NAMES.get(month_name)
        day_num = int(month_day.group(2))
        year = int(month_day.group(3)) if month_day.group(3) else base.year
        if month_num and 1 <= day_num <= 31:
            try:
                resolved = date(year, month_num, day_num)
                # If no year was given and the date has passed, assume next year
                if not month_day.group(3) and resolved < base.date():
                    resolved = resolved.replace(year=year + 1)
                return resolved.strftime("%Y-%m-%d")
            except ValueError:
                pass

    # "Friday, June 14" / "Monday, June 17"
    weekday_month_day = re.match(
        r"\w+,?\s+(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?", cleaned, re.IGNORECASE
    )
    if weekday_month_day:
        month_name = weekday_month_day.group(1).lower()
        month_num = _MONTH_NAMES.get(month_name)
        day_num = int(weekday_month_day.group(2))
        year = int(weekday_month_day.group(3)) if weekday_month_day.group(3) else base.year
        if month_num and 1 <= day_num <= 31:
            try:
                resolved = date(year, month_num, day_num)
                if not weekday_month_day.group(3) and resolved < base.date():
                    resolved = resolved.replace(year=year + 1)
                return resolved.strftime("%Y-%m-%d")
            except ValueError:
                pass

    return cleaned


_SECTION_ALIASES: dict[str, list[str]] = {
    "actions": ["action", "task", "to-do", "todo", "next step", "follow-up", "followup", "commitment", "open item"],
    "decisions": ["decision", "agreed", "agreement", "approval", "conclusion"],
    "dates": ["date", "deadline", "timeline", "milestone", "schedule"],
    "warnings": ["warning", "risk", "blocker", "concern", "open question", "issue"],
}


def _section_to_category(heading_lower: str) -> str:
    for category, aliases in _SECTION_ALIASES.items():
        if any(alias in heading_lower for alias in aliases):
            return category
    return ""


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
