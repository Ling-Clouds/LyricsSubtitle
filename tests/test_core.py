from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from lyrics_subtitle.audio import AudioDecodeError, decode_waveform, find_ffmpeg
from lyrics_subtitle.core import (
    GridSettings,
    LyricLine,
    Project,
    format_ms,
    load_project,
    parse_lrc,
    save_project,
    split_lyrics,
)
from lyrics_subtitle.exporters import (
    ExportError,
    build_lrc,
    build_srt,
    lrc_timestamp,
    srt_timestamp,
    write_text_file,
)
from lyrics_subtitle.history import History


class GridTests(unittest.TestCase):
    def test_common_time(self):
        grid = GridSettings(bpm=120, bpm_base=4, beats_per_bar=4, beat_unit=4, cells_per_beat=4)
        self.assertAlmostEqual(grid.beat_ms, 500.0)
        self.assertAlmostEqual(grid.bar_ms, 2000.0)
        self.assertAlmostEqual(grid.step_ms, 125.0)

    def test_six_eight_quarter_base(self):
        grid = GridSettings(bpm=120, bpm_base=4, beats_per_bar=6, beat_unit=8, cells_per_beat=2)
        self.assertAlmostEqual(grid.beat_ms, 250.0)
        self.assertAlmostEqual(grid.bar_ms, 1500.0)
        self.assertAlmostEqual(grid.step_ms, 125.0)

    def test_six_eight_eighth_base(self):
        grid = GridSettings(bpm=120, bpm_base=8, beats_per_bar=6, beat_unit=8, cells_per_beat=1)
        self.assertAlmostEqual(grid.beat_ms, 500.0)
        self.assertAlmostEqual(grid.bar_ms, 3000.0)

    def test_snap_and_offset(self):
        grid = GridSettings(bpm=120, cells_per_beat=4, offset_ms=0)
        self.assertEqual(grid.snap(0), 0)
        self.assertEqual(grid.snap(60), 0)
        self.assertEqual(grid.snap(63), 125)
        self.assertEqual(grid.snap(130), 125)

        offset_grid = GridSettings(bpm=120, cells_per_beat=4, offset_ms=250)
        self.assertEqual(offset_grid.snap(260), 250)
        self.assertEqual(offset_grid.snap(380), 375)

    def test_line_times(self):
        grid = GridSettings(bpm=120, cells_per_beat=4, offset_ms=0)
        times = list(grid.line_times(0, 500, grid.step_ms))
        self.assertEqual(times, [0.0, 125.0, 250.0, 375.0, 500.0])

    def test_normalized_clamps(self):
        grid = GridSettings(bpm=-5, bpm_base=7, beats_per_bar=0, beat_unit=3, cells_per_beat=0).normalized()
        self.assertGreaterEqual(grid.bpm, 20)
        self.assertEqual(grid.bpm_base, 4)
        self.assertEqual(grid.beats_per_bar, 1)
        self.assertEqual(grid.beat_unit, 4)
        self.assertEqual(grid.cells_per_beat, 1)

    def test_snap_disabled(self):
        grid = GridSettings(bpm=120, cells_per_beat=4, snap_enabled=False)
        self.assertEqual(grid.snap(63), 63)
        self.assertFalse(GridSettings.from_dict(grid.to_dict()).snap_enabled)
        self.assertIn("吸附关闭", grid.describe())


class ProjectTests(unittest.TestCase):
    def make_project(self):
        project = Project(duration_ms=10000)
        project.lines = [
            LyricLine("第一句", 1000),
            LyricLine("第二句", None),
            LyricLine("第三句", 5000),
        ]
        return project

    def test_next_unmarked_and_end(self):
        project = self.make_project()
        self.assertEqual(project.next_unmarked_index(), 1)
        self.assertEqual(project.marked_count, 2)
        self.assertEqual(project.end_ms(0), 5000)
        self.assertEqual(project.end_ms(2), 10000)

    def test_can_set_start(self):
        project = self.make_project()
        self.assertTrue(project.can_set_start(1, 2000)[0])
        self.assertTrue(project.can_set_start(1, 4990)[0])
        self.assertFalse(project.can_set_start(1, 5000)[0])
        self.assertFalse(project.can_set_start(1, 1005)[0])
        self.assertFalse(project.can_set_start(1, 20000)[0])

    def test_clear_and_snapshot(self):
        project = self.make_project()
        snap = project.snapshot()
        project.clear_from(1)
        self.assertEqual(project.marked_count, 1)
        project.restore(snap)
        self.assertEqual(project.marked_count, 2)
        self.assertEqual(project.lines[2].text, "第三句")

    def test_save_load_roundtrip(self):
        project = self.make_project()
        project.audio_path = "C:/music/demo.mp3"
        project.grid = GridSettings(90, 8, 6, 8, 3, -250)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.json"
            save_project(path, project)
            loaded = load_project(path)
        self.assertEqual(loaded.audio_path, project.audio_path)
        self.assertEqual(loaded.lines[0].text, "第一句")
        self.assertEqual(loaded.lines[0].start_ms, 1000)
        self.assertEqual(loaded.grid.to_dict(), project.grid.normalized().to_dict())


