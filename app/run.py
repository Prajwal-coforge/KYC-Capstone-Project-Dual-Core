"""Run reviews against the mock service and write the evaluation output.

    uv run --locked python -m app.run --api-url http://127.0.0.1:8766
    uv run --locked python -m app.run --cases KYC-D01 --submit-reviews

Writes a JSON array (docs/OUTPUT_CONTRACT.md) to --out. With --submit-reviews, each draft is
sent to POST /v1/reviews for a human; approval happens only through the operator CLI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ingest import ingest
from .parsing import IngestError
from .pipeline import CaseRun, review_case
from .sqlite_store import SqliteKnowledgeStore
from .tools_client import ServiceError, ToolClient

ROOT = Path(__file__).resolve().parents[1]


def review_cases(case_ids: list[str], client: ToolClient, store: SqliteKnowledgeStore) -> list[dict]:
    return [run.packet for run in run_cases(case_ids, client, store)]


def run_cases(case_ids: list[str], client: ToolClient, store: SqliteKnowledgeStore) -> list[CaseRun]:
    # One packet per requested case ID, even if it is requested twice.
    return [review_case(cid, client, store) for cid in dict.fromkeys(case_ids)]


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api-url", default="http://127.0.0.1:8766")
    p.add_argument("--data", type=Path, default=ROOT / "data" / "dev")
    p.add_argument("--db", type=Path, default=ROOT / ".state" / "app.sqlite")
    p.add_argument("--out", type=Path, default=ROOT / "submissions" / "results.json")
    p.add_argument("--cases", nargs="*", help="case IDs (default: every case the service lists)")
    p.add_argument("--submit-reviews", action="store_true",
                   help="send each draft to POST /v1/reviews; writes reviews.json next to --out")
    a = p.parse_args(argv)
    if a.db.name == "mock.sqlite":
        sys.exit("Refusing to use the mock service's state file; choose another --db path.")

    client = ToolClient(a.api_url)
    with SqliteKnowledgeStore(a.db) as store:
        try:
            ingest(a.data, store, a.api_url)
            case_ids = a.cases or [c["case_id"] for c in client.list_cases()]
        except (IngestError, OSError, ServiceError) as exc:
            sys.exit(f"Cannot start the run: {exc}")
        runs = run_cases(case_ids, client, store)

    packets = [r.packet for r in runs]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(packets, indent=2, ensure_ascii=False) + "\n")
    for r in runs:
        attempts = {t: res.attempts for t, res in r.tool_results.items()}
        print(f"{r.packet['case_id']}: {r.packet['routing']:<23} {r.seconds * 1000:7.1f} ms  "
              f"attempts={attempts}")
    print(f"Wrote {len(packets)} packets to {a.out}")

    if a.submit_reviews:
        reviews = []
        for packet in packets:
            try:
                body = client.submit_review(packet["case_id"], packet)
                reviews.append({"case_id": packet["case_id"], **{k: body.get(k) for k in
                                ("review_id", "status", "draft_hash")}})
            except ServiceError as exc:
                reviews.append({"case_id": packet["case_id"], "error": exc.error})
        path = a.out.parent / "reviews.json"
        path.write_text(json.dumps(reviews, indent=2) + "\n")
        print(f"Submitted {sum('review_id' in r for r in reviews)} drafts for human review; see {path}")


if __name__ == "__main__":
    main()
