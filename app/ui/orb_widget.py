from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel

from app.core.settings import APP_ROOT


class OrbWidget(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(260, 260)
        self.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.state = "idle"
        self.orb_pixmap = self._load_orb_pixmap()
        self._apply_state_style()
        self._refresh_pixmap()

    @staticmethod
    def _load_orb_pixmap() -> QPixmap:
        image = QImage(str(APP_ROOT / "assets" / "Nova - Orb.png"))
        if image.isNull():
            return QPixmap()
        rect = image.rect()
        left, top, right, bottom = rect.right(), rect.bottom(), rect.left(), rect.top()
        found = False
        for y in range(rect.top(), rect.bottom() + 1):
            for x in range(rect.left(), rect.right() + 1):
                if image.pixelColor(x, y).alpha() > 8:
                    left = min(left, x)
                    top = min(top, y)
                    right = max(right, x)
                    bottom = max(bottom, y)
                    found = True
        if not found:
            return QPixmap.fromImage(image)
        padding = int(max(right - left, bottom - top) * 0.08)
        left = max(rect.left(), left - padding)
        top = max(rect.top(), top - padding)
        right = min(rect.right(), right + padding)
        bottom = min(rect.bottom(), bottom + padding)
        return QPixmap.fromImage(image.copy(left, top, right - left + 1, bottom - top + 1))

    def set_state(self, state: str) -> None:
        self.state = state
        self._apply_state_style()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_pixmap()

    def _refresh_pixmap(self) -> None:
        if self.orb_pixmap.isNull():
            self.clear()
            self.setText("Nova")
            return
        size = max(1, int(min(self.width(), self.height()) * 0.96))
        scaled = self.orb_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)

    def _apply_state_style(self) -> None:
        if self.state == "recording":
            glow = "rgba(255, 138, 31, 0.34)"
        elif self.state == "processing":
            glow = "rgba(255, 184, 77, 0.40)"
        elif self.state == "error":
            glow = "rgba(255, 77, 46, 0.32)"
        else:
            glow = "rgba(255, 138, 31, 0.18)"
        self.setStyleSheet(
            "OrbWidget {"
            "background: transparent;"
            f"border: 1px solid {glow};"
            "border-radius: 130px;"
            "}"
        )
