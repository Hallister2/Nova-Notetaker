ORANGE = "#ff8a1f"
ORANGE_HOT = "#ffb347"
TEXT_MAIN = "#fff1df"
TEXT_MUTED = "#d8a36d"
TEXT_DIM = "#9a6a3a"

APP_STYLESHEET = f"""
QWidget {{
    background-color: #020100;
    color: {TEXT_MAIN};
    font-family: Segoe UI;
}}

QFrame#Panel {{
    background-color: rgba(6, 3, 1, 165);
    border: 1px solid rgba(255, 138, 31, 38);
    border-radius: 18px;
}}

QLabel#Title {{
    color: {ORANGE};
    font-size: 30px;
    letter-spacing: 7px;
    font-weight: 600;
}}

QLabel#Subtitle {{
    color: {TEXT_MUTED};
    font-size: 11px;
    letter-spacing: 3px;
}}

QLabel#SectionTitle {{
    color: #ff9f2e;
    font-size: 11px;
    letter-spacing: 2px;
}}

QLineEdit, QComboBox, QSpinBox {{
    background-color: rgba(8, 4, 1, 190);
    color: {TEXT_MAIN};
    border: 1px solid rgba(255, 138, 31, 75);
    border-radius: 10px;
    padding: 8px 10px;
    font-size: 13px;
}}

QLineEdit:focus, QComboBox:hover, QSpinBox:hover {{
    border: 1px solid rgba(255, 179, 71, 210);
    background-color: rgba(18, 8, 2, 220);
}}

QTabWidget::pane {{
    border: 1px solid rgba(255, 138, 31, 32);
    border-radius: 12px;
    top: -1px;
}}

QTabBar::tab {{
    background-color: rgba(8, 4, 1, 170);
    color: {TEXT_MUTED};
    border: 1px solid rgba(255, 138, 31, 45);
    padding: 8px 18px;
    margin-right: 4px;
}}

QTabBar::tab:selected {{
    color: {TEXT_MAIN};
    border: 1px solid rgba(255, 179, 71, 150);
}}

QListWidget, QTableWidget {{
    background-color: rgba(2, 1, 0, 140);
    border: 1px solid rgba(255, 138, 31, 28);
    border-radius: 12px;
    padding: 6px;
}}

QListWidget::item {{
    padding: 8px;
}}

QListWidget::item:selected {{
    background-color: rgba(255, 138, 31, 45);
    color: {TEXT_MAIN};
}}

QTableWidget::item {{
    padding: 6px;
}}

QTableWidget::item:selected {{
    background-color: rgba(255, 138, 31, 45);
    color: {TEXT_MAIN};
}}

QHeaderView::section {{
    background-color: rgba(8, 4, 1, 220);
    color: {TEXT_MUTED};
    border: 1px solid rgba(255, 138, 31, 35);
    padding: 7px;
}}

QCheckBox {{
    color: {TEXT_MAIN};
}}

QPushButton {{
    background-color: rgba(8, 4, 1, 170);
    color: {TEXT_MAIN};
    border: 1px solid rgba(255, 138, 31, 90);
    border-radius: 11px;
    padding: 9px 14px;
    font-size: 13px;
    letter-spacing: 1px;
}}

QPushButton:hover {{
    background-color: rgba(30, 12, 2, 220);
    border: 1px solid rgba(255, 179, 71, 220);
}}

QPushButton:pressed {{
    background-color: rgba(75, 28, 4, 230);
}}

QPushButton:disabled {{
    color: rgba(216, 163, 109, 90);
    border: 1px solid rgba(255, 138, 31, 25);
}}

QTextEdit {{
    background-color: rgba(2, 1, 0, 140);
    border: 1px solid rgba(255, 138, 31, 28);
    border-radius: 14px;
    color: {TEXT_MAIN};
    padding: 10px;
}}

QProgressBar {{
    background-color: rgba(8, 4, 1, 120);
    border: 1px solid rgba(255, 138, 31, 30);
    border-radius: 8px;
    height: 12px;
}}

QProgressBar::chunk {{
    background-color: {ORANGE};
    border-radius: 8px;
}}
"""
