from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.intelligence.insights import InsightItem, MeetingInsights, load_or_build_insights, write_insights_json
from app.storage.meeting_store import MeetingMetadata
from app.ui.constants import CLOSED_ACTION_STATUSES
from app.ui.review_helpers import candidate_key, ics_escape, read_calendar_review, safe_file_label, write_calendar_review
from app.ui.widgets import InsightCalendarWidget


class CalendarTabMixin:
    def _build_calendar_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 28, 18, 28)
        layout.setSpacing(14)

        title = QLabel("Calendar")
        title.setObjectName("Title")
        subtitle = self._muted_label("Review meeting dates and action follow-ups in one workspace.")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        review_tabs = QTabWidget()
        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        title = QLabel("Dates")
        title.setObjectName("Title")
        panel_layout.addWidget(title)
        panel_layout.addWidget(self._muted_label("Review detected dates by meeting and export only what you need."))

        calendar_header = QGridLayout()
        calendar_header.setHorizontalSpacing(10)
        calendar_header.addWidget(QLabel("Meeting"), 0, 0)
        self.calendar_meeting_filter = QComboBox()
        self.calendar_meeting_filter.currentIndexChanged.connect(self._refresh_calendar_candidates)
        self.calendar_meeting_filter.setMinimumWidth(0)
        calendar_header.addWidget(self.calendar_meeting_filter, 0, 1)
        self.export_all_calendar_button = QPushButton("Export visible dates")
        self.export_all_calendar_button.clicked.connect(self.export_all_calendar_ics)
        self.export_all_calendar_button.setMinimumWidth(0)
        calendar_header.addWidget(self.export_all_calendar_button, 0, 2)
        calendar_header.setColumnStretch(1, 1)
        panel_layout.addLayout(calendar_header)

        calendar_grid = QGridLayout()
        calendar_grid.setSpacing(16)
        calendar_side = QWidget()
        calendar_side.setObjectName("Transparent")
        calendar_side_layout = QVBoxLayout(calendar_side)
        calendar_side_layout.setContentsMargins(0, 0, 0, 0)
        calendar_side_layout.setSpacing(10)
        self.calendar_widget = InsightCalendarWidget()
        self.calendar_widget.setGridVisible(True)
        self.calendar_widget.setMinimumSize(560, 340)
        self.calendar_widget.clicked.connect(self._calendar_date_clicked)
        calendar_side_layout.addWidget(self.calendar_widget, stretch=1)
        self.calendar_day_summary = self._muted_label("Select a highlighted date to see its meeting items.")
        self.calendar_day_summary.setWordWrap(True)
        calendar_side_layout.addWidget(self.calendar_day_summary)
        calendar_grid.addWidget(calendar_side, 0, 0)
        right_side = QWidget()
        right_layout = QVBoxLayout(right_side)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.calendar_empty_state = self._empty_state_widget(
            "calendar",
            "No calendar candidates",
            "Detected dates from meetings will appear here.",
        )
        self.calendar_table = QTableWidget(0, 5)
        self.calendar_table.setMinimumWidth(0)
        self.calendar_table.setMinimumHeight(300)
        self.calendar_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.calendar_table.setHorizontalHeaderLabels(["Approved", "Meeting", "Date", "Context", "Confidence"])
        self._configure_table(self.calendar_table)
        self.calendar_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.calendar_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.calendar_table.verticalHeader().setVisible(False)
        self.calendar_table.itemSelectionChanged.connect(self._calendar_row_selected)
        self.calendar_table.itemChanged.connect(self._calendar_item_changed)
        calendar_table_header = self.calendar_table.horizontalHeader()
        calendar_table_header.setSectionResizeMode(0, QHeaderView.Fixed)
        calendar_table_header.setSectionResizeMode(1, QHeaderView.Fixed)
        calendar_table_header.setSectionResizeMode(2, QHeaderView.Fixed)
        calendar_table_header.setSectionResizeMode(3, QHeaderView.Stretch)
        calendar_table_header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.calendar_table.verticalHeader().setDefaultSectionSize(44)
        self.calendar_table.setColumnWidth(0, 88)
        self.calendar_table.setColumnWidth(1, 260)
        self.calendar_table.setColumnWidth(2, 190)
        self.calendar_table.setColumnWidth(4, 120)
        right_layout.addWidget(self.calendar_empty_state, stretch=1)
        right_layout.addWidget(self.calendar_table, stretch=1)
        calendar_grid.addWidget(right_side, 1, 0)
        calendar_grid.setColumnStretch(0, 1)
        calendar_grid.setRowStretch(0, 3)
        calendar_grid.setRowStretch(1, 2)
        panel_layout.addLayout(calendar_grid, stretch=1)
        review_tabs.addTab(panel, "Dates")
        review_tabs.addTab(self._build_actions_page(embedded=True), "Actions")
        layout.addWidget(review_tabs, stretch=1)
        return page

    def _build_actions_page(self, embedded: bool = False) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        if embedded:
            layout.setContentsMargins(0, 0, 0, 0)
        else:
            layout.setContentsMargins(34, 28, 18, 28)
        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        panel_layout.setSpacing(12)

        title = QLabel("Actions")
        title.setObjectName("Title")
        panel_layout.addWidget(title)
        panel_layout.addWidget(self._muted_label("Review open action items across meetings and update follow-up status."))

        filters = QGridLayout()
        filters.setHorizontalSpacing(10)
        filters.setVerticalSpacing(8)
        self.action_owner_filter = QLineEdit()
        self.action_owner_filter.setPlaceholderText("Filter owner")
        self.action_owner_filter.setMinimumHeight(38)
        self.action_owner_filter.textChanged.connect(self._refresh_action_dashboard)
        self.action_status_filter = QComboBox()
        self.action_status_filter.addItems(["Open work", "open", "in progress", "deferred", "done", "closed", "All statuses"])
        self.action_status_filter.setMinimumHeight(38)
        self.action_status_filter.setMinimumWidth(150)
        self.action_status_filter.currentIndexChanged.connect(self._refresh_action_dashboard)
        self.action_confidence_filter = QComboBox()
        self.action_confidence_filter.addItems(["All confidence", "High", "Medium", "Low"])
        self.action_confidence_filter.setMinimumHeight(38)
        self.action_confidence_filter.setMinimumWidth(160)
        self.action_confidence_filter.currentIndexChanged.connect(self._refresh_action_dashboard)
        filters.addWidget(QLabel("Owner"), 0, 0)
        filters.addWidget(self.action_owner_filter, 0, 1)
        filters.addWidget(QLabel("Status"), 0, 2)
        filters.addWidget(self.action_status_filter, 0, 3)
        filters.addWidget(QLabel("Confidence"), 0, 4)
        filters.addWidget(self.action_confidence_filter, 0, 5)
        filters.setColumnStretch(1, 1)
        panel_layout.addLayout(filters)

        self.actions_empty_state = self._empty_state_widget(
            "actions",
            "No action items",
            "Open follow-ups from processed meetings will appear here.",
        )
        self.action_dashboard_table = QTableWidget(0, 9)
        self.action_dashboard_table.setMinimumWidth(0)
        self.action_dashboard_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.action_dashboard_table.setHorizontalHeaderLabels(["Meeting", "Owner", "Action", "Due", "Confidence", "Status", "Done", "Edit", "Open"])
        self._configure_table(self.action_dashboard_table)
        self.action_dashboard_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.action_dashboard_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.action_dashboard_table.verticalHeader().setVisible(False)
        self.action_dashboard_table.verticalHeader().setDefaultSectionSize(46)
        action_header = self.action_dashboard_table.horizontalHeader()
        action_header.setSectionResizeMode(0, QHeaderView.Fixed)
        action_header.setSectionResizeMode(1, QHeaderView.Fixed)
        action_header.setSectionResizeMode(2, QHeaderView.Stretch)
        action_header.setSectionResizeMode(3, QHeaderView.Fixed)
        action_header.setSectionResizeMode(4, QHeaderView.Fixed)
        action_header.setSectionResizeMode(5, QHeaderView.Fixed)
        action_header.setSectionResizeMode(6, QHeaderView.Fixed)
        action_header.setSectionResizeMode(7, QHeaderView.Fixed)
        action_header.setSectionResizeMode(8, QHeaderView.Fixed)
        self.action_dashboard_table.setColumnWidth(0, 190)
        self.action_dashboard_table.setColumnWidth(1, 96)
        self.action_dashboard_table.setColumnWidth(3, 128)
        self.action_dashboard_table.setColumnWidth(4, 98)
        self.action_dashboard_table.setColumnWidth(5, 132)
        self.action_dashboard_table.setColumnWidth(6, 72)
        self.action_dashboard_table.setColumnWidth(7, 78)
        self.action_dashboard_table.setColumnWidth(8, 96)

        panel_layout.addWidget(self.actions_empty_state, stretch=1)
        panel_layout.addWidget(self.action_dashboard_table, stretch=1)
        layout.addWidget(panel)
        return page

    def _refresh_action_dashboard(self) -> None:
        if not hasattr(self, "action_dashboard_table"):
            return
        self.action_dashboard_table.setRowCount(0)
        for folder in self.meeting_store.list_meetings():
            try:
                metadata = self.meeting_store.read_metadata(folder)
                insights = load_or_build_insights(folder)
                self._auto_close_stale_actions(folder, metadata, insights)
            except Exception:
                continue
            for action_index, action in enumerate(insights.actions):
                if not self._action_matches_filters(action):
                    continue
                row = self.action_dashboard_table.rowCount()
                self.action_dashboard_table.insertRow(row)
                values = [
                    metadata.title or folder.name,
                    action.owner or "Unknown",
                    action.text,
                    action.due_date or "Unknown",
                    action.confidence or "",
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.UserRole, str(folder))
                    item.setData(Qt.UserRole + 1, action_index)
                    self.action_dashboard_table.setItem(row, column, item)

                status_combo = QComboBox()
                status_combo.addItems(["open", "in progress", "done", "deferred", "closed"])
                status_combo.setCurrentText(action.status or "open")
                status_combo.setMinimumHeight(34)
                status_combo.setMinimumWidth(0)
                status_combo.setFixedWidth(120)
                status_combo.currentTextChanged.connect(
                    lambda status, action_index=action_index, meeting_folder=folder: self._update_action_status(
                        meeting_folder, action_index, status,
                    )
                )
                self.action_dashboard_table.setCellWidget(row, 5, status_combo)

                done_button = QPushButton("Done")
                done_button.setObjectName("SubtleActionButton")
                done_button.setFixedSize(60, 28)
                done_button.clicked.connect(lambda checked=False, meeting_folder=folder, action_index=action_index: self._update_action_status(meeting_folder, action_index, "done"))
                done_item = QTableWidgetItem("")
                done_item.setData(Qt.UserRole, str(folder))
                done_item.setData(Qt.UserRole + 1, action_index)
                self.action_dashboard_table.setItem(row, 6, done_item)
                self.action_dashboard_table.setCellWidget(row, 6, done_button)

                edit_button = QPushButton("Edit")
                edit_button.setObjectName("SubtleActionButton")
                edit_button.setFixedSize(62, 28)
                edit_button.clicked.connect(lambda checked=False, meeting_folder=folder, action_index=action_index: self.edit_action_item(meeting_folder, action_index))
                edit_item = QTableWidgetItem("")
                edit_item.setData(Qt.UserRole, str(folder))
                edit_item.setData(Qt.UserRole + 1, action_index)
                self.action_dashboard_table.setItem(row, 7, edit_item)
                self.action_dashboard_table.setCellWidget(row, 7, edit_button)

                open_button = QPushButton("Open")
                open_button.setObjectName("TableActionButton")
                open_button.setFixedSize(82, 28)
                open_button.clicked.connect(lambda checked=False, meeting_folder=folder: self.open_meeting_overview(meeting_folder))
                open_item = QTableWidgetItem("")
                open_item.setData(Qt.UserRole, str(folder))
                open_item.setData(Qt.UserRole + 1, action_index)
                self.action_dashboard_table.setItem(row, 8, open_item)
                self.action_dashboard_table.setCellWidget(row, 8, open_button)
                self.action_dashboard_table.setRowHeight(row, 38)
        has_rows = self.action_dashboard_table.rowCount() > 0
        self.action_dashboard_table.setVisible(has_rows)
        self.actions_empty_state.setVisible(not has_rows)

    def _auto_close_stale_actions(self, folder: Path, metadata: MeetingMetadata, insights: MeetingInsights) -> None:
        days = int(self.settings.get("review", {}).get("action_auto_close_days", 30) or 0)
        if days <= 0 or not insights.actions:
            return
        try:
            started_at = datetime.fromisoformat(metadata.started_at)
        except ValueError:
            return
        age_days = (datetime.now() - started_at).days
        if age_days < days:
            return

        changed = False
        for action in insights.actions:
            if (action.status or "open").lower() not in CLOSED_ACTION_STATUSES:
                action.status = "closed"
                changed = True
        if changed:
            write_insights_json(folder, insights)
            self.log(f"Auto-closed stale action item(s) older than {days} day(s): {metadata.title or folder.name}")

    def _action_matches_filters(self, action: InsightItem) -> bool:
        status_filter = self.action_status_filter.currentText() if hasattr(self, "action_status_filter") else "Open work"
        status = (action.status or "open").lower()
        if status_filter == "Open work" and status in CLOSED_ACTION_STATUSES:
            return False
        if status_filter not in {"Open work", "All statuses"} and status != status_filter.lower():
            return False

        owner_filter = self.action_owner_filter.text().strip().lower() if hasattr(self, "action_owner_filter") else ""
        owner = (action.owner or "Unknown").lower()
        if owner_filter and owner_filter not in owner:
            return False

        confidence_filter = self.action_confidence_filter.currentText() if hasattr(self, "action_confidence_filter") else "All confidence"
        if confidence_filter != "All confidence" and (action.confidence or "").lower() != confidence_filter.lower():
            return False
        return True

    def _populate_calendar_meeting_filter(self) -> None:
        if not hasattr(self, "calendar_meeting_filter"):
            return
        current_value = self.calendar_meeting_filter.currentData()
        self.calendar_meeting_filter.blockSignals(True)
        self.calendar_meeting_filter.clear()
        self.calendar_meeting_filter.addItem("All meetings", "")
        for folder in self.meeting_store.list_meetings():
            try:
                metadata = self.meeting_store.read_metadata(folder)
                label = f"{metadata.title or folder.name} - {metadata.started_at[:10]}"
            except Exception:
                label = folder.name
            self.calendar_meeting_filter.addItem(label, str(folder))
        from app.ui.widgets import select_combo_by_data
        select_combo_by_data(self.calendar_meeting_filter, str(current_value or ""))
        self.calendar_meeting_filter.blockSignals(False)

    def _calendar_filter_folders(self) -> list[Path]:
        if not hasattr(self, "calendar_meeting_filter"):
            return self.meeting_store.list_meetings()
        selected = str(self.calendar_meeting_filter.currentData() or "")
        if selected:
            return [Path(selected)]
        return self.meeting_store.list_meetings()

    def _refresh_calendar_candidates(self) -> None:
        self.calendar_table.blockSignals(True)
        self.calendar_table.setRowCount(0)
        for folder in self._calendar_filter_folders():
            try:
                metadata = self.meeting_store.read_metadata(folder)
                insights = load_or_build_insights(folder)
                review = read_calendar_review(folder)
            except Exception:
                continue
            for date_item in insights.dates:
                key = candidate_key(date_item)
                override = review.get(key, {}) if isinstance(review.get(key, {}), dict) else {}
                approved = bool(override.get("approved", False))
                row = self.calendar_table.rowCount()
                self.calendar_table.insertRow(row)
                values = [
                    "",
                    metadata.title or folder.name,
                    str(override.get("date_text") or date_item.due_date or date_item.text),
                    str(override.get("context") or date_item.context or date_item.text),
                    date_item.confidence or "",
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.UserRole, str(folder))
                    item.setData(Qt.UserRole + 1, key)
                    if column == 0:
                        item.setFlags((item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
                        item.setCheckState(Qt.Checked if approved else Qt.Unchecked)
                    elif column not in (2, 3):
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.calendar_table.setItem(row, column, item)
                self.calendar_table.setRowHeight(row, 36)
        self.calendar_table.blockSignals(False)
        has_rows = self.calendar_table.rowCount() > 0
        self.calendar_table.setVisible(has_rows)
        self.calendar_empty_state.setVisible(not has_rows)
        self._sync_calendar_day_items_from_table()

    def _calendar_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() not in (0, 2, 3):
            return
        folder_raw = item.data(Qt.UserRole)
        key = item.data(Qt.UserRole + 1)
        if not folder_raw or not key:
            return
        folder = Path(str(folder_raw))
        review = read_calendar_review(folder)
        entry = review.get(str(key), {}) if isinstance(review.get(str(key), {}), dict) else {}
        row = item.row()
        approved_item = self.calendar_table.item(row, 0)
        date_item = self.calendar_table.item(row, 2)
        context_item = self.calendar_table.item(row, 3)
        entry["approved"] = approved_item.checkState() == Qt.Checked if approved_item else False
        entry["date_text"] = date_item.text().strip() if date_item else ""
        entry["context"] = context_item.text().strip() if context_item else ""
        review[str(key)] = entry
        write_calendar_review(folder, review)
        self._sync_calendar_day_items_from_table()

    def _sync_calendar_day_items_from_table(self) -> None:
        if not hasattr(self, "calendar_widget"):
            return
        items_by_date: dict[str, list[dict[str, object]]] = {}
        for row in range(self.calendar_table.rowCount()):
            meeting_item = self.calendar_table.item(row, 1)
            date_item = self.calendar_table.item(row, 2)
            context_item = self.calendar_table.item(row, 3)
            approved_item = self.calendar_table.item(row, 0)
            confidence_item = self.calendar_table.item(row, 4)
            if not meeting_item or not date_item:
                continue
            folder = Path(str(meeting_item.data(Qt.UserRole) or ""))
            try:
                metadata = self.meeting_store.read_metadata(folder)
            except Exception:
                metadata = None
            qdate = self._calendar_qdate_from_text(date_item.text(), metadata)
            if not qdate or not qdate.isValid():
                continue
            key = qdate.toString("yyyy-MM-dd")
            items_by_date.setdefault(key, []).append(
                {
                    "row": row,
                    "title": meeting_item.text(),
                    "date": date_item.text(),
                    "context": context_item.text() if context_item else "",
                    "approved": approved_item.checkState() == Qt.Checked if approved_item else False,
                    "confidence": confidence_item.text() if confidence_item else "",
                }
            )
        self.calendar_day_items = items_by_date
        self.calendar_widget.set_items_by_date(items_by_date)
        selected_key = self.calendar_widget.selectedDate().toString("yyyy-MM-dd")
        self._update_calendar_day_summary(selected_key)

    def _calendar_date_clicked(self, date: QDate) -> None:
        key = date.toString("yyyy-MM-dd")
        self._update_calendar_day_summary(key)
        items = getattr(self, "calendar_day_items", {}).get(key, [])
        if items:
            row = int(items[0].get("row", 0))
            self.calendar_table.selectRow(row)

    def _update_calendar_day_summary(self, date_key: str) -> None:
        if not hasattr(self, "calendar_day_summary"):
            return
        items = getattr(self, "calendar_day_items", {}).get(date_key, [])
        if not items:
            self.calendar_day_summary.setText("No detected meeting items on this date.")
            return
        lines = []
        for item in items[:3]:
            status = "approved" if item.get("approved") else "pending"
            context = str(item.get("context") or "").strip()
            title = str(item.get("title") or "Meeting")
            lines.append(f"{title}: {context[:70] or 'Calendar item'} ({status})")
        if len(items) > 3:
            lines.append(f"+ {len(items) - 3} more")
        self.calendar_day_summary.setText("\n".join(lines))

    def _calendar_row_selected(self) -> None:
        if not hasattr(self, "calendar_widget"):
            return
        selected = self.calendar_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        date_item = self.calendar_table.item(row, 2)
        meeting_item = self.calendar_table.item(row, 1)
        if not date_item or not meeting_item:
            return
        folder = Path(str(meeting_item.data(Qt.UserRole) or ""))
        try:
            metadata = self.meeting_store.read_metadata(folder)
        except Exception:
            metadata = None
        qdate = self._calendar_qdate_from_text(date_item.text(), metadata)
        if qdate and qdate.isValid():
            self.calendar_widget.setSelectedDate(qdate)
            self.calendar_widget.showSelectedDate()
            self._update_calendar_day_summary(qdate.toString("yyyy-MM-dd"))

    @staticmethod
    def _calendar_qdate_from_text(text: str, metadata: MeetingMetadata | None) -> QDate | None:
        cleaned = re.sub(r"\s+", " ", text.strip())
        if not cleaned:
            return None
        base = None
        if metadata:
            try:
                base = datetime.fromisoformat(metadata.started_at)
            except ValueError:
                base = None
        if cleaned.lower() == "tomorrow" and base:
            target = base.toordinal() + 1
            value = datetime.fromordinal(target)
            return QDate(value.year, value.month, value.day)
        formats = ["%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%A, %B %d, %Y", "%A, %B %d", "%B %d", "%b %d"]
        for fmt in formats:
            try:
                value = datetime.strptime(cleaned, fmt)
                year = value.year if "%Y" in fmt else (base.year if base else datetime.now().year)
                return QDate(year, value.month, value.day)
            except ValueError:
                continue
        return None

    def export_selected_calendar_ics(self) -> None:
        folder = self._selected_meeting_folder()
        if folder is None:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Nova Notetaker", "Select a meeting to export dates.")
            return
        path = self._export_calendar_ics_for_folders([folder], folder / "calendar_candidates.ics")
        if path:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Nova Notetaker", f"Calendar candidates exported:\n{path}")
            self.log(f"Exported calendar candidates: {path}")

    def export_all_calendar_ics(self) -> None:
        folders = self._calendar_filter_folders()
        selected_label = "all" if len(folders) != 1 else safe_file_label(folders[0].name)
        path = self._export_calendar_ics_for_folders(folders, self.meeting_store.meetings_root / f"nova_calendar_candidates_{selected_label}.ics")
        if path:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Nova Notetaker", f"Calendar candidates exported:\n{path}")
            self.log(f"Exported calendar candidates: {path}")

    def _export_calendar_ics_for_folders(self, folders: list[Path], output_path: Path) -> Path | None:
        items: list[tuple[MeetingMetadata, InsightItem, str, str]] = []
        for folder in folders:
            try:
                metadata = self.meeting_store.read_metadata(folder)
                insights = load_or_build_insights(folder)
                review = read_calendar_review(folder)
                for date_item in insights.dates:
                    override = review.get(candidate_key(date_item), {}) if isinstance(review.get(candidate_key(date_item), {}), dict) else {}
                    if not override.get("approved", False):
                        continue
                    items.append(
                        (
                            metadata,
                            date_item,
                            str(override.get("date_text") or date_item.due_date or date_item.text),
                            str(override.get("context") or date_item.context or date_item.text),
                        )
                    )
            except Exception as error:
                self.log(f"Skipping calendar export for {folder.name}: {error}")
        if not items:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Nova Notetaker", "No approved calendar candidates found.")
            return None

        now_stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Nova Notetaker//Meeting Intelligence//EN",
            "CALSCALE:GREGORIAN",
        ]
        for index, (metadata, date_item, date_text, context) in enumerate(items, start=1):
            title = f"{metadata.title or 'Nova meeting'} - {context}"
            description = f"Meeting: {metadata.title or 'Untitled'}\\nApproved date: {date_text}\\nConfidence: {date_item.confidence or 'Unknown'}"
            lines.extend(
                [
                    "BEGIN:VTODO",
                    f"UID:nova-{now_stamp}-{index}@nova-notetaker",
                    f"DTSTAMP:{now_stamp}",
                    f"SUMMARY:{ics_escape(title)}",
                    f"DESCRIPTION:{ics_escape(description)}",
                    "STATUS:NEEDS-ACTION",
                    "END:VTODO",
                ]
            )
        lines.append("END:VCALENDAR")
        output_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        return output_path
