from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.audio.device_manager import AudioDevice
from app.core.profiles import MeetingProfile
from app.core.templates import NoteTemplate
from app.ui.constants import CAPTURE_PROFILES
from app.ui.widgets import select_combo_by_data


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
