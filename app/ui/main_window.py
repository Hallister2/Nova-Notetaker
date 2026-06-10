from __future__ import annotations

import hashlib
import os
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QSize, QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QCursor, QDesktopServices, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.audio.device_manager import AudioDevice, AudioDeviceManager
from app.core.profiles import MeetingProfile, ProfileStore
from app.core.settings import load_settings, save_settings, validate_settings
from app.core.templates import NoteTemplate, TemplateStore
from app.intelligence.insights import MeetingInsights
from app.storage.meeting_store import MeetingMetadata, MeetingStore
from app.ui.constants import ASSETS_DIR, EMPTY_ASSETS, NAV_ASSETS
from app.ui.styles import THEME_LABELS, build_stylesheet
from app.ui.widgets import select_combo_by_data
from app.ui.workers import BatchProcessingWorker, CaptureWorker, LiveTranscriptionWorker, ProcessingWorker

from app.ui.tabs.search_tab import SearchTabMixin
from app.ui.tabs.logs_tab import LogsTabMixin
from app.ui.tabs.calendar_tab import CalendarTabMixin
from app.ui.tabs.meetings_tab import MeetingsTabMixin
from app.ui.tabs.review_tab import ReviewTabMixin
from app.ui.tabs.templates_tab import TemplatesTabMixin
from app.ui.tabs.settings_tab import SettingsTabMixin
from app.ui.tabs.capture_tab import CaptureTabMixin
from app.ui.tabs.overview_tab import OverviewTabMixin
from app.core.update_checker import UpdateCheckResult, check_for_updates
from app.ui.toast import ToastManager


class _UpdateCheckWorker(QObject):
    finished = Signal(bool, object, str, bool)  # (ok, result, error, is_manual)

    def __init__(self, manual: bool, timeout: int = 5) -> None:
        super().__init__()
        self._manual = manual
        self._timeout = timeout

    def run(self) -> None:
        try:
            result = check_for_updates(timeout=self._timeout)
        except Exception as exc:
            self.finished.emit(False, None, str(exc), self._manual)
            return
        self.finished.emit(True, result, "", self._manual)


class _DownloadWorker(QObject):
    progress = Signal(int)
    finished = Signal(bool, str)

    _CHUNK = 65_536
    _TIMEOUT = 60

    def __init__(self, url: str, dest: str, checksum_url: str = "", checksum_name: str = "") -> None:
        super().__init__()
        self._url = url
        self._dest = dest
        self._checksum_url = checksum_url
        self._checksum_name = checksum_name

    def run(self) -> None:
        try:
            ctx = ssl.create_default_context()
            self._download_file(self._url, self._dest, ctx, emit_progress=True)
            if not self._checksum_url:
                self.finished.emit(False, "Update verification failed: this release does not include a SHA-256 checksum asset.")
                return
            checksum_path = f"{self._dest}.{self._checksum_name or 'sha256'}"
            self._download_file(self._checksum_url, checksum_path, ctx, emit_progress=False)
            expected = self._expected_sha256(checksum_path, os.path.basename(self._dest))
            actual = self._file_sha256(self._dest)
            if not expected or actual.lower() != expected.lower():
                self.finished.emit(False, "Update verification failed: SHA-256 checksum did not match.")
                return
            signature = self._authenticode_status(self._dest)
            if signature and signature.lower() != "valid":
                self.finished.emit(False, f"Update verification failed: installer signature status is {signature}.")
                return
            detail = "signature valid" if signature else "checksum verified; signature unavailable"
            self.finished.emit(True, f"{self._dest}|{detail}")
        except Exception as exc:
            self.finished.emit(False, str(exc))

    def _download_file(self, url: str, dest: str, ctx: ssl.SSLContext, emit_progress: bool) -> None:
        req = urllib.request.Request(url, headers={"User-Agent": "Nova-Notetaker"})
        with urllib.request.urlopen(req, context=ctx, timeout=self._TIMEOUT) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            with open(dest, "wb") as fh:
                while True:
                    chunk = resp.read(self._CHUNK)
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if emit_progress and total:
                        self.progress.emit(min(100, int(downloaded * 100 / total)))

    @staticmethod
    def _file_sha256(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _expected_sha256(path: str, installer_name: str) -> str:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        hashes = re.findall(r"\b[a-fA-F0-9]{64}\b", text)
        if not hashes:
            return ""
        installer_lower = installer_name.lower()
        for line in text.splitlines():
            if installer_lower in line.lower():
                match = re.search(r"\b[a-fA-F0-9]{64}\b", line)
                if match:
                    return match.group(0)
        return hashes[0] if len(hashes) == 1 else ""

    @staticmethod
    def _authenticode_status(path: str) -> str:
        if sys.platform != "win32":
            return ""
        try:
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"(Get-AuthenticodeSignature -LiteralPath '{path.replace("'", "''")}').Status",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            return completed.stdout.strip()
        except Exception:
            return ""


