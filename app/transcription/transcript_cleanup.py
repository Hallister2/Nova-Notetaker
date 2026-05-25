from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.transcription.whisperlive_client import TranscriptionResult


PROFILE_CLEANUP_SETTINGS = {
    "headphones": {
        "enabled": True,
        "similarity_threshold": 0.9,
        "overlap_threshold": 0.75,
    },
    "external_mic_speakers": {
        "enabled": True,
        "similarity_threshold": 0.86,
        "overlap_threshold": 0.65,
    },
    "laptop_speakers": {
        "enabled": True,
        "similarity_threshold": 0.78,
        "overlap_threshold": 0.45,
    },
    "conference_room": {
        "enabled": True,
        "similarity_threshold": 0.8,
        "overlap_threshold": 0.5,
    },
    "debug_raw": {
        "enabled": False,
        "similarity_threshold": 0.82,
        "overlap_threshold": 0.55,
    },
}


def reduce_cross_bleed(
    results: list[TranscriptionResult],
    primary_source: str = "You",
    bleed_source: str = "Meeting",
    similarity_threshold: float = 0.82,
    overlap_threshold: float = 0.55,
) -> tuple[list[TranscriptionResult], list[str]]:
    primary = next((result for result in results if result.source == primary_source), None)
    bleed = next((result for result in results if result.source == bleed_source), None)
    if not primary or not bleed or not primary.text.strip() or not bleed.text.strip():
        return results, []

    bleed_fragments = _split_fragments(bleed.text)
    bleed_words = _normalize(bleed.text).split()
    bleed_normalized = " ".join(bleed_words)
    bleed_ngrams = _build_ngram_sets(bleed_words)
    kept_fragments: list[str] = []
    removed_count = 0

    for fragment in _split_fragments(primary.text):
        if _word_count(fragment) < 5:
            if _word_count(fragment) >= 2 and _normalize(fragment) in bleed_normalized:
                removed_count += 1
                continue
            kept_fragments.append(fragment)
            continue
        if _matches_any(fragment, bleed_fragments, bleed_ngrams, similarity_threshold, overlap_threshold):
            removed_count += 1
            continue
        kept_fragments.append(fragment)

    if not removed_count:
        return results, []

    cleaned_text = _join_fragments(_collapse_repeated_fragments(kept_fragments))
    cleaned_results = [
        TranscriptionResult(
            source=result.source,
            text=cleaned_text if result.source == primary_source else _join_fragments(_collapse_repeated_fragments(_split_fragments(result.text))),
            success=result.success,
            warning=result.warning,
        )
        for result in results
    ]
    warning = f"Removed {removed_count} likely speaker-bleed fragment(s) from the {primary_source} transcript."
    return cleaned_results, [warning]


def reduce_cross_bleed_for_profile(
    results: list[TranscriptionResult],
    profile: str,
) -> tuple[list[TranscriptionResult], list[str]]:
    cleanup_settings = PROFILE_CLEANUP_SETTINGS.get(profile, PROFILE_CLEANUP_SETTINGS["external_mic_speakers"])
    if not cleanup_settings["enabled"]:
        return results, [f"Speaker-bleed cleanup disabled for capture profile: {profile}."]
    return reduce_cross_bleed(
        results,
        similarity_threshold=float(cleanup_settings["similarity_threshold"]),
        overlap_threshold=float(cleanup_settings["overlap_threshold"]),
    )


def _matches_any(
    fragment: str,
    candidates: list[str],
    bleed_ngrams: dict[int, set[tuple[str, ...]]],
    similarity_threshold: float,
    overlap_threshold: float,
) -> bool:
    normalized = _normalize(fragment)
    words = normalized.split()
    max_overlap = _max_ngram_overlap(words, bleed_ngrams)
    if max_overlap >= 7:
        return True
    if len(words) and max_overlap / len(words) >= overlap_threshold and max_overlap >= 4:
        return True

    for candidate in candidates:
        if _word_count(candidate) < 5:
            continue
        candidate_normalized = _normalize(candidate)
        if normalized in candidate_normalized or candidate_normalized in normalized:
            return True
        if SequenceMatcher(None, normalized, candidate_normalized).ratio() >= similarity_threshold:
            return True
    return False


def _split_fragments(text: str) -> list[str]:
    fragments = re.split(r"(?<=[.!?])\s+|\n+|(?<=,)\s+(?=(?:and|but|so|this|that|we|you|i)\b)", text, flags=re.IGNORECASE)
    return [fragment.strip() for fragment in fragments if fragment.strip()]


def _collapse_repeated_fragments(fragments: list[str]) -> list[str]:
    collapsed: list[str] = []
    for fragment in fragments:
        if collapsed and SequenceMatcher(None, _normalize(collapsed[-1]), _normalize(fragment)).ratio() >= 0.9:
            collapsed[-1] = fragment if len(fragment) > len(collapsed[-1]) else collapsed[-1]
        else:
            collapsed.append(fragment)
    return collapsed


def _join_fragments(fragments: list[str]) -> str:
    return " ".join(fragment.strip() for fragment in fragments if fragment.strip()).strip()


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _word_count(text: str) -> int:
    return len(_normalize(text).split())


def _build_ngram_sets(words: list[str], min_n: int = 4, max_n: int = 12) -> dict[int, set[tuple[str, ...]]]:
    ngrams: dict[int, set[tuple[str, ...]]] = {}
    for size in range(min_n, max_n + 1):
        if len(words) < size:
            break
        ngrams[size] = {tuple(words[index:index + size]) for index in range(len(words) - size + 1)}
    return ngrams


def _max_ngram_overlap(words: list[str], bleed_ngrams: dict[int, set[tuple[str, ...]]]) -> int:
    for size in sorted(bleed_ngrams.keys(), reverse=True):
        if len(words) < size:
            continue
        for index in range(len(words) - size + 1):
            if tuple(words[index:index + size]) in bleed_ngrams[size]:
                return size
    return 0
