from __future__ import annotations

import json
import socket
from threading import Thread
from typing import Callable
from urllib.parse import urlparse

import requests


ServiceStatusCallback = Callable[[str, str], None]


def check_services_async(settings: dict, on_result: ServiceStatusCallback) -> None:
    """Run health checks for Ollama and WhisperLive in background threads.

    on_result(service_name, status) is called from a non-UI thread;
    the caller must marshal to the UI thread (e.g. via a Qt signal).

    status values: "ok" | "unreachable" | "disabled"
    """
    ai = settings.get("ai", {})
    transcription = settings.get("transcription", {})

    ollama_url = str(ai.get("ollama_url", "")).strip().rstrip("/")
    whisper_url = str(transcription.get("whisperlive_url", "")).strip().rstrip("/")
    whisper_enabled = bool(transcription.get("enabled", False))

    Thread(target=_check_ollama, args=(ollama_url, on_result), daemon=True).start()
    if whisper_enabled:
        Thread(target=_check_whisperlive, args=(whisper_url, on_result), daemon=True).start()
    else:
        on_result("WhisperLive", "disabled")


def _check_ollama(base_url: str, on_result: ServiceStatusCallback) -> None:
    if not base_url:
        on_result("Ollama", "unreachable")
        return
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        if response.status_code == 200:
            on_result("Ollama", "ok")
        else:
            on_result("Ollama", "unreachable")
    except Exception:
        on_result("Ollama", "unreachable")


def _check_whisperlive(base_url: str, on_result: ServiceStatusCallback) -> None:
    if not base_url:
        on_result("WhisperLive", "unreachable")
        return
    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    port = parsed.port or 9090
    try:
        with socket.create_connection((host, port), timeout=5):
            on_result("WhisperLive", "ok")
    except Exception:
        on_result("WhisperLive", "unreachable")
