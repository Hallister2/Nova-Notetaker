from __future__ import annotations

import socket
from threading import Thread
from typing import Callable
from urllib.parse import urlparse

import requests


ServiceStatusCallback = Callable[[str, str], None]


def check_services_async(settings: dict, on_result: ServiceStatusCallback) -> None:
    """Run health checks for the active AI provider and WhisperLive in background threads.

    on_result(service_name, status) is called from a non-UI thread;
    the caller must marshal to the UI thread (e.g. via a Qt signal).

    status values: "ok" | "unreachable" | "disabled"
    """
    ai = settings.get("ai", {})
    transcription = settings.get("transcription", {})
    provider = str(ai.get("provider", "ollama")).lower()

    if provider == "ollama":
        ollama_url = str(ai.get("ollama_url", "")).strip().rstrip("/")
        Thread(target=_check_ollama, args=(ollama_url, on_result), daemon=True).start()
        on_result("OpenAI", "disabled")
        on_result("Claude", "disabled")
    elif provider == "openai":
        api_key = str(ai.get("openai_api_key", "")).strip()
        Thread(target=_check_openai, args=(api_key, on_result), daemon=True).start()
        on_result("Ollama", "disabled")
        on_result("Claude", "disabled")
    elif provider == "claude":
        api_key = str(ai.get("claude_api_key", "")).strip()
        Thread(target=_check_claude, args=(api_key, on_result), daemon=True).start()
        on_result("Ollama", "disabled")
        on_result("OpenAI", "disabled")
    else:
        on_result("Ollama", "disabled")
        on_result("OpenAI", "disabled")
        on_result("Claude", "disabled")

    whisper_url = str(transcription.get("whisperlive_url", "")).strip().rstrip("/")
    whisper_enabled = bool(transcription.get("enabled", False))
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
        on_result("Ollama", "ok" if response.status_code == 200 else "unreachable")
    except Exception:
        on_result("Ollama", "unreachable")


def _check_openai(api_key: str, on_result: ServiceStatusCallback) -> None:
    if not api_key:
        on_result("OpenAI", "unreachable")
        return
    try:
        response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8,
        )
        on_result("OpenAI", "ok" if response.status_code == 200 else "unreachable")
    except Exception:
        on_result("OpenAI", "unreachable")


def _check_claude(api_key: str, on_result: ServiceStatusCallback) -> None:
    if not api_key:
        on_result("Claude", "unreachable")
        return
    try:
        response = requests.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=8,
        )
        on_result("Claude", "ok" if response.status_code == 200 else "unreachable")
    except Exception:
        on_result("Claude", "unreachable")


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
