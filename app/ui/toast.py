from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget
from PySide6.QtCore import Qt


_PLAIN_MS = 3500
_ACTION_MS = 6000

_ICONS = {
    "success": "✓",
    "info": "●",
    "warning": "!",
    "error": "✕",
}


class _Toast(QFrame):
    dismissed = Signal()

    def __init__(
        self,
        message: str,
        kind: str,
        action_label: str = "",
        action_cb: Callable | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setProperty("kind", kind)
        self.setFrameShape(QFrame.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        icon = QLabel(_ICONS.get(kind, "●"))
        icon.setObjectName("ToastIcon")
        icon.setProperty("kind", kind)
        layout.addWidget(icon)

        msg = QLabel(message)
        msg.setObjectName("ToastMessage")
        msg.setWordWrap(False)
        layout.addWidget(msg, stretch=1)

        if action_label and action_cb:
            btn = QPushButton(action_label)
            btn.setObjectName("ToastAction")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda: (action_cb(), self._dismiss()))
            layout.addWidget(btn)

        self.adjustSize()
        QTimer.singleShot(_ACTION_MS if action_label else _PLAIN_MS, self._dismiss)

    def _dismiss(self) -> None:
        self.dismissed.emit()
        self.hide()
        self.deleteLater()


class ToastManager:
    def __init__(self, anchor: QWidget) -> None:
        self._anchor = anchor
        self._active: list[_Toast] = []

    def success(self, message: str) -> None:
        self._show(message, "success")

    def info(self, message: str) -> None:
        self._show(message, "info")

    def warning(self, message: str) -> None:
        self._show(message, "warning")

    def error(self, message: str) -> None:
        self._show(message, "error")

    def info_action(self, message: str, action_label: str, action_callback: Callable) -> None:
        self._show(message, "info", action_label=action_label, action_cb=action_callback)

    def warning_action(self, message: str, action_label: str, action_callback: Callable) -> None:
        self._show(message, "warning", action_label=action_label, action_cb=action_callback)

    def _show(
        self,
        message: str,
        kind: str,
        action_label: str = "",
        action_cb: Callable | None = None,
    ) -> None:
        toast = _Toast(message, kind, action_label=action_label, action_cb=action_cb, parent=self._anchor)
        toast.dismissed.connect(lambda t=toast: self._remove(t))
        self._active.append(toast)
        self._reposition()
        toast.show()
        toast.raise_()

    def _remove(self, toast: _Toast) -> None:
        if toast in self._active:
            self._active.remove(toast)
        self._reposition()

    def _reposition(self) -> None:
        margin = 16
        gap = 6
        rect = self._anchor.rect()
        bottom = rect.height() - margin
        for toast in reversed(self._active):
            toast.adjustSize()
            x = rect.width() - toast.width() - margin
            y = bottom - toast.height()
            toast.move(QPoint(x, y))
            bottom = y - gap
