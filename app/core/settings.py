from __future__ import annotations

import json
from pathlib import Path
from typing import Any

APP_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = APP_ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "app": {
        "name": "Nova Notetaker",
        "theme": "executive_dark",
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
        "timeout_seconds": 120,
        "long_audio_chunk_seconds": 180,
    },
    "storage": {
        "meetings_dir": "meetings",
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


def _merge_defaults(defaults: dict[str, Any], loaded: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(defaults))
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged
