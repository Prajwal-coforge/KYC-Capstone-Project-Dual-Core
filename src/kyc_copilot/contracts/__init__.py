"""Boundary contracts: frozen models and ports. Stdlib + pydantic; no I/O."""

from kyc_copilot.contracts.interfaces import (
    AddressCanonicalizer,
    KnowledgeStore,
    Narrator,
    StatutoryRule,
)

__all__ = [
    "AddressCanonicalizer",
    "KnowledgeStore",
    "Narrator",
    "StatutoryRule",
]
