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
    NoteTemplate(
        id="technical_change_session",
        name="Technical Change Session",
        category="IT / Change",
        description="Technical working-session report for infrastructure, policy, app, or workflow changes.",
        notes_focus=(
            "Capture objective, current state, proposed change, affected systems, implementation notes, "
            "test plan, risks, decisions, action items, and open questions."
        ),
        custom_instructions=(
            "Use IT/change-management language. Do not turn noisy transcript fragments into owners. "
            "Only assign an owner when a person or team is clearly responsible. Treat acronyms, systems, "
            "policies, OUs, groups, products, and departments as affected items unless the transcript clearly "
            "says they own work. Include concrete test scenarios and technical gotchas even when they are not formal action items. "
            "For Action Items, include only explicit commitments, requests, or assigned work. If no clear owner is stated, use Unknown; "
            "if no explicit work item is stated, write '- None captured.' Do not convert risks, design notes, group names, or test observations into action items. "
            "Keep proposed changes separate from decisions unless the transcript clearly says the group decided, approved, agreed, or committed."
        ),
        preferred_sections=(
            "Purpose / Objective, Current State, Proposed Change, Affected Systems / Policies, "
            "Implementation Notes, Test Plan, Risks / Gotchas, Decisions, Action Items, Open Questions"
        ),
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
        else:
            templates = self._merge_default_templates(templates)
        return templates

    def get_template(self, template_id: str) -> NoteTemplate:
        templates = self.list_templates()
        for template in templates:
            if template.id == template_id:
                return template
        return templates[0]

    def write_templates(self, templates: list[NoteTemplate]) -> None:
        self.path.write_text(json.dumps([asdict(template) for template in templates], indent=2), encoding="utf-8")

    def _merge_default_templates(self, templates: list[NoteTemplate]) -> list[NoteTemplate]:
        existing_ids = {template.id for template in templates}
        missing = [template for template in DEFAULT_TEMPLATES if template.id not in existing_ids]
        if not missing:
            return templates
        merged = [*templates, *missing]
        self.write_templates(merged)
        return merged

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
