<p align="center">
  <img width="591" height="172" alt="Nova Notetaker - Application Logo" src="assets/Nova Notetaker - Application Logo.png" />
</p>

# Nova Notetaker

Nova Notetaker is a Hallister Labs / Nova Suite desktop application for capturing, transcribing,
and summarizing meetings with local-first AI.

It is built for professionals who need a faster way to record meetings, generate structured notes,
track action items, and review past meetings — without sending audio or transcripts to a cloud
service unless you choose to.

## Highlights

- **Live Capture** — Capture microphone and system audio simultaneously using Windows WASAPI
  loopback. Start and stop meetings with a single click. Pause and resume mid-meeting without
  losing context.

- **Live Transcription** — Transcribe audio in real time using a local WhisperLive server.
  Live transcript segments appear during capture with confidence indicators and are used directly
  for notes generation.

- **AI Notes Generation** — Generate structured meeting notes from transcripts using Ollama
  (local), OpenAI / ChatGPT, or Claude (Anthropic). Choose the provider that fits your
  environment.

- **Meeting Templates** — Apply note templates to shape the structure and focus of generated
  notes. Built-in templates cover standard meetings, sales calls, project standups, and more.
  Create and save custom templates.

- **Capture Profiles** — Tune audio cleanup for your physical setup. Profiles for laptop
  speakers, external microphones, headsets, conference rooms, and raw debug capture adjust how
  speaker-bleed and transcript fragments are cleaned up before notes generation.

- **Meetings Browser** — Browse all past meetings with status badges, duration, and note
  previews. Open any meeting to review transcripts, notes, action items, and raw artifacts.

- **Review Queue** — Track open action items across all meetings. View, filter, and mark
  actions complete from a single queue view without opening individual meetings.

- **Full-Text Search** — Search meeting titles, transcripts, notes, and action items across
  your entire meeting archive.

- **Calendar View** — Navigate meetings by date with an integrated calendar. Export meetings as
  iCal events.

- **Meeting Profiles** — Define meeting contexts — company, attendees, title prefix, AI focus —
  and apply them at capture time so notes are scoped to the right audience.

- **Glossary and Corrections** — Inject domain vocabulary into the AI prompt and define
  transcription corrections to fix common mishearings before notes generation.

- **Update Checks** — Check GitHub releases for newer Nova Notetaker builds from the Settings
  page or automatically on startup. Download and install updates in one step.

- **Local-First Storage** — Audio, transcripts, notes, and settings are stored locally. No
  account required. Use any AI provider you already have access to.

## First Run

1. Launch Nova Notetaker.
2. Open **Settings**.
3. On the **Intelligence** tab, select your AI provider and enter credentials or a server URL.
4. On the **Transcription** tab, enable WhisperLive and enter your server URL if you have one.
   Transcription is optional — notes can be generated from audio alone.
5. On the **Device capture** tab, confirm your microphone and system audio device selections.
6. Return to **Live Capture** and start a meeting.

If services are unreachable the status card in the sidebar will reflect that. Run **Preflight**
on the Settings page to get a quick summary of what is and is not reachable.

## Working With Meetings

After stopping a capture, Nova Notetaker automatically:

- Validates and measures the recorded WAV files.
- Runs WhisperLive transcription (if enabled) and cleans up the transcript.
- Generates structured notes via your configured AI provider.
- Writes `transcript.md`, `notes.md`, and `metadata.json` into the meeting folder.
- Surfaces action items for the Review queue.

Meetings appear in the **Meetings** browser immediately. Open a meeting to view the full
transcript, generated notes, action items, raw audio info, and all saved artifacts.

Use the **Review** page to work through open actions across all meetings without opening each
one individually. Actions can be marked complete, reassigned, or auto-closed after a configurable
number of days.

## Capture Profiles

Nova uses capture profiles to tune transcript cleanup for different physical setups:

| Profile | Cleanup level | Best for |
|---|---|---|
| Laptop mic + speakers | Aggressive | Laptop with built-in audio |
| External mic + speakers | Balanced | Desktop or desk mic |
| Headphones / headset | Light | Headset with minimal bleed |
| Conference room | Moderate | Room microphone or speakerphone |
| Debug / raw capture | None | Inspecting raw transcripts |

## AI Providers

Nova Notetaker supports three AI backends for notes generation. Configure them in **Settings → Intelligence**.

| Provider | Notes |
|---|---|
| Ollama (local) | Fully local, no API key required. Run any compatible model on your own hardware. |
| OpenAI / ChatGPT | Requires an OpenAI API key. Supports gpt-4o and other chat-completion models. |
| Claude (Anthropic) | Requires an Anthropic API key. Supports claude-opus, claude-sonnet, and claude-haiku models. |

## Local Data

Nova Notetaker stores all application data locally:

```text
<project root>\config\settings.json
<project root>\meetings\
```

The meetings folder contains one subfolder per meeting. Each subfolder holds:

```text
meetings\<meeting-id>\
    metadata.json
    mic.wav
    system.wav
    transcript.md
    notes.md
```

The meetings directory can be changed in **Settings**. Removing or moving the folder does not
delete anything — Nova Notetaker will simply not find those meetings until the path is restored.

## Development Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

### Build installer

```powershell
.\PackageApplication.ps1
```

Requires Python, PyInstaller, and Inno Setup 6. Pass `-SkipInstaller` to build only the EXE.
Pass `-Version 1.0.0` to bump the version before building.

### Run tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## Status

Nova Notetaker is under active development. The current focus is transcription reliability,
notes quality, meeting review workflows, and polished Nova Suite desktop styling.

---

*Part of the [Nova Suite](https://github.com/Hallister2) family of desktop tools by Hallister Labs.*
