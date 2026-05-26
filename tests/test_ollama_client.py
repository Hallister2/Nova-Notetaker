from __future__ import annotations

from unittest import TestCase

from app.intelligence.ollama_client import OllamaClient


class OllamaClientTests(TestCase):
    def test_required_section_validation(self) -> None:
        valid_notes = "\n".join(
            [
                "## Summary",
                "- Good meeting.",
                "## Key Decisions",
                "- None captured.",
                "## Action Items",
                "- None captured.",
                "## Important Dates",
                "- None captured.",
                "## Risks / Blockers",
                "- None captured.",
                "## Follow-ups",
                "- None captured.",
            ]
        )

        self.assertTrue(OllamaClient._has_required_sections(valid_notes))
        self.assertFalse(OllamaClient._has_required_sections("This was a meeting summary in prose."))

    def test_format_retry_prompt_includes_previous_notes_and_required_sections(self) -> None:
        prompt = OllamaClient._build_format_retry_prompt("Plain summary text.")

        self.assertIn("## Action Items", prompt)
        self.assertIn("Plain summary text.", prompt)
        self.assertIn("Return only Markdown notes", prompt)
