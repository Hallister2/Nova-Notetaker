from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from app.core.templates import NoteTemplate, TemplateStore
from app.storage.meeting_store import MeetingMetadata
from app.workflows.meeting_processor import MeetingProcessor


class TemplateTests(TestCase):
    def test_template_store_seeds_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TemplateStore(Path(temp_dir) / "templates.json")

            templates = store.list_templates()

            self.assertTrue(templates)
            self.assertEqual(templates[0].id, "standard")

    def test_template_store_round_trips_custom_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "templates.json"
            store = TemplateStore(path)
            template = NoteTemplate(
                id="incident_review",
                name="Incident Review",
                category="Operations",
                notes_focus="Root cause, customer impact, timeline, and follow-up owners.",
                custom_instructions="Call out unresolved questions clearly.",
            )

            store.write_templates([template])
            loaded = store.get_template("incident_review")

            self.assertEqual(loaded.name, "Incident Review")
            self.assertIn("Root cause", loaded.to_prompt_context())
            self.assertIn("unresolved questions", loaded.to_prompt_context())

    def test_template_context_is_used_without_profile_context(self) -> None:
        metadata = MeetingMetadata(
            title="Template Only",
            started_at="2026-05-25T12:00:00",
            meeting_profile={},
            note_template={
                "id": "executive",
                "name": "Executive Brief",
                "category": "Executive",
                "notes_focus": "Decisions and deadlines only.",
            },
        )

        context = MeetingProcessor._profile_prompt_context(metadata)

        self.assertIn("Executive Brief", context)
        self.assertIn("Decisions and deadlines only.", context)
