"""Ingestion: markdown → contracts. Depends on contracts only; no network."""

from kyc_copilot.ingestion.ingest import (
    apply_case_links,
    apply_policy_manifest_guard,
    discover,
    ingest,
    load_policy_manifest,
    manifest_hash,
    policy_overlap_warnings,
)
from kyc_copilot.ingestion.parsing import IngestError, chunk_paragraphs, parse_file, read_exact

__all__ = [
    "IngestError",
    "apply_case_links",
    "apply_policy_manifest_guard",
    "chunk_paragraphs",
    "discover",
    "ingest",
    "load_policy_manifest",
    "manifest_hash",
    "parse_file",
    "policy_overlap_warnings",
    "read_exact",
]
