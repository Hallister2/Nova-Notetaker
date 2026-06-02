"""
Nova Notetaker — per-tab mixin package.

Each module contains a mixin class for one UI tab. MainWindow inherits
from all of them so that tab-specific build methods and event handlers are
co-located with the UI they manage while still sharing MainWindow's state.
"""

from app.ui.tabs.capture_tab import CaptureTabMixin
from app.ui.tabs.calendar_tab import CalendarTabMixin
from app.ui.tabs.logs_tab import LogsTabMixin
from app.ui.tabs.meetings_tab import MeetingsTabMixin
from app.ui.tabs.overview_tab import OverviewTabMixin
from app.ui.tabs.review_tab import ReviewTabMixin
from app.ui.tabs.search_tab import SearchTabMixin
from app.ui.tabs.settings_tab import SettingsTabMixin
from app.ui.tabs.templates_tab import TemplatesTabMixin

__all__ = [
    "CaptureTabMixin",
    "CalendarTabMixin",
    "LogsTabMixin",
    "MeetingsTabMixin",
    "OverviewTabMixin",
    "ReviewTabMixin",
    "SearchTabMixin",
    "SettingsTabMixin",
    "TemplatesTabMixin",
]
