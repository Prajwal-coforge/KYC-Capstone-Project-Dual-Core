"""Trace lines stay free of payloads and restricted values. Metrics page on the SLO."""

import json
import tempfile
import unittest
from pathlib import Path

from kyc_copilot.contracts.models import CaseRun, Decision, ToolResult
from kyc_copilot.observability.tracing import JsonlTrace, metrics, trace_events


def _run(routing="complete_review", seconds=0.01, result=None):
    result = result or ToolResult(
        "customer", True, {"source_id": "S", "private_token": "SECRET"}, 1, None, 0.004
    )
    decision = Decision(
        "limited_company",
        routing,
        ["ALDER-LTD-V2"],
        None,
        {},
        [],
        ["within_policy"],
        [],
        "same",
    )
    packet = {"case_id": "KYC-D01", "routing": routing, "narrative": "x" * 30}
    return CaseRun(packet, decision, {"customer": result}, seconds)


class TraceTests(unittest.TestCase):
    def test_tool_and_decision_lines_use_the_agreed_fields(self):
        events = trace_events(_run())
        tool, decision = events
        self.assertEqual(
            set(tool),
            {"event", "case_id", "tool", "attempt", "status", "latency_ms", "circuit"},
        )
        self.assertEqual(tool["status"], "ok")
        self.assertEqual(tool["attempt"], 1)
        self.assertEqual(
            set(decision),
            {
                "event",
                "case_id",
                "routing",
                "classification",
                "reasons",
                "incomplete_reasons",
                "missing_information",
                "policy_ids",
                "latency_ms",
            },
        )
        self.assertEqual(decision["reasons"], ["within_policy"])

    def test_trace_file_has_no_payload_or_private_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            sink = JsonlTrace(path)
            sink.write_run(
                _run(
                    result=ToolResult(
                        "registry",
                        False,
                        {"private_token": "SECRET", "note": "raw document text"},
                        3,
                        "upstream_timeout",
                        0.2,
                        "open",
                    )
                )
            )
            sink.write({"event": "tool_call", "private_token": "SECRET", "status": "ok"})
            text = path.read_text()
        self.assertNotIn("SECRET", text)
        self.assertNotIn("private_token", text)
        self.assertNotIn("raw document", text)
        rows = [json.loads(line) for line in text.splitlines()]
        self.assertEqual(rows[0]["status"], "upstream_timeout")
        self.assertEqual((rows[0]["attempt"], rows[0]["circuit"]), (3, "open"))

    def test_alert_when_success_rate_or_p95_breaches_the_slo(self):
        fast = [{"event": "decision", "latency_ms": 10.0} for _ in range(20)]
        self.assertFalse(metrics(fast)["alert"])
        self.assertEqual(metrics(fast)["success_rate"], 1.0)

        one_slow = [{"event": "decision", "latency_ms": 10.0} for _ in range(19)]
        one_slow.append({"event": "decision", "latency_ms": 16_000.0})
        # 19/20 is still 95%; p95 excludes the worst 5%
        self.assertFalse(metrics(one_slow)["alert"])

        slow = [{"event": "decision", "latency_ms": 10.0} for _ in range(18)]
        slow.extend({"event": "decision", "latency_ms": 16_000.0} for _ in range(2))
        page = metrics(slow)
        self.assertTrue(page["alert"])
        self.assertIn("p95_above_15s", page["alert_reason"])
        self.assertIn("success_rate_below_95", page["alert_reason"])
        self.assertLess(page["success_rate"], 0.95)

        older = [{"event": "decision", "latency_ms": 20_000.0} for _ in range(5)]
        recent = [{"event": "decision", "latency_ms": 10.0} for _ in range(20)]
        self.assertFalse(metrics(older + recent)["alert"])
        self.assertEqual(metrics(older + recent)["cases"], 20)


if __name__ == "__main__":
    unittest.main()
