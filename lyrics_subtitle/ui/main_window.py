from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt, QThread, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..audio import WaveformData, decode_waveform
from ..core import (
    MIN_GAP_MS,
    NOTE_LABELS,
    GridSettings,
    LyricLine,
    Project,
    format_ms,
    load_project,
    save_project,
)
from ..exporters import ExportError, build_lrc, build_srt, write_text_file
from ..history import History
from .panel import LyricsPanel
from .player import AudioPlayer
from .timeline import TimelineView

SPEEDS = (0.5, 0.75, 1.0, 1.25, 1.5)
SNAP_CHOICES = (1, 2, 3, 4, 6, 8, 12, 16)


class WaveformWorker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, path: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._path = path

    def run(self) -> None:
        try:
            data = decode_waveform(self._path)
        except Exception as exc:  # noqa: BLE001 - 要显示给用户
            self.failed.emit(str(exc))
            return
        self.done.emit(data)


class SpaceFilter(QWidget):
    """应用级空格键过滤器：编辑文字时让空格正常输入，其余时候播放/暂停。"""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self._main = window

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space:
            if event.isAutoRepeat():
                return True
            if QApplication.activeWindow() is not self._main:
                return False
            focus = QApplication.focusWidget()
            if isinstance(focus, (QLineEdit, QAbstractSpinBox, QPlainTextEdit, QTextEdit)):
                return False
            if isinstance(focus, QTableWidget) and focus.state() == QAbstractItemView.EditingState:
                return False
            self._main.toggle_play()
            return True
        return False


def _media_icon(playing: bool) -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#ffffff"))
    if playing:
        painter.drawRect(4, 3, 3, 10)
        painter.drawRect(9, 3, 3, 10)
    else:
        painter.drawPolygon(
            QPolygonF([QPointF(4, 3), QPointF(13, 8), QPointF(4, 13)])
        )
    painter.end()
    return QIcon(pixmap)


