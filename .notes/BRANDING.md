# Hallister Labs Brand Context

Last updated: 2026-05-28

Company name: Hallister Labs

Website: www.hallisterlabs.com

Product family: Nova Suite

Current product: Nova Notetaker

Brand architecture: Hallister Labs is the company. Nova Suite is the product family. Nova Notetaker is one application within Nova Suite.

## Naming Guidance

Use "Hallister Labs" for company/about/legal/support contexts.

Use "Nova Suite" when referring to the broader product ecosystem, shared platform, or multi-app experience.

Use "Nova Notetaker" for this specific meeting capture and intelligence app.

Short product references can use "Nova" inside product UI when the context is already clear, such as "Nova is processing a meeting."

Avoid renaming every surface from Nova Notetaker to Nova Suite. Treat Nova Suite as the family wrapper and Nova Notetaker as the app name until a deliberate app-wide rename is requested.

## Product Positioning

Nova Suite should feel like a family of focused local-first productivity tools: fast, polished, useful, private by default, and calm under pressure.

Nova Notetaker specifically emphasizes:

- Meeting capture
- Audio reliability
- Local-first storage
- Transcription and notes
- Reviewable insights, action items, dates, and follow-ups
- Human-in-the-loop control rather than black-box automation

## Visual Personality

The current Nova Notetaker look is executive, dark, technical, and restrained, with bright orange as the energetic brand signal.

Keep future Nova Suite apps visually related by preserving:

- Dark graphite workspace foundations
- Orange primary actions and active navigation
- Compact, information-dense layouts
- Subtle borders and raised panels
- Rounded corners in the 6-8 px range
- Segoe UI as the desktop UI typeface
- Clear status color coding
- Asset-led navigation icons and empty states

Avoid marketing-page visual excess inside the app. Nova Suite apps should feel like capable work tools, not landing pages.

## Core Color System

Primary dark theme, currently `executive_dark`:

- App background: `#101112`
- Sidebar: `#141516`
- Panel: `#18191B`
- Raised surface: `#202123`
- Field/input surface: `#141516`
- Main text: `#F4F6F8`
- Secondary text: `#C0C3C7`
- Muted text: `#85888E`
- Border: `rgba(255, 255, 255, 0.08)`
- Soft surface: `rgba(255, 255, 255, 0.04)`
- Hover surface: `#292A2D`
- Brand orange: `#FF8A1F`
- Brand orange hover: `#FFA13D`
- Primary button text: `#16100A`
- Success: `#3DDC84`
- Recording/danger: `#FF4D4D`
- Informational blue: `#82B6FF`
- Badge surface: `#252628`
- Disabled surface: `#1A1B1D`

Light theme, currently `clean_light` / Graphite Light:

- App background: `#E7E6E2`
- Sidebar: `#DAD9D4`
- Panel: `#F1F0EC`
- Raised surface: `#E2E1DC`
- Field/input surface: `#F8F7F3`
- Main text: `#202224`
- Secondary text: `#4F5358`
- Muted text: `#73777D`
- Border: `rgba(32, 34, 36, 0.16)`
- Soft surface: `rgba(32, 34, 36, 0.055)`
- Hover surface: `#D4D3CE`
- Brand orange: `#FF7A1A`
- Brand orange hover: `#FF8F33`
- Primary button text: `#1C1308`
- Success: `#0E9F6E`
- Recording/danger: `#E02424`
- Informational blue: `#2F6FB7`
- Badge surface: `#DFDED9`
- Disabled surface: `#E1E0DC`

Use orange sparingly and deliberately: primary action, active navigation, active tabs, progress, selected theme controls, date/state badges, and important workflow indicators.

## UI System

Use compact desktop application patterns:

- Left sidebar navigation with icon assets and active orange state.
- Panels and raised panels for grouped tools and operational areas.
- Tables for repeated meeting/review data.
- Badges for status, confidence, dates, and processing states.
- Orange primary buttons for the one action that moves the workflow forward.
- Neutral raised buttons for secondary actions.
- Red/recording state only for active recording or destructive/danger states.
- Blue for processing/informational status.
- Green for healthy, complete, connected, or successful status.

Corner radius guidance:

- Panels: 8 px
- Buttons: 6-7 px
- Cards/metric tiles: 6-7 px
- Progress bars: 4 px
- Badges: 7-12 px depending on size

Typography guidance:

- UI font: Segoe UI
- Base UI size: 13 px
- Muted/metadata text: 11-12 px
- Section labels: 12 px, semi-bold, uppercase where appropriate
- Panel headings: 18 px, bold
- Page titles: 24 px, bold
- Timer/hero operational values: 28 px, bold

## Asset Direction

Existing Nova Notetaker assets live in `assets/`.

Current asset families:

- Brand marks: `Brand Mark 1.png`, `Brand Mark 2.png`, `Brand Mark 3.png`
- App icon: `App Icon.png`
- Orb: `Orb.png`
- Navigation states: `Capture`, `Meetings`, `Review`, `Templates`, `Settings`
- Empty states: no meetings, no actions, no calendar, no search
- Icon examples: app icon, brand mark, icon set, orb, empty state

Future Nova Suite apps should reuse the same system:

- Each major navigation item should have default, active, and full-size asset variants when practical.
- Empty states should be custom branded illustrations, not generic stock art.
- Product icons should feel related to the Nova orb/mark system.
- Brand marks should remain clean, high contrast, and usable on graphite surfaces.

## Copy And Tone

Voice should be calm, capable, and concise.

Good UI copy:

- "Capture saved. Starting post-processing."
- "Nova is already processing a meeting."
- "System audio appears very quiet; confirm the selected output device is correct."

Avoid overly cute, salesy, or verbose copy in operational surfaces. The app should sound competent and steady.

Use specific status text when processing may take time. Prefer telling the user what is happening, such as "Preparing transcript" or "Generating notes with Ollama", over vague loading language.

Operational status language should match the real app state. For Nova Notetaker, the orb/status area should use terms such as Ready, Recording, Finalizing, Processing, Transcribing speaker audio chunk 3/14, and Generating notes. This is part of the Hallister Labs brand promise: calm tools that explain what they are doing.

When an AI-generated interpretation may benefit from user context, prefer visible user-editable context fields over hidden prompt assumptions. For Nova Notetaker, per-meeting context is stored with metadata and should be reused during reprocess.

## Product Metadata And Exports

When adding metadata, generated files, export identifiers, help/about surfaces, or future installer/package text, prefer:

- Company: Hallister Labs
- Suite: Nova Suite
- App: Nova Notetaker
- Website: www.hallisterlabs.com

For calendar/export product identifiers, future wording can move from a single-app identity toward the suite structure, for example:

`-//Hallister Labs//Nova Suite - Nova Notetaker//EN`

## Implementation Notes

Current theme tokens are defined in `app/ui/styles.py`.

Current default app name is defined in `app/core/settings.py` and `config/settings.json`.

Current main window and dialog titles use "Nova Notetaker" throughout `app/ui/main_window.py`.

Do not change visible names, export identifiers, or app titles opportunistically. Apply brand updates intentionally as part of a product rename, about page, installer, export, website, or shared Nova Suite shell task.
