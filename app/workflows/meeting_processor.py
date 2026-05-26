from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re
from typing import Any, Callable

from app.audio.audio_validation import inspect_wav
from app.core.profiles import MeetingProfile
from app.core.templates import NoteTemplate
from app.core.settings import load_settings
from app.intelligence.insights import build_insights_from_notes, write_insights_json
from app.intelligence.ollama_client import OllamaClient
from app.storage.meeting_store import MeetingMetadata, MeetingStore
from app.transcription.transcript_cleanup import reduce_cross_bleed_for_profile
from app.transcription.whisperlive_client import TranscriptionResult, WhisperLiveClient


StatusCallback = Callable[[str], None]


@dataclass
class ProcessingResult:
    warnings: list[str]
    transcript_path: Path
    notes_path: Path


class MeetingProcessor:
    def __init__(self, meeting_store: MeetingStore | None = None, settings: dict[str, Any] | None = None) -> None:
        self.meeting_store = meeting_store or MeetingStore()
        self.settings = settings

    def process(self, folder: Path, metadata: MeetingMetadata, on_status: StatusCallback, mode: str = "full") -> ProcessingResult:
        settings = self.settings or load_settings()
        warnings: list[str] = []

        on_status("Validating captured audio")
        mic_info = inspect_wav(folder / "mic.wav")
        system_info = inspect_wav(folder / "system.wav")
        metadata.audio_files = {
            "mic": mic_info.to_dict(),
            "system": system_info.to_dict(),
        }

        mic_capture_enabled = bool(getattr(metadata, "capture_mic", True))

        for label, info in (("mic", mic_info), ("system", system_info)):
            if label == "mic" and not mic_capture_enabled:
                on_status("mic.wav skipped because microphone capture was muted")
                continue
            if info.valid:
                on_status(
                    f"{label}.wav: {info.duration_seconds:.1f}s, "
                    f"{info.sample_rate} Hz, {info.channels} ch, {info.size_bytes} bytes"
                )
            else:
                warning = f"{label}.wav is not valid: {info.error or 'no audio frames captured'}"
                warnings.append(warning)
                on_status(warning)

        if system_info.valid and system_info.duration_seconds >= 10 and system_info.rms_level < 0.001:
            warning = "System audio appears very quiet; confirm the selected output device is correct."
            warnings.append(warning)
            on_status(warning)

        transcript_path = folder / "transcript.md"
        if mode == "notes_only" and transcript_path.exists():
            on_status("Using existing transcript")
            transcript_text = transcript_path.read_text(encoding="utf-8")
            transcript_text = self._usable_existing_transcript_text(transcript_text)
            has_transcript = bool(transcript_text.strip())
        else:
            on_status("Preparing transcript")
            transcriber = WhisperLiveClient(settings)
            transcript_results: list[TranscriptionResult] = []
            if not mic_capture_enabled:
                transcript_results.append(TranscriptionResult("You", "", False, None))
            elif mic_info.valid:
                transcript_results.append(transcriber.transcribe_file(folder / "mic.wav", "You"))
            else:
                transcript_results.append(TranscriptionResult("You", "", False, "Skipping mic transcription because mic.wav is invalid."))

            if system_info.valid:
                transcript_results.append(transcriber.transcribe_file(folder / "system.wav", "Meeting"))
            else:
                transcript_results.append(
                    TranscriptionResult("Meeting", "", False, "Skipping meeting-audio transcription because system.wav is invalid.")
                )

            for result in transcript_results:
                if result.warning:
                    warnings.append(result.warning)
                    on_status(result.warning)

            if settings.get("transcription", {}).get("cross_bleed_cleanup", True):
                capture_profile = metadata.capture_profile or str(settings.get("audio", {}).get("capture_profile", "external_mic_speakers"))
                transcript_results, cleanup_warnings = reduce_cross_bleed_for_profile(transcript_results, capture_profile)
                for warning in cleanup_warnings:
                    warnings.append(warning)
                    on_status(warning)

            transcript_text = self._format_transcript(transcript_results, warnings)
            transcript_path = self.meeting_store.write_transcript(folder, transcript_text)
            has_transcript = any(result.success and result.text.strip() for result in transcript_results)

        notes_path = folder / "notes.md"
        if not has_transcript:
            warning = "Skipping AI notes because no transcript text is available yet."
            warnings.append(warning)
            on_status(warning)
            notes_path = self.meeting_store.write_notes_stub(folder, metadata, transcript_path, warnings)
        elif settings.get("ai", {}).get("provider", "ollama") == "ollama":
            on_status("Generating notes with Ollama")
            transcript_text = self._cleanup_transcript_for_notes(transcript_text)
            notes_result = OllamaClient(settings).generate_meeting_notes(
                transcript_text,
                profile_context=self._profile_prompt_context(metadata),
            )
            if notes_result.success:
                if notes_result.warning:
                    warnings.append(notes_result.warning)
                    on_status(notes_result.warning)
                notes_path = self.meeting_store.write_notes(folder, metadata, notes_result.text, transcript_path, warnings)
            else:
                if notes_result.warning:
                    warnings.append(notes_result.warning)
                    on_status(notes_result.warning)
                notes_path = self.meeting_store.write_notes_stub(folder, metadata, transcript_path, warnings)
        else:
            warning = "OpenAI provider is selected, but OpenAI notes generation is not wired yet."
            warnings.append(warning)
            on_status(warning)
            notes_path = self.meeting_store.write_notes_stub(folder, metadata, transcript_path, warnings)

        insights_path = write_insights_json(folder, build_insights_from_notes(notes_path))
        on_status(f"Meeting insights saved: {insights_path.name}")
        metadata.processing = {
            "transcript_path": str(transcript_path),
            "notes_path": str(notes_path),
            "insights_path": str(insights_path),
            "warnings": warnings,
            "mode": mode,
        }
        metadata.status = "processed_with_warnings" if warnings else "processed"
        self.meeting_store.write_metadata(folder, metadata)
        return ProcessingResult(warnings=warnings, transcript_path=transcript_path, notes_path=notes_path)

    @staticmethod
    def _format_transcript(results: list[TranscriptionResult], warnings: list[str]) -> str:
        lines = ["# Transcript", ""]
        for result in results:
            lines.append(f"## {result.source}")
            lines.append("")
            lines.append(result.text.strip() if result.success and result.text.strip() else "_Transcript pending._")
            lines.append("")

        if warnings:
            lines.append("## Processing Warnings")
            lines.append("")
            lines.extend(f"- {warning}" for warning in warnings)
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _usable_existing_transcript_text(transcript_text: str) -> str:
        lines: list[str] = []
        in_warnings = False
        for raw_line in transcript_text.splitlines():
            line = raw_line.strip()
            if line.lower() == "## processing warnings":
                in_warnings = True
                continue
            if in_warnings and line.startswith("## "):
                in_warnings = False
            if in_warnings:
                continue
            if not line:
                continue
            if line in {"# Transcript", "_Transcript pending._"}:
                continue
            lines.append(raw_line)
        return "\n".join(lines).strip()

    @classmethod
    def _cleanup_transcript_for_notes(cls, transcript_text: str) -> str:
        cleaned_lines: list[str] = []
        for raw_line in transcript_text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                cleaned_lines.append(raw_line)
                continue
            fragments = re.split(r"(?<=[.!?])\s+", line)
            deduped: list[str] = []
            for fragment in fragments:
                cls._append_clean_fragment(deduped, fragment)
            cleaned_lines.append(" ".join(deduped))
        return "\n".join(cleaned_lines).strip()

    @classmethod
    def _append_clean_fragment(cls, fragments: list[str], fragment: str) -> None:
        normalized = cls._normalize_fragment(fragment)
        if not normalized:
            return
        if not fragments:
            fragments.append(fragment)
            return

        previous_normalized = cls._normalize_fragment(fragments[-1])
        if normalized == previous_normalized:
            return
        if previous_normalized and previous_normalized in normalized:
            fragments[-1] = fragment
            return
        if normalized in previous_normalized:
            return
        if SequenceMatcher(None, previous_normalized, normalized).ratio() >= 0.88:
            if len(normalized) > len(previous_normalized):
                fragments[-1] = fragment
            return
        fragments.append(fragment)

    @staticmethod
    def _normalize_fragment(text: str) -> str:
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _profile_prompt_context(metadata: MeetingMetadata) -> str:
        profile_data = metadata.meeting_profile if isinstance(metadata.meeting_profile, dict) else {}
        template_data = metadata.note_template if isinstance(metadata.note_template, dict) else {}
        contexts = []
        if profile_data:
            try:
                contexts.append(
                    MeetingProfile(
                        **{key: value for key, value in profile_data.items() if key in MeetingProfile.__dataclass_fields__}
                    ).to_prompt_context()
                )
            except Exception:
                contexts.append("\n".join(f"{key}: {value}" for key, value in profile_data.items() if value))
        if template_data:
            try:
                contexts.append(
                    NoteTemplate(
                        **{key: value for key, value in template_data.items() if key in NoteTemplate.__dataclass_fields__}
                    ).to_prompt_context()
                )
            except Exception:
                contexts.append("\n".join(f"{key}: {value}" for key, value in template_data.items() if value))
        return "\n\n".join(context for context in contexts if context)
