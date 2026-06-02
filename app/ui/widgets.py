from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QCalendarWidget, QComboBox, QTableWidgetItem, QWidget


class SortableTableItem(QTableWidgetItem):
    def __lt__(self, other) -> bool:
        left = self.data(Qt.UserRole + 1)
        right = other.data(Qt.UserRole + 1)
        if left is not None and right is not None:
            return str(left) < str(right)
        return super().__lt__(other)


class InsightCalendarWidget(QCalendarWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items_by_date: dict[str, list[dict[str, object]]] = {}

    def set_items_by_date(self, items_by_date: dict[str, list[dict[str, object]]]) -> None:
        self._items_by_date = items_by_date
        self.updateCells()

    def paintCell(self, painter: QPainter, rect, date: QDate) -> None:
        super().paintCell(painter, rect, date)
        items = self._items_by_date.get(date.toString("yyyy-MM-dd"), [])
        if not items:
            return

        approved = sum(1 for item in items if item.get("approved"))
        total = len(items)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        accent = QColor("#FF8A1F" if approved else "#85888E")
        fill = QColor(accent)
        fill.setAlpha(52 if approved else 34)
        badge_rect = rect.adjusted(rect.width() - 29, rect.height() - 21, -5, -5)
        painter.setPen(accent)
        painter.setBrush(fill)
        painter.drawRoundedRect(badge_rect, 7, 7)
        painter.setPen(accent)
        painter.drawText(badge_rect, Qt.AlignCenter, str(total))
        if approved:
            dot_rect = rect.adjusted(7, rect.height() - 13, -(rect.width() - 14), -7)
            painter.setBrush(accent)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(dot_rect)
        painter.restore()


def select_combo_by_data(combo: QComboBox, value: str) -> None:
    for index in range(combo.count()):
        if combo.itemData(index) == value:
            combo.setCurrentIndex(index)
            return
