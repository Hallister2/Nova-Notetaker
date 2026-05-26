THEME_LABELS = {
    "executive_dark": "Executive Dark",
    "clean_light": "Clean Professional",
    "modern_gradient": "Modern Gradient",
}


THEMES = {
    "executive_dark": {
        "app": "#0F1216",
        "sidebar": "#14181E",
        "panel": "#181D24",
        "raised": "#1D232B",
        "field": "#151A20",
        "text": "#F4F6F8",
        "secondary": "#AAB2BE",
        "muted": "#6F7782",
        "border": "rgba(255, 255, 255, 0.07)",
        "soft": "rgba(255, 255, 255, 0.035)",
        "hover": "#242B35",
        "orange": "#FF8A1F",
        "orange_hover": "#FFA13D",
        "success": "#3DDC84",
        "recording": "#FF4D4D",
        "primary_text": "#16100A",
        "blue": "#69A7FF",
        "badge": "#242B35",
        "disabled": "#171B21",
    },
    "clean_light": {
        "app": "#F6F8FB",
        "sidebar": "#FFFFFF",
        "panel": "#FFFFFF",
        "raised": "#F1F4F8",
        "field": "#FFFFFF",
        "text": "#111827",
        "secondary": "#4B5563",
        "muted": "#7B8492",
        "border": "rgba(17, 24, 39, 0.10)",
        "soft": "rgba(17, 24, 39, 0.035)",
        "hover": "#E9EEF5",
        "orange": "#FF7A1A",
        "orange_hover": "#FF8F33",
        "success": "#0E9F6E",
        "recording": "#E02424",
        "primary_text": "#FFFFFF",
        "blue": "#2563EB",
        "badge": "#EEF2F7",
        "disabled": "#EEF1F5",
    },
    "modern_gradient": {
        "app": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #080D24, stop:0.55 #121633, stop:1 #24143D)",
        "sidebar": "rgba(14, 18, 45, 0.95)",
        "panel": "rgba(20, 25, 58, 0.92)",
        "raised": "rgba(32, 28, 72, 0.92)",
        "field": "rgba(18, 23, 56, 0.94)",
        "text": "#F8FAFF",
        "secondary": "#B8C0D9",
        "muted": "#818BA9",
        "border": "rgba(255, 255, 255, 0.11)",
        "soft": "rgba(255, 255, 255, 0.05)",
        "hover": "rgba(52, 43, 105, 0.95)",
        "orange": "#FF7A2F",
        "orange_hover": "#FF9A4D",
        "success": "#35E78A",
        "recording": "#FF5B69",
        "primary_text": "#140B05",
        "blue": "#7AA7FF",
        "badge": "rgba(39, 42, 87, 0.96)",
        "disabled": "rgba(23, 28, 61, 0.95)",
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

QFrame#TranscriptRow {{
    background-color: transparent;
    border: 0;
    border-bottom: 1px solid {t["border"]};
    border-radius: 0;
}}

QFrame#InsightItem {{
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
    background-color: rgba(255, 138, 31, 0.14);
    color: {t["orange"]};
    border: 1px solid rgba(255, 138, 31, 0.35);
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
    background-color: rgba(255, 138, 31, 0.16);
    color: {t["orange"]};
    border: 1px solid rgba(255, 138, 31, 0.55);
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

QPushButton#ThemeButton {{
    background-color: {t["raised"]};
    color: {t["secondary"]};
    border: 1px solid {t["border"]};
    border-radius: 7px;
    padding: 7px 10px;
    font-weight: 700;
}}

QPushButton#ThemeButton[active="true"] {{
    background-color: rgba(255, 138, 31, 0.18);
    color: {t["orange"]};
    border: 1px solid rgba(255, 138, 31, 0.62);
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

QTextEdit {{
    background-color: {t["field"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
    color: {t["text"]};
    padding: 10px;
}}

QTableWidget {{
    background-color: {t["field"]};
    border: 1px solid {t["border"]};
    border-radius: 8px;
    gridline-color: {t["border"]};
    selection-background-color: rgba(255, 138, 31, 0.22);
}}

QTableWidget::item {{
    padding: 6px;
}}

QTableWidget::item:selected {{
    background-color: rgba(255, 138, 31, 0.22);
    color: {t["text"]};
}}

QHeaderView::section {{
    background-color: {t["raised"]};
    color: {t["secondary"]};
    border: 0;
    border-bottom: 1px solid {t["border"]};
    padding: 7px;
    font-weight: 600;
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
