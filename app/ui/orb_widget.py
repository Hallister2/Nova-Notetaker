from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from app.core.settings import APP_ROOT


class OrbWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(260, 260)
        self.phase = 0.0
        self.energy = 0.25
        self.target_energy = 0.25
        self.state = "idle"
        self.orb_pixmap = self._load_orb_pixmap()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(16)

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
                if QColor(image.pixelColor(x, y)).alpha() > 8:
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
        if state == "recording":
            self.target_energy = 0.72
        elif state == "processing":
            self.target_energy = 0.86
        elif state == "error":
            self.target_energy = 0.48
        else:
            self.target_energy = 0.25
        self.update()

    def animate(self) -> None:
        self.phase += 0.035
        self.energy = self.energy * 0.90 + self.target_energy * 0.10
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        base_radius = min(rect.width(), rect.height()) * 0.33
        center = QPointF(rect.center().x(), rect.center().y())
        breath = math.sin(self.phase * 1.2) * 0.06
        spin = self.phase * 42

        main = QColor("#ff8a1f") if self.state != "error" else QColor("#ff4d2e")

        painter.setPen(Qt.NoPen)
        for mult, alpha in [(1.9, 28), (1.45, 46), (1.08, 72)]:
            r = base_radius * mult * (1 + breath)
            glow = QRadialGradient(center, r)
            glow.setColorAt(0.0, QColor(255, 245, 220, int(alpha * self.energy)))
            glow.setColorAt(0.35, QColor(255, 138, 31, int(alpha * self.energy)))
            glow.setColorAt(1.0, QColor(80, 24, 0, 0))
            painter.setBrush(glow)
            painter.drawEllipse(center, r, r)

        if not self.orb_pixmap.isNull():
            size = min(rect.width(), rect.height()) * 0.98 * (1 + breath * 0.12)
            target = QRectF(center.x() - size / 2, center.y() - size / 2, size, size)
            painter.setOpacity(0.95 + self.energy * 0.05)
            painter.drawPixmap(target, self.orb_pixmap, QRectF(self.orb_pixmap.rect()))
            painter.setOpacity(1.0)
            self._draw_animated_overlay(painter, center, base_radius, breath, spin, main)
            return

        self._draw_fallback_orb(painter, center, base_radius, breath, spin, main)

    def _draw_animated_overlay(
        self,
        painter: QPainter,
        center: QPointF,
        base_radius: float,
        breath: float,
        spin: float,
        main: QColor,
    ) -> None:
        painter.setBrush(Qt.NoBrush)
        arc_color = QColor(main)
        arc_color.setAlpha(int(95 + self.energy * 115))
        painter.setPen(QPen(arc_color, 2.4))
        for index, mult in enumerate((1.10, 1.34)):
            r = base_radius * mult * (1 + breath * 0.25)
            painter.drawArc(
                int(center.x() - r),
                int(center.y() - r),
                int(r * 2),
                int(r * 2),
                int((-spin - index * 78) * 16),
                int((-62 + index * 16) * 16),
            )

        pulse = QColor("#ffb347")
        pulse.setAlpha(int(70 + self.energy * 80))
        painter.setPen(QPen(pulse, 1.2))
        r = base_radius * (0.72 + self.energy * 0.06)
        painter.drawEllipse(center, r, r)

    def _draw_fallback_orb(self, painter: QPainter, center: QPointF, base_radius: float, breath: float, spin: float, main: QColor) -> None:
        painter.setBrush(Qt.NoBrush)
        for i, mult in enumerate([0.78, 1.0, 1.24]):
            color = QColor(main)
            color.setAlpha(int(55 + self.energy * 95))
            painter.setPen(QPen(color, 1 + i))
            r = base_radius * mult * (1 + breath * 0.5)
            painter.drawEllipse(center, r, r)

        color = QColor("#ffb347")
        color.setAlpha(int(130 + self.energy * 80))
        painter.setPen(QPen(color, 3))
        r = base_radius * 1.28
        painter.drawArc(
            int(center.x() - r),
            int(center.y() - r),
            int(r * 2),
            int(r * 2),
            int(-spin * 16),
            int(-90 * 16),
        )

        painter.setPen(Qt.NoPen)
        core_r = base_radius * (0.20 + self.energy * 0.09)
        core = QRadialGradient(center, core_r * 3)
        core.setColorAt(0.0, QColor(255, 255, 255, 245))
        core.setColorAt(0.24, QColor(255, 220, 145, 230))
        core.setColorAt(0.55, QColor(255, 138, 31, 160))
        core.setColorAt(1.0, QColor(255, 70, 0, 0))
        painter.setBrush(core)
        painter.drawEllipse(center, core_r * 3, core_r * 3)
