"""Ports and reflective statutory rule base. Stdlib + contracts models; no I/O."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import ClassVar, Protocol

from .models import CaseEvidence, Chunk, Decision, Document, Policy, Source


class KnowledgeStore(Protocol):
    def find_policies(self, entity_type: str, jurisdiction: str, review_date: date) -> list[Policy]:
        """All policies effective on review_date. Callers must handle 0 or >1 results."""

    def get_source(self, source_id: str) -> Source | None: ...

    def get_procedure(self, source_id: str) -> Source | None: ...

    def case_documents(self, case_id: str) -> list[Source]: ...

    def get_document(self, source_id: str) -> Document | None: ...

    def get_chunks(self, source_id: str) -> list[Chunk]: ...

    def verify_quote(self, source_id: str, quote: str) -> bool:
        """True only if quote is non-blank and an exact substring of the source text."""


class Narrator(Protocol):
    def write(self, decision: Decision, evidence: CaseEvidence) -> str: ...


class StatutoryRule(ABC):
    """Self-registering domain rule. Concrete subclasses set rule_id and precedence."""

    _registry: ClassVar[dict[str, type[StatutoryRule]]] = {}
    rule_id: ClassVar[str] = ""
    precedence: ClassVar[int] = 0

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if getattr(cls, "__abstractmethods__", None):
            return
        rule_id = getattr(cls, "rule_id", "") or ""
        if not rule_id:
            raise TypeError(f"{cls.__name__} must define a non-empty ClassVar rule_id")
        StatutoryRule._registry[rule_id] = cls

    @classmethod
    def ordered_rules(cls) -> list[StatutoryRule]:
        types = sorted(
            cls._registry.values(),
            key=lambda rule_type: (rule_type.precedence, rule_type.rule_id),
        )
        return [rule_type() for rule_type in types]

    @abstractmethod
    def apply(self, evidence: CaseEvidence) -> None:
        """Run this statutory check against case evidence (domain refines behavior)."""