class MainWindow(
    CaptureTabMixin,
    MeetingsTabMixin,
    OverviewTabMixin,
    ReviewTabMixin,
    SearchTabMixin,
    CalendarTabMixin,
    LogsTabMixin,
    TemplatesTabMixin,
    SettingsTabMixin,
    QMainWindow,
):
    request_worker_start = Signal()
    request_worker_stop = Signal()
    _service_status_changed = Signal(str, str)  # (service_name, status)

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
        self.overview_workspace_folder: Path | None = None
        self.metadata: MeetingMetadata | None = None
        self.worker_thread: QThread | None = None
        self.worker: CaptureWorker | None = None
        self.live_transcription_thread: QThread | None = None
        self.live_transcription_worker: LiveTranscriptionWorker | None = None
        self.live_transcript_rows: list[tuple[str, str, str, bool]] = []
        self.full_live_transcript_rows: list[tuple[str, str, str, bool]] = []
        self.live_tentative_insights = MeetingInsights()
        self.pending_processing_job: tuple[Path, MeetingMetadata, str] | None = None
        self._processing_queue: list[tuple[Path, MeetingMetadata, str]] = []
        self.processing_thread: QThread | None = None
        self.processing_worker: ProcessingWorker | None = None
        self.batch_processing_thread: QThread | None = None
        self.batch_processing_worker: BatchProcessingWorker | None = None
        self.microphones: list[AudioDevice] = []
        self.loopbacks: list[AudioDevice] = []
        self.active_preview_file = "notes.md"
        self.processing_mode = "full"
        self.recording_started_at: datetime | None = None
        self.processing_started_at: datetime | None = None
        self.timer_phase = "idle"
        self.nav_buttons: list[QPushButton] = []
        self.nav_button_labels = ["Live Capture", "Meetings", "Review", "Search", "Calendar", "Logs", "Templates", "Settings"]
        self.compact_nav_labels = ["Live", "Meet", "Review", "Search", "Cal", "Logs", "Tpl", "Set"]
        self.current_responsive_mode = ""
        self.stop_requested = False
        self.meeting_overview_windows: list[QDialog] = []
        self.theme_buttons: dict[str, QPushButton] = {}
        self.current_theme = self.settings.get("app", {}).get("theme", "executive_dark")
        if self.current_theme not in THEME_LABELS:
            self.current_theme = "executive_dark"

        self.setWindowTitle("Nova Notetaker")
        app_icon = self._asset_icon("Nova Notetaker - Icon.png")
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.setMinimumSize(780, 560)
        self.setStyleSheet(build_stylesheet(self.current_theme))
        self._resize_to_available_screen(preferred_width=1440, preferred_height=820)

        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self._update_elapsed_timer)

        self._build_ui()
        self.refresh_devices()
        self.refresh_meetings()
        self.refresh_review_center()

        issues = validate_settings(self.settings)
        for issue in issues:
            self.log(f"[Settings] {issue}")

        self._service_statuses: dict[str, str] = {}
        self._service_status_changed.connect(self._on_service_status_changed)
        self._run_health_checks()

        self._toast = ToastManager(self)
        self._schedule_startup_update_check()

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
        self.overview_workspace_page = self._build_overview_workspace_page()
        self.pages.addWidget(self.overview_workspace_page)
        self.pages.addWidget(self._build_review_queue_page())
        self.pages.addWidget(self._build_search_page())
        self.pages.addWidget(self._build_calendar_page())
        self.pages.addWidget(self._build_logs_page())
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
        from app.ui.orb_widget import OrbWidget
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(240)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 26, 18, 18)
        layout.setSpacing(10)

        self.sidebar_brand = QLabel()
        self.sidebar_brand.setObjectName("Transparent")
        self.sidebar_brand.setPixmap(self._asset_pixmap("Nova Notetaker - Application Logo.png", 178, 52))
        self.sidebar_brand.setMinimumHeight(54)
        layout.addWidget(self.sidebar_brand)
        layout.addSpacing(20)

        for index, label in enumerate(self.nav_button_labels):
            button = QPushButton(label)
            button.setObjectName("SidebarButton")
            button.setProperty("active", "false")
            button.setCursor(Qt.PointingHandCursor)
            button.setIcon(self._nav_icon(index, active=False))
            button.setIconSize(QSize(22, 22))
            stack_index = index if index < 2 else index + 1
            button.clicked.connect(lambda checked=False, page=stack_index: self._set_active_nav(page))
            layout.addWidget(button)
            self.nav_buttons.append(button)

        layout.addStretch()

        layout.addWidget(self._build_theme_toggle())

        status_card = QFrame()
        status_card.setObjectName("Panel")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 14, 16, 14)
        status_layout.setSpacing(8)
        self.sidebar_ready_label = QLabel("Ready")
        self.sidebar_ready_label.setObjectName("GreenText")
        status_layout.addWidget(self.sidebar_ready_label)
        self.sidebar_status_detail_label = self._muted_label("All systems operational")
        status_layout.addWidget(self.sidebar_status_detail_label)
        self.sidebar_processing_progress = QProgressBar()
        self.sidebar_processing_progress.setRange(0, 0)
        self.sidebar_processing_progress.setTextVisible(False)
        self.sidebar_processing_progress.setVisible(False)
        status_layout.addWidget(self.sidebar_processing_progress)
        mini_orb = OrbWidget()
        mini_orb.setFixedSize(118, 118)
        self.orb = mini_orb
        status_layout.addWidget(mini_orb, alignment=Qt.AlignCenter)
        status_layout.addWidget(QLabel("AI Services"))
        self.sidebar_services_label = self._muted_label("Ollama  -  WhisperLive")
        status_layout.addWidget(self.sidebar_services_label)
        layout.addWidget(status_card)
        return sidebar

    # --- Sidebar/profile/template shared helpers (used by capture and templates tabs) ---

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

    # --- Shared layout/UI utilities ---

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
        self.footer_save_label.setMinimumWidth(0)
        self.footer_save_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
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
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    def _field_block(self, label_text: str, control: QWidget) -> QFrame:
        block = QFrame()
        block.setObjectName("SetupFieldBlock")
        block.setMinimumHeight(64)
        block.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        control.setFixedHeight(40)
        control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = self._field_label(label_text)
        label.setFixedHeight(16)
        layout.addWidget(label)
        layout.addWidget(control)
        return block

    def _button_block(self, label_text: str, control: QWidget) -> QFrame:
        block = QFrame()
        block.setObjectName("SetupFieldBlock")
        block.setMinimumHeight(64)
        block.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        control.setFixedHeight(40)
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        if label_text:
            label = self._field_label(label_text)
            label.setFixedHeight(16)
            layout.addWidget(label)
        else:
            layout.addSpacing(22)
        layout.addWidget(control)
        return block

    def _status_badge(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("StatusBadge")
        label.setProperty("state", self._meeting_status_state(text))
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumWidth(130)
        label.setMaximumWidth(156)
        label.setMinimumHeight(26)
        return label

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setFocusPolicy(Qt.NoFocus)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.horizontalHeader().setHighlightSections(False)
        table.verticalHeader().setHighlightSections(False)

    def _asset_path(self, file_name: str) -> Path:
        return ASSETS_DIR / file_name

    def _asset_icon(self, file_name: str) -> QIcon:
        path = self._asset_path(file_name)
        return QIcon(str(path)) if path.exists() else QIcon()

    def _asset_pixmap(self, file_name: str, max_width: int, max_height: int) -> QPixmap:
        path = self._asset_path(file_name)
        pixmap = QPixmap(str(path)) if path.exists() else QPixmap()
        if pixmap.isNull():
            return pixmap
        return pixmap.scaled(max_width, max_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _nav_icon(self, index: int, active: bool) -> QIcon:
        if index < 0 or index >= len(NAV_ASSETS):
            return QIcon()
        default_name, active_name = NAV_ASSETS[index]
        return self._asset_icon(active_name if active else default_name)

    def _empty_state_widget(self, asset_key: str, title: str, detail: str = "") -> QWidget:
        widget = QWidget()
        widget.setObjectName("Transparent")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(18, 24, 18, 24)
        layout.setSpacing(10)
        asset_name = EMPTY_ASSETS.get(asset_key, "")
        image = QLabel()
        image.setAlignment(Qt.AlignCenter)
        image.setPixmap(self._asset_pixmap(asset_name, 180, 180))
        title_label = QLabel(title)
        title_label.setObjectName("PanelTitle")
        title_label.setAlignment(Qt.AlignCenter)
        detail_label = self._muted_label(detail)
        detail_label.setAlignment(Qt.AlignCenter)
        detail_label.setWordWrap(True)
        layout.addStretch()
        layout.addWidget(image)
        layout.addWidget(title_label)
        if detail:
            layout.addWidget(detail_label)
        layout.addStretch()
        return widget

    @staticmethod
    def _muted_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        return label

    def _set_active_nav(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            stack_index = button_index if button_index < 2 else button_index + 1
            is_active = stack_index == index
            button.setProperty("active", "true" if is_active else "false")
            button.setIcon(self._nav_icon(button_index, active=is_active))
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
        if hasattr(self, "_toast"):
            self._toast._reposition()

    def closeEvent(self, event) -> None:
        for dialog in list(self.meeting_overview_windows):
            dialog.close()
        for attr in ("_update_check_thread", "_download_thread"):
            thread = getattr(self, attr, None)
            if thread and thread.isRunning():
                thread.quit()
                thread.wait(1500)
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
        self.sidebar_brand.setVisible(not compact)
        for index, button in enumerate(self.nav_buttons):
            button.setText(self.compact_nav_labels[index] if compact else self.nav_button_labels[index])
            button.setIconSize(QSize(20 if compact else 22, 20 if compact else 22))
        self.sidebar_ready_label.parentWidget().setVisible(show_status)

    @staticmethod
    def _refresh_widget_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def open_settings(self) -> None:
        self._set_active_nav(8)

    # --- Update check ---

    def _on_update_startup_toggled(self, checked: bool) -> None:
        self.settings.setdefault("app", {})["check_for_updates_on_startup"] = checked
        save_settings(self.settings)

    def _schedule_startup_update_check(self) -> None:
        if not bool(self.settings.get("app", {}).get("check_for_updates_on_startup", True)):
            return
        QTimer.singleShot(1500, lambda: self._check_for_updates(manual=False))

    def _check_for_updates(self, manual: bool) -> None:
        thread = getattr(self, "_update_check_thread", None)
        if thread and thread.isRunning():
            if manual:
                self.statusBar().showMessage("Update check already in progress.")
            return
        if manual:
            self.statusBar().showMessage("Checking for updates…")
        self._update_check_thread = QThread(self)
        self._update_check_worker = _UpdateCheckWorker(manual=manual)
        self._update_check_worker.moveToThread(self._update_check_thread)
        self._update_check_thread.started.connect(self._update_check_worker.run)
        self._update_check_worker.finished.connect(self._on_update_check_finished)
        self._update_check_worker.finished.connect(self._update_check_thread.quit)
        self._update_check_thread.finished.connect(self._update_check_worker.deleteLater)
        self._update_check_thread.start()

    def _on_update_check_finished(self, ok: bool, result: object, error: str, is_manual: bool) -> None:
        if is_manual:
            self.statusBar().clearMessage()
        if not ok or result is None:
            if is_manual:
                self._toast.warning(error or "Unable to check for updates.")
            return
        result: UpdateCheckResult
        if not result.release_found:
            if is_manual:
                self._toast.info("No releases published yet.")
            return
        if not result.is_update_available:
            if is_manual:
                self._toast.success(f"Nova Notetaker {result.current_version} is up to date.")
            return
        label = result.release_name or result.latest_version
        if result.download_url:
            self._toast.info_action(
                f"{label} is available.",
                "Download & Install",
                lambda r=result: self._start_update_download(r),
            )
        else:
            self._toast.info_action(
                f"{label} is available.",
                "View Release",
                lambda url=result.release_url: QDesktopServices.openUrl(QUrl(url)),
            )

    def _start_update_download(self, result: UpdateCheckResult) -> None:
        thread = getattr(self, "_download_thread", None)
        if thread and thread.isRunning():
            return
        try:
            dest_dir = tempfile.mkdtemp(prefix="nova_notetaker_update_")
            dest_path = os.path.join(dest_dir, result.asset_name)
        except OSError as exc:
            self._toast.error(f"Could not create temp directory: {exc}")
            return
        self._download_version = result.latest_version
        self._download_thread = QThread(self)
        self._download_worker = _DownloadWorker(
            url=result.download_url,
            dest=dest_path,
            checksum_url=result.checksum_url,
            checksum_name=result.checksum_name,
        )
        self._download_worker.moveToThread(self._download_thread)
        self._download_thread.started.connect(self._download_worker.run)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.finished.connect(self._download_thread.quit)
        self._download_thread.finished.connect(self._download_worker.deleteLater)
        self._download_thread.start()
        self.statusBar().showMessage(f"Downloading Nova Notetaker {result.latest_version}…  0%")

    def _on_download_progress(self, pct: int) -> None:
        version = getattr(self, "_download_version", "")
        self.statusBar().showMessage(f"Downloading Nova Notetaker {version}…  {pct}%")

    def _on_download_finished(self, ok: bool, path_or_error: str) -> None:
        self.statusBar().clearMessage()
        if not ok:
            self._toast.error(f"Download failed: {path_or_error}")
            return
        version = getattr(self, "_download_version", "")
        installer_path, _, verification_detail = path_or_error.partition("|")
        reply = QMessageBox.question(
            self,
            "Install Update",
            f"Nova Notetaker {version} downloaded.\nClose the app and launch the installer now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            os.startfile(installer_path)
            QApplication.quit()


def run_app() -> None:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
