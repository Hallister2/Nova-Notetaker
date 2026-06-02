from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.intelligence.insights import InsightItem, MeetingInsights, load_or_build_insights, write_insights_json
from app.storage.meeting_store import MeetingMetadata
from app.ui.constants import CLOSED_ACTION_STATUSES
from app.ui.styles import build_stylesheet


class ReviewTabMixin:
    def _build_review_queue_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 28, 18, 28)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("Review Queue")
        title.setObjectName("Title")
        title_block.addWidget(title)
        title_block.addWidget(self._muted_label("Today view for stuck meetings, pinned work, due actions, and recent output."))
        header.addLayout(title_block)
        header.addStretch()
        self.review_refresh_button = QPushButton("Refresh")
        self.review_refresh_button.clicked.connect(self.refresh_review_center)
        header.addWidget(self.review_refresh_button)
        layout.addLayout(header)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(10)
        metrics.setVerticalSpacing(10)
        self.review_metric_attention = QLabel("0")
        self.review_metric_failed = QLabel("0")
        self.review_metric_due = QLabel("0")
        self.review_metric_pinned = QLabel("0")
        metrics.addWidget(self._metric_card("Needs attention", self.review_metric_attention), 0, 0)
        metrics.addWidget(self._metric_card("Repair / failed", self.review_metric_failed), 0, 1)
        metrics.addWidget(self._metric_card("Due soon", self.review_metric_due), 0, 2)
        metrics.addWidget(self._metric_card("Pinned", self.review_metric_pinned), 0, 3)
        layout.addLayout(metrics)

        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)
        panel_layout.setSpacing(12)
        panel_layout.addWidget(self._section_label("Meeting queue"))
        self.review_meetings_table = QTableWidget(0, 7)
        self.review_meetings_table.setHorizontalHeaderLabels(["Priority", "Meeting", "Status", "Readiness", "Actions", "Review", "Open"])
        self.review_meetings_table.setMinimumWidth(0)
        self.review_meetings_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._configure_table(self.review_meetings_table)
        self.review_meetings_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.review_meetings_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.review_meetings_table.itemDoubleClicked.connect(lambda _item: self._open_review_queue_meeting())
        self.review_meetings_table.verticalHeader().setVisible(False)
        self.review_meetings_table.verticalHeader().setDefaultSectionSize(44)
        review_header = self.review_meetings_table.horizontalHeader()
        review_header.setSectionResizeMode(0, QHeaderView.Fixed)
        review_header.setSectionResizeMode(1, QHeaderView.Stretch)
        review_header.setSectionResizeMode(2, QHeaderView.Fixed)
        review_header.setSectionResizeMode(3, QHeaderView.Fixed)
        review_header.setSectionResizeMode(4, QHeaderView.Fixed)
        review_header.setSectionResizeMode(5, QHeaderView.Fixed)
        review_header.setSectionResizeMode(6, QHeaderView.Fixed)
        self.review_meetings_table.setColumnWidth(0, 90)
        self.review_meetings_table.setColumnWidth(2, 150)
        self.review_meetings_table.setColumnWidth(3, 90)
        self.review_meetings_table.setColumnWidth(4, 72)
        self.review_meetings_table.setColumnWidth(5, 72)
        self.review_meetings_table.setColumnWidth(6, 92)
        panel_layout.addWidget(self.review_meetings_table, stretch=2)

        panel_layout.addWidget(self._section_label("Due and owner cleanup"))
        self.review_actions_table = QTableWidget(0, 7)
        self.review_actions_table.setHorizontalHeaderLabels(["Meeting", "Owner", "Action", "Due", "Status", "Done", "Open"])
        self.review_actions_table.setMinimumWidth(0)
        self.review_actions_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._configure_table(self.review_actions_table)
        self.review_actions_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.review_actions_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.review_actions_table.verticalHeader().setVisible(False)
        self.review_actions_table.verticalHeader().setDefaultSectionSize(42)
        action_header = self.review_actions_table.horizontalHeader()
        action_header.setSectionResizeMode(0, QHeaderView.Fixed)
        action_header.setSectionResizeMode(1, QHeaderView.Fixed)
        action_header.setSectionResizeMode(2, QHeaderView.Stretch)
        action_header.setSectionResizeMode(3, QHeaderView.Fixed)
        action_header.setSectionResizeMode(4, QHeaderView.Fixed)
        action_header.setSectionResizeMode(5, QHeaderView.Fixed)
        action_header.setSectionResizeMode(6, QHeaderView.Fixed)
        self.review_actions_table.setColumnWidth(0, 190)
        self.review_actions_table.setColumnWidth(1, 110)
        self.review_actions_table.setColumnWidth(3, 140)
        self.review_actions_table.setColumnWidth(4, 96)
        self.review_actions_table.setColumnWidth(5, 72)
        self.review_actions_table.setColumnWidth(6, 82)
        panel_layout.addWidget(self.review_actions_table, stretch=1)
        layout.addWidget(panel, stretch=1)
        return page

    def refresh_review_center(self) -> None:
        if hasattr(self, "action_dashboard_table"):
            self._refresh_action_dashboard()
        if hasattr(self, "review_meetings_table"):
            self._refresh_review_queue()
        if hasattr(self, "calendar_table"):
            self._populate_calendar_meeting_filter()
            self._refresh_calendar_candidates()

    def _refresh_review_queue(self) -> None:
        self.review_meetings_table.setRowCount(0)
        self.review_actions_table.setRowCount(0)
        attention_count = 0
        failed_count = 0
        due_soon_count = 0
        pinned_count = 0
        recent_rows: list[tuple[int, Path, MeetingMetadata, MeetingInsights, str, int, int, bool]] = []

        for folder in self.meeting_store.list_meetings():
            try:
                metadata = self.meeting_store.read_metadata(folder)
                insights = load_or_build_insights(folder)
            except Exception:
                continue
            open_actions = sum(1 for item in insights.actions if item.status.lower() not in CLOSED_ACTION_STATUSES)
            review_count = len(insights.quality_warnings) + len(insights.warnings)
            has_transcript = self._meeting_has_transcript(folder)
            status_label = self._meeting_status_label(metadata.status, review_count, has_transcript)
            score, _score_lines = self._meeting_readiness_score(folder, metadata, insights)
            pinned = self._meeting_is_important(folder)
            needs_repair = status_label in {"Processing failed", "Missing transcript"} or not (folder / "notes.md").exists()
            priority = self._review_priority(pinned, needs_repair, review_count, open_actions, score)
            if pinned:
                pinned_count += 1
            if needs_repair:
                failed_count += 1
            if needs_repair or review_count or open_actions:
                attention_count += 1
                recent_rows.append((priority, folder, metadata, insights, status_label, open_actions, review_count, pinned))
            elif len(recent_rows) < 8:
                recent_rows.append((priority, folder, metadata, insights, status_label, open_actions, review_count, pinned))

            for action_index, action in enumerate(insights.actions):
                if action.status.lower() in CLOSED_ACTION_STATUSES:
                    continue
                if self._action_is_due_soon(action) or not action.owner or action.owner.lower() == "unknown":
                    if self._action_is_due_soon(action):
                        due_soon_count += 1
                    self._add_review_action_row(folder, metadata, action, action_index)

        for _priority, folder, metadata, insights, status_label, open_actions, review_count, pinned in sorted(recent_rows, key=lambda item: item[0])[:12]:
            self._add_review_meeting_row(folder, metadata, insights, status_label, open_actions, review_count, pinned)

        self.review_metric_attention.setText(str(attention_count))
        self.review_metric_failed.setText(str(failed_count))
        self.review_metric_due.setText(str(due_soon_count))
        self.review_metric_pinned.setText(str(pinned_count))

    @staticmethod
    def _review_priority(pinned: bool, needs_repair: bool, review_count: int, open_actions: int, score: int) -> int:
        priority = 0 if pinned else 100
        priority += 0 if needs_repair else 25
        priority += max(0, 30 - min(review_count, 30))
        priority += max(0, 20 - min(open_actions, 20))
        priority += score
        return priority

    def _add_review_meeting_row(
        self,
        folder: Path,
        metadata: MeetingMetadata,
        insights: MeetingInsights,
        status_label: str,
        open_actions: int,
        review_count: int,
        pinned: bool,
    ) -> None:
        row = self.review_meetings_table.rowCount()
        self.review_meetings_table.insertRow(row)
        score, _score_lines = self._meeting_readiness_score(folder, metadata, insights)
        values = [
            "Pinned" if pinned else ("Repair" if status_label in {"Processing failed", "Missing transcript"} else "Review"),
            metadata.title or folder.name,
            status_label,
            f"{score}%",
            str(open_actions),
            str(review_count),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(Qt.UserRole, str(folder))
            if column in (0, 2, 3, 4, 5):
                item.setTextAlignment(Qt.AlignCenter)
            self.review_meetings_table.setItem(row, column, item)
        open_button = QPushButton("Open")
        open_button.setObjectName("TableActionButton")
        open_button.setFixedSize(76, 30)
        open_button.clicked.connect(lambda checked=False, meeting_folder=folder: self.open_meeting_overview(meeting_folder))
        open_item = QTableWidgetItem("")
        open_item.setData(Qt.UserRole, str(folder))
        self.review_meetings_table.setItem(row, 6, open_item)
        self.review_meetings_table.setCellWidget(row, 6, open_button)

    def _add_review_action_row(self, folder: Path, metadata: MeetingMetadata, action: InsightItem, action_index: int) -> None:
        row = self.review_actions_table.rowCount()
        self.review_actions_table.insertRow(row)
        values = [
            metadata.title or folder.name,
            action.owner or "Unknown",
            action.text,
            action.due_date or "Unknown",
            action.status or "open",
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(Qt.UserRole, str(folder))
            item.setData(Qt.UserRole + 1, action_index)
            if column in (1, 3, 4):
                item.setTextAlignment(Qt.AlignCenter)
            self.review_actions_table.setItem(row, column, item)
        done_button = QPushButton("Done")
        done_button.setObjectName("SubtleActionButton")
        done_button.setFixedSize(60, 28)
        done_button.clicked.connect(lambda checked=False, meeting_folder=folder, index=action_index: self._update_action_status(meeting_folder, index, "done"))
        self.review_actions_table.setCellWidget(row, 5, done_button)
        open_button = QPushButton("Open")
        open_button.setObjectName("TableActionButton")
        open_button.setFixedSize(72, 28)
        open_button.clicked.connect(lambda checked=False, meeting_folder=folder: self.open_meeting_overview(meeting_folder))
        self.review_actions_table.setCellWidget(row, 6, open_button)

    def _open_review_queue_meeting(self) -> None:
        item = self.review_meetings_table.currentItem()
        if item is None:
            return
        folder_value = item.data(Qt.UserRole)
        if folder_value:
            self.open_meeting_overview(Path(str(folder_value)))

    def _action_is_due_soon(self, action: InsightItem, days: int = 7) -> bool:
        due_date = self._calendar_qdate_from_text(action.due_date, None)
        if due_date is None:
            return False
        delta = QDate.currentDate().daysTo(due_date)
        return 0 <= delta <= days

    def _update_action_status(self, folder: Path, action_index: int, status: str) -> None:
        insights = load_or_build_insights(folder)
        if action_index >= len(insights.actions):
            return
        insights.actions[action_index].status = status
        insights.quality_warnings = self._quality_warnings_for_actions(insights)
        write_insights_json(folder, insights)
        self.refresh_meetings()
        self.refresh_review_center()
        self.log(f"Updated action status to {status}: {folder.name}")

    @staticmethod
    def _quality_warnings_for_actions(insights: MeetingInsights) -> list[str]:
        warnings = [warning for warning in insights.quality_warnings if "action item" not in warning.lower()]
        unknown_owner_count = sum(1 for item in insights.actions if not item.owner or item.owner.lower() == "unknown")
        unknown_due_count = sum(1 for item in insights.actions if not item.due_date or item.due_date.lower() == "unknown")
        if unknown_owner_count:
            warnings.append(f"{unknown_owner_count} action item(s) need an owner.")
        if unknown_due_count:
            warnings.append(f"{unknown_due_count} action item(s) do not have a due date.")
        return warnings

    def edit_action_item(self, folder: Path, action_index: int) -> None:
        insights = load_or_build_insights(folder)
        if action_index >= len(insights.actions):
            return
        item = insights.actions[action_index]
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Action Item")
        dialog.setStyleSheet(build_stylesheet(self.current_theme))
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        owner_edit = QLineEdit(item.owner or "Unknown")
        due_edit = QLineEdit(item.due_date or "Unknown")
        task_edit = QTextEdit()
        task_edit.setPlainText(item.text)
        task_edit.setMinimumHeight(90)
        confidence_combo = QComboBox()
        confidence_combo.addItems(["High", "Medium", "Low", "Tentative", ""])
        confidence_combo.setCurrentText(item.confidence if item.confidence in {"High", "Medium", "Low", "Tentative"} else "")
        status_combo = QComboBox()
        status_combo.addItems(["open", "in progress", "done", "deferred", "closed"])
        status_combo.setCurrentText(item.status or "open")
        form.addRow("Owner", owner_edit)
        form.addRow("Due", due_edit)
        form.addRow("Confidence", confidence_combo)
        form.addRow("Status", status_combo)
        form.addRow("Task", task_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        item.owner = owner_edit.text().strip() or "Unknown"
        item.due_date = due_edit.text().strip() or "Unknown"
        item.text = task_edit.toPlainText().strip() or item.text
        item.confidence = confidence_combo.currentText().strip()
        item.status = status_combo.currentText().strip() or "open"
        insights.quality_warnings = self._quality_warnings_for_actions(insights)
        write_insights_json(folder, insights)
        self.refresh_meetings()
        self.refresh_review_center()
        self._refresh_action_dashboard()
        self.log(f"Edited action item: {folder.name}")
