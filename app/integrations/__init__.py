"""
Nova Notetaker — integrations package.

Reserved for future integrations. Each integration should expose:

  class MyIntegration:
      name: str          — human-readable identifier
      def is_available(self) -> bool: ...
      def push(self, folder: Path, metadata, insights) -> None: ...

Current planned integrations:
  - Microsoft Teams calendar sync
  - Slack notification on meeting completion
  - Outlook task creation from action items
"""
