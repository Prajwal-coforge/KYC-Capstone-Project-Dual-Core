"""Branches the dev-set replay does not reach, plus the three open eval rows."""

from __future__ import annotations

import io
import json
import os
import runpy
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from kyc_copilot.adapters.sqlite_store import SqliteKnowledgeStore
from kyc_copilot.adapters.tools_client import ServiceError, ToolClient
from kyc_copilot.contracts.address import compare_addresses, normalize_address
from kyc_copilot.contracts.interfaces import StatutoryRule
from kyc_copilot.contracts.models import (
    TRUSTED,
    CaseEvidence,
    Document,
    ParsedFile,
    Policy,
    Source,
    ToolResult,
)
from kyc_copilot.domain.packet import (
    _append_conflict_document_citations,
    _case_doc,
    _field_quote,
    _follow_up,
    _line,
    build_packet,
)
from kyc_copilot.domain.rules import (
    _combine_address_checks,
    _owner_names,
    _scratch,
    decide,
)
from kyc_copilot.ingestion.ingest import (
    IngestError,
    apply_case_links,
    discover,
    load_policy_manifest,
)
from kyc_copilot.ingestion.parsing import parse_file
from kyc_copilot.narrative.narrator import TemplateNarrator
from kyc_copilot.observability.tracing import metrics
from kyc_copilot.runner import ingest as ingest_runner
from kyc_copilot.runner.cli import load_review_ledger, main, submit_drafts
from kyc_copilot.runner.ingest import _repo_root
from kyc_copilot.runner.ingest import main as ingest_main
from kyc_copilot.runner.pipeline import gather_evidence
from tests.helpers import DEV, MockService
from tests.test_narrative import _decision, _evidence
from tests.test_rules import evidence, registry


def _policy_text(threshold: str, start: str = "2026-01-01", end: str = "2026-12-31") -> str:
    return (
        "# Policy\n\n"
        "Source ID: KYC-POLICY-EDGE\n\n"
        "Entity type: limited_company\n"
        f"Jurisdiction: Alder\n"
        f"Effective from: {start}\n"
        f"Effective through: {end}\n"
        f"EDD monthly threshold: {threshold}\n"
    )


class MetricAndRuleEdges(unittest.TestCase):
    def test_empty_window_has_no_p95(self):
        summary = metrics([])
        self.assertIsNone(summary["p95_ms"])
        self.assertEqual(summary["success_rate"], 1.0)
        self.assertFalse(summary["alert"])

    def test_scratch_outside_decide_is_refused(self):
        with self.assertRaises(RuntimeError):
            _scratch()

    def test_registry_owners_that_are_not_a_list_are_null(self):
        self.assertIsNone(_owner_names({"owners": "none"}))

    def test_address_combination_fails_closed(self):
        self.assertEqual(_combine_address_checks([]), "unknown")
        self.assertEqual(_combine_address_checks(["same", "unknown"]), "unknown")

    def test_unreadable_screening_and_a_single_address_do_not_complete(self):
        store = SqliteKnowledgeStore(":memory:")
        self.addCleanup(store.close)
        from kyc_copilot.runner.ingest import ingest

        ingest(DEV, store)
        ev = evidence(
            screening={"source_id": "C1-SCREENING", "matches": "nope", "pep_indicator": False},
            filing_address=None,
            customer={
                "source_id": "C1-CUSTOMER",
                "entity_id": "ENT-1",
                "entity_type": "limited_company",
                "jurisdiction": "Alder",
                "registered_address": "100 Orchard Walk, Alder",
            },
            registry={**registry(), "registered_address": ""},
        )
        decision = decide(ev, store.find_policies)
        self.assertIn("screening_unreadable", decision.reasons)
        self.assertEqual(decision.address_check, "unknown")
        self.assertNotIn("address_explanation", decision.missing_information)
        self.assertEqual(decision.routing, "escalate")

    def test_renamed_case_id_still_completes(self):
        store = SqliteKnowledgeStore(":memory:")
        self.addCleanup(store.close)
        from kyc_copilot.runner.ingest import ingest

        ingest(DEV, store)
        decision = decide(evidence(case_id="CASE-RENAMED-77"), store.find_policies)
        self.assertEqual(decision.routing, "complete_review")
        self.assertEqual(decision.facts["owner_names"], ["Ari Vale"])

    def test_normalize_address_expands_a_street_token(self):
        self.assertEqual(normalize_address("10 St"), "10 street")
        self.assertEqual(compare_addresses(None, "10 St"), "unknown")


