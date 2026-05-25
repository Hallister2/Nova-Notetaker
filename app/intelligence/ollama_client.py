from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from app.intelligence.note_hints import build_note_hints


@dataclass
class NotesResult:
    text: str
    success: bool
    warning: str | None = None


class OllamaClient:
    def __init__(self, settings: dict[str, Any]) -> None:
        ai = settings.get("ai", {})
        self.url = str(ai.get("ollama_url", "http://localhost:11434")).rstrip("/")
        self.model = str(ai.get("ollama_model", "llama3.1:latest"))
        self.timeout_seconds = int(ai.get("timeout_seconds", 180))

    def generate_meeting_notes(self, transcript: str) -> NotesResult:
        if not transcript.strip():
            return NotesResult(
                text="",
                success=False,
                warning="No transcript text is available for Ollama summarization.",
            )

        prompt = self._build_prompt(transcript)
        try:
            response = requests.post(
                f"{self.url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                    },
                },
                timeout=self.timeout_seconds,
            )
            if not response.ok:
                return NotesResult(
                    text="",
                    success=False,
                    warning=f"Ollama summarization failed: {response.status_code} {response.text[:500]}",
                )
            payload = response.json()
            text = self._clean_notes(str(payload.get("response", "")).strip())
            if not text:
                return NotesResult(
                    text="",
                    success=False,
                    warning="Ollama returned an empty meeting note.",
                )
            return NotesResult(text=text, success=True)
        except Exception as error:
            return NotesResult(
                text="",
                success=False,
                warning=f"Ollama summarization failed: {error}",
            )

    @staticmethod
    def _build_prompt(transcript: str) -> str:
        hints = build_note_hints(transcript)
        hint_block = f"\n\n{hints}\n" if hints else ""
        return (
            "You are Nova Notetaker. Convert this meeting transcript into clean Markdown notes.\n"
            "Return only Markdown notes. Do not include an introduction, explanation, or duplicate title.\n"
            "Use these exact top-level sections:\n"
            "## Summary\n"
            "## Key Decisions\n"
            "## Action Items\n"
            "## Important Dates\n"
            "## Risks / Blockers\n"
            "## Follow-ups\n\n"
            "Rules:\n"
            "- Do not invent facts.\n"
            "- If a section has no evidence, write '- None captured.'\n"
            "- Preserve concrete dates, names, systems, and commitments.\n\n"
            "Action item format:\n"
            "- Owner: <person or Unknown>; Task: <specific task>; Due: <date or Unknown>; Confidence: <High, Medium, or Low>\n"
            "- Use Unknown when the transcript does not clearly name an owner or due date.\n"
            "- Do not assign tasks to Nova unless the transcript explicitly says Nova owns the task.\n"
            "- If an item is inferred from noisy transcript text, mark Confidence: Low.\n\n"
            "Classify direct requests as action items, including phrases like 'please confirm', "
            "'please verify', 'please add', 'please send', 'will own', 'owns', or 'will post'.\n"
            "Do not omit lower-confidence requested tasks. Include them as Action Items with Confidence: Low.\n"
            "For direct address, infer the owner from the name before the comma, such as 'Chad, please confirm...'.\n"
            "Do not move a concrete requested task into Follow-ups if it has an owner or implied owner.\n"
            "Follow-ups are only broad next steps without a clear owner.\n\n"
            "Important date format:\n"
            "- Date: <date>; Context: <what it refers to>; Confidence: <High, Medium, or Low>\n\n"
            f"{hint_block}"
            f"Transcript:\n{transcript}"
        )

    @staticmethod
    def _clean_notes(text: str) -> str:
        lines = text.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        prefaces = (
            "here are the meeting notes",
            "here's the meeting notes",
            "here are your meeting notes",
        )
        if lines and lines[0].strip().lower().rstrip(":") in prefaces:
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)
        if lines and lines[0].strip().lower() == "# meeting notes":
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)
        return "\n".join(lines).strip()
