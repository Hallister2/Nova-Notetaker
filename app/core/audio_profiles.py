from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from app.core.settings import CONFIG_DIR

AUDIO_PROFILES_PATH = CONFIG_DIR / "audio_profiles.json"


@dataclass(frozen=True)
class AudioProfile:
    device_name: str
    sample_rate: int
    channels: int
    source: str = "observed"
    updated_at: str = ""

    @property
    def detail(self) -> str:
        return f"{self.sample_rate} Hz / {self.channels} ch"


def profile_key(device_name: str) -> str:
    return device_name.strip().lower()


def load_audio_profiles() -> dict[str, AudioProfile]:
    if not AUDIO_PROFILES_PATH.exists():
        return {}
    try:
        data = json.loads(AUDIO_PROFILES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    profiles: dict[str, AudioProfile] = {}
    for raw in data.get("profiles", []):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("device_name", "")).strip()
        if not name:
            continue
        try:
            profiles[profile_key(name)] = AudioProfile(
                device_name=name,
                sample_rate=int(raw.get("sample_rate") or 48000),
                channels=int(raw.get("channels") or 2),
                source=str(raw.get("source", "observed")),
                updated_at=str(raw.get("updated_at", "")),
            )
        except Exception:
            continue
    return profiles


def save_audio_profile(device_name: str, sample_rate: int, channels: int, source: str = "observed") -> AudioProfile:
    profiles = load_audio_profiles()
    profile = AudioProfile(
        device_name=device_name,
        sample_rate=int(sample_rate),
        channels=int(channels),
        source=source,
        updated_at=datetime.now().isoformat(timespec="seconds"),
    )
    profiles[profile_key(device_name)] = profile
    AUDIO_PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIO_PROFILES_PATH.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "device_name": item.device_name,
                        "sample_rate": item.sample_rate,
                        "channels": item.channels,
                        "source": item.source,
                        "updated_at": item.updated_at,
                    }
                    for item in sorted(profiles.values(), key=lambda value: value.device_name.lower())
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return profile


def find_audio_profile(device_name: str | None) -> AudioProfile | None:
    if not device_name:
        return None
    return load_audio_profiles().get(profile_key(device_name))
