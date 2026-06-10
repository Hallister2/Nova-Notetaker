from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, QThread, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QCursor, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.audio.capture_service import CaptureConfig, CaptureService
from app.audio.device_manager import AudioDevice, AudioDeviceManager
from app.core.audio_profiles import find_audio_profile, save_audio_profile
from app.core.health import check_services_async
from app.core.settings import save_settings
from app.intelligence.insights import InsightItem, MeetingInsights, load_or_build_insights
from app.storage.meeting_store import MeetingMetadata, MeetingStore
from app.storage.privacy import apply_meeting_privacy, apply_retention_policy
from app.storage.text_preview import read_text_preview
from app.transcription.whisperlive_client import WhisperLiveClient
from app.ui.constants import CAPTURE_PROFILES, CLOSED_ACTION_STATUSES, DEFAULT_LOOPBACK_DEVICE, DEFAULT_MIC_DEVICE
from app.ui.live_insights import append_or_merge_live_row, clean_live_segment_text, tentative_insights_from_live_rows
from app.ui.workers import CaptureWorker, LiveTranscriptionWorker, ProcessingWorker
from app.workflows.meeting_processor import MeetingProcessor


class CaptureTabMixin:
    def _build_live_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.live_page_layout = layout
        layout.setContentsMargins(34, 28, 18, 22)
        layout.setSpacing(18)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("Live Meeting Capture")
        title.setObjectName("Title")
        self.live_title_label = title
        subtitle = QLabel("Capture, transcribe, and generate intelligence from your meetings.")
        subtitle.setObjectName("Subtitle")
        self.live_subtitle_label = subtitle
        title_block.addWidget(title)
        title_block.addWidget(subtitle)

        header.addLayout(title_block)
        layout.addLayout(header)

        main_grid = QGridLayout()
        self.live_main_grid = main_grid
        main_grid.setSpacing(18)
        center = QWidget()
        self.live_center_widget = center
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(14)
        self.meeting_setup_card = self._build_meeting_status_card()
        center_layout.addWidget(self.meeting_setup_card)
        center_layout.addWidget(self._build_transcript_card(), stretch=1)
        center_layout.addWidget(self._build_action_bar())
        main_grid.addWidget(center, 0, 0)
        self.insights_panel = self._build_insights_panel()
        main_grid.addWidget(self.insights_panel, 0, 1)
        main_grid.setColumnStretch(0, 1)
        main_grid.setColumnMinimumWidth(1, 340)
        layout.addLayout(main_grid, stretch=1)
        return page

    def _build_theme_toggle(self) -> QWidget:
        container = QFrame()
        container.setObjectName("ThemeToggle")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        for theme_name, label in (
            ("executive_dark", "Dark"),
            ("clean_light", "Light"),
        ):
            button = QPushButton(label)
            button.setObjectName("ThemeButton")
            button.setProperty("active", "false")
            button.setCursor(QCursor(Qt.PointingHandCursor))
            button.setFixedSize(58, 28)
            button.clicked.connect(lambda checked=False, selected=theme_name: self.set_theme(selected))
            layout.addWidget(button)
            self.theme_buttons[theme_name] = button
        self._sync_theme_buttons()
        return container

    def _build_meeting_status_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Panel")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        from PySide6.QtWidgets import QLineEdit
        self.meeting_title = QLineEdit()
        self.meeting_title.setPlaceholderText("Meeting title")
        self.meeting_title.setText("Teams Meeting")
        self.detect_title_button = QPushButton("Detect")
        self.detect_title_button.setToolTip("Detect title from the active window")
        self.detect_title_button.clicked.connect(self.detect_active_window_title)

        self.meeting_title.setMinimumWidth(0)
        self.meeting_title.setFixedHeight(40)
        self.profile_combo = QComboBox()
        self.profile_combo.setFixedHeight(40)
        self._populate_profile_combo()
        self.profile_combo.currentIndexChanged.connect(self._profile_selection_changed)
        self.template_combo = QComboBox()
        self.template_combo.setFixedHeight(40)
        self._populate_template_combo()
        self.template_combo.currentIndexChanged.connect(self._template_selection_changed)
        self.detect_title_button.setObjectName("SubtleActionButton")
        self.detect_title_button.setFixedHeight(40)
        self.detect_title_button.setFixedWidth(96)

        setup_stack = QVBoxLayout()
        setup_stack.setContentsMargins(0, 0, 0, 0)
        setup_stack.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)
        title_row.addWidget(self._field_block("Meeting", self.meeting_title), stretch=1)
        title_row.addWidget(self._button_block("", self.detect_title_button), stretch=0)

        detail_row = QHBoxLayout()
        detail_row.setContentsMargins(0, 0, 0, 0)
        detail_row.setSpacing(12)
        detail_row.addWidget(self._field_block("Profile", self.profile_combo), stretch=1)
        detail_row.addWidget(self._field_block("Template", self.template_combo), stretch=1)
        setup_stack.addLayout(title_row)
        setup_stack.addLayout(detail_row)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("GreenText")
        self.elapsed_label = QLabel("00:00:00")
        self.elapsed_label.setObjectName("HeroTimer")
        self.status_detail_label = self._muted_label("Waiting to start")
        self.orb_caption = self.status_detail_label
        self.workflow_step_label = QLabel("Setup")
        self.workflow_step_label.setObjectName("WorkflowStep")
        self.capture_mic_toggle = QCheckBox("Capture microphone")
        self.capture_mic_toggle.setObjectName("MicToggle")
        self.capture_mic_toggle.setChecked(bool(self.settings["audio"].get("capture_mic", True)))
        self.capture_mic_toggle.toggled.connect(self._save_capture_mic_toggle)
        self._sync_mic_toggle_label()
        self.settings_summary = self._muted_label("")
        self.settings_summary.setWordWrap(True)
        self.mic_level = QProgressBar()
        self.mic_level.setRange(0, 100)
        self.mic_level.setTextVisible(False)
        self.system_level = QProgressBar()
        self.system_level.setRange(0, 100)
        self.system_level.setTextVisible(False)

        layout.addWidget(self._section_label("Meeting setup"))
        layout.addLayout(setup_stack)
        layout.addWidget(self.settings_summary)
        return card

    def _build_transcript_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Panel")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(self._section_label("Live transcript"))
        self.live_transcript_status_label = self._muted_label("Final transcript is generated after recording.")
        top.addWidget(self.live_transcript_status_label)
        top.addStretch()
        self.speaker_filter = QComboBox()
        self.speaker_filter.addItems(["Speakers", "You", "Meeting Audio"])
        self.pause_button = QPushButton("Pause")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self.toggle_pause_recording)
        top.addWidget(self.speaker_filter)
        top.addWidget(self.pause_button)
        layout.addLayout(top)

        hud = QFrame()
        hud.setObjectName("LiveCaptureHud")
        hud_layout = QGridLayout(hud)
        hud_layout.setContentsMargins(12, 8, 12, 8)
        hud_layout.setHorizontalSpacing(12)
        hud_layout.setVerticalSpacing(4)
        self.live_elapsed_label = QLabel("00:00:00")
        self.live_elapsed_label.setObjectName("CompactTimer")
        self.live_state_label = self._muted_label("Ready")
        self.live_state_label.setObjectName("LiveStateBadge")
        self.live_mic_level = QProgressBar()
        self.live_mic_level.setRange(0, 100)
        self.live_mic_level.setTextVisible(False)
        self.live_mic_level.setMinimumWidth(150)
        self.live_system_level = QProgressBar()
        self.live_system_level.setRange(0, 100)
        self.live_system_level.setTextVisible(False)
        self.live_system_level.setMinimumWidth(150)
        self.recording_health_label = self._muted_label("Preflight not run")
        self.recording_health_label.setWordWrap(True)
        self.capture_format_label = self._muted_label("Capture format pending")
        self.capture_format_label.setWordWrap(True)
        hud_layout.addWidget(self.live_elapsed_label, 0, 0, 2, 1)
        hud_layout.addWidget(self.live_state_label, 0, 1, 2, 1, Qt.AlignLeft | Qt.AlignVCenter)
        hud_layout.addWidget(QLabel("Mic"), 0, 2)
        hud_layout.addWidget(self.live_mic_level, 0, 3)
        hud_layout.addWidget(QLabel("System"), 1, 2)
        hud_layout.addWidget(self.live_system_level, 1, 3)
        hud_layout.addWidget(self.capture_mic_toggle, 0, 4, 2, 1)
        hud_layout.addWidget(self.recording_health_label, 2, 0, 1, 5)
        hud_layout.addWidget(self.capture_format_label, 3, 0, 1, 5)
        hud_layout.setColumnMinimumWidth(3, 160)
        hud_layout.setColumnStretch(3, 1)
        layout.addWidget(hud)

        self.transcript_scroll = QScrollArea()
        self.transcript_scroll.setWidgetResizable(True)
        self.transcript_scroll.setFrameShape(QFrame.NoFrame)
        self.transcript_content = QWidget()
        self.transcript_layout = QVBoxLayout(self.transcript_content)
        self.transcript_layout.setContentsMargins(0, 0, 0, 0)
        self.transcript_layout.setSpacing(0)
        self.transcript_scroll.setWidget(self.transcript_content)
        layout.addWidget(self.transcript_scroll, stretch=1)
        self._set_transcript_rows([])
        return card

    def _build_action_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("ActionDock")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(16)
        self.mark_important_button = QPushButton("Mark Important")
        self.mark_important_button.setEnabled(False)
        self.mark_important_button.clicked.connect(self.mark_current_meeting_important)
        self.new_meeting_button = QPushButton("New Meeting")
        self.new_meeting_button.clicked.connect(self.show_meeting_setup)
        self.open_latest_button = QPushButton("Open latest meeting")
        self.open_latest_button.setEnabled(False)
        self.open_latest_button.clicked.connect(self.open_latest_meeting)
        self.recording_button = QPushButton("Start Recording")
        self.recording_button.setObjectName("PrimaryButton")
        self.recording_button.clicked.connect(self.toggle_capture)
        self.start_button = self.recording_button
        self.stop_button = self.recording_button
        self.add_note_button = QPushButton("Add Note")
        self.add_note_button.setEnabled(False)
        self.add_note_button.clicked.connect(self.add_current_meeting_note)
        layout.addWidget(self.recording_button, stretch=1)
        layout.addWidget(self.new_meeting_button)
        layout.addWidget(self.open_latest_button)
        layout.addWidget(self.mark_important_button)
        layout.addWidget(self.add_note_button)
        return bar

    def _build_insights_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setMaximumWidth(390)
        panel.setMinimumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 20, 18, 18)
        layout.setSpacing(14)
        layout.addWidget(self._section_label("Meeting insights"))
        self.live_insights_context_label = self._muted_label(
            "Live transcript is realtime. Actions, decisions, and dates fill in after notes are processed."
        )
        layout.addWidget(self.live_insights_context_label)
        metrics = QGridLayout()
        metrics.setHorizontalSpacing(8)
        metrics.setVerticalSpacing(8)
        self.live_open_actions_count = QLabel("0")
        self.live_missing_owner_count = QLabel("0")
        self.live_due_soon_count = QLabel("0")
        self.live_review_warning_count = QLabel("0")
        metrics.addWidget(self._metric_card("Open actions", self.live_open_actions_count), 0, 0)
        metrics.addWidget(self._metric_card("Missing owner", self.live_missing_owner_count), 0, 1)
        metrics.addWidget(self._metric_card("Due soon", self.live_due_soon_count), 1, 0)
        metrics.addWidget(self._metric_card("Review", self.live_review_warning_count), 1, 1)
        layout.addLayout(metrics)
        self.action_items_count = QLabel("0")
        self.decisions_count = QLabel("0")
        self.dates_count = QLabel("0")
        candidates_card = QFrame()
        candidates_card.setObjectName("RaisedPanel")
        candidates_layout = QVBoxLayout(candidates_card)
        candidates_layout.setContentsMargins(18, 16, 18, 16)
        candidates_layout.setSpacing(12)
        candidates_header = QHBoxLayout()
        candidates_header.addWidget(self._section_label("Live candidates"))
        candidates_header.addStretch()
        candidates_layout.addLayout(candidates_header)
        self.live_action_items_layout = QVBoxLayout()
        self.live_action_items_layout.setSpacing(7)
        self.live_decisions_layout = QVBoxLayout()
        self.live_decisions_layout.setSpacing(7)
        self.live_dates_layout = QVBoxLayout()
        self.live_dates_layout.setSpacing(7)
        candidates_layout.addWidget(self._candidate_group_header("Action items", self.action_items_count))
        candidates_layout.addLayout(self.live_action_items_layout)
        candidates_layout.addWidget(self._candidate_group_header("Key decisions", self.decisions_count))
        candidates_layout.addLayout(self.live_decisions_layout)
        candidates_layout.addWidget(self._candidate_group_header("Dates detected", self.dates_count))
        candidates_layout.addLayout(self.live_dates_layout)
        layout.addWidget(candidates_card, stretch=1)
        layout.addStretch()
        return panel

    def _candidate_group_header(self, text: str, count_label: QLabel) -> QWidget:
        row = QWidget()
        row.setObjectName("Transparent")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 4, 0, 0)
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        count_label.setObjectName("OrangeText")
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(count_label)
        return row

    def _metric_card(self, label_text: str, value_label: QLabel) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        value_label.setObjectName("StatValue")
        label = QLabel(label_text)
        label.setObjectName("Muted")
        layout.addWidget(value_label)
        layout.addWidget(label)
        return card

    def _insight_card(self, title: str, count_label: QLabel, items: list[str]) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("RaisedPanel")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(9)
        header = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("SectionTitle")
        count_label.setObjectName("OrangeText")
        header.addWidget(label)
        header.addStretch()
        header.addWidget(count_label)
        layout.addLayout(header)
        items_layout = QVBoxLayout()
        items_layout.setSpacing(7)
        layout.addLayout(items_layout)
        self._set_insight_items(items_layout, items)
        if not title.lower().startswith("live"):
            link = QLabel(f"View all {title.lower()}")
            link.setObjectName("OrangeText")
            layout.addWidget(link, alignment=Qt.AlignRight)
        return card, items_layout

    def _set_live_page_margins(self, left: int, top: int, right: int, bottom: int, spacing: int) -> None:
        self.live_page_layout.setContentsMargins(left, top, right, bottom)
        self.live_page_layout.setSpacing(spacing)
        self.live_main_grid.setSpacing(spacing)

    def _set_insights_visible(self, visible: bool, width: int | None = None) -> None:
        self.insights_panel.setVisible(visible)
        if width is not None:
            self.insights_panel.setFixedWidth(width)
        self.live_main_grid.setColumnMinimumWidth(1, width if visible and width else 0)

    def _set_transcript_rows(self, rows: list[tuple[str, str, str] | tuple[str, str, str, bool]]) -> None:
        while self.transcript_layout.count():
            item = self.transcript_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        empty_rows = not rows
        if empty_rows:
            rows = [("--:--:--", "Meeting Audio", "Transcript rows will appear here after capture and processing.")]

        for row_data in rows:
            timestamp, speaker, text = row_data[:3]
            is_partial = bool(row_data[3]) if len(row_data) > 3 else False
            row = QFrame()
            if empty_rows:
                row.setObjectName("TranscriptEmptyRow")
            else:
                row.setObjectName("LiveTranscriptRow" if is_partial else "TranscriptRow")
            row_layout = QGridLayout(row)
            row_layout.setContentsMargins(14, 10, 14, 10)
            row_layout.setHorizontalSpacing(14)
            row_layout.setVerticalSpacing(4)
            time_label = self._muted_label("Now" if is_partial else timestamp)
            speaker_label = QLabel(speaker)
            speaker_label.setObjectName("OrangeText" if speaker == "You" else "BlueText")
            text_label = QLabel(text)
            text_label.setWordWrap(True)
            if is_partial:
                text_label.setObjectName("LivePartialText")
            row_layout.addWidget(time_label, 0, 0, Qt.AlignTop)
            row_layout.addWidget(speaker_label, 0, 1, Qt.AlignTop)
            row_layout.addWidget(text_label, 1, 1)
            row_layout.setColumnMinimumWidth(0, 78)
            row_layout.setColumnMinimumWidth(1, 128)
            row_layout.setColumnStretch(1, 1)
            self.transcript_layout.addWidget(row)
        self.transcript_layout.addStretch()
        QTimer.singleShot(0, self._scroll_live_transcript_to_bottom)

    def _scroll_live_transcript_to_bottom(self) -> None:
        if hasattr(self, "transcript_scroll"):
            scrollbar = self.transcript_scroll.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _set_insight_items(self, layout: QVBoxLayout, items: list[str | InsightItem]) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        empty = not items
        for item_text in items[:5] or ["Listening for stable candidates..."]:
            if isinstance(item_text, InsightItem):
                layout.addWidget(self._insight_preview_widget(item_text))
            else:
                prefix = "" if empty else "- "
                label = self._muted_label(f"{prefix}{item_text}")
                label.setObjectName("InsightPreviewText")
                label.setWordWrap(True)
                layout.addWidget(label)

    def _insight_preview_widget(self, item: InsightItem) -> QWidget:
        container = QFrame()
        container.setObjectName("InsightPreview")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(5)
        title = QLabel(self._compact_insight_text(item.display_text))
        title.setObjectName("InsightPreviewText")
        title.setWordWrap(True)
        layout.addWidget(title)
        badges = QHBoxLayout()
        badges.setSpacing(5)
        for value, kind in (
            (item.owner if item.kind == "action" else "", "owner"),
            (item.date_label if item.kind in {"action", "date"} else "", "date"),
            (item.confidence, f"confidence-{item.confidence.lower()}"),
        ):
            if value:
                badges.addWidget(self._badge_label(value, kind))
        if item.kind == "date" and (item.due_date or item.normalized_date):
            cal_button = QPushButton("Calendar")
            cal_button.setObjectName("SubtleActionButton")
            cal_button.setFixedHeight(24)
            cal_button.setToolTip("Export this date as an .ics file to import into your calendar app.")
            cal_button.clicked.connect(lambda checked=False, date_item=item: self._export_single_date_ics(date_item))
            badges.addWidget(cal_button)
        badges.addStretch()
        layout.addLayout(badges)
        return container

    def _insight_item_widget(self, item: InsightItem) -> QWidget:
        container = QFrame()
        container.setObjectName("InsightItem")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(6)
        title = QLabel(item.display_text)
        title.setObjectName("InsightItemTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        badges = QHBoxLayout()
        badges.setSpacing(6)
        badge_values = []
        if item.kind == "action":
            badge_values.append((item.owner, "owner"))
            badge_values.append((item.date_label, "date"))
            badge_values.append((item.status, "state"))
        elif item.kind == "date":
            badge_values.append((item.date_label, "date"))
        badge_values.append((item.confidence, f"confidence-{item.confidence.lower()}"))
        for value, kind in badge_values:
            if not value:
                continue
            badges.addWidget(self._badge_label(value, kind))
        if item.kind == "date":
            calendar_button = QPushButton("Calendar")
            calendar_button.setObjectName("SubtleActionButton")
            calendar_button.setToolTip("Export this date as an .ics file to import into your calendar app.")
            calendar_button.clicked.connect(lambda checked=False, date_item=item: self._export_single_date_ics(date_item))
            badges.addWidget(calendar_button)
        badges.addStretch()
        layout.addLayout(badges)
        return container

    @staticmethod
    def _badge_label(text: str, kind: str) -> QLabel:
        display_text = text if len(text) <= 22 else f"{text[:19]}..."
        label = QLabel(display_text)
        label.setObjectName("Badge")
        label.setProperty("kind", kind)
        label.setToolTip(text)
        return label

    def _update_insight_group(self, count_label: QLabel, items_layout: QVBoxLayout, items: list[str | InsightItem]) -> None:
        count_label.setText(str(len(items)))
        self._set_insight_items(items_layout, items)

    def _update_live_insights_from_folder(self, folder: Path) -> None:
        insights = load_or_build_insights(folder)
        if hasattr(self, "live_insights_context_label"):
            self.live_insights_context_label.setText("Latest processed meeting insights.")
        self._update_operational_metrics(insights)
        self._update_insight_group(self.action_items_count, self.live_action_items_layout, insights.actions)
        self._update_insight_group(self.decisions_count, self.live_decisions_layout, insights.decisions)
        self._update_insight_group(self.dates_count, self.live_dates_layout, insights.dates)

    def _update_operational_metrics(self, insights: MeetingInsights | None = None) -> None:
        insights = insights or MeetingInsights()
        open_actions = [item for item in insights.actions if (item.status or "open").lower() not in CLOSED_ACTION_STATUSES]
        missing_owner = [
            item
            for item in open_actions
            if not item.owner or item.owner.strip().lower() in {"unknown", "unassigned", "none"}
        ]
        due_soon = [item for item in open_actions if (item.normalized_date or item.due_date) and (item.due_date or item.normalized_date).strip().lower() not in {"unknown", "none"}]
        if hasattr(self, "live_open_actions_count"):
            self.live_open_actions_count.setText(str(len(open_actions)))
            self.live_missing_owner_count.setText(str(len(missing_owner)))
            self.live_due_soon_count.setText(str(len(due_soon)))
            self.live_review_warning_count.setText(str(len(insights.quality_warnings) + len(insights.warnings)))

    def _update_selected_meeting_details(self, folder: Path | None) -> None:
        if folder is None:
            self.selected_meeting_summary.setText("Select a meeting to review extracted details.")
            self._update_insight_group(self.selected_action_count, self.selected_action_items_layout, [])
            self._update_insight_group(self.selected_decision_count, self.selected_decisions_layout, [])
            self._update_insight_group(self.selected_date_count, self.selected_dates_layout, [])
            return
        try:
            metadata = self.meeting_store.read_metadata(folder)
            self.selected_meeting_summary.setText(f"{metadata.title}\n{metadata.started_at}\nStatus: {metadata.status}")
        except Exception:
            self.selected_meeting_summary.setText(folder.name)
        insights = load_or_build_insights(folder)
        self._update_insight_group(self.selected_action_count, self.selected_action_items_layout, insights.actions)
        self._update_insight_group(self.selected_decision_count, self.selected_decisions_layout, insights.decisions)
        self._update_insight_group(self.selected_date_count, self.selected_dates_layout, insights.dates)

    @classmethod
    def _parse_notes_insights(cls, notes_path: Path) -> dict[str, list[str]]:
        insights = {"actions": [], "decisions": [], "dates": []}
        if not notes_path.exists():
            return insights
        section = ""
        for raw_line in notes_path.read_text(encoding="utf-8").splitlines():
            line = cls._plain_note_text(raw_line).strip()
            lower = line.lower()
            if lower.startswith("## "):
                if "action" in lower:
                    section = "actions"
                elif "decision" in lower:
                    section = "decisions"
                elif "date" in lower:
                    section = "dates"
                else:
                    section = ""
                continue
            if not section or not line.startswith("-"):
                continue
            item = line.lstrip("- ").strip()
            if not item or item.startswith("_"):
                continue
            insights[section].append(cls._compact_insight_text(item))
        return insights

    @staticmethod
    def _plain_note_text(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        return text.replace("&nbsp;", " ").replace("&amp;", "&")

    @staticmethod
    def _compact_insight_text(text: str) -> str:
        parts = [part.strip() for part in text.split(";") if part.strip()]
        pairs = {}
        for part in parts:
            if ":" in part:
                key, value = part.split(":", 1)
                pairs[key.strip().lower()] = value.strip()
        if "owner" in pairs and "task" in pairs:
            due = f" | {pairs['due']}" if pairs.get("due") and pairs.get("due", "").lower() != "unknown" else ""
            return f"{pairs['owner']}: {pairs['task']}{due}"
        if "date" in pairs and "context" in pairs:
            return f"{pairs['date']}: {pairs['context']}"
        if len(parts) >= 2:
            return f"{parts[0]}: {parts[1]}"
        return text[:130]

    def _refresh_live_transcript_from_file(self) -> None:
        if not self.meeting_folder:
            return
        transcript_path = self.meeting_folder / "transcript.md"
        if not transcript_path.exists():
            return
        text = read_text_preview(transcript_path)
        rows: list[tuple[str, str, str]] = []
        speaker = "Meeting Audio"
        for line in text.splitlines():
            clean = line.strip()
            if clean == "## You":
                speaker = "You"
                continue
            if clean == "## Meeting":
                speaker = "Meeting Audio"
                continue
            if not clean or clean.startswith("#") or clean.startswith("_") or clean.startswith("-"):
                continue
            rows.append(("--:--:--", speaker, clean))
            if len(rows) >= 12:
                break
        self._set_transcript_rows(rows)

    def _start_live_transcription(self) -> None:
        if self.live_transcription_thread is not None:
            return
        transcription_settings = self.settings.get("transcription", {})
        live_enabled = bool(transcription_settings.get("enabled"))
        live_url = str(transcription_settings.get("whisperlive_url", "")).strip()
        if not live_enabled or not live_url:
            if hasattr(self, "live_transcript_status_label"):
                self.live_transcript_status_label.setText("Live transcript disabled")
            self.log("Live transcript disabled. Final transcript will be generated after recording.")
            return
        self.live_transcript_rows = []
        self.full_live_transcript_rows = []
        self.live_transcription_thread = QThread(self)
        self.live_transcription_worker = LiveTranscriptionWorker(self.settings)
        self.live_transcription_worker.moveToThread(self.live_transcription_thread)
        self.live_transcription_thread.started.connect(self.live_transcription_worker.run)
        self.live_transcription_worker.status.connect(self._live_transcription_status)
        self.live_transcription_worker.segment.connect(self._append_live_transcript_segment)
        self.live_transcription_worker.finished.connect(self.live_transcription_thread.quit)
        self.live_transcription_worker.finished.connect(self.live_transcription_worker.deleteLater)
        self.live_transcription_thread.finished.connect(self._live_transcription_finished)
        self.live_transcription_thread.finished.connect(self.live_transcription_thread.deleteLater)
        if self.worker is not None:
            self.worker.audio_chunk.connect(self.live_transcription_worker.enqueue_audio)
        self.live_transcription_thread.start()

    def _stop_live_transcription(self) -> None:
        if self.live_transcription_worker is not None:
            self.live_transcription_worker.stop()

    def _live_transcription_status(self, message: str) -> None:
        if hasattr(self, "live_transcript_status_label"):
            self.live_transcript_status_label.setText(message)
        self.log(message)

    @Slot(str, str, bool)
    def _append_live_transcript_segment(self, speaker: str, text: str, final: bool) -> None:
        text = clean_live_segment_text(text)
        if not text:
            return
        timestamp = self._recording_offset_label()
        is_partial = not final
        append_or_merge_live_row(self.full_live_transcript_rows, timestamp, speaker, text, is_partial)
        append_or_merge_live_row(self.live_transcript_rows, timestamp, speaker, text, is_partial)
        self.live_transcript_rows = self.live_transcript_rows[-18:]
        self._set_transcript_rows(self.live_transcript_rows)
        self._update_tentative_live_insights()

    def _update_tentative_live_insights(self) -> None:
        if self.timer_phase != "recording":
            return
        insights = tentative_insights_from_live_rows(self.live_transcript_rows)
        self.live_tentative_insights = insights
        if hasattr(self, "live_insights_context_label"):
            self.live_insights_context_label.setText("Tentative live candidates. Confirmed after notes are processed.")
        self._update_operational_metrics(insights)
        self._update_insight_group(self.action_items_count, self.live_action_items_layout, insights.actions)
        self._update_insight_group(self.decisions_count, self.live_decisions_layout, insights.decisions)
        self._update_insight_group(self.dates_count, self.live_dates_layout, insights.dates)

    def _live_transcription_finished(self) -> None:
        self.live_transcription_worker = None
        self.live_transcription_thread = None
        if hasattr(self, "live_transcript_status_label") and self.timer_phase != "recording":
            self.live_transcript_status_label.setText("Final transcript will be refreshed after processing.")
        if self.pending_processing_job:
            folder, metadata, mode = self.pending_processing_job
            self.pending_processing_job = None
            self.log("Live transcript stream closed. Starting post-processing.")
            self._write_live_transcript_artifact(folder, metadata)
            self._start_processing(folder, metadata, mode=mode)

    def _write_live_transcript_artifact(self, folder: Path | None, metadata: MeetingMetadata | None) -> None:
        if folder is None or metadata is None:
            return
        rows = getattr(self, "full_live_transcript_rows", [])
        final_rows = [row for row in rows if len(row) >= 4 and not row[3] and str(row[2]).strip()]
        if not final_rows:
            return
        lines = ["# Live Transcript", "", "## Meeting", ""]
        for _timestamp, _speaker, text, _is_partial in final_rows:
            clean = str(text).strip()
            if clean:
                lines.append(clean)
        path = folder / "live_transcript.md"
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        metadata.processing = {
            **(metadata.processing if isinstance(metadata.processing, dict) else {}),
            "live_transcript_path": str(path),
        }
        self.meeting_store.write_metadata(folder, metadata)

    def _recording_offset_label(self) -> str:
        if not self.recording_started_at:
            return "--:--:--"
        seconds = max(0, int((datetime.now() - self.recording_started_at).total_seconds()))
        return self._format_duration(seconds)

    def _update_elapsed_timer(self) -> None:
        if self.timer_phase == "recording":
            started_at = self.recording_started_at
        elif self.timer_phase == "processing":
            started_at = self.processing_started_at
        else:
            started_at = None

        if not started_at:
            self._set_elapsed_text("00:00:00")
            return
        elapsed = datetime.now() - started_at
        total_seconds = max(0, int(elapsed.total_seconds()))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        self._set_elapsed_text(f"{hours:02}:{minutes:02}:{seconds:02}")

    def _set_elapsed_text(self, text: str) -> None:
        if hasattr(self, "elapsed_label"):
            self.elapsed_label.setText(text)
        if hasattr(self, "live_elapsed_label"):
            self.live_elapsed_label.setText(text)
        if hasattr(self, "sidebar_status_detail_label") and self.timer_phase == "recording":
            self.sidebar_status_detail_label.setText(text)

    def _set_live_capture_state(self, text: str) -> None:
        if hasattr(self, "live_state_label"):
            self.live_state_label.setText(text)

    def _run_health_checks(self) -> None:
        check_services_async(self.settings, self._service_status_changed.emit)

    @Slot(str, str)
    def _on_service_status_changed(self, service: str, status: str) -> None:
        self._service_statuses[service] = status
        self._refresh_service_status_label()

    def _refresh_service_status_label(self) -> None:
        if not hasattr(self, "sidebar_services_label"):
            return
        provider = self.settings.get("ai", {}).get("provider", "ollama")
        provider_display = {"ollama": "Ollama", "openai": "OpenAI", "claude": "Claude"}.get(provider, provider)
        parts = []
        for name in (provider_display, "WhisperLive"):
            state = self._service_statuses.get(name, "unknown")
            if state == "ok":
                indicator = "✓"
            elif state == "disabled":
                indicator = "—"
            elif state == "unreachable":
                indicator = "✗"
            else:
                indicator = "?"
            parts.append(f"{name} {indicator}")
        self.sidebar_services_label.setText("  ·  ".join(parts))

    def _set_sidebar_status(self, state: str, detail: str, processing: bool = False) -> None:
        if hasattr(self, "sidebar_ready_label"):
            self.sidebar_ready_label.setText(state)
            if state.lower() == "recording":
                self.sidebar_ready_label.setObjectName("RedText")
            elif state.lower() == "processing":
                self.sidebar_ready_label.setObjectName("BlueText")
            elif state.lower() == "ready":
                self.sidebar_ready_label.setObjectName("GreenText")
            else:
                self.sidebar_ready_label.setObjectName("OrangeText")
            self._refresh_widget_style(self.sidebar_ready_label)
        if hasattr(self, "sidebar_status_detail_label"):
            self.sidebar_status_detail_label.setText(detail)
        if hasattr(self, "sidebar_processing_progress"):
            self.sidebar_processing_progress.setVisible(processing)

    def refresh_devices(self) -> None:
        self.microphones = self.device_manager.list_microphones()
        self.loopbacks = self.device_manager.list_wasapi_loopbacks()

        self._populate_settings_device_controls()
        self.update_settings_summary()
        self.log(f"Detected {len(self.microphones)} microphone device(s) and {len(self.loopbacks)} loopback device(s).")

        if not self.loopbacks:
            self.log("No WASAPI loopback devices detected. On Windows, install/check pyaudiowpatch and confirm output devices are enabled.")

    def toggle_capture(self) -> None:
        if self.worker is not None:
            self.stop_capture()
            return
        if self.processing_thread is not None:
            return
        self.start_capture()

    def start_capture(self) -> None:
        capture_mic = self.capture_mic_toggle.isChecked()
        self.settings["audio"]["capture_mic"] = capture_mic
        save_settings(self.settings)

        meeting_profile = self._selected_meeting_profile()
        note_template = self._selected_note_template()
        mic_device = self._resolve_microphone_device()
        loop_device = self._resolve_loopback_device()

        if capture_mic and mic_device is None:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Nova Notetaker", "Select a microphone in Settings before starting capture.")
            return

        mic_sample_rate = (mic_device.sample_rate if mic_device else None) or 48000
        mic_channels = self._capture_channels(mic_device, default=1, max_channels=2)
        loopback_sample_rate, loopback_channels = self._loopback_capture_format(loop_device)
        if not loop_device:
            QMessageBox.warning(self, "Nova Notetaker", "Select a system audio device in Settings before starting capture.")
            return
        self._set_recording_health("Starting capture. Mic/system levels will update once streams are online.")
        self._save_audio_selections(mic_device, loop_device)

        title = self.meeting_title.text().strip() or "Untitled Meeting"
        self.meeting_folder = self.meeting_store.create_meeting_folder(title)
        started_at = datetime.now().isoformat(timespec="seconds")
        self.metadata = MeetingMetadata(
            title=title,
            started_at=started_at,
            mic_device_name=mic_device.name if mic_device else None,
            system_device_name=loop_device.name if loop_device else None,
            capture_mic=capture_mic,
            capture_profile=str(self.settings["audio"].get("capture_profile", "external_mic_speakers")),
            meeting_profile=self._profile_metadata(meeting_profile),
            note_template=self._template_metadata(note_template),
            status="recording",
        )
        self.meeting_store.write_metadata(self.meeting_folder, self.metadata)

        config = CaptureConfig(
            meeting_folder=self.meeting_folder,
            mic_device_index=mic_device.index if mic_device else None,
            loopback_device_index=loop_device.index if loop_device else None,
            capture_mic=capture_mic,
            mic_sample_rate=mic_sample_rate,
            mic_channels=mic_channels,
            loopback_sample_rate=loopback_sample_rate,
            loopback_channels=loopback_channels,
        )

        self.current_capture_config = config
        self.current_loopback_device = loop_device
        self.worker_thread = QThread(self)
        self.worker = CaptureWorker(config)
        self.worker.moveToThread(self.worker_thread)

        self.request_worker_start.connect(self.worker.start)
        self.request_worker_stop.connect(self.worker.stop)
        self.worker.status.connect(self._capture_status)
        self.worker.stopped.connect(self.worker_thread.quit)
        self.worker.stopped.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self._capture_finished)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

        self.stop_requested = False
        self.recording_button.setEnabled(True)
        self.recording_button.setText("Stop Recording")
        self.recording_button.setObjectName("DangerButton")
        self._refresh_widget_style(self.recording_button)
        self.settings_button.setEnabled(False)
        self.new_meeting_button.setEnabled(False)
        self.capture_mic_toggle.setEnabled(False)
        self.mark_important_button.setEnabled(True)
        self.add_note_button.setEnabled(True)
        self.pause_button.setEnabled(True)
        self.pause_button.setText("Pause")
        self.reprocess_button.setEnabled(False)
        if hasattr(self, "batch_reprocess_button"):
            self.batch_reprocess_button.setEnabled(False)
        self.recording_started_at = datetime.now()
        self.processing_started_at = None
        self.timer_phase = "recording"
        self.elapsed_timer.start(1000)
        self._update_elapsed_timer()
        self.orb.set_state("recording")
        self._set_sidebar_status("Recording", "00:00:00")
        self.status_label.setObjectName("RedText")
        self.status_label.setText("Recording")
        self._set_live_capture_state("Recording")
        self._refresh_widget_style(self.status_label)
        self.orb_caption.setText("Recording time")
        self.workflow_step_label.setText("Recording")
        self.hide_meeting_setup()
        self.footer_save_label.setText(f"Saving to: {self.meeting_folder.name}")
        self.footer_save_label.setToolTip(str(self.meeting_folder))
        self.live_transcript_rows = []
        self.full_live_transcript_rows = []
        self.system_audio_detected = False
        self.system_audio_warning_shown = False
        self.live_tentative_insights = MeetingInsights()
        self._update_operational_metrics()
        self.action_items_count.setText("0")
        self.decisions_count.setText("0")
        self.dates_count.setText("0")
        QTimer.singleShot(150, self._reset_recording_panels_after_start)
        self.log(f"Meeting folder: {self.meeting_folder}")
        capture_format = (
            f"mic {'muted' if not config.capture_mic else f'{config.mic_sample_rate} Hz / {config.mic_channels} ch'}, "
            f"system {config.loopback_sample_rate} Hz / {config.loopback_channels} ch"
        )
        self._set_capture_format(capture_format)
        self.log(f"Capture format: {capture_format}")
        self.log(f"Capture profile: {self._profile_label(self.settings['audio'].get('capture_profile', ''))}")
        self.request_worker_start.emit()

    def _reset_recording_panels_after_start(self) -> None:
        if self.timer_phase != "recording":
            return
        self._set_insight_items(self.live_action_items_layout, ["Waiting for notes generation"])
        self._set_insight_items(self.live_decisions_layout, ["Waiting for notes generation"])
        self._set_insight_items(self.live_dates_layout, ["Waiting for notes generation"])
        if hasattr(self, "live_insights_context_label"):
            self.live_insights_context_label.setText(
                "Live transcript is realtime. Actions, decisions, and dates fill in after notes are processed."
            )
        self._set_transcript_rows([("--:--:--", "Meeting Audio", "Listening for meeting audio...", True)])
        self._start_live_transcription()

    @Slot(str)
    def _capture_status(self, message: str) -> None:
        self.log(message)
        lower = message.lower()
        if "microphone capture online" in lower:
            self._set_recording_health("Mic online. Waiting for system audio.")
        elif "system loopback capture online" in lower:
            self._set_recording_health("Mic/system capture online.")
            self._remember_current_loopback_profile()
        elif "system loopback capture failed" in lower:
            self._set_recording_health(f"System audio failed: {message}")
            if hasattr(self, "live_transcript_status_label"):
                self.live_transcript_status_label.setText("System audio capture failed; check output device.")
        elif "system loopback capture saved" in lower:
            self._set_recording_health(message)
        elif "microphone capture failed" in lower:
            self._set_recording_health(f"Mic failed: {message}")

    def _set_recording_health(self, text: str) -> None:
        if hasattr(self, "recording_health_label"):
            self.recording_health_label.setText(text)

    def _set_capture_format(self, text: str) -> None:
        if hasattr(self, "capture_format_label"):
            self.capture_format_label.setText(f"Format: {text}")

    def _loopback_capture_format(self, device: AudioDevice | None) -> tuple[int, int]:
        if device is None:
            return 48000, 2
        profile = find_audio_profile(device.name)
        if profile:
            self.log(f"Using saved audio profile for {device.label}: {profile.detail}")
            return profile.sample_rate, profile.channels
        sample_rate = (device.sample_rate if device else None) or 48000
        channels = self._capture_channels(device, default=2, max_channels=None)
        return int(sample_rate), int(channels)

    def _remember_current_loopback_profile(self) -> None:
        device = getattr(self, "current_loopback_device", None)
        config = getattr(self, "current_capture_config", None)
        if device is None or config is None:
            return
        try:
            profile = save_audio_profile(device.name, config.loopback_sample_rate, config.loopback_channels)
            self.log(f"Saved audio profile for {device.label}: {profile.detail}")
        except Exception as error:
            self.log(f"Could not save audio profile: {error}")
    def _resolve_microphone_device(self) -> AudioDevice | None:
        setting = self.settings["audio"].get("mic_device_name", "") or DEFAULT_MIC_DEVICE
        if setting == DEFAULT_MIC_DEVICE:
            default_mic = self.device_manager.default_microphone()
            if default_mic:
                default_mic = self._prefer_visible_microphone(default_mic)
            if default_mic:
                self.log(f"Using Windows default microphone: {default_mic.label}")
                return default_mic
            self.log("Could not resolve Windows default microphone; using first available microphone.")
            return self.microphones[0] if self.microphones else None

        selected = self._device_by_name(self.microphones, setting)
        default_mic = self.device_manager.default_microphone()
        if selected and default_mic and selected.name != default_mic.name:
            self.log(
                "Microphone device is not the current Windows default input. "
                f"Selected: {selected.label}; default: {default_mic.label}"
            )
        return selected

    def _prefer_visible_microphone(self, default_mic: AudioDevice) -> AudioDevice:
        default_key = self.device_manager._physical_device_key(default_mic.name)
        for device in self.microphones:
            visible_key = self.device_manager._physical_device_key(device.name)
            if default_key and (default_key in visible_key or visible_key in default_key):
                return device
        return default_mic

    def _resolve_loopback_device(self) -> AudioDevice | None:
        setting = self.settings["audio"].get("system_loopback_device_name", "") or DEFAULT_LOOPBACK_DEVICE
        if setting == DEFAULT_LOOPBACK_DEVICE:
            default_loopback = self.device_manager.default_wasapi_loopback()
            if default_loopback:
                self.log(f"Using Windows default output for system audio: {default_loopback.label}")
                return default_loopback
            self.log("Could not resolve Windows default output loopback; using first available loopback device.")
            return self.loopbacks[0] if self.loopbacks else None

        selected = self._device_by_name(self.loopbacks, setting)
        default_loopback = self.device_manager.default_wasapi_loopback()
        if selected and default_loopback and selected.name != default_loopback.name:
            self.log(
                "System audio device is not the current Windows default output. "
                f"Selected: {selected.label}; default: {default_loopback.label}"
            )
        return selected

    def toggle_pause_recording(self) -> None:
        if not self.worker:
            return
        if self.worker.is_paused:
            self.worker.resume()
            self.pause_button.setText("Pause")
            self._set_live_capture_state("Recording")
            self.orb.set_state("recording")
            self.log("Recording resumed.")
        else:
            self.worker.pause()
            self.pause_button.setText("Resume")
            self._set_live_capture_state("Paused")
            self.orb.set_state("idle")
            self.log("Recording paused.")

    def stop_capture(self) -> None:
        if not self.worker:
            return
        if self.stop_requested:
            return
        if self.worker.is_paused:
            self.worker.resume()
        self.stop_requested = True
        self.recording_button.setEnabled(False)
        self.recording_button.setText("Stopping...")
        self.status_label.setText("Stopping")
        self._set_live_capture_state("Stopping")
        self._set_sidebar_status("Finalizing", "Closing audio streams")
        self.orb_caption.setText("Finalizing capture")
        self.workflow_step_label.setText("Finalizing")
        self._stop_live_transcription()
        self.log("Stop requested. Waiting for audio streams to close.")
        self.worker.request_stop()
        self.request_worker_stop.emit()

    def _capture_finished(self) -> None:
        if self.metadata and self.meeting_folder:
            self.metadata.ended_at = datetime.now().isoformat(timespec="seconds")
            self.metadata.status = "processing"
            self.meeting_store.write_metadata(self.meeting_folder, self.metadata)
            self.log("Capture saved. Starting post-processing.")

        self.worker = None
        self.worker_thread = None
        self.stop_requested = False
        if self.recording_started_at:
            recording_seconds = max(0, int((datetime.now() - self.recording_started_at).total_seconds()))
            hours, remainder = divmod(recording_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.log(f"Recording duration: {hours:02}:{minutes:02}:{seconds:02}")
        self.recording_button.setEnabled(False)
        self.recording_button.setText("Processing...")
        self.new_meeting_button.setEnabled(False)
        self.mark_important_button.setEnabled(False)
        self.add_note_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("Pause")
        self.orb.set_state("processing")
        self._set_sidebar_status("Processing", "Preparing transcript", processing=True)
        self.status_label.setText("Processing")
        self._set_live_capture_state("Processing")
        self.orb_caption.setText("Processing time")
        self.workflow_step_label.setText("Processing")
        self.processing_started_at = datetime.now()
        self.timer_phase = "processing"
        self._set_elapsed_text("00:00:00")
        self.elapsed_timer.start(1000)
        self._update_elapsed_timer()

        if self.metadata and self.meeting_folder:
            if self.live_transcription_thread is not None:
                self.pending_processing_job = (self.meeting_folder, self.metadata, "full")
                self.log("Waiting for live transcript stream to close before post-processing.")
                if hasattr(self, "live_transcript_status_label"):
                    self.live_transcript_status_label.setText("Closing live transcript before final processing.")
            else:
                self._write_live_transcript_artifact(self.meeting_folder, self.metadata)
                self._start_processing(self.meeting_folder, self.metadata, mode="full")
        else:
            self._processing_finished()

    def _save_audio_selections(self, mic_device: AudioDevice | None, loop_device: AudioDevice | None) -> None:
        if mic_device and self.settings["audio"].get("mic_device_name") != DEFAULT_MIC_DEVICE:
            self.settings["audio"]["mic_device_name"] = mic_device.name
        if self.settings["audio"].get("system_loopback_device_name") != DEFAULT_LOOPBACK_DEVICE:
            self.settings["audio"]["system_loopback_device_name"] = loop_device.name if loop_device else ""
        save_settings(self.settings)

    def _save_capture_mic_toggle(self, enabled: bool) -> None:
        self.settings["audio"]["capture_mic"] = enabled
        save_settings(self.settings)
        self._sync_mic_toggle_label()
        self.update_settings_summary()
        self.mic_level.setValue(0 if not enabled else self.mic_level.value())
        self.log(f"Microphone capture {'enabled' if enabled else 'muted'}.")

    def _sync_mic_toggle_label(self) -> None:
        if hasattr(self, "capture_mic_toggle"):
            enabled = self.capture_mic_toggle.isChecked()
            self.capture_mic_toggle.setText("Mic ON" if enabled else "Mic MUTED")
            self.capture_mic_toggle.setProperty("muted", "false" if enabled else "true")
            self._refresh_widget_style(self.capture_mic_toggle)

    @staticmethod
    def _capture_channels(device: AudioDevice | None, default: int, max_channels: int | None = 2) -> int:
        if device is None or device.channels <= 0:
            return default
        if max_channels is None:
            return device.channels
        return min(device.channels, max_channels)

    def _start_processing(self, folder: Path, metadata: MeetingMetadata, mode: str = "full") -> None:
        if self.processing_thread is not None and self.processing_thread.isRunning():
            self._processing_queue.append((folder, metadata, mode))
            self.log(f"Processing queued: {metadata.title or folder.name} ({len(self._processing_queue)} pending)")
            return
        self._launch_processing_job(folder, metadata, mode)

    def _launch_processing_job(self, folder: Path, metadata: MeetingMetadata, mode: str) -> None:
        self.processing_mode = mode
        if self.timer_phase != "processing":
            self.processing_started_at = datetime.now()
            self.timer_phase = "processing"
            self._set_elapsed_text("00:00:00")
            self._set_live_capture_state("Processing")
            self.elapsed_timer.start(1000)
            self._update_elapsed_timer()
        self.processing_thread = QThread(self)
        self.processing_worker = ProcessingWorker(folder, metadata, mode=mode)
        self.processing_worker.moveToThread(self.processing_thread)
        self.processing_thread.started.connect(self.processing_worker.process)
        self.processing_worker.status.connect(self._processing_status)
        self.processing_worker.finished.connect(self.processing_thread.quit)
        self.processing_worker.finished.connect(self.processing_worker.deleteLater)
        self.processing_thread.finished.connect(self._processing_finished)
        self.processing_thread.finished.connect(self.processing_thread.deleteLater)
        self.processing_thread.start()

    def _processing_status(self, message: str) -> None:
        self.log(message)
        if hasattr(self, "archive_status"):
            self.archive_status.setText(message)
        if hasattr(self, "status_detail_label") and self.timer_phase == "processing":
            self.status_detail_label.setText(message)
        if hasattr(self, "sidebar_status_detail_label") and self.timer_phase == "processing":
            self.sidebar_status_detail_label.setText(message)
        if hasattr(self, "workflow_step_label") and self.timer_phase == "processing":
            lowered = message.lower()
            if "chunk" in lowered:
                self.workflow_step_label.setText("Transcribing")
            elif "notes" in lowered or "ollama" in lowered:
                self.workflow_step_label.setText("Notes")
            elif "insights" in lowered:
                self.workflow_step_label.setText("Insights")

    def _processing_finished(self) -> None:
        processing_seconds = 0
        if self.processing_started_at:
            processing_seconds = max(0, int((datetime.now() - self.processing_started_at).total_seconds()))
        self.processing_worker = None
        self.processing_thread = None
        self.recording_button.setEnabled(True)
        self.recording_button.setText("Start Recording")
        self.recording_button.setObjectName("PrimaryButton")
        self._refresh_widget_style(self.recording_button)
        self.settings_button.setEnabled(True)
        self.new_meeting_button.setEnabled(True)
        self.capture_mic_toggle.setEnabled(True)
        self.mark_important_button.setEnabled(False)
        self.add_note_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("Pause")
        self.elapsed_timer.stop()
        self.timer_phase = "idle"
        self._set_elapsed_text("00:00:00")
        if hasattr(self, "reprocess_button"):
            self.reprocess_button.setEnabled(True)
        if hasattr(self, "repair_meeting_button"):
            self.repair_meeting_button.setEnabled(True)
        if hasattr(self, "batch_reprocess_button"):
            self.batch_reprocess_button.setEnabled(True)
        if hasattr(self, "rebuild_index_button"):
            self.rebuild_index_button.setEnabled(True)
        if hasattr(self, "refresh_meetings_button"):
            self.refresh_meetings_button.setEnabled(True)
        if hasattr(self, "open_folder_button"):
            self.open_folder_button.setEnabled(True)
        if hasattr(self, "export_html_button"):
            self.export_html_button.setEnabled(True)
        if hasattr(self, "export_calendar_button"):
            self.export_calendar_button.setEnabled(True)
        self.orb.set_state("idle")
        self._set_sidebar_status("Ready", "All systems operational")
        self.status_label.setObjectName("GreenText")
        self.status_label.setText("Ready")
        self._set_live_capture_state("Ready")
        self.workflow_step_label.setText("Review")
        self._refresh_widget_style(self.status_label)
        if processing_seconds:
            hours, remainder = divmod(processing_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.orb_caption.setText(f"Processing completed in {hours:02}:{minutes:02}:{seconds:02}")
        else:
            self.orb_caption.setText("Waiting to start")
        if self.meeting_folder:
            privacy_result = apply_meeting_privacy(self.meeting_folder, self.settings)
            retention_result = apply_retention_policy(self.meeting_store, self.settings)
            for warning in (*privacy_result.warnings, *retention_result.warnings):
                self.log(f"Privacy cleanup warning: {warning}")
            if privacy_result.raw_audio_deleted or privacy_result.files_removed or retention_result.meetings_removed:
                self.log(
                    "Privacy cleanup complete: "
                    f"{privacy_result.raw_audio_deleted} audio file(s), "
                    f"{privacy_result.files_removed} archive file(s), "
                    f"{retention_result.meetings_removed} expired meeting(s)."
                )
            self.log(f"Processing complete. Notes: {self.meeting_folder / 'notes.md'}")
            self._refresh_live_transcript_from_file()
            self._update_live_insights_from_folder(self.meeting_folder)
        if hasattr(self, "archive_status"):
            self.archive_status.setText("Processing complete")
        self.refresh_meetings()

        if self._processing_queue:
            next_folder, next_metadata, next_mode = self._processing_queue.pop(0)
            self.log(f"Starting queued processing job: {next_metadata.title or next_folder.name} ({len(self._processing_queue)} remaining)")
            self._launch_processing_job(next_folder, next_metadata, next_mode)

    def show_meeting_setup(self) -> None:
        if hasattr(self, "meeting_setup_card"):
            self.meeting_setup_card.setVisible(True)
        if hasattr(self, "meeting_title"):
            self.meeting_title.setFocus()
            self.meeting_title.selectAll()
        if hasattr(self, "workflow_step_label"):
            self.workflow_step_label.setText("Setup")
        if hasattr(self, "live_transcript_status_label") and self.worker is None:
            self.live_transcript_status_label.setText("Ready for a new meeting.")

    def hide_meeting_setup(self) -> None:
        if hasattr(self, "meeting_setup_card"):
            self.meeting_setup_card.setVisible(False)

    def mark_current_meeting_important(self) -> None:
        self._append_current_marker("important", "Marked important")

    def add_current_meeting_note(self) -> None:
        text, accepted = QInputDialog.getText(self, "Add Meeting Note", "Note")
        if not accepted or not text.strip():
            return
        self._append_current_marker("note", text.strip())

    def _append_current_marker(self, marker_type: str, text: str) -> None:
        if not self.meeting_folder or not self.recording_started_at:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Nova Notetaker", "Start a recording before adding meeting markers.")
            return
        seconds = max(0, int((datetime.now() - self.recording_started_at).total_seconds()))
        marker = {
            "type": marker_type,
            "text": text,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "offset_seconds": seconds,
            "offset_label": self._format_duration(seconds),
        }
        self.meeting_store.append_marker(self.meeting_folder, marker)
        self.refresh_review_center()
        self.log(f"Added meeting marker at {marker['offset_label']}: {text}")

    def _export_single_date_ics(self, item: InsightItem) -> None:
        import os
        import tempfile
        from app.ui.review_helpers import ics_escape
        now_stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        due_date = item.date_label or item.text or ""
        context = item.context or item.text or due_date
        dtstart = ""
        import re as _re
        if _re.match(r"^\d{4}-\d{2}-\d{2}$", due_date.strip()):
            dtstart = f"DTSTART;VALUE=DATE:{due_date.replace('-', '')}"
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Nova Notetaker//Meeting Intelligence//EN",
            "CALSCALE:GREGORIAN",
            "BEGIN:VEVENT",
            f"UID:nova-{now_stamp}-single@nova-notetaker",
            f"DTSTAMP:{now_stamp}",
            f"SUMMARY:{ics_escape(context or due_date)}",
            f"DESCRIPTION:{ics_escape('Date: ' + due_date + '\\nContext: ' + context + '\\nConfidence: ' + (item.confidence or 'Unknown'))}",
        ]
        if dtstart:
            lines.append(dtstart)
        lines += ["END:VEVENT", "END:VCALENDAR"]
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".ics", delete=False, encoding="utf-8", prefix="nova_date_") as fh:
                fh.write("\r\n".join(lines) + "\r\n")
                tmp_path = fh.name
            os.startfile(tmp_path)
            self.log(f"Exported date to calendar: {due_date} – {context}")
        except Exception as error:
            self.log(f"Calendar export failed: {error}")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Nova Notetaker", f"Could not open calendar file:\n{error}")

    def detect_active_window_title(self) -> None:
        title = self._active_window_title()
        if not title:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Nova Notetaker", "Could not read the active window title.")
            return
        cleaned = self._clean_window_title(title)
        self.meeting_title.setText(cleaned)
        self.log(f"Detected meeting title: {cleaned}")

    @staticmethod
    def _active_window_title() -> str:
        if sys.platform != "win32":
            return ""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            return buffer.value
        except Exception:
            return ""

    @staticmethod
    def _clean_window_title(title: str) -> str:
        # Microsoft Teams
        title = title.replace(" | Microsoft Teams", "")
        title = title.replace(" - Microsoft Teams", "")
        title = title.replace("Microsoft Teams", "")
        # Zoom
        title = re.sub(r"\s*[-–]\s*Zoom$", "", title)
        title = re.sub(r"^Zoom\s*[-–]\s*", "", title)
        title = re.sub(r"\s*\(\d+\s*participants?\)", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s*Meeting ID:\s*\d[\d\s-]*", "", title, flags=re.IGNORECASE)
        # Google Meet
        title = re.sub(r"\s*[-–]\s*Google Meet$", "", title)
        title = re.sub(r"^Meet\s*[-–]\s*", "", title)
        # Webex
        title = re.sub(r"\s*[-–]\s*Cisco Webex (Meetings?|Webinars?)$", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s*\|\s*Webex$", "", title, flags=re.IGNORECASE)
        title = re.sub(r"^Webex\s*[-–|]\s*", "", title, flags=re.IGNORECASE)
        # Slack huddle
        title = re.sub(r"\s*[-–]\s*Slack$", "", title)
        cleaned = title.strip(" -|–")
        return cleaned or "Meeting"

    @Slot(str, float)
    def update_level(self, source: str, level: float) -> None:
        value = int(max(0.0, min(level, 1.0)) * 100)
        if source == "mic":
            self.mic_level.setValue(value)
            if hasattr(self, "live_mic_level"):
                self.live_mic_level.setValue(value)
        elif source == "system":
            self.system_level.setValue(value)
            if hasattr(self, "live_system_level"):
                self.live_system_level.setValue(value)
            if value >= 3:
                self.system_audio_detected = True
            elif (
                self.timer_phase == "recording"
                and not getattr(self, "system_audio_detected", False)
                and not getattr(self, "system_audio_warning_shown", False)
                and self.recording_started_at
                and (datetime.now() - self.recording_started_at).total_seconds() >= 30
            ):
                self.system_audio_warning_shown = True
                self.log("System audio is still silent after 30 seconds; confirm the selected output device is correct.")
                if hasattr(self, "live_transcript_status_label"):
                    self.live_transcript_status_label.setText("System audio is silent; check output device.")

    @staticmethod
    def _device_by_name(devices: list[AudioDevice], name: str) -> AudioDevice | None:
        for device in devices:
            if device.name == name:
                return device
        return devices[0] if devices and not name else None

    @staticmethod
    def _profile_label(profile: str) -> str:
        for label, value in CAPTURE_PROFILES.items():
            if value == profile:
                return label
        return profile or "Unknown"

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total_seconds = max(0, int(seconds))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m {secs}s"
        if minutes:
            return f"{minutes}m {secs}s"
        return f"{secs}s"
