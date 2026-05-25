from __future__ import annotations

import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass
class AudioFileInfo:
    path: str
    exists: bool
    valid: bool = False
    size_bytes: int = 0
    duration_seconds: float = 0.0
    sample_rate: int | None = None
    channels: int | None = None
    sample_width_bytes: int | None = None
    frame_count: int | None = None
    rms_level: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def inspect_wav(path: Path) -> AudioFileInfo:
    info = AudioFileInfo(path=str(path), exists=path.exists())
    if not path.exists():
        info.error = "File does not exist"
        return info

    info.size_bytes = path.stat().st_size
    try:
        with wave.open(str(path), "rb") as wav_file:
            info.channels = wav_file.getnchannels()
            info.sample_rate = wav_file.getframerate()
            info.sample_width_bytes = wav_file.getsampwidth()
            info.frame_count = wav_file.getnframes()
            frames = wav_file.readframes(info.frame_count)
            if info.sample_rate:
                info.duration_seconds = round(info.frame_count / info.sample_rate, 3)
            info.rms_level = _calculate_rms(frames, info.sample_width_bytes)
            info.valid = info.frame_count > 0 and info.sample_rate > 0
    except Exception as error:
        info.error = str(error)

    return info


def _calculate_rms(frames: bytes, sample_width: int | None) -> float:
    if not frames or sample_width is None:
        return 0.0
    if sample_width == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif sample_width == 1:
        audio = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        return 0.0
    return round(float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0, 6)
