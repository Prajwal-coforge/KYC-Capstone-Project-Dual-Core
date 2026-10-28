"""Thirty synthetic discrepancy cases end to end: documents and tools -> packet -> evaluator.

test_synthetic_edges.py decides hand-built evidence. These cases go through everything the
assessor exercises: Markdown parsing, the supplied mock over HTTP (with faults), retries,
rules, citations and the supplied evaluator. Gold comes from tests/synthetic_fixture.py.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kyc_copilot.adapters.sqlite_store import SqliteKnowledgeStore
from kyc_copilot.adapters.tools_client import ToolClient
from kyc_copilot.runner.cli import run_cases
from kyc_copilot.runner.ingest import ingest
from tests import synthetic_fixture
from tests.helpers import MockService, load_tool

CONTRACT_FIELDS = {
    "case_id",
    "classification",
    "routing",
    "policy_ids",
    "facts",
    "missing_information",
    "deadline",
    "citations",
    "follow_up_questions",
    "narrative",
}
SEVERITY = {
    "complete_review": 0,
    "enhanced_due_diligence": 1,
    "request_information": 2,
    "escalate": 3,
}


def _run(data: Path, state: Path, db: Path):
    """Fresh mock state and store, ingest, review every listed case. Returns (runs, audit)."""
    mock = MockService(state, data)
    store = SqliteKnowledgeStore(db)
    try:
        ingest(data, store, api_url=mock.url)
        client = ToolClient(mock.url, timeout=5, backoff_seconds=0)
        case_ids = [c["case_id"] for c in client.list_cases()]
        return run_cases(case_ids, client, store), mock.audit()
    finally:
        store.close()
        mock.stop()


class SyntheticEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        cls.data, gold_path = synthetic_fixture.write(tmp / "fixture")
        cls.gold = json.loads(gold_path.read_text())
        cls.dataset = json.loads((cls.data / "dataset.json").read_text())
        cls.db_path = tmp / "app.sqlite"
        cls.runs, cls.audit = _run(cls.data, tmp / "mock.sqlite", cls.db_path)
        cls.packets = [r.packet for r in cls.runs]
        cls.by_id = {r.packet["case_id"]: r for r in cls.runs}
        report = load_tool("evaluate").evaluate(cls.dataset, cls.gold, cls.packets)
        cls.report = report
        cls.results = {r["case_id"]: r for r in report["cases"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def packet(self, n: int) -> dict:
        return self.by_id[f"KYC-S{n:02d}"].packet

    # ---- fixture -----------------------------------------------------------------------------

    def test_fixture_has_thirty_cases_and_its_sources_match_the_files(self):
        # tools/validate_package.py makes these checks with read_text(), which turns the
        # CRLF case (KYC-S20) into LF. Compare exact bytes instead; citations quote them.
        self.assertEqual(len(self.gold), 30)
        sources = self.dataset["sources"]
        for case in self.dataset["cases"]:
            self.assertIn(case["intake_source"], case["documents"])
            for sid in case["documents"]:
                raw = (self.data / "documents" / f"{sid}.md").read_bytes().decode("utf-8")
                self.assertEqual(raw, sources[sid], sid)
            for payload in case["tools"].values():
                self.assertEqual(json.dumps(payload, sort_keys=True), sources[payload["source_id"]])
            self.assertTrue(set(case["faults"]) <= set(case["tools"]), case["case_id"])
        for p in (self.data / "policies").glob("*.md"):
            self.assertEqual(p.read_bytes().decode("utf-8"), sources[p.stem], p.stem)

    # ---- graded output -----------------------------------------------------------------------

    def test_every_case_passes_the_supplied_evaluator(self):
        self.assertEqual(self.report["format_errors"], [])
        failing = {
            cid: {
                "label": self.gold[cid]["rationale"],
                "failed": [k for k, ok in r["checks"].items() if not ok],
                "got": {
                    k: self.by_id[cid].packet.get(k)
                    for k in ("routing", "policy_ids", "facts", "missing_information")
                },
            }
            for cid, r in self.results.items()
            if not r["passed"]
        }
        self.assertEqual(failing, {}, json.dumps(failing, indent=2))

    def test_no_case_is_routed_less_severely_than_gold(self):
        # ASSUMPTIONS.md section 4: going faster must not miss an escalation.
        softer = {
            cid: (self.by_id[cid].packet["routing"], g["routing"][0])
            for cid, g in self.gold.items()
            if SEVERITY[self.by_id[cid].packet["routing"]] < SEVERITY[g["routing"][0]]
        }
        self.assertEqual(softer, {})

    def test_packets_have_the_contract_fields_and_a_question_per_missing_field(self):
        for p in self.packets:
            with self.subTest(p["case_id"]):
                self.assertEqual(set(p) - {"incomplete_reasons"}, CONTRACT_FIELDS)
                self.assertIsNone(p["deadline"])
                asked = [q["field"] for q in p["follow_up_questions"]]
                self.assertEqual(asked, p["missing_information"])

    # ---- tools: retries and outages ----------------------------------------------------------

    def test_the_mock_never_sees_more_than_three_reads_per_case_and_tool(self):
        reads: dict[tuple[str, str], int] = {}
        for row in self.audit:
            self.assertEqual(row["event"], "tool_read")  # no writes, no review submissions
            tool = json.loads(row["detail"])["tool"]
            reads[(row["case_id"], tool)] = reads.get((row["case_id"], tool), 0) + 1
        self.assertLessEqual(max(reads.values()), 3)
        self.assertEqual(reads[("KYC-S21", "screening")], 2)
        self.assertEqual(reads[("KYC-S21", "transaction-summary")], 3)
        self.assertEqual(reads[("KYC-S22", "screening")], 3)

    def test_transient_faults_recover_without_changing_the_route(self):
        run = self.by_id["KYC-S21"]
        self.assertEqual(run.tool_results["screening"].attempts, 2)
        self.assertEqual(run.tool_results["transaction-summary"].attempts, 3)
        self.assertEqual(run.packet["incomplete_reasons"], [])

    def test_a_failed_tool_is_named_and_never_cited(self):
        expected = {
            22: ("screening_unavailable", "KYC-S22-SCREENING"),
            23: ("transactions_unavailable", "KYC-S23-TRANSACTIONS"),
            24: ("customer_unavailable", "KYC-S24-CUSTOMER"),
            25: ("registry_unavailable", "KYC-S25-REGISTRY"),
        }
        for n, (reason, source) in expected.items():
            with self.subTest(n=n):
                p = self.packet(n)
                self.assertEqual(p["incomplete_reasons"], [reason])
                self.assertNotIn(source, {c["source_id"] for c in p["citations"]})
                self.assertIn("incomplete", p["narrative"].lower())

    def test_an_outage_outranks_the_pep_flag(self):
        p = self.packet(23)
        self.assertEqual(p["routing"], "escalate")
        self.assertIn("pep_indicator", self.by_id["KYC-S23"].decision.reasons)

    def test_every_escalation_says_why_in_the_narrative(self):
        why = {
            3: "corporate filing gives 'Birch'",
            4: "declared owner in the corporate filing 'Tamsin Greaves'",
            5: "identity document holder 'Ivo Brandt'",
            6: "birth year 1990",
            7: "entity reference 'ENT-S70'",
            10: "two different values for the same field",
            11: "not a valid calendar date",
            12: "corporate filing is missing",
            13: "more than one identity document",
            14: "type I do not recognize",
            16: "identity document is missing",
            17: "heading does not match",
            18: "document is empty",
            22: "screening service was unavailable",
            26: "match type I do not recognize",
            29: "could not settle on one policy",
            30: "outside the supported scope",
        }
        for n, text in why.items():
            with self.subTest(n=n):
                self.assertIn(text, self.packet(n)["narrative"])

    # ---- untrusted text and restricted values ------------------------------------------------

    def test_an_instruction_in_a_filing_does_not_change_the_route_or_reach_the_narrative(self):
        p = self.packet(15)
        self.assertEqual(p["routing"], "enhanced_due_diligence")
        self.assertNotIn("ignore previous instructions", p["narrative"].lower())
        flagged = [c for c in p["citations"] if c["claim"].startswith("Untrusted instruction")]
        self.assertEqual([c["source_id"] for c in flagged], ["KYC-S15-CORPORATE"])

    def test_restricted_values_reach_neither_the_output_nor_the_store(self):
        output = json.dumps(self.packets, ensure_ascii=False)
        self.assertNotIn("private_token", output)
        self.assertNotIn("SYNTHETIC-PRIVATE", output)
        self.assertNotIn(b"SYNTHETIC-PRIVATE", self.db_path.read_bytes())

    def test_conflicts_cite_every_contradicting_source(self):
        pairs = {
            3: ("KYC-S03-CUSTOMER", "KYC-S03-CORPORATE"),
            4: ("KYC-S04-REGISTRY", "KYC-S04-CORPORATE"),
            5: ("KYC-S05-REGISTRY", "KYC-S05-IDENTITY"),
            6: ("KYC-S06-CUSTOMER", "KYC-S06-IDENTITY"),
            7: ("KYC-S07-CUSTOMER", "KYC-S07-INTAKE"),
            30: ("KYC-S30-CUSTOMER", "KYC-S30-REGISTRY"),
        }
        for n, sources in pairs.items():
            with self.subTest(n=n):
                cited = {c["source_id"] for c in self.packet(n)["citations"]}
                self.assertTrue(set(sources) <= cited, cited)

    # ---- repeatability -----------------------------------------------------------------------

    def test_a_fresh_run_produces_identical_packets(self):
        with tempfile.TemporaryDirectory() as again:
            again = Path(again)
            runs, _ = _run(self.data, again / "mock.sqlite", again / "app.sqlite")
        self.assertEqual([r.packet for r in runs], self.packets)


if __name__ == "__main__":
    unittest.main()
