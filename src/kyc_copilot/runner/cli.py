"""Run reviews against the mock service and write the evaluation output.

    uv run --locked python -m kyc_copilot --api-url http://127.0.0.1:8766
    uv run --locked python -m kyc_copilot --cases KYC-D01 --submit-reviews

Writes a JSON array (docs/OUTPUT_CONTRACT.md) to --out. With --submit-reviews, each new draft is
sent to POST /v1/reviews for a human. An identical case id and draft hash is reused from
review_ledger.json and is not posted again. Approval happens only through the operator CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from kyc_copilot.adapters.store_factory import open_knowledge_store, resolve_store_target
from kyc_copilot.adapters.tools_client import ServiceError, ToolClient
from kyc_copilot.contracts.interfaces import KnowledgeStore
from kyc_copilot.contracts.models import CaseRun
from kyc_copilot.ingestion.parsing import IngestError
from kyc_copilot.observability.tracing import JsonlTrace, metrics, trace_events
from kyc_copilot.runner.ingest import ROOT, ingest
from kyc_copilot.runner.pipeline import review_case


def review_cases(case_ids: list[str], client: ToolClient, store: KnowledgeStore) -> list[dict]:
    return [run.packet for run in run_cases(case_ids, client, store)]


def run_cases(case_ids: list[str], client: ToolClient, store: KnowledgeStore) -> list[CaseRun]:
    # One packet per requested case ID, even if it is requested twice.
    return [review_case(cid, client, store) for cid in dict.fromkeys(case_ids)]


def draft_hash(packet: dict) -> str:
    """SHA-256 of the draft in the compact canonical JSON the review API hashes."""
    raw = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def load_review_ledger(path: Path) -> dict:
    """Case id → draft hash → review metadata. Missing file means no prior reviews."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Review ledger is unreadable: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Review ledger is unreadable: {path}")
    return data


def _business_key(packet: dict) -> str | None:
    """Entity plus review date. A blank entity or date never matches a previous draft."""
    facts = packet.get("facts")
    if not isinstance(facts, dict):
        return None
    entity = facts.get("entity_id")
    day = facts.get("review_date")
    if not isinstance(entity, str) or not entity.strip():
        return None
    if not isinstance(day, str) or not day.strip():
        return None
    return f"{entity}|{day}"


def _prior_review(ledger: dict, key: str, digest: str) -> dict | None:
    by_key = ledger.get(key)
    if by_key is None:
        return None
    if not isinstance(by_key, dict):
        raise ValueError(f"Review ledger entry for {key} is unreadable")
    hit = by_key.get(digest)
    if hit is None:
        return None
    if not isinstance(hit, dict) or hit.get("draft_hash") != digest or not hit.get("review_id"):
        raise ValueError(f"Review ledger entry for {key} is unreadable")
    return hit


def _remember_submit(client: ToolClient, case_id: str) -> None:
    """Copy the client's last submit attempt log into review_submit_events."""
    events = getattr(client, "review_submit_events", None)
    if events is None:
        return
    for attempt, status in getattr(client, "submit_attempt_log", ()):
        events.append(
            {
                "event": "review_submit",
                "case_id": case_id,
                "attempt": attempt,
                "status": status,
            }
        )


