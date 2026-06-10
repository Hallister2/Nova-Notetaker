from __future__ import annotations

from PySide6.QtCore import Qt
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



def select_combo_by_data(combo: QComboBox, value: str) -> None:
    for index in range(combo.count()):
        if combo.itemData(index) == value:
            combo.setCurrentIndex(index)
            return
