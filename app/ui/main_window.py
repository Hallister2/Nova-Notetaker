from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QAbstractItemView,
    QRadioButton,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.audio.capture_service import CaptureConfig, CaptureService
from app.audio.device_manager import AudioDevice, AudioDeviceManager
from app.core.settings import load_settings, save_settings
from app.storage.meeting_store import MeetingMetadata, MeetingStore
from app.ui.orb_widget import OrbWidget
from app.ui.styles import APP_STYLESHEET
from app.workflows.meeting_processor import MeetingProcessor


CAPTURE_PROFILES = {
    "Laptop mic + speakers": "laptop_speakers",
    "External mic + speakers": "external_mic_speakers",
    "Headphones / headset": "headphones",
    "Conference room": "conference_room",
    "Debug / raw capture": "debug_raw",
}


class SortableTableItem(QTableWidgetItem):
    def __lt__(self, other) -> bool:
        left = self.data(Qt.UserRole + 1)
        right = other.data(Qt.UserRole + 1)
        if left is not None and right is not None:
            return str(left) < str(right)
        return super().__lt__(other)


def select_combo_by_data(combo: QComboBox, value: str) -> None:
    for index in range(combo.count()):
        if combo.itemData(index) == value:
            combo.setCurrentIndex(index)
            return


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        settings: dict,
        microphones: list[AudioDevice],
        loopbacks: list[AudioDevice],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nova Settings")
        self.setMinimumWidth(560)
        self.settings = settings
        self.microphones = microphones
        self.loopbacks = loopbacks

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.mic_combo = QComboBox()
        for device in microphones:
            self.mic_combo.addItem(device.label, device.name)
        self._select_combo_by_value(self.mic_combo, settings["audio"].get("mic_device_name", ""))

        self.loopback_combo = QComboBox()
        self.loopback_combo.addItem("None", "")
        for device in loopbacks:
            self.loopback_combo.addItem(device.label, device.name)
        self._select_combo_by_value(self.loopback_combo, settings["audio"].get("system_loopback_device_name", ""))

        self.profile_combo = QComboBox()
        for label, value in CAPTURE_PROFILES.items():
            self.profile_combo.addItem(label, value)
        select_combo_by_data(self.profile_combo, settings["audio"].get("capture_profile", "laptop_speakers"))

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["ollama", "openai"])
        self.provider_combo.setCurrentText(settings["ai"].get("provider", "ollama"))

        self.ollama_url = QLineEdit(settings["ai"].get("ollama_url", ""))
        self.ollama_model = QLineEdit(settings["ai"].get("ollama_model", ""))
        self.ai_timeout = QSpinBox()
        self.ai_timeout.setRange(10, 1800)
        self.ai_timeout.setValue(int(settings["ai"].get("timeout_seconds", 180)))

        self.transcription_enabled = QCheckBox()
        self.transcription_enabled.setChecked(bool(settings["transcription"].get("enabled", False)))
        self.whisper_url = QLineEdit(settings["transcription"].get("whisperlive_url", ""))
        self.whisper_model = QLineEdit(settings["transcription"].get("model", "small"))
        self.whisper_language = QLineEdit(settings["transcription"].get("language", "en"))
        self.use_vad = QCheckBox()
        self.use_vad.setChecked(bool(settings["transcription"].get("use_vad", True)))
        self.cross_bleed_cleanup = QCheckBox()
        self.cross_bleed_cleanup.setChecked(bool(settings["transcription"].get("cross_bleed_cleanup", True)))
        self.transcription_timeout = QSpinBox()
        self.transcription_timeout.setRange(10, 1800)
        self.transcription_timeout.setValue(int(settings["transcription"].get("timeout_seconds", 120)))

        form.addRow("Microphone", self.mic_combo)
        form.addRow("System Audio", self.loopback_combo)
        form.addRow("Capture Profile", self.profile_combo)
        form.addRow("AI Provider", self.provider_combo)
        form.addRow("Ollama URL", self.ollama_url)
        form.addRow("Ollama Model", self.ollama_model)
        form.addRow("AI Timeout", self.ai_timeout)
        form.addRow("WhisperLive Enabled", self.transcription_enabled)
        form.addRow("WhisperLive URL", self.whisper_url)
        form.addRow("Whisper Model", self.whisper_model)
        form.addRow("Whisper Language", self.whisper_language)
        form.addRow("Use VAD", self.use_vad)
        form.addRow("Speaker-Bleed Cleanup", self.cross_bleed_cleanup)
        form.addRow("Transcription Timeout", self.transcription_timeout)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply_to_settings(self) -> dict:
        self.settings["audio"]["mic_device_name"] = str(self.mic_combo.currentData() or "")
        self.settings["audio"]["system_loopback_device_name"] = str(self.loopback_combo.currentData() or "")
        self.settings["audio"]["capture_profile"] = str(self.profile_combo.currentData() or "external_mic_speakers")
        self.settings["ai"]["provider"] = self.provider_combo.currentText()
        self.settings["ai"]["ollama_url"] = self.ollama_url.text().strip()
        self.settings["ai"]["ollama_model"] = self.ollama_model.text().strip()
        self.settings["ai"]["timeout_seconds"] = self.ai_timeout.value()
        self.settings["transcription"]["enabled"] = self.transcription_enabled.isChecked()
        self.settings["transcription"]["whisperlive_url"] = self.whisper_url.text().strip()
        self.settings["transcription"]["model"] = self.whisper_model.text().strip()
        self.settings["transcription"]["language"] = self.whisper_language.text().strip()
        self.settings["transcription"]["use_vad"] = self.use_vad.isChecked()
        self.settings["transcription"]["cross_bleed_cleanup"] = self.cross_bleed_cleanup.isChecked()
        self.settings["transcription"]["timeout_seconds"] = self.transcription_timeout.value()
        return self.settings

    @staticmethod
    def _select_combo_by_value(combo: QComboBox, value: str) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return


class ReprocessDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Reprocess Meeting")
        layout = QVBoxLayout(self)
        self.notes_only = QRadioButton("Regenerate notes only")
        self.notes_only.setChecked(True)
        self.full = QRadioButton("Full reprocess: transcribe audio and regenerate notes")
        layout.addWidget(self.notes_only)
        layout.addWidget(self.full)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def mode(self) -> str:
        return "full" if self.full.isChecked() else "notes_only"


