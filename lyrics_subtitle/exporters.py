"""LRC 与 SRT 导出。"""
from __future__ import annotations

import math
from pathlib import Path

from .core import Project


class ExportError(Exception):
    pass


def _collect(project: Project) -> list[tuple[int, str]]:
    """收集可导出的 (开始毫秒, 单行文本)，跳过未打轴和空文本。"""
    rows: list[tuple[int, str]] = []
    for line in project.lines:
        if line.start_ms is None:
            continue
        text = " ".join(line.text.split())
        if not text:
            continue
        rows.append((max(0, int(round(line.start_ms))), text))
    if not rows:
        raise ExportError("没有可导出的歌词：请先打轴，并确认歌词内容不为空。")
    return rows


def lrc_timestamp(ms: float) -> str:
    """[mm:ss.xx]，按 10ms 四舍五入。"""
    centis = int(math.floor(max(0.0, float(ms)) / 10.0 + 0.5))
    minutes, centis = divmod(centis, 6000)
    seconds, centis = divmod(centis, 100)
    return f"[{minutes:02d}:{seconds:02d}.{centis:02d}]"


def srt_timestamp(ms: float) -> str:
    """00:00:00,000"""
    total = max(0, int(math.floor(float(ms) + 0.5)))
    hours, rem = divmod(total, 3600000)
    minutes, rem = divmod(rem, 60000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def build_lrc(project: Project) -> str:
    rows = _collect(project)
    body = "\n".join(f"{lrc_timestamp(start)}{text}" for start, text in rows)
    return body + "\n"


def build_srt(project: Project) -> str:
    rows = _collect(project)
    duration = max(0, int(project.duration_ms))
    blocks: list[str] = []
    for i, (start, text) in enumerate(rows):
        if i + 1 < len(rows):
            end = rows[i + 1][0]
        else:
            end = duration
        if end <= start:
            end = start + 1
        blocks.append(
            f"{i + 1}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{text}\n"
        )
    return "\n".join(blocks)


def write_text_file(path: str | Path, text: str) -> None:
    """UTF-8（无 BOM）、LF 换行写出。"""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
