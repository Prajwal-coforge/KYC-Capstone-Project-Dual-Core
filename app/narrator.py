"""Re-export narrative narrators during Phase 4 migration."""

from __future__ import annotations

from kyc_copilot.contracts.interfaces import Narrator
from kyc_copilot.narrative.narrator import ROUTE_TEXT, TemplateNarrator

__all__ = ["Narrator", "TemplateNarrator", "ROUTE_TEXT"]
