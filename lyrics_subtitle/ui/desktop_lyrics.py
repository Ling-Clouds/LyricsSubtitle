"""桌面歌词预览窗口与设置对话框。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core import Project


def _timed_lines(project: Project):
    return [
        line
        for line in project.lines
        if line.start_ms is not None and bool(line.text.strip())
    ]


class DesktopLyricsWindow(QWidget):
    """无边框、置顶、可拖动的桌面歌词窗口。"""

    moved = Signal(QPoint)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._project = Project()
        self._position_ms = 0
        self._enabled = False
        self._playing = False
        self._font_family = "Microsoft YaHei"
        self._font_size = 24
        self._color = QColor("#ffffff")
        self._positioned = False
        self._drag_offset: Optional[QPoint] = None

        self.setWindowTitle("桌面歌词")
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.OpenHandCursor)
        self.setMouseTracking(True)
        self._apply_font()
        self._recalculate_size()
        self._ensure_position()

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def font_family(self) -> str:
        return self._font_family

    @property
    def font_size(self) -> int:
        return self._font_size

    @property
    def text_color(self) -> QColor:
        return QColor(self._color)

    @property
    def current_text(self) -> str:
        current, _ = self._texts()
        return current

    @property
    def next_text(self) -> str:
        _, nxt = self._texts()
        return nxt

    def set_project(self, project: Project) -> None:
        self._project = project
        self._recalculate_size()
        self.update()

    def set_position(self, ms: int, playing: bool = False) -> None:
        self._position_ms = max(0, int(ms))
        self.update()

    def set_playing(self, playing: bool) -> None:
        # 当前版本不需要根据暂停状态改变外观，保留接口方便后续扩展。
        self._playing = bool(playing)
        self.update()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if self._enabled:
            self._ensure_position()
            self.show()
            self.raise_()
        else:
            self.hide()

    def apply_appearance(self, family: str, size: int, color: QColor) -> None:
        self._font_family = family or "Microsoft YaHei"
        self._font_size = max(12, min(96, int(size)))
        if color.isValid():
            self._color = QColor(color)
            self._color.setAlpha(255)
        self._apply_font()
        self._recalculate_size()
        self.update()

    def set_saved_position(self, position: QPoint) -> None:
        self.move(position)
        self._positioned = True
        self._clamp_position()

    def reset_position(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.center().x() - self.width() // 2
        y = geo.top() + int(geo.height() * 0.72)
        self.move(x, y)
        self._positioned = True
        self.moved.emit(self.pos())

    # ------------------------------------------------------------------
    # 文本与尺寸
    # ------------------------------------------------------------------
    def _apply_font(self) -> None:
        self._font = QFont(self._font_family, self._font_size)
        self._font.setStyleStrategy(QFont.PreferAntialias)
        self._next_font = QFont(self._font_family, max(12, int(self._font_size * 0.62)))
        self._next_font.setStyleStrategy(QFont.PreferAntialias)

    def _texts(self) -> tuple[str, str]:
        timed = _timed_lines(self._project)
        if not timed:
            return "", ""
        current_index = -1
        for index, line in enumerate(timed):
            if line.start_ms <= self._position_ms:
                current_index = index
            else:
                break

        if current_index < 0:
            return "", timed[0].text.strip()
        current = timed[current_index].text.strip()
        if current_index + 1 < len(timed):
            return current, timed[current_index + 1].text.strip()
        return current, ""

    def _recalculate_size(self) -> None:
        self._apply_font()
        metrics = QFontMetrics(self._font)
        timed = _timed_lines(self._project)
        screen = QGuiApplication.primaryScreen()
        available_width = screen.availableGeometry().width() if screen else 1280
        max_text = 0
        for line in timed:
            max_text = max(max_text, metrics.horizontalAdvance(line.text.strip()))
        if timed:
            width = max(360, min(max_text + 76, int(available_width * 0.82)))
            height = metrics.height() + QFontMetrics(self._next_font).height() + 54
        else:
            width = 420
            height = 92
        self.setFixedSize(width, height)
        if self._positioned:
            self._clamp_position()

    def _ensure_position(self) -> None:
        if not self._positioned:
            self.reset_position()

    def _clamp_position(self) -> None:
        screens = QGuiApplication.screens()
        if not screens:
            return
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or screens[0]
        geo = screen.availableGeometry()
        min_x = geo.left() - self.width() + 100
        max_x = geo.right() - 100
        min_y = geo.top()
        max_y = geo.bottom() - 60
        x = min(max(self.x(), min_x), max_x)
        y = min(max(self.y(), min_y), max_y)
        if x != self.x() or y != self.y():
            self.move(x, y)

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        outer = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        path = QPainterPath()
        path.addRoundedRect(outer, 18.0, 18.0)
        painter.fillPath(path, QColor(10, 13, 18, 178))
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1.0))
        painter.drawPath(path)

        current, next_text = self._texts()
        has_lyrics = bool(_timed_lines(self._project))
        if not has_lyrics:
            main_text = "还没有已打轴的歌词"
            next_text = "打开音频并打轴后显示"
            main_alpha = 125
        elif current:
            main_text = current
            main_alpha = 255
        else:
            main_text = next_text
            next_text = ""
            main_alpha = 170

        padding_x = 28
        content = QRect(
            padding_x,
            12,
            max(1, self.width() - padding_x * 2),
            self.height() - 24,
        )
        main_font = self._font if not (not current and has_lyrics) else QFont(
            self._font_family, max(12, int(self._font_size * 0.72))
        )
        main_metrics = QFontMetrics(main_font)
        sub_metrics = QFontMetrics(self._next_font)
        main_height = main_metrics.height()
        sub_height = sub_metrics.height() if next_text else 0
        total_height = main_height + (8 + sub_height if next_text else 0)
        top = content.top() + max(0, (content.height() - total_height) // 2)

        main_rect = QRect(content.left(), top, content.width(), main_height)
        self._draw_line(
            painter,
            main_rect,
            main_font,
            main_metrics,
            main_text,
            QColor(self._color.red(), self._color.green(), self._color.blue(), main_alpha),
        )
        if next_text:
            sub_rect = QRect(
                content.left(), top + main_height + 8, content.width(), sub_height
            )
            self._draw_line(
                painter,
                sub_rect,
                self._next_font,
                sub_metrics,
                next_text,
                QColor(
                    self._color.red(),
                    self._color.green(),
                    self._color.blue(),
                    145,
                ),
            )
        painter.end()

    @staticmethod
    def _draw_line(
        painter: QPainter,
        rect: QRect,
        font: QFont,
        metrics: QFontMetrics,
        text: str,
        color: QColor,
    ) -> None:
        painter.setFont(font)
        elided = metrics.elidedText(text, Qt.ElideRight, rect.width())
        shadow = QColor(0, 0, 0, 190)
        painter.setPen(shadow)
        painter.drawText(rect.translated(2, 2), Qt.AlignCenter, elided)
        painter.setPen(color)
        painter.drawText(rect, Qt.AlignCenter, elided)

    # ------------------------------------------------------------------
    # 拖动
    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            self.setCursor(Qt.ClosedHandCursor)
            self.raise_()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self._clamp_position()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self.setCursor(Qt.OpenHandCursor)
            self.moved.emit(self.pos())
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class DesktopLyricsSettingsDialog(QDialog):
    """字体、字号、颜色和启用状态的设置对话框。"""

    def __init__(
        self,
        parent: Optional[QWidget],
        enabled: bool,
        family: str,
        size: int,
        color: QColor,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("桌面歌词设置")
        self.setMinimumWidth(540)
        self._color = QColor(color) if color.isValid() else QColor("#ffffff")
        self._color.setAlpha(255)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.enable_box = QCheckBox("启用桌面歌词")
        self.enable_box.setChecked(enabled)
        form.addRow("", self.enable_box)

        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(family))
        form.addRow("字体", self.font_combo)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(14, 96)
        self.size_spin.setSuffix(" pt")
        self.size_spin.setValue(max(14, min(96, int(size))))
        form.addRow("字号", self.size_spin)

        color_row = QHBoxLayout()
        self.color_button = QPushButton()
        self.color_button.clicked.connect(self._pick_color)
        color_row.addWidget(self.color_button)
        color_row.addStretch(1)
        form.addRow("颜色", color_row)
        self._refresh_color_button()

        self.preview = QLabel("夜色落在安静的窗台")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(64)
        self.preview.setStyleSheet(
            "background:#14171c; border:1px solid #2a303a; border-radius:10px;"
        )
        layout.addWidget(QLabel("预览"))
        layout.addWidget(self.preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.font_combo.currentFontChanged.connect(self._update_preview)
        self.size_spin.valueChanged.connect(self._update_preview)
        self._update_preview()

    def _pick_color(self) -> None:
        selected = QColorDialog.getColor(self._color, self, "选择歌词颜色")
        if selected.isValid():
            self._color = QColor(selected)
            self._color.setAlpha(255)
            self._refresh_color_button()
            self._update_preview()

    def _refresh_color_button(self) -> None:
        self.color_button.setText(self._color.name().upper())
        self.color_button.setStyleSheet(
            f"background:{self._color.name()}; color:"
            f"{'#111111' if self._color.lightness() > 140 else '#ffffff'};"
            "padding:6px 18px; border:1px solid #3a414d; border-radius:6px;"
        )

    def _update_preview(self, *args) -> None:
        del args
        font = QFont(self.font_combo.currentFont())
        font.setPointSize(self.size_spin.value())
        self.preview.setFont(font)
        self.preview.setStyleSheet(
            "background:#14171c; border:1px solid #2a303a; border-radius:10px;"
            f"color:{self._color.name()};"
        )

    def values(self) -> tuple[bool, str, int, QColor]:
        family = self.font_combo.currentFont().family() or "Microsoft YaHei"
        return (
            self.enable_box.isChecked(),
            family,
            self.size_spin.value(),
            QColor(self._color),
        )
