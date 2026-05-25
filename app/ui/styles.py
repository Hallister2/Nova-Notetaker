ORANGE = "#FF8A1F"
ORANGE_HOVER = "#FFA13D"
APP_BACKGROUND = "#0F1216"
SIDEBAR = "#14181E"
PANEL = "#181D24"
RAISED = "#1D232B"
TEXT_PRIMARY = "#F4F6F8"
TEXT_SECONDARY = "#AAB2BE"
TEXT_MUTED = "#6F7782"
SUCCESS = "#3DDC84"
RECORDING = "#FF4D4D"

APP_STYLESHEET = f"""
QWidget {{
    background-color: {APP_BACKGROUND};
    color: {TEXT_PRIMARY};
    font-family: Segoe UI;
    font-size: 13px;
}}

QLabel {{
    background-color: transparent;
}}

QFrame#Sidebar {{
    background-color: {SIDEBAR};
    border-right: 1px solid rgba(255, 255, 255, 0.07);
}}

QFrame#Panel {{
    background-color: {PANEL};
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 8px;
}}

QFrame#RaisedPanel {{
    background-color: {RAISED};
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 8px;
}}

QFrame#TranscriptRow {{
    background-color: transparent;
    border: 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 0;
}}

QFrame#Footer {{
    background-color: {SIDEBAR};
    border-top: 1px solid rgba(255, 255, 255, 0.07);
}}

QLabel#Title {{
    color: {TEXT_PRIMARY};
    font-size: 24px;
    font-weight: 700;
}}

QLabel#Logo {{
    color: {ORANGE};
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 5px;
}}

QLabel#LogoSub {{
    color: {TEXT_PRIMARY};
    font-size: 11px;
    letter-spacing: 4px;
}}

QLabel#Subtitle {{
    color: {TEXT_SECONDARY};
    font-size: 13px;
}}

QLabel#Muted {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}

QLabel#SectionTitle {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
}}

QLabel#StatValue {{
    color: {TEXT_PRIMARY};
    font-size: 20px;
    font-weight: 700;
}}

QLabel#OrangeText {{
    color: {ORANGE};
    font-weight: 700;
}}

QLabel#BlueText {{
    color: #69A7FF;
    font-weight: 700;
}}

QLabel#GreenText {{
    color: {SUCCESS};
    font-weight: 700;
}}

QLabel#RedText {{
    color: {RECORDING};
    font-weight: 700;
}}

QLineEdit, QComboBox, QSpinBox {{
    background-color: {RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    padding: 8px 10px;
}}

QLineEdit:focus, QComboBox:hover, QSpinBox:hover {{
    border: 1px solid rgba(255, 138, 31, 0.45);
}}

QComboBox::drop-down {{
    border: 0;
    width: 24px;
}}

QPushButton {{
    background-color: {RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 7px;
    padding: 9px 14px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: #242B35;
    border: 1px solid rgba(255, 255, 255, 0.13);
}}

QPushButton:pressed {{
    background-color: #28313C;
}}

QPushButton:disabled {{
    color: {TEXT_MUTED};
    background-color: #171B21;
}}

QPushButton#PrimaryButton {{
    background-color: {ORANGE};
    color: #16100A;
    border: 1px solid rgba(255, 161, 61, 0.8);
}}

QPushButton#PrimaryButton:hover {{
    background-color: {ORANGE_HOVER};
}}

QPushButton#DangerButton {{
    background-color: {ORANGE};
    color: #16100A;
    border: 1px solid rgba(255, 161, 61, 0.8);
}}

QPushButton#TableActionButton {{
    background-color: rgba(255, 138, 31, 0.16);
    color: {ORANGE};
    border: 1px solid rgba(255, 138, 31, 0.55);
    border-radius: 6px;
    padding: 5px 10px;
    font-weight: 700;
}}

QPushButton#TableActionButton:hover {{
    background-color: {ORANGE};
    color: #16100A;
    border: 1px solid {ORANGE_HOVER};
}}

QPushButton#SidebarButton {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    border: 0;
    border-left: 3px solid transparent;
    border-radius: 6px;
    padding: 11px 14px;
    text-align: left;
    font-weight: 500;
}}

QPushButton#SidebarButton:hover {{
    background-color: rgba(255, 255, 255, 0.04);
    color: {TEXT_PRIMARY};
}}

QPushButton#SidebarButton[active="true"] {{
    background-color: {RAISED};
    color: {TEXT_PRIMARY};
    border-left: 3px solid {ORANGE};
}}

QCheckBox {{
    background-color: transparent;
    color: {TEXT_PRIMARY};
    spacing: 8px;
}}

QCheckBox::indicator {{
    background-color: transparent;
    border: 1px solid rgba(255, 255, 255, 0.35);
    border-radius: 4px;
    width: 15px;
    height: 15px;
}}

QCheckBox::indicator:checked {{
    background-color: {ORANGE};
    border: 1px solid {ORANGE};
}}

QCheckBox#MicToggle {{
    background-color: #232A33;
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 14px;
    padding: 6px 12px;
    font-weight: 700;
}}

QCheckBox#MicToggle[muted="false"] {{
    color: {SUCCESS};
}}

QCheckBox#MicToggle[muted="true"] {{
    color: {ORANGE};
}}

QTextEdit {{
    background-color: #151A20;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    color: {TEXT_PRIMARY};
    padding: 10px;
}}

QTableWidget {{
    background-color: #151A20;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    gridline-color: rgba(255, 255, 255, 0.05);
    selection-background-color: rgba(255, 138, 31, 0.18);
}}

QTableWidget::item {{
    padding: 7px;
}}

QTableWidget::item:selected {{
    background-color: rgba(255, 138, 31, 0.18);
    color: {TEXT_PRIMARY};
}}

QHeaderView::section {{
    background-color: {RAISED};
    color: {TEXT_SECONDARY};
    border: 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.07);
    padding: 8px;
    font-weight: 600;
}}

QProgressBar {{
    background-color: #272D35;
    border: 0;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {ORANGE};
    border-radius: 4px;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px 4px 2px;
}}

QScrollBar::handle:vertical {{
    background: {ORANGE};
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
    background-color: {APP_BACKGROUND};
}}
"""
