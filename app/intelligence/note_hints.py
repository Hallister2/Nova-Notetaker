from __future__ import annotations

import re


ACTION_PATTERNS = (
    r"\b(?P<owner>[A-Z][a-z]+),\s+please\s+(?P<task>[^.]+)",
    r"\b(?P<owner>[A-Z][a-z]+)\s+will\s+(?P<task>[^.]+)",
    r"\b(?P<owner>[A-Z][a-z]+)\s+owns\s+(?P<task>[^.]+)",
    r"\b(?P<task>[^.]*needs an owner[^.]*)",
)

DATE_PATTERN = re.compile(
    r"\b("
    r"next\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)|"
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+[A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th)?|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?|"
    r"Friday,\s+June\s+5|Wednesday,\s+June\s+10|Friday,\s+June\s+14|Monday,\s+June\s+17"
    r")\b",
    re.IGNORECASE,
)


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
            if not task:
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
