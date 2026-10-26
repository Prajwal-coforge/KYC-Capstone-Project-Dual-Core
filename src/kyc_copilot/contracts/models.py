"""Frozen boundary models shared across layers. Stdlib only; no I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

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


@dataclass(frozen=True)
class ParsedFile:
    source: Source
    policy: Policy | None = None
    document: Document | None = None
    chunks: tuple[Chunk, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolResult:
    tool: str
    ok: bool
    payload: dict | None
    attempts: int
    error: str | None = None
    seconds: float = 0.0
    circuit: str = "closed"  # closed | open | half_open

    @property
    def source_id(self) -> str | None:
        return self.payload.get("source_id") if self.payload else None


@dataclass(frozen=True)
class CaseEvidence:
    case_id: str
    review_date: date | None
    entity_ref: str | None
    identity_status: str | None
    identity_document_present: bool
    customer: dict | None
    registry: dict | None
    screening: dict | None
    transactions: dict | None
    failed_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class Decision:
    classification: str
    routing: str
    policy_ids: list[str]
    policy: Policy | None
    facts: dict
    missing_information: list[str]
    reasons: list[str]
    incomplete_reasons: list[str]
    address_check: str  # same | normalized_same | different | unknown
    screening_matches: list[dict] = field(default_factory=list)
    pep: bool | None = None
    monthly_total: int | float | None = None


@dataclass(frozen=True)
class CaseRun:
    packet: dict
    decision: Decision
    tool_results: dict[str, ToolResult]
    seconds: float
