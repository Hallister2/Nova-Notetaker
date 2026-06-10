from __future__ import annotations

import os
from urllib.parse import urlparse

import requests
import websocket

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QComboBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.glossary import (
    load_correction_pairs, load_glossary_terms,
    save_correction_pairs, save_glossary_terms,
)
from app.core.audio_profiles import AUDIO_PROFILES_PATH, load_audio_profiles
from app.core.preflight import run_capture_preflight_checks, summarize_preflight
from app.core.settings import LOGS_DIR, SETTINGS_PATH, USER_DATA_DIR, save_settings, validate_settings
from app.storage.privacy import apply_retention_policy
from app.ui.constants import CAPTURE_PROFILES, DEFAULT_LOOPBACK_DEVICE, DEFAULT_MIC_DEVICE
from app.ui.widgets import select_combo_by_data

_PROVIDER_OPTIONS = [
    ("Ollama (local)", "ollama"),
    ("OpenAI / ChatGPT", "openai"),
    ("Claude (Anthropic)", "claude"),
]


class SettingsTabMixin:
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
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 20)
        panel_layout.setSpacing(16)

        title = QLabel("Settings")
        title.setObjectName("Title")
        panel_layout.addWidget(title)
        panel_layout.addWidget(self._muted_label("Device, capture, transcription, and AI intelligence settings."))

        self.settings_mic_combo = QComboBox()
        self.settings_loopback_combo = QComboBox()
        self.settings_profile_combo = QComboBox()
        for label, value in CAPTURE_PROFILES.items():
            self.settings_profile_combo.addItem(label, value)
        select_combo_by_data(self.settings_profile_combo, self.settings["audio"].get("capture_profile", "laptop_speakers"))

        # AI provider combo (data-driven so stored value stays lowercase)
        self.settings_provider_combo = QComboBox()
        for label, value in _PROVIDER_OPTIONS:
            self.settings_provider_combo.addItem(label, value)
        current_provider = self.settings["ai"].get("provider", "ollama")
        select_combo_by_data(self.settings_provider_combo, current_provider)

        # Ollama fields
        self.settings_ollama_url = QLineEdit(self.settings["ai"].get("ollama_url", ""))
        self.settings_ollama_url.setPlaceholderText("Example: http://192.168.200.2:11434")
        self.settings_ollama_model = QLineEdit(self.settings["ai"].get("ollama_model", ""))
        self.settings_ollama_model.setPlaceholderText("Example: llama3.1:latest")

        # OpenAI fields
        self.settings_openai_api_key = QLineEdit(self.settings["ai"].get("openai_api_key", ""))
        self.settings_openai_api_key.setPlaceholderText("sk-...")
        self.settings_openai_api_key.setEchoMode(QLineEdit.Password)
        self.settings_openai_model = QLineEdit(self.settings["ai"].get("openai_model", "gpt-4o"))
        self.settings_openai_model.setPlaceholderText("Example: gpt-4o")

        # Claude fields
        self.settings_claude_api_key = QLineEdit(self.settings["ai"].get("claude_api_key", ""))
        self.settings_claude_api_key.setPlaceholderText("sk-ant-...")
        self.settings_claude_api_key.setEchoMode(QLineEdit.Password)
        self.settings_claude_model = QLineEdit(self.settings["ai"].get("claude_model", "claude-opus-4-5"))
        self.settings_claude_model.setPlaceholderText("Example: claude-opus-4-5")

        # Shared AI field
        self.settings_ai_timeout = QSpinBox()
        self.settings_ai_timeout.setRange(10, 1800)
        self.settings_ai_timeout.setValue(int(self.settings["ai"].get("timeout_seconds", 180)))

        self.settings_action_auto_close_days = QSpinBox()
        self.settings_action_auto_close_days.setRange(0, 3650)
        self.settings_action_auto_close_days.setValue(int(self.settings.get("review", {}).get("action_auto_close_days", 30)))

        self.settings_transcription_enabled = QCheckBox("WhisperLive enabled")
        self.settings_transcription_enabled.setChecked(bool(self.settings["transcription"].get("enabled", False)))
        self.settings_whisper_url = QLineEdit(self.settings["transcription"].get("whisperlive_url", ""))
        self.settings_whisper_url.setPlaceholderText("Example: http://192.168.200.2:9090")
        self.settings_whisper_model = QLineEdit(self.settings["transcription"].get("model", "small"))
        self.settings_whisper_model.setPlaceholderText("Example: small")
        self.settings_whisper_language = QLineEdit(self.settings["transcription"].get("language", "en"))
        self.settings_whisper_language.setPlaceholderText("Example: en")
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
        storage_settings = self.settings.setdefault("storage", {})
        self.settings_meetings_dir = QLineEdit(str(storage_settings.get("meetings_dir", "Meetings")))
        self.settings_browse_meetings_button = QPushButton("Browse")
        self.settings_browse_meetings_button.clicked.connect(self.browse_meetings_dir)
        self.settings_archive_wav_to_flac = QCheckBox("Compress WAV to FLAC after processing")
        self.settings_archive_wav_to_flac.setChecked(bool(storage_settings.get("archive_wav_to_flac", True)))
        self.settings_delete_raw_audio = QCheckBox("Delete raw audio after processing")
        self.settings_delete_raw_audio.setChecked(bool(storage_settings.get("delete_raw_audio_after_processing", False)))
        self.settings_notes_only_archive = QCheckBox("Notes-only archive")
        self.settings_notes_only_archive.setChecked(bool(storage_settings.get("notes_only_archive", False)))
        self.settings_retention_days = QSpinBox()
        self.settings_retention_days.setRange(0, 3650)
        self.settings_retention_days.setValue(int(storage_settings.get("retention_days", 0)))
        self.settings_apply_retention_button = QPushButton("Apply retention now")
        self.settings_apply_retention_button.clicked.connect(self.apply_retention_now)

        for control in (
            self.settings_mic_combo,
            self.settings_loopback_combo,
            self.settings_profile_combo,
            self.settings_provider_combo,
            self.settings_ollama_url,
            self.settings_ollama_model,
            self.settings_openai_api_key,
            self.settings_openai_model,
            self.settings_claude_api_key,
            self.settings_claude_model,
            self.settings_ai_timeout,
            self.settings_action_auto_close_days,
            self.settings_transcription_enabled,
            self.settings_whisper_url,
            self.settings_whisper_model,
            self.settings_whisper_language,
            self.settings_use_vad,
            self.settings_cross_bleed_cleanup,
            self.settings_transcription_timeout,
            self.settings_long_audio_chunk_seconds,
            self.settings_meetings_dir,
            self.settings_archive_wav_to_flac,
            self.settings_delete_raw_audio,
            self.settings_notes_only_archive,
            self.settings_retention_days,
        ):
            control.setMinimumHeight(36)

        settings_tabs = QTabWidget()
        settings_tabs.addTab(
            self._settings_section(
                [
                    ("Microphone", self._setting_with_hint(self.settings_mic_combo, "Use Windows default unless you need to force a specific input device.")),
                    ("System audio", self._setting_with_hint(self.settings_loopback_combo, "Use Windows default output for the most portable Teams/browser/audio setup.")),
                    ("Capture profile", self._setting_with_hint(self.settings_profile_combo, "Tunes cleanup behavior for laptop speakers, headphones, conference rooms, or debug capture.", visible=True)),
                ]
            ),
            "Device capture",
        )
        settings_tabs.addTab(self._build_intelligence_tab(), "Intelligence")
        settings_tabs.addTab(
            self._settings_section(
                [
                    ("Action auto-close", self._setting_with_hint(self.settings_action_auto_close_days, "Automatically marks aging open actions as closed after this many days from the meeting date. Set to 0 to disable.", visible=True)),
                ]
            ),
            "Review",
        )
        settings_tabs.addTab(
            self._settings_section(
                [
                    ("WhisperLive", self._setting_with_hint(self.settings_transcription_enabled, "Turn this on to stream live transcript during recording and generate final transcripts with WhisperLive.")),
                    ("WhisperLive URL", self._setting_with_hint(self.settings_whisper_url, "Base URL for WhisperLive. Nova converts http/https to the matching WebSocket connection.")),
                    ("Whisper model", self._setting_with_hint(self.settings_whisper_model, "Common values are tiny, base, small, medium, and large-v3. Availability depends on your WhisperLive container/config.", visible=True)),
                    ("Whisper language", self._setting_with_hint(self.settings_whisper_language, "Use ISO-style language codes such as en. Leave as en for English meetings.")),
                    ("Voice activity detection", self._setting_with_hint(self.settings_use_vad, "Helps WhisperLive ignore silence and non-speech. Usually leave enabled.")),
                    ("Transcript cleanup", self._setting_with_hint(self.settings_cross_bleed_cleanup, "Reduces duplicate mic/system bleed and repeated transcript fragments before notes generation.")),
                    ("Transcription timeout", self._setting_with_hint(self.settings_transcription_timeout, "Maximum seconds to wait for each WhisperLive transcription request.")),
                    ("Long recording chunk size", self._setting_with_hint(self.settings_long_audio_chunk_seconds, "Long recordings are split into chunks before WhisperLive. Lower this if long meetings disconnect; 120-180 seconds is a good range.", visible=True)),
                ]
            ),
            "Transcription",
        )
        settings_tabs.addTab(self._build_storage_tab(), "Storage & Privacy")
        settings_tabs.addTab(self._build_glossary_tab(), "Glossary")
        settings_tabs.addTab(self._build_diagnostics_tab(), "Diagnostics")
        settings_tabs.addTab(self._build_updates_tab(), "Updates")
        panel_layout.addWidget(settings_tabs, stretch=1)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        self.settings_refresh_devices_button = QPushButton("Refresh devices")
        self.settings_refresh_devices_button.clicked.connect(self.refresh_devices)
        self.settings_preflight_button = QPushButton("Run preflight")
        self.settings_preflight_button.clicked.connect(self.run_capture_preflight)
        self.settings_test_whisper_button = QPushButton("Test WhisperLive")
        self.settings_test_whisper_button.clicked.connect(self.test_whisperlive_connection)
        self.settings_button = QPushButton("Save settings")
        self.settings_button.setObjectName("PrimaryButton")
        self.settings_button.clicked.connect(self.save_settings_page)
        for button in (
            self.settings_refresh_devices_button,
            self.settings_preflight_button,
            self.settings_test_whisper_button,
            self.settings_button,
        ):
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button_row.addWidget(self.settings_refresh_devices_button)
        button_row.addWidget(self.settings_preflight_button)
        button_row.addWidget(self.settings_test_whisper_button)
        button_row.addStretch()
        button_row.addWidget(self.settings_button)
        panel_layout.addLayout(button_row)
        panel_layout.addStretch()

        scroll.setWidget(panel)
        layout.addWidget(scroll)
        return page

    def _build_intelligence_tab(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("Transparent")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Provider selector — always visible
        provider_form = QFrame()
        provider_form.setObjectName("FormSection")
        provider_fl = QFormLayout(provider_form)
        provider_fl.setContentsMargins(0, 0, 0, 0)
        provider_fl.setLabelAlignment(Qt.AlignLeft)
        provider_fl.setHorizontalSpacing(18)
        provider_fl.setVerticalSpacing(10)
        provider_fl.addRow("AI provider", self._setting_with_hint(
            self.settings_provider_combo,
            "Choose your AI backend for generating meeting notes. Each provider needs its own credentials or server URL.",
            visible=True,
        ))
        layout.addWidget(provider_form)

        # --- Ollama section ---
        self._ollama_section = self._provider_section([
            ("Ollama URL", self._setting_with_hint(self.settings_ollama_url, "Base URL for your Ollama server.")),
            ("Ollama model", self._setting_with_hint(self.settings_ollama_model, "Run `ollama list` on the Ollama host to see installed models.", visible=True)),
        ], test_label="Test Ollama", test_slot=self.test_ollama_connection)
        layout.addWidget(self._ollama_section)

        # --- OpenAI section ---
        self._openai_section = self._provider_section([
            ("API key", self._setting_with_hint(self.settings_openai_api_key, "Your OpenAI API key (starts with sk-). Stored locally in settings.json.")),
            ("Model", self._setting_with_hint(self.settings_openai_model, "Model name, e.g. gpt-4o, gpt-4-turbo, gpt-3.5-turbo.", visible=True)),
        ], test_label="Test OpenAI", test_slot=self.test_openai_connection)
        layout.addWidget(self._openai_section)

        # --- Claude section ---
        self._claude_section = self._provider_section([
            ("API key", self._setting_with_hint(self.settings_claude_api_key, "Your Anthropic API key (starts with sk-ant-). Stored locally in settings.json.")),
            ("Model", self._setting_with_hint(self.settings_claude_model, "Model name, e.g. claude-opus-4-5, claude-sonnet-4-6, claude-haiku-4-5.", visible=True)),
        ], test_label="Test Claude", test_slot=self.test_claude_connection)
        layout.addWidget(self._claude_section)

        # Shared timeout — always visible
        timeout_form = QFrame()
        timeout_form.setObjectName("FormSection")
        timeout_fl = QFormLayout(timeout_form)
        timeout_fl.setContentsMargins(0, 0, 0, 0)
        timeout_fl.setLabelAlignment(Qt.AlignLeft)
        timeout_fl.setHorizontalSpacing(18)
        timeout_fl.setVerticalSpacing(10)
        timeout_fl.addRow("AI timeout (s)", self._setting_with_hint(
            self.settings_ai_timeout,
            "Maximum seconds to wait for notes generation before Nova treats it as failed.",
        ))
        layout.addWidget(timeout_form)
        layout.addStretch()

        self._apply_provider_visibility(self.settings_provider_combo.currentData() or "ollama")
        self.settings_provider_combo.currentIndexChanged.connect(
            lambda _: self._apply_provider_visibility(self.settings_provider_combo.currentData() or "ollama")
        )
        return widget

    def _provider_section(self, rows: list[tuple[str, QWidget]], test_label: str, test_slot) -> QFrame:
        frame = QFrame()
        frame.setObjectName("FormSection")
        fl = QFormLayout(frame)
        fl.setContentsMargins(0, 8, 0, 8)
        fl.setLabelAlignment(Qt.AlignLeft)
        fl.setHorizontalSpacing(18)
        fl.setVerticalSpacing(10)
        for label, control in rows:
            fl.addRow(label, control)
        test_button = QPushButton(test_label)
        test_button.setMinimumHeight(36)
        test_button.clicked.connect(test_slot)
        fl.addRow("", test_button)
        return frame

    def _apply_provider_visibility(self, provider: str) -> None:
        self._ollama_section.setVisible(provider == "ollama")
        self._openai_section.setVisible(provider == "openai")
        self._claude_section.setVisible(provider == "claude")

    def _build_storage_tab(self) -> QWidget:
        location_layout = QHBoxLayout()
        location_layout.setContentsMargins(0, 0, 0, 0)
        location_layout.setSpacing(8)
        location_layout.addWidget(self.settings_meetings_dir, stretch=1)
        location_layout.addWidget(self.settings_browse_meetings_button)
        location_widget = QWidget()
        location_widget.setLayout(location_layout)
        return self._settings_section(
            [
                ("Meeting data location", self._setting_with_hint(location_widget, "Folder used for recordings, transcripts, notes, insights, and indexes.")),
                ("Compress audio", self._setting_with_hint(self.settings_archive_wav_to_flac, "Converts WAV files to FLAC after processing to reduce storage while preserving reprocess capability.")),
                ("Delete raw audio", self._setting_with_hint(self.settings_delete_raw_audio, "Deletes mic/system audio artifacts after processing. Notes and transcripts remain unless notes-only archive is enabled.")),
                ("Notes-only archive", self._setting_with_hint(self.settings_notes_only_archive, "Keeps notes, transcript, metadata, insights, markers, and review state; removes audio and transient artifacts.")),
                ("Retention days", self._setting_with_hint(self.settings_retention_days, "Automatically remove meetings older than this many days. Set to 0 to keep meetings indefinitely.", visible=True)),
                ("", self.settings_apply_retention_button),
            ]
        )

    def _build_diagnostics_tab(self) -> QWidget:
        self.settings_log_location_label = self._muted_label(str(LOGS_DIR))
        self.settings_log_location_label.setWordWrap(True)
        latest_meetings = self.meeting_store.list_meetings()
        latest_meeting = latest_meetings[0] if latest_meetings else None
        self.settings_latest_meeting_label = self._muted_label(str(latest_meeting) if latest_meeting else "No meetings found")
        self.settings_latest_meeting_label.setWordWrap(True)
        self.settings_audio_profiles_label = self._muted_label(self._audio_profiles_summary())
        self.settings_audio_profiles_label.setWordWrap(True)
        self.settings_open_logs_button = QPushButton("Open logs folder")
        self.settings_open_logs_button.clicked.connect(self.open_logs_folder)
        self.settings_copy_diagnostics_button = QPushButton("Copy diagnostics")
        self.settings_copy_diagnostics_button.clicked.connect(self.copy_diagnostics_summary)
        return self._settings_section(
            [
                ("Runtime logs", self.settings_log_location_label),
                ("Latest meeting", self.settings_latest_meeting_label),
                ("Audio profiles", self.settings_audio_profiles_label),
                ("", self.settings_open_logs_button),
                ("", self.settings_copy_diagnostics_button),
            ]
        )
    def _build_glossary_tab(self) -> QWidget:
        from PySide6.QtWidgets import QSplitter, QTextEdit
        widget = QWidget()
        widget.setObjectName("Transparent")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        splitter = QSplitter(Qt.Vertical)

        # --- Terms pane ---
        terms_frame = QFrame()
        terms_frame.setObjectName("Transparent")
        terms_layout = QVBoxLayout(terms_frame)
        terms_layout.setContentsMargins(0, 0, 0, 0)
        terms_layout.setSpacing(6)
        terms_layout.addWidget(self._section_label("Domain vocabulary"))
        terms_layout.addWidget(self._muted_label(
            "Terms injected into the AI prompt to reinforce correct spelling of domain-specific words. One term per line."
        ))
        self._glossary_edit = QTextEdit()
        self._glossary_edit.setPlaceholderText("Active Directory\nGPO\nOneDrive")
        self._glossary_edit.setPlainText("\n".join(load_glossary_terms()))
        terms_layout.addWidget(self._glossary_edit)
        terms_btn_row = QHBoxLayout()
        save_terms_btn = QPushButton("Save terms")
        save_terms_btn.setObjectName("PrimaryButton")
        save_terms_btn.setMinimumHeight(34)
        save_terms_btn.clicked.connect(self._save_glossary)
        reset_terms_btn = QPushButton("Reset to defaults")
        reset_terms_btn.setMinimumHeight(34)
        reset_terms_btn.clicked.connect(self._reset_glossary_to_defaults)
        terms_btn_row.addWidget(save_terms_btn)
        terms_btn_row.addWidget(reset_terms_btn)
        terms_btn_row.addStretch()
        terms_layout.addLayout(terms_btn_row)
        splitter.addWidget(terms_frame)

        # --- Corrections pane ---
        corr_frame = QFrame()
        corr_frame.setObjectName("Transparent")
        corr_layout = QVBoxLayout(corr_frame)
        corr_layout.setContentsMargins(0, 0, 0, 0)
        corr_layout.setSpacing(6)
        corr_layout.addWidget(self._section_label("Transcription corrections"))
        corr_layout.addWidget(self._muted_label(
            "Applied before AI notes generation to fix common mishearings. Format: wrong word → correct word, one per line."
        ))
        self._corrections_edit = QTextEdit()
        self._corrections_edit.setPlaceholderText("APIs → ADS\nGBO → GPO\none drive → OneDrive")
        pairs = load_correction_pairs()
        self._corrections_edit.setPlainText("\n".join(f"{w} → {r}" for w, r in pairs))
        corr_layout.addWidget(self._corrections_edit)
        corr_btn_row = QHBoxLayout()
        save_corr_btn = QPushButton("Save corrections")
        save_corr_btn.setObjectName("PrimaryButton")
        save_corr_btn.setMinimumHeight(34)
        save_corr_btn.clicked.connect(self._save_corrections)
        reset_corr_btn = QPushButton("Reset to defaults")
        reset_corr_btn.setMinimumHeight(34)
        reset_corr_btn.clicked.connect(self._reset_corrections_to_defaults)
        corr_btn_row.addWidget(save_corr_btn)
        corr_btn_row.addWidget(reset_corr_btn)
        corr_btn_row.addStretch()
        corr_layout.addLayout(corr_btn_row)
        splitter.addWidget(corr_frame)

        layout.addWidget(splitter, stretch=1)
        return widget

    def _save_glossary(self) -> None:
        if not hasattr(self, "_glossary_edit"):
            return
        terms = [line.strip() for line in self._glossary_edit.toPlainText().splitlines() if line.strip()]
        save_glossary_terms(terms)
        self.log(f"Glossary saved: {len(terms)} term(s).")
        QMessageBox.information(self, "Nova Notetaker", f"Glossary saved with {len(terms)} term(s).")

    def _reset_glossary_to_defaults(self) -> None:
        from app.core.glossary import DEFAULT_GLOSSARY_TERMS
        if not hasattr(self, "_glossary_edit"):
            return
        self._glossary_edit.setPlainText("\n".join(DEFAULT_GLOSSARY_TERMS))
        self.log("Glossary terms reset to defaults.")

    def _save_corrections(self) -> None:
        if not hasattr(self, "_corrections_edit"):
            return
        pairs: list[tuple[str, str]] = []
        for line in self._corrections_edit.toPlainText().splitlines():
            line = line.strip()
            if not line:
                continue
            for sep in (" → ", " -> ", "→", "->"):
                if sep in line:
                    wrong, _, right = line.partition(sep)
                    w, r = wrong.strip(), right.strip()
                    if w and r:
                        pairs.append((w, r))
                    break
        save_correction_pairs(pairs)
        self.log(f"Corrections saved: {len(pairs)} pair(s).")
        QMessageBox.information(self, "Nova Notetaker", f"Corrections saved with {len(pairs)} pair(s).")

    def _reset_corrections_to_defaults(self) -> None:
        from app.core.glossary import DEFAULT_CORRECTION_PAIRS
        if not hasattr(self, "_corrections_edit"):
            return
        self._corrections_edit.setPlainText("\n".join(f"{w} → {r}" for w, r in DEFAULT_CORRECTION_PAIRS))
        self.log("Corrections reset to defaults.")

    def _build_updates_tab(self) -> QWidget:
        from app import __version__
        widget = QWidget()
        widget.setObjectName("Transparent")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        section = QFrame()
        section.setObjectName("FormSection")
        fl = QFormLayout(section)
        fl.setContentsMargins(16, 16, 16, 16)
        fl.setLabelAlignment(Qt.AlignLeft)
        fl.setHorizontalSpacing(18)
        fl.setVerticalSpacing(12)

        version_label = QLabel(__version__)
        version_label.setObjectName("OrangeText")
        fl.addRow("Current version", version_label)

        check_btn = QPushButton("Check for Updates")
        check_btn.setObjectName("PrimaryButton")
        check_btn.setMinimumHeight(36)
        check_btn.clicked.connect(lambda: self._check_for_updates(manual=True))
        fl.addRow("", check_btn)

        self.settings_update_on_startup_cb = QCheckBox("Check for updates automatically on startup")
        self.settings_update_on_startup_cb.setChecked(
            bool(self.settings.get("app", {}).get("check_for_updates_on_startup", True))
        )
        self.settings_update_on_startup_cb.toggled.connect(self._on_update_startup_toggled)
        fl.addRow("", self.settings_update_on_startup_cb)

        layout.addWidget(section)
        layout.addWidget(self._muted_label(
            "Update checks connect to GitHub releases. When an update is available, Nova Notetaker will download the installer and prompt you to close and install."
        ))
        layout.addStretch()
        return widget

    def _settings_section(self, rows: list[tuple[str, QWidget]]) -> QFrame:
        section = QFrame()
        section.setObjectName("FormSection")
        layout = QFormLayout(section)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setLabelAlignment(Qt.AlignLeft)
        layout.setFormAlignment(Qt.AlignTop)
        layout.setHorizontalSpacing(18)
        layout.setVerticalSpacing(12)
        for label, control in rows:
            layout.addRow(label, control)
        return section

    def _setting_with_hint(self, control: QWidget, hint: str, visible: bool = False) -> QWidget:
        container = QWidget()
        container.setObjectName("Transparent")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        control.setToolTip(hint)
        layout.addWidget(control)
        if visible:
            hint_label = self._muted_label(hint)
            hint_label.setWordWrap(True)
            layout.addWidget(hint_label)
        return container

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

    def browse_meetings_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Meeting data location", self.settings_meetings_dir.text().strip() or str(USER_DATA_DIR / "Meetings"))
        if selected:
            self.settings_meetings_dir.setText(selected)

    def apply_retention_now(self) -> None:
        self.settings.setdefault("storage", {})["retention_days"] = self.settings_retention_days.value()
        result = apply_retention_policy(self.meeting_store, self.settings)
        for warning in result.warnings:
            self.log(f"Retention warning: {warning}")
        QMessageBox.information(self, "Retention", f"Removed {result.meetings_removed} expired meeting(s).")
    def save_settings_page(self) -> None:
        self.settings["audio"]["mic_device_name"] = str(self.settings_mic_combo.currentData() or "")
        self.settings["audio"]["system_loopback_device_name"] = str(self.settings_loopback_combo.currentData() or "")
        self.settings["audio"]["capture_profile"] = str(self.settings_profile_combo.currentData() or "external_mic_speakers")
        self.settings["ai"]["provider"] = str(self.settings_provider_combo.currentData() or "ollama")
        self.settings["ai"]["ollama_url"] = self.settings_ollama_url.text().strip()
        self.settings["ai"]["ollama_model"] = self.settings_ollama_model.text().strip()
        self.settings["ai"]["openai_api_key"] = self.settings_openai_api_key.text().strip()
        self.settings["ai"]["openai_model"] = self.settings_openai_model.text().strip()
        self.settings["ai"]["claude_api_key"] = self.settings_claude_api_key.text().strip()
        self.settings["ai"]["claude_model"] = self.settings_claude_model.text().strip()
        self.settings["ai"]["timeout_seconds"] = self.settings_ai_timeout.value()
        storage = self.settings.setdefault("storage", {})
        storage["meetings_dir"] = self.settings_meetings_dir.text().strip() or "Meetings"
        storage["archive_wav_to_flac"] = self.settings_archive_wav_to_flac.isChecked()
        storage["delete_raw_audio_after_processing"] = self.settings_delete_raw_audio.isChecked()
        storage["notes_only_archive"] = self.settings_notes_only_archive.isChecked()
        storage["retention_days"] = self.settings_retention_days.value()
        self.settings.setdefault("review", {})["action_auto_close_days"] = self.settings_action_auto_close_days.value()
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
        issues = validate_settings(self.settings)
        for issue in issues:
            self.log(f"[Settings] {issue}")
        self._run_health_checks()

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

    def test_openai_connection(self) -> None:
        api_key = self.settings_openai_api_key.text().strip()
        model = self.settings_openai_model.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Nova Notetaker", "Enter an OpenAI API key before testing.")
            return
        try:
            response = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            if response.status_code == 401:
                QMessageBox.warning(self, "OpenAI Test", "API key is invalid or unauthorized.")
                self.log("OpenAI test failed: unauthorized.")
                return
            response.raise_for_status()
            model_ids = [item.get("id", "") for item in response.json().get("data", []) if isinstance(item, dict)]
            model_message = f"Model found: {model}" if model in model_ids else f"Model '{model}' not listed (may still work)."
            if not model:
                model_message = "No model configured."
            QMessageBox.information(self, "OpenAI Test", f"OpenAI API is reachable.\n{model_message}")
            self.log(f"OpenAI test succeeded. {model_message}")
        except Exception as error:
            QMessageBox.warning(self, "OpenAI Test", f"OpenAI test failed:\n{error}")
            self.log(f"OpenAI test failed: {error}")

    def test_claude_connection(self) -> None:
        api_key = self.settings_claude_api_key.text().strip()
        model = self.settings_claude_model.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Nova Notetaker", "Enter a Claude API key before testing.")
            return
        try:
            response = requests.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                timeout=10,
            )
            if response.status_code == 401:
                QMessageBox.warning(self, "Claude Test", "API key is invalid or unauthorized.")
                self.log("Claude test failed: unauthorized.")
                return
            response.raise_for_status()
            model_ids = [item.get("id", "") for item in response.json().get("data", []) if isinstance(item, dict)]
            model_message = f"Model found: {model}" if model in model_ids else f"Model '{model}' not listed (may still work)."
            if not model:
                model_message = "No model configured."
            QMessageBox.information(self, "Claude Test", f"Claude API is reachable.\n{model_message}")
            self.log(f"Claude test succeeded. {model_message}")
        except Exception as error:
            QMessageBox.warning(self, "Claude Test", f"Claude test failed:\n{error}")
            self.log(f"Claude test failed: {error}")

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

    def run_capture_preflight(self) -> None:
        self.refresh_devices()
        mic_required = self.capture_mic_toggle.isChecked() if hasattr(self, "capture_mic_toggle") else bool(self.settings["audio"].get("capture_mic", True))
        mic_device = self._resolve_microphone_device()
        loop_device = self._resolve_loopback_device()
        mic_channels = self._capture_channels(mic_device, default=1, max_channels=2)
        loopback_sample_rate, loopback_channels = self._loopback_capture_format(loop_device)
        checks = run_capture_preflight_checks(
            settings=self.settings,
            meetings_root=self.meeting_store.meetings_root,
            mic_device=mic_device,
            loopback_device=loop_device,
            capture_mic=mic_required,
            mic_channels=mic_channels,
            loopback_channels=loopback_channels,
            check_ai=True,
        )
        _passed, lines = summarize_preflight(checks)
        title = "Preflight Passed" if all(check.passed or not check.critical for check in checks) else "Preflight Needs Review"
        QMessageBox.information(self, title, "\n".join(lines))
        for line in lines:
            self.log(f"Preflight: {line}")
        if hasattr(self, "recording_health_label"):
            self._set_recording_health("; ".join(lines[:5]))
        if hasattr(self, "capture_format_label"):
            self._set_capture_format(f"mic {'muted' if not mic_required else f'{(mic_device.sample_rate if mic_device else 48000)} Hz / {mic_channels} ch'}, system {loopback_sample_rate} Hz / {loopback_channels} ch")

    def open_logs_folder(self) -> None:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(LOGS_DIR))
        except Exception as error:
            QMessageBox.warning(self, "Logs", f"Could not open logs folder:\n{error}")

    def copy_diagnostics_summary(self) -> None:
        lines = [
            "Nova Notetaker Diagnostics",
            f"Settings: {SETTINGS_PATH}",
            f"Logs: {LOGS_DIR}",
            f"Meetings: {self.meeting_store.meetings_root}",
            f"Audio profiles: {self._audio_profiles_summary()}",
            f"Microphones: {len(self.microphones)}",
            f"Loopbacks: {len(self.loopbacks)}",
        ]
        for path in sorted(LOGS_DIR.glob("runtime-*.log"), key=lambda item: item.stat().st_mtime, reverse=True)[:1]:
            lines.append(f"Latest runtime log: {path}")
            try:
                tail = path.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
                lines.extend(tail)
            except Exception as error:
                lines.append(f"Could not read runtime log: {error}")
        QApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self, "Diagnostics", "Diagnostics copied to clipboard.")
        self.log("Diagnostics copied to clipboard.")

    def _audio_profiles_summary(self) -> str:
        profiles = load_audio_profiles()
        if not profiles:
            return f"No saved profiles ({AUDIO_PROFILES_PATH})"
        return "; ".join(f"{profile.device_name}: {profile.detail}" for profile in profiles.values())

    def update_settings_summary(self) -> None:
        mic_setting = self.settings["audio"].get("mic_device_name", "") or DEFAULT_MIC_DEVICE
        mic_name = "Windows default microphone" if mic_setting == DEFAULT_MIC_DEVICE else mic_setting or "No microphone selected"
        system_setting = self.settings["audio"].get("system_loopback_device_name", "") or DEFAULT_LOOPBACK_DEVICE
        system_name = "Windows default output" if system_setting == DEFAULT_LOOPBACK_DEVICE else system_setting or "No system audio selected"
        profile = self._profile_label(self.settings["audio"].get("capture_profile", ""))
        meeting_profile_name = self._selected_meeting_profile().name if hasattr(self, "profile_combo") else "General Meeting"
        template_name = self._selected_note_template().name if hasattr(self, "template_combo") else "Standard Meeting Notes"
        provider = self.settings["ai"].get("provider", "ollama")
        provider_display = {"ollama": "Ollama", "openai": "OpenAI", "claude": "Claude"}.get(provider, provider)
        whisper = "on" if self.settings["transcription"].get("enabled", False) else "off"
        mic_state = "on" if self.settings["audio"].get("capture_mic", True) else "muted"
        self.settings_summary.setText(
            f"Mic {mic_state}  |  System: {system_name}  |  Audio: {profile}  |  Meeting: {meeting_profile_name}  |  Template: {template_name}  |  {provider_display} / WhisperLive {whisper}"
        )
        if hasattr(self, "footer_transcription_label"):
            self.footer_transcription_label.setText(f"Transcription: WhisperLive {whisper}")
        if hasattr(self, "footer_intelligence_label"):
            self.footer_intelligence_label.setText(f"Intelligence: {provider_display}")
        if hasattr(self, "sidebar_services_label"):
            self.sidebar_services_label.setText(f"{provider_display}  -  WhisperLive")
