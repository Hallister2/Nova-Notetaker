from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Slot
from app.core.crash_logging import write_runtime_log

from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class LogsTabMixin:
    def _build_logs_page(self) -> QWidget:
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

    @Slot(str)
    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        if hasattr(self, "log_output"):
            self.log_output.append(line)
        write_runtime_log(message)
