from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class SearchTabMixin:
    def _build_search_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 28, 18, 28)
        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        title = QLabel("Search")
        title.setObjectName("Title")
        panel_layout.addWidget(title)
        panel_layout.addWidget(self._muted_label("Search meeting titles, notes, transcripts, owners, and dates."))
        search_controls = QHBoxLayout()
        self.meeting_search_input = QLineEdit()
        self.meeting_search_input.setPlaceholderText("Search notes, transcripts, titles, owners, dates...")
        self.meeting_search_input.returnPressed.connect(self.search_meetings)
        self.meeting_search_button = QPushButton("Search")
        self.meeting_search_button.clicked.connect(self.search_meetings)
        search_controls.addWidget(self.meeting_search_input, stretch=1)
        search_controls.addWidget(self.meeting_search_button)
        panel_layout.addLayout(search_controls)
        self.search_empty_state = self._empty_state_widget(
            "search",
            "No search results",
            "Search meeting titles, notes, transcripts, owners, and dates.",
        )
        self.search_results_table = QTableWidget(0, 4)
        self.search_results_table.setMinimumWidth(0)
        self.search_results_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.search_results_table.setHorizontalHeaderLabels(["Meeting", "File", "Match", "Open"])
        self._configure_table(self.search_results_table)
        self.search_results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.search_results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.search_results_table.verticalHeader().setVisible(False)
        self.search_results_table.setVisible(False)
        search_header = self.search_results_table.horizontalHeader()
        search_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        search_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        search_header.setSectionResizeMode(2, QHeaderView.Stretch)
        search_header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.search_results_table.setColumnWidth(3, 120)
        panel_layout.addWidget(self.search_empty_state, stretch=1)
        panel_layout.addWidget(self.search_results_table, stretch=1)
        layout.addWidget(panel)
        return page

    def search_meetings(self) -> None:
        query = self.meeting_search_input.text().strip().lower() if hasattr(self, "meeting_search_input") else ""
        if not query:
            self.search_results_table.setRowCount(0)
            self.search_results_table.setVisible(False)
            self.search_empty_state.setVisible(True)
            return
        self.search_results_table.setRowCount(0)
        for folder in self.meeting_store.list_meetings():
            try:
                metadata = self.meeting_store.read_metadata(folder)
                title = metadata.title or folder.name
            except Exception:
                title = folder.name
            for file_name in ("notes.md", "transcript.md"):
                path = folder / file_name
                if not path.exists():
                    continue
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    plain = self._plain_note_text(line).strip()
                    if query in plain.lower() or query in title.lower():
                        self._add_search_result(folder, title, file_name, plain[:220] or title)
                        break
        has_rows = self.search_results_table.rowCount() > 0
        self.search_results_table.setVisible(has_rows)
        self.search_empty_state.setVisible(not has_rows)

    def _add_search_result(self, folder: Path, title: str, file_name: str, match: str) -> None:
        row = self.search_results_table.rowCount()
        self.search_results_table.insertRow(row)
        for column, value in enumerate((title, file_name, match)):
            item = QTableWidgetItem(value)
            item.setData(Qt.UserRole, str(folder))
            self.search_results_table.setItem(row, column, item)
        button = QPushButton("Open meeting")
        button.setObjectName("TableActionButton")
        button.clicked.connect(lambda checked=False, meeting_folder=folder: self.open_meeting_overview(meeting_folder))
        open_item = QTableWidgetItem("")
        open_item.setData(Qt.UserRole, str(folder))
        self.search_results_table.setItem(row, 3, open_item)
        self.search_results_table.setCellWidget(row, 3, button)
        self.search_results_table.setRowHeight(row, 38)
