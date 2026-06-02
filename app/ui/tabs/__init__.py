"""
Nova Notetaker — per-tab mixin package.

Each module here contains a mixin class for one UI tab. MainWindow inherits
from all of them so that tab-specific build methods and event handlers are
co-located with the UI they manage while still sharing MainWindow's state.

Current modules:
  (tab extraction in progress — see main_window.py for the full method inventory)

Extraction order (simplest to most complex):
  1. search_tab.py   — _build_search_page, search_meetings, _add_search_result
  2. logs_tab.py     — _build_logs_page, log
  3. calendar_tab.py — _build_calendar_page + calendar/ICS helpers
  4. meetings_tab.py — _build_meetings_page + refresh_meetings + filters
  5. review_tab.py   — _build_review_queue_page + action-item status
  6. templates_tab.py — _build_templates_page + profile/template CRUD
  7. settings_tab.py  — _build_settings_page + save/validate
  8. capture_tab.py  — _build_live_page + recording/pause/live transcript
  9. overview_tab.py — _build_overview_workspace_page + detail cards
"""
