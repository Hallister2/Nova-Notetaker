THEME_LABELS = {
    "executive_dark": "Executive Dark",
    "clean_light": "Graphite Light",
}


THEMES = {
    "executive_dark": {
        "app": "#101112",
        "sidebar": "#141516",
        "panel": "#18191B",
        "raised": "#202123",
        "field": "#141516",
        "text": "#F4F6F8",
        "secondary": "#C0C3C7",
        "muted": "#85888E",
        "border": "rgba(255, 255, 255, 0.08)",
        "soft": "rgba(255, 255, 255, 0.04)",
        "hover": "#292A2D",
        "orange": "#FF8A1F",
        "orange_hover": "#FFA13D",
        "success": "#3DDC84",
        "recording": "#FF4D4D",
        "primary_text": "#16100A",
        "blue": "#82B6FF",
        "badge": "#252628",
        "disabled": "#1A1B1D",
    },
    "clean_light": {
        "app": "#ECEBE8",
        "sidebar": "#E3E2DE",
        "panel": "#F4F3EF",
        "raised": "#E8E7E3",
        "field": "#FAF9F5",
        "text": "#232426",
        "secondary": "#55585D",
        "muted": "#777B80",
        "border": "rgba(35, 36, 38, 0.13)",
        "soft": "rgba(35, 36, 38, 0.045)",
        "hover": "#DDDBD6",
        "orange": "#FF7A1A",
        "orange_hover": "#FF8F33",
        "success": "#0E9F6E",
        "recording": "#E02424",
        "primary_text": "#1C1308",
        "blue": "#2F6FB7",
        "badge": "#DFDED9",
        "disabled": "#E1E0DC",
    },
}


