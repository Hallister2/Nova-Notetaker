from __future__ import annotations

import os
import re
import shutil
import stat
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.intelligence.insights import InsightItem, MeetingInsights, load_or_build_insights, write_insights_json
from app.storage.meeting_store import MeetingMetadata
from app.ui.constants import CLOSED_ACTION_STATUSES
from app.ui.dialogs import ReprocessDialog
from app.ui.styles import build_stylesheet
from app.ui.widgets import SortableTableItem
from app.workflows.meeting_processor import MeetingProcessor


class MeetingsTabMixin:
    def _build_meetings_page(self) -> QWidget:
        meetings_tab = QWidget()
        meetings_layout = QGridLayout(meetings_tab)
        self.meetings_layout = meetings_layout
        meetings_layout.setContentsMargins(34, 28, 18, 28)
        meetings_layout.setSpacing(18)

        meetings_panel = QFrame()
        meetings_panel.setObjectName("Panel")
        meetings_panel_layout = QVBoxLayout(meetings_panel)
        meetings_panel_layout.setContentsMargins(18, 18, 18, 18)
        meetings_title = QLabel("Meetings")
        meetings_title.setObjectName("Title")
        self.meetings_empty_state = self._empty_state_widget(
            "meetings",
            "No meetings yet",
            "Captured meetings will appear here after your first recording.",
        )
        self.meeting_table = QTableWidget(0, 7)
        self.meeting_table.setMinimumWidth(0)
        self.meeting_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.meeting_table.setHorizontalHeaderLabels(["Date", "Time", "Meeting Name", "Status", "Actions", "Review", "Open"])
        self._configure_table(self.meeting_table)
        self.meeting_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.meeting_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.meeting_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.meeting_table.itemDoubleClicked.connect(lambda _item: self.open_meeting_overview())
        self.meeting_table.setSortingEnabled(True)
        self.meeting_table.verticalHeader().setVisible(False)
        header = self.meeting_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        self.meeting_table.setColumnWidth(3, 150)
        self.meeting_table.setColumnWidth(4, 76)
        self.meeting_table.setColumnWidth(5, 76)
        self.meeting_table.setColumnWidth(6, 112)
        self.meeting_table.verticalHeader().setDefaultSectionSize(50)
        filters = QHBoxLayout()
        filters.setSpacing(10)
        self.meeting_filter_combo = QComboBox()
        self.meeting_filter_combo.addItems(["All meetings", "Needs repair", "Needs review", "Has open actions", "Complete", "Missing transcript"])
        self.meeting_filter_combo.currentIndexChanged.connect(self.refresh_meetings)
        self.meeting_filter_combo.setMinimumHeight(38)
        self.meeting_filter_combo.setMinimumWidth(190)
        filters.addWidget(QLabel("Filter"))
        filters.addWidget(self.meeting_filter_combo)
        filters.addStretch()
        archive_buttons = QGridLayout()
        archive_buttons.setHorizontalSpacing(8)
        archive_buttons.setVerticalSpacing(8)
        self.refresh_meetings_button = QPushButton("Refresh")
        self.refresh_meetings_button.clicked.connect(self.refresh_meetings)
        self.reprocess_button = QPushButton("Reprocess")
        self.reprocess_button.clicked.connect(self.reprocess_selected_meeting)
        self.repair_meeting_button = QPushButton("Retry / repair")
        self.repair_meeting_button.clicked.connect(self.repair_selected_meeting)
        self.batch_reprocess_button = QPushButton("Batch reprocess")
        self.batch_reprocess_button.clicked.connect(self.batch_reprocess_selected_meetings)
        self.rebuild_index_button = QPushButton("Rebuild index")
        self.rebuild_index_button.clicked.connect(self.rebuild_meeting_intelligence_index)
        self.open_folder_button = QPushButton("Open folder")
        self.open_folder_button.clicked.connect(self.open_selected_meeting_folder)
        self.pin_meeting_button = QPushButton("Pin important")
        self.pin_meeting_button.clicked.connect(self.mark_selected_meeting_important)
        self.export_html_button = QPushButton("Export briefing")
        self.export_html_button.clicked.connect(self.export_selected_executive_briefing)
        self.export_calendar_button = QPushButton("Export calendar")
        self.export_calendar_button.clicked.connect(self.export_selected_calendar_ics)
        self.delete_meeting_button = QPushButton("Delete selected")
        self.delete_meeting_button.clicked.connect(self.delete_selected_meetings)
        archive_button_list = (
            self.refresh_meetings_button,
            self.reprocess_button,
            self.repair_meeting_button,
            self.batch_reprocess_button,
            self.rebuild_index_button,
            self.open_folder_button,
            self.pin_meeting_button,
            self.export_html_button,
            self.export_calendar_button,
            self.delete_meeting_button,
        )
        for index, button in enumerate(archive_button_list):
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            archive_buttons.addWidget(button, index // 4, index % 4)
        self.archive_status = self._muted_label("Ready")
        meetings_panel_layout.addWidget(meetings_title)
        meetings_panel_layout.addLayout(filters)
        meetings_panel_layout.addWidget(self.meetings_empty_state, stretch=1)
        meetings_panel_layout.addWidget(self.meeting_table, stretch=1)
        meetings_panel_layout.addLayout(archive_buttons)
        meetings_panel_layout.addWidget(self.archive_status)

        meetings_layout.addWidget(meetings_panel, 0, 0)
        meetings_layout.setColumnStretch(0, 1)
        return meetings_tab

    def _build_meeting_details_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(380)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        title = QLabel("Meeting details")
        title.setObjectName("Title")
        layout.addWidget(title)
        self.selected_meeting_summary = self._muted_label("Select a meeting to review extracted details.")
        layout.addWidget(self.selected_meeting_summary)
        self.selected_action_count = QLabel("0")
        self.selected_decision_count = QLabel("0")
        self.selected_date_count = QLabel("0")
        action_card, self.selected_action_items_layout = self._insight_card("Action items", self.selected_action_count, ["No meeting selected"])
        decision_card, self.selected_decisions_layout = self._insight_card("Key decisions", self.selected_decision_count, ["No meeting selected"])
        dates_card, self.selected_dates_layout = self._insight_card("Scheduling details", self.selected_date_count, ["No meeting selected"])
        layout.addWidget(action_card)
        layout.addWidget(decision_card)
        layout.addWidget(dates_card)
        layout.addStretch()
        return panel

    def _apply_meetings_responsive(self, mode: str) -> None:
        if mode == "narrow":
            self.meetings_layout.setContentsMargins(16, 18, 12, 18)
        else:
            self.meetings_layout.setContentsMargins(28 if mode == "compact" else 34, 28, 18, 28)

    def refresh_meetings(self) -> None:
        if not hasattr(self, "meeting_table"):
            return
        current_folder = self._selected_meeting_folder()
        self.meeting_table.setSortingEnabled(False)
        self.meeting_table.setRowCount(0)
        for folder in self.meeting_store.list_meetings():
            insights = MeetingInsights()
            try:
                metadata = self.meeting_store.read_metadata(folder)
                date_text, time_text = self._split_started_at(metadata.started_at)
                title = metadata.title or folder.name
                status = metadata.status
                insights = load_or_build_insights(folder)
                self._auto_close_stale_actions(folder, metadata, insights)
            except Exception:
                metadata = None
                date_text, time_text, title, status = "", "", folder.name, "unknown"

            open_actions = sum(1 for item in insights.actions if item.status.lower() not in CLOSED_ACTION_STATUSES)
            processing_warnings = metadata.processing.get("warnings", []) if metadata and isinstance(metadata.processing, dict) else []
            review_count = len(insights.quality_warnings) + len(insights.warnings) + len(processing_warnings)
            if not self._meeting_matches_filter(folder, metadata, status, open_actions, review_count):
                continue

            row = self.meeting_table.rowCount()
            self.meeting_table.insertRow(row)
            transcript_path = folder / "transcript.md"
            has_transcript = transcript_path.exists() and bool(
                MeetingProcessor._usable_existing_transcript_text(transcript_path.read_text(encoding="utf-8", errors="ignore")).strip()
            )
            status_label = self._meeting_status_label(status, review_count, has_transcript)
            values = [date_text, time_text, title, status_label, str(open_actions), str(review_count)]
            for column, value in enumerate(values):
                display_value = "" if column == 3 else value
                item = SortableTableItem(display_value)
                item.setData(Qt.UserRole, str(folder))
                item.setData(Qt.UserRole + 1, self._meeting_sort_key(column, date_text, time_text, title, status, open_actions, review_count))
                if column in (0, 1):
                    item.setTextAlignment(Qt.AlignCenter)
                if column == 3:
                    item.setTextAlignment(Qt.AlignCenter)
                if column in (4, 5):
                    item.setTextAlignment(Qt.AlignCenter)
                self.meeting_table.setItem(row, column, item)

            status_cell = QWidget()
            status_cell.setObjectName("Transparent")
            status_layout = QHBoxLayout(status_cell)
            status_layout.setContentsMargins(6, 4, 6, 4)
            status_layout.addWidget(self._status_badge(status_label), alignment=Qt.AlignCenter)
            self.meeting_table.setCellWidget(row, 3, status_cell)

            open_button = QPushButton("Open")
            open_button.setObjectName("TableActionButton")
            open_button.setFixedSize(82, 32)
            open_button.setToolTip("Open this meeting overview")
            open_button.clicked.connect(lambda checked=False, meeting_folder=folder: self.open_meeting_overview(meeting_folder))
            open_item = SortableTableItem("")
            open_item.setData(Qt.UserRole, str(folder))
            open_item.setData(Qt.UserRole + 1, "")
            self.meeting_table.setItem(row, 6, open_item)
            open_cell = QWidget()
            open_cell.setObjectName("Transparent")
            open_layout = QHBoxLayout(open_cell)
            open_layout.setContentsMargins(5, 5, 5, 5)
            open_layout.addWidget(open_button, alignment=Qt.AlignCenter)
            self.meeting_table.setCellWidget(row, 6, open_cell)
            self.meeting_table.setRowHeight(row, 50)

            if current_folder and folder == current_folder:
                self.meeting_table.selectRow(row)

        self.meeting_table.setSortingEnabled(True)
        self.meeting_table.sortItems(0, Qt.DescendingOrder)
        self.meeting_table.setColumnWidth(3, 172)
        self.meeting_table.setColumnWidth(4, 92)
        self.meeting_table.setColumnWidth(5, 92)
        self.meeting_table.setColumnWidth(6, 112)
        if self.meeting_table.rowCount() and self._selected_meeting_folder() is None:
            self.meeting_table.selectRow(0)
        if hasattr(self, "meetings_empty_state"):
            has_rows = self.meeting_table.rowCount() > 0
            self.meeting_table.setVisible(has_rows)
            self.meetings_empty_state.setVisible(not has_rows)
        if hasattr(self, "open_latest_button"):
            self.open_latest_button.setEnabled(bool(self.meeting_store.list_meetings()))
        try:
            from app.storage.meeting_index import write_meeting_index
            write_meeting_index(self.meeting_store)
        except Exception as error:
            self.log(f"Meeting index refresh failed: {error}")
        self.refresh_review_center()

    def _meeting_matches_filter(
        self,
        folder: Path,
        metadata: MeetingMetadata | None,
        status: str,
        open_actions: int,
        review_count: int,
    ) -> bool:
        selected_filter = self.meeting_filter_combo.currentText() if hasattr(self, "meeting_filter_combo") else "All meetings"
        if selected_filter == "Needs repair":
            return self._meeting_needs_repair(folder, metadata)
        if selected_filter == "Needs review":
            return review_count > 0
        if selected_filter == "Has open actions":
            return open_actions > 0
        if selected_filter == "Complete":
            return status.startswith("processed")
        if selected_filter == "Missing transcript":
            transcript_path = folder / "transcript.md"
            if not transcript_path.exists():
                return True
            transcript_text = transcript_path.read_text(encoding="utf-8", errors="ignore")
            return not MeetingProcessor._usable_existing_transcript_text(transcript_text).strip()
        return True

    def _meeting_needs_repair(self, folder: Path, metadata: MeetingMetadata | None = None) -> bool:
        if metadata and "failed" in metadata.status.lower():
            return True
        if metadata and metadata.status.lower() in {"processing", "transcribing"}:
            return True
        if not self._meeting_has_transcript(folder):
            return True
        if not (folder / "notes.md").exists():
            return True
        if metadata and isinstance(metadata.processing, dict):
            warnings = metadata.processing.get("warnings", [])
            if any("failed for chunk" in str(warning).lower() for warning in warnings if warning):
                return True
        return False

    def preview_selected_meeting(self) -> None:
        self.update_meeting_health()
        self.preview_selected_meeting_file(self.active_preview_file)

    def preview_selected_meeting_file(self, file_name: str) -> None:
        folder = self._selected_meeting_folder()
        if not hasattr(self, "meeting_preview_title"):
            return
        if folder is None:
            self.meeting_preview_title.setText("SELECT A MEETING")
            self.meeting_preview.clear()
            self._update_selected_meeting_details(None)
            return
        self.active_preview_file = file_name
        self.update_meeting_health()
        self._update_selected_meeting_details(folder)
        path = folder / file_name
        self.meeting_preview_title.setText(f"{folder.name} / {file_name}")
        if not path.exists():
            self.meeting_preview.setPlainText(f"{file_name} has not been created yet.")
            return
        content = path.read_text(encoding="utf-8")
        if file_name == "notes.md":
            self.meeting_preview.setMarkdown(content)
        else:
            self.meeting_preview.setPlainText(content)

    def update_meeting_health(self) -> None:
        if not hasattr(self, "meeting_health"):
            return
        folder = self._selected_meeting_folder()
        if folder is None:
            self.meeting_health.clear()
            return
        try:
            metadata = self.meeting_store.read_metadata(folder)
            self.meeting_health.setPlainText(self._format_health_summary(metadata))
        except Exception as error:
            self.meeting_health.setPlainText(f"Health summary unavailable: {error}")

    def _meeting_has_transcript(self, folder: Path) -> bool:
        transcript_path = folder / "transcript.md"
        if not transcript_path.exists():
            return False
        transcript_text = transcript_path.read_text(encoding="utf-8", errors="ignore")
        return bool(MeetingProcessor._usable_existing_transcript_text(transcript_text).strip())

    def _meeting_is_important(self, folder: Path) -> bool:
        return any(str(marker.get("type", "")).lower() == "important" for marker in self.meeting_store.read_markers(folder))

    def _meeting_readiness_score(self, folder: Path, metadata: MeetingMetadata, insights: MeetingInsights) -> tuple[int, list[str]]:
        score = 100
        lines: list[str] = []
        if not self._meeting_has_transcript(folder):
            score -= 30
            lines.append("Transcript missing")
        if not (folder / "notes.md").exists():
            score -= 25
            lines.append("Notes missing")
        if "failed" in metadata.status.lower():
            score -= 25
            lines.append("Processing failed")
        unknown_owner_count = sum(1 for item in insights.actions if not item.owner or item.owner.lower() == "unknown")
        unknown_due_count = sum(1 for item in insights.actions if not item.due_date or item.due_date.lower() == "unknown")
        low_confidence_count = sum(
            1
            for item in [*insights.actions, *insights.decisions, *insights.dates]
            if item.confidence.lower() in {"low", "tentative"}
        )
        if unknown_owner_count:
            score -= min(15, unknown_owner_count * 5)
            lines.append(f"{unknown_owner_count} action owner(s) missing")
        if unknown_due_count:
            score -= min(10, unknown_due_count * 3)
            lines.append(f"{unknown_due_count} action due date(s) missing")
        if low_confidence_count:
            score -= min(10, low_confidence_count * 3)
            lines.append(f"{low_confidence_count} low-confidence item(s)")
        if not lines:
            lines.append("Ready for review/export")
        return max(0, min(100, score)), lines

    def _selected_meeting_folder(self) -> Path | None:
        if not hasattr(self, "meeting_table"):
            return None
        selected_items = self.meeting_table.selectedItems()
        if not selected_items:
            return None
        raw_path = selected_items[0].data(Qt.UserRole)
        return Path(raw_path) if raw_path else None

    def _selected_meeting_folders(self) -> list[Path]:
        if not hasattr(self, "meeting_table"):
            return []
        folders: list[Path] = []
        seen: set[str] = set()
        for item in self.meeting_table.selectedItems():
            raw_path = item.data(Qt.UserRole)
            if not raw_path or raw_path in seen:
                continue
            seen.add(raw_path)
            folders.append(Path(raw_path))
        return folders

    @staticmethod
    def _split_started_at(started_at: str) -> tuple[str, str]:
        if not started_at:
            return "", ""
        try:
            value = datetime.fromisoformat(started_at)
            return value.strftime("%Y-%m-%d"), value.strftime("%H:%M:%S")
        except ValueError:
            parts = started_at.split("T", 1)
            return parts[0], parts[1] if len(parts) > 1 else ""

    @staticmethod
    def _meeting_status_label(status: str, review_count: int, has_transcript: bool = True) -> str:
        normalized = status.lower()
        if "failed" in normalized:
            return "Processing failed"
        if not has_transcript:
            return "Missing transcript"
        if review_count:
            return "Needs review"
        if normalized.startswith("processed"):
            return "Complete"
        if normalized in {"recording", "processing", "transcribing"}:
            return "Processing"
        if normalized in {"stub", "draft", "unknown"}:
            return "Draft"
        return status.replace("_", " ").title()

    @staticmethod
    def _meeting_status_state(label: str) -> str:
        normalized = label.lower()
        if normalized == "complete":
            return "complete"
        if "review" in normalized or "missing" in normalized:
            return "review"
        if "processing" in normalized:
            return "processing"
        return "draft"

    @staticmethod
    def _meeting_sort_key(
        column: int,
        date_text: str,
        time_text: str,
        title: str,
        status: str,
        open_actions: int = 0,
        review_count: int = 0,
    ) -> str:
        full_timestamp = f"{date_text} {time_text}".strip()
        if column == 0:
            return full_timestamp
        if column == 1:
            return full_timestamp
        if column == 2:
            return title.lower()
        if column == 3:
            return status.lower()
        if column == 4:
            return f"{open_actions:06d}"
        if column == 5:
            return f"{review_count:06d}"
        return ""

    def _format_health_summary(self, metadata: MeetingMetadata) -> str:
        warnings = metadata.processing.get("warnings", []) if isinstance(metadata.processing, dict) else []
        lines = [
            f"Status: {metadata.status}",
            f"Profile: {self._profile_label(metadata.capture_profile or '')}",
            f"Meeting Profile: {metadata.meeting_profile.get('name', 'Unknown') if isinstance(metadata.meeting_profile, dict) else 'Unknown'}",
            f"Template: {metadata.note_template.get('name', 'Unknown') if isinstance(metadata.note_template, dict) else 'Unknown'}",
            f"Mic Capture: {'on' if metadata.capture_mic else 'muted'}",
            f"Started: {metadata.started_at}",
            f"Ended: {metadata.ended_at or 'Unknown'}",
        ]

        for label in ("mic", "system"):
            audio_info = metadata.audio_files.get(label, {}) if isinstance(metadata.audio_files, dict) else {}
            if not audio_info:
                lines.append(f"{label}.wav: no validation data")
                continue
            valid = "valid" if audio_info.get("valid") else "invalid"
            duration = audio_info.get("duration_seconds", 0)
            sample_rate = audio_info.get("sample_rate") or "?"
            channels = audio_info.get("channels") or "?"
            size = audio_info.get("size_bytes", 0)
            lines.append(f"{label}.wav: {valid}, {duration}s, {sample_rate} Hz, {channels} ch, {size} bytes")

        bleed_warning = next((warning for warning in warnings if "speaker-bleed" in warning.lower()), None)
        if bleed_warning:
            lines.append(f"Bleed: likely detected ({bleed_warning})")
        elif warnings:
            lines.append(f"Warnings: {len(warnings)}")
        else:
            lines.append("Warnings: none")

        diagnostics = metadata.processing.get("diagnostics", {}) if isinstance(metadata.processing, dict) else {}
        if isinstance(diagnostics, dict) and diagnostics:
            processing_seconds = diagnostics.get("processing_seconds")
            transcription_seconds = diagnostics.get("transcription_seconds")
            notes_seconds = diagnostics.get("notes_seconds")
            if processing_seconds:
                lines.append(f"Processing time: {self._format_duration(float(processing_seconds))}")
            if transcription_seconds:
                lines.append(f"Transcription time: {self._format_duration(float(transcription_seconds))}")
            if notes_seconds:
                lines.append(f"Notes time: {self._format_duration(float(notes_seconds))}")
            transcription = diagnostics.get("transcription", {})
            if isinstance(transcription, dict):
                for source, details in transcription.items():
                    if not isinstance(details, dict) or not details.get("chunk_count"):
                        continue
                    lines.append(
                        f"{source} chunks: {details.get('successful_chunks', 0)}/{details.get('chunk_count')} ok, "
                        f"{details.get('failed_chunks', 0)} failed, {details.get('reused_chunks', 0)} reused"
                    )

        return "\n".join(lines)

    def open_selected_meeting_folder(self) -> None:
        folder = self._selected_meeting_folder()
        if folder is None:
            QMessageBox.information(self, "Nova Notetaker", "Select a meeting to open.")
            return
        os.startfile(folder)

    def export_selected_notes_html(self) -> None:
        folder = self._selected_meeting_folder()
        if folder is None:
            QMessageBox.information(self, "Nova Notetaker", "Select a meeting to export.")
            return
        notes_path = folder / "notes.md"
        if not notes_path.exists():
            QMessageBox.information(self, "Nova Notetaker", "This meeting does not have notes yet.")
            return
        self._export_notes_html_for_folder(folder)

    def export_selected_executive_briefing(self) -> None:
        folder = self._selected_meeting_folder()
        if folder is None:
            QMessageBox.information(self, "Nova Notetaker", "Select a meeting to export.")
            return
        self._export_executive_briefing_for_folder(folder)

    def copy_current_preview(self) -> None:
        if not hasattr(self, "meeting_preview"):
            return
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.meeting_preview.toPlainText())
        self.log(f"Copied {self.active_preview_file} preview to clipboard.")

    def delete_selected_meetings(self) -> None:
        folders = self._selected_meeting_folders()
        if not folders:
            QMessageBox.information(self, "Nova Notetaker", "Select one or more meetings to delete.")
            return
        count = len(folders)
        noun = "meeting" if count == 1 else "meetings"
        response = QMessageBox.question(
            self,
            "Delete meetings",
            f"Delete {count} selected {noun}? This will remove the meeting folder and its audio, transcript, notes, and metadata.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if response != QMessageBox.Yes:
            return

        meetings_root = self.meeting_store.meetings_root.resolve()
        deleted = 0
        skipped: list[str] = []
        for folder in folders:
            try:
                resolved = folder.resolve()
                if meetings_root not in resolved.parents:
                    skipped.append(folder.name)
                    continue
                if self._meeting_folder_is_active(resolved):
                    skipped.append(f"{folder.name}: meeting is currently recording or processing")
                    continue
                self._close_views_for_meeting_folder(resolved)
                self._remove_meeting_folder(resolved)
                deleted += 1
            except Exception as error:
                skipped.append(f"{folder.name}: {error}")

        self.log(f"Deleted {deleted} {noun}.")
        if skipped:
            self.log(f"Skipped {len(skipped)} meeting(s): {'; '.join(skipped)}")
            QMessageBox.warning(self, "Nova Notetaker", f"Deleted {deleted}, skipped {len(skipped)}. See Logs for details.")
        self.refresh_meetings()

    def _meeting_folder_is_active(self, folder: Path) -> bool:
        if not self.meeting_folder:
            return False
        try:
            active_folder = self.meeting_folder.resolve()
        except Exception:
            return False
        if active_folder != folder:
            return False
        return bool(self.worker or self.processing_thread or self.live_transcription_thread or self.pending_processing_job)

    def _close_views_for_meeting_folder(self, folder: Path) -> None:
        folder_raw = str(folder)
        for dialog in list(self.meeting_overview_windows):
            if dialog.property("meeting_folder") == folder_raw:
                dialog.close()
        if self.overview_workspace_folder:
            try:
                if self.overview_workspace_folder.resolve() == folder:
                    self.overview_workspace_folder = None
                    while self.overview_workspace_layout.count() > 0:
                        item = self.overview_workspace_layout.takeAt(0)
                        widget = item.widget()
                        if widget is not None:
                            widget.deleteLater()
                    self.overview_workspace_layout.addWidget(
                        self._empty_state_widget("meetings", "No meeting selected", "Open a meeting from Meetings, Search, Calendar, or Actions."),
                        stretch=1,
                    )
            except Exception:
                pass

    def _remove_meeting_folder(self, folder: Path) -> None:
        def make_writable(path: str) -> None:
            try:
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            except Exception:
                pass

        def retry_with_writable(function, path: str, exc) -> None:
            make_writable(path)
            function(path)

        for root, dirs, files in os.walk(folder):
            for name in [*files, *dirs]:
                make_writable(str(Path(root) / name))
        make_writable(str(folder))

        try:
            shutil.rmtree(folder, onexc=retry_with_writable)
        except TypeError:
            shutil.rmtree(folder, onerror=lambda function, path, exc_info: retry_with_writable(function, path, exc_info[1]))
        if folder.exists():
            make_writable(str(folder))
            os.rmdir(folder)

    def reprocess_selected_meeting(self) -> None:
        folder = self._selected_meeting_folder()
        if folder is None:
            QMessageBox.information(self, "Nova Notetaker", "Select a meeting to reprocess.")
            return
        if self.processing_thread is not None:
            QMessageBox.information(self, "Nova Notetaker", "Nova is already processing a meeting.")
            return
        try:
            metadata = self.meeting_store.read_metadata(folder)
        except Exception as error:
            QMessageBox.warning(self, "Nova Notetaker", f"Could not read meeting metadata: {error}")
            return
        self.meeting_profiles = self.profile_store.list_profiles()
        self.note_templates = self.template_store.list_templates()
        current_profile_id = (
            str(metadata.meeting_profile.get("id", ""))
            if isinstance(metadata.meeting_profile, dict)
            else ""
        ) or self.settings.get("app", {}).get("selected_profile_id", "general")
        current_template_id = (
            str(metadata.note_template.get("id", ""))
            if isinstance(metadata.note_template, dict)
            else ""
        ) or self.settings.get("app", {}).get("selected_template_id", "standard")
        dialog = ReprocessDialog(
            self,
            self.meeting_profiles,
            self.note_templates,
            current_profile_id,
            current_template_id,
        )
        dialog.setStyleSheet(build_stylesheet(self.current_theme))
        if dialog.exec() != QDialog.Accepted:
            return
        meeting_profile = self.profile_store.get_profile(dialog.profile_id)
        note_template = self.template_store.get_template(dialog.template_id)
        metadata.meeting_profile = self._profile_metadata(meeting_profile)
        metadata.note_template = self._template_metadata(note_template)
        metadata.status = "processing"
        self.meeting_store.write_metadata(folder, metadata)
        self.meeting_folder = folder
        self.metadata = metadata
        self.recording_button.setEnabled(False)
        self.recording_button.setText("Processing...")
        self.recording_button.setObjectName("DangerButton")
        self._refresh_widget_style(self.recording_button)
        self.reprocess_button.setEnabled(False)
        if hasattr(self, "repair_meeting_button"):
            self.repair_meeting_button.setEnabled(False)
        if hasattr(self, "batch_reprocess_button"):
            self.batch_reprocess_button.setEnabled(False)
        if hasattr(self, "rebuild_index_button"):
            self.rebuild_index_button.setEnabled(False)
        self.refresh_meetings_button.setEnabled(False)
        self.open_folder_button.setEnabled(False)
        self.export_html_button.setEnabled(False)
        if hasattr(self, "export_calendar_button"):
            self.export_calendar_button.setEnabled(False)
        self.archive_status.setText("Reprocessing selected meeting...")
        if hasattr(self, "meeting_preview"):
            self.meeting_preview.setPlainText("Reprocessing selected meeting...")
        self._set_active_nav(1)
        self.log(
            f"Reprocessing meeting ({dialog.mode}) with {meeting_profile.name} / {note_template.name}: {folder}"
        )
        self._start_processing(folder, metadata, mode=dialog.mode)

    def batch_reprocess_selected_meetings(self) -> None:
        from app.ui.workers import BatchProcessingWorker
        from PySide6.QtCore import QThread
        folders = self._selected_meeting_folders()
        if not folders:
            QMessageBox.information(self, "Nova Notetaker", "Select one or more meetings to batch reprocess.")
            return
        if self.processing_thread is not None or self.batch_processing_thread is not None:
            QMessageBox.information(self, "Nova Notetaker", "Nova is already processing meetings.")
            return

        self.meeting_profiles = self.profile_store.list_profiles()
        self.note_templates = self.template_store.list_templates()
        dialog = ReprocessDialog(
            self,
            self.meeting_profiles,
            self.note_templates,
            self.settings.get("app", {}).get("selected_profile_id", "general"),
            self.settings.get("app", {}).get("selected_template_id", "standard"),
        )
        dialog.setWindowTitle("Batch Reprocess Meetings")
        dialog.setStyleSheet(build_stylesheet(self.current_theme))
        if dialog.exec() != QDialog.Accepted:
            return

        meeting_profile = self.profile_store.get_profile(dialog.profile_id)
        note_template = self.template_store.get_template(dialog.template_id)
        jobs: list[tuple[Path, MeetingMetadata]] = []
        for folder in folders:
            try:
                metadata = self.meeting_store.read_metadata(folder)
                metadata.meeting_profile = self._profile_metadata(meeting_profile)
                metadata.note_template = self._template_metadata(note_template)
                metadata.status = "processing"
                self.meeting_store.write_metadata(folder, metadata)
                jobs.append((folder, metadata))
            except Exception as error:
                self.log(f"Skipping batch reprocess for {folder.name}: {error}")

        if not jobs:
            QMessageBox.warning(self, "Nova Notetaker", "No selected meetings could be prepared for reprocess.")
            return

        self._set_active_nav(5)
        self.archive_status.setText(f"Batch reprocessing {len(jobs)} meeting(s)...")
        self.reprocess_button.setEnabled(False)
        self.batch_reprocess_button.setEnabled(False)
        self.refresh_meetings_button.setEnabled(False)
        self.batch_processing_thread = QThread(self)
        self.batch_processing_worker = BatchProcessingWorker(jobs, mode=dialog.mode)
        self.batch_processing_worker.moveToThread(self.batch_processing_thread)
        self.batch_processing_thread.started.connect(self.batch_processing_worker.process)
        self.batch_processing_worker.status.connect(self.log)
        self.batch_processing_worker.finished.connect(self.batch_processing_thread.quit)
        self.batch_processing_worker.finished.connect(self.batch_processing_worker.deleteLater)
        self.batch_processing_thread.finished.connect(self._batch_processing_finished)
        self.batch_processing_thread.finished.connect(self.batch_processing_thread.deleteLater)
        self.batch_processing_thread.start()

    def _batch_processing_finished(self) -> None:
        self.batch_processing_worker = None
        self.batch_processing_thread = None
        if hasattr(self, "archive_status"):
            self.archive_status.setText("Batch reprocess complete")
        for button_name in (
            "reprocess_button",
            "repair_meeting_button",
            "batch_reprocess_button",
            "rebuild_index_button",
            "refresh_meetings_button",
            "export_calendar_button",
        ):
            if hasattr(self, button_name):
                getattr(self, button_name).setEnabled(True)
        self.refresh_meetings()
        self.log("Batch reprocess complete.")

    def rebuild_meeting_intelligence_index(self) -> None:
        from app.storage.meeting_index import write_meeting_index
        rebuilt = 0
        failed = 0
        for folder in self.meeting_store.list_meetings():
            try:
                load_or_build_insights(folder)
                rebuilt += 1
            except Exception as error:
                failed += 1
                self.log(f"Could not rebuild insights for {folder.name}: {error}")
        try:
            write_meeting_index(self.meeting_store)
        except Exception as error:
            failed += 1
            self.log(f"Could not rebuild meeting index: {error}")
        self.refresh_meetings()
        self.refresh_review_center()
        message = f"Rebuilt intelligence for {rebuilt} meeting(s)"
        if failed:
            message += f"; {failed} issue(s)"
        self.archive_status.setText(message)
        self.log(message)