class AbstractRuleIsNotRegistered(unittest.TestCase):
    def test_an_abstract_subclass_is_skipped_and_a_blank_id_is_refused(self):
        class Meta(type(StatutoryRule)):
            def __new__(mcls, name, bases, namespace, **kwargs):
                namespace["__abstractmethods__"] = frozenset({"apply"})
                return super().__new__(mcls, name, bases, namespace, **kwargs)

        before = set(StatutoryRule._registry)

        class Pending(StatutoryRule, metaclass=Meta):
            def apply(self, evidence: CaseEvidence) -> None:
                return None

        self.assertEqual(set(StatutoryRule._registry), before)

        with self.assertRaises(TypeError):

            class NoId(StatutoryRule):
                def apply(self, evidence: CaseEvidence) -> None:
                    return None


class StoreAndParseEdges(unittest.TestCase):
    def test_duplicate_source_ids_are_refused_and_a_bad_write_rolls_back(self):
        store = SqliteKnowledgeStore(":memory:")
        self.addCleanup(store.close)
        source = Source("S", "document", TRUSTED, None, "s.md", "text", "abc")
        item = ParsedFile(source)
        with self.assertRaises(ValueError):
            store.replace_all([item, item], {})
        bad = ParsedFile(Source("S", "nope", TRUSTED, None, "s.md", "text", "abc"))
        with self.assertRaises(sqlite3.IntegrityError):
            store.replace_all([bad], {"manifest_sha256": "1"})
        self.assertEqual(store.counts()["sources"], 0)
        self.assertIsNone(store.get_document("missing"))

    def test_all_policies_reads_what_ingest_stored(self):
        store = SqliteKnowledgeStore(":memory:")
        self.addCleanup(store.close)
        from kyc_copilot.runner.ingest import ingest

        ingest(DEV, store)
        policies = store.all_policies()
        self.assertGreaterEqual(len(policies), 1)
        self.assertIsInstance(policies[0], Policy)

    def test_manifest_directory_and_case_link_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(IngestError):
                discover(root)
            (root / "policies").mkdir()
            (root / "documents").mkdir()
            with self.assertRaises(IngestError):
                discover(root)
            manifest = root / "manifest.json"
            manifest.write_text("{}\n")
            with self.assertRaises(IngestError):
                load_policy_manifest(manifest)

        kept = ParsedFile(
            Source("DOC", "document", TRUSTED, None, "DOC.md", "body", "h"),
            document=Document("DOC", "OLD", "corporate", False, None, None),
        )
        updated, warnings = apply_case_links(
            [kept],
            {"CASE-1": {"documents": ["MISSING", "DOC"], "intake_source": "DOC"}},
        )
        self.assertEqual(updated[0].document.case_id, "CASE-1")
        self.assertTrue(updated[0].document.is_intake)
        self.assertTrue(any("MISSING" in w for w in warnings))
        orphan = ParsedFile(
            Source("ORPHAN", "document", TRUSTED, None, "ORPHAN.md", "body", "h"),
            document=Document("ORPHAN", "OLD", "corporate", False, None, None),
        )
        _, more = apply_case_links([orphan], {})
        self.assertIn("ORPHAN: document file is not listed by any case in the service", more)

    def test_parse_edges_for_threshold_window_source_id_and_final_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            floated = root / "KYC-POLICY-EDGE.md"
            floated.write_text(_policy_text("1.5"))
            parsed = parse_file(floated, "policies")
            self.assertEqual(parsed.policy.edd_threshold, 1.5)

            bad_number = root / "KYC-POLICY-BAD.md"
            bad_number.write_text(_policy_text("many"))
            with self.assertRaises(IngestError):
                parse_file(bad_number, "policies")

            reversed_window = root / "KYC-POLICY-REV.md"
            reversed_window.write_text(_policy_text("10", "2026-12-31", "2026-01-01"))
            with self.assertRaises(IngestError):
                parse_file(reversed_window, "policies")

            mismatched = root / "FILENAME.md"
            mismatched.write_text("Source ID: HEADER-ID\n\nBody\n")
            parsed = parse_file(mismatched, "documents")
            self.assertEqual(parsed.source.source_id, "HEADER-ID")
            self.assertTrue(any("differs from filename" in w for w in parsed.warnings))

            tail = root / "TAIL.md"
            tail.write_bytes(b"Source ID: TAIL\n\nOnly paragraph")
            parsed = parse_file(tail, "documents")
            self.assertEqual(parsed.chunks[-1].text, "Only paragraph")


