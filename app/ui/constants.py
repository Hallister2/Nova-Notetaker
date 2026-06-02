from __future__ import annotations

from app.core.settings import APP_ROOT

CAPTURE_PROFILES = {
    "Laptop mic + speakers": "laptop_speakers",
    "External mic + speakers": "external_mic_speakers",
    "Headphones / headset": "headphones",
    "Conference room": "conference_room",
    "Debug / raw capture": "debug_raw",
}

DEFAULT_LOOPBACK_DEVICE = "__default_wasapi_loopback__"
DEFAULT_MIC_DEVICE = "__default_microphone__"
ASSETS_DIR = APP_ROOT / "assets"
CLOSED_ACTION_STATUSES = {"done", "closed"}

NAV_ASSETS = [
    ("Nav - Capture.png", "Nav - Capture Active.png"),
    ("Nav - Meetings.png", "Nav - Meetings Active.png"),
    ("Nav - Review.png", "Nav - Review Active.png"),
    ("Nav - Search.png", "Nav - Search Active.png"),
    ("Nav - Calendar.png", "Nav - Calendar Active.png"),
    ("Nav - Logs.png", "Nav - Logs Active.png"),
    ("Nav - Templates.png", "Nav - Templates Active.png"),
    ("Nav - Settings.png", "Nav - Settings Active.png"),
]

EMPTY_ASSETS = {
    "meetings": "Nova - Empty Meetings.png",
    "actions": "Nova - Empty Actions.png",
    "calendar": "Nova - Empty Calendar.png",
    "search": "Nova - Empty Search.png",
}
