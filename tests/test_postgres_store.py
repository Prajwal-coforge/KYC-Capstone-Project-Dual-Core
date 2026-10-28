"""PostgresKnowledgeStore: DSN parsing without a server; live tests when KYC_DATABASE_URL is set."""

from __future__ import annotations

import os
import unittest
from datetime import date

from kyc_copilot.adapters.postgres_store import PostgresKnowledgeStore, normalize_dsn
from kyc_copilot.adapters.sqlite_store import SCHEMA_VERSION
from kyc_copilot.contracts.models import Chunk, Document, ParsedFile, Policy, Source


def _file(
    source_id: str,
    kind: str = "document",
    *,
    content: str = "body",
    policy: Policy | None = None,
    document: Document | None = None,
    chunks: tuple[Chunk, ...] = (),
) -> ParsedFile:
    trust = "trusted" if kind in ("policy", "procedure") else "untrusted"
    return ParsedFile(
        Source(source_id, kind, trust, source_id, f"mem:{source_id}", content, "abc"),
        policy=policy,
        document=document,
        chunks=chunks,
    )


class DsnParsingTests(unittest.TestCase):
    def test_remote_host_defaults_sslmode_require(self) -> None:
        out = normalize_dsn("postgresql://kyc:kyc@db.example:5432/kyc")
        self.assertIn("sslmode=require", out)

    def test_localhost_does_not_force_sslmode(self) -> None:
        for host in ("localhost", "127.0.0.1"):
            dsn = f"postgresql://kyc:kyc@{host}:5432/kyc"
            self.assertEqual(normalize_dsn(dsn), dsn)

    def test_existing_sslmode_is_kept(self) -> None:
        dsn = "postgresql://kyc:kyc@db.example:5432/kyc?sslmode=disable"
        self.assertEqual(normalize_dsn(dsn), dsn)

    def test_postgres_scheme_is_accepted(self) -> None:
        out = normalize_dsn("postgres://kyc:kyc@remote:5432/kyc")
        self.assertTrue(out.startswith("postgres://"))
        self.assertIn("sslmode=require", out)

    def test_adapter_exposes_schema_version_and_write_port(self) -> None:
        self.assertEqual(PostgresKnowledgeStore.schema_version, SCHEMA_VERSION)
        names = ("replace_all", "save_tool_evidence", "find_policies", "verify_quote", "counts")
        for name in names:
            self.assertTrue(callable(getattr(PostgresKnowledgeStore, name, None)), name)


@unittest.skipUnless(os.environ.get("KYC_DATABASE_URL"), "KYC_DATABASE_URL not set")
class PostgresLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = PostgresKnowledgeStore(os.environ["KYC_DATABASE_URL"])
        self.addCleanup(self.store.close)

    def test_schema_version_matches_sqlite(self) -> None:
        self.assertEqual(self.store.schema_version, SCHEMA_VERSION)

    def test_replace_all_is_one_transaction_and_finds_inclusive_dates(self) -> None:
        policy = Policy(
            "P1",
            "limited_company",
            "Alder",
            date(2026, 1, 1),
            date(2026, 12, 31),
            15000,
        )
        parsed = [
            _file("P1", "policy", content="EDD monthly threshold: 15000", policy=policy),
            _file(
                "C-INTAKE",
                document=Document(
                    "C-INTAKE",
                    "C",
                    "intake",
                    True,
                    date(2026, 6, 15),
                    "ENT-1",
                    "attached",
                ),
                chunks=(Chunk("C-INTAKE", 0, 1, 0, 4, "body"),),
            ),
            _file(
                "C-CORPORATE",
                document=Document(
                    "C-CORPORATE",
                    "C",
                    "corporate",
                    False,
                    None,
                    None,
                    None,
                    "Alder",
                    "Ari Vale",
                    "100 Orchard Walk, Alder.",
                ),
            ),
        ]
        diff = self.store.replace_all(parsed, {"manifest_sha256": "m1"})
        self.assertIn("P1", diff["added"] + diff["updated"] + diff["unchanged"])
        hit = self.store.find_policies("limited_company", "Alder", date(2026, 1, 1))
        self.assertEqual([p.source_id for p in hit], ["P1"])
        hit = self.store.find_policies("limited_company", "Alder", date(2026, 12, 31))
        self.assertEqual([p.source_id for p in hit], ["P1"])
        self.assertEqual(self.store.get_document("C-CORPORATE").filing_jurisdiction, "Alder")
        self.assertEqual(self.store.get_document("C-CORPORATE").declared_owner, "Ari Vale")
        self.assertTrue(self.store.verify_quote("P1", "EDD monthly threshold: 15000"))
        self.assertFalse(self.store.verify_quote("P1", "   "))
        self.assertFalse(self.store.verify_quote("P1", ""))

    def test_duplicate_source_ids_raise(self) -> None:
        item = _file("DUP")
        with self.assertRaises(ValueError):
            self.store.replace_all([item, item], {"manifest_sha256": "dup"})

    def test_save_tool_evidence_does_not_overwrite_ingested_id(self) -> None:
        self.store.replace_all(
            [_file("SCOPE", "procedure", content="scope text")],
            {"manifest_sha256": "m2"},
        )
        # procedure without policy object still ingested as source
        with self.assertRaises(ValueError):
            self.store.save_tool_evidence("C", "customer", "SCOPE", "{}")
        self.assertIn("scope text", self.store.get_source("SCOPE").content)

    def test_tool_evidence_is_quotable_and_stale_tools_drop_on_manifest_change(self) -> None:
        self.store.replace_all([_file("DOC", content="doc")], {"manifest_sha256": "old"})
        self.store.save_tool_evidence("C", "screening", "C-SCREENING", '{"n": 1}')
        self.assertTrue(self.store.verify_quote("C-SCREENING", '"n": 1'))
        self.store.replace_all([_file("DOC", content="doc")], {"manifest_sha256": "new"})
        self.assertIsNone(self.store.get_source("C-SCREENING"))


if __name__ == "__main__":
    unittest.main()
