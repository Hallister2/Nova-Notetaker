from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable

import numpy as np


AudioChunkCallback = Callable[[bytes, int, int], None]


@dataclass
class CaptureConfig:
    meeting_folder: Path
    mic_device_index: int | None
    loopback_device_index: int | None
    capture_mic: bool = True
    mic_sample_rate: int = 48000
    mic_channels: int = 1
    loopback_sample_rate: int = 48000
    loopback_channels: int = 2
    live_audio_callback: AudioChunkCallback | None = None


StatusCallback = Callable[[str], None]
LevelCallback = Callable[[str, float], None]


class CaptureService:
    """Coordinates microphone and WASAPI loopback capture.

    This service is intentionally separate from the UI. The first milestone is
    raw audio reliability, so this writes mic.wav and system.wav for inspection.
    """

    def __init__(self, config: CaptureConfig, on_status: StatusCallback, on_level: LevelCallback):
        self.config = config
        self.on_status = on_status
        self.on_level = on_level
        self.stop_event = Event()
        self.pause_event = Event()   # cleared = paused, set = running
        self.pause_event.set()
        self.callbacks_enabled = Event()
        self.callbacks_enabled.set()
        self.callback_lock = Lock()
        self.stream_lock = Lock()
        self.loopback_stream = None
        self.threads: list[Thread] = []

    def start(self) -> None:
        self.stop_event.clear()
        self.callbacks_enabled.set()
        self.config.meeting_folder.mkdir(parents=True, exist_ok=True)

        mic_path = self.config.meeting_folder / "mic.wav"
        system_path = self.config.meeting_folder / "system.wav"

        self.threads = []
        if self.config.capture_mic:
            self.threads.append(Thread(target=self._record_mic_sounddevice, args=(mic_path,), daemon=True, name="mic-capture"))
        else:
            self._emit_status("Microphone capture muted")
            self._emit_level("mic", 0.0)

        self.threads.append(Thread(target=self._record_loopback_pyaudiowpatch, args=(system_path,), daemon=True, name="system-capture"))

        for thread in self.threads:
            thread.start()

        self._emit_status("Capture started")

    def stop(self) -> None:
        self.request_stop()
        for thread in self.threads:
            thread.join(timeout=10)
            if thread.is_alive():
                self._emit_status(f"Capture thread did not stop cleanly: {thread.name}")
        self._emit_status("Capture stopped")
        self.callbacks_enabled.clear()

    def request_stop(self) -> None:
        self.stop_event.set()
        self.pause_event.set()  # Unblock any paused loops so threads can exit
        with self.stream_lock:
            stream = self.loopback_stream
        if stream is not None:
            try:
                if stream.is_active():
                    stream.stop_stream()
            except Exception:
                pass

    def pause(self) -> None:
        self.pause_event.clear()
        self._emit_status("Recording paused")
        self._emit_level("mic", 0.0)
        self._emit_level("system", 0.0)

    def resume(self) -> None:
        self.pause_event.set()
        self._emit_status("Recording resumed")

    def _emit_status(self, message: str) -> None:
        if not self.callbacks_enabled.is_set():
            return
        with self.callback_lock:
            if not self.callbacks_enabled.is_set():
                return
            try:
                self.on_status(message)
            except RuntimeError:
                self.callbacks_enabled.clear()

    def _emit_level(self, source: str, level: float) -> None:
        if not self.callbacks_enabled.is_set():
            return
        try:
            self.on_level(source, level)
        except RuntimeError:
            self.callbacks_enabled.clear()

    def _record_mic_sounddevice(self, path: Path) -> None:
        try:
            import sounddevice as sd
            import soundfile as sf

            self._emit_status("Microphone capture online")

            with sf.SoundFile(
                path,
                mode="w",
                samplerate=self.config.mic_sample_rate,
                channels=self.config.mic_channels,
                subtype="PCM_16",
            ) as audio_file:
                def callback(indata, frames, time_info, status):
                    if status:
                        self._emit_status(f"Mic status: {status}")
                    if self.pause_event.is_set():
                        audio_file.write(indata.copy())
                        level = float(np.sqrt(np.mean(np.square(indata)))) if indata.size else 0.0
                        self._emit_level("mic", min(level * 20, 1.0))

                with sd.InputStream(
                    samplerate=self.config.mic_sample_rate,
                    channels=self.config.mic_channels,
                    dtype="float32",
                    device=self.config.mic_device_index,
                    callback=callback,
                ):
                    while not self.stop_event.wait(0.1):
                        pass
        except Exception as error:
            self._emit_status(f"Microphone capture failed: {error}")

    def _record_loopback_pyaudiowpatch(self, path: Path) -> None:
        try:
            import pyaudiowpatch as pyaudio

            if self.config.loopback_device_index is None:
                self._emit_status("System loopback not selected")
                return

            pa = pyaudio.PyAudio()
            chunk = 1024
            sample_rate = self.config.loopback_sample_rate
            requested_channels = self.config.loopback_channels
            sample_format = pyaudio.paInt16

            try:
                stream, channels = self._open_loopback_stream(
                    pa,
                    sample_format=sample_format,
                    sample_rate=sample_rate,
                    requested_channels=requested_channels,
                    chunk=chunk,
                )
                with self.stream_lock:
                    self.loopback_stream = stream

                self._emit_status("System loopback capture online")

                with wave.open(str(path), "wb") as wav_file:
                    wav_file.setnchannels(channels)
                    wav_file.setsampwidth(pa.get_sample_size(sample_format))
                    wav_file.setframerate(sample_rate)

                    chunks_written = 0
                    while not self.stop_event.is_set():
                        # Block while paused, keeping the stream open so it doesn't timeout
                        if not self.pause_event.is_set():
                            self.pause_event.wait(timeout=0.1)
                            continue
                        try:
                            data = stream.read(chunk, exception_on_overflow=False)
                        except Exception:
                            if self.stop_event.is_set():
                                break
                            raise
                        if not data:
                            continue
                        wav_file.writeframes(data)
                        chunks_written += 1
                        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                        level = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
                        self._emit_level("system", min(level * 8, 1.0))
                        self._emit_live_audio(data, sample_rate, channels)

                self._emit_status(f"System loopback capture saved {chunks_written} audio chunk(s)")
                if stream.is_active():
                    stream.stop_stream()
                stream.close()
                with self.stream_lock:
                    self.loopback_stream = None
            finally:
                with self.stream_lock:
                    self.loopback_stream = None
                pa.terminate()
        except Exception as error:
            self._emit_status(f"System loopback capture failed: {error}")

    def _open_loopback_stream(self, pa, sample_format: int, sample_rate: int, requested_channels: int, chunk: int):
        errors: list[str] = []
        for channels in self._loopback_channel_candidates(requested_channels):
            try:
                stream = pa.open(
                    format=sample_format,
                    channels=channels,
                    rate=sample_rate,
                    input=True,
                    input_device_index=self.config.loopback_device_index,
                    frames_per_buffer=chunk,
                )
                if channels != requested_channels:
                    self._emit_status(
                        f"System loopback using {channels} channel(s); device rejected {requested_channels}."
                    )
                return stream, channels
            except Exception as error:
                errors.append(f"{channels} channel(s): {error}")
        raise RuntimeError("; ".join(errors) or "Could not open system loopback stream")

    @staticmethod
    def _loopback_channel_candidates(requested_channels: int) -> list[int]:
        candidates = [requested_channels, 2, 1]
        unique: list[int] = []
        for channels in candidates:
            if channels > 0 and channels not in unique:
                unique.append(channels)
        return unique

    def _emit_live_audio(self, data: bytes, sample_rate: int, channels: int) -> None:
        callback = self.config.live_audio_callback
        if callback is None or not self.callbacks_enabled.is_set():
            return
        try:
            callback(data, sample_rate, channels)
        except RuntimeError:
            self.callbacks_enabled.clear()
        except Exception as error:
            self._emit_status(f"Live transcript audio stream failed: {error}")
            self.config.live_audio_callback = None
