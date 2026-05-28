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

    def generate_meeting_notes(self, transcript: str, profile_context: str = "") -> NotesResult:
        if not transcript.strip():
            return NotesResult(
                text="",
                success=False,
                warning="No transcript text is available for Ollama summarization.",
            )

        required_sections = self._preferred_sections_from_context(profile_context)
        prompt = self._build_prompt(transcript, profile_context=profile_context)
        try:
            text, warning = self._generate_notes_text(prompt)
            if not text:
                return NotesResult(
                    text="",
                    success=False,
                    warning="Ollama returned an empty meeting note.",
                )
            if not self._has_required_sections(text, required_sections):
                retry_prompt = self._build_format_retry_prompt(text, required_sections)
                retry_text, retry_warning = self._generate_notes_text(retry_prompt)
                if retry_text and self._has_required_sections(retry_text, required_sections):
                    return NotesResult(text=retry_text, success=True)
                warning_parts = [
                    "Ollama returned notes without the required Nova sections.",
                    warning or "",
                    retry_warning or "",
                ]
                warning = " ".join(part for part in warning_parts if part).strip()
            return NotesResult(text=text, success=True)
        except Exception as error:
            return NotesResult(
                text="",
                success=False,
                warning=f"Ollama summarization failed: {error}",
            )

    def _generate_notes_text(self, prompt: str) -> tuple[str, str | None]:
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
            return "", f"Ollama summarization failed: {response.status_code} {response.text[:500]}"
        payload = response.json()
        return self._clean_notes(str(payload.get("response", "")).strip()), None

    @staticmethod
    def _build_prompt(transcript: str, profile_context: str = "") -> str:
        hints = build_note_hints(transcript)
        hint_block = f"\n\n{hints}\n" if hints else ""
        profile_block = f"\nMeeting profile context:\n{profile_context}\n" if profile_context.strip() else ""
        required_sections = OllamaClient._preferred_sections_from_context(profile_context)
        section_block = "".join(f"## {section}\n" for section in required_sections)
        technical_rules = OllamaClient._technical_session_rules(required_sections)
        return (
            "You are Nova Notetaker. Convert this meeting transcript into clean Markdown notes.\n"
            "Return only Markdown notes. Do not include an introduction, explanation, or duplicate title.\n"
            "Use these exact top-level sections, in this order:\n"
            f"{section_block}\n"
            "Rules:\n"
            "- Do not invent facts.\n"
            "- If a section has no evidence, write '- None captured.'\n"
            "- Preserve concrete dates, names, systems, and commitments.\n\n"
            "Evidence fidelity rules:\n"
            "- Meeting-specific context may explain the purpose and vocabulary, but transcript evidence controls factual details.\n"
            "- If the transcript wording is garbled or uncertain, either omit the detail or label it as unclear; do not smooth it into a confident fact.\n"
            "- Do not convert proposed ideas, examples, risks, or test observations into decisions or action items.\n\n"
            "Source-separated transcript rules:\n"
            "- Speaker Audio and Microphone Audio may contain overlapping phrases because speakers and microphones can capture the same words.\n"
            "- Treat overlapping phrases across sources as duplicate evidence, not separate events.\n"
            "- Include a duplicated action, date, decision, risk, or follow-up only once in the final notes.\n"
            "- Prefer the clearer/more complete wording when the two sources overlap.\n"
            "- Do not omit unique information that appears in only one source.\n\n"
            "Key Decisions rules:\n"
            "- Include only explicit choices, approvals, rejected options, direction changes, or agreements.\n"
            "- Do not list ordinary assignments, deadlines, or status updates as decisions.\n"
            "- If a bullet has an owner and task, it belongs in Action Items, not Key Decisions.\n\n"
            "Action item format:\n"
            "- Owner: <person or Unknown>; Task: <specific task>; Due: <date or Unknown>; Confidence: <High, Medium, or Low>\n"
            "- Use Unknown when the transcript does not clearly name an owner or due date.\n"
            "- Do not assign tasks to Nova unless the transcript explicitly says Nova owns the task.\n"
            "- Do not use Everybody, everyone, the meeting, or broad audiences as owners; use Unknown instead.\n"
            "- Do not use system names, products, dashboards, teams, or tools as owners unless the transcript clearly assigns ownership to them.\n"
            "- Keep confidence only in the Confidence field. Do not append '(High)', '(Medium)', or '(Low)' to Owner, Task, Due, Date, or Context.\n"
            "- Mark uncertain owners or dates as Unknown instead of guessing from surrounding text.\n"
            "- If an item is inferred from noisy transcript text, mark Confidence: Low.\n\n"
            f"{technical_rules}"
            "Classify direct requests as action items, including phrases like 'please confirm', "
            "'please verify', 'please add', 'please send', 'will own', 'owns', or 'will post'.\n"
            "Do not omit lower-confidence requested tasks. Include them as Action Items with Confidence: Low.\n"
            "For direct address, infer the owner from the name before the comma, such as 'Chad, please confirm...'.\n"
            "Do not move a concrete requested task into Follow-ups if it has an owner or implied owner.\n"
            "Follow-ups are only broad next steps without a clear owner.\n\n"
            "Important date format:\n"
            "- Date: <date>; Context: <what it refers to>; Confidence: <High, Medium, or Low>\n\n"
            "Use the meeting profile context to tune emphasis and terminology, but do not invent facts from it.\n"
            "Use glossary/context terms to correct obvious transcription vocabulary mistakes when the meeting evidence supports it.\n"
            "Do not use glossary/context terms as owners unless the transcript clearly assigns work to that person or team.\n"
            f"{hint_block}"
            f"{profile_block}\n"
            f"Transcript:\n{transcript}"
        )

    @staticmethod
    def _build_format_retry_prompt(notes: str, required_sections: list[str] | None = None) -> str:
        sections = required_sections or OllamaClient._default_required_sections()
        section_block = "".join(f"## {section}\n" for section in sections)
        return (
            "Your previous Nova Notetaker response did not follow the required Markdown format.\n"
            "Rewrite the notes below using exactly these top-level sections, in this order:\n"
            f"{section_block}\n"
            "Return only Markdown notes. Do not add a title or explanation.\n"
            "If a section has no evidence, write '- None captured.'\n\n"
            "Action item format:\n"
            "- Owner: <person or Unknown>; Task: <specific task>; Due: <date or Unknown>; Confidence: <High, Medium, or Low>\n\n"
            "Do not invent owners or due dates. Keep confidence only in the Confidence field.\n\n"
            "Important date format:\n"
            "- Date: <date>; Context: <what it refers to>; Confidence: <High, Medium, or Low>\n\n"
            f"Notes to rewrite:\n{notes}"
        )

    @staticmethod
    def _has_required_sections(text: str, required_sections: list[str] | None = None) -> bool:
        lowered = text.lower()
        required = required_sections or OllamaClient._default_required_sections()
        return all(f"## {section.lower()}" in lowered for section in required)

    @staticmethod
    def _preferred_sections_from_context(profile_context: str) -> list[str]:
        for raw_line in profile_context.splitlines():
            if raw_line.lower().startswith("preferred sections:"):
                raw_sections = raw_line.split(":", 1)[1]
                sections = [section.strip() for section in raw_sections.split(",") if section.strip()]
                if sections:
                    return sections
        return OllamaClient._default_required_sections()

    @staticmethod
    def _default_required_sections() -> list[str]:
        return [
            "Summary",
            "Key Decisions",
            "Action Items",
            "Important Dates",
            "Risks / Blockers",
            "Follow-ups",
        ]

    @staticmethod
    def _technical_session_rules(required_sections: list[str]) -> str:
        lowered = {section.lower() for section in required_sections}
        if "test plan" not in lowered and "proposed change" not in lowered:
            return ""
        return (
            "Technical change session rules:\n"
            "- Purpose / Objective can use the meeting-specific context when it describes why the meeting happened.\n"
            "- Current State should describe only existing conditions, not proposed fixes.\n"
            "- Proposed Change should contain candidate or planned technical changes that are not clearly finalized.\n"
            "- Decisions should include only explicit decisions, approvals, or agreed direction. If the transcript says 'suggestion', 'theory', 'test', or 'we need to see', place it under Proposed Change, Test Plan, or Open Questions instead.\n"
            "- Test Plan should capture validation scenarios, test users/accounts, group targeting checks, migration behavior to verify, and access checks.\n"
            "- Action Items must be explicit assigned work or direct requests. Do not include broken phrases like 'say okay', 'does a match', or organization/acronym statements such as 'ADS will not mirror'.\n"
            "- If a work item is real but the owner is unclear, use Owner: Unknown; if the work item itself is unclear, omit it.\n\n"
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
