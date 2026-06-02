from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

APP_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = APP_ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "app": {
        "name": "Nova Notetaker",
        "theme": "executive_dark",
        "selected_profile_id": "general",
        "selected_template_id": "standard",
    },
    "audio": {
        "mic_device_name": "",
        "system_loopback_device_name": "",
        "capture_mic": True,
        "capture_profile": "laptop_speakers",
        "sample_rate": 16000,
        "channels": 1,
    },
    "ai": {
        "provider": "ollama",
        "ollama_url": "http://localhost:11434",
        "ollama_model": "llama3.1:latest",
        "openai_model": "gpt-5.2",
        "timeout_seconds": 180,
    },
    "transcription": {
        "enabled": False,
        "whisperlive_url": "http://localhost:9090",
        "model": "small",
        "language": "en",
        "use_vad": True,
        "cross_bleed_cleanup": True,
        "word_timestamps": False,
        "low_confidence_threshold": 0.4,
        "timeout_seconds": 120,
        "long_audio_chunk_seconds": 180,
        "websocket_chunk_delay_seconds": 0.005,
        "post_audio_quiet_seconds": 5.0,
        "post_audio_max_wait_seconds": 120,
    },
    "storage": {
        "meetings_dir": "meetings",
    },
    "review": {
        "action_auto_close_days": 30,
    },
}


def load_settings() -> dict[str, Any]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_PATH.exists():
        save_settings(DEFAULT_SETTINGS)
        return json.loads(json.dumps(DEFAULT_SETTINGS))

    with SETTINGS_PATH.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)

    return _merge_defaults(DEFAULT_SETTINGS, loaded)


def save_settings(settings: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with SETTINGS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)


def validate_settings(settings: dict[str, Any]) -> list[str]:
    """Return a list of human-readable validation warnings for the given settings dict."""
    issues: list[str] = []
    ai = settings.get("ai", {})
    transcription = settings.get("transcription", {})
    audio = settings.get("audio", {})

    ollama_url = str(ai.get("ollama_url", "")).strip()
    if ollama_url and not _is_valid_url(ollama_url):
        issues.append(f"AI: Ollama URL '{ollama_url}' does not look like a valid URL (expected http://host:port).")

    whisper_url = str(transcription.get("whisperlive_url", "")).strip()
    if whisper_url and not _is_valid_url(whisper_url):
        issues.append(f"Transcription: WhisperLive URL '{whisper_url}' does not look like a valid URL.")

    ollama_model = str(ai.get("ollama_model", "")).strip()
    if not ollama_model:
        issues.append("AI: Ollama model name is empty.")

    whisper_model = str(transcription.get("model", "")).strip()
    if transcription.get("enabled") and whisper_model not in {"tiny", "base", "small", "medium", "large", "large-v2", "large-v3"}:
        issues.append(f"Transcription: Whisper model '{whisper_model}' is not a recognised model name.")

    ai_timeout = ai.get("timeout_seconds", 180)
    if not isinstance(ai_timeout, (int, float)) or int(ai_timeout) < 10:
        issues.append("AI: Timeout must be at least 10 seconds.")

    sample_rate = audio.get("sample_rate", 16000)
    if sample_rate not in {8000, 16000, 22050, 44100, 48000}:
        issues.append(f"Audio: Sample rate {sample_rate} is unusual; expected 16000 or 48000.")

    return issues


def _is_valid_url(url: str) -> bool:
    return bool(re.match(r"^https?://[^\s/$.?#].[^\s]*$", url, re.IGNORECASE))


def _merge_defaults(defaults: dict[str, Any], loaded: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(defaults))
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged
