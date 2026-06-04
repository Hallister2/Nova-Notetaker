from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from app.intelligence.ollama_client import OllamaClient, NotesResult


class OpenAIClient:
    def __init__(self, settings: dict[str, Any]) -> None:
        ai = settings.get("ai", {})
        self.api_key = str(ai.get("openai_api_key", "")).strip()
        self.model = str(ai.get("openai_model", "gpt-4o")).strip() or "gpt-4o"
        self.timeout_seconds = int(ai.get("timeout_seconds", 180))

    def generate_meeting_notes(self, transcript: str, profile_context: str = "") -> NotesResult:
        if not transcript.strip():
            return NotesResult(text="", success=False, warning="No transcript text is available for OpenAI summarization.")
        if not self.api_key:
            return NotesResult(text="", success=False, warning="OpenAI API key is not configured.")

        required_sections = OllamaClient._preferred_sections_from_context(profile_context)
        prompt = OllamaClient._build_prompt(transcript, profile_context=profile_context)
        try:
            text, warning = self._call_api(prompt)
            if not text:
                return NotesResult(text="", success=False, warning="OpenAI returned an empty meeting note.")
            if not OllamaClient._has_required_sections(text, required_sections):
                retry_prompt = OllamaClient._build_format_retry_prompt(text, required_sections)
                retry_text, retry_warning = self._call_api(retry_prompt)
                if retry_text and OllamaClient._has_required_sections(retry_text, required_sections):
                    return NotesResult(text=retry_text, success=True)
                warning_parts = ["OpenAI returned notes without the required Nova sections.", warning or "", retry_warning or ""]
                warning = " ".join(p for p in warning_parts if p).strip()
            return NotesResult(text=text, success=True, warning=warning)
        except Exception as error:
            return NotesResult(text="", success=False, warning=f"OpenAI summarization failed: {error}")

    def _call_api(self, prompt: str) -> tuple[str, str | None]:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            return "", f"OpenAI API error: {response.status_code} {response.text[:500]}"
        payload = response.json()
        text = str(payload.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
        return OllamaClient._clean_notes(text), None
