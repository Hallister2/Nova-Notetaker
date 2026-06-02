from __future__ import annotations

import json
import re
from pathlib import Path

from app.core.settings import CONFIG_DIR


ACTION_PATTERNS = (
    r"\b(?P<owner>[A-Z][a-z]+),\s+please\s+(?P<task>[^.]+)",
    r"\b(?P<owner>[A-Z][a-z]+)\s+will\s+(?P<task>[^.]+)",
    r"\b(?P<owner>[A-Z][a-z]+)\s+owns\s+(?P<task>[^.]+)",
    r"\b(?P<task>[^.]*needs an owner[^.]*)",
)

ACTION_TASK_STOP_PREFIXES = (
    "say ",
    "says ",
    "said ",
    "okay ",
    "not mirror ",
    "does a match",
)

_BASE_DATE_PATTERN = (
    r"next\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)|"
    r"this\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)|"
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+[A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th)?|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?"
)


def _load_hints(path: Path = CONFIG_DIR / "hints.json") -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_date_pattern() -> re.Pattern:
    hints = _load_hints()
    extra_patterns = [re.escape(p.strip()) for p in hints.get("extra_date_patterns", []) if p.strip()]
    combined = _BASE_DATE_PATTERN
    if extra_patterns:
        combined = combined + "|" + "|".join(extra_patterns)
    return re.compile(r"\b(" + combined + r")\b", re.IGNORECASE)


DATE_PATTERN = _build_date_pattern()


def build_note_hints(transcript: str) -> str:
    body = _strip_markdown_structure(transcript)
    actions = _extract_actions(body)
    dates = _extract_dates(body)
    if not actions and not dates:
        return ""

    lines = ["Potential extraction hints. Use these only if supported by the transcript; do not invent details."]
    if actions:
        lines.append("Potential action items:")
        lines.extend(f"- {action}" for action in actions[:12])
    if dates:
        lines.append("Potential dates:")
        lines.extend(f"- {date}" for date in dates[:12])
    return "\n".join(lines)


def _extract_actions(text: str) -> list[str]:
    actions: list[str] = []
    seen: set[str] = set()
    for pattern in ACTION_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            owner = match.groupdict().get("owner") or "Unknown"
            task = _clean_fragment(match.groupdict().get("task", ""))
            if not task or _looks_like_noisy_action(task):
                continue
            action = f"Owner: {owner}; Task: {task}"
            key = action.lower()
            if key not in seen:
                actions.append(action)
                seen.add(key)
    return actions


def _extract_dates(text: str) -> list[str]:
    dates: list[str] = []
    seen: set[str] = set()
    for match in DATE_PATTERN.finditer(text):
        value = match.group(1).strip()
        key = value.lower()
        if key not in seen:
            dates.append(value)
            seen.add(key)
    return dates


def _strip_markdown_structure(text: str) -> str:
    text = re.sub(r"^#+\s+.*$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"_Transcript pending\._", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_fragment(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" -;,.")
    return text[:180]


def _looks_like_noisy_action(task: str) -> bool:
    normalized = task.lower().strip()
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if len(normalized.split()) < 3:
        return True
    return any(normalized.startswith(prefix) for prefix in ACTION_TASK_STOP_PREFIXES)
