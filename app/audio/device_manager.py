from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal


@dataclass(frozen=True)
class AudioDevice:
    name: str
    index: int | None
    kind: Literal["input", "output", "loopback", "unknown"]
    host_api: str = ""
    channels: int = 0
    sample_rate: int | None = None

    @property
    def label(self) -> str:
        if self.kind == "input" and self.host_api == "Windows WASAPI":
            return self.name
        suffix = f" [{self.host_api}]" if self.host_api else ""
        return f"{self.name}{suffix}"


class AudioDeviceManager:
    def list_microphones(self) -> list[AudioDevice]:
        devices: list[AudioDevice] = []
        try:
            import sounddevice as sd
            hostapis = sd.query_hostapis()
            for index, raw in enumerate(sd.query_devices()):
                if int(raw.get("max_input_channels", 0)) <= 0:
                    continue
                host_api = hostapis[raw["hostapi"]]["name"]
                devices.append(
                    AudioDevice(
                        name=str(raw["name"]),
                        index=index,
                        kind="input",
                        host_api=host_api,
                        channels=int(raw.get("max_input_channels", 0)),
                        sample_rate=int(raw.get("default_samplerate", 0)) or None,
                    )
                )
        except Exception:
            return []
        return self._filter_microphones_for_ui(devices)

    def default_microphone(self) -> AudioDevice | None:
        try:
            import sounddevice as sd

            hostapis = sd.query_hostapis()
            raw = sd.query_devices(kind="input")
            index = int(raw.get("index", sd.default.device[0] if sd.default.device else -1))
            host_api = hostapis[raw["hostapi"]]["name"]
            return AudioDevice(
                name=str(raw["name"]),
                index=index,
                kind="input",
                host_api=host_api,
                channels=int(raw.get("max_input_channels", 0)),
                sample_rate=int(raw.get("default_samplerate", 0)) or None,
            )
        except Exception:
            return None

    def list_wasapi_loopbacks(self) -> list[AudioDevice]:
        devices: list[AudioDevice] = []
        try:
            import pyaudiowpatch as pyaudio
            pa = pyaudio.PyAudio()
            try:
                for raw in pa.get_loopback_device_info_generator():
                    devices.append(
                        AudioDevice(
                            name=str(raw.get("name", "Unknown loopback")),
                            index=int(raw.get("index")),
                            kind="loopback",
                            host_api="WASAPI loopback",
                            channels=int(raw.get("maxInputChannels", 0)) or 2,
                            sample_rate=int(raw.get("defaultSampleRate", 0)) or None,
                        )
                    )
            finally:
                pa.terminate()
        except Exception:
            return []
        return devices

    def default_wasapi_loopback(self) -> AudioDevice | None:
        try:
            import pyaudiowpatch as pyaudio
            pa = pyaudio.PyAudio()
            try:
                raw = pa.get_default_wasapi_loopback()
                return AudioDevice(
                    name=str(raw.get("name", "Default output loopback")),
                    index=int(raw.get("index")),
                    kind="loopback",
                    host_api="WASAPI loopback",
                    channels=int(raw.get("maxInputChannels", 0)) or 2,
                    sample_rate=int(raw.get("defaultSampleRate", 0)) or None,
                )
            finally:
                pa.terminate()
        except Exception:
            return None

    @classmethod
    def _filter_microphones_for_ui(cls, devices: list[AudioDevice]) -> list[AudioDevice]:
        visible = [device for device in devices if not cls._is_audio_alias(device)]
        wasapi_devices = [device for device in visible if device.host_api == "Windows WASAPI"]
        if wasapi_devices:
            visible = wasapi_devices

        ranked = sorted(visible, key=cls._microphone_rank)

        deduped: dict[str, AudioDevice] = {}
        for device in ranked:
            key = cls._physical_device_key(device.name)
            if key not in deduped:
                deduped[key] = device

        return list(deduped.values())

    @staticmethod
    def _is_audio_alias(device: AudioDevice) -> bool:
        name = device.name.lower()
        alias_fragments = (
            "microsoft sound mapper",
            "primary sound capture driver",
        )
        return any(fragment in name for fragment in alias_fragments)

    @staticmethod
    def _microphone_rank(device: AudioDevice) -> tuple[int, str]:
        host_rank = {
            "Windows WASAPI": 0,
            "MME": 1,
            "Windows DirectSound": 2,
            "Windows WDM-KS": 3,
        }.get(device.host_api, 9)
        return host_rank, device.name.lower()

    @staticmethod
    def _physical_device_key(name: str) -> str:
        key = name.lower()
        key = re.sub(r"\s+", " ", key)
        key = re.sub(r"\s*\(\d+-\s*", " (", key)
        return key.strip()
