from __future__ import annotations

import json
from pathlib import Path

from app.core.settings import CONFIG_DIR


GLOSSARY_PATH = CONFIG_DIR / "glossary.json"

DEFAULT_GLOSSARY_TERMS = [
    "Active Directory",
    "ADS",
    "BDI",
    "Documents Redirection",
    "GPO",
    "GPP",
    "Group Policy",
    "item-level targeting",
    "MDCO",
    "MBCO",
    "OneDrive",
    "OU",
    "registry setting",
    "Storage Sense",
    "UMI Documents",
    "user hive",
    "user-based redirection",
    "WAN",
    "WCO",
    "WSO",
    "WSTO",
]

COMMON_TRANSCRIPTION_CORRECTIONS = [
    "ADS may be misheard as APIs or ABS in policy/GPO discussions.",
    "GPO may be transcribed as GBO or GBO projects.",
    "Folder Redirection may be transcribed as photo redirection, fighting chip, documentary direction, or backbench redirection.",
    "OneDrive may be transcribed as one drive or one drop.",
    "UMI Documents may be transcribed as you my documents or View my documents.",
    "OU may be confused with group; preserve the uncertainty if the speaker corrects it.",
]


def load_glossary_terms(path: Path = GLOSSARY_PATH) -> list[str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        save_glossary_terms(DEFAULT_GLOSSARY_TERMS, path)
        return list(DEFAULT_GLOSSARY_TERMS)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        save_glossary_terms(DEFAULT_GLOSSARY_TERMS, path)
        return list(DEFAULT_GLOSSARY_TERMS)

    if isinstance(data, dict):
        raw_terms = data.get("terms", [])
    else:
        raw_terms = data

    terms = _normalize_terms(raw_terms if isinstance(raw_terms, list) else [])
    if not terms:
        terms = list(DEFAULT_GLOSSARY_TERMS)
    merged = _merge_terms(terms, DEFAULT_GLOSSARY_TERMS)
    if merged != terms:
        save_glossary_terms(merged, path)
    return merged


def save_glossary_terms(terms: list[str], path: Path = GLOSSARY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"terms": _normalize_terms(terms)}, indent=2), encoding="utf-8")


def glossary_prompt_context(terms: list[str] | None = None) -> str:
    terms = _normalize_terms(terms if terms is not None else load_glossary_terms())
    if not terms:
        return ""
    return (
        "IT glossary / domain vocabulary:\n"
        + ", ".join(terms)
        + "\nCommon transcription corrections:\n"
        + "\n".join(f"- {correction}" for correction in COMMON_TRANSCRIPTION_CORRECTIONS)
    )


def glossary_hotwords(terms: list[str] | None = None) -> str:
    return ", ".join(_normalize_terms(terms if terms is not None else load_glossary_terms()))


def _merge_terms(existing: list[str], defaults: list[str]) -> list[str]:
    merged = list(existing)
    seen = {term.lower(): term for term in merged}
    for term in defaults:
        key = term.lower()
        if key not in seen:
            merged.append(term)
            seen[key] = term
    return merged


def _normalize_terms(terms: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for term in terms:
        value = str(term).strip()
        key = value.lower()
        if not value or key in seen:
            continue
        normalized.append(value)
        seen.add(key)
    return normalized