class NarrativeAndCitationEdges(unittest.TestCase):
    def test_template_states_each_unresolved_condition(self):
        narrator = TemplateNarrator()
        notes = [
            narrator.write(
                _decision(reasons=["unsupported_scope"], routing="escalate"),
                _evidence(),
            ),
            narrator.write(
                _decision(reasons=["no_applicable_policy"], routing="escalate", policy=None),
                _evidence(),
            ),
            narrator.write(
                _decision(reasons=["ownership_unknown"], routing="escalate"),
                _evidence(registry={"ownership_depth": None}),
            ),
            narrator.write(
                _decision(
                    reasons=["screening_unrecognized_match"],
                    routing="escalate",
                    screening_matches=[{"candidate_name": "Ada", "match_type": "fuzzy"}],
                ),
                _evidence(),
            ),
            narrator.write(
                _decision(reasons=["screening_unreadable"], routing="escalate"),
                _evidence(),
            ),
            narrator.write(
                _decision(
                    reasons=["address_mismatch"],
                    routing="request_information",
                    address_check="unknown",
                    missing_information=["address_explanation"],
                ),
                _evidence(),
            ),
            narrator.write(
                _decision(
                    reasons=["transactions_unreadable"],
                    routing="escalate",
                    monthly_total=None,
                ),
                _evidence(),
            ),
        ]
        joined = "\n".join(notes)
        self.assertIn("outside the supported scope", joined)
        self.assertIn("could not settle on one policy", joined)
        self.assertIn("does not say how deep the ownership goes", joined)
        self.assertIn("match type I do not recognize", joined)
        self.assertIn("could not read the screening response", joined)
        self.assertIn("missing from the customer or registry", joined)
        self.assertIn("could not read the monthly transaction total", joined)

    def test_follow_up_without_a_filing_and_for_an_unknown_field(self):
        decision = _decision()
        ev = _evidence(
            customer={"registered_address": "1 High Street"},
            registry={"registered_address": "9 New Quay"},
            filing_address=None,
        )
        question = _follow_up("address_explanation", decision, ev)
        self.assertIn("9 New Quay", question)
        self.assertNotIn("corporate filing", question)
        other = _follow_up("tax_residency", decision, ev)
        self.assertIn("tax residency", other)

    def test_missing_quote_and_missing_source_do_not_invent_a_citation(self):
        self.assertIsNone(_line("no header here", "Review date:"))
        self.assertIsNone(_field_quote("Name: Ada", "Birth year:"))

        class Store:
            def __init__(self):
                self.docs = {
                    "ID": Document(
                        "ID",
                        "C1",
                        "identity",
                        False,
                        None,
                        None,
                        holder_name="Ada",
                        birth_year=1980,
                    )
                }
                self.sources = {
                    "ID": Source("ID", "document", TRUSTED, None, "ID.md", "Name: Ada\n", "h")
                }

            def case_documents(self, case_id):
                return [Source("ID", "document", TRUSTED, None, "ID.md", "Name: Ada\n", "h")]

            def get_document(self, source_id):
                return self.docs.get(source_id)

            def get_source(self, source_id):
                return self.sources.get(source_id)

        store = Store()
        self.assertIsNone(_case_doc(store, "C1", "corporate"))
        store.sources.pop("ID")
        self.assertIsNone(_case_doc(store, "C1", "identity"))

        store.sources["ID"] = Source("ID", "document", TRUSTED, None, "ID.md", "Name: Ada\n", "h")
        candidates: list[tuple[str, str, str | None]] = []
        _append_conflict_document_citations(
            candidates,
            _decision(reasons=["birth_year_conflict"]),
            _evidence(case_id="C1"),
            store,
        )
        self.assertEqual(candidates[0][0], "Identity birth year")
        self.assertIsNone(candidates[0][2])

    def test_shuffled_document_order_does_not_change_the_packet(self):
        store = SqliteKnowledgeStore(":memory:")
        self.addCleanup(store.close)
        from kyc_copilot.runner.ingest import ingest

        ingest(DEV, store)

        class Reversed:
            def __init__(self, inner):
                self.inner = inner

            def case_documents(self, case_id):
                return list(reversed(self.inner.case_documents(case_id)))

            def __getattr__(self, name):
                return getattr(self.inner, name)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        mock = MockService(Path(tmp.name) / "mock.sqlite")
        self.addCleanup(mock.stop)
        client = ToolClient(mock.url, timeout=5)
        from kyc_copilot.runner.cli import run_cases

        forward = run_cases(["KYC-D01"], client, store)[0].packet
        backward = run_cases(["KYC-D01"], client, Reversed(store))[0].packet
        self.assertEqual(forward, backward)


