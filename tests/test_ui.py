from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from lyrics_subtitle.ui.main_window import MainWindow
from lyrics_subtitle.ui.theme import apply_theme


class MainWindowSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.resize(1400, 900)
        self.window.show()
        QTest.qWait(60)
        self.window.load_demo()
        QTest.qWait(60)
        for line in self.window.project.lines:
            line.start_ms = None
        self.window._sync_views(None)
        self.window._dirty = False

    def tearDown(self) -> None:
        self.window._dirty = False
        self.window.close()
        QTest.qWait(20)

    def _click_time(self, ms: int, modifiers=Qt.NoModifier) -> None:
        timeline = self.window.timeline
        _, _, track = timeline._lanes()
        x = int(round(timeline._time_to_x(ms)))
        y = int(track.center().y())
        QTest.mouseClick(timeline, Qt.LeftButton, modifiers, QPoint(x, y))
        QTest.qWait(10)

    def test_click_to_mark_and_reject_out_of_order(self) -> None:
        self._click_time(4000)
        self.assertEqual(self.window.project.lines[0].start_ms, 4000)

        self._click_time(8000)
        self.assertEqual(self.window.project.lines[1].start_ms, 8000)

        # 早于上一句，应被忽略，并保持当前目标不变
        self._click_time(3000)
        self.assertIsNone(self.window.project.lines[2].start_ms)
        self.assertEqual(self.window.project.next_unmarked_index(), 2)

    def test_alt_disables_snapping(self) -> None:
        self._click_time(4000)
        self._click_time(8000)
        self._click_time(12340, Qt.AltModifier)
        start = self.window.project.lines[2].start_ms
        self.assertIsNotNone(start)
        self.assertLess(abs(start - 12340), 60)
        self.assertNotEqual(start, self.window.project.grid.snap(12340))
        self._click_time(14000)
        self.assertEqual(self.window.project.lines[3].start_ms, 14000)

    def test_drag_commit_and_undo(self) -> None:
        self._click_time(4000)
        self._click_time(8000)
        self.window._on_drag_committed(0, 5000)
        self.assertEqual(self.window.project.lines[0].start_ms, 5000)
        self.window.undo()
        self.assertEqual(self.window.project.lines[0].start_ms, 4000)

    def test_ruler_click_seeks(self) -> None:
        timeline = self.window.timeline
        x = int(round(timeline._time_to_x(5000)))
        QTest.mouseClick(timeline, Qt.LeftButton, Qt.NoModifier, QPoint(x, 10))
        QTest.qWait(20)
        self.assertLess(abs(timeline.playhead_ms - 5000), 80)

    def test_bpm_change_updates_grid(self) -> None:
        self.window.bpm_spin.setValue(90.0)
        QTest.qWait(10)
        self.assertAlmostEqual(self.window.project.grid.bpm, 90.0)

    def test_text_edit_and_undo(self) -> None:
        original = self.window.project.lines[0].text
        item = self.window.panel.table.item(0, 3)
        item.setText("改过的第一句")
        QTest.qWait(10)
        self.assertEqual(self.window.project.lines[0].text, "改过的第一句")
        self.window.undo()
        self.assertEqual(self.window.project.lines[0].text, original)

    def test_replace_lyrics_keeps_times_by_index(self) -> None:
        self._click_time(4000)
        self._click_time(8000)
        self.window.replace_lyrics(["甲", "乙", "丙"])
        self.assertEqual([line.text for line in self.window.project.lines], ["甲", "乙", "丙"])
        self.assertEqual(self.window.project.lines[0].start_ms, 4000)
        self.assertEqual(self.window.project.lines[1].start_ms, 8000)
        self.assertIsNone(self.window.project.lines[2].start_ms)

    def test_loop_points(self) -> None:
        self.window.seek(1000)
        self.window.set_loop_a()
        self.window.seek(3000)
        self.window.set_loop_b()
        self.window.loop_btn.setChecked(True)
        QTest.qWait(10)
        self.assertEqual(self.window.player._loop_a, 1000)
        self.assertEqual(self.window.player._loop_b, 3000)

    def test_lyrics_dialog(self) -> None:
        from lyrics_subtitle.ui.panel import LyricsEditDialog

        dialog = LyricsEditDialog("第一句\n第二句")
        self.assertEqual(dialog.lyrics(), ["第一句", "第二句"])
        dialog.deleteLater()

    def test_menu_actions_trigger(self) -> None:
        self.window.act_zoom_in.trigger()
        self.window.act_zoom_out.trigger()
        self.window.act_fit.trigger()
        self.window.act_follow.trigger()
        self.assertFalse(self.window.act_follow.isChecked())
        self.window.act_follow.trigger()
        self.assertTrue(self.window.act_follow.isChecked())

    def test_async_audio_load(self) -> None:
        path = self.window.project.audio_path
        self.window._load_audio(path)
        for _ in range(100):
            QTest.qWait(30)
            if not self.window._audio_loading:
                break
        self.assertFalse(self.window._audio_loading)
        self.assertIsNotNone(self.window.timeline.waveform)
        self.assertAlmostEqual(self.window.project.duration_ms, 48000, delta=60)
        for _ in range(50):
            QTest.qWait(20)
            if self.window._worker is None:
                break
        self.assertIsNone(self.window._worker)

    def test_boundary_drag_moves_next_line(self) -> None:
        self._click_time(4000)
        self._click_time(8000)
        timeline = self.window.timeline
        _, _, track = timeline._lanes()
        y = int(track.center().y())
        boundary_x = int(round(timeline._time_to_x(8000)))
        self.assertEqual(timeline._boundary_at(QPoint(boundary_x, y)), 1)
        QTest.mouseMove(timeline, QPoint(boundary_x, y))
        QTest.qWait(10)
        self.assertEqual(timeline.cursor().shape(), Qt.SizeHorCursor)

        QTest.mousePress(timeline, Qt.LeftButton, Qt.NoModifier, QPoint(boundary_x, y))
        target_x = int(round(timeline._time_to_x(9000)))
        QTest.mouseMove(timeline, QPoint(target_x, y))
        QTest.mouseRelease(timeline, Qt.LeftButton, Qt.NoModifier, QPoint(target_x, y))
        QTest.qWait(10)

        self.assertEqual(self.window.project.lines[1].start_ms, 9000)
        self.assertEqual(self.window.project.lines[0].start_ms, 4000)
        self.assertEqual(self.window.project.end_ms(0), 9000)

    def test_ruler_drag_pans_timeline(self) -> None:
        timeline = self.window.timeline
        timeline.zoom_at(3.0, timeline.width() / 2)
        before = timeline.view_start_ms
        ruler, _, _ = timeline._lanes()
        y = int(ruler.center().y())
        x = int(timeline.width() * 0.7)
        QTest.mousePress(timeline, Qt.LeftButton, Qt.NoModifier, QPoint(x, y))
        QTest.mouseMove(timeline, QPoint(x - 120, y))
        QTest.mouseRelease(timeline, Qt.LeftButton, Qt.NoModifier, QPoint(x - 120, y))
        QTest.qWait(10)
        self.assertGreater(timeline.view_start_ms, before)

    def test_snap_none_and_grid_snap(self) -> None:
        timeline = self.window.timeline
        self.window.snap_combo.setCurrentIndex(0)
        QTest.qWait(10)
        self.assertFalse(self.window.project.grid.snap_enabled)

        x = int(round(timeline._time_to_x(4060)))
        QTest.mouseClick(timeline, Qt.LeftButton, Qt.NoModifier, QPoint(x, 10))
        QTest.qWait(10)
        self.assertNotEqual(timeline.playhead_ms % 125, 0)

        self.window.snap_combo.setCurrentIndex(4)
        QTest.qWait(10)
        self.assertTrue(self.window.project.grid.snap_enabled)
        x = int(round(timeline._time_to_x(4060)))
        QTest.mouseClick(timeline, Qt.LeftButton, Qt.NoModifier, QPoint(x, 10))
        QTest.qWait(10)
        self.assertEqual(timeline.playhead_ms % 125, 0)

        _, _, track = timeline._lanes()
        QTest.mouseMove(timeline, QPoint(x, int(track.center().y())))
        QTest.qWait(10)
        self.assertEqual(timeline._hover_time_ms % 125, 0)

    def test_project_suffix(self) -> None:
        self.assertTrue(self.window._default_export_path("lysp").endswith(".lysp"))
        self.assertEqual(MainWindow._ensure_suffix("demo", ".lysp"), "demo.lysp")
        self.assertEqual(MainWindow._ensure_suffix("demo.lysp", ".lysp"), "demo.lysp")

    def test_empty_lyrics_table_click(self) -> None:
        from lyrics_subtitle.ui.panel import LyricsTable

        table = LyricsTable(0, 4)
        table.resize(320, 240)
        table.show()
        QTest.qWait(20)
        hits: list[bool] = []
        table.empty_clicked.connect(lambda: hits.append(True))
        QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(40, 40))
        QTest.qWait(10)
        self.assertTrue(hits)
        table.deleteLater()

    def test_audio_plus_click(self) -> None:
        from lyrics_subtitle.ui.timeline import TimelineView

        view = TimelineView()
        view.resize(600, 320)
        view.show()
        QTest.qWait(20)
        hits: list[bool] = []
        view.audio_import_requested.connect(lambda: hits.append(True))
        _, wave, _ = view._lanes()
        QTest.mouseClick(
            view, Qt.LeftButton, Qt.NoModifier, QPoint(100, int(wave.center().y()))
        )
        QTest.qWait(10)
        self.assertTrue(hits)
        view.deleteLater()

    def test_audio_drop_on_waveform(self) -> None:
        from PySide6.QtCore import QMimeData, QPointF, QUrl
        from PySide6.QtGui import QDropEvent

        from lyrics_subtitle.ui.timeline import TimelineView

        view = TimelineView()
        view.resize(600, 320)
        view.show()
        QTest.qWait(20)
        path = self.window.project.audio_path
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path)])
        _, wave, _ = view._lanes()
        event = QDropEvent(
            QPointF(100, wave.center().y()),
            Qt.CopyAction,
            mime,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        hits: list[str] = []
        view.audio_dropped.connect(hits.append)
        view.dropEvent(event)
        self.assertEqual([Path(p) for p in hits], [Path(path)])
        view.deleteLater()


if __name__ == "__main__":
    unittest.main()
