from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from threading import Event, Thread
import json
import tempfile
import time
import uuid
import wave

import numpy as np
import websocket


@dataclass
class TranscriptionResult:
    source: str
    text: str
    success: bool
    warning: str | None = None


class WhisperLiveClient:
    def __init__(self, settings: dict[str, Any]) -> None:
        transcription = settings.get("transcription", {})
        self.enabled = bool(transcription.get("enabled", False))
        self.url = str(transcription.get("whisperlive_url", "")).rstrip("/")
        self.model = str(transcription.get("model", "small"))
        if self.model == "whisper":
            self.model = "small"
        self.timeout_seconds = int(transcription.get("timeout_seconds", 120))
        self.language = str(transcription.get("language", "en"))
        self.use_vad = bool(transcription.get("use_vad", True))
        self.long_audio_chunk_seconds = int(transcription.get("long_audio_chunk_seconds", 180))

    def transcribe_file(self, audio_path: Path, source: str) -> TranscriptionResult:
        if not self.enabled:
            return TranscriptionResult(
                source=source,
                text="",
                success=False,
                warning="WhisperLive transcription is disabled in config/settings.json.",
            )
        if not self.url:
            return TranscriptionResult(
                source=source,
                text="",
                success=False,
                warning="WhisperLive URL is not configured.",
            )
        if not audio_path.exists():
            return TranscriptionResult(
                source=source,
                text="",
                success=False,
                warning=f"{source} audio file is missing.",
            )

        try:
            duration_seconds = self._wav_duration_seconds(audio_path)
            if duration_seconds > self.long_audio_chunk_seconds:
                text, chunk_warnings = self._transcribe_long_wav(audio_path, duration_seconds)
            else:
                text = self._transcribe_wav_with_retries(audio_path)
                chunk_warnings = []
            if not text:
                return TranscriptionResult(
                    source=source,
                    text="",
                    success=False,
                    warning=f"WhisperLive connected for {source}, but no speech text was returned.",
                )
            warning = "; ".join(chunk_warnings) if chunk_warnings else None
            return TranscriptionResult(source=source, text=text, success=True, warning=warning)
        except Exception as error:
            return TranscriptionResult(
                source=source,
                text="",
                success=False,
                warning=f"WhisperLive transcription failed for {source}: {error}",
            )

    def _transcribe_long_wav(self, audio_path: Path, duration_seconds: float) -> tuple[str, list[str]]:
        texts: list[str] = []
        warnings: list[str] = []
        with tempfile.TemporaryDirectory(prefix="nova_whisper_chunks_") as temp_dir:
            chunk_paths = self._split_wav(audio_path, Path(temp_dir), self.long_audio_chunk_seconds)
            for index, chunk_path in enumerate(chunk_paths, start=1):
                try:
                    text = self._transcribe_wav_with_retries(chunk_path)
                    if text.strip():
                        texts.append(text.strip())
                    else:
                        warnings.append(f"WhisperLive returned no text for chunk {index}/{len(chunk_paths)}.")
                except Exception as error:
                    warnings.append(f"WhisperLive failed for chunk {index}/{len(chunk_paths)}: {error}")
        if not texts and warnings:
            raise RuntimeError("; ".join(warnings))
        if duration_seconds:
            warnings.insert(0, f"Long recording transcribed in {len(chunk_paths)} chunk(s).")
        return " ".join(texts).strip(), warnings

    def _transcribe_wav_with_retries(self, audio_path: Path) -> str:
        attempts = 2
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self._transcribe_wav_over_websocket(audio_path)
            except Exception as error:
                last_error = error
                if attempt < attempts:
                    time.sleep(2)
        raise RuntimeError(str(last_error) if last_error else "Unknown WhisperLive error")

    @staticmethod
    def _wav_duration_seconds(audio_path: Path) -> float:
        with wave.open(str(audio_path), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            return frame_count / float(frame_rate) if frame_rate else 0.0

    @staticmethod
    def _split_wav(audio_path: Path, output_dir: Path, chunk_seconds: int) -> list[Path]:
        paths: list[Path] = []
        with wave.open(str(audio_path), "rb") as source:
            channels = source.getnchannels()
            sample_width = source.getsampwidth()
            frame_rate = source.getframerate()
            frames_per_chunk = max(1, int(frame_rate * chunk_seconds))
            index = 1
            while True:
                data = source.readframes(frames_per_chunk)
                if not data:
                    break
                chunk_path = output_dir / f"chunk_{index:03}.wav"
                with wave.open(str(chunk_path), "wb") as chunk:
                    chunk.setnchannels(channels)
                    chunk.setsampwidth(sample_width)
                    chunk.setframerate(frame_rate)
                    chunk.writeframes(data)
                paths.append(chunk_path)
                index += 1
        return paths

    def _transcribe_wav_over_websocket(self, audio_path: Path) -> str:
        parsed = urlparse(self.url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        host = parsed.hostname or self.url.replace("http://", "").replace("https://", "")
        port = parsed.port or (443 if scheme == "wss" else 80)
        ws_url = f"{scheme}://{host}:{port}"

        client_uid = str(uuid.uuid4())
        ready = Event()
        done = Event()
        warnings: list[str] = []
        segments_by_key: dict[tuple[str, str, str], str] = {}

        ws = websocket.create_connection(ws_url, timeout=self.timeout_seconds)
        try:
            ws.send(json.dumps({
                "uid": client_uid,
                "language": self.language,
                "task": "transcribe",
                "model": self.model,
                "use_vad": self.use_vad,
                "send_last_n_segments": 10,
                "no_speech_thresh": 0.45,
                "clip_audio": False,
                "same_output_threshold": 10,
                "enable_translation": False,
                "target_language": "en",
                "hotwords": None,
                "enable_diarization": False,
                "max_speakers": 10,
                "word_timestamps": False,
            }))

            receiver = Thread(
                target=self._receive_messages,
                args=(ws, client_uid, ready, done, segments_by_key, warnings),
                daemon=True,
            )
            receiver.start()

            if not ready.wait(timeout=30):
                raise RuntimeError("WhisperLive server did not become ready.")

            for audio_chunk, duration_seconds in self._iter_wav_float32_chunks(audio_path):
                ws.send_binary(audio_chunk.tobytes())
                time.sleep(duration_seconds)

            ws.send("END_OF_AUDIO")
            done.wait(timeout=15)
            receiver.join(timeout=2)
        finally:
            ws.close()

        if warnings:
            raise RuntimeError("; ".join(warnings))

        return " ".join(text.strip() for text in segments_by_key.values() if text.strip()).strip()

    @staticmethod
    def _receive_messages(
        ws: websocket.WebSocket,
        client_uid: str,
        ready: Event,
        done: Event,
        segments_by_key: dict[tuple[str, str, str], str],
        warnings: list[str],
    ) -> None:
        while not done.is_set():
            try:
                raw = ws.recv()
            except Exception:
                done.set()
                return

            if not raw:
                continue

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if message.get("uid") not in (None, client_uid):
                continue

            if message.get("message") == "SERVER_READY":
                ready.set()
                continue
            if message.get("message") == "DISCONNECT":
                done.set()
                continue
            if message.get("status") == "ERROR":
                warnings.append(str(message.get("message", "WhisperLive server error")))
                done.set()
                continue
            if message.get("status") == "WARNING":
                warnings.append(str(message.get("message", "WhisperLive server warning")))
                continue

            for segment in message.get("segments", []):
                text = str(segment.get("text", "")).strip()
                if not text:
                    continue
                key = (
                    str(segment.get("start", "")),
                    str(segment.get("end", "")),
                    text,
                )
                segments_by_key[key] = text

    @staticmethod
    def _iter_wav_float32_chunks(audio_path: Path, target_rate: int = 16000, chunk_size: int = 4096):
        with wave.open(str(audio_path), "rb") as wav_file:
            source_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()

            while True:
                data = wav_file.readframes(chunk_size)
                if not data:
                    break

                audio = WhisperLiveClient._pcm_bytes_to_float32(data, sample_width)
                if channels > 1:
                    audio = audio.reshape(-1, channels).mean(axis=1)
                if source_rate != target_rate:
                    audio = WhisperLiveClient._resample_linear(audio, source_rate, target_rate)

                duration = len(audio) / float(target_rate) if target_rate else 0.0
                yield audio.astype(np.float32), duration

    @staticmethod
    def _pcm_bytes_to_float32(data: bytes, sample_width: int) -> np.ndarray:
        if sample_width == 2:
            return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        if sample_width == 4:
            return np.frombuffer(data, dtype=np.int32).astype(np.float32) / 2147483648.0
        if sample_width == 1:
            return (np.frombuffer(data, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        raise ValueError(f"Unsupported WAV sample width: {sample_width} bytes")

    @staticmethod
    def _resample_linear(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
        if audio.size == 0 or source_rate == target_rate:
            return audio
        source_positions = np.arange(audio.size)
        target_size = int(audio.size * target_rate / source_rate)
        target_positions = np.linspace(0, audio.size - 1, target_size)
        return np.interp(target_positions, source_positions, audio).astype(np.float32)
