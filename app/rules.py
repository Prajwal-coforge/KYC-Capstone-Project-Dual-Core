"""Re-export domain rules during Phase 1–3 migration. Prefer `kyc_copilot.domain.rules`."""

from __future__ import annotations

from kyc_copilot.contracts.models import CaseEvidence, Decision
from kyc_copilot.domain.rules import (
    SCOPE_ID,
    SUPPORTED,
    compare_addresses,
    decide,
    normalize_address,
)

__all__ = [
    "SCOPE_ID",
    "SUPPORTED",
    "CaseEvidence",
    "Decision",
    "compare_addresses",
    "decide",
    "normalize_address",
]