def _save_review_ledger(path: Path, ledger: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n")


def submit_drafts(client: ToolClient, packets: list[dict], ledger_path: Path) -> list[dict]:
    """Post each draft once. Reuse only when entity, review date, and draft hash all match."""
    ledger = load_review_ledger(ledger_path)
    reviews = []
    for packet in packets:
        case_id = packet["case_id"]
        digest = draft_hash(packet)
        key = _business_key(packet)
        prior = _prior_review(ledger, key, digest) if key else None
        if prior:
            reviews.append(
                {
                    "case_id": case_id,
                    "review_id": prior["review_id"],
                    "status": prior.get("status"),
                    "draft_hash": digest,
                    "reused": True,
                }
            )
            continue
        try:
            body = client.submit_review(case_id, packet)
            _remember_submit(client, case_id)
        except ServiceError as exc:
            _remember_submit(client, case_id)
            note = packet.get("narrative") or ""
            packet["narrative"] = note.rstrip() + "\nDraft was not submitted."
            reviews.append({"case_id": case_id, "error": exc.error})
            continue
        server_hash = body.get("draft_hash")
        review_id = body.get("review_id")
        if server_hash != digest or not review_id:
            reviews.append({"case_id": case_id, "error": "draft_hash_mismatch"})
            continue
        entry = {
            "review_id": review_id,
            "status": body.get("status"),
            "draft_hash": digest,
        }
        if key:
            ledger.setdefault(key, {})[digest] = entry
        _save_review_ledger(ledger_path, ledger)
        reviews.append({"case_id": case_id, **entry})
    return reviews


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--api-url", default="http://127.0.0.1:8766")
    p.add_argument("--data", type=Path, default=ROOT / "data" / "dev")
    p.add_argument("--db", type=Path, default=ROOT / ".state" / "app.sqlite")
    p.add_argument(
        "--dsn",
        default=None,
        help="Postgres DSN (overrides --db). Else KYC_DATABASE_URL. Local default remains --db.",
    )
    p.add_argument("--out", type=Path, default=ROOT / "submissions" / "results.json")
    p.add_argument(
        "--cases",
        nargs="*",
        help="case IDs (default: every case the service lists)",
    )
    p.add_argument(
        "--trace",
        type=Path,
        default=None,
        help="JSONL trace path (default: trace.jsonl next to --out)",
    )
    p.add_argument(
        "--submit-reviews",
        action="store_true",
        help=(
            "POST each new draft to /v1/reviews; reuse an identical draft from review_ledger.json"
        ),
    )
    a = p.parse_args(argv)
    try:
        target = resolve_store_target(db=str(a.db), dsn=a.dsn, env=os.environ)
        store_cm = open_knowledge_store(target)
    except ValueError as exc:
        sys.exit(str(exc))
    except Exception:
        sys.exit(
            "The knowledge store could not be opened. Nothing was written to another database."
        )

    client = ToolClient(a.api_url)
    with store_cm as store:
        try:
            client.health()
            cases = client.list_cases()
            links = {
                c["case_id"]: {
                    "documents": list(c["documents"]),
                    "intake_source": c.get("intake_source"),
                }
                for c in cases
            }
            ingest(a.data, store, case_links=links)
            case_ids = a.cases or [c["case_id"] for c in cases]
        except (IngestError, OSError, ServiceError, KeyError, TypeError) as exc:
            sys.exit(f"Cannot start the run: {exc}")
        runs = run_cases(case_ids, client, store)

    packets = [r.packet for r in runs]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(packets, indent=2, ensure_ascii=False) + "\n")
    trace_path = a.trace or a.out.parent / "trace.jsonl"
    if trace_path.exists():
        trace_path.unlink()
    sink = JsonlTrace(trace_path)
    decisions = []
    for r in runs:
        sink.write_run(r)
        decisions.extend(e for e in trace_events(r) if e["event"] == "decision")
    summary = metrics(decisions)
    sink.write(summary)
    for r in runs:
        attempts = {t: res.attempts for t, res in r.tool_results.items()}
        print(
            f"{r.packet['case_id']}: {r.packet['routing']:<23} "
            f"{r.seconds * 1000:7.1f} ms  attempts={attempts}"
        )
    print(f"Wrote {len(packets)} packets to {a.out}")
    print(f"Trace: {trace_path}")
    print(
        f"Metrics: success_rate={summary['success_rate']:.0%}  "
        f"p95_ms={summary['p95_ms']}  "
        f"alert={summary['alert']}  reason={summary['alert_reason']}"
    )

    if a.submit_reviews:
        ledger_path = a.out.parent / "review_ledger.json"
        try:
            reviews = submit_drafts(client, packets, ledger_path)
        except ValueError as exc:
            sys.exit(str(exc))
        path = a.out.parent / "reviews.json"
        path.write_text(json.dumps(reviews, indent=2) + "\n")
        fresh = sum("review_id" in r and not r.get("reused") for r in reviews)
        reused = sum(bool(r.get("reused")) for r in reviews)
        for event in getattr(client, "review_submit_events", []):
            sink.write(event)
        print(f"Submitted {fresh} drafts for human review; reused {reused}; see {path}")


if __name__ == "__main__":
    main()
