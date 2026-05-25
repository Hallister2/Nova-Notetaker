from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class OrbWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(260, 260)
        self.phase = 0.0
        self.energy = 0.25
        self.target_energy = 0.25
        self.state = "idle"

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(16)

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
