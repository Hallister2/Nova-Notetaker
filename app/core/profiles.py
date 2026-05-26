from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.settings import CONFIG_DIR


PROFILES_PATH = CONFIG_DIR / "profiles.json"


@dataclass(frozen=True)
class MeetingProfile:
    id: str
    name: str
    category: str = "General Meeting"
    company_conducting: str = ""
    companies_attending: str = ""
    default_meeting_title_prefix: str = ""
    default_note_template_id: str = ""
    ai_context: str = ""
    notes_focus: str = ""

    def to_prompt_context(self) -> str:
        lines = [
            f"Profile: {self.name}",
            f"Category: {self.category}",
        ]
        if self.company_conducting:
            lines.append(f"Company conducting: {self.company_conducting}")
        if self.companies_attending:
            lines.append(f"Companies attending: {self.companies_attending}")
        if self.default_note_template_id:
            lines.append(f"Default note template: {self.default_note_template_id}")
        if self.ai_context:
            lines.append(f"Context: {self.ai_context}")
        if self.notes_focus:
            lines.append(f"Notes focus: {self.notes_focus}")
        return "\n".join(lines)


DEFAULT_PROFILES = [
    MeetingProfile(
        id="general",
        name="General Meeting",
        category="General Meeting",
        default_note_template_id="standard",
        ai_context="Use balanced meeting notes suitable for internal review.",
        notes_focus="Summary, decisions, action items, dates, risks, and follow-ups.",
    ),
    MeetingProfile(
        id="project_sync",
        name="Project Sync",
        category="Project Meeting",
        default_note_template_id="project_sync",
        ai_context="This is a project coordination meeting.",
        notes_focus="Prioritize owners, blockers, delivery dates, decisions, dependencies, and next steps.",
    ),
    MeetingProfile(
        id="team_call",
        name="Team Call",
        category="Team Call",
        default_note_template_id="standard",
        ai_context="This is an internal team call.",
        notes_focus="Prioritize team commitments, decisions, reminders, risks, and any follow-up ownership.",
    ),
    MeetingProfile(
        id="vendor_call",
        name="Vendor Call",
        category="Vendor Call",
        default_note_template_id="vendor_call",
        ai_context="This is a meeting with an outside vendor or partner.",
        notes_focus="Prioritize commitments, risks, commercial details, dates, open questions, and accountability.",
    ),
    MeetingProfile(
        id="personal_review",
        name="Personal Review",
        category="Personal Review",
        default_note_template_id="executive_summary",
        ai_context="This is a personal review or one-on-one style meeting.",
        notes_focus="Prioritize feedback, goals, commitments, development items, and follow-up dates.",
    ),
]


class ProfileStore:
    def __init__(self, path: Path = PROFILES_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.write_profiles(DEFAULT_PROFILES)

    def list_profiles(self) -> list[MeetingProfile]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.write_profiles(DEFAULT_PROFILES)
            return list(DEFAULT_PROFILES)

        profiles = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict):
                continue
            profiles.append(self._profile_from_dict(item))

        if not profiles:
            profiles = list(DEFAULT_PROFILES)
            self.write_profiles(profiles)
        return profiles

    def get_profile(self, profile_id: str) -> MeetingProfile:
        for profile in self.list_profiles():
            if profile.id == profile_id:
                return profile
        return self.list_profiles()[0]

    def write_profiles(self, profiles: list[MeetingProfile]) -> None:
        self.path.write_text(json.dumps([asdict(profile) for profile in profiles], indent=2), encoding="utf-8")

    @staticmethod
    def make_id(name: str, existing_ids: set[str]) -> str:
        base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "profile"
        candidate = base
        counter = 2
        while candidate in existing_ids:
            candidate = f"{base}_{counter}"
            counter += 1
        return candidate

    @staticmethod
    def _profile_from_dict(data: dict[str, Any]) -> MeetingProfile:
        fields = MeetingProfile.__dataclass_fields__
        filtered = {key: value for key, value in data.items() if key in fields}
        return MeetingProfile(**filtered)
