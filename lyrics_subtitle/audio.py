"""音频解码与波形峰值。

播放由 QtMultimedia 直接读取原始文件；这里只负责用 ffmpeg 把音频解码成
8kHz 单声道 PCM，再压缩成固定时间 Bucket 的 min/max 包络，供时间轴绘制。
这样无论 mp3 / flac / m4a 都能统一处理，也不依赖 Qt 的波形接口。
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


class AudioDecodeError(Exception):
    pass


@dataclass
class WaveformData:
    duration_ms: int
    sample_rate: int
    bucket_ms: float
    mins: np.ndarray
    maxs: np.ndarray

    @property
    def bucket_count(self) -> int:
        return int(self.mins.shape[0])


def find_ffmpeg() -> Optional[str]:
    """按优先级查找 ffmpeg：环境变量 → 程序自带 → PATH → imageio-ffmpeg。"""
    env = os.environ.get("LYRICSUB_FFMPEG")
    if env and Path(env).is_file():
        return str(Path(env))

    suffix = ".exe" if os.name == "nt" else ""
    bundled = [
        Path(__file__).resolve().parents[1] / "bin" / f"ffmpeg{suffix}",
        Path(sys.executable).resolve().parent / "bin" / f"ffmpeg{suffix}",
        Path(sys.executable).resolve().parent / f"ffmpeg{suffix}",
    ]
    for candidate in bundled:
        if candidate.is_file():
            return str(candidate)

    found = shutil.which("ffmpeg")
    if found:
        return found

    try:  # 可选依赖，安装了就有随包 ffmpeg
        import imageio_ffmpeg  # type: ignore

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception:
        pass
    return None


def decode_waveform(
    path: str | Path,
    bucket_ms: float = 2.0,
    sample_rate: int = 8000,
) -> WaveformData:
    """解码音频并返回波形包络。失败时抛出 AudioDecodeError。"""
    source = Path(path)
    if not source.is_file():
        raise AudioDecodeError(f"找不到音频文件：\n{source}")

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise AudioDecodeError(
            "未找到 ffmpeg。\n"
            "请安装 ffmpeg 并加入 PATH，或执行：pip install imageio-ffmpeg"
        )

    with tempfile.TemporaryDirectory(prefix="lyricsub_") as tmp:
        wav_path = Path(tmp) / "wave.wav"
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-acodec",
            "pcm_s16le",
            "-f",
            "wav",
            str(wav_path),
        ]
        run_kwargs: dict = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.PIPE,
            "timeout": 600,
        }
        if os.name == "nt":
            run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            proc = subprocess.run(cmd, **run_kwargs)
        except FileNotFoundError as exc:
            raise AudioDecodeError(f"无法启动 ffmpeg：{exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AudioDecodeError("音频解码超时，文件可能过大或已损坏。") from exc

        if proc.returncode != 0 or not wav_path.is_file():
            detail = (proc.stderr or b"").decode("utf-8", "replace").strip()
            detail = detail[-800:] if detail else "未知错误"
            raise AudioDecodeError(f"音频解码失败：\n{detail}")

        try:
            with wave.open(str(wav_path), "rb") as reader:
                rate = reader.getframerate()
                width = reader.getsampwidth()
                channels = reader.getnchannels()
                frames = reader.readframes(reader.getnframes())
        except Exception as exc:  # wave.Error, EOFError 等
            raise AudioDecodeError(f"无法读取解码后的音频：{exc}") from exc

    if width != 2:
        raise AudioDecodeError("音频解码结果不是 16 位 PCM，无法生成波形。")
    if channels != 1:
        raise AudioDecodeError("音频解码结果不是单声道，无法生成波形。")

    samples = np.frombuffer(frames, dtype="<i2")
    if samples.size == 0:
        raise AudioDecodeError("音频中没有可用的声音数据。")

    bucket_samples = max(1, int(round(rate * bucket_ms / 1000.0)))
    bucket_count = int(math.ceil(samples.size / bucket_samples))
    padded = np.zeros(bucket_count * bucket_samples, dtype=np.int16)
    padded[: samples.size] = samples
    blocks = padded.reshape(bucket_count, bucket_samples)
    mins = blocks.min(axis=1).astype(np.int16)
    maxs = blocks.max(axis=1).astype(np.int16)

    duration_ms = int(round(samples.size / rate * 1000.0))
    actual_bucket_ms = bucket_samples / rate * 1000.0
    return WaveformData(
        duration_ms=duration_ms,
        sample_rate=rate,
        bucket_ms=actual_bucket_ms,
        mins=mins,
        maxs=maxs,
    )
