"""Ingestion tests. Run: uv run --locked python -m unittest -v"""

import ast
import shutil
import sys
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path

from kyc_copilot.runner.ingest import ingest

from kyc_copilot.adapters.sqlite_store import SCHEMA_VERSION, SqliteKnowledgeStore
from kyc_copilot.ingestion.parsing import IngestError, chunk_paragraphs, parse_file

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "data" / "dev"
MANIFEST = ROOT / "contracts" / "policy_manifest.json"
INGESTION_SRC = ROOT / "src" / "kyc_copilot" / "ingestion"


class AdapterStoreSchemaTests(unittest.TestCase):
    """Cycle 2.2: SCHEMA_VERSION 3 persists ENG-01 Document columns."""

    def test_schema_version_is_3(self):
        self.assertEqual(SCHEMA_VERSION, 3)

    def test_corporate_and_identity_columns_round_trip(self):
        store = SqliteKnowledgeStore(":memory:")
        self.addCleanup(store.close)
        ingest(DEV, store)
        corporate = store.get_document("KYC-D01-CORPORATE")
        identity = store.get_document("KYC-D01-IDENTITY")
        missing = store.get_document("KYC-D02-IDENTITY")
        self.assertEqual(corporate.filing_jurisdiction, "Alder")
        self.assertEqual(corporate.declared_owner, "Ari Vale")
        self.assertEqual(corporate.filing_address, "100 Orchard Walk, Alder.")
        self.assertEqual(identity.holder_name, "Ari Vale")
        self.assertEqual(identity.birth_year, 1985)
        self.assertEqual(identity.document_reference, "SYN-ID-D01")
        self.assertFalse(identity.identity_not_supplied)
        self.assertTrue(missing.identity_not_supplied)


class DevDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = SqliteKnowledgeStore(":memory:")
        cls.report = ingest(DEV, cls.store)

    @classmethod
    def tearDownClass(cls):
        cls.store.close()

    def test_counts(self):
        # 4 policy versions + 1 procedure + 12 cases x 3 documents
        self.assertEqual(self.report["totals"]["sources"], 41)
        self.assertEqual(self.report["totals"]["policies"], 4)
        self.assertEqual(self.report["totals"]["documents"], 36)
        self.assertEqual(self.report["warnings"], [])

    def test_content_is_byte_exact_and_chunks_slice_it(self):
        for path in list((DEV / "policies").glob("*.md")) + list((DEV / "documents").glob("*.md")):
            src = self.store.get_source(path.stem)
            self.assertIsNotNone(src, path.stem)
            self.assertEqual(src.content, path.read_bytes().decode("utf-8"))
            for c in self.store.get_chunks(src.source_id):
                self.assertEqual(src.content[c.start_offset : c.end_offset], c.text)

    def test_policy_selected_by_review_date(self):
        cases = [
            ("limited_company", "Alder", "2026-10-01", "KYC-POLICY-ALDER-LTD-V2", 50000),
            ("limited_company", "Alder", "2026-09-01", "KYC-POLICY-ALDER-LTD-V2", 50000),
            ("limited_company", "Alder", "2026-08-31", "KYC-POLICY-ALDER-LTD-V1", 30000),
            ("limited_company", "Birch", "2026-10-01", "KYC-POLICY-BIRCH-LTD-V1", 40000),
            ("sole_proprietor", "Alder", "2026-10-01", "KYC-POLICY-ALDER-SOLE-V1", 25000),
        ]
        for entity, jurisdiction, day, expected_id, threshold in cases:
            found = self.store.find_policies(entity, jurisdiction, day)
            self.assertEqual(
                [p.source_id for p in found],
                [expected_id],
                (entity, jurisdiction, day),
            )
            self.assertEqual(found[0].edd_threshold, threshold)

    def test_unsupported_or_out_of_window_returns_no_policy(self):
        self.assertEqual(self.store.find_policies("sole_proprietor", "Birch", "2026-10-01"), [])
        self.assertEqual(self.store.find_policies("limited_company", "Alder", "2027-01-01"), [])
        self.assertEqual(
            self.store.find_policies("limited_company", "Alder", date(2025, 12, 31)),
            [],
        )

    def test_scope_procedure_is_stored_as_trusted_procedure(self):
        proc = self.store.get_procedure("KYC-SCOPE-01")
        self.assertIsNotNone(proc)
        self.assertEqual(proc.trust, "trusted")
        self.assertIsNone(self.store.get_procedure("KYC-POLICY-ALDER-LTD-V2"))

    def test_case_documents_intake_first_and_untrusted(self):
        docs = self.store.case_documents("KYC-D01")
        self.assertEqual(
            [d.source_id for d in docs], ["KYC-D01-INTAKE", "KYC-D01-CORPORATE", "KYC-D01-IDENTITY"]
        )
        self.assertTrue(all(d.trust == "untrusted" for d in docs))

    def test_intake_metadata(self):
        d01 = self.store.get_document("KYC-D01-INTAKE")
        self.assertEqual((d01.review_date, d01.entity_ref), (date(2026, 10, 1), "ENT-D01"))
        self.assertEqual(self.store.get_document("KYC-D06-INTAKE").review_date, date(2026, 8, 31))

    def test_intake_identity_status(self):
        self.assertEqual(self.store.get_document("KYC-D01-INTAKE").identity_status, "attached")
        self.assertEqual(self.store.get_document("KYC-D02-INTAKE").identity_status, "not supplied")
        self.assertIsNone(self.store.get_document("KYC-D01-CORPORATE").identity_status)

    def test_injection_text_is_stored_as_untrusted_data(self):
        src = self.store.get_source("KYC-D08-CORPORATE")
        self.assertIn("IMPORTANT SYSTEM MESSAGE", src.content)
        self.assertEqual(src.trust, "untrusted")

    def test_verify_quote(self):
        ok = "Supported matrix: limited_company in Alder or Birch; sole_proprietor in Alder only."
        self.assertTrue(self.store.verify_quote("KYC-SCOPE-01", ok))
        self.assertFalse(self.store.verify_quote("KYC-SCOPE-01", ok.lower()))
        self.assertFalse(self.store.verify_quote("KYC-SCOPE-01", "   "))
        self.assertFalse(self.store.verify_quote("NO-SUCH-SOURCE", "anything"))
        self.assertFalse(self.store.verify_quote("KYC-D01-INTAKE", ok))

    def test_rerun_is_idempotent(self):
        again = ingest(DEV, self.store)
        self.assertEqual((again["added"], again["updated"], again["removed"]), (0, 0, 0))
        self.assertEqual(again["unchanged"], 41)
        self.assertEqual(again["manifest_sha256"], self.report["manifest_sha256"])


class SyncBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = self.tmp / "data"
        shutil.copytree(DEV, self.data)
        self.store = SqliteKnowledgeStore(":memory:")
        self.addCleanup(self.store.close)

    def test_changed_and_removed_files_are_synced(self):
        ingest(self.data, self.store)
        (self.data / "documents" / "KYC-D12-IDENTITY.md").unlink()
        intake = self.data / "documents" / "KYC-D01-INTAKE.md"
        intake.write_text(intake.read_text() + "\nExtra line.\n")
        report = ingest(self.data, self.store)
        self.assertEqual((report["updated"], report["removed"]), (1, 1))
        self.assertIsNone(self.store.get_source("KYC-D12-IDENTITY"))
        self.assertIn("Extra line.", self.store.get_source("KYC-D01-INTAKE").content)

    def test_malformed_policy_stores_nothing_and_keeps_previous_data(self):
        ingest(self.data, self.store)
        before = self.store.counts()
        bad = self.data / "policies" / "KYC-POLICY-ALDER-LTD-V2.md"
        bad.write_text(
            bad.read_text().replace(
                "Effective from: 2026-09-01",
                "Effective from: someday",
            )
        )
        with self.assertRaises(IngestError):
            ingest(self.data, self.store)
        self.assertEqual(self.store.counts(), before)

    def test_missing_policy_field_is_rejected(self):
        bad = self.data / "policies" / "KYC-POLICY-BIRCH-LTD-V1.md"
        bad.write_text(bad.read_text().replace("EDD monthly threshold: 40000\n", ""))
        with self.assertRaises(IngestError):
            ingest(self.data, self.store)

    def test_overlapping_policy_windows_warn(self):
        # Overlap detection is pure; a known-policy byte change also fails PolicyManifestGuard
        # on ingest (ENG-01), so exercise the warning helper on discovered files directly.
        from kyc_copilot.ingestion.ingest import discover, policy_overlap_warnings

        v2 = self.data / "policies" / "KYC-POLICY-ALDER-LTD-V2.md"
        v2.write_text(
            v2.read_text().replace(
                "Effective from: 2026-09-01",
                "Effective from: 2026-08-01",
            )
        )
        warnings = policy_overlap_warnings(discover(self.data))
        self.assertTrue(any("overlapping" in w for w in warnings))
        with self.assertRaises(IngestError):
            ingest(self.data, self.store)

    def test_crlf_text_is_preserved(self):
        path = self.data / "documents" / "KYC-D01-CORPORATE.md"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        ingest(self.data, self.store)
        self.assertIn("\r\n", self.store.get_source("KYC-D01-CORPORATE").content)
        for c in self.store.get_chunks("KYC-D01-CORPORATE"):
            self.assertNotIn("\r", c.text[-1:])


class ToolEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.store = SqliteKnowledgeStore(":memory:")
        self.addCleanup(self.store.close)
        ingest(DEV, self.store)

    def test_tool_evidence_is_quotable(self):
        self.store.save_tool_evidence(
            "KYC-D01",
            "transaction-summary",
            "KYC-D01-TRANSACTIONS",
            '{"monthly_total": 12000, "source_id": "KYC-D01-TRANSACTIONS"}',
        )
        self.assertTrue(self.store.verify_quote("KYC-D01-TRANSACTIONS", '"monthly_total": 12000'))
        self.assertEqual(self.store.get_source("KYC-D01-TRANSACTIONS").trust, "untrusted")

    def test_refetch_replaces_previous_evidence(self):
        for total in (1, 2):
            self.store.save_tool_evidence("C", "screening", "C-SCREENING", f'{{"n": {total}}}')
        self.assertTrue(self.store.verify_quote("C-SCREENING", '"n": 2'))
        self.assertFalse(self.store.verify_quote("C-SCREENING", '"n": 1'))

    def test_tool_cannot_overwrite_an_ingested_source(self):
        with self.assertRaises(ValueError):
            self.store.save_tool_evidence("KYC-D01", "customer", "KYC-SCOPE-01", "{}")
        self.assertIn("Supported matrix", self.store.get_source("KYC-SCOPE-01").content)

    def test_reingest_keeps_evidence_but_new_fixtures_drop_it(self):
        self.store.save_tool_evidence("C", "screening", "C-SCREENING", "{}")
        ingest(DEV, self.store)
        self.assertIsNotNone(self.store.get_source("C-SCREENING"))
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            shutil.copytree(DEV, data)
            (data / "documents" / "KYC-D12-IDENTITY.md").unlink()
            ingest(data, self.store)
        self.assertIsNone(self.store.get_source("C-SCREENING"))

    def test_old_schema_database_is_rebuilt(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.sqlite"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE documents(source_id TEXT PRIMARY KEY, case_id TEXT)")
            with SqliteKnowledgeStore(path) as store:
                report = ingest(DEV, store)
                self.assertEqual(report["added"], 41)
                self.assertEqual(
                    store.get_document("KYC-D02-INTAKE").identity_status,
                    "not supplied",
                )


class ParsingTests(unittest.TestCase):
    def test_chunks_are_paragraphs(self):
        text = "# T\n\nfirst line\nsecond line\n\n\nthird\n"
        chunks = chunk_paragraphs("S", text)
        self.assertEqual([c.text for c in chunks], ["# T", "first line\nsecond line", "third"])
        self.assertEqual([c.start_line for c in chunks], [1, 3, 7])
        for c in chunks:
            self.assertEqual(text[c.start_offset : c.end_offset], c.text)

    def test_missing_source_id_header_falls_back_to_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "KYC-X1-INTAKE.md"
            path.write_text("# Intake\n\nReview date: 2026-10-01\n")
            parsed = parse_file(path, "documents")
        self.assertEqual(parsed.source.source_id, "KYC-X1-INTAKE")
        self.assertEqual(parsed.document.case_id, "KYC-X1")
        self.assertEqual(len(parsed.warnings), 1)


class KycCopilotParsingTests(unittest.TestCase):
    """Cycle 1.2: corporate/identity fields and suffix checks via kyc_copilot.ingestion."""

    def test_corporate_filing_fields_are_parsed(self):
        from kyc_copilot.ingestion.parsing import parse_file as kyc_parse

        parsed = kyc_parse(DEV / "documents" / "KYC-D01-CORPORATE.md", "documents")
        doc = parsed.document
        self.assertEqual(doc.doc_type, "corporate")
        self.assertEqual(doc.filing_jurisdiction, "Alder")
        self.assertEqual(doc.declared_owner, "Ari Vale")
        self.assertEqual(doc.filing_address, "100 Orchard Walk, Alder.")

    def test_identity_fields_are_parsed(self):
        from kyc_copilot.ingestion.parsing import parse_file as kyc_parse

        parsed = kyc_parse(DEV / "documents" / "KYC-D01-IDENTITY.md", "documents")
        doc = parsed.document
        self.assertEqual(doc.doc_type, "identity")
        self.assertEqual(doc.holder_name, "Ari Vale")
        self.assertEqual(doc.birth_year, 1985)
        self.assertEqual(doc.document_reference, "SYN-ID-D01")
        self.assertFalse(doc.identity_not_supplied)

    def test_identity_not_included_sets_identity_not_supplied(self):
        from kyc_copilot.ingestion.parsing import parse_file as kyc_parse

        parsed = kyc_parse(DEV / "documents" / "KYC-D02-IDENTITY.md", "documents")
        self.assertTrue(parsed.document.identity_not_supplied)
        self.assertIsNone(parsed.document.holder_name)

    def test_unrecognized_document_suffix_is_flagged(self):
        from kyc_copilot.ingestion.parsing import parse_file as kyc_parse

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "KYC-X1-OTHER.md"
            path.write_text(
                "# Odd attachment\n\nSource ID: KYC-X1-OTHER\n\nReview date: 2026-10-01\n"
            )
            parsed = kyc_parse(path, "documents")
        self.assertTrue(
            any("unrecognized_document_suffix" in w for w in parsed.warnings),
            parsed.warnings,
        )


