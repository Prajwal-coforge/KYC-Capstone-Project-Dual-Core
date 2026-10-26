"""Re-export domain packet builders during Phase 4 migration."""

from __future__ import annotations

from kyc_copilot.domain.packet import (
    SCOPE_PHRASES,
    _follow_up,
    build_citations,
    build_packet,
)

__all__ = [
    "SCOPE_PHRASES",
    "_follow_up",
    "build_citations",
    "build_packet",
]
