"""离屏渲染主窗口截图，用于开发时检查布局。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lyrics_subtitle.ui.main_window import MainWindow  # noqa: E402
from lyrics_subtitle.ui.theme import apply_theme  # noqa: E402


def _grab(window: MainWindow, name: str) -> None:
    for _ in range(6):
        QApplication.processEvents()
    output = ROOT / name
    pixmap = window.grab()
    pixmap.save(str(output))
    print(f"saved {output} {pixmap.width()}x{pixmap.height()}")


def main() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    apply_theme(app)

    empty = MainWindow()
    empty.resize(1440, 900)
    empty.show()
    QTest.qWait(120)
    empty.statusBar().clearMessage()
    _grab(empty, "preview_empty.png")
    empty._dirty = False
    empty.close()

    window = MainWindow()
    window.load_demo()
    window.resize(1440, 900)
    window.show()
    QTest.qWait(200)
    window.statusBar().clearMessage()
    _grab(window, "preview.png")

    # 进行中的状态：只保留前两句，当前目标为第三句
    for line in window.project.lines[2:]:
        line.start_ms = None
    window._sync_views(None)
    window._update_status()
    window._update_time_label()
    QTest.qWait(50)
    _grab(window, "preview_working.png")

    window.timeline.zoom_at(3.0, window.timeline.width() / 2)
    QTest.qWait(50)
    _grab(window, "preview_zoom.png")
    window.timeline.fit_all()
    QTest.qWait(50)

    # 播放中的状态
    window.player.set_volume(0.0)
    window.toggle_play()
    QTest.qWait(1200)
    _grab(window, "preview_playing.png")
    window.player.pause()

    window.resize(1120, 720)
    QTest.qWait(100)
    _grab(window, "preview_small.png")

    window.resize(1000, 640)
    QTest.qWait(100)
    _grab(window, "preview_min.png")
    window._dirty = False
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