def _make_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#2a6f66"))
    painter.drawRoundedRect(2, 2, 60, 60, 14, 14)
    painter.setPen(QColor("#ffffff"))
    font = QFont("Microsoft YaHei UI", 26)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "词")
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project = Project()
        self.history = History()
        self.player = AudioPlayer(self)

        self._project_path: Optional[Path] = None
        self._last_dir = Path.home()
        self._dirty = False
        self._updating_ui = False
        self._playing = False
        self._audio_loading = False
        self._duration_from_decode = False
        self._audio_token = 0
        self._worker: Optional[WaveformWorker] = None
        self._last_player_error = ""
        self._loop_a: Optional[int] = None
        self._loop_b: Optional[int] = None

        self.setMinimumSize(1000, 640)
        self._apply_default_size()
        self.setWindowIcon(_make_icon())

        self._build_ui()
        self._build_actions()
        self._connect()
        self._refresh_all()

        self._space_filter = SpaceFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._space_filter)

        self._update_title()
        self._update_status()
        self._update_grid_visibility()

    def _update_grid_visibility(self) -> None:
        visible = self.width() >= 1150
        if hasattr(self, "grid_label"):
            self.grid_label.setVisible(visible)
            self.grid_sep.setVisible(visible)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_grid_visibility()

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------
    def _bar(self) -> tuple[QFrame, QHBoxLayout]:
        frame = QFrame()
        frame.setObjectName("Toolbar")
        frame.setFixedHeight(42)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(4)
        return frame, layout

    def _tb(
        self,
        text: str,
        tip: str,
        slot=None,
        checkable: bool = False,
        name: str = "",
    ) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setFocusPolicy(Qt.NoFocus)
        button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        if checkable:
            button.setCheckable(True)
        if name:
            button.setObjectName(name)
        if slot is not None:
            button.clicked.connect(slot)
        return button

    def _sep(self) -> QFrame:
        line = QFrame()
        line.setObjectName("Sep")
        line.setFixedSize(1, 20)
        return line

    def _dim_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DimLabel")
        return label

    def _apply_default_size(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1400, 860)
            return
        available = screen.availableGeometry()
        width = min(1440, max(1000, int(available.width() * 0.92)))
        height = min(900, max(640, int(available.height() * 0.92)))
        self.resize(width, height)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("Central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 文件栏 ----------------------------------------------------
        file_bar, file_layout = self._bar()
        brand = QLabel("歌词打轴")
        brand_font = QFont("Microsoft YaHei UI", 11)
        brand_font.setBold(True)
        brand.setFont(brand_font)
        brand.setStyleSheet("color:#8fe8dc; padding:0 6px 0 2px;")
        file_layout.addWidget(brand)
        file_layout.addWidget(self._sep())

        self.btn_new = self._tb("新建", "新建工程 (Ctrl+N)", self.new_project)
        self.btn_open_audio = self._tb("打开音频", "打开音频文件 (Ctrl+O)", self.open_audio)
        self.btn_open_project = self._tb("打开工程", "打开已保存的工程 (Ctrl+Shift+O)", self.open_project)
        self.btn_save = self._tb("保存", "保存工程 (Ctrl+S)", self.save_project)
        self.btn_export_lrc = self._tb("导出 LRC", "导出网易云等平台使用的 LRC 歌词", self.export_lrc)
        self.btn_export_srt = self._tb("导出 SRT", "导出视频剪辑软件使用的 SRT 字幕", self.export_srt)
        for button in (
            self.btn_new,
            self.btn_open_audio,
            self.btn_open_project,
            self.btn_save,
        ):
            file_layout.addWidget(button)
        file_layout.addWidget(self._sep())
        for button in (self.btn_export_lrc, self.btn_export_srt):
            file_layout.addWidget(button)

        file_layout.addStretch(1)
        self.btn_help = self._tb("快捷键", "查看快捷键与使用说明 (F1)", self.show_shortcuts)
        file_layout.addWidget(self.btn_help)
        self.follow_btn = self._tb(
            "跟随播放头", "播放时自动滚动时间轴", None, checkable=True
        )
        self.follow_btn.setChecked(True)
        file_layout.addWidget(self.follow_btn)
        root.addWidget(file_bar)

        # ---- 播放栏 ----------------------------------------------------
        transport, transport_layout = self._bar()
        self.play_btn = self._tb("播放", "播放 / 暂停（空格）", self.toggle_play, name="PlayButton")
        self.play_btn.setIcon(_media_icon(False))
        self.play_btn.setIconSize(QSize(14, 14))
        self.play_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.play_btn.setMinimumWidth(92)
        transport_layout.addWidget(self.play_btn)

        self.time_label = QLabel("0:00.000 / 0:00.000")
        self.time_label.setObjectName("TimeLabel")
        self.time_label.setFont(QFont("Consolas", 11))
        self.time_label.setMinimumWidth(210)
        transport_layout.addWidget(self.time_label)
        transport_layout.addWidget(self._sep())

        transport_layout.addWidget(self._dim_label("速度"))
        self.speed_combo = QComboBox()
        for value in SPEEDS:
            self.speed_combo.addItem(f"{value:g}×", value)
        self.speed_combo.setCurrentIndex(2)
        self.speed_combo.setFixedWidth(72)
        transport_layout.addWidget(self.speed_combo)
        transport_layout.addWidget(self._sep())

        self.loop_a_btn = self._tb("A", "把当前播放位置设为循环起点", self.set_loop_a)
        self.loop_b_btn = self._tb("B", "把当前播放位置设为循环终点", self.set_loop_b)
        self.loop_btn = self._tb("循环", "开启 / 关闭 A-B 循环", None, checkable=True)
        for button in (self.loop_a_btn, self.loop_b_btn, self.loop_btn):
            transport_layout.addWidget(button)
        transport_layout.addWidget(self._sep())

        self.zoom_out_btn = self._tb("−", "缩小时间轴", self.timeline_zoom_out)
        self.zoom_in_btn = self._tb("+", "放大时间轴", self.timeline_zoom_in)
        self.fit_btn = self._tb("适配", "显示整首音频", self.timeline_fit)
        for button in (self.zoom_out_btn, self.zoom_in_btn, self.fit_btn):
            transport_layout.addWidget(button)
        transport_layout.addStretch(1)
        root.addWidget(transport)

        # ---- 网格栏 ----------------------------------------------------
        grid_bar, grid_layout = self._bar()
        grid_layout.addWidget(self._dim_label("BPM"))
        self.bpm_spin = QDoubleSpinBox()
        self.bpm_spin.setRange(20.0, 400.0)
        self.bpm_spin.setDecimals(1)
        self.bpm_spin.setSingleStep(1.0)
        self.bpm_spin.setValue(120.0)
        self.bpm_spin.setKeyboardTracking(False)
        self.bpm_spin.setFixedWidth(78)
        self.bpm_spin.setToolTip("歌曲速度；具体按哪个音符计数由右侧的 BPM 基准决定")
        grid_layout.addWidget(self.bpm_spin)
        grid_layout.addWidget(self._sep())

        grid_layout.addWidget(self._dim_label("拍号"))
        self.num_combo = QComboBox()
        for n in range(1, 17):
            self.num_combo.addItem(str(n), n)
        self.num_combo.setCurrentIndex(3)
        self.num_combo.setFixedWidth(48)
        self.num_combo.setToolTip("拍号分子：每小节几拍")
        grid_layout.addWidget(self.num_combo)
        grid_layout.addWidget(self._dim_label("/"))
        self.den_combo = QComboBox()
        for den in (2, 4, 8, 16):
            self.den_combo.addItem(str(den), den)
        self.den_combo.setCurrentIndex(1)
        self.den_combo.setFixedWidth(48)
        self.den_combo.setToolTip("拍号分母：一拍对应哪种音符")
        grid_layout.addWidget(self.den_combo)
        grid_layout.addWidget(self._sep())

        base_label = QLabel("BPM 基准")
        base_label.setObjectName("DimLabel")
        grid_layout.addWidget(base_label)
        self.base_combo = QComboBox()
        for value in (2, 4, 8, 16):
            self.base_combo.addItem(NOTE_LABELS[value], value)
        self.base_combo.setCurrentIndex(1)
        self.base_combo.setFixedWidth(128)
        self.base_combo.setToolTip(
            "BPM 按哪个音符计数。默认四分音符；6/8 若 BPM 指八分音符速度，这里选八分音符"
        )
        grid_layout.addWidget(self.base_combo)
        grid_layout.addWidget(self._sep())

        grid_layout.addWidget(self._dim_label("吸附"))
        self.snap_combo = QComboBox()
        self.snap_combo.addItem("无", 0)
        for value in SNAP_CHOICES:
            self.snap_combo.addItem(f"{value} 格/拍", value)
        self.snap_combo.setCurrentIndex(4)
        self.snap_combo.setFixedWidth(92)
        self.snap_combo.setToolTip(
            "每拍细分几格；4 格/拍相当于十六分音符。选择“无”可关闭吸附，连续拖动播放头"
        )
        grid_layout.addWidget(self.snap_combo)
        grid_layout.addWidget(self._sep())

        grid_layout.addWidget(self._dim_label("偏移"))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-3600000, 3600000)
        self.offset_spin.setSuffix(" ms")
        self.offset_spin.setKeyboardTracking(False)
        self.offset_spin.setFixedWidth(108)
        self.offset_spin.setToolTip("第一小节第一拍所在的绝对时间；用来对齐前奏后的首拍")
        grid_layout.addWidget(self.offset_spin)
        self.offset_btn = self._tb("设为首拍", "把当前播放位置设为第一小节第一拍", self.set_offset_to_playhead)
        grid_layout.addWidget(self.offset_btn)

        grid_layout.addWidget(self._sep())
        self.grid_sep = self._sep()
        grid_layout.addWidget(self.grid_sep)
        self.grid_label = QLabel("")
        self.grid_label.setObjectName("DimLabel")
        grid_layout.addWidget(self.grid_label)
        grid_layout.addStretch(1)
        root.addWidget(grid_bar)

        # ---- 主体 ------------------------------------------------------
        self.panel = LyricsPanel()
        self.panel.setMinimumWidth(300)
        self.panel.setMaximumWidth(620)
        self.timeline = TimelineView()

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.panel)
        splitter.addWidget(self.timeline)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 1060])
        root.addWidget(splitter, 1)

        # ---- 状态栏 ----------------------------------------------------
        status = self.statusBar()
        status.setSizeGripEnabled(True)
        self.progress_label = QLabel("未打开音频")
        self.progress_label.setMinimumWidth(190)
        self.target_label = QLabel("")
        self.target_label.setMinimumWidth(160)
        self.hover_label = QLabel("")
        self.hover_label.setMinimumWidth(150)
        self.hover_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        status.addWidget(self.progress_label)
        status.addPermanentWidget(self.target_label)
        status.addPermanentWidget(self.hover_label)

    def _build_actions(self) -> None:
        self.act_new = QAction("新建工程", self)
        self.act_new.setShortcut(QKeySequence("Ctrl+N"))
        self.act_new.triggered.connect(self.new_project)

        self.act_open_audio = QAction("打开音频…", self)
        self.act_open_audio.setShortcut(QKeySequence("Ctrl+O"))
        self.act_open_audio.triggered.connect(self.open_audio)

        self.act_open_project = QAction("打开工程…", self)
        self.act_open_project.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.act_open_project.triggered.connect(self.open_project)

        self.act_save = QAction("保存工程", self)
        self.act_save.setShortcut(QKeySequence("Ctrl+S"))
        self.act_save.triggered.connect(self.save_project)

        self.act_save_as = QAction("另存为…", self)
        self.act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.act_save_as.triggered.connect(self.save_project_as)

        self.act_export_lrc = QAction("导出 LRC…", self)
        self.act_export_lrc.triggered.connect(self.export_lrc)

        self.act_export_srt = QAction("导出 SRT…", self)
        self.act_export_srt.triggered.connect(self.export_srt)

        self.act_quit = QAction("退出", self)
        self.act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self.act_quit.triggered.connect(self.close)

        self.act_undo = QAction("撤销", self)
        self.act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self.act_undo.triggered.connect(self.undo)

        self.act_redo = QAction("重做", self)
        self.act_redo.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        self.act_redo.triggered.connect(self.redo)

        self.act_edit_lyrics = QAction("编辑歌词…", self)
        self.act_edit_lyrics.setShortcut(QKeySequence("Ctrl+E"))
        self.act_edit_lyrics.triggered.connect(self.panel.open_editor)

        self.act_clear_times = QAction("清空所有时间", self)
        self.act_clear_times.triggered.connect(self.clear_all_times)

        self.act_zoom_in = QAction("放大", self)
        self.act_zoom_in.setShortcut(QKeySequence("Ctrl+="))
        self.act_zoom_in.triggered.connect(self.timeline_zoom_in)

        self.act_zoom_out = QAction("缩小", self)
        self.act_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        self.act_zoom_out.triggered.connect(self.timeline_zoom_out)

        self.act_fit = QAction("适配窗口", self)
        self.act_fit.setShortcut(QKeySequence("Ctrl+0"))
        self.act_fit.triggered.connect(self.timeline_fit)

        self.act_follow = QAction("跟随播放头", self)
        self.act_follow.setCheckable(True)
        self.act_follow.setChecked(True)
        self.act_follow.toggled.connect(self._set_follow)

        self.act_play = QAction("播放 / 暂停", self)
        self.act_play.triggered.connect(self.toggle_play)

        self.act_set_a = QAction("设置循环起点 A", self)
        self.act_set_a.triggered.connect(self.set_loop_a)
        self.act_set_b = QAction("设置循环终点 B", self)
        self.act_set_b.triggered.connect(self.set_loop_b)

        self.act_shortcuts = QAction("快捷键与说明", self)
        self.act_shortcuts.setShortcut(QKeySequence("F1"))
        self.act_shortcuts.triggered.connect(self.show_shortcuts)

        self.act_about = QAction("关于", self)
        self.act_about.triggered.connect(self.show_about)

        menu = self.menuBar()
        file_menu = menu.addMenu("文件")
        file_menu.addAction(self.act_new)
        file_menu.addAction(self.act_open_audio)
        file_menu.addAction(self.act_open_project)
        file_menu.addSeparator()
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_export_lrc)
        file_menu.addAction(self.act_export_srt)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        edit_menu = menu.addMenu("编辑")
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_edit_lyrics)
        edit_menu.addAction(self.act_clear_times)

        view_menu = menu.addMenu("视图")
        view_menu.addAction(self.act_zoom_in)
        view_menu.addAction(self.act_zoom_out)
        view_menu.addAction(self.act_fit)
        view_menu.addSeparator()
        view_menu.addAction(self.act_follow)

        play_menu = menu.addMenu("播放")
        play_menu.addAction(self.act_play)
        play_menu.addSeparator()
        play_menu.addAction(self.act_set_a)
        play_menu.addAction(self.act_set_b)

        help_menu = menu.addMenu("帮助")
        help_menu.addAction(self.act_shortcuts)
        help_menu.addAction(self.act_about)

    def _connect(self) -> None:
        self.follow_btn.toggled.connect(self._set_follow)
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        self.loop_btn.toggled.connect(self.toggle_loop)

        self.bpm_spin.valueChanged.connect(self._on_grid_changed)
        self.num_combo.currentIndexChanged.connect(self._on_grid_changed)
        self.den_combo.currentIndexChanged.connect(self._on_grid_changed)
        self.base_combo.currentIndexChanged.connect(self._on_grid_changed)
        self.snap_combo.currentIndexChanged.connect(self._on_grid_changed)
        self.offset_spin.valueChanged.connect(self._on_grid_changed)

        self.timeline.seek_requested.connect(self.seek)
        self.timeline.mark_requested.connect(self.mark_at)
        self.timeline.line_selected.connect(self._on_timeline_line_selected)
        self.timeline.line_start_committed.connect(self._on_drag_committed)
        self.timeline.context_menu_requested.connect(self._on_timeline_menu)
        self.timeline.hover_time_changed.connect(self._on_hover_time)
        self.timeline.audio_import_requested.connect(self.open_audio)
        self.timeline.audio_dropped.connect(self._on_audio_dropped)

        self.panel.lines_replaced.connect(self.replace_lyrics)
        self.panel.text_changed.connect(self._on_text_edited)
        self.panel.seek_requested.connect(self.seek)
        self.panel.selection_changed.connect(self._on_panel_selection)
        self.panel.clear_times_requested.connect(self.clear_all_times)
        self.panel.clear_from_requested.connect(self.clear_from)

        self.player.position_changed.connect(self._on_player_position)
        self.player.duration_changed.connect(self._on_player_duration)
        self.player.playing_changed.connect(self._on_playing_changed)
        self.player.error.connect(self._on_player_error)

    # ------------------------------------------------------------------
    # 整体刷新
    # ------------------------------------------------------------------
    def _refresh_all(self) -> None:
        self.timeline.set_project(self.project)
        self._apply_grid_to_ui()
        self._sync_views(None)
        self._update_time_label()
        self._update_status()

    def _sync_views(self, selected: Optional[int]) -> None:
        current = self.project.next_unmarked_index()
        self.timeline.project = self.project
        self.timeline.current_index = current
        self.timeline.set_selected(selected)
        self.panel.set_lines(self.project.lines, current, selected)
        self.timeline.refresh()
        self._update_count()

    def _update_count(self) -> None:
        marked = self.project.marked_count
        total = len(self.project.lines)
        prefix = "正在分析波形 · " if self._audio_loading else ""
        self.progress_label.setText(f"{prefix}已打轴 {marked}/{total}")

    def _update_status(self) -> None:
        self._update_count()
        total = len(self.project.lines)
        nxt = self.project.next_unmarked_index()
        if total == 0:
            text = "请先在左侧输入歌词"
        elif nxt is None:
            text = "全部歌词已打轴"
        else:
            text = f"下一句：第 {nxt + 1} 句"
        self.target_label.setText(text)

    def _update_time_label(self) -> None:
        self.time_label.setText(
            f"{format_ms(self.timeline.playhead_ms)} / {format_ms(self.project.duration_ms)}"
        )

    def _update_grid_label(self) -> None:
        text = self.project.grid.describe()
        self.grid_label.setText(text)
        self.grid_label.setToolTip(text)
        self.bpm_spin.setToolTip("歌曲速度（按 BPM 基准音符计数）\n" + text)

    def _update_title(self) -> None:
        if self.project.audio_path:
            name = Path(self.project.audio_path).stem
        elif self._project_path is not None:
            name = self._project_path.stem
        else:
            name = "未命名"
        prefix = "● " if self._dirty else ""
        self.setWindowTitle(f"{prefix}{name} — 歌词打轴 · LyricsSubtitle")

    def _mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self._update_title()

    def _toast(self, message: str, timeout: int = 3000) -> None:
        self.statusBar().showMessage(message, timeout)

    def _on_hover_time(self, ms: int) -> None:
        if ms < 0:
            self.hover_label.setText("")
        else:
            self.hover_label.setText(f"光标 {format_ms(ms)}")

    def _set_follow(self, checked: bool) -> None:
        self.timeline.follow = bool(checked)
        for widget in (self.follow_btn, self.act_follow):
            widget.blockSignals(True)
            widget.setChecked(bool(checked))
            widget.blockSignals(False)

    def _on_speed_changed(self, *args) -> None:
        rate = self.speed_combo.currentData()
        if rate is not None:
            self.player.set_rate(float(rate))

    # ------------------------------------------------------------------
    # 工程与音频
    # ------------------------------------------------------------------
    def _maybe_save(self) -> bool:
        if not self._dirty:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("保存更改")
        box.setText("当前工程有未保存的更改，是否保存？")
        save = box.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("不保存", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            return self.save_project()
        if clicked is discard:
            return True
        return False

    def new_project(self) -> None:
        if not self._maybe_save():
            return
        self.player.unload()
        self.player.stop()
        self._reset_loop()
        self._audio_token += 1
        self._audio_loading = False
        self._duration_from_decode = False
        self.project = Project()
        self._project_path = None
        self.history.clear()
        self.timeline.set_waveform(None)
        self.timeline.set_loading(False)
        self.timeline.set_project(self.project)
        self.timeline.set_playhead(0)
        self.timeline.px_per_sec = 42.0
        self.timeline.view_start_ms = 0.0
        self.panel.set_lines([], None)
        self._apply_grid_to_ui()
        self._sync_views(None)
        self._dirty = False
        self._update_title()
        self._update_time_label()
        self._update_status()
        self._toast("已新建工程")

    def open_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开音频",
            str(self._last_dir),
            "音频文件 (*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus);;所有文件 (*)",
        )
        if not path:
            return
        self._last_dir = Path(path).parent
        self._load_audio(path)

    def _on_audio_dropped(self, path: str) -> None:
        source = Path(path)
        if not source.is_file():
            self._toast("拖入的文件不存在")
            return
        self._last_dir = source.parent
        self._load_audio(str(source))

    def _load_audio(self, path: str, sync: bool = False, fallback_duration: int = 0) -> None:
        source = Path(path)
        if not source.is_file():
            QMessageBox.warning(self, "打开音频", f"找不到音频文件：\n{source}")
            return

        self.player.unload()
        self.player.load(str(source))
        self._reset_loop()
        self._last_player_error = ""
        self.project.audio_path = str(source)
        self.project.duration_ms = max(0, int(fallback_duration))
        self._duration_from_decode = False
        self._audio_loading = True
        self._audio_token += 1
        token = self._audio_token

        self.timeline.set_waveform(None)
        self.timeline.set_project(self.project)
        self.timeline.set_loading(True)
        self.timeline.set_playhead(0)
        self.timeline.px_per_sec = 42.0
        self.timeline.view_start_ms = 0.0

        self._mark_dirty()
        self._update_title()
        self._update_time_label()
        self._update_status()
        self._toast("正在分析波形…", 5000)

        if sync:
            try:
                waveform = decode_waveform(str(source))
            except Exception as exc:  # noqa: BLE001
                self._on_waveform_failed(str(exc), token)
                return
            self._on_waveform_ready(waveform, token)
            return

        worker = WaveformWorker(str(source), self)
        worker.done.connect(lambda data, t=token: self._on_waveform_ready(data, t))
        worker.failed.connect(lambda message, t=token: self._on_waveform_failed(message, t))
        worker.finished.connect(lambda w=worker: self._on_worker_finished(w))
        self._worker = worker
        worker.start()

    def _on_worker_finished(self, worker: WaveformWorker) -> None:
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

    def _on_waveform_ready(self, waveform: WaveformData, token: int) -> None:
        if token != self._audio_token:
            return
        self._audio_loading = False
        self._duration_from_decode = True
        self.project.duration_ms = int(waveform.duration_ms)
        self.timeline.set_waveform(waveform)
        self.timeline.set_loading(False)
        self.timeline.set_playhead(min(self.timeline.playhead_ms, self.project.duration_ms))
        self.timeline.fit_all()
        self._update_time_label()
        self._update_status()
        self._toast(f"音频已载入：{format_ms(self.project.duration_ms)}")

        too_late = [
            i + 1 for i, line in enumerate(self.project.lines)
            if line.start_ms is not None and line.start_ms > self.project.duration_ms
        ]
        if too_late:
            self._toast(
                f"注意：第 {', '.join(map(str, too_late[:5]))} 句的开始时间超出音频长度，请检查",
                6000,
            )

    def _on_waveform_failed(self, message: str, token: int) -> None:
        if token != self._audio_token:
            return
        self._audio_loading = False
        self.timeline.set_loading(False)
        if self.player.duration > 0 and self.project.duration_ms <= 0:
            self.project.duration_ms = self.player.duration
        if self.project.duration_ms > 0:
            self.timeline.refresh()
            self.timeline.fit_all()
        self._update_time_label()
        self._update_status()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("波形分析失败")
        box.setText("无法生成波形，但播放与打轴仍可继续（如果该音频能被播放器打开）。")
        box.setDetailedText(message)
        box.exec()

    def _on_player_duration(self, duration: int) -> None:
        if self._duration_from_decode or duration <= 0:
            return
        if self.project.duration_ms <= 0:
            self.project.duration_ms = int(duration)
            self.timeline.refresh()
            self.timeline.fit_all()
            self._update_time_label()
            self._update_status()

    def open_project(self) -> None:
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开工程",
            str(self._last_dir),
            "歌词打轴工程 (*.lysp *.json);;所有文件 (*)",
        )
        if not path:
            return
        try:
            project = load_project(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "打开工程", f"无法读取工程文件：\n{exc}")
            return

        self._last_dir = Path(path).parent
        self.player.unload()
        self.player.stop()
        self._reset_loop()
        self._audio_token += 1
        self._audio_loading = False
        self._duration_from_decode = False
        self.project = project
        self._project_path = Path(path)
        self.history.clear()

        self.timeline.set_waveform(None)
        self.timeline.set_loading(False)
        self.timeline.set_project(self.project)
        self.timeline.set_playhead(0)
        self.panel.set_lines(self.project.lines, self.project.next_unmarked_index())
        self._apply_grid_to_ui()
        self._sync_views(None)
        self._dirty = False
        self._update_title()
        self._update_time_label()
        self._update_status()

        audio_path = Path(self.project.audio_path) if self.project.audio_path else None
        if audio_path is not None and audio_path.is_file():
            self._load_audio(str(audio_path), fallback_duration=self.project.duration_ms)
            self._dirty = False
            self._update_title()
        elif audio_path is not None:
            if self._ask_locate_audio(audio_path):
                new_path, _ = QFileDialog.getOpenFileName(
                    self,
                    "重新定位音频",
                    str(audio_path.parent),
                    "音频文件 (*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus);;所有文件 (*)",
                )
                if new_path:
                    self._last_dir = Path(new_path).parent
                    self._load_audio(new_path)
                    self._dirty = False
                    self._update_title()
                else:
                    self._audio_missing_state()
            else:
                self._audio_missing_state()
        else:
            self.timeline.fit_all()
            self.timeline.refresh()

        self._toast(f"已打开工程：{Path(path).name}")

    def _ask_locate_audio(self, path: Path) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("找不到音频")
        box.setText(f"找不到工程引用的音频文件：\n{path}\n\n是否重新定位？")
        locate = box.addButton("重新定位…", QMessageBox.ButtonRole.AcceptRole)
        skip = box.addButton("跳过", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is locate

    def _audio_missing_state(self) -> None:
        self.player.unload()
        self.timeline.set_waveform(None)
        self.timeline.refresh()
        self.timeline.fit_all()
        self._update_status()
        self._toast("音频文件缺失，只显示已保存的歌词时间", 5000)

    def save_project(self) -> bool:
        if self._project_path is None:
            return self.save_project_as()
        try:
            save_project(self._project_path, self.project)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存工程", f"保存失败：\n{exc}")
            return False
        self._dirty = False
        self._update_title()
        self._toast(f"已保存：{self._project_path.name}")
        return True

    def save_project_as(self) -> bool:
        default = self._default_export_path("lysp")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存工程",
            default,
            "歌词打轴工程 (*.lysp);;所有文件 (*)",
        )
        if not path:
            return False
        path = self._ensure_suffix(path, ".lysp")
        try:
            save_project(path, self.project)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存工程", f"保存失败：\n{exc}")
            return False
        self._project_path = Path(path)
        self._last_dir = self._project_path.parent
        self._dirty = False
        self._update_title()
        self._toast(f"已保存：{self._project_path.name}")
        return True

    # ------------------------------------------------------------------
    # 播放与定位
    # ------------------------------------------------------------------
    def toggle_play(self) -> None:
        if not self.project.audio_path or not Path(self.project.audio_path).is_file():
            self._toast("请先打开音频文件")
            return
        self.player.toggle()

    def seek(self, ms: int) -> None:
        if self.project.audio_path and Path(self.project.audio_path).is_file():
            self.player.seek(ms)
        self.timeline.set_playhead(ms)
        self._update_time_label()

    def _on_player_position(self, ms: int) -> None:
        if not self._playing and self.project.grid.snap_enabled:
            ms = self.project.grid.snap(ms)
        ensure = self._playing and self.follow_btn.isChecked()
        self.timeline.set_playhead(ms, ensure_visible=ensure)
        self._update_time_label()

    def _on_playing_changed(self, playing: bool) -> None:
        self._playing = bool(playing)
        self.play_btn.setText("暂停" if playing else "播放")
        self.play_btn.setIcon(_media_icon(self._playing))
        if not self._playing and self.project.grid.snap_enabled:
            snapped = self.project.grid.snap(self.timeline.playhead_ms)
            self.timeline.set_playhead(snapped)
            self._update_time_label()

    def _on_player_error(self, message: str) -> None:
        if message == self._last_player_error:
            return
        self._last_player_error = message
        self._toast(f"播放失败：{message}", 6000)

    def set_loop_a(self) -> None:
        self._loop_a = int(self.timeline.playhead_ms)
        if self._loop_b is not None and self._loop_b <= self._loop_a:
            self._loop_b = None
        self._apply_loop()
        self._toast(f"循环起点 A = {format_ms(self._loop_a)}")

    def set_loop_b(self) -> None:
        if self._loop_a is None:
            self._toast("请先设置循环起点 A")
            return
        value = int(self.timeline.playhead_ms)
        if value <= self._loop_a:
            self._toast("循环终点必须晚于起点 A")
            return
        self._loop_b = value
        self._apply_loop()
        self._toast(f"循环终点 B = {format_ms(self._loop_b)}")

    def _apply_loop(self) -> None:
        enabled = self.loop_btn.isChecked()
        has_points = self._loop_a is not None and self._loop_b is not None
        if enabled and not has_points:
            self.loop_btn.blockSignals(True)
            self.loop_btn.setChecked(False)
            self.loop_btn.blockSignals(False)
            enabled = False
        self.player.set_loop(self._loop_a if has_points and enabled else None,
                             self._loop_b if has_points and enabled else None)
        self.timeline.set_loop(self._loop_a, self._loop_b, bool(enabled and has_points))
        self.loop_a_btn.setToolTip(
            "把当前播放位置设为循环起点" if self._loop_a is None else f"A = {format_ms(self._loop_a)}"
        )
        self.loop_b_btn.setToolTip(
            "把当前播放位置设为循环终点" if self._loop_b is None else f"B = {format_ms(self._loop_b)}"
        )

    def _reset_loop(self) -> None:
        self._loop_a = None
        self._loop_b = None
        self.player.set_loop(None, None)
        self.timeline.set_loop(None, None, False)
        self.loop_btn.blockSignals(True)
        self.loop_btn.setChecked(False)
        self.loop_btn.blockSignals(False)
        self.loop_a_btn.setToolTip("把当前播放位置设为循环起点")
        self.loop_b_btn.setToolTip("把当前播放位置设为循环终点")

    def toggle_loop(self, checked: bool) -> None:
        if checked and (self._loop_a is None or self._loop_b is None):
            self._toast("请先用 A、B 按钮设置循环范围")
            self.loop_btn.blockSignals(True)
            self.loop_btn.setChecked(False)
            self.loop_btn.blockSignals(False)
            self._apply_loop()
            return
        self._apply_loop()

    # ------------------------------------------------------------------
    # 打轴与歌词编辑
    # ------------------------------------------------------------------
    def mark_at(self, ms: int) -> None:
        if not self.project.lines:
            self._toast("请先在左侧输入歌词")
            return
        if not self.project.audio_path or not Path(self.project.audio_path).is_file():
            self._toast("请先打开音频文件")
            return
        if self._audio_loading:
            self._toast("音频正在分析，请稍候")
            return
        if self.project.duration_ms <= 0:
            self._toast("音频长度未知，暂时不能打轴")
            return
        index = self.project.next_unmarked_index()
        if index is None:
            self._toast("所有歌词都已打轴")
            return
        duration = self.project.duration_ms
        max_start = max(0, duration - MIN_GAP_MS) if duration > 0 else max(0, ms)
        value = min(max(0, int(ms)), max_start)
        ok, reason = self.project.can_set_start(index, value)
        if not ok:
            self._toast(reason)
            return
        self.history.push(self.project.snapshot())
        self.project.lines[index].start_ms = value
        self._after_timing_change(f"第 {index + 1} 句 → {format_ms(value)}")

    def _on_drag_committed(self, index: int, start_ms: int) -> None:
        if index < 0 or index >= len(self.project.lines):
            return
        ok, reason = self.project.can_set_start(index, start_ms)
        if not ok:
            self._toast(reason)
            self.timeline.refresh()
            return
        self.history.push(self.project.snapshot())
        self.project.lines[index].start_ms = int(start_ms)
        self._after_timing_change(
            f"第 {index + 1} 句 → {format_ms(start_ms)}", selected=index
        )

    def _after_timing_change(self, message: str, selected: Optional[int] = None) -> None:
        self._sync_views(selected)
        self._mark_dirty()
        self._update_status()
        self._update_time_label()
        self._toast(message)
        self.timeline.set_playhead(self.timeline.playhead_ms)

    def _on_timeline_line_selected(self, index: int) -> None:
        self.timeline.set_selected(index)
        self.panel.set_selected(index)

    def _on_panel_selection(self, index: int) -> None:
        self.timeline.set_selected(index)

    def _on_text_edited(self, index: int, text: str) -> None:
        if index < 0 or index >= len(self.project.lines):
            return
        if self.project.lines[index].text == text:
            return
        self.history.push(self.project.snapshot())
        self.project.lines[index].text = text
        self.timeline.update()
        self._mark_dirty()
        self._toast(f"已修改第 {index + 1} 句歌词")

    def replace_lyrics(self, texts: list[str]) -> None:
        if not texts:
            self._toast("没有可用的歌词行")
            return
        self.history.push(self.project.snapshot())
        old = self.project.lines
        new_lines = [
            LyricLine(text=text, start_ms=old[i].start_ms if i < len(old) else None)
            for i, text in enumerate(texts)
        ]
        self.project.lines = new_lines
        self._sync_views(None)
        self._mark_dirty()
        self._update_status()
        if len(old) != len(new_lines):
            self._toast(
                f"歌词行数 {len(old)} → {len(new_lines)}，时间按行号保留，请检查",
                5000,
            )
        else:
            self._toast(f"已更新歌词，共 {len(new_lines)} 句")

    def clear_all_times(self) -> None:
        if self.project.marked_count == 0:
            self._toast("还没有已打轴的歌词")
            return
        if not self._confirm_clear("确定要清空所有歌词的时间吗？"):
            return
        self.history.push(self.project.snapshot())
        for line in self.project.lines:
            line.start_ms = None
        self._sync_views(None)
        self._mark_dirty()
        self._update_status()
        self._toast("已清空所有时间")

    def clear_from(self, index: int) -> None:
        if index < 0 or index >= len(self.project.lines):
            return
        if not any(line.start_ms is not None for line in self.project.lines[index:]):
            self._toast("这一句之后没有已打轴的内容")
            return
        if not self._confirm_clear(f"确定清除第 {index + 1} 句及之后的时间吗？"):
            return
        self.history.push(self.project.snapshot())
        self.project.clear_from(index)
        self._sync_views(None)
        self._mark_dirty()
        self._update_status()
        self._toast(f"已清除第 {index + 1} 句及之后的时间")

    def _confirm_clear(self, text: str) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("确认")
        box.setText(text)
        clear = box.addButton("清除", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is clear

    def undo(self) -> None:
        focus = QApplication.focusWidget()
        if isinstance(focus, QLineEdit):
            focus.undo()
            return
        snapshot = self.history.undo(self.project.snapshot())
        if snapshot is None:
            self._toast("没有可撤销的操作")
            return
        self.project.restore(snapshot)
        self._sync_views(None)
        self._mark_dirty()
        self._update_status()
        self._toast("已撤销")

    def redo(self) -> None:
        focus = QApplication.focusWidget()
        if isinstance(focus, QLineEdit):
            focus.redo()
            return
        snapshot = self.history.redo(self.project.snapshot())
        if snapshot is None:
            self._toast("没有可重做的操作")
            return
        self.project.restore(snapshot)
        self._sync_views(None)
        self._mark_dirty()
        self._update_status()
        self._toast("已重做")

    # ------------------------------------------------------------------
    # 网格
    # ------------------------------------------------------------------
    def _on_grid_changed(self, *args) -> None:
        if self._updating_ui:
            return
        snap_value = self.snap_combo.currentData()
        if snap_value in (None, 0):
            snap_enabled = False
            cells = self.project.grid.cells_per_beat
        else:
            snap_enabled = True
            cells = int(snap_value)
        self.project.grid = GridSettings(
            bpm=self.bpm_spin.value(),
            bpm_base=int(self.base_combo.currentData() or 4),
            beats_per_bar=int(self.num_combo.currentData() or 4),
            beat_unit=int(self.den_combo.currentData() or 4),
            cells_per_beat=max(1, int(cells)),
            offset_ms=float(self.offset_spin.value()),
            snap_enabled=snap_enabled,
        ).normalized()
        self._update_grid_label()
        self.timeline.refresh()
        if self.project.grid.snap_enabled and not self._playing:
            snapped = self.project.grid.snap(self.timeline.playhead_ms)
            if snapped != self.timeline.playhead_ms:
                self.seek(snapped)
        self._mark_dirty()

    def _apply_grid_to_ui(self) -> None:
        grid = self.project.grid
        self._updating_ui = True
        try:
            self.bpm_spin.setValue(float(grid.bpm))
            self._set_combo_data(self.num_combo, grid.beats_per_bar)
            self._set_combo_data(self.den_combo, grid.beat_unit)
            self._set_combo_data(self.base_combo, grid.bpm_base)
            if not grid.snap_enabled:
                self.snap_combo.setCurrentIndex(0)
            else:
                index = self.snap_combo.findData(grid.cells_per_beat)
                if index < 0:
                    self.snap_combo.addItem(
                        f"{grid.cells_per_beat} 格/拍", grid.cells_per_beat
                    )
                    index = self.snap_combo.count() - 1
                self.snap_combo.setCurrentIndex(index)
            self.offset_spin.setValue(int(round(grid.offset_ms)))
        finally:
            self._updating_ui = False
        self._update_grid_label()

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: int) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def set_offset_to_playhead(self) -> None:
        value = int(round(self.timeline.playhead_ms))
        value = max(self.offset_spin.minimum(), min(self.offset_spin.maximum(), value))
        if self.offset_spin.value() == value:
            self._on_grid_changed()
        else:
            self.offset_spin.setValue(value)
        self._toast(f"首拍已对齐到 {format_ms(value)}")

    # ------------------------------------------------------------------
    # 时间轴菜单与缩放
    # ------------------------------------------------------------------
    def _on_timeline_menu(self, index: int, position: QPoint) -> None:
        menu = QMenu(self)
        if index >= 0 and index < len(self.project.lines):
            line = self.project.lines[index]
            if line.start_ms is not None:
                play = menu.addAction("从此句开始播放")
                play.triggered.connect(lambda *_: self.seek(int(line.start_ms)))
            copy = menu.addAction("复制这句歌词")
            copy.triggered.connect(lambda *_: QApplication.clipboard().setText(line.text))
            clear = menu.addAction("清除此句及之后的时间")
            clear.triggered.connect(lambda *_: self.clear_from(index))
            menu.addSeparator()
        fit = menu.addAction("适配窗口")
        fit.triggered.connect(self.timeline_fit)
        zoom_in = menu.addAction("放大")
        zoom_in.triggered.connect(self.timeline_zoom_in)
        zoom_out = menu.addAction("缩小")
        zoom_out.triggered.connect(self.timeline_zoom_out)
        menu.exec(position)

    def timeline_zoom_in(self) -> None:
        self.timeline.zoom_in()

    def timeline_zoom_out(self) -> None:
        self.timeline.zoom_out()

    def timeline_fit(self) -> None:
        self.timeline.fit_all()

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def _default_export_path(self, ext: str) -> str:
        if self.project.audio_path:
            folder = Path(self.project.audio_path).parent
            stem = Path(self.project.audio_path).stem
        elif self._project_path is not None:
            folder = self._project_path.parent
            stem = self._project_path.stem
        else:
            folder = self._last_dir
            stem = "歌词"
        return str(folder / f"{stem}.{ext}")

    @staticmethod
    def _ensure_suffix(path: str, suffix: str) -> str:
        if path.lower().endswith(suffix.lower()):
            return path
        return path + suffix

    def export_lrc(self) -> None:
        if self.project.marked_count == 0:
            self._toast("还没有已打轴的歌词")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出 LRC",
            self._default_export_path("lrc"),
            "LRC 歌词 (*.lrc);;所有文件 (*)",
        )
        if not path:
            return
        path = self._ensure_suffix(path, ".lrc")
        try:
            text = build_lrc(self.project)
            write_text_file(path, text)
        except (ExportError, OSError) as exc:
            QMessageBox.critical(self, "导出 LRC", f"导出失败：\n{exc}")
            return
        self._last_dir = Path(path).parent
        exported = sum(
            1 for line in self.project.lines
            if line.start_ms is not None and line.text.strip()
        )
        skipped = len(self.project.lines) - exported
        suffix = f"，跳过 {skipped} 句未打轴/空行" if skipped else ""
        self._toast(f"已导出 {exported} 句 LRC{suffix}：{Path(path).name}", 5000)

    def export_srt(self) -> None:
        if self.project.marked_count == 0:
            self._toast("还没有已打轴的歌词")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出 SRT",
            self._default_export_path("srt"),
            "SRT 字幕 (*.srt);;所有文件 (*)",
        )
        if not path:
            return
        path = self._ensure_suffix(path, ".srt")
        try:
            text = build_srt(self.project)
            write_text_file(path, text)
        except (ExportError, OSError) as exc:
            QMessageBox.critical(self, "导出 SRT", f"导出失败：\n{exc}")
            return
        self._last_dir = Path(path).parent
        exported = sum(
            1 for line in self.project.lines
            if line.start_ms is not None and line.text.strip()
        )
        skipped = len(self.project.lines) - exported
        suffix = f"，跳过 {skipped} 句未打轴/空行" if skipped else ""
        self._toast(f"已导出 {exported} 句 SRT{suffix}：{Path(path).name}", 5000)

    # ------------------------------------------------------------------
    # 帮助与收尾
    # ------------------------------------------------------------------
    def show_shortcuts(self) -> None:
        text = (
            "空格          播放 / 暂停\n"
            "Ctrl+Z        撤销\n"
            "Ctrl+Y        重做\n"
            "Ctrl+O        打开音频\n"
            "Ctrl+S        保存工程\n"
            "Ctrl+E        编辑歌词\n"
            "点击空白歌词  打开歌词编辑框\n"
            "点击音频加号  导入音频（也可直接拖入音频轨）\n"
            "滚轮          以鼠标位置为中心缩放时间轴\n"
            "Shift+滚轮    左右平移时间轴\n"
            "中键拖动      平移时间轴\n"
            "拖动标尺      左右平移时间轴\n"
            "拖动播放头    抓住红色三角或在波形上拖动\n"
            "Alt+点击      落轴时临时关闭吸附\n"
            "拖动块间边界  调整下一句的开始时间（双箭头）\n"
            "点击最后一块  继续给下一句打轴\n"
            "双击字幕块    从这句开始播放\n"
            "双击时间列    从这句开始播放\n"
        )
        QMessageBox.information(self, "快捷键与操作", text)

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于 歌词打轴",
            "歌词打轴 · LyricsSubtitle\n\n"
            "把歌词按 BPM 网格对齐到音频，导出 LRC 与 SRT。\n"
            "使用 PySide6 构建。",
        )

    def load_demo(self) -> None:
        from ..demo import build_demo

        project, waveform = build_demo()
        self._audio_token += 1
        self._audio_loading = False
        self._duration_from_decode = True
        self.project = project
        self._project_path = None
        self.history.clear()
        self.player.unload()
        self.player.load(project.audio_path)
        self._reset_loop()
        self.timeline.set_waveform(waveform)
        self.timeline.set_loading(False)
        self.timeline.set_project(project)
        self.timeline.fit_all()
        self.timeline.set_playhead(0)
        self.panel.set_lines(project.lines, project.next_unmarked_index())
        self._apply_grid_to_ui()
        self._sync_views(None)
        self._dirty = False
        self._update_title()
        self._update_time_label()
        self._update_status()
        self._toast("已载入示例工程")

    def closeEvent(self, event) -> None:
        if not self._maybe_save():
            event.ignore()
            return
        app = QApplication.instance()
        if app is not None and hasattr(self, "_space_filter"):
            app.removeEventFilter(self._space_filter)
        self.player.stop()
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.wait(4000)
            if worker.isRunning():
                worker.terminate()
                worker.wait(1000)
        event.accept()
