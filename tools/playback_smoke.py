"""播放链路的最小化检查（离屏）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from lyrics_subtitle.ui.main_window import MainWindow
from lyrics_subtitle.ui.theme import apply_theme


def main() -> int:
    app = QApplication([])
    apply_theme(app)
    window = MainWindow()
    window.show()
    window.load_demo()
    QTest.qWait(150)
    window.toggle_play()
    QTest.qWait(1500)
    print("playing:", window.player.is_playing)
    print("raw position:", window.player._player.position())
    print("timeline playhead:", window.timeline.playhead_ms)
    print("state:", window.play_btn.text().encode("unicode_escape").decode("ascii"))
    window.player.pause()
    QTest.qWait(100)
    print("paused:", not window.player.is_playing)
    window._dirty = False
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
