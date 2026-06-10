from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Callable
import wave

from app.audio.audio_validation import inspect_wav
from app.core.glossary import glossary_prompt_context, load_glossary_terms
from app.core.profiles import MeetingProfile
from app.core.templates import NoteTemplate
from app.core.settings import load_settings
from app.intelligence.insights import build_insights_from_notes, write_insights_json
from app.intelligence.ollama_client import OllamaClient
from app.storage.meeting_store import MeetingMetadata, MeetingStore
from app.transcription.transcript_cleanup import apply_glossary_corrections, reduce_cross_bleed_for_profile
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
        processing_started = time.monotonic()
        transcription_started = 0.0
        transcription_seconds = 0.0
        notes_started = 0.0
        notes_seconds = 0.0
        transcription_details: dict[str, Any] = {}
        mic_capture_enabled = bool(getattr(metadata, "capture_mic", True))
        notes_transcript_text = ""

        self._restore_archived_wavs(folder, on_status)
        on_status("Waiting for captured audio files to settle")
        self._wait_for_audio_files_ready(folder, include_mic=mic_capture_enabled)
        on_status("Validating captured audio")
        mic_info = inspect_wav(folder / "mic.wav")
        system_info = inspect_wav(folder / "system.wav")
        metadata.audio_files = {
            "mic": mic_info.to_dict(),
            "system": system_info.to_dict(),
        }

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
            notes_transcript_text = transcript_text
            has_transcript = bool(transcript_text.strip())
        else:
            on_status("Preparing transcript")
            transcription_started = time.monotonic()
            live_result = self._live_transcript_result(folder, metadata, settings, on_status)
            if live_result is not None:
                transcript_results = [TranscriptionResult("You", "", False, None), live_result]
            else:
                transcript_results = self._transcribe_capture_sources(
                    folder,
                    metadata,
                    settings,
                    mic_capture_enabled,
                    mic_info.valid,
                    system_info.valid,
                    on_status,
                )
            transcription_seconds = time.monotonic() - transcription_started

            # Deterministic post-correction pass using glossary terms
            on_status("Applying glossary corrections")
            glossary_terms = load_glossary_terms()
            transcript_results = apply_glossary_corrections(transcript_results, glossary_terms)

            # Speaker-bleed cleanup (profile-driven)
            capture_profile = str(getattr(metadata, "capture_profile", "") or "external_mic_speakers")
            if settings.get("transcription", {}).get("cross_bleed_cleanup", True):
                transcript_results, bleed_warnings = reduce_cross_bleed_for_profile(transcript_results, capture_profile)
                for bw in bleed_warnings:
                    warnings.append(bw)
                    on_status(bw)

            for result in transcript_results:
                if result.details:
                    transcription_details[result.source] = result.details
                if result.warning:
                    warnings.append(result.warning)
                    on_status(result.warning)

            transcript_text = self._format_transcript(transcript_results, warnings)
            notes_transcript_text = self._format_transcript_for_notes(transcript_results)
            transcript_path = self.meeting_store.write_transcript(folder, transcript_text)
            has_transcript = any(result.success and result.text.strip() for result in transcript_results)

        notes_path = folder / "notes.md"
        if not has_transcript:
            warning = "Skipping AI notes because no transcript text is available yet."
            warnings.append(warning)
            on_status(warning)
            notes_path = self.meeting_store.write_notes_stub(folder, metadata, transcript_path, warnings)
        else:
            provider = settings.get("ai", {}).get("provider", "ollama").lower()
            provider_labels = {"ollama": "Ollama", "openai": "OpenAI", "claude": "Claude"}
            on_status(f"Generating notes with {provider_labels.get(provider, provider)}")
            notes_started = time.monotonic()
            transcript_text = self._cleanup_transcript_for_notes(notes_transcript_text or transcript_text)
            profile_context = self._profile_prompt_context(metadata)
            if provider == "openai":
                from app.intelligence.openai_client import OpenAIClient
                notes_result = OpenAIClient(settings).generate_meeting_notes(transcript_text, profile_context=profile_context)
            elif provider == "claude":
                from app.intelligence.claude_client import ClaudeClient
                notes_result = ClaudeClient(settings).generate_meeting_notes(transcript_text, profile_context=profile_context)
            else:
                notes_result = OllamaClient(settings).generate_meeting_notes(transcript_text, profile_context=profile_context)
            notes_seconds = time.monotonic() - notes_started
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

        meeting_date = None
        try:
            if metadata.started_at:
                meeting_date = datetime.fromisoformat(metadata.started_at)
        except (ValueError, TypeError):
            pass
        insights_path = write_insights_json(folder, build_insights_from_notes(notes_path, meeting_date=meeting_date))
        on_status(f"Meeting insights saved: {insights_path.name}")
        audio_archive = self._archive_audio_files(folder, metadata, settings, warnings, on_status)
        metadata.processing = {
            **(metadata.processing if isinstance(metadata.processing, dict) else {}),
            "transcript_path": str(transcript_path),
            "notes_path": str(notes_path),
            "insights_path": str(insights_path),
            "warnings": warnings,
            "mode": mode,
            "diagnostics": {
                "processing_seconds": round(time.monotonic() - processing_started, 3),
                "transcription_seconds": round(transcription_seconds, 3),
                "notes_seconds": round(notes_seconds, 3),
                "transcription": transcription_details,
                "capture_quality": self._capture_quality_summary(metadata, has_transcript, len(warnings)),
                "audio_archive": audio_archive,
            },
        }
        metadata.status = "processed_with_warnings" if warnings else "processed"
        self.meeting_store.write_metadata(folder, metadata)
        return ProcessingResult(warnings=warnings, transcript_path=transcript_path, notes_path=notes_path)

    def _live_transcript_result(
        self,
        folder: Path,
        metadata: MeetingMetadata,
        settings: dict[str, Any],
        on_status: StatusCallback,
    ) -> TranscriptionResult | None:
        if not settings.get("transcription", {}).get("prefer_live_transcript", True):
            return None
        path = folder / "live_transcript.md"
        if isinstance(metadata.processing, dict):
            configured = str(metadata.processing.get("live_transcript_path") or "")
            if configured:
                path = Path(configured)
        if not path.exists():
            return None
        text = self._usable_existing_transcript_text(path.read_text(encoding="utf-8", errors="ignore"))
        if len(text.split()) < int(settings.get("transcription", {}).get("live_transcript_min_words", 30)):
            return None
        on_status("Using live transcript captured during recording")
        return TranscriptionResult(
            "Meeting",
            text,
            True,
            None,
            {"source": "live_transcript", "path": str(path), "word_count": len(text.split())},
        )

    def _transcribe_capture_sources(
        self,
        folder: Path,
        metadata: MeetingMetadata,
        settings: dict[str, Any],
        mic_capture_enabled: bool,
        mic_valid: bool,
        system_valid: bool,
        on_status: StatusCallback,
    ) -> list[TranscriptionResult]:
        jobs: list[tuple[str, Path, str]] = []
        results: dict[str, TranscriptionResult] = {}
        if not mic_capture_enabled:
            results["You"] = TranscriptionResult("You", "", False, None)
        elif mic_valid:
            jobs.append(("You", folder / "mic.wav", "microphone"))
        else:
            results["You"] = TranscriptionResult("You", "", False, "Skipping mic transcription because mic.wav is invalid.")

        if system_valid:
            jobs.append(("Meeting", folder / "system.wav", "meeting audio"))
        else:
            results["Meeting"] = TranscriptionResult("Meeting", "", False, "Skipping meeting-audio transcription because system.wav is invalid.")

        if jobs:
            workers = min(len(jobs), 2)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        WhisperLiveClient(settings).transcribe_file,
                        path,
                        source,
                        on_status=on_status,
                        previous_chunks=self._previous_successful_chunks(metadata, source),
                    ): (source, label)
                    for source, path, label in jobs
                }
                for future in as_completed(futures):
                    source, label = futures[future]
                    try:
                        results[source] = future.result()
                    except Exception as error:
                        results[source] = TranscriptionResult(source, "", False, f"Skipping {label} transcription because it failed: {error}")

        return [results.get("You", TranscriptionResult("You", "", False, None)), results.get("Meeting", TranscriptionResult("Meeting", "", False, None))]

    def _restore_archived_wavs(self, folder: Path, on_status: StatusCallback) -> None:
        if shutil.which("ffmpeg") is None:
            return
        restored = False
        for label in ("mic", "system"):
            wav_path = folder / f"{label}.wav"
            flac_path = folder / f"{label}.flac"
            if wav_path.exists() or not flac_path.exists():
                continue
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(flac_path), str(wav_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                restored = True
            except Exception as error:
                on_status(f"Could not restore {label}.wav from archived FLAC: {error}")
        if restored:
            on_status("Archived FLAC audio restored for processing")

    def _archive_audio_files(
        self,
        folder: Path,
        metadata: MeetingMetadata,
        settings: dict[str, Any],
        warnings: list[str],
        on_status: StatusCallback,
    ) -> dict[str, str]:
        storage = settings.get("storage", {})
        if not storage.get("archive_wav_to_flac", True):
            return {}
        if shutil.which("ffmpeg") is None:
            return {"status": "skipped", "reason": "ffmpeg not found"}
        archived: dict[str, str] = {"status": "archived"}
        for label, enabled in (("mic", bool(getattr(metadata, "capture_mic", True))), ("system", True)):
            source = folder / f"{label}.wav"
            if not enabled or not source.exists():
                continue
            target = folder / f"{label}.flac"
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), str(target)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if target.exists() and target.stat().st_size > 0:
                    source.unlink()
                    archived[label] = target.name
            except Exception as error:
                warning = f"Audio archive skipped for {label}.wav: {error}"
                warnings.append(warning)
                on_status(warning)
        if len(archived) == 1:
            return {"status": "skipped", "reason": "no wav files archived"}
        on_status("Raw WAV audio archived to FLAC")
        return archived

    @staticmethod
    def _previous_successful_chunks(metadata: MeetingMetadata, source: str) -> dict[int, str]:
        if not isinstance(metadata.processing, dict):
            return {}
        diagnostics = metadata.processing.get("diagnostics", {})
        if not isinstance(diagnostics, dict):
            return {}
        transcription = diagnostics.get("transcription", {})
        if not isinstance(transcription, dict):
            return {}
        source_details = transcription.get(source, {})
        if not isinstance(source_details, dict):
            return {}
        chunks = source_details.get("chunks", [])
        if not isinstance(chunks, list):
            return {}
        previous: dict[int, str] = {}
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            if str(chunk.get("status", "")).lower() not in {"success", "reused"}:
                continue
            text = str(chunk.get("text", "")).strip()
            if not text:
                continue
            try:
                previous[int(chunk.get("index"))] = text
            except (TypeError, ValueError):
                continue
        return previous

    @staticmethod
    def _capture_quality_summary(metadata: MeetingMetadata, has_transcript: bool, warning_count: int = 0) -> dict[str, Any]:
        system_audio = metadata.audio_files.get("system", {}) if isinstance(metadata.audio_files, dict) else {}
        mic_audio = metadata.audio_files.get("mic", {}) if isinstance(metadata.audio_files, dict) else {}
        system_state = MeetingProcessor._audio_quality_state(system_audio)
        mic_state = "muted" if not metadata.capture_mic else MeetingProcessor._audio_quality_state(mic_audio)
        transcript_state = "available" if has_transcript else "missing"
        score = 100
        for state in (system_state, mic_state, transcript_state):
            if state in {"missing", "invalid"}:
                score -= 30
            elif state == "quiet":
                score -= 15
        score -= min(warning_count * 5, 25)
        return {
            "system_audio": system_state,
            "microphone_audio": mic_state,
            "transcript": transcript_state,
            "warning_count": warning_count,
            "score": max(0, score),
        }

    @staticmethod
    def _audio_quality_state(audio_info: dict[str, Any]) -> str:
        if not audio_info:
            return "missing"
        if not audio_info.get("valid"):
            return "invalid"
        duration = float(audio_info.get("duration_seconds") or 0)
        rms_level = float(audio_info.get("rms_level") or 0)
        if duration >= 10 and rms_level < 0.001:
            return "quiet"
        return "good"

    @classmethod
    def _wait_for_audio_files_ready(cls, folder: Path, include_mic: bool, timeout_seconds: float = 20.0) -> None:
        paths = [folder / "system.wav"]
        if include_mic:
            paths.append(folder / "mic.wav")
        deadline = time.monotonic() + timeout_seconds
        for path in paths:
            cls._wait_for_audio_file_ready(path, deadline)

    @staticmethod
    def _wait_for_audio_file_ready(path: Path, deadline: float) -> None:
        previous_size: int | None = None
        while time.monotonic() < deadline:
            try:
                current_size = path.stat().st_size
                if current_size == previous_size:
                    with wave.open(str(path), "rb") as wav_file:
                        wav_file.getparams()
                    return
                previous_size = current_size
            except FileNotFoundError:
                return
            except (PermissionError, OSError, EOFError, wave.Error):
                previous_size = None
            time.sleep(0.25)

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
    def _format_transcript_for_notes(results: list[TranscriptionResult]) -> str:
        lines = [
            "# Source-Separated Transcript",
            "",
            "The following transcript sources were captured separately. They may contain overlapping phrases from speaker bleed. Use both as evidence, but summarize duplicated phrases only once.",
            "",
        ]
        for result in results:
            if not result.success or not result.text.strip():
                continue
            label = "Microphone Audio" if result.source == "You" else "Speaker Audio" if result.source == "Meeting" else result.source
            lines.append(f"## {label}")
            lines.append("")
            lines.append(result.text.strip())
            lines.append("")
        return "\n".join(lines).strip()

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
        meeting_context = str(getattr(metadata, "meeting_context", "") or "").strip()
        if meeting_context:
            contexts.append(f"Meeting-specific context provided by user:\n{meeting_context}")
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
        glossary_context = glossary_prompt_context()
        if glossary_context:
            contexts.append(glossary_context)
        return "\n\n".join(context for context in contexts if context)
