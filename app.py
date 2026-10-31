from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from lyrics_subtitle.ui.main_window import MainWindow
from lyrics_subtitle.ui.theme import apply_theme


def _log(message: str) -> None:
    path = os.environ.get("LYRICSUB_STARTUP_LOG")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(message + "\n")
    except OSError:
        pass


def _self_test(window: MainWindow) -> int:
    marker = Path(tempfile.gettempdir()) / "lyrics_subtitle_selftest.txt"
    try:
        from lyrics_subtitle.audio import find_ffmpeg
        from lyrics_subtitle.exporters import build_lrc, build_srt

        window.load_demo()
        build_lrc(window.project)
        build_srt(window.project)
        marker.write_text(
            "ok\n"
            f"ffmpeg={find_ffmpeg()}\n"
            f"duration_ms={window.project.duration_ms}\n"
            f"lines={len(window.project.lines)}\n",
            encoding="utf-8",
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - 用于打包后的自检
        marker.write_text(f"failed\n{type(exc).__name__}: {exc}\n", encoding="utf-8")
        return 4


def main() -> int:
    args = sys.argv[1:]
    _log("start")

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    _log("before QApplication")
    app = QApplication(sys.argv)
    app.setApplicationName("LyricsSubtitle")
    app.setApplicationDisplayName("歌词打轴")
    apply_theme(app)
    _log("after QApplication")

    window = MainWindow()
    _log("after MainWindow")
    if "--self-test" in args:
        code = _self_test(window)
        _log(f"self-test {code}")
        return code
    if "--demo" in args:
        window.load_demo()
        _log("after load_demo")
    window.show()
    _log("after show")
    if "--smoke-test" in args:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(1500, app.quit)
    _log("before exec")
    code = app.exec()
    _log(f"after exec {code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