class PolicyManifestGuardTests(unittest.TestCase):
    """Cycle 1.3: PolicyManifestGuard and no-network ingestion package."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = self.tmp / "data"
        shutil.copytree(DEV, self.data)
        self.store = SqliteKnowledgeStore(":memory:")
        self.addCleanup(self.store.close)

    def test_tampered_known_policy_hash_raises_ingest_error(self):
        from kyc_copilot.ingestion.ingest import IngestError as KycIngestError
        from kyc_copilot.ingestion.ingest import ingest as kyc_ingest

        target = self.data / "policies" / "KYC-SCOPE-01.md"
        target.write_bytes(target.read_bytes() + b"\n")
        with self.assertRaises(KycIngestError) as ctx:
            kyc_ingest(self.data, self.store, manifest_path=MANIFEST)
        self.assertIn("KYC-SCOPE-01", str(ctx.exception))

    def test_unknown_policy_file_is_not_loaded_and_warns(self):
        from kyc_copilot.ingestion.ingest import ingest as kyc_ingest

        new_policy = self.data / "policies" / "KYC-POLICY-NEW-UNLISTED.md"
        new_policy.write_text(
            "# Unlisted policy\n\n"
            "Source ID: KYC-POLICY-NEW-UNLISTED\n\n"
            "Entity type: limited_company\n"
            "Jurisdiction: Alder\n"
            "Effective from: 2026-01-01\n"
            "Effective through: 2026-12-31\n"
            "EDD monthly threshold: 99999\n"
        )
        before_policies = 4
        report = kyc_ingest(self.data, self.store, manifest_path=MANIFEST)
        self.assertTrue(
            any(
                w == "new_policy_file_not_loaded:KYC-POLICY-NEW-UNLISTED"
                for w in report["warnings"]
            ),
            report["warnings"],
        )
        self.assertIsNone(self.store.get_source("KYC-POLICY-NEW-UNLISTED"))
        self.assertEqual(self.store.counts()["policies"], before_policies)
        self.assertEqual(
            self.store.find_policies("limited_company", "Alder", "2026-06-01")[0].edd_threshold,
            30000,
        )

    def test_ingestion_package_does_not_import_urllib(self):
        forbidden = {"urllib", "urllib.request", "urllib.error", "urllib.parse"}
        files = list(INGESTION_SRC.glob("*.py"))
        self.assertTrue(files, f"expected Python modules under {INGESTION_SRC}")
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            found: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        found.add(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    found.add(node.module)
            hits = {name for name in found if name.split(".")[0] == "urllib" or name in forbidden}
            self.assertFalse(hits, f"{path.name} imports {sorted(hits)}")


class ServiceLinkTests(unittest.TestCase):
    """Uses the real mock service; reads only GET /v1/cases."""

    def test_case_ids_come_from_the_service_when_available(self):
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import runtime
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as tmp:
            server = runtime.create_server(DEV, Path(tmp) / "mock.sqlite", port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_address[1]}"
                with SqliteKnowledgeStore(":memory:") as store:
                    report = ingest(DEV, store, api_url=url)
                    self.assertTrue(report["case_links_from_service"])
                    self.assertEqual(report["warnings"], [])
                    self.assertEqual(len(store.case_documents("KYC-D05")), 3)
                    self.assertTrue(store.get_document("KYC-D05-INTAKE").is_intake)
            finally:
                server.shutdown()
                server.server_close()

    def test_unreachable_service_falls_back_with_warning(self):
        with SqliteKnowledgeStore(":memory:") as store:
            report = ingest(DEV, store, api_url="http://127.0.0.1:9")
            self.assertFalse(report["case_links_from_service"])
            self.assertTrue(any("could not read case list" in w for w in report["warnings"]))
            self.assertEqual(len(store.case_documents("KYC-D01")), 3)


if __name__ == "__main__":
    unittest.main()
