from __future__ import annotations

import re

from app.intelligence.insights import InsightItem, MeetingInsights


LiveTranscriptRow = tuple[str, str, str, bool]


ACTION_WORDS = (
    "follow up",
    "review",
    "verify",
    "confirm",
    "create",
    "draft",
    "send",
    "update",
    "check",
    "submit",
    "prepare",
    "own",
)

DECISION_MARKERS = (
    "decided",
    "decision",
    "agreed",
    "approved",
    "rejected",
    "will remain",
    "should not be changed",
    "not changing",
)

DATE_PATTERN = re.compile(
    r"\b(today|tomorrow|next week|next month|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"january|february|march|april|may|june|july|august|september|october|november|december)\b",
    flags=re.IGNORECASE,
)


def clean_live_segment_text(text: str) -> str:
    return " ".join(str(text or "").split())


def segments_overlap(previous: str, current: str) -> bool:
    previous_clean = " ".join(previous.lower().split())
    current_clean = " ".join(current.lower().split())
    if not previous_clean or not current_clean:
        return False
    if previous_clean in current_clean or current_clean in previous_clean:
        return True
    previous_tail = " ".join(previous_clean.split()[-6:])
    current_head = " ".join(current_clean.split()[:6])
    return bool(previous_tail and current_head and (previous_tail in current_clean or current_head in previous_clean))


def append_or_merge_live_row(rows: list[LiveTranscriptRow], timestamp: str, speaker: str, text: str, is_partial: bool) -> None:
    if not rows:
        rows.append((timestamp, speaker, text, is_partial))
        return
    last_timestamp, last_speaker, last_text, last_partial = rows[-1]
    same_speaker = last_speaker == speaker
    if not same_speaker:
        rows.append((timestamp, speaker, text, is_partial))
        return
    if last_partial:
        rows[-1] = (timestamp if not is_partial else last_timestamp, speaker, text, is_partial)
        return
    if segments_overlap(last_text, text):
        rows[-1] = (timestamp, speaker, text, is_partial)
        return
    if is_partial:
        rows[-1] = (last_timestamp, speaker, f"{last_text.rstrip()} {text.lstrip()}", True)
        return
    merged = f"{last_text.rstrip()} {text.lstrip()}"
    if len(merged) <= 420:
        rows[-1] = (last_timestamp, speaker, merged, False)
    else:
        rows.append((timestamp, speaker, text, is_partial))


def tentative_insights_from_live_rows(rows: list[LiveTranscriptRow]) -> MeetingInsights:
    insights = MeetingInsights()
    seen: set[str] = set()
    final_rows = [row for row in rows if len(row) >= 4 and not row[3]]
    for _timestamp, _speaker, text, _partial in final_rows[-12:]:
        for sentence in live_candidate_sentences(text):
            lowered = sentence.lower()
            if looks_like_live_action(sentence):
                add_tentative_item(insights.actions, tentative_action_from_sentence(sentence), seen)
            if looks_like_live_date(lowered):
                add_tentative_item(
                    insights.dates,
                    InsightItem(
                        kind="date",
                        text=sentence,
                        due_date=tentative_due_label(sentence),
                        context=sentence,
                        confidence="Tentative",
                    ),
                    seen,
                )
            if looks_like_live_decision(lowered):
                add_tentative_item(insights.decisions, InsightItem(kind="decision", text=sentence, confidence="Tentative"), seen)
    if insights.actions or insights.decisions or insights.dates:
        insights.quality_warnings.append("Live candidates need review after final notes are generated.")
    insights.actions = insights.actions[:5]
    insights.decisions = insights.decisions[:4]
    insights.dates = insights.dates[:4]
    return insights


def live_candidate_sentences(text: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?])\s+|\s+-\s+", text)
    return [piece.strip(" .") for piece in pieces if len(piece.strip()) >= 24]


def looks_like_live_action(sentence: str) -> bool:
    lowered = sentence.lower()
    owner_pattern = r"\b[A-Z][a-z]+\s+(owns|will|to|should|needs to|need to)\b"
    return bool(re.search(owner_pattern, sentence)) or any(word in lowered for word in ACTION_WORDS)


def looks_like_live_date(lowered: str) -> bool:
    return bool(DATE_PATTERN.search(lowered))


def looks_like_live_decision(lowered: str) -> bool:
    return any(marker in lowered for marker in DECISION_MARKERS)


def tentative_due_label(sentence: str) -> str:
    match = DATE_PATTERN.search(sentence)
    return match.group(1).title() if match else "Mentioned live"


def tentative_action_from_sentence(sentence: str) -> InsightItem:
    owner = "Unknown"
    match = re.search(r"\b([A-Z][a-z]+)\s+(owns|will|to|should|needs to|need to)\b", sentence)
    if match:
        owner = match.group(1)
    due = tentative_due_label(sentence) if looks_like_live_date(sentence.lower()) else "Unknown"
    return InsightItem(kind="action", text=sentence, owner=owner, due_date=due, confidence="Tentative")


def add_tentative_item(items: list[InsightItem], item: InsightItem, seen: set[str]) -> None:
    key = re.sub(r"\s+", " ", f"{item.kind}:{item.owner}:{item.due_date}:{item.text}".lower()).strip()
    if key in seen:
        return
    seen.add(key)
    items.append(item)
