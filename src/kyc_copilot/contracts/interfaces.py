"""Ports and reflective statutory rule base. Stdlib + contracts models; no I/O."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import ClassVar, Protocol, runtime_checkable

from .models import CaseEvidence, Chunk, Decision, Document, Policy, Source


class KnowledgeStore(Protocol):
    def find_policies(self, entity_type: str, jurisdiction: str, review_date: date) -> list[Policy]:
        """All policies effective on review_date. Callers must handle 0 or >1 results."""

    def get_source(self, source_id: str) -> Source | None:
        """Return any stored source by id, or None if unknown."""

    def get_procedure(self, source_id: str) -> Source | None:
        """Return a procedure/scope source only; None when missing or wrong kind."""

    def case_documents(self, case_id: str) -> list[Source]:
        """Documents linked to the case, intake first then by source_id."""

    def get_document(self, source_id: str) -> Document | None:
        """Parsed document metadata for a source, or None if not a document."""

    def get_chunks(self, source_id: str) -> list[Chunk]:
        """Paragraph chunks in order for citation and retrieval."""

    def verify_quote(self, source_id: str, quote: str) -> bool:
        """True only if quote is non-blank and an exact substring of the source text."""


class Narrator(Protocol):
    def write(self, decision: Decision, evidence: CaseEvidence) -> str:
        """Produce the human-facing narrative for a decided packet."""


@runtime_checkable
class AddressCanonicalizer(Protocol):
    """Deterministic address normalization strategy (no network, never invents a winner)."""

    def canonicalize(self, raw_address: str) -> str: ...


class StatutoryRule(ABC):
    """Self-registering domain rule. Concrete subclasses set rule_id and precedence."""

    _registry: ClassVar[dict[str, type[StatutoryRule]]] = {}
    rule_id: ClassVar[str] = ""
    precedence: ClassVar[int] = 0

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Register concrete subclasses by rule_id; abstract bases stay unregistered."""
        super().__init_subclass__(**kwargs)
        if getattr(cls, "__abstractmethods__", None):
            return
        rule_id = getattr(cls, "rule_id", "") or ""
        if not rule_id:
            raise TypeError(f"{cls.__name__} must define a non-empty ClassVar rule_id")
        StatutoryRule._registry[rule_id] = cls

    @classmethod
    def ordered_rules(cls) -> list[StatutoryRule]:
        """Fresh instances sorted by (precedence, rule_id) for deterministic apply order."""
        types = sorted(
            cls._registry.values(),
            key=lambda rule_type: (rule_type.precedence, rule_type.rule_id),
        )
        return [rule_type() for rule_type in types]

    @abstractmethod
    def apply(self, evidence: CaseEvidence) -> None:
        """Run this statutory check against case evidence (domain refines behavior)."""
