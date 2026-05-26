from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.settings import CONFIG_DIR


TEMPLATES_PATH = CONFIG_DIR / "templates.json"


@dataclass(frozen=True)
class NoteTemplate:
    id: str
    name: str
    category: str = "General"
    description: str = ""
    notes_focus: str = ""
    custom_instructions: str = ""
    preferred_sections: str = "Summary, Key Decisions, Action Items, Important Dates, Risks / Blockers, Follow-ups"

    def to_prompt_context(self) -> str:
        lines = [
            f"Template: {self.name}",
            f"Template category: {self.category}",
        ]
        if self.description:
            lines.append(f"Description: {self.description}")
        if self.notes_focus:
            lines.append(f"Notes focus: {self.notes_focus}")
        if self.preferred_sections:
            lines.append(f"Preferred sections: {self.preferred_sections}")
        if self.custom_instructions:
            lines.append(f"Custom instructions: {self.custom_instructions}")
        return "\n".join(lines)


DEFAULT_TEMPLATES = [
    NoteTemplate(
        id="standard",
        name="Standard Meeting Notes",
        category="General",
        description="Balanced notes for most meetings.",
        notes_focus="Capture summary, decisions, action items, dates, risks, and follow-ups.",
    ),
    NoteTemplate(
        id="executive_summary",
        name="Executive Summary",
        category="Executive",
        description="Concise high-signal notes for leadership review.",
        notes_focus="Prioritize outcomes, decisions, risks, deadlines, and owner accountability.",
        custom_instructions="Keep wording concise and avoid transcript-like detail.",
    ),
    NoteTemplate(
        id="project_sync",
        name="Project Sync",
        category="Project",
        description="Project meeting notes with emphasis on delivery and blockers.",
        notes_focus="Prioritize blockers, dependencies, owners, due dates, decisions, and next steps.",
    ),
    NoteTemplate(
        id="vendor_call",
        name="Vendor Call",
        category="Vendor",
        description="Notes for outside vendor or partner meetings.",
        notes_focus="Prioritize commitments, open questions, commercial risks, dates, and accountability.",
    ),
]


class TemplateStore:
    def __init__(self, path: Path = TEMPLATES_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.write_templates(DEFAULT_TEMPLATES)

    def list_templates(self) -> list[NoteTemplate]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.write_templates(DEFAULT_TEMPLATES)
            return list(DEFAULT_TEMPLATES)

        templates = []
        for item in data if isinstance(data, list) else []:
            if isinstance(item, dict):
                templates.append(self._template_from_dict(item))

        if not templates:
            templates = list(DEFAULT_TEMPLATES)
            self.write_templates(templates)
        return templates

    def get_template(self, template_id: str) -> NoteTemplate:
        templates = self.list_templates()
        for template in templates:
            if template.id == template_id:
                return template
        return templates[0]

    def write_templates(self, templates: list[NoteTemplate]) -> None:
        self.path.write_text(json.dumps([asdict(template) for template in templates], indent=2), encoding="utf-8")

    @staticmethod
    def make_id(name: str, existing_ids: set[str]) -> str:
        base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "template"
        candidate = base
        counter = 2
        while candidate in existing_ids:
            candidate = f"{base}_{counter}"
            counter += 1
        return candidate

    @staticmethod
    def _template_from_dict(data: dict[str, Any]) -> NoteTemplate:
        fields = NoteTemplate.__dataclass_fields__
        filtered = {key: value for key, value in data.items() if key in fields}
        return NoteTemplate(**filtered)