def build_stylesheet(theme_name: str = "executive_dark") -> str:
    t = THEMES.get(theme_name, THEMES["executive_dark"])
    return f"""
QWidget {{
    background-color: {t["app"]};
    color: {t["text"]};
    font-family: Segoe UI;
    font-size: 13px;
}}

QLabel {{
    background-color: transparent;
}}

QFrame#Sidebar {{
    background-color: {t["sidebar"]};
    border-right: 1px solid {t["border"]};
}}

QFrame#Panel {{
    background-color: {t["panel"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
}}

QFrame#RaisedPanel {{
    background-color: {t["raised"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
}}

QFrame#ActionDock {{
    background-color: {t["raised"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
}}

QFrame#MetricCard {{
    background-color: {t["soft"]};
    border: 1px solid {t["border"]};
    border-radius: 7px;
}}

QFrame#LiveCaptureHud {{
    background-color: {t["soft"]};
    border: 1px solid {t["border"]};
    border-radius: 7px;
}}

QFrame#TranscriptRow {{
    background-color: transparent;
    border: 0;
    border-bottom: 1px solid {t["border"]};
    border-radius: 0;
}}

QFrame#LiveTranscriptRow {{
    background-color: rgba(255, 138, 31, 0.045);
    border: 1px solid rgba(255, 138, 31, 0.12);
    border-radius: 7px;
}}

QFrame#InsightItem {{
    background-color: {t["soft"]};
    border: 1px solid {t["border"]};
    border-radius: 6px;
}}

QFrame#InsightPreview {{
    background-color: {t["soft"]};
    border: 1px solid {t["border"]};
    border-radius: 6px;
}}

QFrame#Footer {{
    background-color: {t["sidebar"]};
    border-top: 1px solid {t["border"]};
}}

QWidget#Transparent {{
    background-color: transparent;
}}

QWidget#OverviewRoot {{
    background-color: {t["app"]};
}}

QLabel#Title {{
    color: {t["text"]};
    font-size: 24px;
    font-weight: 700;
}}

QLabel#PanelTitle {{
    color: {t["text"]};
    font-size: 18px;
    font-weight: 700;
}}

QLabel#Logo {{
    color: {t["orange"]};
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 5px;
}}

QLabel#LogoSub {{
    color: {t["text"]};
    font-size: 11px;
    letter-spacing: 4px;
}}

QLabel#Subtitle {{
    color: {t["secondary"]};
    font-size: 13px;
}}

QLabel#Muted {{
    color: {t["muted"]};
    font-size: 12px;
}}

QLabel#SectionTitle {{
    color: {t["secondary"]};
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
}}

QLabel#FieldLabel {{
    color: {t["muted"]};
    font-size: 12px;
    font-weight: 600;
}}

QLabel#StatValue {{
    color: {t["text"]};
    font-size: 20px;
    font-weight: 700;
}}

QLabel#HeroTimer {{
    color: {t["text"]};
    font-size: 28px;
    font-weight: 700;
}}

QLabel#CompactTimer {{
    color: {t["text"]};
    font-size: 16px;
    font-weight: 800;
}}

QLabel#WorkflowStep {{
    background-color: rgba(255, 138, 31, 0.10);
    color: {t["orange"]};
    border: 1px solid rgba(255, 138, 31, 0.30);
    border-radius: 12px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 800;
}}

QLabel#OrangeText {{
    color: {t["orange"]};
    font-weight: 700;
}}

QLabel#BlueText {{
    color: {t["blue"]};
    font-weight: 700;
}}

QLabel#GreenText {{
    color: {t["success"]};
    font-weight: 700;
}}

QLabel#RedText {{
    color: {t["recording"]};
    font-weight: 700;
}}

QLabel#Badge {{
    background-color: {t["badge"]};
    color: {t["secondary"]};
    border: 1px solid {t["border"]};
    border-radius: 7px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 700;
}}

QLabel#InsightItemTitle {{
    background-color: transparent;
    color: {t["text"]};
    font-size: 12px;
}}

QLabel#InsightPreviewText {{
    background-color: transparent;
    color: {t["secondary"]};
    font-size: 12px;
}}

QLabel#LivePartialText {{
    background-color: transparent;
    color: {t["text"]};
    font-size: 13px;
}}

QLabel#Badge[kind="confidence-high"] {{
    background-color: rgba(61, 220, 132, 0.14);
    color: {t["success"]};
}}

QLabel#Badge[kind="confidence-medium"] {{
    background-color: rgba(250, 204, 21, 0.16);
    color: #D49100;
}}

QLabel#Badge[kind="confidence-low"] {{
    background-color: rgba(251, 113, 133, 0.15);
    color: #FB5470;
}}

QLabel#Badge[kind="confidence-tentative"] {{
    background-color: rgba(105, 167, 255, 0.12);
    color: {t["blue"]};
}}

QLabel#Badge[kind="date"] {{
    background-color: rgba(255, 138, 31, 0.15);
    color: {t["orange"]};
}}

QLabel#Badge[kind="state"] {{
    background-color: rgba(255, 138, 31, 0.14);
    color: {t["orange"]};
}}

QLabel#StatusBadge {{
    background-color: {t["badge"]};
    color: {t["secondary"]};
    border: 1px solid {t["border"]};
    border-radius: 9px;
    padding: 4px 9px;
    font-size: 11px;
    font-weight: 800;
}}

QLabel#StatusBadge[state="complete"] {{
    background-color: rgba(61, 220, 132, 0.13);
    color: {t["success"]};
    border: 1px solid rgba(61, 220, 132, 0.25);
}}

QLabel#StatusBadge[state="review"] {{
    background-color: rgba(255, 138, 31, 0.10);
    color: {t["orange"]};
    border: 1px solid rgba(255, 138, 31, 0.28);
}}

QLabel#StatusBadge[state="processing"] {{
    background-color: rgba(105, 167, 255, 0.14);
    color: {t["blue"]};
    border: 1px solid rgba(105, 167, 255, 0.28);
}}

QLabel#StatusBadge[state="draft"] {{
    background-color: {t["soft"]};
    color: {t["muted"]};
}}

QFrame#FormSection {{
    background-color: {t["soft"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
}}

QLineEdit, QComboBox, QSpinBox {{
    background-color: {t["field"]};
    color: {t["text"]};
    border: 1px solid {t["border"]};
    border-radius: 6px;
    padding: 8px 10px;
    min-height: 18px;
}}

QLineEdit:focus, QComboBox:hover, QSpinBox:hover {{
    border: 1px solid rgba(255, 138, 31, 0.55);
}}

QComboBox::drop-down {{
    border: 0;
    width: 24px;
}}

QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
}}

QPushButton {{
    background-color: {t["raised"]};
    color: {t["text"]};
    border: 1px solid {t["border"]};
    border-radius: 7px;
    padding: 9px 14px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {t["hover"]};
    border: 1px solid rgba(255, 138, 31, 0.24);
}}

QPushButton:pressed {{
    background-color: {t["badge"]};
}}

QPushButton:disabled {{
    color: {t["muted"]};
    background-color: {t["disabled"]};
}}

QPushButton#PrimaryButton, QPushButton#DangerButton {{
    background-color: {t["orange"]};
    color: {t["primary_text"]};
    border: 1px solid {t["orange_hover"]};
}}

QPushButton#PrimaryButton:hover, QPushButton#DangerButton:hover {{
    background-color: {t["orange_hover"]};
}}

QPushButton#TableActionButton {{
    background-color: rgba(255, 138, 31, 0.10);
    color: {t["orange"]};
    border: 1px solid rgba(255, 138, 31, 0.38);
    border-radius: 6px;
    padding: 5px 10px;
    font-weight: 700;
}}

QPushButton#TableActionButton:hover {{
    background-color: {t["orange"]};
    color: {t["primary_text"]};
    border: 1px solid {t["orange_hover"]};
}}

QPushButton#SubtleActionButton {{
    background-color: {t["soft"]};
    color: {t["secondary"]};
    border: 1px solid {t["border"]};
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
}}

QFrame#ThemeToggle {{
    background-color: {t["raised"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
}}

QPushButton#ThemeButton {{
    background-color: transparent;
    color: {t["secondary"]};
    border: 0;
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 700;
    min-width: 0;
}}

QPushButton#ThemeButton[active="true"] {{
    background-color: rgba(255, 138, 31, 0.14);
    color: {t["orange"]};
    border: 1px solid rgba(255, 138, 31, 0.34);
}}

QPushButton#ThemeButton:hover {{
    background-color: {t["hover"]};
    color: {t["text"]};
}}

QPushButton#ThemeButton[active="true"]:hover {{
    background-color: rgba(255, 138, 31, 0.18);
    color: {t["orange"]};
}}

QPushButton#SidebarButton {{
    background-color: transparent;
    color: {t["secondary"]};
    border: 0;
    border-left: 3px solid transparent;
    border-radius: 6px;
    padding: 11px 14px;
    text-align: left;
    font-weight: 500;
}}

QPushButton#SidebarButton:hover {{
    background-color: {t["soft"]};
    color: {t["text"]};
}}

QPushButton#SidebarButton[active="true"] {{
    background-color: {t["raised"]};
    color: {t["text"]};
    border-left: 3px solid {t["orange"]};
}}

QCheckBox {{
    background-color: transparent;
    color: {t["text"]};
    spacing: 8px;
    min-height: 28px;
}}

QCheckBox::indicator {{
    background-color: transparent;
    border: 1px solid {t["border"]};
    border-radius: 4px;
    width: 15px;
    height: 15px;
}}

QCheckBox::indicator:checked {{
    background-color: {t["orange"]};
    border: 1px solid {t["orange"]};
}}

QRadioButton {{
    background-color: transparent;
    color: {t["text"]};
    spacing: 10px;
    padding: 5px 2px;
}}

QRadioButton::indicator {{
    width: 17px;
    height: 17px;
    border-radius: 9px;
    border: 1px solid {t["secondary"]};
    background-color: transparent;
}}

QRadioButton::indicator:hover {{
    border: 1px solid {t["orange"]};
}}

QRadioButton::indicator:checked {{
    border: 2px solid {t["orange"]};
    background-color: {t["orange"]};
}}

QCheckBox#MicToggle {{
    background-color: {t["raised"]};
    border: 1px solid {t["border"]};
    border-radius: 14px;
    padding: 6px 12px;
    font-weight: 700;
}}

QCheckBox#MicToggle[muted="false"] {{
    color: {t["success"]};
}}

QCheckBox#MicToggle[muted="true"] {{
    color: {t["orange"]};
}}

QCalendarWidget {{
    background-color: {t["field"]};
    color: {t["text"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
}}

QCalendarWidget QWidget {{
    alternate-background-color: {t["field"]};
    background-color: {t["field"]};
    color: {t["text"]};
}}

QCalendarWidget QToolButton {{
    background-color: transparent;
    color: {t["text"]};
    border: 0;
    border-radius: 5px;
    padding: 6px 8px;
}}

QCalendarWidget QToolButton:hover {{
    background-color: {t["hover"]};
}}

QCalendarWidget QMenu {{
    background-color: {t["panel"]};
    color: {t["text"]};
    border: 1px solid {t["border"]};
}}

QCalendarWidget QSpinBox {{
    min-width: 72px;
}}

QTextEdit {{
    background-color: {t["field"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
    color: {t["text"]};
    padding: 10px;
}}

QTableWidget {{
    background-color: {t["field"]};
    alternate-background-color: rgba(255, 255, 255, 0.018);
    border: 1px solid {t["border"]};
    border-radius: 8px;
    gridline-color: transparent;
    outline: 0;
    selection-background-color: rgba(255, 138, 31, 0.09);
}}

QTableWidget::item {{
    border: 0;
    border-bottom: 1px solid {t["border"]};
    padding: 6px 10px;
}}

QTableWidget::item:selected {{
    background-color: rgba(255, 138, 31, 0.09);
    color: {t["text"]};
    border: 0;
    border-bottom: 1px solid rgba(255, 138, 31, 0.18);
}}

QTableWidget::item:focus {{
    outline: 0;
    border: 0;
    border-bottom: 1px solid rgba(255, 138, 31, 0.18);
}}

QTableWidget QWidget#Transparent {{
    background-color: transparent;
}}

QHeaderView::section {{
    background-color: {t["raised"]};
    color: {t["secondary"]};
    border: 0;
    border-bottom: 1px solid {t["border"]};
    padding: 8px 10px;
    font-weight: 600;
}}

QTableCornerButton::section {{
    background-color: {t["raised"]};
    border: 0;
    border-bottom: 1px solid {t["border"]};
}}

QTabWidget::pane {{
    border: 0;
    background-color: transparent;
}}

QTabBar::tab {{
    background-color: {t["raised"]};
    color: {t["secondary"]};
    border: 1px solid {t["border"]};
    border-radius: 7px;
    padding: 8px 14px;
    margin-right: 6px;
    font-weight: 700;
}}

QTabBar::tab:selected {{
    background-color: rgba(255, 138, 31, 0.16);
    color: {t["orange"]};
    border: 1px solid rgba(255, 138, 31, 0.38);
}}

QProgressBar {{
    background-color: {t["raised"]};
    border: 0;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {t["orange"]};
    border-radius: 4px;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px 4px 2px;
}}

QScrollBar::handle:vertical {{
    background: {t["orange"]};
    border-radius: 4px;
    min-height: 36px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px 4px 2px 4px;
}}

QScrollBar::handle:horizontal {{
    background: {t["border"]};
    border-radius: 4px;
    min-width: 36px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QScrollArea {{
    background-color: transparent;
    border: 0;
}}

QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}

QDialog {{
    background-color: {t["app"]};
}}
"""


APP_STYLESHEET = build_stylesheet("executive_dark")
