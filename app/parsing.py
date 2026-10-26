"""Re-export ingestion parsing from `kyc_copilot.ingestion` during the migration."""
from __future__ import annotations

from kyc_copilot.contracts.models import ParsedFile
from kyc_copilot.ingestion.parsing import (
    DOCUMENT_FIELDS,
    FIELD_RE,
    POLICY_FIELDS,
    SOURCE_ID_RE,
    TITLE_RE,
    IngestError,
    chunk_paragraphs,
    parse_file,
    read_exact,
)

__all__ = [
    "DOCUMENT_FIELDS",
    "FIELD_RE",
    "IngestError",
    "POLICY_FIELDS",
    "SOURCE_ID_RE",
    "TITLE_RE",
    "ParsedFile",
    "chunk_paragraphs",
    "parse_file",
    "read_exact",
]
