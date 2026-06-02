from __future__ import annotations

import json
import queue
import uuid
from pathlib import Path

import websocket

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.audio.capture_service import CaptureConfig, CaptureService
from app.core.glossary import glossary_hotwords
from app.storage.meeting_store import MeetingMetadata, MeetingStore
from app.transcription.whisperlive_client import WhisperLiveClient
from app.workflows.meeting_processor import MeetingProcessor


class CaptureWorker(QObject):
    status = Signal(str)
    level = Signal(str, float)
    audio_chunk = Signal(bytes, int, int)
    stopped = Signal()

    def __init__(self, config: CaptureConfig) -> None:
        super().__init__()
        config.live_audio_callback = self.audio_chunk.emit
        self.service = CaptureService(config, self.status.emit, self.level.emit)

    @Slot()
    def start(self) -> None:
        self.service.start()

    @Slot()
    def stop(self) -> None:
        self.service.stop()
        self.stopped.emit()

    def request_stop(self) -> None:
        self.service.request_stop()

    def pause(self) -> None:
        self.service.pause()

    def resume(self) -> None:
        self.service.resume()

    @property
    def is_paused(self) -> bool:
        return not self.service.pause_event.is_set()


class LiveTranscriptionWorker(QObject):
    status = Signal(str)
    segment = Signal(str, str, bool)
    finished = Signal()

    def __init__(self, settings: dict) -> None:
        super().__init__()
        transcription = settings.get("transcription", {})
        self.enabled = bool(transcription.get("enabled", False))
        self.url = str(transcription.get("whisperlive_url", "")).rstrip("/")
        self.model = str(transcription.get("model", "small"))
        self.language = str(transcription.get("language", "en"))
        self.use_vad = bool(transcription.get("use_vad", True))
        self.timeout_seconds = int(transcription.get("timeout_seconds", 120))
        self.hotwords = str(transcription.get("hotwords", "") or glossary_hotwords()).strip()
        self.client_uid = str(uuid.uuid4())
        self.audio_queue: queue.Queue[tuple[bytes, int, int] | None] = queue.Queue(maxsize=80)
        self.stop_requested = False
        self.seen_segments: set[tuple[str, str, str]] = set()

    @Slot()
    def run(self) -> None:
        if not self.enabled:
            self.status.emit("Live transcript disabled; final transcript will be generated after recording.")
            self.finished.emit()
            return
        if not self.url:
            self.status.emit("Live transcript unavailable: WhisperLive URL is not configured.")
            self.finished.emit()
            return

        ws_url = self._websocket_url()
        ws: websocket.WebSocket | None = None
        try:
            ws = self._connect_websocket(ws_url)
        except Exception as error:
            if not self.stop_requested:
                self.status.emit(f"Live transcript unavailable: {error}")
            self.finished.emit()
            return

        try:
            while not self.stop_requested:
                if ws is None:
                    try:
                        ws = self._connect_websocket(ws_url, reconnect=True)
                    except Exception as error:
                        self.status.emit(f"Live transcript reconnect failed: {error}")
                        self._wait_before_reconnect()
                        continue

                if not self._receive_available_segments(ws):
                    ws = self._close_websocket(ws)
                    continue
                try:
                    queued = self.audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if queued is None:
                    break
                try:
                    self._send_audio_chunk(ws, queued)
                except websocket.WebSocketConnectionClosedException:
                    ws = self._close_websocket(ws)
                    self._requeue_audio_chunk(queued)
                except Exception as error:
                    self.status.emit(f"Live transcript reconnecting after send failed: {error}")
                    ws = self._close_websocket(ws)
                    self._requeue_audio_chunk(queued)
            if ws is not None:
                try:
                    ws.send("END_OF_AUDIO")
                except Exception:
                    pass
                for _ in range(20):
                    if not self._receive_available_segments(ws):
                        break
        except Exception as error:
            if not self.stop_requested:
                self.status.emit(f"Live transcript stopped: {error}")
        finally:
            self._close_websocket(ws)
            self.finished.emit()

    def _websocket_url(self) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(self.url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        host = parsed.hostname or self.url.replace("http://", "").replace("https://", "")
        port = parsed.port or (443 if scheme == "wss" else 80)
        return f"{scheme}://{host}:{port}"

    def _connect_websocket(self, ws_url: str, reconnect: bool = False) -> websocket.WebSocket:
        self.status.emit("Live transcript reconnecting" if reconnect else "Live transcript connecting")
        ws = websocket.create_connection(ws_url, timeout=self.timeout_seconds)
        ws.send(json.dumps({
            "uid": self.client_uid,
            "language": self.language,
            "task": "transcribe",
            "model": self.model,
            "use_vad": self.use_vad,
            "send_last_n_segments": 4,
            "no_speech_thresh": 0.45,
            "clip_audio": False,
            "same_output_threshold": 4,
            "enable_translation": False,
            "target_language": "en",
            "hotwords": self.hotwords or None,
            "enable_diarization": False,
            "max_speakers": 10,
            "word_timestamps": False,
        }))
        self._wait_for_server_ready(ws)
        ws.settimeout(0.01)
        self.status.emit("Live transcript listening")
        return ws

    def _wait_for_server_ready(self, ws: websocket.WebSocket) -> None:
        while not self.stop_requested:
            raw = ws.recv()
            message = json.loads(raw) if raw else {}
            if message.get("uid") not in (None, self.client_uid):
                continue
            if message.get("message") == "SERVER_READY":
                return
            if message.get("status") == "ERROR":
                raise RuntimeError(str(message.get("message", "WhisperLive server error")))
        raise RuntimeError("Live transcript stopped before WhisperLive became ready.")

    def _send_audio_chunk(self, ws: websocket.WebSocket, queued: tuple[bytes, int, int]) -> None:
        data, sample_rate, channels = queued
        audio = WhisperLiveClient._pcm_bytes_to_float32(data, 2)
        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)
        if sample_rate != 16000:
            audio = WhisperLiveClient._resample_linear(audio, sample_rate, 16000)
        ws.send_binary(audio.astype("float32").tobytes())

    def _requeue_audio_chunk(self, queued: tuple[bytes, int, int]) -> None:
        try:
            self.audio_queue.put_nowait(queued)
        except queue.Full:
            pass

    def _wait_before_reconnect(self) -> None:
        for _ in range(10):
            if self.stop_requested:
                return
            QThread.msleep(100)

    @staticmethod
    def _close_websocket(ws: websocket.WebSocket | None) -> None:
        if ws is None:
            return None
        try:
            ws.close()
        except Exception:
            pass
        return None

    @Slot(bytes, int, int)
    def enqueue_audio(self, data: bytes, sample_rate: int, channels: int) -> None:
        if self.stop_requested:
            return
        try:
            self.audio_queue.put_nowait((data, sample_rate, channels))
        except queue.Full:
            pass

    @Slot()
    def stop(self) -> None:
        self.stop_requested = True
        try:
            self.audio_queue.put_nowait(None)
        except queue.Full:
            pass

    def _receive_available_segments(self, ws: websocket.WebSocket) -> bool:
        while True:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                return True
            except websocket.WebSocketConnectionClosedException:
                if not self.stop_requested:
                    self.status.emit("Live transcript connection closed; reconnecting.")
                return False
            except Exception as error:
                if not self.stop_requested:
                    self.status.emit(f"Live transcript receive failed; reconnecting: {error}")
                return False
            if not raw:
                return True
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if message.get("uid") not in (None, self.client_uid):
                continue
            if message.get("message") == "DISCONNECT":
                if not self.stop_requested:
                    self.status.emit("Live transcript server disconnected; reconnecting.")
                return False
            if message.get("status") == "ERROR":
                if not self.stop_requested:
                    self.status.emit(
                        f"Live transcript server error; reconnecting: {message.get('message', 'unknown error')}"
                    )
                return False
            for segment in message.get("segments", []):
                text = str(segment.get("text", "")).strip()
                if not text:
                    continue
                key = (str(segment.get("start", "")), str(segment.get("end", "")), text)
                if key in self.seen_segments:
                    continue
                self.seen_segments.add(key)
                final = bool(segment.get("completed") or segment.get("final"))
                self.segment.emit("Meeting Audio", text, final)


