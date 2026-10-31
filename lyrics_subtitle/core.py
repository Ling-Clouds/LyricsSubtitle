"""核心数据模型、节拍网格计算与时间格式化。

内部统一使用整数毫秒表示时间。网格可以按 BPM、拍号、BPM 基准音符、
每拍细分格数以及首拍偏移计算，所有吸附都在这里完成，界面只负责绘制。
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

# 相邻两句歌词之间至少保留的时间，避免导出 LRC 时出现完全相同的秒数。
MIN_GAP_MS = 10

NOTE_VALUES = (2, 4, 8, 16)
NOTE_LABELS = {
    2: "二分音符 (1/2)",
    4: "四分音符 (1/4)",
    8: "八分音符 (1/8)",
    16: "十六分音符 (1/16)",
}


# ---------------------------------------------------------------------------
# 节拍网格
# ---------------------------------------------------------------------------

@dataclass
class GridSettings:
    """BPM 网格参数。

    bpm       : BPM 数值，按 bpm_base 指定的音符计数
    bpm_base  : BPM 的基准音符（4 = 四分音符，8 = 八分音符，...）
    beats_per_bar : 拍号分子
    beat_unit : 拍号分母（一拍对应的音符）
    cells_per_beat : 每拍细分成几格（吸附精度）
    offset_ms : 第一小节第一拍所在的绝对时间
    """

    bpm: float = 120.0
    bpm_base: int = 4
    beats_per_bar: int = 4
    beat_unit: int = 4
    cells_per_beat: int = 4
    offset_ms: float = 0.0
    snap_enabled: bool = True

    def normalized(self) -> "GridSettings":
        """返回参数合法化后的副本，避免损坏的工程文件导致除零等问题。"""
        bpm = float(self.bpm)
        if not math.isfinite(bpm):
            bpm = 120.0
        bpm = min(400.0, max(20.0, bpm))

        base = int(self.bpm_base) if int(self.bpm_base) in NOTE_VALUES else 4
        num = min(16, max(1, int(self.beats_per_bar)))
        den = int(self.beat_unit) if int(self.beat_unit) in NOTE_VALUES else 4
        cells = min(32, max(1, int(self.cells_per_beat)))
        offset = float(self.offset_ms)
        if not math.isfinite(offset):
            offset = 0.0
        snap = bool(self.snap_enabled)
        return GridSettings(bpm, base, num, den, cells, offset, snap)

    # -- 时长 ---------------------------------------------------------------
    @property
    def base_note_ms(self) -> float:
        """BPM 基准音符的时长。"""
        return 60000.0 / self.bpm

    @property
    def beat_ms(self) -> float:
        """一拍（拍号分母音符）的时长。"""
        return self.base_note_ms * (self.bpm_base / self.beat_unit)

    @property
    def bar_ms(self) -> float:
        """一小节的时长。"""
        return self.beat_ms * self.beats_per_bar

    @property
    def step_ms(self) -> float:
        """一条吸附线的间距。"""
        return self.beat_ms / self.cells_per_beat

    # -- 吸附与网格线 -------------------------------------------------------
    def snap(self, t_ms: float) -> int:
        """把时间吸附到最近的网格线；关闭吸附时只做毫秒取整。"""
        if not self.snap_enabled:
            return int(math.floor(float(t_ms) + 0.5))
        step = self.step_ms
        if step <= 0:
            return int(round(t_ms))
        n = math.floor((t_ms - self.offset_ms) / step + 0.5)
        return int(math.floor(self.offset_ms + n * step + 0.5))

    def line_times(self, start_ms: float, end_ms: float, step_ms: float) -> Iterator[float]:
        """生成 [start_ms, end_ms] 范围内、间距为 step_ms 的网格线时间。"""
        if step_ms <= 0:
            return
        first = math.ceil((start_ms - self.offset_ms) / step_ms - 1e-9)
        last = math.floor((end_ms - self.offset_ms) / step_ms + 1e-9)
        for k in range(first, last + 1):
            yield self.offset_ms + k * step_ms

    def bar_number(self, t_ms: float) -> int:
        """时间所在小节的编号，首小节为 1。"""
        if self.bar_ms <= 0:
            return 1
        return int(math.floor((t_ms - self.offset_ms) / self.bar_ms + 1e-9)) + 1

    def describe(self) -> str:
        text = (
            f"每拍 {self.beat_ms:.1f} ms · 每小节 {self.bar_ms:.1f} ms"
            f" · 每格 {self.step_ms:.1f} ms"
        )
        if not self.snap_enabled:
            text += " · 吸附关闭"
        return text

    # -- 序列化 -------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "bpm": float(self.bpm),
            "bpm_base": int(self.bpm_base),
            "beats_per_bar": int(self.beats_per_bar),
            "beat_unit": int(self.beat_unit),
            "cells_per_beat": int(self.cells_per_beat),
            "offset_ms": float(self.offset_ms),
            "snap_enabled": bool(self.snap_enabled),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "GridSettings":
        if not isinstance(data, dict):
            return cls()
        defaults = cls()
        return cls(
            bpm=_as_float(data.get("bpm"), defaults.bpm),
            bpm_base=_as_int(data.get("bpm_base"), defaults.bpm_base),
            beats_per_bar=_as_int(data.get("beats_per_bar"), defaults.beats_per_bar),
            beat_unit=_as_int(data.get("beat_unit"), defaults.beat_unit),
            cells_per_beat=_as_int(data.get("cells_per_beat"), defaults.cells_per_beat),
            offset_ms=_as_float(data.get("offset_ms"), defaults.offset_ms),
            snap_enabled=bool(data.get("snap_enabled", True)),
        ).normalized()


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


# ---------------------------------------------------------------------------
# 歌词与工程
# ---------------------------------------------------------------------------

@dataclass
class LyricLine:
    text: str = ""
    start_ms: Optional[int] = None


@dataclass
class Project:
    audio_path: str = ""
    grid: GridSettings = field(default_factory=GridSettings)
    lines: list[LyricLine] = field(default_factory=list)
    duration_ms: int = 0

    # -- 查询 ---------------------------------------------------------------
    def marked_items(self) -> list[tuple[int, LyricLine]]:
        return [(i, line) for i, line in enumerate(self.lines) if line.start_ms is not None]

    @property
    def marked_count(self) -> int:
        return sum(1 for line in self.lines if line.start_ms is not None)

    def next_unmarked_index(self) -> Optional[int]:
        """下一句待打轴的歌词下标；全部完成时返回 None。"""
        for i, line in enumerate(self.lines):
            if line.start_ms is None:
                return i
        return None

    def previous_marked_start(self, index: int) -> Optional[int]:
        for i in range(index - 1, -1, -1):
            start = self.lines[i].start_ms
            if start is not None:
                return start
        return None

    def next_marked_start(self, index: int) -> Optional[int]:
        for i in range(index + 1, len(self.lines)):
            start = self.lines[i].start_ms
            if start is not None:
                return start
        return None

    def can_set_start(self, index: int, start_ms: int) -> tuple[bool, str]:
        """检查给第 index 句设置开始时间是否合法。"""
        if not self.lines:
            return False, "还没有歌词，请先粘贴歌词"
        if index < 0 or index >= len(self.lines):
            return False, "歌词序号无效"
        start = int(start_ms)
        if start < 0:
            return False, "开始时间不能为负数"
        if self.duration_ms > 0 and start > self.duration_ms:
            return False, "开始时间超出音频长度"

        prev = self.previous_marked_start(index)
        if prev is not None and start < prev + MIN_GAP_MS:
            return False, "必须晚于上一句的开始时间"
        nxt = self.next_marked_start(index)
        if nxt is not None and start > nxt - MIN_GAP_MS:
            return False, "必须早于下一句的开始时间"
        return True, ""

    def end_ms(self, index: int) -> int:
        """第 index 句的结束时间：下一句开始，最后一句到音频末尾。"""
        if index < 0 or index >= len(self.lines):
            return 0
        start = self.lines[index].start_ms
        if start is None:
            return 0
        nxt = self.next_marked_start(index)
        if nxt is not None and nxt > start:
            return nxt
        if self.duration_ms > start:
            return self.duration_ms
        return start + 1000

    # -- 修改 ---------------------------------------------------------------
    def clear_from(self, index: int) -> None:
        for line in self.lines[index:]:
            line.start_ms = None

    def snapshot(self) -> list[tuple[str, Optional[int]]]:
        return [(line.text, line.start_ms) for line in self.lines]

    def restore(self, snap: list[tuple[str, Optional[int]]]) -> None:
        self.lines = [LyricLine(text=str(text), start_ms=start) for text, start in snap]

    # -- 序列化 -------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "app": "LyricsSubtitle",
            "version": 1,
            "audio_path": self.audio_path,
            "duration_ms": int(self.duration_ms),
            "grid": self.grid.to_dict(),
            "lines": [
                {"text": line.text, "start_ms": line.start_ms}
                for line in self.lines
            ],
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "Project":
        if not isinstance(data, dict):
            return cls()
        project = cls()
        project.audio_path = str(data.get("audio_path") or "")
        project.duration_ms = max(0, _as_int(data.get("duration_ms"), 0))
        project.grid = GridSettings.from_dict(data.get("grid"))

        raw_lines = data.get("lines")
        if isinstance(raw_lines, list):
            for item in raw_lines:
                if isinstance(item, dict):
                    text = str(item.get("text") or "")
                    start = item.get("start_ms")
                elif isinstance(item, (list, tuple)) and item:
                    text = str(item[0] or "")
                    start = item[1] if len(item) > 1 else None
                else:
                    continue
                if start is None:
                    line = LyricLine(text=text, start_ms=None)
                else:
                    line = LyricLine(text=text, start_ms=max(0, _as_int(start, 0)))
                project.lines.append(line)
        return project


def load_project(path: str | Path) -> Project:
    text = Path(path).read_text(encoding="utf-8-sig")
    return Project.from_dict(json.loads(text))


def save_project(path: str | Path, project: Project) -> None:
    text = json.dumps(project.to_dict(), ensure_ascii=False, indent=2)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")


# ---------------------------------------------------------------------------
# 时间与文本工具
# ---------------------------------------------------------------------------

def format_ms(ms: float, show_millis: bool = True) -> str:
    """格式化为 m:ss.mmm 或 h:mm:ss.mmm。"""
    value = float(ms)
    total = int(math.floor(value + 0.5)) if value >= 0 else -int(math.floor(-value + 0.5))
    sign = "-" if total < 0 else ""
    total = abs(total)
    hours, rem = divmod(total, 3600000)
    minutes, rem = divmod(rem, 60000)
    seconds, millis = divmod(rem, 1000)
    if hours:
        out = f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        out = f"{minutes}:{seconds:02d}"
    if show_millis:
        out += f".{millis:03d}"
    return sign + out


def split_lyrics(text: str) -> list[str]:
    """按换行拆分歌词，忽略空行与首尾空白。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return [line.strip() for line in text.split("\n") if line.strip()]


_LRC_RE = re.compile(
    r"^\s*\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]\s*(.*)$"
)


def parse_lrc(text: str) -> list[tuple[str, int]]:
    """解析标准 LRC 的 [mm:ss.xx] 行，返回 (歌词, 毫秒) 列表。"""
    entries: list[tuple[str, int]] = []
    for raw in text.splitlines():
        match = _LRC_RE.match(raw)
        if not match:
            continue
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        frac = match.group(3) or ""
        if len(frac) == 0:
            frac_ms = 0
        elif len(frac) == 1:
            frac_ms = int(frac) * 100
        elif len(frac) == 2:
            frac_ms = int(frac) * 10
        else:
            frac_ms = int(frac[:3])
        total = (minutes * 60 + seconds) * 1000 + frac_ms
        entries.append((match.group(4).strip(), total))
    return entries
