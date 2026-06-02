from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.profiles import MeetingProfile
from app.core.settings import save_settings
from app.core.templates import NoteTemplate
from app.ui.widgets import select_combo_by_data


class TemplatesTabMixin:
    def _build_templates_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.templates_page_layout = layout
        layout.setContentsMargins(34, 28, 18, 28)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        self.templates_content_layout = content_layout
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        title = QLabel("Templates")
        title.setObjectName("Title")
        content_layout.addWidget(title)
        content_layout.addWidget(self._muted_label("Edit meeting profiles for context and note templates for output style."))

        from PySide6.QtWidgets import QTabWidget
        template_tabs = QTabWidget()
        template_tabs.addTab(self._build_meeting_profiles_section(), "Meeting profiles")
        template_tabs.addTab(self._build_note_templates_section(), "Note templates")
        content_layout.addWidget(template_tabs, stretch=1)
        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.active_profile_id = ""
        self.active_template_id = ""
        self.refresh_profiles_table()
        self.refresh_templates_table()
        return page

    def _build_meeting_profiles_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("Panel")
        layout = QGridLayout(section)
        self.profile_section_layout = layout
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        list_panel = QWidget()
        self.profile_list_panel = list_panel
        list_panel.setObjectName("Transparent")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(8)
        title = QLabel("Meeting profiles")
        title.setObjectName("PanelTitle")
        list_layout.addWidget(title)
        list_layout.addWidget(self._muted_label("Profiles tell Nova what kind of meeting this is and what context matters."))

        self.profiles_table = QTableWidget(0, 2)
        self.profiles_table.setHorizontalHeaderLabels(["Profile", "Category"])
        self._configure_table(self.profiles_table)
        self.profiles_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.profiles_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.profiles_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.profiles_table.verticalHeader().setVisible(False)
        self.profiles_table.horizontalHeader().setStretchLastSection(True)
        self.profiles_table.setMinimumHeight(125)
        self.profiles_table.itemSelectionChanged.connect(self._profile_row_selected)
        list_layout.addWidget(self.profiles_table, stretch=1)

        list_buttons = QHBoxLayout()
        self.new_profile_button = QPushButton("New profile")
        self.new_profile_button.clicked.connect(self.new_profile)
        self.duplicate_profile_button = QPushButton("Duplicate")
        self.duplicate_profile_button.clicked.connect(self.duplicate_profile)
        self.preview_profile_button = QPushButton("Preview")
        self.preview_profile_button.clicked.connect(self.preview_profile_prompt)
        self.delete_profile_button = QPushButton("Delete")
        self.delete_profile_button.clicked.connect(self.delete_profile)
        list_buttons.addWidget(self.new_profile_button)
        list_buttons.addWidget(self.duplicate_profile_button)
        list_buttons.addWidget(self.preview_profile_button)
        list_buttons.addWidget(self.delete_profile_button)
        list_layout.addLayout(list_buttons)

        editor_panel = QWidget()
        self.profile_editor_panel = editor_panel
        editor_panel.setObjectName("Transparent")
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        editor_title = QLabel("Profile editor")
        editor_title.setObjectName("SectionTitle")
        editor_layout.addWidget(editor_title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(7)
        self.profile_name_edit = QLineEdit()
        self.profile_category_edit = QLineEdit()
        self.profile_company_conducting_edit = QLineEdit()
        self.profile_companies_attending_edit = QLineEdit()
        self.profile_title_prefix_edit = QLineEdit()
        self.profile_default_template_combo = QComboBox()
        self._populate_profile_default_template_combo()
        self.profile_context_edit = QTextEdit()
        self.profile_context_edit.setMaximumHeight(74)
        self.profile_focus_edit = QTextEdit()
        self.profile_focus_edit.setMaximumHeight(74)
        form.addRow("Name", self.profile_name_edit)
        form.addRow("Category", self.profile_category_edit)
        form.addRow("Company conducting", self.profile_company_conducting_edit)
        form.addRow("Companies attending", self.profile_companies_attending_edit)
        form.addRow("Title prefix", self.profile_title_prefix_edit)
        form.addRow("Default note template", self.profile_default_template_combo)
        form.addRow("AI context", self.profile_context_edit)
        form.addRow("Notes focus", self.profile_focus_edit)
        editor_layout.addLayout(form)

        save_row = QHBoxLayout()
        self.save_profile_button = QPushButton("Save profile")
        self.save_profile_button.setObjectName("PrimaryButton")
        self.save_profile_button.clicked.connect(self.save_profile)
        save_row.addStretch()
        save_row.addWidget(self.save_profile_button)
        editor_layout.addLayout(save_row)

        layout.addWidget(list_panel, 0, 0)
        layout.addWidget(editor_panel, 0, 1)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 2)
        return section

    def _build_note_templates_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("Panel")
        layout = QGridLayout(section)
        self.template_section_layout = layout
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        list_panel = QWidget()
        self.template_list_panel = list_panel
        list_panel.setObjectName("Transparent")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(8)
        title = QLabel("Note templates")
        title.setObjectName("PanelTitle")
        list_layout.addWidget(title)
        list_layout.addWidget(self._muted_label("Templates control the generated notes structure, tone, and preferred sections."))

        self.templates_table = QTableWidget(0, 2)
        self.templates_table.setHorizontalHeaderLabels(["Template", "Category"])
        self._configure_table(self.templates_table)
        self.templates_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.templates_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.templates_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.templates_table.verticalHeader().setVisible(False)
        self.templates_table.horizontalHeader().setStretchLastSection(True)
        self.templates_table.setMinimumHeight(125)
        self.templates_table.itemSelectionChanged.connect(self._template_row_selected)
        list_layout.addWidget(self.templates_table, stretch=1)

        list_buttons = QHBoxLayout()
        self.new_template_button = QPushButton("New template")
        self.new_template_button.clicked.connect(self.new_template)
        self.duplicate_template_button = QPushButton("Duplicate")
        self.duplicate_template_button.clicked.connect(self.duplicate_template)
        self.preview_template_button = QPushButton("Preview")
        self.preview_template_button.clicked.connect(self.preview_template_prompt)
        self.delete_template_button = QPushButton("Delete")
        self.delete_template_button.clicked.connect(self.delete_template)
        list_buttons.addWidget(self.new_template_button)
        list_buttons.addWidget(self.duplicate_template_button)
        list_buttons.addWidget(self.preview_template_button)
        list_buttons.addWidget(self.delete_template_button)
        list_layout.addLayout(list_buttons)

        editor_panel = QWidget()
        self.template_editor_panel = editor_panel
        editor_panel.setObjectName("Transparent")
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        editor_title = QLabel("Template editor")
        editor_title.setObjectName("SectionTitle")
        editor_layout.addWidget(editor_title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(7)
        self.template_name_edit = QLineEdit()
        self.template_category_edit = QLineEdit()
        self.template_description_edit = QLineEdit()
        self.template_sections_edit = QLineEdit()
        self.template_focus_edit = QTextEdit()
        self.template_focus_edit.setMaximumHeight(72)
        self.template_custom_edit = QTextEdit()
        self.template_custom_edit.setMaximumHeight(86)
        form.addRow("Name", self.template_name_edit)
        form.addRow("Category", self.template_category_edit)
        form.addRow("Description", self.template_description_edit)
        form.addRow("Preferred sections", self.template_sections_edit)
        form.addRow("Notes focus", self.template_focus_edit)
        form.addRow("Custom instructions", self.template_custom_edit)
        editor_layout.addLayout(form)

        save_row = QHBoxLayout()
        self.save_template_button = QPushButton("Save template")
        self.save_template_button.setObjectName("PrimaryButton")
        self.save_template_button.clicked.connect(self.save_template)
        save_row.addStretch()
        save_row.addWidget(self.save_template_button)
        editor_layout.addLayout(save_row)

        layout.addWidget(list_panel, 0, 0)
        layout.addWidget(editor_panel, 0, 1)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 2)
        return section

    def _apply_templates_responsive(self, mode: str) -> None:
        if not hasattr(self, "profile_section_layout"):
            return

        if mode == "narrow":
            margins = (16, 18, 12, 18)
            section_margins = (12, 12, 12, 12)
            spacing = 10
            stack_sections = True
        elif mode == "compact":
            margins = (22, 22, 14, 22)
            section_margins = (12, 12, 12, 12)
            spacing = 12
            stack_sections = True
        elif mode == "medium":
            margins = (28, 24, 16, 24)
            section_margins = (14, 14, 14, 14)
            spacing = 14
            stack_sections = False
        else:
            margins = (34, 28, 18, 28)
            section_margins = (14, 14, 14, 14)
            spacing = 14
            stack_sections = False

        self.templates_page_layout.setContentsMargins(*margins)
        self.templates_content_layout.setSpacing(spacing)
        for section_layout in (self.profile_section_layout, self.template_section_layout):
            section_layout.setContentsMargins(*section_margins)
            section_layout.setSpacing(spacing)

        if stack_sections:
            self.profile_section_layout.addWidget(self.profile_list_panel, 0, 0)
            self.profile_section_layout.addWidget(self.profile_editor_panel, 1, 0)
            self.profile_section_layout.setColumnStretch(0, 1)
            self.profile_section_layout.setColumnStretch(1, 0)
            self.template_section_layout.addWidget(self.template_list_panel, 0, 0)
            self.template_section_layout.addWidget(self.template_editor_panel, 1, 0)
            self.template_section_layout.setColumnStretch(0, 1)
            self.template_section_layout.setColumnStretch(1, 0)
        else:
            self.profile_section_layout.addWidget(self.profile_list_panel, 0, 0)
            self.profile_section_layout.addWidget(self.profile_editor_panel, 0, 1)
            self.profile_section_layout.setColumnStretch(0, 1)
            self.profile_section_layout.setColumnStretch(1, 2)
            self.template_section_layout.addWidget(self.template_list_panel, 0, 0)
            self.template_section_layout.addWidget(self.template_editor_panel, 0, 1)
            self.template_section_layout.setColumnStretch(0, 1)
            self.template_section_layout.setColumnStretch(1, 2)

    def refresh_profiles_table(self, selected_id: str | None = None) -> None:
        self.meeting_profiles = self.profile_store.list_profiles()
        target_id = selected_id or self.active_profile_id or self.settings.get("app", {}).get("selected_profile_id", "general")

        self.profiles_table.blockSignals(True)
        self.profiles_table.setRowCount(0)
        selected_row = 0
        for row, profile in enumerate(self.meeting_profiles):
            self.profiles_table.insertRow(row)
            name_item = QTableWidgetItem(profile.name)
            name_item.setData(Qt.UserRole, profile.id)
            category_item = QTableWidgetItem(profile.category)
            category_item.setData(Qt.UserRole, profile.id)
            self.profiles_table.setItem(row, 0, name_item)
            self.profiles_table.setItem(row, 1, category_item)
            if profile.id == target_id:
                selected_row = row
        self.profiles_table.blockSignals(False)

        if self.meeting_profiles:
            self.profiles_table.selectRow(selected_row)
            self._load_profile_into_editor(self.meeting_profiles[selected_row])
        else:
            self.active_profile_id = ""
            self._clear_profile_editor()

    def _profile_row_selected(self) -> None:
        selected = self.profiles_table.selectedItems()
        if not selected:
            return
        profile_id = str(selected[0].data(Qt.UserRole) or "")
        for profile in self.meeting_profiles:
            if profile.id == profile_id:
                self._load_profile_into_editor(profile)
                return

    def _load_profile_into_editor(self, profile: MeetingProfile) -> None:
        self.active_profile_id = profile.id
        self.profile_name_edit.setText(profile.name)
        self.profile_category_edit.setText(profile.category)
        self.profile_company_conducting_edit.setText(profile.company_conducting)
        self.profile_companies_attending_edit.setText(profile.companies_attending)
        self.profile_title_prefix_edit.setText(profile.default_meeting_title_prefix)
        select_combo_by_data(self.profile_default_template_combo, profile.default_note_template_id)
        self.profile_context_edit.setPlainText(profile.ai_context)
        self.profile_focus_edit.setPlainText(profile.notes_focus)

    def _clear_profile_editor(self) -> None:
        self.profile_name_edit.clear()
        self.profile_category_edit.setText("General Meeting")
        self.profile_company_conducting_edit.clear()
        self.profile_companies_attending_edit.clear()
        self.profile_title_prefix_edit.clear()
        select_combo_by_data(self.profile_default_template_combo, "")
        self.profile_context_edit.clear()
        self.profile_focus_edit.clear()

    def new_profile(self) -> None:
        self.profiles_table.clearSelection()
        self.active_profile_id = ""
        self._clear_profile_editor()
        self.profile_name_edit.setText("New Profile")
        self.profile_name_edit.setFocus()
        self.profile_name_edit.selectAll()

    def duplicate_profile(self) -> None:
        profile = next((item for item in self.meeting_profiles if item.id == self.active_profile_id), None)
        if profile is None:
            return
        existing_ids = {item.id for item in self.meeting_profiles}
        name = f"{profile.name} Copy"
        duplicate = MeetingProfile(
            id=self.profile_store.make_id(name, existing_ids),
            name=name,
            category=profile.category,
            company_conducting=profile.company_conducting,
            companies_attending=profile.companies_attending,
            default_meeting_title_prefix=profile.default_meeting_title_prefix,
            default_note_template_id=profile.default_note_template_id,
            ai_context=profile.ai_context,
            notes_focus=profile.notes_focus,
        )
        profiles = [*self.meeting_profiles, duplicate]
        profiles.sort(key=lambda item: (item.category.lower(), item.name.lower()))
        self.profile_store.write_profiles(profiles)
        self._populate_profile_combo()
        self.refresh_profiles_table(duplicate.id)
        self.log(f"Duplicated meeting profile: {profile.name}")

    def preview_profile_prompt(self) -> None:
        profile = MeetingProfile(
            id=self.active_profile_id or "preview",
            name=self.profile_name_edit.text().strip() or "Preview Profile",
            category=self.profile_category_edit.text().strip() or "General Meeting",
            company_conducting=self.profile_company_conducting_edit.text().strip(),
            companies_attending=self.profile_companies_attending_edit.text().strip(),
            default_meeting_title_prefix=self.profile_title_prefix_edit.text().strip(),
            default_note_template_id=str(self.profile_default_template_combo.currentData() or ""),
            ai_context=self.profile_context_edit.toPlainText().strip(),
            notes_focus=self.profile_focus_edit.toPlainText().strip(),
        )
        QMessageBox.information(self, "Profile Preview", profile.to_prompt_context())

    def save_profile(self) -> None:
        name = self.profile_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Nova Notetaker", "Profile name is required.")
            return

        existing_ids = {profile.id for profile in self.meeting_profiles}
        profile_id = self.active_profile_id or self.profile_store.make_id(name, existing_ids)
        profile = MeetingProfile(
            id=profile_id,
            name=name,
            category=self.profile_category_edit.text().strip() or "General Meeting",
            company_conducting=self.profile_company_conducting_edit.text().strip(),
            companies_attending=self.profile_companies_attending_edit.text().strip(),
            default_meeting_title_prefix=self.profile_title_prefix_edit.text().strip(),
            default_note_template_id=str(self.profile_default_template_combo.currentData() or ""),
            ai_context=self.profile_context_edit.toPlainText().strip(),
            notes_focus=self.profile_focus_edit.toPlainText().strip(),
        )

        profiles = [item for item in self.meeting_profiles if item.id != profile_id]
        profiles.append(profile)
        profiles.sort(key=lambda item: (item.category.lower(), item.name.lower()))
        self.profile_store.write_profiles(profiles)
        self.meeting_profiles = self.profile_store.list_profiles()
        self.settings.setdefault("app", {})["selected_profile_id"] = profile.id
        save_settings(self.settings)
        self._populate_profile_combo()
        select_combo_by_data(self.profile_combo, profile.id)
        self.refresh_profiles_table(profile.id)
        self.update_settings_summary()
        self.log(f"Saved meeting profile: {profile.name}")

    def delete_profile(self) -> None:
        if not self.active_profile_id:
            return
        if len(self.meeting_profiles) <= 1:
            QMessageBox.warning(self, "Nova Notetaker", "At least one meeting profile must remain.")
            return
        profile = next((item for item in self.meeting_profiles if item.id == self.active_profile_id), None)
        if profile is None:
            return

        response = QMessageBox.question(
            self,
            "Delete Meeting Profile",
            f"Delete the meeting profile '{profile.name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if response != QMessageBox.Yes:
            return

        remaining = [item for item in self.meeting_profiles if item.id != profile.id]
        self.profile_store.write_profiles(remaining)
        selected_id = remaining[0].id
        if self.settings.get("app", {}).get("selected_profile_id") == profile.id:
            self.settings.setdefault("app", {})["selected_profile_id"] = selected_id
            save_settings(self.settings)
        self._populate_profile_combo()
        select_combo_by_data(self.profile_combo, self.settings.get("app", {}).get("selected_profile_id", selected_id))
        self.refresh_profiles_table(selected_id)
        self.update_settings_summary()
        self.log(f"Deleted meeting profile: {profile.name}")

    def refresh_templates_table(self, selected_id: str | None = None) -> None:
        self.note_templates = self.template_store.list_templates()
        target_id = selected_id or self.active_template_id or self.settings.get("app", {}).get("selected_template_id", "standard")

        self.templates_table.blockSignals(True)
        self.templates_table.setRowCount(0)
        selected_row = 0
        for row, template in enumerate(self.note_templates):
            self.templates_table.insertRow(row)
            name_item = QTableWidgetItem(template.name)
            name_item.setData(Qt.UserRole, template.id)
            category_item = QTableWidgetItem(template.category)
            category_item.setData(Qt.UserRole, template.id)
            self.templates_table.setItem(row, 0, name_item)
            self.templates_table.setItem(row, 1, category_item)
            if template.id == target_id:
                selected_row = row
        self.templates_table.blockSignals(False)

        if self.note_templates:
            self.templates_table.selectRow(selected_row)
            self._load_template_into_editor(self.note_templates[selected_row])
        else:
            self.active_template_id = ""
            self._clear_template_editor()

    def _template_row_selected(self) -> None:
        selected = self.templates_table.selectedItems()
        if not selected:
            return
        template_id = str(selected[0].data(Qt.UserRole) or "")
        for template in self.note_templates:
            if template.id == template_id:
                self._load_template_into_editor(template)
                return

    def _load_template_into_editor(self, template: NoteTemplate) -> None:
        self.active_template_id = template.id
        self.template_name_edit.setText(template.name)
        self.template_category_edit.setText(template.category)
        self.template_description_edit.setText(template.description)
        self.template_sections_edit.setText(template.preferred_sections)
        self.template_focus_edit.setPlainText(template.notes_focus)
        self.template_custom_edit.setPlainText(template.custom_instructions)

    def _clear_template_editor(self) -> None:
        self.template_name_edit.clear()
        self.template_category_edit.setText("General")
        self.template_description_edit.clear()
        self.template_sections_edit.setText("Summary, Key Decisions, Action Items, Important Dates, Risks / Blockers, Follow-ups")
        self.template_focus_edit.clear()
        self.template_custom_edit.clear()

    def new_template(self) -> None:
        self.templates_table.clearSelection()
        self.active_template_id = ""
        self._clear_template_editor()
        self.template_name_edit.setText("New Template")
        self.template_name_edit.setFocus()
        self.template_name_edit.selectAll()

    def duplicate_template(self) -> None:
        template = next((item for item in self.note_templates if item.id == self.active_template_id), None)
        if template is None:
            return
        existing_ids = {item.id for item in self.note_templates}
        name = f"{template.name} Copy"
        duplicate = NoteTemplate(
            id=self.template_store.make_id(name, existing_ids),
            name=name,
            category=template.category,
            description=template.description,
            notes_focus=template.notes_focus,
            custom_instructions=template.custom_instructions,
            preferred_sections=template.preferred_sections,
        )
        templates = [*self.note_templates, duplicate]
        templates.sort(key=lambda item: (item.category.lower(), item.name.lower()))
        self.template_store.write_templates(templates)
        self._populate_template_combo()
        self._populate_profile_default_template_combo()
        self.refresh_templates_table(duplicate.id)
        self.log(f"Duplicated note template: {template.name}")

    def preview_template_prompt(self) -> None:
        template = NoteTemplate(
            id=self.active_template_id or "preview",
            name=self.template_name_edit.text().strip() or "Preview Template",
            category=self.template_category_edit.text().strip() or "General",
            description=self.template_description_edit.text().strip(),
            notes_focus=self.template_focus_edit.toPlainText().strip(),
            custom_instructions=self.template_custom_edit.toPlainText().strip(),
            preferred_sections=self.template_sections_edit.text().strip()
            or "Summary, Key Decisions, Action Items, Important Dates, Risks / Blockers, Follow-ups",
        )
        QMessageBox.information(self, "Template Preview", template.to_prompt_context())

    def save_template(self) -> None:
        name = self.template_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Nova Notetaker", "Template name is required.")
            return

        existing_ids = {template.id for template in self.note_templates}
        template_id = self.active_template_id or self.template_store.make_id(name, existing_ids)
        template = NoteTemplate(
            id=template_id,
            name=name,
            category=self.template_category_edit.text().strip() or "General",
            description=self.template_description_edit.text().strip(),
            notes_focus=self.template_focus_edit.toPlainText().strip(),
            custom_instructions=self.template_custom_edit.toPlainText().strip(),
            preferred_sections=self.template_sections_edit.text().strip()
            or "Summary, Key Decisions, Action Items, Important Dates, Risks / Blockers, Follow-ups",
        )

        templates = [item for item in self.note_templates if item.id != template_id]
        templates.append(template)
        templates.sort(key=lambda item: (item.category.lower(), item.name.lower()))
        self.template_store.write_templates(templates)
        self.note_templates = self.template_store.list_templates()
        self.settings.setdefault("app", {})["selected_template_id"] = template.id
        save_settings(self.settings)
        self._populate_template_combo()
        self._populate_profile_default_template_combo()
        select_combo_by_data(self.template_combo, template.id)
        self.refresh_templates_table(template.id)
        self.update_settings_summary()
        self.log(f"Saved note template: {template.name}")

    def delete_template(self) -> None:
        if not self.active_template_id:
            return
        if len(self.note_templates) <= 1:
            QMessageBox.warning(self, "Nova Notetaker", "At least one template must remain.")
            return
        template = next((item for item in self.note_templates if item.id == self.active_template_id), None)
        if template is None:
            return

        response = QMessageBox.question(
            self,
            "Delete Template",
            f"Delete the template '{template.name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if response != QMessageBox.Yes:
            return

        remaining = [item for item in self.note_templates if item.id != template.id]
        self.template_store.write_templates(remaining)
        selected_id = remaining[0].id
        if self.settings.get("app", {}).get("selected_template_id") == template.id:
            self.settings.setdefault("app", {})["selected_template_id"] = selected_id
            save_settings(self.settings)
        self._populate_template_combo()
        self._populate_profile_default_template_combo()
        select_combo_by_data(self.template_combo, self.settings.get("app", {}).get("selected_template_id", selected_id))
        self.refresh_templates_table(selected_id)
        self.update_settings_summary()
        self.log(f"Deleted note template: {template.name}")
