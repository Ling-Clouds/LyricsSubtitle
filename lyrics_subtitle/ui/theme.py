"""深色主题与配色。"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

COLORS = {
    "bg": "#15171c",
    "panel": "#1a1d23",
    "panel_alt": "#1e2229",
    "border": "#2a2f38",
    "text": "#d9dee7",
    "text_dim": "#8b94a3",
    "text_faint": "#5d6673",
    "accent": "#35b8a6",
    "accent_dim": "#2a6f66",
    "accent_text": "#8fe8dc",
    "playhead": "#ff5f56",
    "selected": "#f0a35e",
    "grid_sub": "#20252d",
    "grid_beat": "#3a4452",
    "grid_bar": "#5f6e82",
    "wave": "#3fa89b",
    "wave_bg": "#111318",
    "block": "#235149",
    "block_alt": "#1f4640",
    "block_hover": "#2a5f57",
    "block_selected": "#2f7268",
    "ruler_bg": "#181b21",
    "track_bg": "#171a20",
    "ruler_text": "#7f8999",
    "loop_fill": "#ff5f56",
}

QSS = """
QMainWindow, QDialog { background: #15171c; }
QWidget { color: #d9dee7; }

QMenuBar {
    background: #1a1d23;
    color: #aeb7c4;
    border-bottom: 1px solid #262b33;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
}
QMenuBar::item:selected {
    background: #242932;
    color: #ffffff;
}

QFrame#Toolbar {
    background: #1a1d23;
    border-bottom: 1px solid #262b33;
}

QToolButton, QPushButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 5px 9px;
    color: #d9dee7;
}
QToolButton:hover, QPushButton:hover {
    background: #242932;
    border-color: #343b47;
}
QToolButton:pressed, QPushButton:pressed { background: #1f242c; }
QToolButton:checked {
    background: #1e3b37;
    border-color: #2f6f66;
    color: #8fe8dc;
}
QToolButton:disabled, QPushButton:disabled { color: #5d6673; }

QToolButton#PlayButton {
    background: #2a6f66;
    border: 1px solid #35b8a6;
    padding: 5px 16px;
    font-weight: 600;
    color: #ffffff;
}
QToolButton#PlayButton:hover { background: #348278; }
QToolButton#PlayButton:pressed { background: #255f57; }

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background: #20242b;
    border: 1px solid #2f3540;
    border-radius: 4px;
    padding: 3px 6px;
    min-height: 18px;
    selection-background-color: #2a6f66;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {
    border-color: #3d4654;
}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border-color: #35b8a6;
}
QComboBox QAbstractItemView {
    background: #20242b;
    border: 1px solid #3d4654;
    selection-background-color: #2a6f66;
    outline: 0;
}
QComboBox::drop-down {
    border: none;
    width: 16px;
}

QPlainTextEdit {
    background: #171a20;
    border: 1px solid #2f3540;
    border-radius: 4px;
    selection-background-color: #2a6f66;
}

QTableWidget {
    background: #171a20;
    alternate-background-color: #1a1e25;
    border: none;
    gridline-color: #262b33;
    selection-background-color: #2a4f4a;
    selection-color: #ffffff;
}
QTableWidget::item { padding: 2px 4px; border: none; }
QHeaderView::section {
    background: #1c2027;
    color: #8b94a3;
    border: none;
    border-bottom: 1px solid #2a2f38;
    padding: 4px 6px;
    font-weight: 600;
}

QSplitter::handle { background: #20242b; }
QSplitter::handle:hover { background: #2a6f66; }

QScrollBar:horizontal {
    background: #14161b;
    height: 12px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #333b47;
    min-width: 30px;
    border-radius: 6px;
}
QScrollBar::handle:horizontal:hover { background: #3f4a59; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    height: 0;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}

QScrollBar:vertical {
    background: #14161b;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #333b47;
    min-height: 30px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover { background: #3f4a59; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

QMessageBox { background: #1a1d23; }
QMessageBox QLabel { color: #d9dee7; }
QMessageBox QPushButton {
    background: #242932;
    border: 1px solid #3a424f;
    border-radius: 4px;
    padding: 5px 16px;
    min-width: 70px;
}
QMessageBox QPushButton:hover { background: #2d343f; }

QStatusBar {
    background: #1a1d23;
    border-top: 1px solid #262b33;
    color: #8b94a3;
}
QStatusBar::item { border: none; }

QMenu {
    background: #20242b;
    border: 1px solid #3a424f;
    padding: 4px;
}
QMenu::item {
    padding: 5px 24px 5px 20px;
    border-radius: 3px;
}
QMenu::item:selected { background: #2a4f4a; }
QMenu::separator { height: 1px; background: #2a2f38; margin: 4px 8px; }

QToolTip {
    background: #20242b;
    color: #d9dee7;
    border: 1px solid #3a424f;
    padding: 4px;
}

QLabel#Hint { color: #6f7987; }
QLabel#TimeLabel { color: #e8edf4; }
QLabel#DimLabel { color: #7f8999; }
QFrame#Sep { background: #2a2f38; max-width: 1px; min-width: 1px; }

QDialogButtonBox QPushButton {
    background: #242932;
    border: 1px solid #3a424f;
    padding: 5px 18px;
    min-width: 70px;
}
QDialogButtonBox QPushButton:hover { background: #2d343f; }
QDialogButtonBox QPushButton:default {
    background: #2a6f66;
    border-color: #35b8a6;
}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 9))

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(COLORS["bg"]))
    palette.setColor(QPalette.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Base, QColor("#171a20"))
    palette.setColor(QPalette.AlternateBase, QColor("#1a1e25"))
    palette.setColor(QPalette.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.Button, QColor("#20242b"))
    palette.setColor(QPalette.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Highlight, QColor(COLORS["accent_dim"]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase, QColor("#20242b"))
    palette.setColor(QPalette.ToolTipText, QColor(COLORS["text"]))
    palette.setColor(QPalette.PlaceholderText, QColor(COLORS["text_faint"]))
    palette.setColor(QPalette.Link, QColor(COLORS["accent"]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(COLORS["text_faint"]))
    app.setPalette(palette)
    app.setStyleSheet(QSS)