class ProcessingWorker(QObject):
    status = Signal(str)
    finished = Signal()

    def __init__(self, folder: Path, metadata: MeetingMetadata, mode: str = "full") -> None:
        super().__init__()
        self.folder = folder
        self.metadata = metadata
        self.mode = mode

    @Slot()
    def process(self) -> None:
        try:
            MeetingProcessor().process(self.folder, self.metadata, self.status.emit, mode=self.mode)
        except Exception as error:
            message = f"Post-processing failed: {error}"
            self.status.emit(message)
            self.metadata.status = "processing_failed"
            self.metadata.processing = {
                **(self.metadata.processing if isinstance(self.metadata.processing, dict) else {}),
                "warnings": [*((self.metadata.processing or {}).get("warnings", []) if isinstance(self.metadata.processing, dict) else []), message],
                "mode": self.mode,
            }
            try:
                MeetingStore().write_metadata(self.folder, self.metadata)
            except Exception:
                pass
        finally:
            self.finished.emit()


class BatchProcessingWorker(QObject):
    status = Signal(str)
    finished = Signal()

    def __init__(self, jobs: list[tuple[Path, MeetingMetadata]], mode: str = "notes_only") -> None:
        super().__init__()
        self.jobs = jobs
        self.mode = mode

    @Slot()
    def process(self) -> None:
        processor = MeetingProcessor()
        try:
            for index, (folder, metadata) in enumerate(self.jobs, start=1):
                self.status.emit(f"Batch reprocess {index}/{len(self.jobs)}: {metadata.title or folder.name}")
                processor.process(folder, metadata, self.status.emit, mode=self.mode)
        except Exception as error:
            self.status.emit(f"Batch reprocess failed: {error}")
        finally:
            self.finished.emit()
