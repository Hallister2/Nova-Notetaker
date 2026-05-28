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

    def test_prompt_uses_preferred_template_sections(self) -> None:
        context = (
            "Template: Technical Change Session\n"
            "Preferred sections: Purpose / Objective, Current State, Proposed Change, Test Plan, Open Questions"
        )

        prompt = OllamaClient._build_prompt("Discussed OneDrive GPO changes.", profile_context=context)

        self.assertIn("## Purpose / Objective", prompt)
        self.assertIn("## Current State", prompt)
        self.assertIn("## Test Plan", prompt)
        self.assertNotIn("## Key Decisions\n## Action Items\n## Important Dates", prompt)
        self.assertIn("Technical change session rules", prompt)
        self.assertIn("Proposed Change should contain candidate or planned technical changes", prompt)
        self.assertIn("Action Items must be explicit assigned work", prompt)

    def test_required_section_validation_accepts_template_sections(self) -> None:
        required = ["Purpose / Objective", "Current State", "Test Plan"]
        notes = "\n".join(
            [
                "## Purpose / Objective",
                "- Test OneDrive policy.",
                "## Current State",
                "- Legacy policy exists.",
                "## Test Plan",
                "- Validate user-based redirection.",
            ]
        )

        self.assertTrue(OllamaClient._has_required_sections(notes, required))
        self.assertFalse(OllamaClient._has_required_sections(notes, ["Summary"]))

    def test_format_retry_prompt_uses_template_sections(self) -> None:
        prompt = OllamaClient._build_format_retry_prompt("Bad notes", ["Purpose / Objective", "Test Plan"])

        self.assertIn("## Purpose / Objective", prompt)
        self.assertIn("## Test Plan", prompt)
        self.assertNotIn("## Summary", prompt)

    def test_prompt_guards_against_invented_action_fields(self) -> None:
        prompt = OllamaClient._build_prompt("Chad, please verify the local recordings.")

        self.assertIn("Do not invent facts", prompt)
        self.assertIn("Keep confidence only in the Confidence field", prompt)
        self.assertIn("Do not assign tasks to Nova", prompt)
        self.assertIn("Mark uncertain owners or dates as Unknown", prompt)
        self.assertIn("Do not use glossary/context terms as owners", prompt)
        self.assertIn("Do not use Everybody, everyone", prompt)

    def test_prompt_handles_source_separated_overlap(self) -> None:
        prompt = OllamaClient._build_prompt(
            "# Source-Separated Transcript\n\n"
            "## Speaker Audio\nPlease send the report Friday.\n\n"
            "## Microphone Audio\nI will send the report Friday."
        )

        self.assertIn("Speaker Audio and Microphone Audio may contain overlapping phrases", prompt)
        self.assertIn("Treat overlapping phrases across sources as duplicate evidence", prompt)
        self.assertIn("Do not omit unique information that appears in only one source", prompt)
