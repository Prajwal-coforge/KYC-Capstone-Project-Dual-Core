"""Frozen boundary models shared across layers. Stdlib + Pydantic; no I/O."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass

# Policies and procedures are rules we maintain. Case documents are customer-supplied
# evidence: quotable data, never instructions.
TRUSTED = "trusted"
UNTRUSTED = "untrusted"

_FROZEN = ConfigDict(frozen=True)


@dataclass(config=_FROZEN)
class Source:
    source_id: str
    kind: str  # policy | procedure | document | tool
    trust: str  # trusted | untrusted
    title: str | None
    path: str
    content: str  # exact text; citation quotes are matched against this
    sha256: str


@dataclass(config=_FROZEN)
class Policy:
    source_id: str
    entity_type: str
    jurisdiction: str
    effective_from: date
    effective_through: date
    edd_threshold: int | float


@dataclass(config=_FROZEN)
class Document:
    source_id: str
    case_id: str | None
    doc_type: str | None
    is_intake: bool
    review_date: date | None
    entity_ref: str | None
    identity_status: str | None = None  # intake "Identity document:" value, e.g. "attached"
    filing_jurisdiction: str | None = None
    declared_owner: str | None = None
    filing_address: str | None = None
    holder_name: str | None = None
    birth_year: int | None = None
    document_reference: str | None = None
    identity_not_supplied: bool = False
    company_name: str | None = None
    label_conflicts: tuple[str, ...] = ()
    empty: bool = False
    review_date_unreadable: bool = False


@dataclass(config=_FROZEN)
class Chunk:
    source_id: str
    chunk_no: int
    start_line: int
    start_offset: int
    end_offset: int
    text: str


@dataclass(config=_FROZEN)
class ParsedFile:
    source: Source
    policy: Policy | None = None
    document: Document | None = None
    chunks: tuple[Chunk, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(config=_FROZEN)
class ToolResult:
    tool: str
    ok: bool
    payload: dict[str, Any] | None
    attempts: int
    error: str | None = None
    seconds: float = 0.0
    circuit: str = "closed"  # closed | open | half_open
    attempt_log: tuple[tuple[int, str], ...] = ()

    @property
    def source_id(self) -> str | None:
        """Tool response source_id when the call succeeded with a payload."""
        return self.payload.get("source_id") if self.payload else None


@dataclass(config=_FROZEN)
class CaseEvidence:
    case_id: str
    review_date: date | None
    entity_ref: str | None
    identity_status: str | None
    identity_document_present: bool
    customer: dict[str, Any] | None
    registry: dict[str, Any] | None
    screening: dict[str, Any] | None
    transactions: dict[str, Any] | None
    failed_tools: tuple[str, ...] = ()
    filing_jurisdiction: str | None = None
    declared_owner: str | None = None
    filing_address: str | None = None
    holder_name: str | None = None
    birth_year: int | None = None
    document_reference: str | None = None
    identity_not_supplied: bool = False
    company_name: str | None = None
    document_faults: tuple[str, ...] = ()


@dataclass(config=_FROZEN)
class Decision:
    classification: str
    routing: str
    policy_ids: list[str]
    policy: Policy | None
    facts: dict[str, Any]
    missing_information: list[str]
    reasons: list[str]
    incomplete_reasons: list[str]
    address_check: str  # same | normalized_same | different | unknown
    screening_matches: list[dict[str, Any]] = Field(default_factory=list)
    pep: bool | None = None
    monthly_total: int | float | None = None


@dataclass(config=_FROZEN)
class CaseRun:
    packet: dict[str, Any]
    decision: Decision
    tool_results: dict[str, ToolResult]
    seconds: float
