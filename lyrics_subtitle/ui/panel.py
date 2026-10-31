"""左侧歌词列表面板。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import LyricLine, format_ms, split_lyrics
from .theme import COLORS


class LyricsEditDialog(QDialog):
    def __init__(self, current_text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑歌词")
        self.resize(560, 440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        tip = QLabel("每行一句歌词，空行会被忽略。可以直接从别处粘贴。")
        tip.setObjectName("DimLabel")
        layout.addWidget(tip)

        self.edit = QPlainTextEdit()
        self.edit.setPlainText(current_text)
        self.edit.setPlaceholderText("第一句歌词\n第二句歌词\n第三句歌词")
        layout.addWidget(self.edit, 1)

        if not current_text.strip():
            clipboard = QApplication.clipboard().text()
            if clipboard.strip():
                self.edit.setPlainText(clipboard)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = buttons.button(QDialogButtonBox.Ok)
        cancel = buttons.button(QDialogButtonBox.Cancel)
        ok.setText("应用")
        cancel.setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def lyrics(self) -> list[str]:
        return split_lyrics(self.edit.toPlainText())


class LyricsTable(QTableWidget):
    """歌词表；没有内容时整块区域可单击打开编辑框。"""

    empty_clicked = Signal()

    def mousePressEvent(self, event) -> None:
        if self.rowCount() == 0 and event.button() == Qt.LeftButton:
            self.empty_clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.rowCount() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor("#6f7987"))
            painter.setFont(QFont("Microsoft YaHei UI", 10))
            painter.drawText(
                self.viewport().rect(), Qt.AlignCenter, "点击这里输入歌词"
            )


class LyricsPanel(QWidget):
    text_changed = Signal(int, str)
    lines_replaced = Signal(list)
    seek_requested = Signal(int)
    selection_changed = Signal(int)
    clear_times_requested = Signal()
    clear_from_requested = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lines: list[LyricLine] = []
        self._current_index: Optional[int] = None
        self._updating = False
        self._last_selected: Optional[int] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("歌词")
        title_font = QFont("Microsoft YaHei UI", 11)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch(1)
        self.count_label = QLabel("0 句")
        self.count_label.setObjectName("DimLabel")
        header.addWidget(self.count_label)
        root.addLayout(header)

        self.table = LyricsTable(0, 4)
        self.table.viewport().setCursor(Qt.PointingHandCursor)
        self.table.setHorizontalHeaderLabels(["", "#", "开始", "歌词"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.table.setWordWrap(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.cellChanged.connect(self._on_cell_changed)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        self.table.empty_clicked.connect(self.open_editor)
        self.table.verticalHeader().setDefaultSectionSize(26)

        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.Fixed)
        header_view.setSectionResizeMode(1, QHeaderView.Fixed)
        header_view.setSectionResizeMode(2, QHeaderView.Fixed)
        header_view.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 22)
        self.table.setColumnWidth(1, 38)
        self.table.setColumnWidth(2, 82)

        root.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.edit_button = QPushButton("编辑歌词…")
        self.edit_button.clicked.connect(self.open_editor)
        self.clear_button = QPushButton("清空时间")
        self.clear_button.setToolTip("清除所有歌词的时间，保留歌词文字")
        self.clear_button.clicked.connect(self.clear_times_requested)
        buttons.addWidget(self.edit_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        root.addLayout(buttons)

        hint = QLabel("双击歌词单元格可直接改字；双击时间列可跳转播放。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

    # ------------------------------------------------------------------
    # 数据同步
    # ------------------------------------------------------------------
    def set_lines(
        self,
        lines: list[LyricLine],
        current_index: Optional[int],
        selected_index: Optional[int] = None,
    ) -> None:
        self._updating = True
        try:
            self._lines = list(lines)
            self.table.viewport().setCursor(
                Qt.PointingHandCursor if not lines else Qt.ArrowCursor
            )
            if self.table.rowCount() != len(lines):
                self.table.setRowCount(len(lines))
            for row, line in enumerate(lines):
                self._ensure_row(row)
                self._set_cell(row, 0, "▶" if row == current_index else "", Qt.AlignCenter)
                self._set_cell(row, 1, str(row + 1), Qt.AlignCenter)
                time_text = format_ms(line.start_ms) if line.start_ms is not None else "--:--.---"
                self._set_cell(row, 2, time_text, Qt.AlignCenter)
                self._set_cell(row, 3, line.text, Qt.AlignLeft | Qt.AlignVCenter)
            self._current_index = current_index
            self._apply_styles()
            if selected_index is not None:
                self._select_row(selected_index)
            elif current_index is not None:
                self._select_row(current_index)
            self._update_count()
        finally:
            self._updating = False

    def set_current(self, index: Optional[int], select: bool = True) -> None:
        self._current_index = index
        self._updating = True
        try:
            self._apply_styles()
            if select and index is not None:
                self._select_row(index)
        finally:
            self._updating = False

    def set_selected(self, index: Optional[int]) -> None:
        self._updating = True
        try:
            if index is None:
                self.table.clearSelection()
            else:
                self._select_row(index)
        finally:
            self._updating = False

    def current_index(self) -> Optional[int]:
        return self._current_index

    def selected_index(self) -> Optional[int]:
        row = self.table.currentRow()
        return row if row >= 0 else None

    def _ensure_row(self, row: int) -> None:
        for col in range(4):
            item = self.table.item(row, col)
            if item is None:
                item = QTableWidgetItem()
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
                if col == 3:
                    flags |= Qt.ItemIsEditable
                item.setFlags(flags)
                self.table.setItem(row, col, item)

    def _set_cell(self, row: int, col: int, text: str, align) -> None:
        item = self.table.item(row, col)
        if item.text() == text:
            return
        old = self.table.blockSignals(True)
        item.setText(text)
        item.setTextAlignment(align)
        self.table.blockSignals(old)

    def _apply_styles(self) -> None:
        time_font = QFont("Consolas", 9)
        text_font = QFont("Microsoft YaHei UI", 9)
        bold_font = QFont("Microsoft YaHei UI", 9)
        bold_font.setBold(True)
        current_bg = QBrush(QColor("#1d3b37"))

        for row, line in enumerate(self._lines):
            marked = line.start_ms is not None
            is_current = row == self._current_index
            for col in range(4):
                item = self.table.item(row, col)
                if item is None:
                    continue
                if col == 2:
                    item.setFont(time_font)
                    item.setForeground(QColor(COLORS["text_dim"] if marked else COLORS["text_faint"]))
                elif col == 3:
                    item.setFont(bold_font if is_current else text_font)
                    item.setForeground(QColor(COLORS["text"] if marked else "#7f8999"))
                elif col == 0:
                    item.setFont(text_font)
                    item.setForeground(QColor(COLORS["accent_text"] if is_current else "#00000000"))
                else:
                    item.setFont(text_font)
                    item.setForeground(QColor(COLORS["text_dim"] if marked else COLORS["text_faint"]))
                if is_current:
                    item.setBackground(current_bg)
                else:
                    item.setBackground(QBrush())
            tooltip = line.text
            if line.start_ms is not None:
                tooltip = f"{format_ms(line.start_ms)}\n{line.text}"
            for col in range(4):
                item = self.table.item(row, col)
                if item is not None:
                    item.setToolTip(tooltip)
        self._update_count()

    def _select_row(self, row: int) -> None:
        if 0 <= row < self.table.rowCount():
            self.table.selectRow(row)
            item = self.table.item(row, 3)
            if item is not None:
                self.table.scrollToItem(item, QAbstractItemView.EnsureVisible)

    def _update_count(self) -> None:
        marked = sum(1 for line in self._lines if line.start_ms is not None)
        self.count_label.setText(f"{len(self._lines)} 句 · 已打轴 {marked}")

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def _on_selection_changed(self) -> None:
        if self._updating:
            return
        row = self.table.currentRow()
        if row < 0:
            return
        self._last_selected = row
        self.selection_changed.emit(row)

    def _on_cell_changed(self, row: int, col: int) -> None:
        if self._updating or col != 3 or row < 0 or row >= len(self._lines):
            return
        item = self.table.item(row, col)
        if item is None:
            return
        text = item.text().strip()
        if text == self._lines[row].text:
            return
        self._updating = True
        try:
            item.setText(text)
        finally:
            self._updating = False
        self.text_changed.emit(row, text)

    def _on_double_click(self, item: QTableWidgetItem) -> None:
        row, col = item.row(), item.column()
        if col in (0, 1, 2) and 0 <= row < len(self._lines):
            start = self._lines[row].start_ms
            if start is not None:
                self.seek_requested.emit(int(start))

    def _show_context_menu(self, pos: QPoint) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0 or row >= len(self._lines):
            return
        line = self._lines[row]
        menu = QMenu(self)
        if line.start_ms is not None:
            play_action = menu.addAction("从此句开始播放")
            play_action.triggered.connect(lambda: self.seek_requested.emit(int(line.start_ms)))
        edit_action = menu.addAction("编辑这句文字")
        edit_action.triggered.connect(lambda: self._edit_row(row))
        clear_action = menu.addAction("清除此句及之后的时间")
        clear_action.setEnabled(any(l.start_ms is not None for l in self._lines[row:]))
        clear_action.triggered.connect(lambda: self.clear_from_requested.emit(row))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _edit_row(self, row: int) -> None:
        item = self.table.item(row, 3)
        if item is not None:
            self.table.setCurrentItem(item)
            self.table.editItem(item)

    def open_editor(self) -> None:
        current = "\n".join(line.text for line in self._lines)
        dialog = LyricsEditDialog(current, self)
        if dialog.exec() == QDialog.Accepted:
            texts = dialog.lyrics()
            if texts:
                self.lines_replaced.emit(texts)
