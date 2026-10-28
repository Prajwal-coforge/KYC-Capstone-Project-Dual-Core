"""One cloud case at a time. Postgres only. The queue keeps the case otherwise.

Run this on the instance, where the AWS CLI can see the queue:

    python -m kyc_copilot.runner.batch_queue

A message is deleted only after the review exits 0. If the database URL is
missing, is not Postgres, or the review fails, the message stays on the queue.
This module never opens SQLite and never unsets KYC_DATABASE_URL.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

Run = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class CaseMessage:
    case_id: str
    receipt: str


def require_postgres_url(env: Mapping[str, str]) -> str:
    """The cloud batch has one ledger. A file is not a substitute."""
    url = (env.get("KYC_DATABASE_URL") or "").strip()
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return url
    raise ValueError(
        "Cloud batch requires a Postgres KYC_DATABASE_URL. The case stays on the queue."
    )


def parse_receive(payload: str) -> CaseMessage | None:
    """Read one SQS receive-message body. An empty receive means the queue is idle."""
    try:
        data = json.loads(payload or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Queue response is unreadable. The case stays on the queue.") from exc
    if not isinstance(data, dict):
        raise ValueError("Queue response is unreadable. The case stays on the queue.")
    messages = data.get("Messages") or []
    if not messages:
        return None
    message = messages[0]
    if not isinstance(message, dict):
        raise ValueError("Queue message is unreadable. The case stays on the queue.")
    receipt = message.get("ReceiptHandle")
    if not isinstance(receipt, str) or not receipt:
        raise ValueError("Queue message has no receipt. The case stays on the queue.")
    case_id = _case_id(message.get("Body"))
    if not case_id:
        raise ValueError("Queue message has no case id. The case stays on the queue.")
    return CaseMessage(case_id, receipt)


def _case_id(body: object) -> str:
    if not isinstance(body, str):
        return ""
    text = body.strip()
    if not text:
        return ""
    if not text.startswith("{"):
        return text
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return ""
    if isinstance(obj, dict) and isinstance(obj.get("case_id"), str):
        return obj["case_id"].strip()
    return ""


def review_command(case_id: str, env: Mapping[str, str]) -> list[str]:
    """The image command overrides the mock. The database URL is passed by name, not value."""
    api = (env.get("KYC_API_URL") or "http://127.0.0.1:8766").strip()
    review = ["python", "-m", "kyc_copilot", "--cases", case_id, "--api-url", api]
    image = (env.get("KYC_IMAGE") or "").strip()
    out = (env.get("KYC_OUT_DIR") or "").strip()
    if out:
        review.extend(["--out", "/out/results.json" if image else f"{out}/results.json"])
    if not image:
        return [sys.executable, *review[1:]]
    command = ["docker", "run", "--rm"]
    network = (env.get("KYC_DOCKER_NETWORK") or "").strip()
    run_user = (env.get("KYC_RUN_USER") or "").strip()
    if network:
        command.extend(["--network", network])
    if run_user:
        command.extend(["--user", run_user])
    command.extend(["-e", "KYC_DATABASE_URL", "-e", "KYC_API_URL"])
    if out:
        command.extend(["-v", f"{out}:/out"])
    command.append(image)
    command.extend(review)
    return command


def run_once(env: Mapping[str, str], run: Run = subprocess.run) -> int:
    """Receive one case. Delete it only when the Postgres review exits 0."""
    try:
        require_postgres_url(env)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    queue_url = (env.get("KYC_QUEUE_URL") or "").strip()
    if not queue_url:
        print("Cloud batch requires KYC_QUEUE_URL. The case stays on the queue.", file=sys.stderr)
        return 2
    region = (env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or "us-east-1").strip()
    received = run(
        _receive_args(queue_url, region),
        check=False,
        capture_output=True,
        text=True,
    )
    if received.returncode != 0:
        print("Could not read the queue. The case stays on the queue.", file=sys.stderr)
        return 1
    try:
        message = parse_receive(received.stdout)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    if message is None:
        return 3
    reviewed = run(review_command(message.case_id, env), check=False)
    if reviewed.returncode != 0:
        print("Review did not finish. The case stays on the queue.", file=sys.stderr)
        return 1
    if _copy_outputs(message.case_id, env, region, run) != 0:
        return 1
    deleted = run(_delete_args(queue_url, region, message.receipt), check=False)
    if deleted.returncode != 0:
        print(
            "The review finished but the queue message could not be deleted. It may run again.",
            file=sys.stderr,
        )
        return 1
    return 0


def _copy_outputs(case_id: str, env: Mapping[str, str], region: str, run: Run) -> int:
    """Copy the packet and trace after a good review. A missed copy leaves the case queued."""
    out = (env.get("KYC_OUT_DIR") or "").strip()
    packet = (env.get("KYC_PACKET_BUCKET") or "").strip()
    trace = (env.get("KYC_TRACE_BUCKET") or "").strip()
    if not out and not packet and not trace:
        return 0
    if not (out and packet and trace) or not _safe_case_id(case_id):
        print("Packet copy is incomplete. The case stays on the queue.", file=sys.stderr)
        return 1
    copies = (
        [
            "aws",
            "s3",
            "cp",
            f"{out}/results.json",
            f"s3://{packet}/cases/{case_id}/results.json",
            "--region",
            region,
        ],
        [
            "aws",
            "s3",
            "cp",
            f"{out}/trace.jsonl",
            f"s3://{trace}/cases/{case_id}/trace.jsonl",
            "--region",
            region,
        ],
    )
    for args in copies:
        copied = run(args, check=False)
        if copied.returncode != 0:
            print("The packet was not copied. The case stays on the queue.", file=sys.stderr)
            return 1
    return 0


def _safe_case_id(case_id: str) -> bool:
    return bool(case_id) and "/" not in case_id and "\\" not in case_id and ".." not in case_id


def _receive_args(queue_url: str, region: str) -> list[str]:
    return [
        "aws",
        "sqs",
        "receive-message",
        "--queue-url",
        queue_url,
        "--max-number-of-messages",
        "1",
        "--wait-time-seconds",
        "0",
        "--visibility-timeout",
        "300",
        "--region",
        region,
        "--output",
        "json",
    ]


def _delete_args(queue_url: str, region: str, receipt: str) -> list[str]:
    return [
        "aws",
        "sqs",
        "delete-message",
        "--queue-url",
        queue_url,
        "--receipt-handle",
        receipt,
        "--region",
        region,
    ]


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    return run_once(os.environ)


if __name__ == "__main__":
    raise SystemExit(main())
