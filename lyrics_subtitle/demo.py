"""生成一个可直接试用的示例工程（音频 + 歌词时间）。"""
from __future__ import annotations

import tempfile
import wave
from pathlib import Path

import numpy as np

from .audio import WaveformData, decode_waveform
from .core import GridSettings, LyricLine, Project

DEMO_LYRICS = [
    "夜色落在安静的窗台",
    "风把旧旋律轻轻吹来",
    "我在时间的缝隙里等待",
    "等一句没说完的对白",
    "街灯把影子拉得很长",
    "脚步跟着节拍慢慢晃",
    "如果回忆也可以重放",
    "就让这首歌替我说完",
]

DEMO_STARTS = [4000, 8000, 12000, 16000, 20000, 24000, 28000, 32000]


def _write_demo_audio(path: Path) -> None:
    sample_rate = 22050
    bpm = 120.0
    bars = 24
    beat = 60.0 / bpm
    bar = beat * 4
    duration = bars * bar
    total = int(sample_rate * duration)

    audio = np.zeros(total, dtype=np.float64)
    time = np.arange(total) / sample_rate
    audio += 0.018 * np.sin(2 * np.pi * 110.0 * time)

    chords = (
        (261.63, 329.63, 392.00),
        (220.00, 261.63, 329.63),
        (174.61, 220.00, 261.63),
        (196.00, 246.94, 293.66),
    )
    for bar_index in range(bars):
        start = int(bar_index * bar * sample_rate)
        end = min(total, int((bar_index + 1) * bar * sample_rate))
        if end <= start:
            continue
        local = np.arange(end - start) / sample_rate
        chord = chords[bar_index % 4]
        for freq in chord:
            audio[start:end] += 0.032 * np.sin(2 * np.pi * freq * local)
        for k in range(8):
            note_start = start + int(k * beat / 2 * sample_rate)
            note_end = min(total, note_start + int(0.18 * sample_rate))
            if note_end <= note_start:
                continue
            local_note = np.arange(note_end - note_start) / sample_rate
            audio[note_start:note_end] += (
                0.075
                * np.sin(2 * np.pi * chord[k % 3] * 2 * local_note)
                * np.exp(-local_note * 7)
            )

    for index in range(bars * 4):
        start = int(index * beat * sample_rate)
        length = min(total - start, int(0.14 * sample_rate))
        if length <= 0:
            continue
        local = np.arange(length) / sample_rate
        freq = 52.0 + 70.0 * np.exp(-local * 30)
        audio[start : start + length] += 0.55 * np.sin(2 * np.pi * freq * local) * np.exp(-local * 18)

    rng = np.random.default_rng(11)
    for index in range(bars * 8):
        start = int(index * beat / 2 * sample_rate)
        length = min(total - start, int(0.035 * sample_rate))
        if length <= 0:
            continue
        noise = rng.standard_normal(length)
        audio[start : start + length] += 0.05 * noise * np.exp(-np.arange(length) / (0.008 * sample_rate))

    peak = float(np.max(np.abs(audio)))
    if peak > 0:
        audio = audio / peak * 0.9
    pcm = (audio * 32767).astype("<i2")

    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(pcm.tobytes())


def build_demo() -> tuple[Project, WaveformData]:
    path = Path(tempfile.gettempdir()) / "lyrics_subtitle_demo.wav"
    _write_demo_audio(path)
    waveform = decode_waveform(path)

    project = Project(audio_path=str(path), duration_ms=waveform.duration_ms)
    project.grid = GridSettings(
        bpm=120.0,
        bpm_base=4,
        beats_per_bar=4,
        beat_unit=4,
        cells_per_beat=4,
        offset_ms=0.0,
    )
    project.lines = [
        LyricLine(text=text, start_ms=start)
        for text, start in zip(DEMO_LYRICS, DEMO_STARTS)
    ]
    return project, waveform
