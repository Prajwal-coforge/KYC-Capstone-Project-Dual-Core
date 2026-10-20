"""Ingest policies and case documents into the application's SQLite store.

    uv run --locked python -m app.ingest --data data/dev --db .state/app.sqlite
    uv run --locked python -m app.ingest --data data/dev --api-url http://127.0.0.1:8766

Only counts and source IDs are printed. Document text is untrusted evidence and is
stored verbatim (citation quotes must match it exactly); it is never executed or obeyed.
Case data (customer, registry, screening, transactions) is NOT ingested: the workflow
must read it through the mock API tools. Do not point this at dataset.json.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .parsing import IngestError, ParsedFile, parse_file
from .sqlite_store import SqliteKnowledgeStore

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1"


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


def fetch_case_links(api_url: str, timeout: float = 5.0) -> dict[str, dict]:
    """GET /v1/cases: the authoritative case -> document mapping, when the service is up."""
    with urllib.request.urlopen(api_url.rstrip("/") + "/v1/cases", timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return {c["case_id"]: {"documents": list(c["documents"]), "intake_source": c.get("intake_source")}
            for c in body["cases"]}


def apply_case_links(parsed: list[ParsedFile], links: dict[str, dict]) -> list[str]:
    """Override filename-derived case IDs with the service's mapping. Returns warnings."""
    warnings: list[str] = []
    by_id = {p.source.source_id: p for p in parsed if p.document}
    listed: set[str] = set()
    for case_id, link in sorted(links.items()):
        for sid in link["documents"]:
            listed.add(sid)
            item = by_id.get(sid)
            if item is None:
                warnings.append(f"{case_id}: service lists {sid} but no such file was ingested")
                continue
            item.document = dataclasses.replace(
                item.document, case_id=case_id, is_intake=(sid == link.get("intake_source")))
    for sid in sorted(set(by_id) - listed):
        warnings.append(f"{sid}: document file is not listed by any case in the service")
    return warnings


def policy_overlap_warnings(parsed: list[ParsedFile]) -> list[str]:
    policies = [p.policy for p in parsed if p.policy]
    out = []
    for i, a in enumerate(policies):
        for b in policies[i + 1:]:
            if (a.entity_type, a.jurisdiction) == (b.entity_type, b.jurisdiction) and \
                    a.effective_from <= b.effective_through and b.effective_from <= a.effective_through:
                out.append(f"policies {a.source_id} and {b.source_id} have overlapping effective dates")
    return out


def manifest_hash(parsed: list[ParsedFile]) -> str:
    lines = sorted(f"{p.source.source_id}:{p.source.sha256}" for p in parsed)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def ingest(data_dir: Path, store: SqliteKnowledgeStore, api_url: str | None = None) -> dict:
    parsed = discover(data_dir)
    warnings = [w for p in parsed for w in p.warnings] + policy_overlap_warnings(parsed)
    linked = False
    if api_url:
        try:
            warnings += apply_case_links(parsed, fetch_case_links(api_url))
            linked = True
        except (OSError, urllib.error.URLError, ValueError, KeyError) as exc:
            warnings.append(f"could not read case list from service ({type(exc).__name__}); "
                            "case IDs derived from source IDs instead")
    manifest = manifest_hash(parsed)
    diff = store.replace_all(parsed, {
        "data_dir": str(data_dir), "manifest_sha256": manifest, "schema_version": SCHEMA_VERSION,
        "case_links_from_service": str(linked).lower()})
    return {"data_dir": str(data_dir), "manifest_sha256": manifest, "case_links_from_service": linked,
            **{k: len(v) for k, v in diff.items()}, "changed_ids": diff["added"] + diff["updated"],
            "removed_ids": diff["removed"], "totals": store.counts(), "warnings": warnings}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, default=ROOT / "data" / "dev")
    p.add_argument("--db", type=Path, default=ROOT / ".state" / "app.sqlite")
    p.add_argument("--api-url", help="optional mock service URL, used only to map documents to cases")
    a = p.parse_args()
    if a.db.name == "mock.sqlite":
        sys.exit("Refusing to use the mock service's state file; choose another --db path.")
    try:
        with SqliteKnowledgeStore(a.db) as store:
            report = ingest(a.data, store, a.api_url)
    except (IngestError, OSError) as exc:
        sys.exit(f"Ingestion failed, nothing stored: {exc}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