class CliEdges(unittest.TestCase):
    def test_unreadable_ledgers_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review_ledger.json"
            path.write_text("{")
            with self.assertRaises(ValueError):
                load_review_ledger(path)
            path.write_text("[]\n")
            with self.assertRaises(ValueError):
                load_review_ledger(path)
            packet = {
                "case_id": "C1",
                "facts": {"entity_id": "ENT-1", "review_date": "2026-10-01"},
            }
            key = "ENT-1|2026-10-01"
            path.write_text(json.dumps({key: []}))
            with self.assertRaises(ValueError):
                submit_drafts(_Client({}), [packet], path)
            from kyc_copilot.runner.cli import draft_hash

            digest = draft_hash(packet)
            path.write_text(json.dumps({key: {digest: {"draft_hash": "no", "review_id": "r"}}}))
            with self.assertRaises(ValueError):
                submit_drafts(_Client({}), [packet], path)

    def test_submit_records_a_service_error_and_a_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review_ledger.json"
            packet = {"case_id": "C1", "routing": "complete_review"}
            down = submit_drafts(_Client(error=ServiceError("down")), [packet], path)
            self.assertEqual(down[0]["error"], "down")
            mismatch = submit_drafts(
                _Client({"draft_hash": "nope", "review_id": "r1"}), [packet], path
            )
            self.assertEqual(mismatch[0]["error"], "draft_hash_mismatch")

    def test_cli_exits_when_ingest_cannot_start_and_when_the_ledger_is_bad(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out" / "results.json"
            with self.assertRaises(SystemExit) as caught:
                main(
                    [
                        "--api-url",
                        "http://127.0.0.1:9",
                        "--data",
                        str(root / "missing"),
                        "--db",
                        str(root / "app.sqlite"),
                        "--out",
                        str(out),
                    ]
                )
            self.assertIn("Cannot start the run", str(caught.exception))

            mock_dir = tempfile.TemporaryDirectory()
            self.addCleanup(mock_dir.cleanup)
            mock = MockService(Path(mock_dir.name) / "mock.sqlite")
            self.addCleanup(mock.stop)
            out.parent.mkdir(parents=True)
            (out.parent / "review_ledger.json").write_text("[]\n")
            with self.assertRaises(SystemExit) as caught:
                main(
                    [
                        "--api-url",
                        mock.url,
                        "--db",
                        str(root / "app.sqlite"),
                        "--out",
                        str(out),
                        "--cases",
                        "KYC-D01",
                        "--submit-reviews",
                    ]
                )
            self.assertIn("unreadable", str(caught.exception))

    def test_ingest_cli_and_module_entries(self):
        env = {key: value for key, value in os.environ.items() if key != "KYC_DATABASE_URL"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            db = Path(tmp) / "app.sqlite"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                ingest_main(["--data", str(DEV), "--db", str(db)])
            self.assertIn("manifest_sha256", json.loads(buffer.getvalue()))
            with self.assertRaises(SystemExit):
                ingest_main(["--db", str(Path(tmp) / "mock.sqlite")])
            with self.assertRaises(SystemExit) as caught:
                ingest_main(["--data", str(Path(tmp) / "missing"), "--db", str(db)])
            self.assertIn("Ingestion failed", str(caught.exception))

        with patch("sys.argv", ["kyc_copilot", "--help"]):
            with self.assertRaises(SystemExit) as caught:
                runpy.run_module("kyc_copilot", run_name="__main__")
            self.assertEqual(caught.exception.code, 0)
        with patch("sys.argv", ["kyc_copilot.runner.cli", "--help"]):
            with self.assertRaises(SystemExit) as caught:
                runpy.run_module("kyc_copilot.runner.cli", run_name="__main__")
            self.assertEqual(caught.exception.code, 0)
        with patch("sys.argv", ["kyc_copilot.runner.ingest", "--help"]):
            with self.assertRaises(SystemExit) as caught:
                runpy.run_module("kyc_copilot.runner.ingest", run_name="__main__")
            self.assertEqual(caught.exception.code, 0)

    def test_repo_root_falls_back_when_the_markers_are_absent(self):
        here = Path(ingest_runner.__file__).resolve()
        with patch("kyc_copilot.runner.ingest.Path.is_dir", return_value=False):
            root = _repo_root()
        self.assertEqual(root, here.parents[3])

    def test_a_tool_that_claims_a_policy_id_is_dropped(self):
        class Row:
            source_id = "X"

        class Store:
            def case_documents(self, case_id):
                return [Row()]

            def get_document(self, source_id):
                return None

            def save_tool_evidence(self, *args):
                raise ValueError("already ingested")

        class Client:
            def reset_circuits(self):
                return None

            def fetch(self, case_id, tool):
                return ToolResult(tool, True, {"source_id": "KYC-SCOPE-01"}, 1, None)

        evidence, _results, intake_id = gather_evidence("C1", Client(), Store())
        self.assertIsNone(intake_id)
        self.assertIn("customer", evidence.failed_tools)


class _Client:
    def __init__(self, body=None, error=None):
        self.body = body or {}
        self.error = error

    def submit_review(self, case_id, packet):
        if self.error:
            raise self.error
        return self.body


class PacketBuildUsesTheNarrator(unittest.TestCase):
    def test_unknown_missing_field_is_named_in_the_question(self):
        store = SqliteKnowledgeStore(":memory:")
        self.addCleanup(store.close)
        packet = build_packet(
            _decision(
                routing="request_information",
                missing_information=["tax_residency"],
                reasons=["identity_document_missing"],
            ),
            _evidence(),
            None,
            store,
            TemplateNarrator(),
        )
        self.assertEqual(packet["follow_up_questions"][0]["field"], "tax_residency")
