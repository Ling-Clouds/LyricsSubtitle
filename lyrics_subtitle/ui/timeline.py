"""时间轴控件：标尺、波形轨、字幕轨的绘制与鼠标交互。"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import QScrollBar, QWidget

from ..audio import WaveformData
from ..core import MIN_GAP_MS, Project, format_ms
from .theme import COLORS

RULER_H = 30
SCROLL_H = 12
MIN_PPS = 1.0
MAX_PPS = 4000.0
BOUNDARY_PX = 6.0
PLAYHEAD_GRAB_PX = 8.0
AUDIO_SUFFIXES = {
    ".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus",
    ".wma", ".aiff", ".aif", ".ape", ".wv",
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class TimelineView(QWidget):
    seek_requested = Signal(int)
    mark_requested = Signal(int)
    line_selected = Signal(int)
    line_start_committed = Signal(int, int)
    context_menu_requested = Signal(int, QPoint)
    hover_time_changed = Signal(int)
    audio_import_requested = Signal()
    audio_dropped = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(250)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAcceptDrops(True)

        self.project = Project()
        self.waveform: Optional[WaveformData] = None
        self.playhead_ms = 0
        self.px_per_sec = 42.0
        self.view_start_ms = 0.0
        self.follow = True
        self.current_index: Optional[int] = None
        self.selected_index: Optional[int] = None
        self.loading = False

        self._hover_pos: Optional[QPointF] = None
        self._hover_block: Optional[int] = None
        self._hover_boundary: Optional[int] = None
        self._hover_time_ms: Optional[int] = None
        self._scrubbing = False
        self._panning = False
        self._pan_last_x = 0.0
        self._ruler_drag: Optional[dict] = None
        self._drag: Optional[dict] = None
        self._pressed_block: Optional[int] = None
        self._drop_active = False
        self._loop_a: Optional[int] = None
        self._loop_b: Optional[int] = None
        self._loop_enabled = False
        self._needs_fit = False

        self._scroll = QScrollBar(Qt.Horizontal, self)
        self._scroll.setSingleStep(1000)
        self._scroll.setPageStep(5000)
        self._scroll.valueChanged.connect(self._on_scroll)

    # ------------------------------------------------------------------
    # 基本状态
    # ------------------------------------------------------------------
    def sizeHint(self) -> QSize:
        return QSize(900, 330)

    def _has_audio(self) -> bool:
        return bool(self.project.audio_path) and Path(self.project.audio_path).is_file()

    def set_project(self, project: Project) -> None:
        self.project = project
        self.current_index = project.next_unmarked_index()
        self.selected_index = None
        self._clamp_view()
        self._sync_scrollbar()
        self.update()

    def set_waveform(self, waveform: Optional[WaveformData]) -> None:
        self.waveform = waveform
        if waveform is not None:
            self._needs_fit = True
            self.fit_all()
        self.update()

    def set_loading(self, loading: bool) -> None:
        self.loading = loading
        self.update()

    def refresh(self) -> None:
        self._clamp_view()
        self._sync_scrollbar()
        self.update()

    def set_current_index(self, index: Optional[int]) -> None:
        self.current_index = index
        self.update()

    def set_selected(self, index: Optional[int]) -> None:
        self.selected_index = index
        self.update()

    def set_loop(self, a: Optional[int], b: Optional[int], enabled: bool) -> None:
        self._loop_a = a
        self._loop_b = b
        self._loop_enabled = enabled
        self.update()

    def set_playhead(self, ms: int, ensure_visible: bool = False) -> None:
        duration = self.project.duration_ms
        if duration > 0:
            ms = min(max(0, int(ms)), duration)
        else:
            ms = max(0, int(ms))
        self.playhead_ms = ms
        if ensure_visible and self.follow:
            self._ensure_visible(ms)
        self.update()

    # ------------------------------------------------------------------
    # 视图变换
    # ------------------------------------------------------------------
    def _visible_ms(self) -> float:
        if self.px_per_sec <= 0:
            return 0.0
        return self.width() / self.px_per_sec * 1000.0

    def _time_to_x(self, ms: float) -> float:
        return (ms - self.view_start_ms) / 1000.0 * self.px_per_sec

    def _x_to_time(self, x: float) -> float:
        return self.view_start_ms + x / self.px_per_sec * 1000.0

    def _clamp_view(self) -> None:
        duration = float(self.project.duration_ms)
        if duration <= 0:
            self.view_start_ms = 0.0
            return
        visible = self._visible_ms()
        max_start = max(0.0, duration - visible)
        self.view_start_ms = _clamp(self.view_start_ms, 0.0, max_start)

    def fit_all(self) -> None:
        duration = self.project.duration_ms
        if duration > 0 and self.width() > 50 and self.isVisible():
            self.px_per_sec = _clamp(
                (self.width() - 14) / (duration / 1000.0), MIN_PPS, MAX_PPS
            )
            self.view_start_ms = 0.0
            self._needs_fit = False
        elif duration > 0:
            self._needs_fit = True
        self._clamp_view()
        self._sync_scrollbar()
        self.update()

    def zoom_at(self, factor: float, x: float) -> None:
        new_pps = _clamp(self.px_per_sec * factor, MIN_PPS, MAX_PPS)
        if abs(new_pps - self.px_per_sec) < 1e-6:
            return
        anchor_time = self._x_to_time(x)
        self.px_per_sec = new_pps
        self.view_start_ms = anchor_time - x / new_pps * 1000.0
        self._clamp_view()
        self._sync_scrollbar()
        self.update()

    def zoom_in(self) -> None:
        self.zoom_at(1.35, self.width() / 2)

    def zoom_out(self) -> None:
        self.zoom_at(1 / 1.35, self.width() / 2)

    def _ensure_visible(self, ms: int) -> None:
        duration = self.project.duration_ms
        if duration <= 0:
            return
        visible = self._visible_ms()
        if visible <= 0:
            return
        if ms < self.view_start_ms or ms > self.view_start_ms + visible * 0.92:
            self.view_start_ms = ms - visible * 0.12
            self._clamp_view()
            self._sync_scrollbar()

    def _sync_scrollbar(self) -> None:
        visible = self._visible_ms()
        duration = float(self.project.duration_ms)
        max_start = int(max(0.0, duration - visible))
        self._scroll.blockSignals(True)
        self._scroll.setRange(0, max_start)
        self._scroll.setPageStep(max(1, int(visible)))
        self._scroll.setValue(int(self.view_start_ms))
        self._scroll.blockSignals(False)
        self._scroll.setEnabled(max_start > 0)

    def _on_scroll(self, value: int) -> None:
        self.view_start_ms = float(value)
        self.update()

    # ------------------------------------------------------------------
    # 几何
    # ------------------------------------------------------------------
    def _content_height(self) -> int:
        return max(0, self.height() - SCROLL_H)

    def _lanes(self) -> tuple[QRectF, QRectF, QRectF]:
        width = float(self.width())
        height = float(self._content_height())
        ruler = QRectF(0, 0, width, RULER_H)
        remaining = max(0.0, height - RULER_H)
        track_h = max(78.0, min(150.0, remaining * 0.30))
        wave = QRectF(0, RULER_H, width, max(0.0, remaining - track_h))
        track = QRectF(0, wave.bottom(), width, track_h)
        return ruler, wave, track

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._scroll.setGeometry(0, self.height() - SCROLL_H, self.width(), SCROLL_H)
        if self._needs_fit and self.project.duration_ms > 0 and self.width() > 50:
            self.fit_all()
        self._clamp_view()
        self._sync_scrollbar()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._needs_fit and self.project.duration_ms > 0 and self.width() > 50:
            self.fit_all()

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(COLORS["bg"]))
        ruler, wave, track = self._lanes()

        if wave.height() > 0:
            painter.fillRect(wave, QColor(COLORS["wave_bg"]))
        painter.fillRect(ruler, QColor(COLORS["ruler_bg"]))
        painter.fillRect(track, QColor(COLORS["track_bg"]))

        self._paint_waveform(painter, wave)
        if self._drop_active and wave.height() > 0:
            pen = QPen(QColor(COLORS["accent"]), 1.5, Qt.DashLine)
            pen.setDashPattern([6, 4])
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(wave.adjusted(4, 6, -4, -6), 6, 6)
        self._paint_grid(painter, wave.top(), track.bottom())
        self._paint_loop(painter, track)
        self._paint_blocks(painter, track)
        self._paint_ruler(painter, ruler)
        self._paint_playhead(painter, ruler, track)
        self._paint_hover(painter, ruler, track)

        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.drawLine(0, int(ruler.bottom()), self.width(), int(ruler.bottom()))
        painter.drawLine(0, int(track.top()), self.width(), int(track.top()))

    def _paint_waveform(self, painter: QPainter, rect: QRectF) -> None:
        if rect.height() <= 2:
            return
        mid = rect.center().y()
        half = rect.height() / 2.0 - 5.0
        painter.save()
        painter.setClipRect(rect)
        painter.setRenderHint(QPainter.Antialiasing, False)

        if not self._has_audio():
            self._paint_audio_placeholder(painter, rect)
            painter.restore()
            return

        if self.waveform is None:
            painter.setPen(QColor(COLORS["text_faint"]))
            painter.setFont(QFont("Microsoft YaHei UI", 9))
            message = "正在分析波形…" if self.loading else "音频已载入，但波形不可用"
            painter.drawText(rect, Qt.AlignCenter, message)
            painter.setPen(QPen(QColor(COLORS["border"]), 1))
            painter.drawLine(int(rect.left()), int(mid), int(rect.right()), int(mid))
            painter.restore()
            return

        data = self.waveform
        count = data.bucket_count
        pen = QPen(QColor(COLORS["wave"]), 1)
        painter.setPen(pen)
        y_scale = half / 32768.0
        left = int(rect.left())
        right = int(rect.right())
        for x in range(left, right + 1):
            t0 = self._x_to_time(x)
            t1 = self._x_to_time(x + 1)
            b0 = int(t0 / data.bucket_ms)
            b1 = int(t1 / data.bucket_ms)
            if b1 < b0:
                b1 = b0
            if b1 < 0 or b0 >= count:
                continue
            b0 = max(0, b0)
            b1 = min(count - 1, b1)
            mn = int(data.mins[b0 : b1 + 1].min())
            mx = int(data.maxs[b0 : b1 + 1].max())
            y0 = mid - mx * y_scale
            y1 = mid - mn * y_scale
            painter.drawLine(QPointF(x, y0), QPointF(x, y1 + 0.6))

        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        painter.drawLine(int(rect.left()), int(mid), int(rect.right()), int(mid))
        painter.restore()

    def _paint_audio_placeholder(self, painter: QPainter, rect: QRectF) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        center = rect.center()
        cx = center.x()
        cy = center.y() - 8
        painter.setPen(QPen(QColor(COLORS["accent"]), 1.5))
        painter.setBrush(QColor("#1c3532"))
        painter.drawEllipse(QPointF(cx, cy), 27, 27)
        painter.setPen(QPen(QColor(COLORS["accent_text"]), 2.5))
        painter.drawLine(QPointF(cx - 10, cy), QPointF(cx + 10, cy))
        painter.drawLine(QPointF(cx, cy - 10), QPointF(cx, cy + 10))

        painter.setPen(QColor(COLORS["text_dim"]))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        text = (
            "松开鼠标导入音频"
            if self._drop_active
            else "点击导入音频，或把音频文件拖到这里"
        )
        painter.drawText(
            QRectF(rect.left(), cy + 36, rect.width(), 24),
            Qt.AlignHCenter | Qt.AlignTop,
            text,
        )

    def _paint_grid(self, painter: QPainter, top: float, bottom: float) -> None:
        grid = self.project.grid
        if grid.step_ms <= 0 or self.project.duration_ms <= 0:
            return
        t0, t1 = self.view_start_ms, self.view_start_ms + self._visible_ms()
        if self.project.duration_ms > 0:
            t1 = min(t1, float(self.project.duration_ms))
        if t1 <= t0:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setClipRect(QRectF(0, top, self.width(), max(0.0, bottom - top)))

        layers = (
            (grid.step_ms, COLORS["grid_sub"], 1),
            (grid.beat_ms, COLORS["grid_beat"], 2),
            (grid.bar_ms, COLORS["grid_bar"], 3),
        )
        bar_px = grid.bar_ms * self.px_per_sec / 1000.0

        for step, color, width in layers:
            if step <= 0:
                continue
            if step * self.px_per_sec / 1000.0 < 3.0:
                continue
            pen = QPen(QColor(color), width)
            painter.setPen(pen)
            for time_ms in grid.line_times(t0, t1, step):
                x = int(round(self._time_to_x(time_ms))) + 0.5
                if -1 <= x <= self.width() + 1:
                    painter.drawLine(QPointF(x, top), QPointF(x, bottom))

        if bar_px >= 42.0:
            painter.setFont(QFont("Microsoft YaHei UI", 7))
            painter.setPen(QColor("#5a6575"))
            for time_ms in grid.line_times(t0, t1, grid.bar_ms):
                x = int(round(self._time_to_x(time_ms)))
                number = grid.bar_number(time_ms)
                if number >= 1 and 0 <= x <= self.width() - 12:
                    painter.drawText(QPointF(x + 4, top + 14), str(number))
        painter.restore()

    def _paint_loop(self, painter: QPainter, track: QRectF) -> None:
        if not (self._loop_enabled and self._loop_a is not None and self._loop_b is not None):
            return
        a, b = sorted((self._loop_a, self._loop_b))
        if b <= a:
            return
        xa = self._time_to_x(a)
        xb = self._time_to_x(b)
        painter.save()
        painter.setClipRect(track)
        fill = QColor(COLORS["loop_fill"])
        fill.setAlpha(20)
        painter.fillRect(QRectF(xa, track.top(), xb - xa, track.height()), fill)
        pen = QPen(QColor(COLORS["playhead"]), 1, Qt.DashLine)
        pen.setDashPattern([4, 4])
        painter.setPen(pen)
        for x, label in ((xa, "A"), (xb, "B")):
            painter.drawLine(QPointF(x, track.top()), QPointF(x, track.bottom()))
            painter.setFont(QFont("Microsoft YaHei UI", 7))
            painter.drawText(QPointF(x + 3, track.top() + 12), label)
        painter.restore()

    def _paint_blocks(self, painter: QPainter, track: QRectF) -> None:
        painter.save()
        painter.setClipRect(track)
        font = QFont("Microsoft YaHei UI", 9)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        y = track.top() + 15
        height = max(26.0, track.height() - 30.0)

        if not any(line.start_ms is not None for line in self.project.lines):
            painter.setPen(QColor("#525b69"))
            painter.setFont(QFont("Microsoft YaHei UI", 9))
            if self.loading:
                hint = "正在分析波形…"
            elif not self.project.audio_path or not Path(self.project.audio_path).is_file():
                hint = "先打开音频文件"
            elif not self.project.lines:
                hint = "在左侧输入歌词，再点击这条字幕轨打轴"
            else:
                index = self.current_index if self.current_index is not None else 0
                hint = f"点击这条字幕轨，为第 {index + 1} 句落轴"
            painter.drawText(track, Qt.AlignCenter, hint)
            painter.setFont(font)

        for index, line in enumerate(self.project.lines):
            if line.start_ms is None:
                continue
            start = line.start_ms
            if self._drag and self._drag["index"] == index and self._drag["moved"]:
                start = self._drag["preview"]
            solid_end, actual_end = self._display_bounds(index, start)
            if actual_end <= start:
                continue
            x0 = self._time_to_x(start)
            solid_x1 = self._time_to_x(solid_end)
            actual_x1 = self._time_to_x(actual_end)
            if actual_x1 < -2 or x0 > self.width() + 2:
                continue

            if actual_x1 > solid_x1 + 0.5:
                tail_fill = QColor(COLORS["block"])
                tail_fill.setAlpha(48)
                painter.setBrush(tail_fill)
                tail_pen = QPen(QColor("#2f4a46"), 1, Qt.DashLine)
                tail_pen.setDashPattern([3, 4])
                painter.setPen(tail_pen)
                painter.drawRoundedRect(
                    QRectF(solid_x1, y, max(1.0, actual_x1 - solid_x1), height), 4, 4
                )

            if solid_x1 <= x0:
                continue
            if index == self.selected_index:
                fill = QColor(COLORS["block_selected"])
            elif index == self._hover_block:
                fill = QColor(COLORS["block_hover"])
            else:
                fill = QColor(COLORS["block"] if index % 2 == 0 else COLORS["block_alt"])

            rect = QRectF(x0 + 1, y, max(2.0, solid_x1 - x0 - 2), height)
            painter.setBrush(fill)
            if index == self.selected_index:
                painter.setPen(QPen(QColor(COLORS["selected"]), 2))
            else:
                painter.setPen(QPen(QColor("#365a55"), 1))
            painter.drawRoundedRect(rect, 4, 4)

            text_left = max(x0, 0.0) + 8.0
            text_width = solid_x1 - text_left - 8.0
            if text_width >= 18:
                painter.setPen(QColor("#e9f1f4"))
                elided = metrics.elidedText(line.text, Qt.ElideRight, int(text_width))
                painter.drawText(
                    QRectF(text_left, y, text_width, height),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    elided,
                )

        boundary_index: Optional[int] = None
        if self._drag is not None and self._drag["moved"]:
            boundary_index = int(self._drag["index"])
        elif self._hover_boundary is not None:
            boundary_index = self._hover_boundary
        if boundary_index is not None and 0 <= boundary_index < len(self.project.lines):
            line = self.project.lines[boundary_index]
            if line.start_ms is not None:
                position = line.start_ms
                if self._drag is not None and self._drag["index"] == boundary_index:
                    position = int(self._drag["preview"])
                bx = self._time_to_x(position)
                if -2 <= bx <= self.width() + 2:
                    painter.setPen(QPen(QColor(COLORS["selected"]), 1.5))
                    painter.drawLine(QPointF(bx, y), QPointF(bx, y + height))
        painter.restore()

    def _paint_ruler(self, painter: QPainter, ruler: QRectF) -> None:
        painter.save()
        painter.setClipRect(ruler)
        if self.project.duration_ms <= 0:
            painter.restore()
            return
        font = QFont("Consolas", 8)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        painter.setPen(QColor(COLORS["ruler_text"]))

        step = self._ruler_step()
        minor = step / 5.0
        t0 = self.view_start_ms
        t1 = self.view_start_ms + self._visible_ms()
        if t1 > t0 and self.px_per_sec > 0:
            if minor * self.px_per_sec / 1000.0 >= 6:
                first = math.ceil(t0 / minor) * minor
                t = first
                while t <= t1:
                    x = self._time_to_x(t)
                    if 0 <= x <= self.width():
                        painter.drawLine(
                            QPointF(x, ruler.bottom() - 4), QPointF(x, ruler.bottom())
                        )
                    t += minor

            first = math.ceil(t0 / step) * step
            t = first
            while t <= t1:
                x = self._time_to_x(t)
                if 0 <= x <= self.width() + 2:
                    painter.setPen(QColor(COLORS["border"]))
                    painter.drawLine(
                        QPointF(x, ruler.bottom() - 9), QPointF(x, ruler.bottom())
                    )
                    label = format_ms(t, show_millis=step < 1000)
                    if x + 5 + metrics.horizontalAdvance(label) <= self.width():
                        painter.setPen(QColor(COLORS["ruler_text"]))
                        painter.drawText(QPointF(x + 5, 12), label)
                t += step
        painter.restore()

    def _ruler_step(self) -> float:
        target_ms = 95.0 / max(self.px_per_sec, 0.001) * 1000.0
        for candidate in (
            10, 20, 25, 50, 100, 200, 250, 500,
            1000, 2000, 2500, 5000, 10000, 15000,
            30000, 60000, 120000, 300000, 600000,
        ):
            if candidate >= target_ms:
                return float(candidate)
        return math.ceil(target_ms / 600000.0) * 600000.0

    def _paint_playhead(self, painter: QPainter, ruler: QRectF, track: QRectF) -> None:
        x = self._time_to_x(self.playhead_ms)
        if x < -8 or x > self.width() + 8:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor(COLORS["playhead"]), 1.6)
        painter.setPen(pen)
        painter.drawLine(QPointF(x, ruler.top()), QPointF(x, track.bottom()))
        painter.setBrush(QColor(COLORS["playhead"]))
        painter.setPen(Qt.NoPen)
        triangle = QPolygonF(
            [QPointF(x - 5.5, ruler.top()), QPointF(x + 5.5, ruler.top()), QPointF(x, ruler.top() + 9)]
        )
        painter.drawPolygon(triangle)
        painter.restore()

    def _paint_hover(self, painter: QPainter, ruler: QRectF, track: QRectF) -> None:
        if (
            self._hover_pos is None
            or self._hover_time_ms is None
            or self._drag is not None
            or self._panning
            or self._ruler_drag is not None
        ):
            return
        y = self._hover_pos.y()
        if y < 0 or y > self._content_height():
            return
        x = self._time_to_x(self._hover_time_ms)
        if x < -1 or x > self.width() + 1:
            return
        painter.save()
        pen = QPen(QColor("#dbe2ea"), 1, Qt.DashLine)
        pen.setDashPattern([2, 4])
        painter.setPen(pen)
        painter.drawLine(QPointF(x, ruler.top()), QPointF(x, track.bottom()))

        label = format_ms(self._hover_time_ms)
        font = QFont("Consolas", 8)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        width = metrics.horizontalAdvance(label) + 10
        left = x + 8
        if left + width > self.width():
            left = x - width - 8
        box = QRectF(left, 2, width, 16)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#252b35"))
        painter.drawRoundedRect(box, 3, 3)
        painter.setPen(QColor("#e6ecf3"))
        painter.drawText(box, Qt.AlignCenter, label)
        painter.restore()

    # ------------------------------------------------------------------
    # 命中与时间
    # ------------------------------------------------------------------
    def _end_for(self, index: int, start: int) -> int:
        if self._drag and self._drag["index"] == index + 1 and self._drag["moved"]:
            preview = int(self._drag["preview"])
            if preview > start:
                return preview
        nxt = self.project.next_marked_start(index)
        if nxt is not None and nxt > start:
            return nxt
        if self.project.duration_ms > start:
            return self.project.duration_ms
        return start + 1000

    def _last_marked_index(self) -> int:
        for i in range(len(self.project.lines) - 1, -1, -1):
            if self.project.lines[i].start_ms is not None:
                return i
        return -1

    def _display_bounds(self, index: int, start: int) -> tuple[int, int]:
        """返回 (实心块结束, 实际结束)。

        最后一句在还有未打轴歌词时，结束时间暂定延伸到音频末尾。为了不让
        它看起来像持续了几十秒，实心块只画一小段，后面用半透明尾巴表示
        “这一句会持续到下一句”，点击尾巴即可继续打轴。
        """
        actual_end = self._end_for(index, start)
        if (
            index == self._last_marked_index()
            and self.project.next_unmarked_index() is not None
        ):
            provisional = start + max(float(self.project.grid.bar_ms), 2000.0)
            solid_end = min(float(actual_end), provisional)
            return int(round(solid_end)), actual_end
        return actual_end, actual_end

    def _block_at(self, pos: QPoint | QPointF, include_last_body: bool = False) -> int:
        _, _, track = self._lanes()
        point = QPointF(pos)
        if not track.contains(point):
            return -1
        last_marked = self._last_marked_index()
        sequential = self.project.next_unmarked_index() is not None
        for index in range(len(self.project.lines) - 1, -1, -1):
            line = self.project.lines[index]
            if line.start_ms is None:
                continue
            solid_end, _ = self._display_bounds(index, line.start_ms)
            x0 = self._time_to_x(line.start_ms)
            x1 = self._time_to_x(solid_end)
            if sequential and index == last_marked and not include_last_body:
                # 最后一句的实心块和尾巴都让位给“继续打下一句”，
                # 它的句首用左侧的边界手柄调整。
                continue
            if x0 - 1 <= point.x() <= x1 + 1:
                return index
        return -1

    def _boundary_at(self, pos: QPoint | QPointF) -> Optional[int]:
        """返回鼠标附近可拖动的句首边界对应的歌词下标。"""
        _, _, track = self._lanes()
        point = QPointF(pos)
        if not track.contains(point):
            return None

        first_marked = -1
        for i, line in enumerate(self.project.lines):
            if line.start_ms is not None:
                first_marked = i
                break
        if first_marked < 0:
            return None

        best_index: Optional[int] = None
        best_distance = BOUNDARY_PX + 1.0
        for index, line in enumerate(self.project.lines):
            if line.start_ms is None:
                continue
            if index != first_marked and self.project.previous_marked_start(index) is None:
                continue
            x = self._time_to_x(line.start_ms)
            distance = abs(point.x() - x)
            if distance <= BOUNDARY_PX and distance < best_distance:
                best_index = index
                best_distance = distance
        return best_index

    def _snap_time(self, t_ms: float, modifiers) -> int:
        duration = self.project.duration_ms
        t = _clamp(t_ms, 0.0, float(duration) if duration > 0 else max(0.0, t_ms))
        if not (modifiers & Qt.AltModifier):
            t = float(self.project.grid.snap(t))
        if duration > 0:
            t = _clamp(t, 0.0, float(duration))
        return int(round(t))

    def _time_for_x(self, x: float, modifiers) -> int:
        """把横坐标转换成用于播放头/悬停指示线的时间。

        吸附是否生效只看“吸附”下拉框；Alt 只影响落轴和边界拖动，
        这样“无”以外的选项下播放头和指示线都会稳定停在网格上。
        """
        duration = self.project.duration_ms
        t = self._x_to_time(x)
        if duration > 0:
            t = _clamp(t, 0.0, float(duration))
        else:
            t = max(0.0, t)
        t = float(self.project.grid.snap(t))
        if duration > 0:
            t = _clamp(t, 0.0, float(duration))
        return int(round(t))

    def _clamp_drag_start(self, index: int, t_ms: float, modifiers) -> int:
        line = self.project.lines[index]
        old = line.start_ms or 0
        duration = self.project.duration_ms
        t = _clamp(t_ms, 0.0, float(duration) if duration > 0 else max(0.0, t_ms))
        if not (modifiers & Qt.AltModifier):
            t = float(self.project.grid.snap(t))
        low = 0.0
        prev = self.project.previous_marked_start(index)
        if prev is not None:
            low = prev + MIN_GAP_MS
        high = float(max(0, duration - MIN_GAP_MS)) if duration > 0 else float(old)
        nxt = self.project.next_marked_start(index)
        if nxt is not None:
            high = min(high, nxt - MIN_GAP_MS)
        if high <= low:
            return old
        return int(round(_clamp(t, low, high)))

    # ------------------------------------------------------------------
    # 鼠标 / 滚轮
    # ------------------------------------------------------------------
    def _update_cursor(self, pos: QPointF) -> None:
        if self._panning or (self._ruler_drag and self._ruler_drag.get("moved")):
            self.setCursor(Qt.ClosedHandCursor)
            return
        if self._drag is not None:
            self.setCursor(Qt.SizeHorCursor)
            return
        ruler, wave, track = self._lanes()
        if track.contains(pos):
            if self._boundary_at(pos) is not None:
                self.setCursor(Qt.SizeHorCursor)
            elif self._block_at(pos) >= 0:
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.CrossCursor)
        elif ruler.contains(pos):
            if abs(pos.x() - self._time_to_x(self.playhead_ms)) <= PLAYHEAD_GRAB_PX:
                self.setCursor(Qt.SizeHorCursor)
            else:
                self.setCursor(Qt.OpenHandCursor)
        elif wave.contains(pos):
            if self._has_audio():
                self.setCursor(Qt.SizeHorCursor)
            else:
                self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        self.setFocus()
        self._pressed_block = None
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_last_x = pos.x()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() != Qt.LeftButton:
            return

        ruler, wave, track = self._lanes()
        if ruler.contains(pos):
            if abs(pos.x() - self._time_to_x(self.playhead_ms)) <= PLAYHEAD_GRAB_PX:
                self._scrubbing = True
                self._emit_seek(pos.x(), event.modifiers())
            else:
                self._ruler_drag = {
                    "press_x": pos.x(),
                    "view_start": self.view_start_ms,
                    "moved": False,
                }
            return

        if wave.contains(pos):
            if not self._has_audio():
                self.audio_import_requested.emit()
                return
            self._scrubbing = True
            self._emit_seek(pos.x(), event.modifiers())
            return

        if track.contains(pos):
            boundary = self._boundary_at(pos)
            if boundary is not None:
                line = self.project.lines[boundary]
                self.selected_index = boundary
                self._drag = {
                    "index": boundary,
                    "press_x": pos.x(),
                    "old_start": line.start_ms or 0,
                    "moved": False,
                    "preview": line.start_ms or 0,
                }
                self.line_selected.emit(boundary)
                self.update()
                return

            index = self._block_at(pos)
            if index >= 0:
                self._pressed_block = index
                self.selected_index = index
                self.line_selected.emit(index)
                self.update()
                return

            t = self._snap_time(self._x_to_time(pos.x()), event.modifiers())
            self.mark_requested.emit(t)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        self._hover_pos = pos
        self._hover_block = self._block_at(pos) if not self._panning else None
        self._hover_boundary = self._boundary_at(pos) if not self._panning else None

        if self._scrubbing:
            self._emit_seek(pos.x(), event.modifiers())
        elif self._ruler_drag is not None:
            drag = self._ruler_drag
            dx = pos.x() - drag["press_x"]
            if not drag["moved"] and abs(dx) >= 3:
                drag["moved"] = True
            if drag["moved"]:
                self.view_start_ms = (
                    drag["view_start"] - dx / max(self.px_per_sec, 0.001) * 1000.0
                )
                self._clamp_view()
                self._sync_scrollbar()
                self.update()
        elif self._panning:
            dx = pos.x() - self._pan_last_x
            self._pan_last_x = pos.x()
            self.view_start_ms -= dx / max(self.px_per_sec, 0.001) * 1000.0
            self._clamp_view()
            self._sync_scrollbar()
            self.update()
        elif self._drag is not None:
            drag = self._drag
            if not drag["moved"] and abs(pos.x() - drag["press_x"]) >= 3:
                drag["moved"] = True
            if drag["moved"]:
                preview = self._clamp_drag_start(
                    drag["index"], self._x_to_time(pos.x()), event.modifiers()
                )
                drag["preview"] = preview
                self.update()

        self._update_cursor(pos)
        t = self._time_for_x(pos.x(), event.modifiers())
        self._hover_time_ms = t
        self.hover_time_changed.emit(t)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning and event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            return

        if self._ruler_drag is not None and event.button() == Qt.LeftButton:
            drag = self._ruler_drag
            self._ruler_drag = None
            if not drag["moved"]:
                self._emit_seek(event.position().x(), event.modifiers())
            self.update()
            return

        if self._scrubbing and event.button() == Qt.LeftButton:
            self._scrubbing = False
            return

        if self._drag is not None and event.button() == Qt.LeftButton:
            drag = self._drag
            self._drag = None
            index = drag["index"]
            if drag["moved"]:
                if drag["preview"] != drag["old_start"]:
                    self.line_start_committed.emit(index, int(drag["preview"]))
            else:
                line = self.project.lines[index]
                if line.start_ms is not None:
                    self.seek_requested.emit(int(line.start_ms))
            self.update()
            return

        if self._pressed_block is not None and event.button() == Qt.LeftButton:
            index = self._pressed_block
            self._pressed_block = None
            line = self.project.lines[index]
            if line.start_ms is not None:
                self.seek_requested.emit(int(line.start_ms))
            self.update()

    def _drop_path(self, event) -> Optional[str]:
        _, wave, _ = self._lanes()
        if not wave.contains(event.position()):
            return None
        mime = event.mimeData()
        if mime is None or not mime.hasUrls():
            return None
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if not path:
                continue
            if Path(path).suffix.lower() not in AUDIO_SUFFIXES:
                continue
            if Path(path).is_file():
                return path
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._drop_path(event) is not None:
            self._drop_active = True
            self.update()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        active = self._drop_path(event) is not None
        if active != self._drop_active:
            self._drop_active = active
            self.update()
        if active:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        if self._drop_active:
            self._drop_active = False
            self.update()
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        path = self._drop_path(event)
        self._drop_active = False
        self.update()
        if path is not None:
            self.audio_dropped.emit(path)
            event.acceptProposedAction()
        else:
            event.ignore()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta == 0:
            return
        if event.modifiers() & Qt.ShiftModifier:
            self.view_start_ms -= (delta / 120.0) * 100.0 / max(self.px_per_sec, 0.001) * 1000.0
            self._clamp_view()
            self._sync_scrollbar()
        else:
            factor = 1.25 ** (delta / 120.0)
            self.zoom_at(factor, event.position().x())
        self.update()
        event.accept()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        index = self._block_at(event.pos(), include_last_body=True)
        if index >= 0:
            self.selected_index = index
            self.line_selected.emit(index)
            self.update()
        self.context_menu_requested.emit(index, event.globalPos())
        event.accept()

    def leaveEvent(self, event) -> None:
        self._hover_pos = None
        self._hover_block = None
        self._hover_boundary = None
        self._hover_time_ms = None
        self.hover_time_changed.emit(-1)
        self.setCursor(Qt.ArrowCursor)
        self.update()
        super().leaveEvent(event)

    def _emit_seek(self, x: float, modifiers=Qt.NoModifier) -> None:
        self.seek_requested.emit(self._time_for_x(x, modifiers))
