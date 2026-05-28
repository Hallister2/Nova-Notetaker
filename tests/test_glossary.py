from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from app.core.glossary import glossary_hotwords, glossary_prompt_context, load_glossary_terms


class GlossaryTests(TestCase):
    def test_load_glossary_terms_seeds_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            terms = load_glossary_terms(Path(temp_dir) / "glossary.json")

            self.assertIn("OneDrive", terms)
            self.assertIn("GPO", terms)
            self.assertIn("Storage Sense", terms)

    def test_load_glossary_terms_preserves_custom_terms_and_adds_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "glossary.json"
            path.write_text('{"terms": ["Custom App"]}', encoding="utf-8")

            terms = load_glossary_terms(path)

            self.assertIn("Custom App", terms)
            self.assertIn("OneDrive", terms)

    def test_glossary_context_and_hotwords_include_terms(self) -> None:
        terms = ["OneDrive", "GPO"]

        self.assertIn("IT glossary", glossary_prompt_context(terms))
        self.assertIn("ADS may be misheard as APIs or ABS", glossary_prompt_context(terms))
        self.assertEqual(glossary_hotwords(terms), "OneDrive, GPO")
