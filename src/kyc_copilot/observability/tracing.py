"""Append-only JSONL traces and the two SLO metrics.

One line per tool call and one line per decision. Payloads, documents, and
restricted keys such as private_token are never written.
"""

from __future__ import annotations

import json
from pathlib import Path

from kyc_copilot.contracts.models import CaseRun
from kyc_copilot.contracts.redaction import redact

SLO_MS = 15_000
WINDOW = 20


def trace_events(run: CaseRun) -> list[dict]:
    """Tool-call lines, then the decision line, for one case."""
    case_id = run.packet["case_id"]
    events = [
        {
            "event": "tool_call",
            "case_id": case_id,
            "tool": tool,
            "attempt": result.attempts,
            "status": "ok" if result.ok else (result.error or "error"),
            "latency_ms": round(result.seconds * 1000, 1),
            "circuit": result.circuit,
        }
        for tool, result in run.tool_results.items()
    ]
    decision = run.decision
    events.append(
        {
            "event": "decision",
            "case_id": case_id,
            "routing": decision.routing,
            "classification": decision.classification,
            "reasons": list(decision.reasons),
            "incomplete_reasons": list(decision.incomplete_reasons),
            "missing_information": list(decision.missing_information),
            "policy_ids": list(decision.policy_ids),
            "latency_ms": round(run.seconds * 1000, 1),
        }
    )
    return events


def metrics(decision_events: list[dict]) -> dict:
    """Success rate and p95 time-to-packet over the last 20 decisions.

    A case succeeds when its packet was produced within the 15s SLO.
    Escalation is a success. Alert when success rate is under 95% or p95 exceeds 15s.
    """
    window = [e for e in decision_events if e.get("event") == "decision"][-WINDOW:]
    times = [float(e["latency_ms"]) for e in window]
    successes = sum(1 for t in times if t <= SLO_MS)
    rate = (successes / len(times)) if times else 1.0
    p95 = _percentile(times, 0.95)
    reasons = []
    if times and rate < 0.95:
        reasons.append("success_rate_below_95")
    if p95 is not None and p95 > SLO_MS:
        reasons.append("p95_above_15s")
    return {
        "event": "metrics",
        "cases": len(times),
        "success_rate": round(rate, 4),
        "p95_ms": p95,
        "slo_ms": SLO_MS,
        "alert": bool(reasons),
        "alert_reason": reasons or None,
    }


def _percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile; None when the window is empty."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, int(q * len(ordered) + 0.999999) - 1)
    return round(ordered[index], 1)


class JsonlTrace:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: dict) -> None:
        """Append one redacted JSONL event; never persist restricted keys."""
        clean = redact(event)
        line = json.dumps(clean, sort_keys=True, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def write_run(self, run: CaseRun) -> None:
        """Append tool-call and decision events for one finished case run."""
        for event in trace_events(run):
            self.write(event)
