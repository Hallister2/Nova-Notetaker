from __future__ import annotations

from urllib.parse import urlparse

import requests
import websocket

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
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

from app.core.settings import save_settings, validate_settings
from app.ui.constants import CAPTURE_PROFILES, DEFAULT_LOOPBACK_DEVICE, DEFAULT_MIC_DEVICE
from app.ui.widgets import select_combo_by_data


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
        panel_layout.addWidget(self._muted_label("Device, capture, WhisperLive, and Ollama settings."))

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
        self.settings_action_auto_close_days = QSpinBox()
        self.settings_action_auto_close_days.setRange(0, 3650)
        self.settings_action_auto_close_days.setValue(int(self.settings.get("review", {}).get("action_auto_close_days", 30)))

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
            self.settings_action_auto_close_days,
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
        settings_tabs.addTab(
            self._settings_section(
                [
                    ("AI provider", self._setting_with_hint(self.settings_provider_combo, "Ollama is currently wired for local note generation. OpenAI is reserved for a later provider pass.")),
                    ("Ollama URL", self._setting_with_hint(self.settings_ollama_url, "Base URL for your Ollama server. Use the same address you use for Ollama API calls.")),
                    ("Ollama model", self._setting_with_hint(self.settings_ollama_model, "Any installed Ollama model name works here. Run `ollama list` on the Ollama host to see available models.", visible=True)),
                    ("AI timeout", self._setting_with_hint(self.settings_ai_timeout, "Maximum seconds to wait for notes generation before Nova treats it as failed.")),
                ]
            ),
            "Intelligence",
        )
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
                    ("WhisperLive", self._setting_with_hint(self.settings_transcription_enabled, "Turn this on to transcribe audio with your WhisperLive server during processing.")),
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
        panel_layout.addWidget(settings_tabs, stretch=1)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        self.settings_refresh_devices_button = QPushButton("Refresh devices")
        self.settings_refresh_devices_button.clicked.connect(self.refresh_devices)
        self.settings_preflight_button = QPushButton("Run preflight")
        self.settings_preflight_button.clicked.connect(self.run_capture_preflight)
        self.settings_test_ollama_button = QPushButton("Test Ollama")
        self.settings_test_ollama_button.clicked.connect(self.test_ollama_connection)
        self.settings_test_whisper_button = QPushButton("Test WhisperLive")
        self.settings_test_whisper_button.clicked.connect(self.test_whisperlive_connection)
        self.settings_button = QPushButton("Save settings")
        self.settings_button.setObjectName("PrimaryButton")
        self.settings_button.clicked.connect(self.save_settings_page)
        for button in (
            self.settings_refresh_devices_button,
            self.settings_preflight_button,
            self.settings_test_ollama_button,
            self.settings_test_whisper_button,
            self.settings_button,
        ):
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button_row.addWidget(self.settings_refresh_devices_button)
        button_row.addWidget(self.settings_preflight_button)
        button_row.addWidget(self.settings_test_ollama_button)
        button_row.addWidget(self.settings_test_whisper_button)
        button_row.addStretch()
        button_row.addWidget(self.settings_button)
        panel_layout.addLayout(button_row)
        panel_layout.addStretch()

        scroll.setWidget(panel)
        layout.addWidget(scroll)
        return page

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

    def save_settings_page(self) -> None:
        self.settings["audio"]["mic_device_name"] = str(self.settings_mic_combo.currentData() or "")
        self.settings["audio"]["system_loopback_device_name"] = str(self.settings_loopback_combo.currentData() or "")
        self.settings["audio"]["capture_profile"] = str(self.settings_profile_combo.currentData() or "external_mic_speakers")
        self.settings["ai"]["provider"] = self.settings_provider_combo.currentText()
        self.settings["ai"]["ollama_url"] = self.settings_ollama_url.text().strip()
        self.settings["ai"]["ollama_model"] = self.settings_ollama_model.text().strip()
        self.settings["ai"]["timeout_seconds"] = self.settings_ai_timeout.value()
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
        checks: list[tuple[str, bool, str]] = []
        self.refresh_devices()

        mic_required = self.capture_mic_toggle.isChecked() if hasattr(self, "capture_mic_toggle") else bool(self.settings["audio"].get("capture_mic", True))
        mic_device = self._resolve_microphone_device()
        loop_device = self._resolve_loopback_device()
        checks.append(("Microphone", bool(mic_device) or not mic_required, mic_device.label if mic_device else "Muted or unavailable"))
        checks.append(("System audio", bool(loop_device), loop_device.label if loop_device else "No WASAPI loopback resolved"))

        try:
            self.meeting_store.meetings_root.mkdir(parents=True, exist_ok=True)
            probe_path = self.meeting_store.meetings_root / ".nova_write_test"
            probe_path.write_text("ok", encoding="utf-8")
            probe_path.unlink(missing_ok=True)
            checks.append(("Meeting storage", True, str(self.meeting_store.meetings_root)))
        except Exception as error:
            checks.append(("Meeting storage", False, str(error)))

        ollama_url = self.settings_ollama_url.text().strip().rstrip("/") if hasattr(self, "settings_ollama_url") else self.settings["ai"].get("ollama_url", "")
        ollama_model = self.settings_ollama_model.text().strip() if hasattr(self, "settings_ollama_model") else self.settings["ai"].get("ollama_model", "")
        try:
            response = requests.get(f"{ollama_url}/api/tags", timeout=5)
            response.raise_for_status()
            models = [item.get("name", "") for item in response.json().get("models", []) if isinstance(item, dict)]
            model_ok = not ollama_model or ollama_model in models
            detail = f"{ollama_model} found" if model_ok and ollama_model else "Reachable"
            if ollama_model and not model_ok:
                detail = f"{ollama_model} not found"
            checks.append(("Ollama", model_ok, detail))
        except Exception as error:
            checks.append(("Ollama", False, str(error)))

        whisper_enabled = self.settings_transcription_enabled.isChecked() if hasattr(self, "settings_transcription_enabled") else bool(self.settings["transcription"].get("enabled", False))
        if whisper_enabled:
            whisper_url = self.settings_whisper_url.text().strip().rstrip("/") if hasattr(self, "settings_whisper_url") else self.settings["transcription"].get("whisperlive_url", "")
            try:
                parsed = urlparse(whisper_url)
                scheme = "wss" if parsed.scheme == "https" else "ws"
                host = parsed.hostname or whisper_url.replace("http://", "").replace("https://", "")
                port = parsed.port or (443 if scheme == "wss" else 80)
                ws_url = f"{scheme}://{host}:{port}"
                ws = websocket.create_connection(ws_url, timeout=5)
                ws.close()
                checks.append(("WhisperLive", True, ws_url))
            except Exception as error:
                checks.append(("WhisperLive", False, str(error)))
        else:
            checks.append(("WhisperLive", True, "Disabled"))

        lines = [f"{'OK' if passed else 'Review'} - {name}: {detail}" for name, passed, detail in checks]
        all_passed = all(passed for _, passed, _ in checks)
        title = "Preflight Passed" if all_passed else "Preflight Needs Review"
        QMessageBox.information(self, title, "\n".join(lines))
        for line in lines:
            self.log(f"Preflight: {line}")

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
