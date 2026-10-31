"""基于 QtMultimedia 的音频播放器，带平滑播放头和 A-B 循环。"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class AudioPlayer(QObject):
    position_changed = Signal(int)
    duration_changed = Signal(int)
    playing_changed = Signal(bool)
    error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)
        self._output.setVolume(0.9)

        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.errorOccurred.connect(self._on_error)

        self._rate = 1.0
        self._duration = 0
        self._playing = False
        self._loop_a: Optional[int] = None
        self._loop_b: Optional[int] = None

        self._base_pos = 0
        self._base_time = time.monotonic()
        self._last_raw = -1

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------
    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def duration(self) -> int:
        return self._duration

    # ------------------------------------------------------------------
    # 控制
    # ------------------------------------------------------------------
    def load(self, path: str) -> None:
        self._player.stop()
        self._base_pos = 0
        self._base_time = time.monotonic()
        self._last_raw = -1
        self._duration = 0
        self._player.setSource(QUrl.fromLocalFile(path))

    def unload(self) -> None:
        self._player.stop()
        self._player.setSource(QUrl())
        self._duration = 0
        self._playing = False
        self._base_pos = 0
        self._last_raw = -1

    def play(self) -> None:
        if self._player.source().isEmpty():
            self.error.emit("还没有打开音频文件。")
            return
        if self._duration > 0 and self._player.position() >= self._duration - 80:
            self.seek(0)
        self._base_pos = max(0, self._player.position())
        self._base_time = time.monotonic()
        self._last_raw = -1
        self._player.play()

    def pause(self) -> None:
        self._player.pause()
        self.position_changed.emit(max(0, self._player.position()))

    def toggle(self) -> None:
        if self._playing:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self._player.stop()

    def seek(self, ms: int) -> None:
        target = max(0, int(ms))
        if self._duration > 0:
            target = min(target, self._duration)
        self._player.setPosition(target)
        self._base_pos = target
        self._base_time = time.monotonic()
        self._last_raw = -1
        self.position_changed.emit(target)

    def set_rate(self, rate: float) -> None:
        rate = min(2.0, max(0.25, float(rate)))
        self._player.setPlaybackRate(rate)
        self._rate = rate
        self._base_pos = max(0, self._player.position())
        self._base_time = time.monotonic()
        self._last_raw = -1

    def set_volume(self, volume: float) -> None:
        self._output.setVolume(min(1.0, max(0.0, float(volume))))

    def set_loop(self, a: Optional[int], b: Optional[int]) -> None:
        self._loop_a = a
        self._loop_b = b

    # ------------------------------------------------------------------
    # 信号处理
    # ------------------------------------------------------------------
    def _on_position(self, position: int) -> None:
        # positionChanged 的精度因后端而异，播放头主要由 _tick 外推。
        if not self._playing:
            self.position_changed.emit(max(0, position))

    def _on_duration(self, duration: int) -> None:
        if duration > 0 and duration != self._duration:
            self._duration = duration
            self.duration_changed.emit(duration)

    def _on_state(self, state) -> None:
        playing = state == QMediaPlayer.PlayingState
        if playing == self._playing:
            return
        self._playing = playing
        if playing:
            self._base_pos = max(0, self._player.position())
            self._base_time = time.monotonic()
            self._last_raw = -1
        else:
            self.position_changed.emit(max(0, self._player.position()))
        self.playing_changed.emit(playing)

    def _on_error(self, error, message: str) -> None:
        text = message.strip() if message else "音频播放失败。"
        self.error.emit(text)

    def _tick(self) -> None:
        if not self._playing:
            return
        raw = self._player.position()
        now = time.monotonic()
        if raw != self._last_raw:
            self._last_raw = raw
            self._base_pos = raw
            self._base_time = now

        display = self._base_pos + (now - self._base_time) * 1000.0 * self._rate
        if self._loop_a is not None and self._loop_b is not None and self._loop_b > self._loop_a:
            if display >= self._loop_b:
                self.seek(self._loop_a)
                return
        if self._duration > 0 and display > self._duration:
            display = self._duration
        self.position_changed.emit(max(0, int(display)))
