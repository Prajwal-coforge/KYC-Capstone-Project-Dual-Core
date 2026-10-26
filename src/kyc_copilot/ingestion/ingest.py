"""Ingest policies and case documents into a KnowledgeStore.

No network: callers (runner/adapters) pass pre-fetched case links when needed.
Policy SHA-256 values are checked against contracts/policy_manifest.json.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from kyc_copilot.contracts.models import ParsedFile
from kyc_copilot.ingestion.parsing import IngestError, parse_file

DEFAULT_MANIFEST = Path(__file__).resolve().parents[3] / "contracts" / "policy_manifest.json"


class _IngestStore(Protocol):
    def replace_all(self, parsed: Any, meta: dict[str, str]) -> dict[str, list[str]]: ...

    def counts(self) -> dict[str, int]: ...


def discover(data_dir: Path) -> list[ParsedFile]:
    parsed: list[ParsedFile] = []
    for folder in ("policies", "documents"):
        directory = data_dir / folder
        if not directory.is_dir():
            raise IngestError(f"missing directory: {directory}")
        parsed += [parse_file(p, folder) for p in sorted(directory.glob("*.md"))]
    if not any(p.source.kind == "procedure" for p in parsed):
        raise IngestError("no scope/procedure document found (a policy file without policy fields)")
    return parsed


def load_policy_manifest(manifest_path: Path) -> dict[str, str]:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    policies = raw.get("policies")
    if not isinstance(policies, dict) or not policies:
        raise IngestError(f"invalid policy manifest: {manifest_path}")
    return {str(k): str(v) for k, v in policies.items()}


def apply_policy_manifest_guard(
    parsed: list[ParsedFile], manifest: dict[str, str]
) -> tuple[list[ParsedFile], list[str]]:
    """ENG-01: known hash mismatch stops the run; unknown policy files are not loaded."""
    kept: list[ParsedFile] = []
    warnings: list[str] = []
    for item in parsed:
        if item.source.kind not in ("policy", "procedure"):
            kept.append(item)
            continue
        source_id = item.source.source_id
        expected = manifest.get(source_id)
        if expected is None:
            warnings.append(f"new_policy_file_not_loaded:{source_id}")
            continue
        if item.source.sha256 != expected:
            raise IngestError(
                f"policy hash mismatch for {source_id}: "
                f"manifest={expected} actual={item.source.sha256}"
            )
        kept.append(item)
    return kept, warnings


def apply_case_links(
    parsed: list[ParsedFile], links: dict[str, dict]
) -> tuple[list[ParsedFile], list[str]]:
    """Override filename-derived case IDs with the service's mapping. Returns warnings."""
    warnings: list[str] = []
    by_id = {p.source.source_id: p for p in parsed if p.document}
    replacements: dict[str, ParsedFile] = {}
    listed: set[str] = set()
    for case_id, link in sorted(links.items()):
        for sid in link["documents"]:
            listed.add(sid)
            item = by_id.get(sid)
            if item is None:
                warnings.append(f"{case_id}: service lists {sid} but no such file was ingested")
                continue
            new_doc = dataclasses.replace(
                item.document,
                case_id=case_id,
                is_intake=(sid == link.get("intake_source")),
            )
            replacements[sid] = dataclasses.replace(item, document=new_doc)
    for sid in sorted(set(by_id) - listed):
        warnings.append(f"{sid}: document file is not listed by any case in the service")
    out = [replacements.get(p.source.source_id, p) for p in parsed]
    return out, warnings


def policy_overlap_warnings(parsed: list[ParsedFile]) -> list[str]:
    policies = [p.policy for p in parsed if p.policy]
    out: list[str] = []
    for i, a in enumerate(policies):
        for b in policies[i + 1 :]:
            if (a.entity_type, a.jurisdiction) == (b.entity_type, b.jurisdiction) and (
                a.effective_from <= b.effective_through and b.effective_from <= a.effective_through
            ):
                out.append(
                    f"policies {a.source_id} and {b.source_id} have overlapping effective dates"
                )
    return out


def manifest_hash(parsed: list[ParsedFile]) -> str:
    lines = sorted(f"{p.source.source_id}:{p.source.sha256}" for p in parsed)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def ingest(
    data_dir: Path,
    store: _IngestStore,
    case_links: dict[str, dict] | None = None,
    manifest_path: Path | None = DEFAULT_MANIFEST,
    schema_version: str = "2",
) -> dict:
    parsed = discover(data_dir)
    warnings = [w for p in parsed for w in p.warnings] + policy_overlap_warnings(parsed)
    if manifest_path is not None:
        parsed, guard_warnings = apply_policy_manifest_guard(
            parsed, load_policy_manifest(manifest_path)
        )
        warnings += guard_warnings
    linked = False
    if case_links is not None:
        parsed, link_warnings = apply_case_links(parsed, case_links)
        warnings += link_warnings
        linked = True
    digest = manifest_hash(parsed)
    diff = store.replace_all(
        parsed,
        {
            "data_dir": str(data_dir),
            "manifest_sha256": digest,
            "schema_version": schema_version,
            "case_links_from_service": str(linked).lower(),
        },
    )
    return {
        "data_dir": str(data_dir),
        "manifest_sha256": digest,
        "case_links_from_service": linked,
        **{k: len(v) for k, v in diff.items()},
        "changed_ids": diff["added"] + diff["updated"],
        "removed_ids": diff["removed"],
        "totals": store.counts(),
        "warnings": warnings,
    }
