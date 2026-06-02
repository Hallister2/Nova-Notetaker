from __future__ import annotations

import html
import os
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.intelligence.insights import InsightItem, MeetingInsights, load_or_build_insights, write_insights_json
from app.storage.meeting_store import MeetingMetadata
from app.ui.constants import CLOSED_ACTION_STATUSES
from app.ui.review_helpers import (
    apply_speaker_aliases_to_markdown,
    read_speaker_aliases,
    transcript_speakers,
    write_speaker_aliases,
)
from app.ui.styles import build_stylesheet


class OverviewTabMixin:
    def _build_overview_workspace_page(self) -> QWidget:
        page = QWidget()
        self.overview_workspace_layout = QVBoxLayout(page)
        self.overview_workspace_layout.setContentsMargins(34, 28, 18, 28)
        self.overview_workspace_layout.setSpacing(14)
        title = QLabel("Meeting Overview")
        title.setObjectName("Title")
        self.overview_workspace_layout.addWidget(title)
        self.overview_workspace_empty = self._empty_state_widget(
            "meetings",
            "No meeting selected",
            "Open a meeting from Meetings, Search, Calendar, or Actions.",
        )
        self.overview_workspace_layout.addWidget(self.overview_workspace_empty, stretch=1)
        return page

    def open_meeting_workspace(self, folder: Path | None = None) -> None:
        folder = folder or self._selected_meeting_folder()
        if folder is None:
            QMessageBox.information(self, "Nova Notetaker", "Select a meeting to open.")
            return
        try:
            metadata = self.meeting_store.read_metadata(folder)
        except Exception as error:
            QMessageBox.warning(self, "Nova Notetaker", f"Could not read meeting metadata: {error}")
            return
        self.overview_workspace_folder = folder
        while self.overview_workspace_layout.count() > 0:
            item = self.overview_workspace_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.overview_workspace_layout.addWidget(self._build_overview_workspace_header(folder, metadata))
        self.overview_workspace_layout.addWidget(self._build_meeting_overview_widget(folder, metadata), stretch=1)
        self._set_active_nav(2)

    def _build_overview_workspace_header(self, folder: Path, metadata: MeetingMetadata) -> QWidget:
        header_widget = QWidget()
        header_widget.setObjectName("Transparent")
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        title_block = QVBoxLayout()
        title = QLabel("Meeting Overview")
        title.setObjectName("Title")
        subtitle = self._muted_label(f"{metadata.title or folder.name}  |  {metadata.started_at}")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block)
        header.addStretch()
        popout_button = QPushButton("Pop out")
        popout_button.clicked.connect(lambda: self.open_meeting_overview(folder))
        export_button = QPushButton("Export briefing")
        export_button.clicked.connect(lambda: self._export_executive_briefing_for_folder(folder))
        rename_button = QPushButton("Rename speakers")
        rename_button.clicked.connect(lambda: self.rename_speakers_for_meeting(folder))
        header.addWidget(rename_button)
        header.addWidget(export_button)
        header.addWidget(popout_button)
        return header_widget

    def _build_meeting_overview_widget(self, folder: Path, metadata: MeetingMetadata) -> QWidget:
        widget = QWidget()
        widget.setObjectName("Transparent")
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        notes_path = folder / "notes.md"
        transcript_path = folder / "transcript.md"
        insights = load_or_build_insights(folder)
        summary_lines = self._note_section_lines(notes_path, "summary")

        briefing_band = QFrame()
        briefing_band.setObjectName("Panel")
        briefing_band_layout = QGridLayout(briefing_band)
        briefing_band_layout.setContentsMargins(16, 14, 16, 14)
        briefing_band_layout.setHorizontalSpacing(16)
        briefing_band_layout.setVerticalSpacing(10)
        summary_card = self._overview_text_card("Executive summary", summary_lines[:4] or ["No summary has been generated yet."])
        status_card = self._overview_status_card(metadata, insights)
        briefing_band_layout.addWidget(summary_card, 0, 0)
        briefing_band_layout.addWidget(status_card, 0, 1)
        briefing_band_layout.setColumnStretch(0, 2)
        briefing_band_layout.setColumnStretch(1, 1)
        layout.addWidget(briefing_band, 0, 0, 1, 2)

        evidence_panel = QFrame()
        evidence_panel.setObjectName("Panel")
        evidence_layout = QVBoxLayout(evidence_panel)
        evidence_layout.setContentsMargins(16, 14, 16, 14)
        evidence_layout.setSpacing(10)
        evidence_layout.addWidget(self._section_label("Meeting record"))
        evidence_layout.addWidget(self._build_audio_player_bar(folder))
        evidence_tabs = QTabWidget()
        notes_view = QTextEdit()
        notes_view.setReadOnly(True)
        notes_view.setMarkdown(self._notes_for_display(notes_path) if notes_path.exists() else "notes.md has not been created yet.")
        transcript_view = QTextEdit()
        transcript_view.setReadOnly(True)
        transcript_view.setMarkdown(self._transcript_for_display(transcript_path, folder) if transcript_path.exists() else "transcript.md has not been created yet.")
        evidence_tabs.addTab(notes_view, "Structured notes")
        evidence_tabs.addTab(transcript_view, "Transcript evidence")
        evidence_tabs.setMinimumHeight(280)
        evidence_layout.addWidget(evidence_tabs, stretch=1)
        layout.addWidget(evidence_panel, 1, 0, 1, 2)

        briefing_scroll = QScrollArea()
        briefing_scroll.setWidgetResizable(True)
        briefing_scroll.setFrameShape(QFrame.NoFrame)
        briefing_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        briefing = QWidget()
        briefing.setObjectName("Transparent")
        briefing_layout = QVBoxLayout(briefing)
        briefing_layout.setContentsMargins(0, 0, 0, 0)
        briefing_layout.setSpacing(12)

        briefing_layout.addWidget(self._overview_items_card("Key decisions", insights.decisions, "No decisions detected."))
        briefing_layout.addWidget(self._overview_items_card("Action items", insights.actions, "No action items detected."))
        briefing_layout.addWidget(self._overview_items_card("Dates / follow-ups", insights.dates, "No dates detected."))
        warning_items = insights.quality_warnings + insights.warnings
        briefing_layout.addWidget(self._overview_text_card("Risks / review needed", warning_items or ["No review warnings."]))
        briefing_scroll.setWidget(briefing)

        intelligence_scroll = QScrollArea()
        intelligence_scroll.setWidgetResizable(True)
        intelligence_scroll.setFrameShape(QFrame.NoFrame)
        intelligence_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        intelligence_scroll.setMinimumWidth(320)
        intelligence_scroll.setMaximumWidth(420)
        intelligence_panel = QFrame()
        intelligence_panel.setObjectName("Panel")
        intelligence_layout = QVBoxLayout(intelligence_panel)
        intelligence_layout.setContentsMargins(16, 16, 16, 16)
        intelligence_layout.setSpacing(12)
        intelligence_layout.addWidget(self._section_label("Action center"))
        intelligence_layout.addWidget(self._overview_action_items_card(folder, insights))
        intelligence_layout.addWidget(self._overview_context_card(folder, metadata))
        intelligence_layout.addWidget(self._overview_markers_card(folder))
        intelligence_layout.addWidget(self._section_label("Meeting health"))
        intelligence_layout.addWidget(self._overview_quality_card(folder, metadata, insights))
        intelligence_layout.addWidget(self._overview_resolve_checklist_card(folder, metadata, insights))
        details = QTextEdit()
        details.setReadOnly(True)
        details.setMaximumHeight(150)
        details.setPlainText(self._format_health_summary(metadata))
        intelligence_layout.addWidget(self._section_label("Meeting details"))
        intelligence_layout.addWidget(details)
        intelligence_layout.addStretch()
        intelligence_scroll.setWidget(intelligence_panel)

        layout.addWidget(briefing_scroll, 2, 0)
        layout.addWidget(intelligence_scroll, 2, 1)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(0, 0)
        layout.setRowStretch(1, 2)
        layout.setRowStretch(2, 3)
        return widget

    def _build_audio_player_bar(self, folder: Path) -> QWidget:
        bar = QFrame()
        bar.setObjectName("RaisedPanel")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        mic_path = folder / "mic.wav"
        system_path = folder / "system.wav"

        source_combo = QComboBox()
        if mic_path.exists():
            source_combo.addItem("Microphone", str(mic_path))
        if system_path.exists():
            source_combo.addItem("System Audio", str(system_path))

        play_button = QPushButton("▶ Play")
        play_button.setObjectName("SubtleActionButton")
        play_button.setFixedWidth(90)
        stop_button = QPushButton("■ Stop")
        stop_button.setObjectName("SubtleActionButton")
        stop_button.setFixedWidth(90)
        status_label = self._muted_label("Select a track and press Play")
        status_label.setFixedWidth(240)

        if not mic_path.exists() and not system_path.exists():
            layout.addWidget(self._muted_label("No audio files available for playback."))
            return bar

        def _play() -> None:
            selected_path = source_combo.currentData()
            if not selected_path:
                return
            try:
                from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            except ImportError:
                status_label.setText("Qt Multimedia not available.")
                return
            if not hasattr(bar, "_player"):
                bar._player = QMediaPlayer(bar)
                bar._audio_out = QAudioOutput(bar)
                bar._player.setAudioOutput(bar._audio_out)
                bar._player.playbackStateChanged.connect(
                    lambda state: play_button.setText("▶ Play" if state.name == "StoppedState" or state == 0 else "⏸ Pause")
                )
            player = bar._player
            current_url = player.source().toLocalFile() if player.source().isValid() else ""
            if current_url == selected_path and player.playbackState() == 1:
                player.pause()
                play_button.setText("▶ Play")
                status_label.setText("Paused")
                return
            if current_url == selected_path and player.playbackState() == 2:
                player.play()
                play_button.setText("⏸ Pause")
                status_label.setText(f"Playing: {Path(selected_path).name}")
                return
            player.setSource(QUrl.fromLocalFile(selected_path))
            player.play()
            play_button.setText("⏸ Pause")
            status_label.setText(f"Playing: {Path(selected_path).name}")

        def _stop() -> None:
            if hasattr(bar, "_player"):
                bar._player.stop()
            play_button.setText("▶ Play")
            status_label.setText("Stopped")

        play_button.clicked.connect(_play)
        stop_button.clicked.connect(_stop)

        layout.addWidget(QLabel("Audio:"))
        layout.addWidget(source_combo)
        layout.addWidget(play_button)
        layout.addWidget(stop_button)
        layout.addWidget(status_label)
        layout.addStretch()
        return bar

    def _overview_status_card(self, metadata: MeetingMetadata, insights: MeetingInsights) -> QFrame:
        open_actions = sum(1 for item in insights.actions if item.status.lower() not in CLOSED_ACTION_STATUSES)
        review_count = len(insights.quality_warnings) + len(insights.warnings)
        dates_count = len(insights.dates)
        decisions_count = len(insights.decisions)
        transcript_ok = False
        if isinstance(metadata.processing, dict):
            transcript_raw = str(metadata.processing.get("transcript_path") or "")
            transcript_ok = bool(transcript_raw and Path(transcript_raw).exists())
        lines = [
            f"Open actions: {open_actions}",
            f"Decisions: {decisions_count}",
            f"Dates: {dates_count}",
            f"Review warnings: {review_count}",
            f"Status: {self._meeting_status_label(metadata.status, review_count, transcript_ok)}",
        ]
        return self._overview_text_card("Follow-up status", lines)

    def _overview_text_card(self, title: str, lines: list[str]) -> QFrame:
        card = QFrame()
        card.setObjectName("RaisedPanel")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(self._section_label(title))
        for line in lines[:6]:
            label = QLabel(str(line).lstrip("- ").strip())
            label.setWordWrap(True)
            layout.addWidget(label)
        return card

    def _overview_items_card(self, title: str, items: list[InsightItem], empty_text: str) -> QFrame:
        count_label = QLabel(str(len(items)))
        card, _items_layout = self._insight_card(title, count_label, items or [empty_text])
        return card

    def _overview_context_card(self, folder: Path, metadata: MeetingMetadata) -> QFrame:
        card = QFrame()
        card.setObjectName("RaisedPanel")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(self._section_label("Meeting context"))
        context_edit = QTextEdit()
        context_edit.setPlaceholderText("Add context for reprocessing, such as meeting purpose, systems discussed, known terminology, or what Nova should infer carefully.")
        context_edit.setPlainText(str(getattr(metadata, "meeting_context", "") or ""))
        context_edit.setMaximumHeight(120)
        layout.addWidget(context_edit)
        save_button = QPushButton("Save context")
        save_button.setObjectName("SubtleActionButton")
        save_button.clicked.connect(lambda checked=False, meeting_folder=folder, editor=context_edit: self._save_meeting_context(meeting_folder, editor.toPlainText()))
        layout.addWidget(save_button)
        layout.addWidget(self._muted_label("Saved context is included the next time notes are reprocessed."))
        return card

    def _save_meeting_context(self, folder: Path, context: str) -> None:
        try:
            metadata = self.meeting_store.read_metadata(folder)
            metadata.meeting_context = context.strip()
            self.meeting_store.write_metadata(folder, metadata)
            self.log(f"Saved meeting context: {folder.name}")
            if hasattr(self, "archive_status"):
                self.archive_status.setText("Meeting context saved")
        except Exception as error:
            QMessageBox.warning(self, "Nova Notetaker", f"Could not save meeting context: {error}")

    def open_latest_meeting(self) -> None:
        meetings = self.meeting_store.list_meetings()
        if not meetings:
            QMessageBox.information(self, "Nova Notetaker", "No meetings have been captured yet.")
            return
        self.open_meeting_overview(meetings[0])

    def mark_selected_meeting_important(self) -> None:
        folder = self._selected_meeting_folder()
        if folder is None:
            QMessageBox.information(self, "Nova Notetaker", "Select a meeting to pin.")
            return
        self.mark_meeting_important(folder)

    def mark_meeting_important(self, folder: Path) -> None:
        markers = self.meeting_store.read_markers(folder)
        if any(str(marker.get("type", "")).lower() == "important" for marker in markers):
            if hasattr(self, "archive_status"):
                self.archive_status.setText("Meeting already pinned")
            return
        markers.append(
            {
                "type": "important",
                "text": "Pinned important",
                "created_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                "offset_seconds": 0,
                "offset_label": "Pinned",
            }
        )
        self.meeting_store.write_markers(folder, markers)
        if hasattr(self, "archive_status"):
            self.archive_status.setText("Meeting pinned")
        self.refresh_review_center()
        self.log(f"Pinned important meeting: {folder.name}")

    def _overview_quality_card(self, folder: Path, metadata: MeetingMetadata, insights: MeetingInsights) -> QFrame:
        from app.workflows.meeting_processor import MeetingProcessor
        card = QFrame()
        card.setObjectName("RaisedPanel")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(self._section_label("Quality summary"))
        transcript_raw_path = metadata.processing.get("transcript_path", "") if isinstance(metadata.processing, dict) else ""
        transcript_path = Path(transcript_raw_path) if transcript_raw_path else None
        transcript_ok = bool(
            transcript_path
            and transcript_path.exists()
            and MeetingProcessor._usable_existing_transcript_text(transcript_path.read_text(encoding="utf-8", errors="ignore")).strip()
        )
        system_audio = metadata.audio_files.get("system", {}) if isinstance(metadata.audio_files, dict) else {}
        mic_audio = metadata.audio_files.get("mic", {}) if isinstance(metadata.audio_files, dict) else {}
        duration = max(float(system_audio.get("duration_seconds") or 0), float(mic_audio.get("duration_seconds") or 0))
        processing = metadata.processing if isinstance(metadata.processing, dict) else {}
        warnings = processing.get("warnings", [])
        diagnostics = processing.get("diagnostics", {}) if isinstance(processing.get("diagnostics", {}), dict) else {}
        transcription = diagnostics.get("transcription", {}) if isinstance(diagnostics.get("transcription", {}), dict) else {}
        capture_quality = diagnostics.get("capture_quality", {}) if isinstance(diagnostics.get("capture_quality", {}), dict) else {}
        readiness_score, readiness_lines = self._meeting_readiness_score(folder, metadata, insights)
        summary = [
            f"Readiness: {readiness_score}%",
            f"Recording: {self._format_duration(duration)}" if duration else "Recording: unknown",
            f"System audio: {capture_quality.get('system_audio') or self._audio_quality_label(system_audio)}",
            f"Microphone: {capture_quality.get('microphone_audio') or ('muted' if not metadata.capture_mic else self._audio_quality_label(mic_audio))}",
            f"Transcript: {'available' if transcript_ok else 'missing'}",
            f"Open actions: {sum(1 for item in insights.actions if item.status.lower() not in CLOSED_ACTION_STATUSES)}",
            f"Review warnings: {len(insights.quality_warnings) + len(warnings)}",
        ]
        if diagnostics.get("transcription_seconds"):
            summary.append(f"Transcription time: {self._format_duration(float(diagnostics.get('transcription_seconds') or 0))}")
        for source, details in transcription.items():
            if not isinstance(details, dict) or not details.get("chunk_count"):
                continue
            summary.append(
                f"{source} chunks: {details.get('successful_chunks', 0)}/{details.get('chunk_count')} ok"
            )
        for line in summary:
            label = QLabel(line)
            label.setWordWrap(True)
            layout.addWidget(label)
        for line in readiness_lines[:3]:
            layout.addWidget(self._muted_label(f"- {line}"))
        return card

    @staticmethod
    def _audio_quality_label(audio_info: dict) -> str:
        if not audio_info:
            return "missing"
        if not audio_info.get("valid"):
            return "invalid"
        duration = float(audio_info.get("duration_seconds") or 0)
        rms_level = float(audio_info.get("rms_level") or 0)
        if duration >= 10 and rms_level < 0.001:
            return "quiet"
        return "good"

    def _overview_resolve_checklist_card(
        self,
        folder: Path,
        metadata: MeetingMetadata,
        insights: MeetingInsights,
        dialog: QDialog | None = None,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("RaisedPanel")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(self._section_label("Resolve meeting"))
        checks = [
            ("Transcript", self._meeting_has_transcript(folder)),
            ("Notes", (folder / "notes.md").exists()),
            ("Actions reviewed", not any(item.status.lower() not in CLOSED_ACTION_STATUSES for item in insights.actions)),
            ("Warnings clear", not insights.quality_warnings and not insights.warnings),
            ("Pinned if important", self._meeting_is_important(folder)),
        ]
        for label, complete in checks:
            prefix = "Done" if complete else "Open"
            row = QLabel(f"{prefix}: {label}")
            row.setWordWrap(True)
            layout.addWidget(row)
        actions = QGridLayout()
        actions.setHorizontalSpacing(6)
        actions.setVerticalSpacing(6)
        repair_button = QPushButton("Repair")
        repair_button.setObjectName("SubtleActionButton")
        repair_button.clicked.connect(lambda checked=False, meeting_folder=folder: self.repair_meeting(meeting_folder))
        export_button = QPushButton("Export")
        export_button.setObjectName("SubtleActionButton")
        export_button.clicked.connect(lambda checked=False, meeting_folder=folder: self._export_executive_briefing_for_folder(meeting_folder))
        rename_button = QPushButton("Speakers")
        rename_button.setObjectName("SubtleActionButton")
        rename_button.clicked.connect(lambda checked=False, meeting_folder=folder: self.rename_speakers_for_meeting(meeting_folder))
        pin_button = QPushButton("Pin")
        pin_button.setObjectName("SubtleActionButton")
        pin_button.clicked.connect(lambda checked=False, meeting_folder=folder: self.mark_meeting_important(meeting_folder))
        for index, button in enumerate((repair_button, export_button, rename_button, pin_button)):
            actions.addWidget(button, index // 2, index % 2)
        layout.addLayout(actions)
        return card

    def _overview_markers_card(self, folder: Path) -> QFrame:
        card = QFrame()
        card.setObjectName("RaisedPanel")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        markers = self.meeting_store.read_markers(folder)
        header = QHBoxLayout()
        label = QLabel("Meeting markers")
        label.setObjectName("SectionTitle")
        count = QLabel(str(len(markers)))
        count.setObjectName("OrangeText")
        header.addWidget(label)
        header.addStretch()
        header.addWidget(count)
        layout.addLayout(header)
        if not markers:
            layout.addWidget(self._muted_label("- None added"))
            return card
        for marker in markers[:6]:
            marker_label = marker.get("offset_label") or self._format_duration(float(marker.get("offset_seconds") or 0))
            text = str(marker.get("text") or "").strip()
            kind = str(marker.get("type") or "marker").title()
            row = QLabel(f"{marker_label} - {kind}: {text}")
            row.setWordWrap(True)
            layout.addWidget(row)
        return card

    def _overview_action_items_card(self, folder: Path, insights: MeetingInsights) -> QFrame:
        card = QFrame()
        card.setObjectName("RaisedPanel")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(9)
        header = QHBoxLayout()
        label = QLabel("Action items")
        label.setObjectName("SectionTitle")
        count_label = QLabel(str(len(insights.actions)))
        count_label.setObjectName("OrangeText")
        header.addWidget(label)
        header.addStretch()
        header.addWidget(count_label)
        layout.addLayout(header)

        if not insights.actions:
            layout.addWidget(self._muted_label("- None detected"))
            return card

        for index, item in enumerate(insights.actions[:8]):
            row = self._insight_item_widget(item)
            status_combo = QComboBox()
            status_combo.addItems(["open", "in progress", "done", "deferred", "closed"])
            status_combo.setCurrentText(item.status or "open")
            status_combo.setMinimumHeight(32)
            status_combo.setMinimumWidth(132)
            status_combo.setToolTip("Update action item status")
            status_combo.currentTextChanged.connect(
                lambda status, action_index=index, meeting_folder=folder: self._update_action_status(meeting_folder, action_index, status)
            )
            row.layout().addWidget(status_combo)
            edit_button = QPushButton("Edit")
            edit_button.setObjectName("SubtleActionButton")
            edit_button.setMinimumHeight(32)
            edit_button.clicked.connect(lambda checked=False, action_index=index, meeting_folder=folder: self.edit_action_item(meeting_folder, action_index))
            row.layout().addWidget(edit_button)
            layout.addWidget(row)
        return card

    def open_meeting_overview(self, folder: Path | None = None) -> None:
        folder = folder or self._selected_meeting_folder()
        if folder is None:
            QMessageBox.information(self, "Nova Notetaker", "Select a meeting to open.")
            return
        try:
            metadata = self.meeting_store.read_metadata(folder)
        except Exception as error:
            QMessageBox.warning(self, "Nova Notetaker", f"Could not read meeting metadata: {error}")
            return

        dialog = QDialog()
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.setWindowTitle(f"Nova Meeting Overview - {metadata.title or folder.name}")
        dialog.setStyleSheet(build_stylesheet(self.current_theme))
        dialog.setMinimumSize(720, 520)
        dialog.setProperty("meeting_folder", str(folder.resolve()))
        self.meeting_overview_windows.append(dialog)
        dialog.destroyed.connect(lambda *_: self._forget_overview_window(dialog))

        overview_root = QWidget()
        overview_root.setObjectName("OverviewRoot")
        dialog.setLayout(QVBoxLayout())
        dialog.layout().setContentsMargins(0, 0, 0, 0)
        dialog.layout().addWidget(overview_root)

        layout = QVBoxLayout(overview_root)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel(metadata.title or folder.name)
        title.setObjectName("Title")
        subtitle = self._muted_label(f"{metadata.started_at}  |  Status: {metadata.status}")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block)
        header.addStretch()
        open_folder_button = QPushButton("Open folder")
        open_folder_button.clicked.connect(lambda: os.startfile(folder))
        export_button = QPushButton("Export briefing")
        export_button.clicked.connect(lambda: self._export_executive_briefing_for_folder(folder))
        notes_export_button = QPushButton("Export notes")
        notes_export_button.clicked.connect(lambda: self._export_notes_html_for_folder(folder))
        rename_speakers_button = QPushButton("Rename speakers")
        rename_speakers_button.clicked.connect(lambda: self.rename_speakers_for_meeting(folder))
        header.addWidget(open_folder_button)
        header.addWidget(export_button)
        header.addWidget(notes_export_button)
        header.addWidget(rename_speakers_button)
        layout.addLayout(header)

        content = QGridLayout()
        content.setSpacing(16)

        notes_panel = QFrame()
        notes_panel.setObjectName("Panel")
        notes_layout = QVBoxLayout(notes_panel)
        notes_layout.setContentsMargins(18, 18, 18, 18)
        notes_layout.setSpacing(12)
        notes_path = folder / "notes.md"
        summary_lines = self._note_section_lines(notes_path, "summary")
        if summary_lines:
            summary_card = QFrame()
            summary_card.setObjectName("RaisedPanel")
            summary_layout = QVBoxLayout(summary_card)
            summary_layout.setContentsMargins(14, 12, 14, 12)
            summary_layout.setSpacing(7)
            summary_layout.addWidget(self._section_label("Executive summary"))
            for line in summary_lines[:4]:
                summary_label = QLabel(line)
                summary_label.setWordWrap(True)
                summary_layout.addWidget(summary_label)
            notes_layout.addWidget(summary_card)
        notes_layout.addWidget(self._section_label("Structured notes"))
        notes_view = QTextEdit()
        notes_view.setReadOnly(True)
        if notes_path.exists():
            notes_view.setMarkdown(self._notes_for_display(notes_path))
        else:
            notes_view.setPlainText("notes.md has not been created yet.")
        notes_layout.addWidget(notes_view, stretch=1)
        transcript_path = folder / "transcript.md"
        transcript_view = QTextEdit()
        transcript_view.setReadOnly(True)
        if transcript_path.exists():
            transcript_view.setMarkdown(self._transcript_for_display(transcript_path, folder))
        else:
            transcript_view.setPlainText("transcript.md has not been created yet.")
        transcript_view.setMaximumHeight(220)
        notes_layout.addWidget(self._section_label("Transcript"))
        notes_layout.addWidget(transcript_view)

        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setFrameShape(QFrame.NoFrame)
        details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        details_scroll.setMinimumWidth(330)
        details_scroll.setMaximumWidth(430)
        details_panel = QFrame()
        details_panel.setObjectName("Panel")
        details_layout = QVBoxLayout(details_panel)
        details_layout.setContentsMargins(16, 16, 16, 16)
        details_layout.setSpacing(14)
        details_layout.addWidget(self._section_label("Meeting intelligence"))

        insights = load_or_build_insights(folder)
        details_layout.addWidget(self._overview_action_items_card(folder, insights))
        details_layout.addWidget(self._overview_context_card(folder, metadata))
        details_layout.addWidget(self._overview_markers_card(folder))
        for title_text, items in (
            ("Key decisions", insights.decisions),
            ("Scheduling details", insights.dates),
        ):
            count_label = QLabel(str(len(items)))
            card, _items_layout = self._insight_card(title_text, count_label, items or ["None detected"])
            details_layout.addWidget(card)
        if insights.quality_warnings:
            warning_card = QFrame()
            warning_card.setObjectName("RaisedPanel")
            warning_layout = QVBoxLayout(warning_card)
            warning_layout.setContentsMargins(14, 12, 14, 12)
            warning_layout.addWidget(self._section_label("Review needed"))
            for warning in insights.quality_warnings[:4]:
                warning_layout.addWidget(self._muted_label(f"- {warning}"))
            details_layout.addWidget(warning_card)

        details_layout.addWidget(self._section_label("Meeting health"))
        details_layout.addWidget(self._overview_quality_card(folder, metadata, insights))
        details_layout.addWidget(self._overview_resolve_checklist_card(folder, metadata, insights, dialog))
        details_layout.addWidget(self._section_label("Meeting details"))
        health = QTextEdit()
        health.setReadOnly(True)
        health.setMaximumHeight(145)
        health.setPlainText(self._format_health_summary(metadata))
        details_layout.addWidget(health)
        details_layout.addStretch()
        details_scroll.setWidget(details_panel)

        content.addWidget(notes_panel, 0, 0)
        content.addWidget(details_scroll, 0, 1)
        content.setColumnStretch(0, 2)
        content.setColumnStretch(1, 1)
        layout.addLayout(content, stretch=1)
        self._fit_dialog_to_available_screen(dialog, preferred_width=1180, preferred_height=760)
        dialog.show()

    def _forget_overview_window(self, dialog: QDialog) -> None:
        if dialog in self.meeting_overview_windows:
            self.meeting_overview_windows.remove(dialog)

    def _export_notes_html_for_folder(self, folder: Path) -> None:
        notes_path = folder / "notes.md"
        if not notes_path.exists():
            QMessageBox.information(self, "Nova Notetaker", "This meeting does not have notes yet.")
            return
        document = QTextDocument()
        document.setMarkdown(self._notes_for_display(notes_path))
        html_path = folder / "notes.html"
        html_path.write_text(document.toHtml(), encoding="utf-8")
        self.log(f"Exported HTML notes: {html_path}")

    def _export_executive_briefing_for_folder(self, folder: Path) -> None:
        try:
            metadata = self.meeting_store.read_metadata(folder)
        except Exception as error:
            QMessageBox.warning(self, "Nova Notetaker", f"Could not read meeting metadata: {error}")
            return
        insights = load_or_build_insights(folder)
        html_path = folder / "executive_briefing.html"
        html_path.write_text(self._executive_briefing_html(folder, metadata, insights), encoding="utf-8")
        self.log(f"Exported executive briefing: {html_path}")

    def _executive_briefing_html(self, folder: Path, metadata: MeetingMetadata, insights: MeetingInsights) -> str:
        notes_path = folder / "notes.md"
        summary_lines = self._note_section_lines(notes_path, "summary")
        warnings = insights.quality_warnings + insights.warnings
        title = html.escape(metadata.title or folder.name)
        started = html.escape(metadata.started_at or "")

        def list_html(items: list[str]) -> str:
            if not items:
                return "<p class=\"muted\">None captured.</p>"
            return "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in items) + "</ul>"

        def insight_list(items: list[InsightItem]) -> str:
            if not items:
                return "<p class=\"muted\">None captured.</p>"
            rows = []
            for item in items:
                badges = []
                for value in (item.owner if item.kind == "action" else "", item.due_date, item.status if item.kind == "action" else "", item.confidence):
                    if value:
                        badges.append(f"<span>{html.escape(value)}</span>")
                rows.append(
                    "<li>"
                    f"<div>{html.escape(item.display_text)}</div>"
                    f"<div class=\"badges\">{''.join(badges)}</div>"
                    "</li>"
                )
            return "<ul>" + "".join(rows) + "</ul>"

        return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Nova Meeting Briefing - {title}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; color: #1f2933; margin: 42px; line-height: 1.45; }}
    h1 {{ margin-bottom: 4px; }}
    h2 {{ margin-top: 28px; border-bottom: 1px solid #d5d9df; padding-bottom: 6px; }}
    .muted {{ color: #667085; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 22px 0; }}
    .metric {{ border: 1px solid #d5d9df; border-radius: 8px; padding: 12px; }}
    .metric strong {{ display: block; font-size: 24px; }}
    li {{ margin: 8px 0; }}
    .badges span {{ display: inline-block; margin: 6px 6px 0 0; padding: 2px 7px; border-radius: 999px; background: #eef1f5; color: #425466; font-size: 12px; }}
    @media print {{ body {{ margin: 24px; }} }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <div class="muted">{started} | Status: {html.escape(metadata.status)}</div>
  <div class="grid">
    <div class="metric"><strong>{sum(1 for item in insights.actions if item.status.lower() not in CLOSED_ACTION_STATUSES)}</strong>Open actions</div>
    <div class="metric"><strong>{len(insights.decisions)}</strong>Decisions</div>
    <div class="metric"><strong>{len(insights.dates)}</strong>Dates</div>
    <div class="metric"><strong>{len(warnings)}</strong>Review warnings</div>
  </div>
  <h2>Executive Summary</h2>
  {list_html(summary_lines)}
  <h2>Key Decisions</h2>
  {insight_list(insights.decisions)}
  <h2>Action Items</h2>
  {insight_list(insights.actions)}
  <h2>Dates / Follow-ups</h2>
  {insight_list(insights.dates)}
  <h2>Review Needed</h2>
  {list_html([str(item.text if isinstance(item, InsightItem) else item) for item in warnings])}
</body>
</html>
"""

    def rename_speakers_for_meeting(self, folder: Path) -> None:
        transcript_path = folder / "transcript.md"
        if not transcript_path.exists():
            QMessageBox.information(self, "Nova Notetaker", "This meeting does not have a transcript yet.")
            return
        transcript_text = transcript_path.read_text(encoding="utf-8", errors="ignore")
        speakers = transcript_speakers(transcript_text)
        if not speakers:
            QMessageBox.information(self, "Nova Notetaker", "No transcript speaker headings were found.")
            return
        aliases = read_speaker_aliases(folder)
        changed = False
        for speaker in speakers:
            current = aliases.get(speaker, speaker)
            prompt = f"{speaker}\nLeave unchanged to keep the transcript label; clear to remove a saved alias."
            value, accepted = QInputDialog.getText(self, "Rename Speaker", prompt, text=current)
            if not accepted:
                continue
            value = value.strip()
            if value and value != speaker:
                aliases[speaker] = value
                changed = True
            elif speaker in aliases:
                aliases.pop(speaker)
                changed = True
        if changed:
            write_speaker_aliases(folder, aliases)
            self.log(f"Updated speaker names for {folder.name}")
            QMessageBox.information(self, "Nova Notetaker", "Speaker names updated. Reopen the meeting overview to see the refreshed transcript labels.")

    @classmethod
    def _note_section_lines(cls, notes_path: Path, section_name: str) -> list[str]:
        if not notes_path.exists():
            return []
        target = section_name.lower()
        in_section = False
        lines: list[str] = []
        for raw_line in notes_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = cls._plain_note_text(raw_line).strip()
            if line.startswith("## "):
                in_section = target in line.lower()
                continue
            if in_section and line.startswith("-"):
                item = line.lstrip("- ").strip()
                if item and item.lower().rstrip(".") not in {"none", "none captured"}:
                    lines.append(item)
            elif in_section and line.startswith("## "):
                break
        return lines

    @staticmethod
    def _notes_for_display(notes_path: Path) -> str:
        import re
        text = notes_path.read_text(encoding="utf-8")
        text = re.sub(r";\s*Source:\s*<span[^>]*>[^<]+</span>", "", text)
        text = re.sub(r";\s*Source:\s*[^;\n]+", "", text)
        text = re.sub(r"\bSource:\s*<span[^>]*>[^<]+</span>;?\s*", "", text)
        text = re.sub(r"\bSource:\s*[^;\n]+;?\s*", "", text)
        return text

    @staticmethod
    def _transcript_for_display(transcript_path: Path, folder: Path) -> str:
        text = transcript_path.read_text(encoding="utf-8", errors="ignore")
        return apply_speaker_aliases_to_markdown(text, read_speaker_aliases(folder))

    def repair_selected_meeting(self) -> None:
        folder = self._selected_meeting_folder()
        if folder is None:
            QMessageBox.information(self, "Nova Notetaker", "Select a meeting to repair.")
            return
        self.repair_meeting(folder)

    def repair_meeting(self, folder: Path) -> None:
        if self.processing_thread is not None or self.batch_processing_thread is not None:
            QMessageBox.information(self, "Nova Notetaker", "Nova is already processing meetings.")
            return
        try:
            metadata = self.meeting_store.read_metadata(folder)
        except Exception as error:
            QMessageBox.warning(self, "Nova Notetaker", f"Could not read meeting metadata: {error}")
            return

        transcript_path = folder / "transcript.md"
        notes_path = folder / "notes.md"
        insights_path = folder / "insights.json"
        has_transcript = self._meeting_has_transcript(folder)
        needs_full_retry = not has_transcript or "failed" in metadata.status.lower()
        if isinstance(metadata.processing, dict):
            warnings = metadata.processing.get("warnings", [])
            if any("failed for chunk" in str(warning).lower() for warning in warnings if warning):
                needs_full_retry = True

        if notes_path.exists() and has_transcript and not needs_full_retry:
            insights = load_or_build_insights(folder)
            write_insights_json(folder, insights)
            metadata.status = "processed_with_warnings" if insights.quality_warnings else "processed"
            metadata.processing = {
                **(metadata.processing if isinstance(metadata.processing, dict) else {}),
                "notes_path": str(notes_path),
                "transcript_path": str(transcript_path),
                "insights_path": str(insights_path),
            }
            self.meeting_store.write_metadata(folder, metadata)
            self.refresh_meetings()
            self.refresh_review_center()
            self.archive_status.setText("Repair complete")
            self.log(f"Rebuilt insights for repaired meeting: {folder.name}")
            return

        mode = "full" if needs_full_retry else "notes_only"
        metadata.status = "processing"
        self.meeting_store.write_metadata(folder, metadata)
        self.meeting_folder = folder
        self.metadata = metadata
        for button_name in ("repair_meeting_button", "reprocess_button", "batch_reprocess_button", "rebuild_index_button"):
            if hasattr(self, button_name):
                getattr(self, button_name).setEnabled(False)
        self.archive_status.setText("Repairing selected meeting...")
        self.log(f"Repairing meeting with {mode} processing: {folder}")
        self._start_processing(folder, metadata, mode=mode)
