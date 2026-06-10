from __future__ import annotations

import shutil
import socket
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import requests
import websocket

from app.audio.capture_service import CaptureConfig, CaptureService
from app.audio.device_manager import AudioDevice


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    passed: bool
    detail: str
    critical: bool = True

    @property
    def label(self) -> str:
        return f"{'OK' if self.passed else 'Review'} - {self.name}: {self.detail}"


def run_capture_preflight_checks(
    *,
    settings: dict,
    meetings_root: Path,
    mic_device: AudioDevice | None,
    loopback_device: AudioDevice | None,
    capture_mic: bool,
    mic_channels: int,
    loopback_channels: int,
    check_ai: bool = True,
    probe_audio: bool = True,
) -> list[PreflightCheck]:
    checks: list[PreflightCheck] = []
    checks.append(PreflightCheck("Microphone", bool(mic_device) or not capture_mic, _device_detail(mic_device) if mic_device else "Muted or unavailable", critical=capture_mic))
    checks.append(PreflightCheck("System audio", bool(loopback_device), _device_detail(loopback_device) if loopback_device else "No WASAPI loopback resolved"))

    checks.extend(_check_storage(meetings_root))
    if probe_audio:
        checks.append(_probe_microphone(settings, mic_device, capture_mic, mic_channels))
        checks.append(_probe_loopback(loopback_device, loopback_channels))
    else:
        checks.append(PreflightCheck("Mic open", True, "Skipped until recording starts", critical=False))
        checks.append(PreflightCheck("System open", True, "Skipped until recording starts", critical=False))

    transcription = settings.get("transcription", {})
    if bool(transcription.get("enabled", False)):
        checks.append(_probe_whisperlive(str(transcription.get("whisperlive_url", "")).strip()))
    else:
        checks.append(PreflightCheck("WhisperLive", True, "Disabled", critical=False))

    if check_ai:
        checks.append(_probe_ai(settings))
    return checks


def summarize_preflight(checks: list[PreflightCheck]) -> tuple[bool, list[str]]:
    critical_ok = all(check.passed or not check.critical for check in checks)
    return critical_ok, [check.label for check in checks]


def _device_detail(device: AudioDevice | None) -> str:
    if device is None:
        return "Unavailable"
    rate = f", {device.sample_rate} Hz" if device.sample_rate else ""
    channels = f", {device.channels} ch" if device.channels else ""
    return f"{device.label}{rate}{channels}"


def _check_storage(meetings_root: Path) -> list[PreflightCheck]:
    try:
        meetings_root.mkdir(parents=True, exist_ok=True)
        probe_path = meetings_root / ".nova_write_test"
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink(missing_ok=True)
        usage = shutil.disk_usage(meetings_root)
        free_gb = usage.free / (1024 ** 3)
        return [
            PreflightCheck("Meeting storage", True, str(meetings_root)),
            PreflightCheck("Free disk space", free_gb >= 2.0, f"{free_gb:.1f} GB available", critical=False),
        ]
    except Exception as error:
        return [PreflightCheck("Meeting storage", False, str(error))]


def _probe_microphone(settings: dict, mic_device: AudioDevice | None, capture_mic: bool, channels: int) -> PreflightCheck:
    if not capture_mic:
        return PreflightCheck("Mic open", True, "Muted", critical=False)
    if mic_device is None:
        return PreflightCheck("Mic open", False, "No microphone selected")
    try:
        import sounddevice as sd
        sample_rate = int((mic_device.sample_rate if mic_device else None) or settings.get("audio", {}).get("sample_rate", 48000) or 48000)
        stream = sd.InputStream(samplerate=sample_rate, channels=channels, dtype="float32", device=mic_device.index)
        try:
            pass
        finally:
            stream.close()
        return PreflightCheck("Mic open", True, f"{sample_rate} Hz / {channels} ch")
    except Exception as error:
        return PreflightCheck("Mic open", False, str(error))


def _probe_loopback(loopback_device: AudioDevice | None, channels: int) -> PreflightCheck:
    if loopback_device is None or loopback_device.index is None:
        return PreflightCheck("System open", False, "No system loopback selected")
    try:
        import pyaudiowpatch as pyaudio
        pa = pyaudio.PyAudio()
        try:
            sample_rate = int(loopback_device.sample_rate or 48000)
            with TemporaryDirectory() as tmp:
                config = CaptureConfig(
                    meeting_folder=Path(tmp),
                    mic_device_index=None,
                    loopback_device_index=loopback_device.index,
                    capture_mic=False,
                    loopback_sample_rate=sample_rate,
                    loopback_channels=channels,
                )
                service = CaptureService(config, lambda _message: None, lambda _source, _level: None)
                stream, opened_channels = service._open_loopback_stream(pa, pyaudio.paInt16, sample_rate, channels, 1024)
                try:
                    if stream.is_active():
                        stream.stop_stream()
                finally:
                    stream.close()
            return PreflightCheck("System open", True, f"{sample_rate} Hz / {opened_channels} ch")
        finally:
            pa.terminate()
    except Exception as error:
        return PreflightCheck("System open", False, str(error))


def _probe_whisperlive(base_url: str) -> PreflightCheck:
    if not base_url:
        return PreflightCheck("WhisperLive", False, "URL is empty")
    try:
        parsed = urlparse(base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        host = parsed.hostname or base_url.replace("http://", "").replace("https://", "")
        port = parsed.port or (443 if scheme == "wss" else 80)
        ws_url = f"{scheme}://{host}:{port}"
        ws = websocket.create_connection(ws_url, timeout=5)
        ws.close()
        return PreflightCheck("WhisperLive", True, ws_url)
    except Exception as error:
        return PreflightCheck("WhisperLive", False, str(error))


def _probe_ai(settings: dict) -> PreflightCheck:
    ai = settings.get("ai", {})
    provider = str(ai.get("provider", "ollama")).lower()
    if provider == "ollama":
        url = str(ai.get("ollama_url", "")).strip().rstrip("/")
        model = str(ai.get("ollama_model", "")).strip()
        try:
            response = requests.get(f"{url}/api/tags", timeout=5)
            response.raise_for_status()
            models = [item.get("name", "") for item in response.json().get("models", []) if isinstance(item, dict)]
            if model and model not in models:
                return PreflightCheck("Ollama", False, f"{model} not found", critical=False)
            return PreflightCheck("Ollama", True, model or "Reachable", critical=False)
        except Exception as error:
            return PreflightCheck("Ollama", False, str(error), critical=False)
    if provider == "openai":
        api_key = str(ai.get("openai_api_key", "")).strip()
        if not api_key:
            return PreflightCheck("OpenAI", False, "API key missing", critical=False)
        try:
            response = requests.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=5)
            return PreflightCheck("OpenAI", response.status_code == 200, "Reachable" if response.status_code == 200 else f"HTTP {response.status_code}", critical=False)
        except Exception as error:
            return PreflightCheck("OpenAI", False, str(error), critical=False)
    if provider == "claude":
        api_key = str(ai.get("claude_api_key", "")).strip()
        if not api_key:
            return PreflightCheck("Claude", False, "API key missing", critical=False)
        try:
            response = requests.get("https://api.anthropic.com/v1/models", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"}, timeout=5)
            return PreflightCheck("Claude", response.status_code == 200, "Reachable" if response.status_code == 200 else f"HTTP {response.status_code}", critical=False)
        except Exception as error:
            return PreflightCheck("Claude", False, str(error), critical=False)
    return PreflightCheck("AI", False, f"Unknown provider {provider}", critical=False)