class CaptureWorker(QObject):
    status = Signal(str)
    level = Signal(str, float)
    stopped = Signal()

    def __init__(self, config: CaptureConfig) -> None:
        super().__init__()
        self.service = CaptureService(config, self.status.emit, self.level.emit)

    @Slot()
    def start(self) -> None:
        self.service.start()

    @Slot()
    def stop(self) -> None:
        self.service.stop()
        self.stopped.emit()

    def request_stop(self) -> None:
        self.service.request_stop()


class ProcessingWorker(QObject):
    status = Signal(str)
    finished = Signal()

    def __init__(self, folder: Path, metadata: MeetingMetadata, mode: str = "full") -> None:
        super().__init__()
        self.folder = folder
        self.metadata = metadata
        self.mode = mode

    @Slot()
    def process(self) -> None:
        try:
            MeetingProcessor().process(self.folder, self.metadata, self.status.emit, mode=self.mode)
        except Exception as error:
            self.status.emit(f"Post-processing failed: {error}")
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    request_worker_start = Signal()
    request_worker_stop = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        self.device_manager = AudioDeviceManager()
        self.meeting_store = MeetingStore()
        self.meeting_folder: Path | None = None
        self.metadata: MeetingMetadata | None = None
        self.worker_thread: QThread | None = None
        self.worker: CaptureWorker | None = None
        self.processing_thread: QThread | None = None
        self.processing_worker: ProcessingWorker | None = None
        self.microphones: list[AudioDevice] = []
        self.loopbacks: list[AudioDevice] = []
        self.active_preview_file = "notes.md"
        self.processing_mode = "full"
        self.recording_started_at: datetime | None = None
        self.nav_buttons: list[QPushButton] = []
        self.nav_button_labels = ["Live Capture", "Meetings", "Logs", "Templates", "Settings"]
        self.compact_nav_labels = ["Live", "Meet", "Logs", "Tpl", "Set"]
        self.current_responsive_mode = ""
        self.stop_requested = False

        self.setWindowTitle("Nova Notetaker")
        self.setMinimumSize(900, 620)
        self.setStyleSheet(APP_STYLESHEET)

        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self._update_elapsed_timer)

        self._build_ui()
        self.refresh_devices()
        self.refresh_meetings()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = self._build_sidebar()
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_live_page())
        self.pages.addWidget(self._build_meetings_page())
        self.pages.addWidget(self._build_archive_page())
        self.pages.addWidget(self._build_templates_page())
        self.pages.addWidget(self._build_settings_page())

        content_layout.addWidget(self.pages, stretch=1)
        content_layout.addWidget(self._build_footer())
        root_layout.addWidget(self.sidebar)
        root_layout.addWidget(content, stretch=1)
        self.setCentralWidget(root)
        self._set_active_nav(0)
        self._apply_responsive_layout(self.width())

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(240)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 26, 18, 18)
        layout.setSpacing(10)

        logo = QLabel("NOVA")
        logo.setObjectName("Logo")
        logo_sub = QLabel("NOTETAKER")
        logo_sub.setObjectName("LogoSub")
        layout.addWidget(logo)
        layout.addWidget(logo_sub)
        layout.addSpacing(24)

        for index, label in enumerate(self.nav_button_labels):
            button = QPushButton(label)
            button.setObjectName("SidebarButton")
            button.setProperty("active", "false")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, page=index: self._set_active_nav(page))
            layout.addWidget(button)
            self.nav_buttons.append(button)

        layout.addStretch()
        status_card = QFrame()
        status_card.setObjectName("Panel")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 14, 16, 14)
        status_layout.setSpacing(8)
        self.sidebar_ready_label = QLabel("Ready")
        self.sidebar_ready_label.setObjectName("GreenText")
        status_layout.addWidget(self.sidebar_ready_label)
        status_layout.addWidget(self._muted_label("All systems operational"))
        mini_orb = OrbWidget()
        mini_orb.setFixedSize(118, 118)
        self.orb = mini_orb
        status_layout.addWidget(mini_orb, alignment=Qt.AlignCenter)
        status_layout.addWidget(QLabel("AI Services"))
        self.sidebar_services_label = self._muted_label("Ollama  -  WhisperLive")
        status_layout.addWidget(self.sidebar_services_label)
        layout.addWidget(status_card)
        return sidebar

    def _build_live_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.live_page_layout = layout
        layout.setContentsMargins(34, 28, 18, 28)
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

        self.settings_button = QPushButton("Configure")
        self.settings_button.clicked.connect(self.open_settings)
        self.new_meeting_button = QPushButton("Start Recording")
        self.new_meeting_button.setObjectName("PrimaryButton")
        self.new_meeting_button.clicked.connect(self.start_capture)
        self.start_button = self.new_meeting_button
        header.addLayout(title_block)
        header.addStretch()
        header.addWidget(self.settings_button)
        header.addWidget(self.new_meeting_button)
        layout.addLayout(header)

        main_grid = QGridLayout()
        self.live_main_grid = main_grid
        main_grid.setSpacing(18)
        center = QWidget()
        self.live_center_widget = center
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(14)
        center_layout.addWidget(self._build_meeting_status_card())
        center_layout.addWidget(self._build_transcript_card(), stretch=1)
        center_layout.addWidget(self._build_action_bar())
        main_grid.addWidget(center, 0, 0)
        self.insights_panel = self._build_insights_panel()
        main_grid.addWidget(self.insights_panel, 0, 1)
        main_grid.setColumnStretch(0, 1)
        main_grid.setColumnMinimumWidth(1, 380)
        layout.addLayout(main_grid, stretch=1)
        return page

    def _build_meeting_status_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Panel")
        layout = QGridLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setHorizontalSpacing(28)
        layout.setVerticalSpacing(8)

        self.meeting_title = QLineEdit()
        self.meeting_title.setPlaceholderText("Meeting title")
        self.meeting_title.setText("Teams Meeting")
        self.detect_title_button = QPushButton("Detect title")
        self.detect_title_button.clicked.connect(self.detect_active_window_title)

        title_stack = QVBoxLayout()
        title_stack.setSpacing(8)
        self.meeting_title.setMinimumWidth(360)
        title_stack.addWidget(self.meeting_title)
        title_stack.addWidget(self.detect_title_button, alignment=Qt.AlignLeft)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("GreenText")
        self.elapsed_label = QLabel("00:00:00")
        self.elapsed_label.setObjectName("StatValue")
        self.status_detail_label = self._muted_label("Waiting to start")
        self.orb_caption = self.status_detail_label
        self.capture_mic_toggle = QCheckBox("Capture microphone")
        self.capture_mic_toggle.setChecked(bool(self.settings["audio"].get("capture_mic", True)))
        self.capture_mic_toggle.toggled.connect(self._save_capture_mic_toggle)
        self.settings_summary = self._muted_label("")
        self.mic_level = QProgressBar()
        self.mic_level.setRange(0, 100)
        self.system_level = QProgressBar()
        self.system_level.setRange(0, 100)

        layout.addWidget(self._section_label("Meeting title"), 0, 0)
        layout.addWidget(self._section_label("Status"), 0, 1)
        layout.addWidget(self._section_label("Audio levels"), 0, 2, 1, 2)
        layout.addLayout(title_stack, 1, 0, 3, 1)
        layout.addWidget(self.status_label, 1, 1)
        layout.addWidget(self.elapsed_label, 2, 1)
        layout.addWidget(self.status_detail_label, 3, 1)
        layout.addWidget(QLabel("Mic"), 1, 2)
        layout.addWidget(self.mic_level, 1, 3)
        layout.addWidget(QLabel("System"), 2, 2)
        layout.addWidget(self.system_level, 2, 3)
        layout.addWidget(self.capture_mic_toggle, 3, 2, 1, 2)
        layout.addWidget(self.settings_summary, 4, 0, 1, 4)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 2)
        return card

    def _build_transcript_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Panel")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(self._section_label("Live transcript"))
        top.addStretch()
        self.speaker_filter = QComboBox()
        self.speaker_filter.addItems(["Speakers", "You", "Meeting Audio"])
        self.pause_button = QPushButton("Pause")
        self.pause_button.setEnabled(False)
        top.addWidget(self.speaker_filter)
        top.addWidget(self.pause_button)
        layout.addLayout(top)

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
        bar.setObjectName("Panel")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(16)
        self.mark_important_button = QPushButton("Mark Important")
        self.mark_important_button.setEnabled(False)
        self.stop_button = QPushButton("Stop Recording")
        self.stop_button.setObjectName("DangerButton")
        self.stop_button.clicked.connect(self.stop_capture)
        self.stop_button.setEnabled(False)
        self.add_note_button = QPushButton("Add Note")
        self.add_note_button.setEnabled(False)
        layout.addWidget(self.mark_important_button)
        layout.addWidget(self.stop_button, stretch=1)
        layout.addWidget(self.add_note_button)
        return bar

    def _build_insights_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setFixedWidth(390)
        panel.setMinimumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 20, 18, 18)
        layout.setSpacing(14)
        layout.addWidget(self._section_label("Meeting insights"))
        layout.addWidget(self._muted_label("Real-time intelligence"))
        self.action_items_count = QLabel("0")
        self.decisions_count = QLabel("0")
        self.dates_count = QLabel("0")
        layout.addWidget(self._insight_card("Action items", self.action_items_count, ["Waiting for notes generation"]))
        layout.addWidget(self._insight_card("Key decisions", self.decisions_count, ["Waiting for notes generation"]))
        layout.addWidget(self._insight_card("Dates detected", self.dates_count, ["Waiting for notes generation"]))
        layout.addStretch()
        return panel

    def _insight_card(self, title: str, count_label: QLabel, items: list[str]) -> QFrame:
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
        for item in items:
            layout.addWidget(self._muted_label(f"- {item}"))
        link = QLabel(f"View all {title.lower()}")
        link.setObjectName("OrangeText")
        layout.addWidget(link, alignment=Qt.AlignRight)
        return card

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
        self.meeting_table = QTableWidget(0, 4)
        self.meeting_table.setHorizontalHeaderLabels(["Date", "Time", "Meeting Name", "Status"])
        self.meeting_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.meeting_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.meeting_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.meeting_table.setSortingEnabled(True)
        self.meeting_table.itemSelectionChanged.connect(self.preview_selected_meeting)
        self.meeting_table.horizontalHeader().setStretchLastSection(True)
        archive_buttons = QHBoxLayout()
        self.refresh_meetings_button = QPushButton("Refresh")
        self.refresh_meetings_button.clicked.connect(self.refresh_meetings)
        self.reprocess_button = QPushButton("Reprocess")
        self.reprocess_button.clicked.connect(self.reprocess_selected_meeting)
        self.open_folder_button = QPushButton("Open folder")
        self.open_folder_button.clicked.connect(self.open_selected_meeting_folder)
        self.export_html_button = QPushButton("Export HTML")
        self.export_html_button.clicked.connect(self.export_selected_notes_html)
        for button in (self.refresh_meetings_button, self.reprocess_button, self.open_folder_button, self.export_html_button):
            archive_buttons.addWidget(button)
        self.archive_status = self._muted_label("Ready")
        meetings_panel_layout.addWidget(meetings_title)
        meetings_panel_layout.addWidget(self.meeting_table, stretch=1)
        meetings_panel_layout.addLayout(archive_buttons)
        meetings_panel_layout.addWidget(self.archive_status)

        preview_panel = QFrame()
        preview_panel.setObjectName("Panel")
        self.meeting_preview_panel = preview_panel
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(18, 18, 18, 18)
        self.meeting_preview_title = QLabel("Select a meeting")
        self.meeting_preview_title.setObjectName("SectionTitle")
        self.meeting_health = QTextEdit()
        self.meeting_health.setReadOnly(True)
        self.meeting_health.setMaximumHeight(150)
        self.meeting_preview = QTextEdit()
        self.meeting_preview.setReadOnly(True)
        preview_buttons = QHBoxLayout()
        self.show_notes_button = QPushButton("Notes")
        self.show_notes_button.clicked.connect(lambda: self.preview_selected_meeting_file("notes.md"))
        self.show_transcript_button = QPushButton("Transcript")
        self.show_transcript_button.clicked.connect(lambda: self.preview_selected_meeting_file("transcript.md"))
        self.show_metadata_button = QPushButton("Metadata")
        self.show_metadata_button.clicked.connect(lambda: self.preview_selected_meeting_file("metadata.json"))
        self.copy_preview_button = QPushButton("Copy")
        self.copy_preview_button.clicked.connect(self.copy_current_preview)
        for button in (self.show_notes_button, self.show_transcript_button, self.show_metadata_button, self.copy_preview_button):
            preview_buttons.addWidget(button)
        preview_layout.addWidget(self.meeting_preview_title)
        preview_layout.addWidget(self.meeting_health)
        preview_layout.addLayout(preview_buttons)
        preview_layout.addWidget(self.meeting_preview, stretch=1)
        meetings_layout.addWidget(meetings_panel, 0, 0)
        meetings_layout.addWidget(preview_panel, 0, 1)
        meetings_layout.setColumnStretch(0, 1)
        meetings_layout.setColumnStretch(1, 2)
        return meetings_tab

    def _build_archive_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 28, 18, 28)
        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        title = QLabel("Logs")
        title.setObjectName("Title")
        panel_layout.addWidget(title)
        panel_layout.addWidget(self._muted_label("Raw output logs for capture, transcription, and processing."))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.append("Nova Notetaker online.")
        panel_layout.addWidget(self.log_output, stretch=1)
        layout.addWidget(panel)
        return page

    def _build_templates_page(self) -> QWidget:
        return self._placeholder_page("Templates", "Meeting note templates are queued for a future pass.")

    def _build_settings_page(self) -> QWidget:
        page = self._placeholder_page("Settings", "Device, capture, WhisperLive, and Ollama settings are managed in the configuration window.")
        button = QPushButton("Open settings")
        button.clicked.connect(self.open_settings)
        page.layout().itemAt(0).widget().layout().addWidget(button, alignment=Qt.AlignLeft)
        return page

    def _placeholder_page(self, title_text: str, body_text: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 28, 18, 28)
        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        title = QLabel(title_text)
        title.setObjectName("Title")
        panel_layout.addWidget(title)
        panel_layout.addWidget(self._muted_label(body_text))
        panel_layout.addStretch()
        layout.addWidget(panel)
        return page

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("Footer")
        self.footer = footer
        footer.setFixedHeight(54)
        layout = QHBoxLayout(footer)
        self.footer_layout = layout
        layout.setContentsMargins(28, 0, 28, 0)
        self.footer_save_label = QLabel("Saving to: meetings")
        self.footer_save_label.setObjectName("Subtitle")
        self.footer_autosave_label = QLabel("Auto-save: ON")
        self.footer_autosave_label.setObjectName("Subtitle")
        self.footer_transcription_label = QLabel("Transcription: WhisperLive")
        self.footer_transcription_label.setObjectName("Subtitle")
        self.footer_intelligence_label = QLabel("Intelligence: Ollama")
        self.footer_intelligence_label.setObjectName("Subtitle")
        layout.addWidget(self.footer_save_label)
        layout.addStretch()
        layout.addWidget(self.footer_autosave_label)
        layout.addSpacing(28)
        layout.addWidget(self.footer_transcription_label)
        layout.addSpacing(28)
        layout.addWidget(self.footer_intelligence_label)
        return footer

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    @staticmethod
    def _muted_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        return label

    def _set_active_nav(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setProperty("active", "true" if button_index == index else "false")
            button.style().unpolish(button)
            button.style().polish(button)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())

    def _apply_responsive_layout(self, width: int) -> None:
        if width >= 1380:
            mode = "wide"
        elif width >= 1180:
            mode = "medium"
        elif width >= 980:
            mode = "compact"
        else:
            mode = "narrow"

        if mode == self.current_responsive_mode:
            return
        self.current_responsive_mode = mode

        if mode == "wide":
            self._set_sidebar_mode(width=240, compact=False, show_status=True)
            self._set_live_page_margins(34, 28, 18, 28, spacing=18)
            self._set_insights_visible(True, width=390)
            self.meeting_title.setMinimumWidth(360)
            self.settings_summary.setVisible(True)
            self.footer.setFixedHeight(54)
            self.footer_save_label.setVisible(True)
            self.footer_transcription_label.setVisible(True)
            self.footer_intelligence_label.setVisible(True)
        elif mode == "medium":
            self._set_sidebar_mode(width=220, compact=False, show_status=True)
            self._set_live_page_margins(28, 24, 16, 24, spacing=16)
            self._set_insights_visible(True, width=340)
            self.meeting_title.setMinimumWidth(300)
            self.settings_summary.setVisible(True)
            self.footer.setFixedHeight(50)
            self.footer_save_label.setVisible(True)
            self.footer_transcription_label.setVisible(True)
            self.footer_intelligence_label.setVisible(True)
        elif mode == "compact":
            self._set_sidebar_mode(width=190, compact=False, show_status=False)
            self._set_live_page_margins(22, 22, 14, 22, spacing=14)
            self._set_insights_visible(False)
            self.meeting_title.setMinimumWidth(260)
            self.settings_summary.setVisible(True)
            self.footer.setFixedHeight(46)
            self.footer_save_label.setVisible(False)
            self.footer_transcription_label.setVisible(True)
            self.footer_intelligence_label.setVisible(True)
        else:
            self._set_sidebar_mode(width=88, compact=True, show_status=False)
            self._set_live_page_margins(16, 18, 12, 18, spacing=12)
            self._set_insights_visible(False)
            self.meeting_title.setMinimumWidth(200)
            self.settings_summary.setVisible(False)
            self.footer.setFixedHeight(42)
            self.footer_save_label.setVisible(False)
            self.footer_transcription_label.setVisible(False)
            self.footer_intelligence_label.setVisible(False)

        self._apply_meetings_responsive(mode)

    def _set_sidebar_mode(self, width: int, compact: bool, show_status: bool) -> None:
        self.sidebar.setFixedWidth(width)
        self.sidebar.layout().setContentsMargins(12 if compact else 18, 22, 12 if compact else 18, 16)
        for index, button in enumerate(self.nav_buttons):
            button.setText(self.compact_nav_labels[index] if compact else self.nav_button_labels[index])
        self.sidebar_ready_label.parentWidget().setVisible(show_status)

    def _set_live_page_margins(self, left: int, top: int, right: int, bottom: int, spacing: int) -> None:
        self.live_page_layout.setContentsMargins(left, top, right, bottom)
        self.live_page_layout.setSpacing(spacing)
        self.live_main_grid.setSpacing(spacing)

    def _set_insights_visible(self, visible: bool, width: int | None = None) -> None:
        self.insights_panel.setVisible(visible)
        if width is not None:
            self.insights_panel.setFixedWidth(width)
        self.live_main_grid.setColumnMinimumWidth(1, width if visible and width else 0)

    def _apply_meetings_responsive(self, mode: str) -> None:
        if not hasattr(self, "meeting_preview_panel"):
            return
        if mode == "narrow":
            self.meeting_preview_panel.setVisible(False)
            self.meetings_layout.setContentsMargins(16, 18, 12, 18)
        else:
            self.meeting_preview_panel.setVisible(True)
            self.meetings_layout.setContentsMargins(28 if mode == "compact" else 34, 28, 18, 28)

    def _set_transcript_rows(self, rows: list[tuple[str, str, str]]) -> None:
        while self.transcript_layout.count():
            item = self.transcript_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not rows:
            rows = [("--:--:--", "Meeting Audio", "Transcript rows will appear here after capture and processing.")]

        for timestamp, speaker, text in rows:
            row = QFrame()
            row.setObjectName("TranscriptRow")
            row_layout = QGridLayout(row)
            row_layout.setContentsMargins(12, 11, 12, 11)
            row_layout.setHorizontalSpacing(12)
            time_label = self._muted_label(timestamp)
            speaker_label = QLabel(speaker)
            speaker_label.setObjectName("OrangeText" if speaker == "You" else "BlueText")
            text_label = QLabel(text)
            text_label.setWordWrap(True)
            row_layout.addWidget(time_label, 0, 0, Qt.AlignTop)
            row_layout.addWidget(speaker_label, 0, 1, Qt.AlignTop)
            row_layout.addWidget(text_label, 1, 1)
            row_layout.setColumnMinimumWidth(0, 72)
            row_layout.setColumnMinimumWidth(1, 120)
            row_layout.setColumnStretch(1, 1)
            self.transcript_layout.addWidget(row)
        self.transcript_layout.addStretch()

    def _refresh_live_transcript_from_file(self) -> None:
        if not self.meeting_folder:
            return
        transcript_path = self.meeting_folder / "transcript.md"
        if not transcript_path.exists():
            return
        text = transcript_path.read_text(encoding="utf-8")
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

    def _update_elapsed_timer(self) -> None:
        if not self.recording_started_at:
            self.elapsed_label.setText("00:00:00")
            return
        elapsed = datetime.now() - self.recording_started_at
        total_seconds = max(0, int(elapsed.total_seconds()))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.elapsed_label.setText(f"{hours:02}:{minutes:02}:{seconds:02}")

    @staticmethod
    def _refresh_widget_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _build_legacy_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("Panel")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 12, 22, 12)

        title_block = QVBoxLayout()
        title = QLabel("NOVA NOTETAKER")
        title.setObjectName("Title")
        subtitle = QLabel("MEETING INTELLIGENCE CAPTURE SYSTEM")
        subtitle.setObjectName("Subtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)

        self.status_label = QLabel("● READY")
        self.status_label.setObjectName("Subtitle")

        header_layout.addLayout(title_block)
        header_layout.addStretch()
        header_layout.addWidget(self.status_label)

        self.settings_button = QPushButton("SETTINGS")
        self.settings_button.clicked.connect(self.open_settings)
        header_layout.addWidget(self.settings_button)

        self.meeting_title = QLineEdit()
        self.meeting_title.setPlaceholderText("Meeting title")
        self.meeting_title.setText("Teams Meeting")
        self.detect_title_button = QPushButton("DETECT TITLE")
        self.detect_title_button.clicked.connect(self.detect_active_window_title)

        self.capture_mic_toggle = QCheckBox("Capture microphone")
        self.capture_mic_toggle.setChecked(bool(self.settings["audio"].get("capture_mic", True)))
        self.capture_mic_toggle.toggled.connect(self._save_capture_mic_toggle)

        self.start_button = QPushButton("START MEETING")
        self.start_button.clicked.connect(self.start_capture)

        self.stop_button = QPushButton("STOP MEETING")
        self.stop_button.clicked.connect(self.stop_capture)
        self.stop_button.setEnabled(False)

        self.tabs = QTabWidget()

        main_tab = QWidget()
        main_layout = QGridLayout(main_tab)
        main_layout.setSpacing(12)

        capture_panel = QFrame()
        capture_panel.setObjectName("Panel")
        capture_layout = QVBoxLayout(capture_panel)
        capture_layout.setContentsMargins(18, 18, 18, 18)
        capture_layout.setSpacing(12)

        capture_title = QLabel("MEETING CAPTURE")
        capture_title.setObjectName("SectionTitle")
        self.settings_summary = QLabel("")
        self.settings_summary.setObjectName("Subtitle")

        capture_layout.addWidget(capture_title)
        capture_layout.addWidget(QLabel("Meeting Title"))
        capture_layout.addWidget(self.meeting_title)
        capture_layout.addWidget(self.detect_title_button)
        capture_layout.addWidget(self.capture_mic_toggle)
        capture_layout.addWidget(self.settings_summary)
        capture_layout.addSpacing(8)
        capture_layout.addWidget(self.start_button)
        capture_layout.addWidget(self.stop_button)
        capture_layout.addStretch()

        signal_panel = QFrame()
        signal_panel.setObjectName("Panel")
        signal_layout = QVBoxLayout(signal_panel)
        signal_layout.setContentsMargins(18, 18, 18, 18)
        signal_layout.setSpacing(10)

        self.orb = OrbWidget()
        self.orb_caption = QLabel("SYSTEM IDLE")
        self.orb_caption.setObjectName("Subtitle")
        self.orb_caption.setAlignment(__import__("PySide6.QtCore").QtCore.Qt.AlignCenter)

        levels_title = QLabel("LIVE SIGNAL")
        levels_title.setObjectName("SectionTitle")
        self.mic_level = QProgressBar()
        self.mic_level.setRange(0, 100)
        self.system_level = QProgressBar()
        self.system_level.setRange(0, 100)

        signal_layout.addWidget(self.orb, stretch=1)
        signal_layout.addWidget(self.orb_caption)
        signal_layout.addWidget(levels_title)
        signal_layout.addWidget(QLabel("Mic"))
        signal_layout.addWidget(self.mic_level)
        signal_layout.addWidget(QLabel("System"))
        signal_layout.addWidget(self.system_level)

        main_layout.addWidget(capture_panel, 0, 0)
        main_layout.addWidget(signal_panel, 0, 1)
        main_layout.setColumnStretch(0, 1)
        main_layout.setColumnStretch(1, 2)

        meetings_tab = QWidget()
        meetings_layout = QGridLayout(meetings_tab)
        meetings_layout.setSpacing(12)

        meetings_panel = QFrame()
        meetings_panel.setObjectName("Panel")
        meetings_panel_layout = QVBoxLayout(meetings_panel)
        meetings_panel_layout.setContentsMargins(18, 18, 18, 18)

        meetings_title = QLabel("MEETING ARCHIVE")
        meetings_title.setObjectName("SectionTitle")
        self.meeting_table = QTableWidget(0, 4)
        self.meeting_table.setHorizontalHeaderLabels(["Date", "Time", "Meeting Name", "Status"])
        self.meeting_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.meeting_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.meeting_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.meeting_table.setSortingEnabled(True)
        self.meeting_table.itemSelectionChanged.connect(self.preview_selected_meeting)
        self.meeting_table.horizontalHeader().setStretchLastSection(True)
        archive_buttons = QHBoxLayout()
        self.refresh_meetings_button = QPushButton("REFRESH")
        self.refresh_meetings_button.clicked.connect(self.refresh_meetings)
        self.reprocess_button = QPushButton("REPROCESS")
        self.reprocess_button.clicked.connect(self.reprocess_selected_meeting)
        self.open_folder_button = QPushButton("OPEN FOLDER")
        self.open_folder_button.clicked.connect(self.open_selected_meeting_folder)
        self.export_html_button = QPushButton("EXPORT HTML")
        self.export_html_button.clicked.connect(self.export_selected_notes_html)
        archive_buttons.addWidget(self.refresh_meetings_button)
        archive_buttons.addWidget(self.reprocess_button)
        archive_buttons.addWidget(self.open_folder_button)
        archive_buttons.addWidget(self.export_html_button)
        self.archive_status = QLabel("Ready")
        self.archive_status.setObjectName("Subtitle")
        meetings_panel_layout.addWidget(meetings_title)
        meetings_panel_layout.addWidget(self.meeting_table, stretch=1)
        meetings_panel_layout.addLayout(archive_buttons)
        meetings_panel_layout.addWidget(self.archive_status)

        preview_panel = QFrame()
        preview_panel.setObjectName("Panel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(18, 18, 18, 18)
        self.meeting_preview_title = QLabel("SELECT A MEETING")
        self.meeting_preview_title.setObjectName("SectionTitle")
        self.meeting_health = QTextEdit()
        self.meeting_health.setReadOnly(True)
        self.meeting_health.setMaximumHeight(150)
        self.meeting_preview = QTextEdit()
        self.meeting_preview.setReadOnly(True)
        preview_buttons = QHBoxLayout()
        self.show_notes_button = QPushButton("NOTES")
        self.show_notes_button.clicked.connect(lambda: self.preview_selected_meeting_file("notes.md"))
        self.show_transcript_button = QPushButton("TRANSCRIPT")
        self.show_transcript_button.clicked.connect(lambda: self.preview_selected_meeting_file("transcript.md"))
        self.show_metadata_button = QPushButton("METADATA")
        self.show_metadata_button.clicked.connect(lambda: self.preview_selected_meeting_file("metadata.json"))
        self.copy_preview_button = QPushButton("COPY")
        self.copy_preview_button.clicked.connect(self.copy_current_preview)
        preview_buttons.addWidget(self.show_notes_button)
        preview_buttons.addWidget(self.show_transcript_button)
        preview_buttons.addWidget(self.show_metadata_button)
        preview_buttons.addWidget(self.copy_preview_button)
        preview_layout.addWidget(self.meeting_preview_title)
        preview_layout.addWidget(self.meeting_health)
        preview_layout.addLayout(preview_buttons)
        preview_layout.addWidget(self.meeting_preview, stretch=1)

        meetings_layout.addWidget(meetings_panel, 0, 0)
        meetings_layout.addWidget(preview_panel, 0, 1)
        meetings_layout.setColumnStretch(0, 1)
        meetings_layout.setColumnStretch(1, 2)

        logs_tab = QWidget()
        logs_layout = QVBoxLayout(logs_tab)
        logs_layout.setContentsMargins(0, 0, 0, 0)

        log_title = QLabel("CAPTURE LOG")
        log_title.setObjectName("SectionTitle")
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.append("Nova Notetaker online.")

        log_panel = QFrame()
        log_panel.setObjectName("Panel")
        log_panel_layout = QVBoxLayout(log_panel)
        log_panel_layout.setContentsMargins(18, 18, 18, 18)
        log_panel_layout.addWidget(log_title)
        log_panel_layout.addWidget(self.log_output, stretch=1)
        logs_layout.addWidget(log_panel)

        self.tabs.addTab(main_tab, "Main")
        self.tabs.addTab(meetings_tab, "Meetings")
        self.tabs.addTab(logs_tab, "Logs")

        root_layout.addWidget(header)
        root_layout.addWidget(self.tabs, stretch=1)
        self.setCentralWidget(root)

    def refresh_devices(self) -> None:
        self.microphones = self.device_manager.list_microphones()
        self.loopbacks = self.device_manager.list_wasapi_loopbacks()

        self.update_settings_summary()
        self.log(f"Detected {len(self.microphones)} microphone device(s) and {len(self.loopbacks)} loopback device(s).")

        if not self.loopbacks:
            self.log("No WASAPI loopback devices detected. On Windows, install/check pyaudiowpatch and confirm output devices are enabled.")

    def start_capture(self) -> None:
        mic_device = self._device_by_name(self.microphones, self.settings["audio"].get("mic_device_name", ""))
        loop_device = self._device_by_name(self.loopbacks, self.settings["audio"].get("system_loopback_device_name", ""))

        if mic_device is None:
            QMessageBox.warning(self, "Nova Notetaker", "Select a microphone in Settings before starting capture.")
            return

        self._save_audio_selections(mic_device, loop_device)

        title = self.meeting_title.text().strip() or "Untitled Meeting"
        self.meeting_folder = self.meeting_store.create_meeting_folder(title)
        started_at = datetime.now().isoformat(timespec="seconds")
        self.metadata = MeetingMetadata(
            title=title,
            started_at=started_at,
            mic_device_name=mic_device.name,
            system_device_name=loop_device.name if loop_device else None,
            capture_mic=bool(self.settings["audio"].get("capture_mic", True)),
            capture_profile=str(self.settings["audio"].get("capture_profile", "external_mic_speakers")),
            status="recording",
        )
        self.meeting_store.write_metadata(self.meeting_folder, self.metadata)

        config = CaptureConfig(
            meeting_folder=self.meeting_folder,
            mic_device_index=mic_device.index,
            loopback_device_index=loop_device.index if loop_device else None,
            capture_mic=bool(self.settings["audio"].get("capture_mic", True)),
            mic_sample_rate=mic_device.sample_rate or 48000,
            mic_channels=self._capture_channels(mic_device, default=1),
            loopback_sample_rate=(loop_device.sample_rate if loop_device else None) or 48000,
            loopback_channels=self._capture_channels(loop_device, default=2),
        )

        self.worker_thread = QThread(self)
        self.worker = CaptureWorker(config)
        self.worker.moveToThread(self.worker_thread)

        self.request_worker_start.connect(self.worker.start)
        self.request_worker_stop.connect(self.worker.stop)
        self.worker.status.connect(self.log)
        self.worker.level.connect(self.update_level)
        self.worker.stopped.connect(self.worker_thread.quit)
        self.worker.stopped.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self._capture_finished)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

        self.stop_requested = False
        self.start_button.setEnabled(False)
        self.start_button.setText("Recording")
        self.stop_button.setEnabled(True)
        self.settings_button.setEnabled(False)
        self.capture_mic_toggle.setEnabled(False)
        self.reprocess_button.setEnabled(False)
        self.recording_started_at = datetime.now()
        self.elapsed_timer.start(1000)
        self._update_elapsed_timer()
        self.orb.set_state("recording")
        self.status_label.setObjectName("RedText")
        self.status_label.setText("Recording")
        self._refresh_widget_style(self.status_label)
        self.orb_caption.setText("Recording in progress")
        self.footer_save_label.setText(f"Saving to: {self.meeting_folder}")
        self._set_transcript_rows([("--:--:--", "Meeting Audio", "Capture is running. Transcript will appear after processing.")])
        self.log(f"Meeting folder: {self.meeting_folder}")
        self.log(
            "Capture format: "
            f"mic {'muted' if not config.capture_mic else f'{config.mic_sample_rate} Hz / {config.mic_channels} ch'}, "
            f"system {config.loopback_sample_rate} Hz / {config.loopback_channels} ch"
        )
        self.log(f"Capture profile: {self._profile_label(self.settings['audio'].get('capture_profile', ''))}")
        self.request_worker_start.emit()

    def stop_capture(self) -> None:
        if not self.worker:
            return
        if self.stop_requested:
            return
        self.stop_requested = True
        self.stop_button.setEnabled(False)
        self.status_label.setText("Stopping")
        self.orb_caption.setText("Finalizing capture")
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
        self.stop_button.setEnabled(False)
        self.orb.set_state("processing")
        self.status_label.setText("Processing")
        self.orb_caption.setText("Generating notes")

        if self.metadata and self.meeting_folder:
            self._start_processing(self.meeting_folder, self.metadata, mode="full")
        else:
            self._processing_finished()

    def _save_audio_selections(self, mic_device: AudioDevice, loop_device: AudioDevice | None) -> None:
        self.settings["audio"]["mic_device_name"] = mic_device.name
        self.settings["audio"]["system_loopback_device_name"] = loop_device.name if loop_device else ""
        save_settings(self.settings)

    def _save_capture_mic_toggle(self, enabled: bool) -> None:
        self.settings["audio"]["capture_mic"] = enabled
        save_settings(self.settings)
        self.update_settings_summary()
        self.mic_level.setValue(0 if not enabled else self.mic_level.value())
        self.log(f"Microphone capture {'enabled' if enabled else 'muted'}.")

    @staticmethod
    def _capture_channels(device: AudioDevice | None, default: int) -> int:
        if device is None or device.channels <= 0:
            return default
        return min(device.channels, 2)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self, self.settings, self.microphones, self.loopbacks)
        if dialog.exec() != QDialog.Accepted:
            return
        self.settings = dialog.apply_to_settings()
        save_settings(self.settings)
        self.update_settings_summary()
        self.log("Settings saved.")

    def update_settings_summary(self) -> None:
        mic_name = self.settings["audio"].get("mic_device_name", "") or "No microphone selected"
        system_name = self.settings["audio"].get("system_loopback_device_name", "") or "No system audio selected"
        profile = self._profile_label(self.settings["audio"].get("capture_profile", ""))
        provider = self.settings["ai"].get("provider", "ollama")
        whisper = "on" if self.settings["transcription"].get("enabled", False) else "off"
        mic_state = "on" if self.settings["audio"].get("capture_mic", True) else "muted"
        self.settings_summary.setText(
            f"Mic {mic_state}  |  System: {system_name}  |  Profile: {profile}  |  {provider} / WhisperLive {whisper}"
        )
        if hasattr(self, "footer_transcription_label"):
            self.footer_transcription_label.setText(f"Transcription: WhisperLive {whisper}")
        if hasattr(self, "footer_intelligence_label"):
            self.footer_intelligence_label.setText(f"Intelligence: {provider}")
        if hasattr(self, "sidebar_services_label"):
            self.sidebar_services_label.setText(f"Ollama  -  WhisperLive {whisper}")

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

    def _start_processing(self, folder: Path, metadata: MeetingMetadata, mode: str = "full") -> None:
        self.processing_mode = mode
        self.processing_thread = QThread(self)
        self.processing_worker = ProcessingWorker(folder, metadata, mode=mode)
        self.processing_worker.moveToThread(self.processing_thread)
        self.processing_thread.started.connect(self.processing_worker.process)
        self.processing_worker.status.connect(self.log)
        self.processing_worker.finished.connect(self.processing_thread.quit)
        self.processing_worker.finished.connect(self.processing_worker.deleteLater)
        self.processing_thread.finished.connect(self._processing_finished)
        self.processing_thread.finished.connect(self.processing_thread.deleteLater)
        self.processing_thread.start()

    def _processing_finished(self) -> None:
        self.processing_worker = None
        self.processing_thread = None
        self.start_button.setEnabled(True)
        self.start_button.setText("Start Recording")
        self.stop_button.setEnabled(False)
        self.settings_button.setEnabled(True)
        self.capture_mic_toggle.setEnabled(True)
        self.elapsed_timer.stop()
        if hasattr(self, "reprocess_button"):
            self.reprocess_button.setEnabled(True)
        if hasattr(self, "refresh_meetings_button"):
            self.refresh_meetings_button.setEnabled(True)
        if hasattr(self, "open_folder_button"):
            self.open_folder_button.setEnabled(True)
        if hasattr(self, "export_html_button"):
            self.export_html_button.setEnabled(True)
        self.orb.set_state("idle")
        self.status_label.setObjectName("GreenText")
        self.status_label.setText("Ready")
        self._refresh_widget_style(self.status_label)
        self.orb_caption.setText("Waiting to start")
        if self.meeting_folder:
            self.log(f"Processing complete. Notes: {self.meeting_folder / 'notes.md'}")
            self._refresh_live_transcript_from_file()
        if hasattr(self, "archive_status"):
            self.archive_status.setText("Processing complete")
        self.refresh_meetings()
        self.preview_selected_meeting_file(self.active_preview_file)

    def refresh_meetings(self) -> None:
        if not hasattr(self, "meeting_table"):
            return
        current_folder = self._selected_meeting_folder()
        self.meeting_table.setSortingEnabled(False)
        self.meeting_table.setRowCount(0)
        for folder in self.meeting_store.list_meetings():
            try:
                metadata = self.meeting_store.read_metadata(folder)
                date_text, time_text = self._split_started_at(metadata.started_at)
                title = metadata.title or folder.name
                status = metadata.status
            except Exception:
                date_text, time_text, title, status = "", "", folder.name, "unknown"

            row = self.meeting_table.rowCount()
            self.meeting_table.insertRow(row)
            values = [date_text, time_text, title, status]
            for column, value in enumerate(values):
                item = SortableTableItem(value)
                item.setData(Qt.UserRole, str(folder))
                item.setData(Qt.UserRole + 1, self._meeting_sort_key(column, date_text, time_text, title, status))
                if column in (0, 1):
                    item.setTextAlignment(Qt.AlignCenter)
                self.meeting_table.setItem(row, column, item)

            if current_folder and folder == current_folder:
                self.meeting_table.selectRow(row)

        self.meeting_table.setSortingEnabled(True)
        self.meeting_table.sortItems(0, Qt.DescendingOrder)
        self.meeting_table.resizeColumnsToContents()
        if self.meeting_table.rowCount() and self._selected_meeting_folder() is None:
            self.meeting_table.selectRow(0)

    def preview_selected_meeting(self) -> None:
        self.update_meeting_health()
        self.preview_selected_meeting_file(self.active_preview_file)

    def preview_selected_meeting_file(self, file_name: str) -> None:
        folder = self._selected_meeting_folder()
        if folder is None:
            self.meeting_preview_title.setText("SELECT A MEETING")
            self.meeting_preview.clear()
            return
        self.active_preview_file = file_name
        self.update_meeting_health()
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
        folder = self._selected_meeting_folder()
        if folder is None:
            self.meeting_health.clear()
            return
        try:
            metadata = self.meeting_store.read_metadata(folder)
            self.meeting_health.setPlainText(self._format_health_summary(metadata))
        except Exception as error:
            self.meeting_health.setPlainText(f"Health summary unavailable: {error}")

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
        dialog = ReprocessDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        metadata.status = "processing"
        self.meeting_store.write_metadata(folder, metadata)
        self.meeting_folder = folder
        self.metadata = metadata
        self.start_button.setEnabled(False)
        self.reprocess_button.setEnabled(False)
        self.refresh_meetings_button.setEnabled(False)
        self.open_folder_button.setEnabled(False)
        self.export_html_button.setEnabled(False)
        self.archive_status.setText("Reprocessing selected meeting...")
        self.meeting_preview.setPlainText("Reprocessing selected meeting...")
        self._set_active_nav(2)
        self.log(f"Reprocessing meeting ({dialog.mode}): {folder}")
        self._start_processing(folder, metadata, mode=dialog.mode)

    def copy_current_preview(self) -> None:
        QApplication.clipboard().setText(self.meeting_preview.toPlainText())
        self.log(f"Copied {self.active_preview_file} preview to clipboard.")

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
        document = QTextDocument()
        document.setMarkdown(notes_path.read_text(encoding="utf-8"))
        html_path = folder / "notes.html"
        html_path.write_text(document.toHtml(), encoding="utf-8")
        self.log(f"Exported HTML notes: {html_path}")

    def detect_active_window_title(self) -> None:
        title = self._active_window_title()
        if not title:
            QMessageBox.information(self, "Nova Notetaker", "Could not read the active window title.")
            return
        cleaned = self._clean_window_title(title)
        self.meeting_title.setText(cleaned)
        self.log(f"Detected meeting title: {cleaned}")

    def _selected_meeting_folder(self) -> Path | None:
        if not hasattr(self, "meeting_table"):
            return None
        selected_items = self.meeting_table.selectedItems()
        if not selected_items:
            return None
        raw_path = selected_items[0].data(Qt.UserRole)
        return Path(raw_path) if raw_path else None

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
    def _meeting_sort_key(column: int, date_text: str, time_text: str, title: str, status: str) -> str:
        full_timestamp = f"{date_text} {time_text}".strip()
        if column == 0:
            return full_timestamp
        if column == 1:
            return full_timestamp
        if column == 2:
            return title.lower()
        if column == 3:
            return status.lower()
        return ""

    def _format_health_summary(self, metadata: MeetingMetadata) -> str:
        warnings = metadata.processing.get("warnings", []) if isinstance(metadata.processing, dict) else []
        lines = [
            f"Status: {metadata.status}",
            f"Profile: {self._profile_label(metadata.capture_profile or '')}",
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

        return "\n".join(lines)

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
        title = title.replace(" | Microsoft Teams", "")
        title = title.replace(" - Microsoft Teams", "")
        title = title.replace("Microsoft Teams", "")
        return title.strip(" -|") or "Teams Meeting"

    @Slot(str, float)
    def update_level(self, source: str, level: float) -> None:
        value = int(max(0.0, min(level, 1.0)) * 100)
        if source == "mic":
            self.mic_level.setValue(value)
        elif source == "system":
            self.system_level.setValue(value)

    @Slot(str)
    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.append(f"[{timestamp}] {message}")


def run_app() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
