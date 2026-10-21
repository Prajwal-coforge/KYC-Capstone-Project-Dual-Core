"""Plain data objects and the storage port.

The workflow depends on `KnowledgeStore`, never on SQLite directly, so another
backend (for example Postgres) can be added as a new adapter later.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

# Policies and procedures are rules we maintain. Case documents are customer-supplied
# evidence: quotable data, never instructions.
TRUSTED = "trusted"
UNTRUSTED = "untrusted"


@dataclass(frozen=True)
class Source:
    source_id: str
    kind: str  # policy | procedure | document | tool
    trust: str  # trusted | untrusted
    title: str | None
    path: str
    content: str  # exact text; citation quotes are matched against this
    sha256: str


@dataclass(frozen=True)
class Policy:
    source_id: str
    entity_type: str
    jurisdiction: str
    effective_from: date
    effective_through: date
    edd_threshold: int | float


@dataclass(frozen=True)
class Document:
    source_id: str
    case_id: str | None
    doc_type: str | None
    is_intake: bool
    review_date: date | None
    entity_ref: str | None
    identity_status: str | None = None  # intake "Identity document:" value, e.g. "attached"


@dataclass(frozen=True)
class Chunk:
    source_id: str
    chunk_no: int
    start_line: int
    start_offset: int
    end_offset: int
    text: str


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
