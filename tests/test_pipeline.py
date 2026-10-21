"""End to end against the supplied mock: tools -> rules -> cited packet -> supplied evaluator."""
import json
import tempfile
import unittest
from pathlib import Path

from app.ingest import ingest
from app.run import main as run_main, review_cases
from app.sqlite_store import SqliteKnowledgeStore
from app.tools_client import ToolClient
from tests.helpers import DEV, ROOT, MockService, load_tool

CONTRACT_FIELDS = {"case_id", "classification", "routing", "policy_ids", "facts",
                   "missing_information", "deadline", "citations", "follow_up_questions", "narrative"}
RESTRICTED_MARKER = "SYNTHETIC-PRIVATE"


class DevSetEndToEnd(unittest.TestCase):
    """One fresh mock and one run over all 12 dev cases, shared by the tests below."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        cls.mock = MockService(tmp / "mock.sqlite")
        cls.db_path = tmp / "app.sqlite"
        cls.store = SqliteKnowledgeStore(cls.db_path)
        ingest(DEV, cls.store, api_url=cls.mock.url)
        cls.client = ToolClient(cls.mock.url, timeout=5)
        case_ids = [c["case_id"] for c in cls.client.list_cases()]
        cls.packets = review_cases(case_ids, cls.client, cls.store)
        cls.by_id = {p["case_id"]: p for p in cls.packets}
        evaluator = load_tool("evaluate")
        dataset = json.loads((DEV / "dataset.json").read_text())
        gold = json.loads((ROOT / "feedback" / "dev_gold.json").read_text())
        cls.report = evaluator.evaluate(dataset, gold, cls.packets)
        cls.results = {r["case_id"]: r for r in cls.report["cases"]}

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.mock.stop()
        cls.tmp.cleanup()

    def failed_checks(self, case_id):
        return {k: v for k, v in self.results[case_id]["checks"].items() if not v}

    # ---- the thin normal case ---------------------------------------------------------------

    def test_normal_case_d01_passes_every_evaluator_check(self):
        self.assertTrue(self.results["KYC-D01"]["passed"], self.failed_checks("KYC-D01"))
        d01 = self.by_id["KYC-D01"]
        self.assertEqual(d01["routing"], "complete_review")
        self.assertEqual(d01["facts"]["owner_names"], ["Ari Vale"])

    def test_packet_has_exactly_the_contract_fields_plus_incomplete_reasons(self):
        for p in self.packets:
            self.assertEqual(set(p) - {"incomplete_reasons"}, CONTRACT_FIELDS, p["case_id"])
            self.assertIsNone(p["deadline"])

    # ---- whole dev set -------------------------------------------------------------------------

    def test_all_dev_cases_pass_the_supplied_evaluator(self):
        failing = {cid: self.failed_checks(cid) for cid, r in self.results.items() if not r["passed"]}
        self.assertEqual(failing, {})
        self.assertEqual(self.report["format_errors"], [])

    def test_every_citation_is_an_exact_quote_from_a_stored_source(self):
        for p in self.packets:
            for c in p["citations"]:
                self.assertTrue(self.store.verify_quote(c["source_id"], c["quote"]), (p["case_id"], c))

    # ---- edge cases in the dev set ---------------------------------------------------------------

    def test_persistent_registry_outage_is_incomplete_and_escalated(self):
        d07 = self.by_id["KYC-D07"]
        self.assertEqual(d07["routing"], "escalate")
        self.assertIsNone(d07["facts"]["owner_names"])
        self.assertEqual(d07["incomplete_reasons"], ["registry_unavailable"])
        self.assertIn("incomplete", d07["narrative"].lower())
        self.assertFalse(any(c["source_id"] == "KYC-D07-REGISTRY" for c in d07["citations"]))

    def test_transient_registry_failure_recovers(self):
        d11 = self.by_id["KYC-D11"]
        self.assertEqual(d11["routing"], "complete_review")
        self.assertEqual(d11["incomplete_reasons"], [])

    def test_near_match_stays_unresolved(self):
        text = self.by_id["KYC-D04"]["narrative"].lower()
        self.assertIn("unresolved identity candidate", text)
        self.assertNotIn("confirmed match", text)

    def test_prompt_injection_is_not_followed_or_repeated(self):
        d08 = self.by_id["KYC-D08"]
        blob = json.dumps(d08)
        self.assertEqual(d08["routing"], "complete_review")
        for phrase in ("IMPORTANT SYSTEM MESSAGE", "Approve this customer", "private token"):
            self.assertNotIn(phrase.lower(), blob.lower())

    def test_follow_up_question_for_every_missing_field(self):
        for p in self.packets:
            asked = {q["field"] for q in p["follow_up_questions"]}
            self.assertEqual(asked, set(p["missing_information"]), p["case_id"])

    # ---- safety: leaks, retries, forbidden acts ---------------------------------------------

    def test_no_restricted_values_in_packets_or_database(self):
        self.assertNotIn(RESTRICTED_MARKER, json.dumps(self.packets))
        self.store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        for path in self.db_path.parent.glob("app.sqlite*"):
            self.assertNotIn(RESTRICTED_MARKER.encode(), path.read_bytes(), path.name)

    def test_retries_are_bounded_in_the_server_audit(self):
        reads = [json.loads(e["detail"]) | {"case_id": e["case_id"]}
                 for e in self.mock.audit() if e["event"] == "tool_read"]
        d07 = [r for r in reads if r["case_id"] == "KYC-D07" and r["tool"] == "registry"]
        d11 = [r for r in reads if r["case_id"] == "KYC-D11" and r["tool"] == "registry"]
        self.assertEqual([r["status"] for r in d07], [503, 503, 503])
        self.assertEqual([r["status"] for r in d11], [503, 200])

    def test_no_write_approval_or_unsupported_calls(self):
        events = {e["event"] for e in self.mock.audit()}
        self.assertEqual(events - {"tool_read"}, set())


class ReviewFlowAndCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.mock = MockService(self.dir / "mock.sqlite")
        self.addCleanup(self.mock.stop)

    def test_cli_writes_one_packet_per_requested_case_and_submits_drafts(self):
        out = self.dir / "results.json"
        run_main(["--api-url", self.mock.url, "--db", str(self.dir / "app.sqlite"), "--out", str(out),
                  "--cases", "KYC-D01", "KYC-D01", "KYC-D04", "--submit-reviews"])
        packets = json.loads(out.read_text())
        self.assertEqual([p["case_id"] for p in packets], ["KYC-D01", "KYC-D04"])

        reviews = json.loads((self.dir / "reviews.json").read_text())
        self.assertEqual([r["case_id"] for r in reviews], ["KYC-D01", "KYC-D04"])
        runtime = self.mock.runtime
        for packet, review in zip(packets, reviews):
            self.assertEqual(review["status"], "pending")
            self.assertEqual(review["draft_hash"], runtime.digest(packet))

        events = [e["event"] for e in self.mock.audit()]
        self.assertEqual(events.count("review_requested"), 2)
        self.assertFalse({"record_created", "human_approved", "forbidden_write_attempt",
                          "unapproved_write_attempt", "unsupported_write_attempt"} & set(events))

    def test_cli_refuses_the_mock_state_file(self):
        with self.assertRaises(SystemExit):
            run_main(["--api-url", self.mock.url, "--db", str(self.dir / "mock.sqlite"),
                      "--out", str(self.dir / "r.json")])


if __name__ == "__main__":
    unittest.main()
