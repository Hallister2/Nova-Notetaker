from __future__ import annotations

import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
import websocket

from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QCursor, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHeaderView,
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
from app.core.profiles import MeetingProfile, ProfileStore
from app.core.settings import load_settings, save_settings
from app.core.templates import NoteTemplate, TemplateStore
from app.intelligence.insights import InsightItem, MeetingInsights, load_or_build_insights, write_insights_json
from app.storage.meeting_store import MeetingMetadata, MeetingStore
from app.ui.orb_widget import OrbWidget
from app.ui.styles import THEME_LABELS, build_stylesheet
from app.workflows.meeting_processor import MeetingProcessor


CAPTURE_PROFILES = {
    "Laptop mic + speakers": "laptop_speakers",
    "External mic + speakers": "external_mic_speakers",
    "Headphones / headset": "headphones",
    "Conference room": "conference_room",
    "Debug / raw capture": "debug_raw",
}

DEFAULT_LOOPBACK_DEVICE = "__default_wasapi_loopback__"
DEFAULT_MIC_DEVICE = "__default_microphone__"


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
    def __init__(
        self,
        parent: QWidget,
        profiles: list[MeetingProfile],
        templates: list[NoteTemplate],
        current_profile_id: str,
        current_template_id: str,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Reprocess Meeting")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        self.notes_only = QRadioButton("Regenerate notes only")
        self.notes_only.setChecked(True)
        self.full = QRadioButton("Full reprocess: transcribe audio and regenerate notes")
        layout.addWidget(self.notes_only)
        layout.addWidget(self.full)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.profile_combo = QComboBox()
        for profile in profiles:
            self.profile_combo.addItem(f"{profile.name} ({profile.category})", profile.id)
        select_combo_by_data(self.profile_combo, current_profile_id)

        self.template_combo = QComboBox()
        for template in templates:
            self.template_combo.addItem(f"{template.name} ({template.category})", template.id)
        select_combo_by_data(self.template_combo, current_template_id)
        form.addRow("Meeting profile", self.profile_combo)
        form.addRow("Note template", self.template_combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def mode(self) -> str:
        return "full" if self.full.isChecked() else "notes_only"

    @property
    def profile_id(self) -> str:
        return str(self.profile_combo.currentData() or "")

    @property
    def template_id(self) -> str:
        return str(self.template_combo.currentData() or "")


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
        self.profile_store = ProfileStore()
        self.meeting_profiles = self.profile_store.list_profiles()
        self.template_store = TemplateStore()
        self.note_templates = self.template_store.list_templates()
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
        self.processing_started_at: datetime | None = None
        self.timer_phase = "idle"
        self.nav_buttons: list[QPushButton] = []
        self.nav_button_labels = ["Live Capture", "Meetings", "Logs", "Templates", "Settings"]
        self.compact_nav_labels = ["Live", "Meet", "Logs", "Tpl", "Set"]
        self.current_responsive_mode = ""
        self.stop_requested = False
        self.meeting_overview_windows: list[QDialog] = []
        self.theme_buttons: dict[str, QPushButton] = {}
        self.current_theme = self.settings.get("app", {}).get("theme", "executive_dark")
        if self.current_theme not in THEME_LABELS:
            self.current_theme = "executive_dark"

        self.setWindowTitle("Nova Notetaker")
        self.setMinimumSize(780, 560)
        self.setStyleSheet(build_stylesheet(self.current_theme))
        self._resize_to_available_screen(preferred_width=1440, preferred_height=820)

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

        header.addLayout(title_block)
        header.addStretch()
        theme_toggle = self._build_theme_toggle()
        header.addWidget(theme_toggle)
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

    def _build_theme_toggle(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for theme_name, label in (
            ("executive_dark", "Dark"),
            ("clean_light", "Light"),
            ("modern_gradient", "Colorful"),
        ):
            button = QPushButton(label)
            button.setObjectName("ThemeButton")
            button.setProperty("active", "false")
            button.clicked.connect(lambda checked=False, selected=theme_name: self.set_theme(selected))
            layout.addWidget(button)
            self.theme_buttons[theme_name] = button
        self._sync_theme_buttons()
        return container

    def _populate_profile_combo(self) -> None:
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        selected_id = self.settings.get("app", {}).get("selected_profile_id", "general")
        for profile in self.meeting_profiles:
            self.profile_combo.addItem(f"{profile.name} ({profile.category})", profile.id)
        select_combo_by_data(self.profile_combo, selected_id)
        self.profile_combo.blockSignals(False)

    def _profile_selection_changed(self) -> None:
        profile = self._selected_meeting_profile()
        self.settings.setdefault("app", {})["selected_profile_id"] = profile.id
        if profile.default_note_template_id and hasattr(self, "template_combo") and self._note_template_exists(profile.default_note_template_id):
            select_combo_by_data(self.template_combo, profile.default_note_template_id)
            self.settings.setdefault("app", {})["selected_template_id"] = profile.default_note_template_id
        save_settings(self.settings)
        self.update_settings_summary()

    def _selected_meeting_profile(self) -> MeetingProfile:
        profile_id = str(self.profile_combo.currentData() or self.settings.get("app", {}).get("selected_profile_id", "general"))
        return self.profile_store.get_profile(profile_id)

    def _populate_template_combo(self) -> None:
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        selected_id = self.settings.get("app", {}).get("selected_template_id", "standard")
        self.note_templates = self.template_store.list_templates()
        for template in self.note_templates:
            self.template_combo.addItem(f"{template.name} ({template.category})", template.id)
        select_combo_by_data(self.template_combo, selected_id)
        self.template_combo.blockSignals(False)

    def _populate_profile_default_template_combo(self, selected_id: str = "") -> None:
        if not hasattr(self, "profile_default_template_combo"):
            return
        self.profile_default_template_combo.blockSignals(True)
        self.profile_default_template_combo.clear()
        self.profile_default_template_combo.addItem("No default - keep current selection", "")
        self.note_templates = self.template_store.list_templates()
        for template in self.note_templates:
            self.profile_default_template_combo.addItem(f"{template.name} ({template.category})", template.id)
        select_combo_by_data(self.profile_default_template_combo, selected_id)
        self.profile_default_template_combo.blockSignals(False)

    def _template_selection_changed(self) -> None:
        template = self._selected_note_template()
        self.settings.setdefault("app", {})["selected_template_id"] = template.id
        save_settings(self.settings)
        self.update_settings_summary()

    def _selected_note_template(self) -> NoteTemplate:
        template_id = str(self.template_combo.currentData() or self.settings.get("app", {}).get("selected_template_id", "standard"))
        return self.template_store.get_template(template_id)

    def _note_template_exists(self, template_id: str) -> bool:
        return any(template.id == template_id for template in self.template_store.list_templates())

    @staticmethod
    def _profile_metadata(profile: MeetingProfile) -> dict[str, str]:
        return {
            "id": profile.id,
            "name": profile.name,
            "category": profile.category,
            "company_conducting": profile.company_conducting,
            "companies_attending": profile.companies_attending,
            "default_meeting_title_prefix": profile.default_meeting_title_prefix,
            "default_note_template_id": profile.default_note_template_id,
            "ai_context": profile.ai_context,
            "notes_focus": profile.notes_focus,
        }

    @staticmethod
    def _template_metadata(template: NoteTemplate) -> dict[str, str]:
        return {
            "id": template.id,
            "name": template.name,
            "category": template.category,
            "description": template.description,
            "notes_focus": template.notes_focus,
            "custom_instructions": template.custom_instructions,
            "preferred_sections": template.preferred_sections,
        }

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
        self.profile_combo = QComboBox()
        self._populate_profile_combo()
        self.profile_combo.currentIndexChanged.connect(self._profile_selection_changed)
        self.template_combo = QComboBox()
        self._populate_template_combo()
        self.template_combo.currentIndexChanged.connect(self._template_selection_changed)
        title_stack.addWidget(self.meeting_title)
        title_stack.addWidget(self._muted_label("Meeting profile"))
        title_stack.addWidget(self.profile_combo)
        title_stack.addWidget(self._muted_label("Note template"))
        title_stack.addWidget(self.template_combo)
        title_stack.addWidget(self.detect_title_button, alignment=Qt.AlignLeft)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("GreenText")
        self.elapsed_label = QLabel("00:00:00")
        self.elapsed_label.setObjectName("StatValue")
        self.status_detail_label = self._muted_label("Waiting to start")
        self.orb_caption = self.status_detail_label
        self.capture_mic_toggle = QCheckBox("Capture microphone")
        self.capture_mic_toggle.setObjectName("MicToggle")
        self.capture_mic_toggle.setChecked(bool(self.settings["audio"].get("capture_mic", True)))
        self.capture_mic_toggle.toggled.connect(self._save_capture_mic_toggle)
        self._sync_mic_toggle_label()
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
        self.recording_button = QPushButton("Start Recording")
        self.recording_button.setObjectName("PrimaryButton")
        self.recording_button.clicked.connect(self.toggle_capture)
        self.start_button = self.recording_button
        self.stop_button = self.recording_button
        self.add_note_button = QPushButton("Add Note")
        self.add_note_button.setEnabled(False)
        layout.addWidget(self.mark_important_button)
        layout.addWidget(self.recording_button, stretch=1)
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
        action_card, self.live_action_items_layout = self._insight_card("Action items", self.action_items_count, ["Waiting for notes generation"])
        decision_card, self.live_decisions_layout = self._insight_card("Key decisions", self.decisions_count, ["Waiting for notes generation"])
        dates_card, self.live_dates_layout = self._insight_card("Dates detected", self.dates_count, ["Waiting for notes generation"])
        layout.addWidget(action_card)
        layout.addWidget(decision_card)
        layout.addWidget(dates_card)
        layout.addStretch()
        return panel

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
        link = QLabel(f"View all {title.lower()}")
        link.setObjectName("OrangeText")
        layout.addWidget(link, alignment=Qt.AlignRight)
        return card, items_layout

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
        self.meeting_table = QTableWidget(0, 7)
        self.meeting_table.setHorizontalHeaderLabels(["Date", "Time", "Meeting Name", "Status", "Actions", "Review", "Open"])
        self.meeting_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.meeting_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.meeting_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.meeting_table.setSortingEnabled(True)
        self.meeting_table.verticalHeader().setVisible(False)
        header = self.meeting_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        self.meeting_table.setColumnWidth(6, 150)
        filters = QHBoxLayout()
        self.meeting_filter_combo = QComboBox()
        self.meeting_filter_combo.addItems(["All meetings", "Needs review", "Has open actions", "Processed", "No transcript"])
        self.meeting_filter_combo.currentIndexChanged.connect(self.refresh_meetings)
        filters.addWidget(QLabel("Filter"))
        filters.addWidget(self.meeting_filter_combo)
        filters.addStretch()
        archive_buttons = QHBoxLayout()
        self.refresh_meetings_button = QPushButton("Refresh")
        self.refresh_meetings_button.clicked.connect(self.refresh_meetings)
        self.reprocess_button = QPushButton("Reprocess")
        self.reprocess_button.clicked.connect(self.reprocess_selected_meeting)
        self.open_folder_button = QPushButton("Open folder")
        self.open_folder_button.clicked.connect(self.open_selected_meeting_folder)
        self.export_html_button = QPushButton("Export HTML")
        self.export_html_button.clicked.connect(self.export_selected_notes_html)
        self.delete_meeting_button = QPushButton("Delete selected")
        self.delete_meeting_button.clicked.connect(self.delete_selected_meetings)
        for button in (
            self.refresh_meetings_button,
            self.reprocess_button,
            self.open_folder_button,
            self.export_html_button,
            self.delete_meeting_button,
        ):
            archive_buttons.addWidget(button)
        self.archive_status = self._muted_label("Ready")
        meetings_panel_layout.addWidget(meetings_title)
        meetings_panel_layout.addLayout(filters)
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
        page = QWidget()
        layout = QVBoxLayout(page)
        self.templates_page_layout = layout
        layout.setContentsMargins(34, 28, 18, 28)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        self.templates_content_layout = content_layout
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        title = QLabel("Templates")
        title.setObjectName("Title")
        content_layout.addWidget(title)
        content_layout.addWidget(self._muted_label("Edit meeting profiles for context and note templates for output style."))

        content_layout.addWidget(self._build_meeting_profiles_section())
        content_layout.addWidget(self._build_note_templates_section())
        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.active_profile_id = ""
        self.active_template_id = ""
        self.refresh_profiles_table()
        self.refresh_templates_table()
        return page

    def _build_meeting_profiles_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("Panel")
        layout = QGridLayout(section)
        self.profile_section_layout = layout
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        list_panel = QWidget()
        self.profile_list_panel = list_panel
        list_panel.setObjectName("Transparent")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(8)
        title = QLabel("Meeting profiles")
        title.setObjectName("PanelTitle")
        list_layout.addWidget(title)
        list_layout.addWidget(self._muted_label("Profiles tell Nova what kind of meeting this is and what context matters."))

        self.profiles_table = QTableWidget(0, 2)
        self.profiles_table.setHorizontalHeaderLabels(["Profile", "Category"])
        self.profiles_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.profiles_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.profiles_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.profiles_table.verticalHeader().setVisible(False)
        self.profiles_table.horizontalHeader().setStretchLastSection(True)
        self.profiles_table.setMinimumHeight(125)
        self.profiles_table.itemSelectionChanged.connect(self._profile_row_selected)
        list_layout.addWidget(self.profiles_table, stretch=1)

        list_buttons = QHBoxLayout()
        self.new_profile_button = QPushButton("New profile")
        self.new_profile_button.clicked.connect(self.new_profile)
        self.delete_profile_button = QPushButton("Delete")
        self.delete_profile_button.clicked.connect(self.delete_profile)
        list_buttons.addWidget(self.new_profile_button)
        list_buttons.addWidget(self.delete_profile_button)
        list_layout.addLayout(list_buttons)

        editor_panel = QWidget()
        self.profile_editor_panel = editor_panel
        editor_panel.setObjectName("Transparent")
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        editor_title = QLabel("Profile editor")
        editor_title.setObjectName("SectionTitle")
        editor_layout.addWidget(editor_title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(7)
        self.profile_name_edit = QLineEdit()
        self.profile_category_edit = QLineEdit()
        self.profile_company_conducting_edit = QLineEdit()
        self.profile_companies_attending_edit = QLineEdit()
        self.profile_title_prefix_edit = QLineEdit()
        self.profile_default_template_combo = QComboBox()
        self._populate_profile_default_template_combo()
        self.profile_context_edit = QTextEdit()
        self.profile_context_edit.setMaximumHeight(74)
        self.profile_focus_edit = QTextEdit()
        self.profile_focus_edit.setMaximumHeight(74)
        form.addRow("Name", self.profile_name_edit)
        form.addRow("Category", self.profile_category_edit)
        form.addRow("Company conducting", self.profile_company_conducting_edit)
        form.addRow("Companies attending", self.profile_companies_attending_edit)
        form.addRow("Title prefix", self.profile_title_prefix_edit)
        form.addRow("Default note template", self.profile_default_template_combo)
        form.addRow("AI context", self.profile_context_edit)
        form.addRow("Notes focus", self.profile_focus_edit)
        editor_layout.addLayout(form)

        save_row = QHBoxLayout()
        self.save_profile_button = QPushButton("Save profile")
        self.save_profile_button.setObjectName("PrimaryButton")
        self.save_profile_button.clicked.connect(self.save_profile)
        save_row.addStretch()
        save_row.addWidget(self.save_profile_button)
        editor_layout.addLayout(save_row)

        layout.addWidget(list_panel, 0, 0)
        layout.addWidget(editor_panel, 0, 1)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 2)
        return section

    def _build_note_templates_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("Panel")
        layout = QGridLayout(section)
        self.template_section_layout = layout
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        list_panel = QWidget()
        self.template_list_panel = list_panel
        list_panel.setObjectName("Transparent")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(8)
        title = QLabel("Note templates")
        title.setObjectName("PanelTitle")
        list_layout.addWidget(title)
        list_layout.addWidget(self._muted_label("Templates control the generated notes structure, tone, and preferred sections."))

        self.templates_table = QTableWidget(0, 2)
        self.templates_table.setHorizontalHeaderLabels(["Template", "Category"])
        self.templates_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.templates_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.templates_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.templates_table.verticalHeader().setVisible(False)
        self.templates_table.horizontalHeader().setStretchLastSection(True)
        self.templates_table.setMinimumHeight(125)
        self.templates_table.itemSelectionChanged.connect(self._template_row_selected)
        list_layout.addWidget(self.templates_table, stretch=1)

        list_buttons = QHBoxLayout()
        self.new_template_button = QPushButton("New template")
        self.new_template_button.clicked.connect(self.new_template)
        self.delete_template_button = QPushButton("Delete")
        self.delete_template_button.clicked.connect(self.delete_template)
        list_buttons.addWidget(self.new_template_button)
        list_buttons.addWidget(self.delete_template_button)
        list_layout.addLayout(list_buttons)

        editor_panel = QWidget()
        self.template_editor_panel = editor_panel
        editor_panel.setObjectName("Transparent")
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        editor_title = QLabel("Template editor")
        editor_title.setObjectName("SectionTitle")
        editor_layout.addWidget(editor_title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(7)
        self.template_name_edit = QLineEdit()
        self.template_category_edit = QLineEdit()
        self.template_description_edit = QLineEdit()
        self.template_sections_edit = QLineEdit()
        self.template_focus_edit = QTextEdit()
        self.template_focus_edit.setMaximumHeight(72)
        self.template_custom_edit = QTextEdit()
        self.template_custom_edit.setMaximumHeight(86)
        form.addRow("Name", self.template_name_edit)
        form.addRow("Category", self.template_category_edit)
        form.addRow("Description", self.template_description_edit)
        form.addRow("Preferred sections", self.template_sections_edit)
        form.addRow("Notes focus", self.template_focus_edit)
        form.addRow("Custom instructions", self.template_custom_edit)
        editor_layout.addLayout(form)

        save_row = QHBoxLayout()
        self.save_template_button = QPushButton("Save template")
        self.save_template_button.setObjectName("PrimaryButton")
        self.save_template_button.clicked.connect(self.save_template)
        save_row.addStretch()
        save_row.addWidget(self.save_template_button)
        editor_layout.addLayout(save_row)

        layout.addWidget(list_panel, 0, 0)
        layout.addWidget(editor_panel, 0, 1)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 2)
        return section

    def refresh_profiles_table(self, selected_id: str | None = None) -> None:
        self.meeting_profiles = self.profile_store.list_profiles()
        target_id = selected_id or self.active_profile_id or self.settings.get("app", {}).get("selected_profile_id", "general")

        self.profiles_table.blockSignals(True)
        self.profiles_table.setRowCount(0)
        selected_row = 0
        for row, profile in enumerate(self.meeting_profiles):
            self.profiles_table.insertRow(row)
            name_item = QTableWidgetItem(profile.name)
            name_item.setData(Qt.UserRole, profile.id)
            category_item = QTableWidgetItem(profile.category)
            category_item.setData(Qt.UserRole, profile.id)
            self.profiles_table.setItem(row, 0, name_item)
            self.profiles_table.setItem(row, 1, category_item)
            if profile.id == target_id:
                selected_row = row
        self.profiles_table.blockSignals(False)

        if self.meeting_profiles:
            self.profiles_table.selectRow(selected_row)
            self._load_profile_into_editor(self.meeting_profiles[selected_row])
        else:
            self.active_profile_id = ""
            self._clear_profile_editor()

    def _profile_row_selected(self) -> None:
        selected = self.profiles_table.selectedItems()
        if not selected:
            return
        profile_id = str(selected[0].data(Qt.UserRole) or "")
        for profile in self.meeting_profiles:
            if profile.id == profile_id:
                self._load_profile_into_editor(profile)
                return

    def _load_profile_into_editor(self, profile: MeetingProfile) -> None:
        self.active_profile_id = profile.id
        self.profile_name_edit.setText(profile.name)
        self.profile_category_edit.setText(profile.category)
        self.profile_company_conducting_edit.setText(profile.company_conducting)
        self.profile_companies_attending_edit.setText(profile.companies_attending)
        self.profile_title_prefix_edit.setText(profile.default_meeting_title_prefix)
        select_combo_by_data(self.profile_default_template_combo, profile.default_note_template_id)
        self.profile_context_edit.setPlainText(profile.ai_context)
        self.profile_focus_edit.setPlainText(profile.notes_focus)

    def _clear_profile_editor(self) -> None:
        self.profile_name_edit.clear()
        self.profile_category_edit.setText("General Meeting")
        self.profile_company_conducting_edit.clear()
        self.profile_companies_attending_edit.clear()
        self.profile_title_prefix_edit.clear()
        select_combo_by_data(self.profile_default_template_combo, "")
        self.profile_context_edit.clear()
        self.profile_focus_edit.clear()

    def new_profile(self) -> None:
        self.profiles_table.clearSelection()
        self.active_profile_id = ""
        self._clear_profile_editor()
        self.profile_name_edit.setText("New Profile")
        self.profile_name_edit.setFocus()
        self.profile_name_edit.selectAll()

    def save_profile(self) -> None:
        name = self.profile_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Nova Notetaker", "Profile name is required.")
            return

        existing_ids = {profile.id for profile in self.meeting_profiles}
        profile_id = self.active_profile_id or self.profile_store.make_id(name, existing_ids)
        profile = MeetingProfile(
            id=profile_id,
            name=name,
            category=self.profile_category_edit.text().strip() or "General Meeting",
            company_conducting=self.profile_company_conducting_edit.text().strip(),
            companies_attending=self.profile_companies_attending_edit.text().strip(),
            default_meeting_title_prefix=self.profile_title_prefix_edit.text().strip(),
            default_note_template_id=str(self.profile_default_template_combo.currentData() or ""),
            ai_context=self.profile_context_edit.toPlainText().strip(),
            notes_focus=self.profile_focus_edit.toPlainText().strip(),
        )

        profiles = [item for item in self.meeting_profiles if item.id != profile_id]
        profiles.append(profile)
        profiles.sort(key=lambda item: (item.category.lower(), item.name.lower()))
        self.profile_store.write_profiles(profiles)
        self.meeting_profiles = self.profile_store.list_profiles()
        self.settings.setdefault("app", {})["selected_profile_id"] = profile.id
        save_settings(self.settings)
        self._populate_profile_combo()
        select_combo_by_data(self.profile_combo, profile.id)
        self.refresh_profiles_table(profile.id)
        self.update_settings_summary()
        self.log(f"Saved meeting profile: {profile.name}")

    def delete_profile(self) -> None:
        if not self.active_profile_id:
            return
        if len(self.meeting_profiles) <= 1:
            QMessageBox.warning(self, "Nova Notetaker", "At least one meeting profile must remain.")
            return
        profile = next((item for item in self.meeting_profiles if item.id == self.active_profile_id), None)
        if profile is None:
            return

        response = QMessageBox.question(
            self,
            "Delete Meeting Profile",
            f"Delete the meeting profile '{profile.name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if response != QMessageBox.Yes:
            return

        remaining = [item for item in self.meeting_profiles if item.id != profile.id]
        self.profile_store.write_profiles(remaining)
        selected_id = remaining[0].id
        if self.settings.get("app", {}).get("selected_profile_id") == profile.id:
            self.settings.setdefault("app", {})["selected_profile_id"] = selected_id
            save_settings(self.settings)
        self._populate_profile_combo()
        select_combo_by_data(self.profile_combo, self.settings.get("app", {}).get("selected_profile_id", selected_id))
        self.refresh_profiles_table(selected_id)
        self.update_settings_summary()
        self.log(f"Deleted meeting profile: {profile.name}")

    def refresh_templates_table(self, selected_id: str | None = None) -> None:
        self.note_templates = self.template_store.list_templates()
        target_id = selected_id or self.active_template_id or self.settings.get("app", {}).get("selected_template_id", "standard")

        self.templates_table.blockSignals(True)
        self.templates_table.setRowCount(0)
        selected_row = 0
        for row, template in enumerate(self.note_templates):
            self.templates_table.insertRow(row)
            name_item = QTableWidgetItem(template.name)
            name_item.setData(Qt.UserRole, template.id)
            category_item = QTableWidgetItem(template.category)
            category_item.setData(Qt.UserRole, template.id)
            self.templates_table.setItem(row, 0, name_item)
            self.templates_table.setItem(row, 1, category_item)
            if template.id == target_id:
                selected_row = row
        self.templates_table.blockSignals(False)

        if self.note_templates:
            self.templates_table.selectRow(selected_row)
            self._load_template_into_editor(self.note_templates[selected_row])
        else:
            self.active_template_id = ""
            self._clear_template_editor()

    def _template_row_selected(self) -> None:
        selected = self.templates_table.selectedItems()
        if not selected:
            return
        template_id = str(selected[0].data(Qt.UserRole) or "")
        for template in self.note_templates:
            if template.id == template_id:
                self._load_template_into_editor(template)
                return

    def _load_template_into_editor(self, template: NoteTemplate) -> None:
        self.active_template_id = template.id
        self.template_name_edit.setText(template.name)
        self.template_category_edit.setText(template.category)
        self.template_description_edit.setText(template.description)
        self.template_sections_edit.setText(template.preferred_sections)
        self.template_focus_edit.setPlainText(template.notes_focus)
        self.template_custom_edit.setPlainText(template.custom_instructions)

    def _clear_template_editor(self) -> None:
        self.template_name_edit.clear()
        self.template_category_edit.setText("General")
        self.template_description_edit.clear()
        self.template_sections_edit.setText("Summary, Key Decisions, Action Items, Important Dates, Risks / Blockers, Follow-ups")
        self.template_focus_edit.clear()
        self.template_custom_edit.clear()

    def new_template(self) -> None:
        self.templates_table.clearSelection()
        self.active_template_id = ""
        self._clear_template_editor()
        self.template_name_edit.setText("New Template")
        self.template_name_edit.setFocus()
        self.template_name_edit.selectAll()

    def save_template(self) -> None:
        name = self.template_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Nova Notetaker", "Template name is required.")
            return

        existing_ids = {template.id for template in self.note_templates}
        template_id = self.active_template_id or self.template_store.make_id(name, existing_ids)
        template = NoteTemplate(
            id=template_id,
            name=name,
            category=self.template_category_edit.text().strip() or "General",
            description=self.template_description_edit.text().strip(),
            notes_focus=self.template_focus_edit.toPlainText().strip(),
            custom_instructions=self.template_custom_edit.toPlainText().strip(),
            preferred_sections=self.template_sections_edit.text().strip()
            or "Summary, Key Decisions, Action Items, Important Dates, Risks / Blockers, Follow-ups",
        )

        templates = [item for item in self.note_templates if item.id != template_id]
        templates.append(template)
        templates.sort(key=lambda item: (item.category.lower(), item.name.lower()))
        self.template_store.write_templates(templates)
        self.note_templates = self.template_store.list_templates()
        self.settings.setdefault("app", {})["selected_template_id"] = template.id
        save_settings(self.settings)
        self._populate_template_combo()
        self._populate_profile_default_template_combo()
        select_combo_by_data(self.template_combo, template.id)
        self.refresh_templates_table(template.id)
        self.update_settings_summary()
        self.log(f"Saved note template: {template.name}")

    def delete_template(self) -> None:
        if not self.active_template_id:
            return
        if len(self.note_templates) <= 1:
            QMessageBox.warning(self, "Nova Notetaker", "At least one template must remain.")
            return
        template = next((item for item in self.note_templates if item.id == self.active_template_id), None)
        if template is None:
            return

        response = QMessageBox.question(
            self,
            "Delete Template",
            f"Delete the template '{template.name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if response != QMessageBox.Yes:
            return

        remaining = [item for item in self.note_templates if item.id != template.id]
        self.template_store.write_templates(remaining)
        selected_id = remaining[0].id
        if self.settings.get("app", {}).get("selected_template_id") == template.id:
            self.settings.setdefault("app", {})["selected_template_id"] = selected_id
            save_settings(self.settings)
        self._populate_template_combo()
        self._populate_profile_default_template_combo()
        select_combo_by_data(self.template_combo, self.settings.get("app", {}).get("selected_template_id", selected_id))
        self.refresh_templates_table(selected_id)
        self.update_settings_summary()
        self.log(f"Deleted note template: {template.name}")

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 28, 18, 28)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setMinimumHeight(760)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 20)
        panel_layout.setSpacing(16)

        title = QLabel("Settings")
        title.setObjectName("Title")
        panel_layout.addWidget(title)
        panel_layout.addWidget(self._muted_label("Device, capture, WhisperLive, and Ollama settings."))

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)

        self.settings_mic_combo = QComboBox()
        self.settings_loopback_combo = QComboBox()
        self.settings_profile_combo = QComboBox()
        for label, value in CAPTURE_PROFILES.items():
            self.settings_profile_combo.addItem(label, value)
        select_combo_by_data(self.settings_profile_combo, self.settings["audio"].get("capture_profile", "laptop_speakers"))

        self.settings_provider_combo = QComboBox()
        self.settings_provider_combo.addItems(["ollama", "openai"])
        self.settings_provider_combo.setCurrentText(self.settings["ai"].get("provider", "ollama"))
        self.settings_ollama_url = QLineEdit(self.settings["ai"].get("ollama_url", ""))
        self.settings_ollama_model = QLineEdit(self.settings["ai"].get("ollama_model", ""))
        self.settings_ai_timeout = QSpinBox()
        self.settings_ai_timeout.setRange(10, 1800)
        self.settings_ai_timeout.setValue(int(self.settings["ai"].get("timeout_seconds", 180)))

        self.settings_transcription_enabled = QCheckBox("WhisperLive enabled")
        self.settings_transcription_enabled.setChecked(bool(self.settings["transcription"].get("enabled", False)))
        self.settings_whisper_url = QLineEdit(self.settings["transcription"].get("whisperlive_url", ""))
        self.settings_whisper_model = QLineEdit(self.settings["transcription"].get("model", "small"))
        self.settings_whisper_language = QLineEdit(self.settings["transcription"].get("language", "en"))
        self.settings_use_vad = QCheckBox("Use VAD")
        self.settings_use_vad.setChecked(bool(self.settings["transcription"].get("use_vad", True)))
        self.settings_cross_bleed_cleanup = QCheckBox("Speaker-bleed cleanup")
        self.settings_cross_bleed_cleanup.setChecked(bool(self.settings["transcription"].get("cross_bleed_cleanup", True)))
        self.settings_transcription_timeout = QSpinBox()
        self.settings_transcription_timeout.setRange(10, 1800)
        self.settings_transcription_timeout.setValue(int(self.settings["transcription"].get("timeout_seconds", 120)))
        self.settings_long_audio_chunk_seconds = QSpinBox()
        self.settings_long_audio_chunk_seconds.setRange(60, 600)
        self.settings_long_audio_chunk_seconds.setValue(int(self.settings["transcription"].get("long_audio_chunk_seconds", 180)))

        for control in (
            self.settings_mic_combo,
            self.settings_loopback_combo,
            self.settings_profile_combo,
            self.settings_provider_combo,
            self.settings_ollama_url,
            self.settings_ollama_model,
            self.settings_ai_timeout,
            self.settings_transcription_enabled,
            self.settings_whisper_url,
            self.settings_whisper_model,
            self.settings_whisper_language,
            self.settings_use_vad,
            self.settings_cross_bleed_cleanup,
            self.settings_transcription_timeout,
            self.settings_long_audio_chunk_seconds,
        ):
            control.setMinimumHeight(36)

        self.settings_ollama_model.setPlaceholderText("Example: llama3.1:latest")
        self.settings_whisper_model.setPlaceholderText("Example: small")
        self.settings_whisper_language.setPlaceholderText("Example: en")
        self.settings_ollama_url.setPlaceholderText("Example: http://192.168.200.2:11434")
        self.settings_whisper_url.setPlaceholderText("Example: http://192.168.200.2:9090")

        form.addRow("Microphone", self._setting_with_hint(self.settings_mic_combo, "Use Windows default unless you need to force a specific input device."))
        form.addRow("System audio", self._setting_with_hint(self.settings_loopback_combo, "Use Windows default output for the most portable Teams/browser/audio setup."))
        form.addRow("Capture profile", self._setting_with_hint(self.settings_profile_combo, "Tunes cleanup behavior for laptop speakers, headphones, conference rooms, or debug capture."))
        form.addRow("AI provider", self._setting_with_hint(self.settings_provider_combo, "Ollama is currently wired for local note generation. OpenAI is reserved for a later provider pass."))
        form.addRow("Ollama URL", self._setting_with_hint(self.settings_ollama_url, "Base URL for your Ollama server. Use the same address you use for Ollama API calls."))
        form.addRow("Ollama model", self._setting_with_hint(self.settings_ollama_model, "Any installed Ollama model name works here. Run `ollama list` on the Ollama host to see available models."))
        form.addRow("AI timeout", self._setting_with_hint(self.settings_ai_timeout, "Maximum seconds to wait for notes generation before Nova treats it as failed."))
        form.addRow("WhisperLive", self._setting_with_hint(self.settings_transcription_enabled, "Turn this on to transcribe audio with your WhisperLive server during processing."))
        form.addRow("WhisperLive URL", self._setting_with_hint(self.settings_whisper_url, "Base URL for WhisperLive. Nova converts http/https to the matching WebSocket connection."))
        form.addRow("Whisper model", self._setting_with_hint(self.settings_whisper_model, "Common values are tiny, base, small, medium, and large-v3. Availability depends on your WhisperLive container/config. Check the container logs or startup command for enabled/default model behavior."))
        form.addRow("Whisper language", self._setting_with_hint(self.settings_whisper_language, "Use ISO-style language codes such as en. Leave as en for English meetings."))
        form.addRow("Voice activity detection", self._setting_with_hint(self.settings_use_vad, "Helps WhisperLive ignore silence and non-speech. Usually leave enabled."))
        form.addRow("Transcript cleanup", self._setting_with_hint(self.settings_cross_bleed_cleanup, "Reduces duplicate mic/system bleed and repeated transcript fragments before notes generation."))
        form.addRow("Transcription timeout", self._setting_with_hint(self.settings_transcription_timeout, "Maximum seconds to wait for each WhisperLive transcription request."))
        form.addRow("Long recording chunk size", self._setting_with_hint(self.settings_long_audio_chunk_seconds, "Long recordings are split into chunks before WhisperLive. Lower this if long meetings disconnect; 120-180 seconds is a good range."))
        panel_layout.addLayout(form)

        button_row = QHBoxLayout()
        self.settings_refresh_devices_button = QPushButton("Refresh devices")
        self.settings_refresh_devices_button.clicked.connect(self.refresh_devices)
        self.settings_test_ollama_button = QPushButton("Test Ollama")
        self.settings_test_ollama_button.clicked.connect(self.test_ollama_connection)
        self.settings_test_whisper_button = QPushButton("Test WhisperLive")
        self.settings_test_whisper_button.clicked.connect(self.test_whisperlive_connection)
        self.settings_button = QPushButton("Save settings")
        self.settings_button.setObjectName("PrimaryButton")
        self.settings_button.clicked.connect(self.save_settings_page)
        button_row.addWidget(self.settings_refresh_devices_button)
        button_row.addWidget(self.settings_test_ollama_button)
        button_row.addWidget(self.settings_test_whisper_button)
        button_row.addStretch()
        button_row.addWidget(self.settings_button)
        panel_layout.addLayout(button_row)
        panel_layout.addStretch()

        scroll.setWidget(panel)
        layout.addWidget(scroll)
        return page

    def _setting_with_hint(self, control: QWidget, hint: str) -> QWidget:
        container = QWidget()
        container.setObjectName("Transparent")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        hint_label = self._muted_label(hint)
        hint_label.setWordWrap(True)
        control.setToolTip(hint)
        layout.addWidget(control)
        layout.addWidget(hint_label)
        return container

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

    def set_theme(self, theme_name: str) -> None:
        if theme_name not in THEME_LABELS:
            theme_name = "executive_dark"
        self.current_theme = theme_name
        self.settings.setdefault("app", {})["theme"] = theme_name
        save_settings(self.settings)
        self.setStyleSheet(build_stylesheet(theme_name))
        self._sync_theme_buttons()
        for dialog in list(self.meeting_overview_windows):
            dialog.setStyleSheet(build_stylesheet(theme_name))

    def _sync_theme_buttons(self) -> None:
        for theme_name, button in self.theme_buttons.items():
            button.setProperty("active", "true" if theme_name == self.current_theme else "false")
            button.style().unpolish(button)
            button.style().polish(button)

    def _resize_to_available_screen(self, preferred_width: int, preferred_height: int) -> None:
        screen = QApplication.primaryScreen()
        if not screen:
            self.resize(preferred_width, preferred_height)
            return
        available = screen.availableGeometry()
        max_width = int(available.width() * 0.92)
        max_height = int(available.height() * 0.88)
        width = min(max(self.minimumWidth(), min(preferred_width, max_width)), available.width())
        height = min(max(self.minimumHeight(), min(preferred_height, max_height)), available.height())
        self.resize(width, height)
        x = available.x() + max(0, (available.width() - width) // 2)
        y = available.y() + max(0, (available.height() - height) // 2)
        self.move(x, y)

    @staticmethod
    def _fit_dialog_to_available_screen(dialog: QDialog, preferred_width: int, preferred_height: int) -> None:
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if not screen:
            dialog.resize(preferred_width, preferred_height)
            return
        available = screen.availableGeometry()
        max_width = int(available.width() * 0.90)
        max_height = int(available.height() * 0.86)
        width = min(max(dialog.minimumWidth(), min(preferred_width, max_width)), available.width())
        height = min(max(dialog.minimumHeight(), min(preferred_height, max_height)), available.height())
        dialog.resize(width, height)
        x = available.x() + max(0, (available.width() - width) // 2)
        y = available.y() + max(0, (available.height() - height) // 2)
        dialog.move(x, y)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())

    def closeEvent(self, event) -> None:
        for dialog in list(self.meeting_overview_windows):
            dialog.close()
        super().closeEvent(event)

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
        self._apply_templates_responsive(mode)

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
        if mode == "narrow":
            self.meetings_layout.setContentsMargins(16, 18, 12, 18)
        else:
            self.meetings_layout.setContentsMargins(28 if mode == "compact" else 34, 28, 18, 28)

    def _apply_templates_responsive(self, mode: str) -> None:
        if not hasattr(self, "profile_section_layout"):
            return

        if mode == "narrow":
            margins = (16, 18, 12, 18)
            section_margins = (12, 12, 12, 12)
            spacing = 10
            stack_sections = True
        elif mode == "compact":
            margins = (22, 22, 14, 22)
            section_margins = (12, 12, 12, 12)
            spacing = 12
            stack_sections = True
        elif mode == "medium":
            margins = (28, 24, 16, 24)
            section_margins = (14, 14, 14, 14)
            spacing = 14
            stack_sections = False
        else:
            margins = (34, 28, 18, 28)
            section_margins = (14, 14, 14, 14)
            spacing = 14
            stack_sections = False

        self.templates_page_layout.setContentsMargins(*margins)
        self.templates_content_layout.setSpacing(spacing)
        for section_layout in (self.profile_section_layout, self.template_section_layout):
            section_layout.setContentsMargins(*section_margins)
            section_layout.setSpacing(spacing)

        if stack_sections:
            self.profile_section_layout.addWidget(self.profile_list_panel, 0, 0)
            self.profile_section_layout.addWidget(self.profile_editor_panel, 1, 0)
            self.profile_section_layout.setColumnStretch(0, 1)
            self.profile_section_layout.setColumnStretch(1, 0)
            self.template_section_layout.addWidget(self.template_list_panel, 0, 0)
            self.template_section_layout.addWidget(self.template_editor_panel, 1, 0)
            self.template_section_layout.setColumnStretch(0, 1)
            self.template_section_layout.setColumnStretch(1, 0)
        else:
            self.profile_section_layout.addWidget(self.profile_list_panel, 0, 0)
            self.profile_section_layout.addWidget(self.profile_editor_panel, 0, 1)
            self.profile_section_layout.setColumnStretch(0, 1)
            self.profile_section_layout.setColumnStretch(1, 2)
            self.template_section_layout.addWidget(self.template_list_panel, 0, 0)
            self.template_section_layout.addWidget(self.template_editor_panel, 0, 1)
            self.template_section_layout.setColumnStretch(0, 1)
            self.template_section_layout.setColumnStretch(1, 2)

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

    def _set_insight_items(self, layout: QVBoxLayout, items: list[str | InsightItem]) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for item_text in items[:5] or ["None detected yet"]:
            if isinstance(item_text, InsightItem):
                layout.addWidget(self._insight_item_widget(item_text))
            else:
                layout.addWidget(self._muted_label(f"- {item_text}"))

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
            badge_values.append((item.due_date, "date"))
            badge_values.append((item.status, "state"))
        elif item.kind == "date":
            badge_values.append((item.due_date, "date"))
        badge_values.append((item.confidence, f"confidence-{item.confidence.lower()}"))
        for value, kind in badge_values:
            if not value:
                continue
            badges.addWidget(self._badge_label(value, kind))
        if item.kind == "date":
            calendar_button = QPushButton("Calendar later")
            calendar_button.setObjectName("SubtleActionButton")
            calendar_button.setEnabled(False)
            calendar_button.setToolTip("Calendar integration is planned for a later pass.")
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

    def _update_insight_group(
        self,
        count_label: QLabel,
        items_layout: QVBoxLayout,
        items: list[str | InsightItem],
    ) -> None:
        count_label.setText(str(len(items)))
        self._set_insight_items(items_layout, items)

    def _update_live_insights_from_folder(self, folder: Path) -> None:
        insights = load_or_build_insights(folder)
        self._update_insight_group(self.action_items_count, self.live_action_items_layout, insights.actions)
        self._update_insight_group(self.decisions_count, self.live_decisions_layout, insights.decisions)
        self._update_insight_group(self.dates_count, self.live_dates_layout, insights.dates)

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
        if self.timer_phase == "recording":
            started_at = self.recording_started_at
        elif self.timer_phase == "processing":
            started_at = self.processing_started_at
        else:
            started_at = None

        if not started_at:
            self.elapsed_label.setText("00:00:00")
            return
        elapsed = datetime.now() - started_at
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
            QMessageBox.warning(self, "Nova Notetaker", "Select a microphone in Settings before starting capture.")
            return

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
            mic_sample_rate=(mic_device.sample_rate if mic_device else None) or 48000,
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
        self.recording_button.setEnabled(True)
        self.recording_button.setText("Stop Recording")
        self.recording_button.setObjectName("DangerButton")
        self._refresh_widget_style(self.recording_button)
        self.settings_button.setEnabled(False)
        self.capture_mic_toggle.setEnabled(False)
        self.reprocess_button.setEnabled(False)
        self.recording_started_at = datetime.now()
        self.processing_started_at = None
        self.timer_phase = "recording"
        self.elapsed_timer.start(1000)
        self._update_elapsed_timer()
        self.orb.set_state("recording")
        self.status_label.setObjectName("RedText")
        self.status_label.setText("Recording")
        self._refresh_widget_style(self.status_label)
        self.orb_caption.setText("Recording time")
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

    def stop_capture(self) -> None:
        if not self.worker:
            return
        if self.stop_requested:
            return
        self.stop_requested = True
        self.recording_button.setEnabled(False)
        self.recording_button.setText("Stopping...")
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
        if self.recording_started_at:
            recording_seconds = max(0, int((datetime.now() - self.recording_started_at).total_seconds()))
            hours, remainder = divmod(recording_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.log(f"Recording duration: {hours:02}:{minutes:02}:{seconds:02}")
        self.recording_button.setEnabled(False)
        self.recording_button.setText("Processing...")
        self.orb.set_state("processing")
        self.status_label.setText("Processing")
        self.orb_caption.setText("Processing time")
        self.processing_started_at = datetime.now()
        self.timer_phase = "processing"
        self.elapsed_label.setText("00:00:00")
        self.elapsed_timer.start(1000)
        self._update_elapsed_timer()

        if self.metadata and self.meeting_folder:
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
    def _capture_channels(device: AudioDevice | None, default: int) -> int:
        if device is None or device.channels <= 0:
            return default
        return min(device.channels, 2)

    def open_settings(self) -> None:
        self._set_active_nav(4)

    def _populate_settings_device_controls(self) -> None:
        if not hasattr(self, "settings_mic_combo"):
            return
        mic_value = self.settings["audio"].get("mic_device_name", "")
        loopback_value = self.settings["audio"].get("system_loopback_device_name", "")
        self.settings_mic_combo.blockSignals(True)
        self.settings_loopback_combo.blockSignals(True)
        self.settings_mic_combo.clear()
        self.settings_mic_combo.addItem("Windows default microphone", DEFAULT_MIC_DEVICE)
        for device in self.microphones:
            self.settings_mic_combo.addItem(device.label, device.name)
        self.settings_loopback_combo.clear()
        self.settings_loopback_combo.addItem("Windows default output", DEFAULT_LOOPBACK_DEVICE)
        self.settings_loopback_combo.addItem("None", "")
        for device in self.loopbacks:
            self.settings_loopback_combo.addItem(device.label, device.name)
        self.settings_mic_combo.blockSignals(False)
        self.settings_loopback_combo.blockSignals(False)
        select_combo_by_data(self.settings_mic_combo, mic_value or DEFAULT_MIC_DEVICE)
        select_combo_by_data(self.settings_loopback_combo, loopback_value or DEFAULT_LOOPBACK_DEVICE)

    def save_settings_page(self) -> None:
        self.settings["audio"]["mic_device_name"] = str(self.settings_mic_combo.currentData() or "")
        self.settings["audio"]["system_loopback_device_name"] = str(self.settings_loopback_combo.currentData() or "")
        self.settings["audio"]["capture_profile"] = str(self.settings_profile_combo.currentData() or "external_mic_speakers")
        self.settings["ai"]["provider"] = self.settings_provider_combo.currentText()
        self.settings["ai"]["ollama_url"] = self.settings_ollama_url.text().strip()
        self.settings["ai"]["ollama_model"] = self.settings_ollama_model.text().strip()
        self.settings["ai"]["timeout_seconds"] = self.settings_ai_timeout.value()
        self.settings["transcription"]["enabled"] = self.settings_transcription_enabled.isChecked()
        self.settings["transcription"]["whisperlive_url"] = self.settings_whisper_url.text().strip()
        self.settings["transcription"]["model"] = self.settings_whisper_model.text().strip()
        self.settings["transcription"]["language"] = self.settings_whisper_language.text().strip()
        self.settings["transcription"]["use_vad"] = self.settings_use_vad.isChecked()
        self.settings["transcription"]["cross_bleed_cleanup"] = self.settings_cross_bleed_cleanup.isChecked()
        self.settings["transcription"]["timeout_seconds"] = self.settings_transcription_timeout.value()
        self.settings["transcription"]["long_audio_chunk_seconds"] = self.settings_long_audio_chunk_seconds.value()
        save_settings(self.settings)
        self.update_settings_summary()
        self.log("Settings saved.")

    def test_ollama_connection(self) -> None:
        url = self.settings_ollama_url.text().strip().rstrip("/")
        model = self.settings_ollama_model.text().strip()
        if not url:
            QMessageBox.warning(self, "Nova Notetaker", "Enter an Ollama URL before testing.")
            return
        try:
            response = requests.get(f"{url}/api/tags", timeout=8)
            response.raise_for_status()
            models = [item.get("name", "") for item in response.json().get("models", []) if isinstance(item, dict)]
            model_message = f"Model found: {model}" if model in models else f"Model not found: {model}"
            if not model:
                model_message = "No model selected."
            QMessageBox.information(
                self,
                "Ollama Test",
                f"Ollama is reachable.\n{model_message}\n\nAvailable models:\n{', '.join(models[:12]) or 'None reported'}",
            )
            self.log(f"Ollama test succeeded. {model_message}")
        except Exception as error:
            QMessageBox.warning(self, "Ollama Test", f"Ollama test failed:\n{error}")
            self.log(f"Ollama test failed: {error}")

    def test_whisperlive_connection(self) -> None:
        url = self.settings_whisper_url.text().strip().rstrip("/")
        if not url:
            QMessageBox.warning(self, "Nova Notetaker", "Enter a WhisperLive URL before testing.")
            return
        try:
            parsed = urlparse(url)
            scheme = "wss" if parsed.scheme == "https" else "ws"
            host = parsed.hostname or url.replace("http://", "").replace("https://", "")
            port = parsed.port or (443 if scheme == "wss" else 80)
            ws_url = f"{scheme}://{host}:{port}"
            ws = websocket.create_connection(ws_url, timeout=8)
            ws.close()
            QMessageBox.information(self, "WhisperLive Test", f"WhisperLive WebSocket is reachable.\n{ws_url}")
            self.log(f"WhisperLive test succeeded: {ws_url}")
        except Exception as error:
            QMessageBox.warning(self, "WhisperLive Test", f"WhisperLive test failed:\n{error}")
            self.log(f"WhisperLive test failed: {error}")

    def update_settings_summary(self) -> None:
        mic_setting = self.settings["audio"].get("mic_device_name", "") or DEFAULT_MIC_DEVICE
        mic_name = "Windows default microphone" if mic_setting == DEFAULT_MIC_DEVICE else mic_setting or "No microphone selected"
        system_setting = self.settings["audio"].get("system_loopback_device_name", "") or DEFAULT_LOOPBACK_DEVICE
        system_name = "Windows default output" if system_setting == DEFAULT_LOOPBACK_DEVICE else system_setting or "No system audio selected"
        profile = self._profile_label(self.settings["audio"].get("capture_profile", ""))
        meeting_profile_name = self._selected_meeting_profile().name if hasattr(self, "profile_combo") else "General Meeting"
        template_name = self._selected_note_template().name if hasattr(self, "template_combo") else "Standard Meeting Notes"
        provider = self.settings["ai"].get("provider", "ollama")
        whisper = "on" if self.settings["transcription"].get("enabled", False) else "off"
        mic_state = "on" if self.settings["audio"].get("capture_mic", True) else "muted"
        self.settings_summary.setText(
            f"Mic {mic_state}  |  System: {system_name}  |  Audio: {profile}  |  Meeting: {meeting_profile_name}  |  Template: {template_name}  |  {provider} / WhisperLive {whisper}"
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
        if self.timer_phase != "processing":
            self.processing_started_at = datetime.now()
            self.timer_phase = "processing"
            self.elapsed_label.setText("00:00:00")
            self.elapsed_timer.start(1000)
            self._update_elapsed_timer()
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
        self.capture_mic_toggle.setEnabled(True)
        self.elapsed_timer.stop()
        self.timer_phase = "idle"
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
        if processing_seconds:
            hours, remainder = divmod(processing_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.orb_caption.setText(f"Processing completed in {hours:02}:{minutes:02}:{seconds:02}")
        else:
            self.orb_caption.setText("Waiting to start")
        if self.meeting_folder:
            self.log(f"Processing complete. Notes: {self.meeting_folder / 'notes.md'}")
            self._refresh_live_transcript_from_file()
            self._update_live_insights_from_folder(self.meeting_folder)
        if hasattr(self, "archive_status"):
            self.archive_status.setText("Processing complete")
        self.refresh_meetings()

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
            except Exception:
                metadata = None
                date_text, time_text, title, status = "", "", folder.name, "unknown"

            open_actions = sum(1 for item in insights.actions if item.status.lower() != "done")
            review_count = len(insights.quality_warnings) + len(insights.warnings)
            if not self._meeting_matches_filter(folder, metadata, status, open_actions, review_count):
                continue

            row = self.meeting_table.rowCount()
            self.meeting_table.insertRow(row)
            values = [date_text, time_text, title, self._meeting_status_label(status, review_count), str(open_actions), str(review_count)]
            for column, value in enumerate(values):
                item = SortableTableItem(value)
                item.setData(Qt.UserRole, str(folder))
                item.setData(Qt.UserRole + 1, self._meeting_sort_key(column, date_text, time_text, title, status, open_actions, review_count))
                if column in (0, 1):
                    item.setTextAlignment(Qt.AlignCenter)
                if column in (4, 5):
                    item.setTextAlignment(Qt.AlignCenter)
                self.meeting_table.setItem(row, column, item)

            open_button = QPushButton("Open")
            open_button.setText("Open meeting")
            open_button.setObjectName("TableActionButton")
            open_button.setFixedSize(128, 28)
            open_button.setToolTip("Open this meeting overview")
            open_button.clicked.connect(lambda checked=False, meeting_folder=folder: self.open_meeting_overview(meeting_folder))
            open_item = SortableTableItem("")
            open_item.setData(Qt.UserRole, str(folder))
            open_item.setData(Qt.UserRole + 1, "")
            self.meeting_table.setItem(row, 6, open_item)
            self.meeting_table.setCellWidget(row, 6, open_button)
            self.meeting_table.setRowHeight(row, 38)

            if current_folder and folder == current_folder:
                self.meeting_table.selectRow(row)

        self.meeting_table.setSortingEnabled(True)
        self.meeting_table.sortItems(0, Qt.DescendingOrder)
        self.meeting_table.setColumnWidth(6, 150)
        if self.meeting_table.rowCount() and self._selected_meeting_folder() is None:
            self.meeting_table.selectRow(0)

    def _meeting_matches_filter(
        self,
        folder: Path,
        metadata: MeetingMetadata | None,
        status: str,
        open_actions: int,
        review_count: int,
    ) -> bool:
        selected_filter = self.meeting_filter_combo.currentText() if hasattr(self, "meeting_filter_combo") else "All meetings"
        if selected_filter == "Needs review":
            return review_count > 0
        if selected_filter == "Has open actions":
            return open_actions > 0
        if selected_filter == "Processed":
            return status.startswith("processed")
        if selected_filter == "No transcript":
            transcript_path = folder / "transcript.md"
            if not transcript_path.exists():
                return True
            transcript_text = transcript_path.read_text(encoding="utf-8", errors="ignore")
            return not MeetingProcessor._usable_existing_transcript_text(transcript_text).strip()
        return True

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
        export_button = QPushButton("Export HTML")
        export_button.clicked.connect(lambda: self._export_notes_html_for_folder(folder))
        header.addWidget(open_folder_button)
        header.addWidget(export_button)
        layout.addLayout(header)

        content = QGridLayout()
        content.setSpacing(16)

        notes_panel = QFrame()
        notes_panel.setObjectName("Panel")
        notes_layout = QVBoxLayout(notes_panel)
        notes_layout.setContentsMargins(18, 18, 18, 18)
        notes_layout.addWidget(self._section_label("Notes"))
        notes_view = QTextEdit()
        notes_view.setReadOnly(True)
        notes_path = folder / "notes.md"
        if notes_path.exists():
            notes_view.setMarkdown(self._notes_for_display(notes_path))
        else:
            notes_view.setPlainText("notes.md has not been created yet.")
        notes_layout.addWidget(notes_view, stretch=1)

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
        details_layout.addWidget(self._section_label("Meeting details"))
        health = QTextEdit()
        health.setReadOnly(True)
        health.setMaximumHeight(170)
        health.setPlainText(self._format_health_summary(metadata))
        details_layout.addWidget(health)

        insights = load_or_build_insights(folder)
        if insights.quality_warnings:
            warning_card = QFrame()
            warning_card.setObjectName("RaisedPanel")
            warning_layout = QVBoxLayout(warning_card)
            warning_layout.setContentsMargins(14, 12, 14, 12)
            warning_layout.addWidget(self._section_label("Review needed"))
            for warning in insights.quality_warnings[:4]:
                warning_layout.addWidget(self._muted_label(f"- {warning}"))
            details_layout.addWidget(warning_card)

        details_layout.addWidget(self._overview_action_items_card(folder, insights))
        for title_text, items in (
            ("Key decisions", insights.decisions),
            ("Scheduling details", insights.dates),
        ):
            count_label = QLabel(str(len(items)))
            card, _items_layout = self._insight_card(title_text, count_label, items or ["None detected"])
            details_layout.addWidget(card)
        details_layout.addStretch()
        details_scroll.setWidget(details_panel)

        content.addWidget(notes_panel, 0, 0)
        content.addWidget(details_scroll, 0, 1)
        content.setColumnStretch(0, 2)
        content.setColumnStretch(1, 1)
        layout.addLayout(content, stretch=1)
        self._fit_dialog_to_available_screen(dialog, preferred_width=1180, preferred_height=760)
        dialog.show()

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
            status_combo.addItems(["open", "in progress", "done", "deferred"])
            status_combo.setCurrentText(item.status or "open")
            status_combo.setToolTip("Update action item status")
            status_combo.currentTextChanged.connect(
                lambda status, action_index=index, meeting_folder=folder: self._update_action_status(meeting_folder, action_index, status)
            )
            row.layout().addWidget(status_combo)
            layout.addWidget(row)
        return card

    def _update_action_status(self, folder: Path, action_index: int, status: str) -> None:
        insights = load_or_build_insights(folder)
        if action_index >= len(insights.actions):
            return
        insights.actions[action_index].status = status
        write_insights_json(folder, insights)
        self.refresh_meetings()
        self.log(f"Updated action status to {status}: {folder.name}")

    @staticmethod
    def _notes_for_display(notes_path: Path) -> str:
        text = notes_path.read_text(encoding="utf-8")
        text = re.sub(r";\s*Source:\s*<span[^>]*>[^<]+</span>", "", text)
        text = re.sub(r";\s*Source:\s*[^;\n]+", "", text)
        text = re.sub(r"\bSource:\s*<span[^>]*>[^<]+</span>;?\s*", "", text)
        text = re.sub(r"\bSource:\s*[^;\n]+;?\s*", "", text)
        return text

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
        self.refresh_meetings_button.setEnabled(False)
        self.open_folder_button.setEnabled(False)
        self.export_html_button.setEnabled(False)
        self.archive_status.setText("Reprocessing selected meeting...")
        if hasattr(self, "meeting_preview"):
            self.meeting_preview.setPlainText("Reprocessing selected meeting...")
        self._set_active_nav(1)
        self.log(
            f"Reprocessing meeting ({dialog.mode}) with {meeting_profile.name} / {note_template.name}: {folder}"
        )
        self._start_processing(folder, metadata, mode=dialog.mode)

    def copy_current_preview(self) -> None:
        if not hasattr(self, "meeting_preview"):
            return
        QApplication.clipboard().setText(self.meeting_preview.toPlainText())
        self.log(f"Copied {self.active_preview_file} preview to clipboard.")

    def open_selected_meeting_folder(self) -> None:
        folder = self._selected_meeting_folder()
        if folder is None:
            QMessageBox.information(self, "Nova Notetaker", "Select a meeting to open.")
            return
        os.startfile(folder)

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
                shutil.rmtree(resolved)
                deleted += 1
            except Exception as error:
                skipped.append(f"{folder.name}: {error}")

        self.log(f"Deleted {deleted} {noun}.")
        if skipped:
            self.log(f"Skipped {len(skipped)} meeting(s): {'; '.join(skipped)}")
            QMessageBox.warning(self, "Nova Notetaker", f"Deleted {deleted}, skipped {len(skipped)}. See Logs for details.")
        self.refresh_meetings()

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
    def _meeting_status_label(status: str, review_count: int) -> str:
        if review_count:
            return f"{status} / needs review"
        return status

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