class FormatTests(unittest.TestCase):
    def test_format_ms(self):
        self.assertEqual(format_ms(0), "0:00.000")
        self.assertEqual(format_ms(1234), "0:01.234")
        self.assertEqual(format_ms(61234), "1:01.234")
        self.assertEqual(format_ms(3661234), "1:01:01.234")

    def test_split_and_parse(self):
        self.assertEqual(split_lyrics("a\r\n\r\n b \n"), ["a", "b"])
        parsed = parse_lrc("[00:01.20]第一句\n[01:02.345]第二句\n")
        self.assertEqual(parsed, [("第一句", 1200), ("第二句", 62345)])

    def test_lrc_srt_timestamps(self):
        self.assertEqual(lrc_timestamp(1000), "[00:01.00]")
        self.assertEqual(lrc_timestamp(61234), "[01:01.23]")
        self.assertEqual(srt_timestamp(61234), "00:01:01,234")


class ExportTests(unittest.TestCase):
    def make_project(self):
        project = Project(duration_ms=10000)
        project.lines = [
            LyricLine("第一句", 1000),
            LyricLine("第二句", 5000),
            LyricLine("没打轴", None),
        ]
        return project

    def test_lrc(self):
        text = build_lrc(self.make_project())
        self.assertEqual(text, "[00:01.00]第一句\n[00:05.00]第二句\n")

    def test_srt_contiguous(self):
        text = build_srt(self.make_project())
        expected = (
            "1\n00:00:01,000 --> 00:00:05,000\n第一句\n"
            "\n"
            "2\n00:00:05,000 --> 00:00:10,000\n第二句\n"
        )
        self.assertEqual(text, expected)

    def test_empty_export_raises(self):
        with self.assertRaises(ExportError):
            build_lrc(Project(duration_ms=1000))

    def test_write_utf8_without_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "歌词.srt"
            write_text_file(path, "中文\n")
            data = path.read_bytes()
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(data.decode("utf-8"), "中文\n")

    def test_empty_text_lines_are_skipped(self):
        project = Project(duration_ms=5000)
        project.lines = [
            LyricLine("", 1000),
            LyricLine("有内容", 2000),
        ]
        self.assertEqual(build_lrc(project), "[00:02.00]有内容\n")
        srt = build_srt(project)
        self.assertIn("00:00:02,000 --> 00:00:05,000", srt)


class HistoryTests(unittest.TestCase):
    def test_undo_redo(self):
        history = History()
        history.push([("a", 1)])
        history.push([("a", 2)])
        self.assertTrue(history.can_undo)
        state = history.undo([("a", 3)])
        self.assertEqual(state, [("a", 2)])
        state = history.undo(state)
        self.assertEqual(state, [("a", 1)])
        self.assertIsNone(history.undo(state))
        state = history.redo([("a", 1)])
        self.assertEqual(state, [("a", 2)])


@unittest.skipUnless(find_ffmpeg(), "ffmpeg 不可用，跳过音频解码测试")
class AudioTests(unittest.TestCase):
    def test_decode_generated_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tone.wav"
            rate = 8000
            seconds = 1.0
            t = np.arange(int(rate * seconds)) / rate
            samples = (0.5 * np.sin(2 * np.pi * 440 * t) * 32767).astype("<i2")
            with wave.open(str(path), "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(rate)
                writer.writeframes(samples.tobytes())

            waveform = decode_waveform(path)
            self.assertAlmostEqual(waveform.duration_ms, 1000, delta=2)
            self.assertEqual(waveform.sample_rate, 8000)
            self.assertGreater(waveform.bucket_count, 0)
            self.assertGreater(int(waveform.maxs.max()), 1000)

    def test_missing_file(self):
        with self.assertRaises(AudioDecodeError):
            decode_waveform("Z:/definitely/not/here.wav")


if __name__ == "__main__":
    unittest.main()
