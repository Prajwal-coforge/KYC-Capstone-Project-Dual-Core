"""Ingest policies and case documents into the application's SQLite store.

    uv run --locked python -m app.ingest --data data/dev --db .state/app.sqlite
    uv run --locked python -m app.ingest --data data/dev --api-url http://127.0.0.1:8766

Network (GET /v1/cases) stays here; pure ingest + PolicyManifestGuard live in
`kyc_copilot.ingestion`. Do not point this at dataset.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from kyc_copilot.contracts.models import ParsedFile
from kyc_copilot.ingestion import (
    apply_case_links,
    discover,
    manifest_hash,
    policy_overlap_warnings,
)
from kyc_copilot.ingestion import (
    ingest as _core_ingest,
)
from kyc_copilot.ingestion.parsing import IngestError, parse_file

from .sqlite_store import SCHEMA_VERSION, SqliteKnowledgeStore

# Re-exports for callers/tests that imported these from app.ingest.
__all__ = [
    "IngestError",
    "ParsedFile",
    "SCHEMA_VERSION",
    "SqliteKnowledgeStore",
    "apply_case_links",
    "discover",
    "fetch_case_links",
    "ingest",
    "manifest_hash",
    "parse_file",
    "policy_overlap_warnings",
]

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "contracts" / "policy_manifest.json"


def fetch_case_links(api_url: str, timeout: float = 5.0) -> dict[str, dict]:
    """GET /v1/cases: the authoritative case -> document mapping, when the service is up."""
    with urllib.request.urlopen(api_url.rstrip("/") + "/v1/cases", timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return {
        c["case_id"]: {"documents": list(c["documents"]), "intake_source": c.get("intake_source")}
        for c in body["cases"]
    }


def ingest(data_dir: Path, store: SqliteKnowledgeStore, api_url: str | None = None) -> dict:
    case_links = None
    extra_warnings: list[str] = []
    if api_url:
        try:
            case_links = fetch_case_links(api_url)
        except (OSError, urllib.error.URLError, ValueError, KeyError) as exc:
            extra_warnings.append(
                f"could not read case list from service ({type(exc).__name__}); "
                "case IDs derived from source IDs instead"
            )
            case_links = None
    report = _core_ingest(
        data_dir,
        store,
        case_links=case_links,
        manifest_path=DEFAULT_MANIFEST,
        schema_version=str(SCHEMA_VERSION),
    )
    if extra_warnings:
        report = {**report, "warnings": list(report["warnings"]) + extra_warnings}
        report["case_links_from_service"] = False
    return report


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--data", type=Path, default=ROOT / "data" / "dev")
    p.add_argument("--db", type=Path, default=ROOT / ".state" / "app.sqlite")
    p.add_argument(
        "--api-url",
        help="optional mock service URL, used only to map documents to cases",
    )
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
