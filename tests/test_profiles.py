from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from app.core.profiles import MeetingProfile, ProfileStore


class ProfileTests(TestCase):
    def test_profile_store_seeds_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProfileStore(Path(temp_dir) / "profiles.json")

            profiles = store.list_profiles()

            self.assertTrue(profiles)
            self.assertEqual(profiles[0].id, "general")

    def test_profile_prompt_context_contains_fields(self) -> None:
        profile = MeetingProfile(
            id="vendor",
            name="Vendor Review",
            category="Vendor Call",
            company_conducting="Nova",
            companies_attending="Contoso",
            default_note_template_id="vendor_call",
            ai_context="Vendor status review.",
            notes_focus="Risks and commitments.",
        )

        context = profile.to_prompt_context()

        self.assertIn("Vendor Review", context)
        self.assertIn("Contoso", context)
        self.assertIn("vendor_call", context)
        self.assertIn("Risks and commitments.", context)

    def test_profile_store_makes_unique_ids(self) -> None:
        profile_id = ProfileStore.make_id("Project Sync", {"project_sync"})

        self.assertEqual(profile_id, "project_sync_2")

    def test_profile_store_reads_profiles_without_default_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles.json"
            path.write_text(
                '[{"id":"legacy","name":"Legacy Profile","category":"General Meeting"}]',
                encoding="utf-8",
            )
            store = ProfileStore(path)

            profile = store.get_profile("legacy")

            self.assertEqual(profile.name, "Legacy Profile")
            self.assertEqual(profile.default_note_template_id, "")
