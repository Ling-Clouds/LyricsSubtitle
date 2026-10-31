"""歌词时间与文本的撤销 / 重做栈。

快照只保存 (歌词文本, 开始毫秒) 列表，BPM 等网格设置不进入撤销栈。
"""
from __future__ import annotations

from typing import Optional

Snapshot = list[tuple[str, Optional[int]]]


class History:
    def __init__(self, limit: int = 200) -> None:
        self._undo: list[Snapshot] = []
        self._redo: list[Snapshot] = []
        self._limit = max(1, int(limit))

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def push(self, snapshot: Snapshot) -> None:
        """在修改之前调用，记录修改前的状态。"""
        snap = list(snapshot)
        if self._undo and self._undo[-1] == snap:
            return
        self._undo.append(snap)
        if len(self._undo) > self._limit:
            del self._undo[0]
        self._redo.clear()

    def undo(self, current: Snapshot) -> Optional[Snapshot]:
        if not self._undo:
            return None
        self._redo.append(list(current))
        return self._undo.pop()

    def redo(self, current: Snapshot) -> Optional[Snapshot]:
        if not self._redo:
            return None
        self._undo.append(list(current))
        return self._redo.pop()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)
