# Nova Notetaker

Nova Notetaker is a local-first desktop meeting capture app with NOVA-inspired branding.

Initial MVP goals:

- PySide6 desktop UI from day one
- Native Windows WASAPI loopback attempt for system audio
- Separate microphone and system audio capture
- Markdown meeting notes
- Ollama-first summarization with optional OpenAI/ChatGPT provider later
- WhisperLive transcription integration later

## First milestone

The first milestone is intentionally focused on audio reliability:

1. Launch desktop app.
2. Enumerate audio devices.
3. Select microphone and system output device.
4. Start/stop meeting capture.
5. Save meeting metadata and raw audio streams.
6. Validate captured WAV files.
7. Create transcript and notes artifacts after capture.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

For native Windows loopback, `pyaudiowpatch` is included because it exposes WASAPI loopback devices more directly than standard PyAudio.

## Current capture flow

After you stop a meeting, Nova Notetaker now:

- validates `mic.wav` and `system.wav`
- writes audio duration, sample rate, channel count, and file size into `metadata.json`
- writes `transcript.md`
- writes `notes.md`
- records any processing warnings in both notes and metadata

## Capture Profiles

Nova uses capture profiles to tune transcript cleanup for different physical setups:

- `Laptop mic + speakers`: most aggressive cleanup for speaker bleed.
- `External mic + speakers`: balanced cleanup for better desk setups.
- `Headphones / headset`: light cleanup because speaker bleed should be minimal.
- `Conference room`: moderate cleanup for room audio.
- `Debug / raw capture`: disables speaker-bleed cleanup so you can inspect raw transcripts.

WhisperLive transcription is currently disabled by default until your internal endpoint is confirmed. Configure it in `config/settings.json`:

```json
"transcription": {
  "enabled": false,
  "whisperlive_url": "http://localhost:9090",
  "http_transcription_endpoint": "/v1/audio/transcriptions",
  "model": "whisper",
  "timeout_seconds": 120
}
```

When transcription is enabled and returns text, the Ollama provider will generate meeting notes through:

```json
"ai": {
  "provider": "ollama",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llama3.1:8b"
}
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_meeting_processor
```
