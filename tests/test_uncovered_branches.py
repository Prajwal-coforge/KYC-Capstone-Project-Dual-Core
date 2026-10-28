"""Branches the dev-set replay does not reach. Statement coverage of the package stays complete."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from kyc_copilot.adapters.sqlite_store import SqliteKnowledgeStore
from kyc_copilot.contracts.models import Document, ParsedFile, Source
from kyc_copilot.domain.packet import _follow_up, build_citations
from kyc_copilot.domain.rules import decide
from kyc_copilot.ingestion.ingest import document_set_faults
from kyc_copilot.ingestion.parsing import (
    FILING_ADDRESS_RE,
    FILING_JURISDICTION_RE,
    _label_value,
    parse_file,
)
from kyc_copilot.narrative.narrator import _address_difference_note
from kyc_copilot.runner.cli import _business_key
from kyc_copilot.runner.ingest import ingest
from kyc_copilot.runner.pipeline import _document_faults, _heading_faults
from tests.helpers import DEV
from tests.test_rules import evidence


def _document(source_id: str, doc_type: str, **over) -> Document:
    return Document(
        source_id,
        "C1",
        doc_type,
        doc_type == "intake",
        date(2026, 10, 1),
        "ENT-1",
        **over,
    )


def _parsed(document: Document) -> ParsedFile:
    source = Source(document.source_id, "document", "untrusted", None, "mem", "body", "abc")
    return ParsedFile(source, document=document)


class MissingAddressWordingTests(unittest.TestCase):
    def test_a_missing_registry_address_is_named(self) -> None:
        note = _address_difference_note("100 Orchard Walk, Alder", None, None)
        self.assertIn("registry did not supply an address", note)
        self.assertNotIn("None", note)

        ev = evidence(
            registry={**evidence().registry, "registered_address": None},
            filing_address=None,
        )

        class _Decision:
            facts = {"entity_id": "ENT-1"}

        question = _follow_up("address_explanation", _Decision(), ev)
        self.assertIn("registry did not supply an address", question)
        self.assertIn("100 Orchard Walk, Alder", question)
        self.assertNotIn("None", question)


class BlankBusinessKeyTests(unittest.TestCase):
    def test_a_blank_review_date_does_not_match_a_previous_draft(self) -> None:
        self.assertIsNone(
            _business_key(
                {"facts": {"entity_id": "ENT-1", "review_date": "  "}},
            )
        )


class DocumentFaultBranchTests(unittest.TestCase):
    def test_unknown_empty_and_duplicate_documents_are_named(self) -> None:
        faults = _document_faults(
            [
                _document("A", "intake"),
                _document("B", "intake"),
                _document(
                    "C",
                    "memo",
                    empty=True,
                    review_date_unreadable=True,
                    label_conflicts=("company name",),
                ),
            ]
        )
        self.assertIn("duplicate_intake", faults)
        self.assertIn("unknown_document", faults)
        self.assertIn("empty_document", faults)
        self.assertIn("review_date_unreadable", faults)
        self.assertIn("label_conflict", faults)

    def test_an_unknown_document_type_is_a_set_fault(self) -> None:
        faults = document_set_faults(
            [
                _parsed(_document("C1-INTAKE", "intake")),
                _parsed(_document("C1-CORPORATE", "corporate")),
                _parsed(_document("C1-IDENTITY", "identity")),
                _parsed(_document("C1-MEMO", "memo")),
            ]
        )
        self.assertEqual(faults["C1"], ["unknown_document"])

    def test_a_heading_must_name_its_own_document_type(self) -> None:
        intake = _document("C1-INTAKE", "intake")
        corporate = _document("C1-CORPORATE", "corporate")
        memo = _document("C1-MEMO", "memo")
        blank = _document("C1-IDENTITY", "identity", empty=True)
        self.assertEqual(
            _heading_faults(
                [
                    (intake, "Periodic review intake\r"),
                    (corporate, "Corporate filing attachment"),
                    (memo, None),
                    (blank, None),
                ]
            ),
            (),
        )
        for title in ("Identity attachment status", "Corporate identity filing", None):
            with self.subTest(title=title):
                self.assertEqual(_heading_faults([(corporate, title)]), ("heading_mismatch",))


class ParserBranchTests(unittest.TestCase):
    def test_label_value_absent_present_and_kept_period(self) -> None:
        self.assertIsNone(_label_value(FILING_JURISDICTION_RE, "no labels here"))
        self.assertEqual(
            _label_value(FILING_JURISDICTION_RE, "Filing jurisdiction: Alder."),
            "Alder",
        )
        self.assertEqual(
            _label_value(
                FILING_ADDRESS_RE,
                "Registered address in supplied filing: 100 Orchard Walk.",
                keep_period=True,
            ),
            "100 Orchard Walk.",
        )

    def _parse(self, name: str, body: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_text(body)
            return parse_file(path, "documents")

    def test_two_filing_jurisdictions_conflict(self) -> None:
        parsed = self._parse(
            "C1-CORPORATE.md",
            "Source ID: C1-CORPORATE\nFiling jurisdiction: Alder\nFiling jurisdiction: Birch\n",
        )
        self.assertIn("filing jurisdiction", parsed.document.label_conflicts)
        self.assertIsNone(parsed.document.filing_jurisdiction)

    def test_conflicting_company_name_labels_are_unset(self) -> None:
        parsed = self._parse(
            "C1-CORPORATE.md",
            "Source ID: C1-CORPORATE\nCompany name: North Mill\nCompany name: South Mill\n",
        )
        self.assertIsNone(parsed.document.company_name)
        self.assertIn("company name", parsed.document.label_conflicts)

    def test_company_name_that_disagrees_with_prose_is_unset(self) -> None:
        parsed = self._parse(
            "C1-CORPORATE.md",
            "Source ID: C1-CORPORATE\nCompany name: North Mill\nSouth Mill manufactures bolts.\n",
        )
        self.assertIsNone(parsed.document.company_name)
        self.assertIn("company name", parsed.document.label_conflicts)


class CurrencyCitationTests(unittest.TestCase):
    def test_currency_mismatch_cites_the_policy_sentence(self) -> None:
        store = SqliteKnowledgeStore(":memory:")
        self.addCleanup(store.close)
        ingest(DEV, store)
        ev = evidence(
            transactions={
                "source_id": "C1-TRANSACTIONS",
                "monthly_total": 12000,
                "currency": "USD",
            }
        )
        decision = decide(ev, store.find_policies)
        quotes = [c["quote"] for c in build_citations(decision, ev, None, store)]
        self.assertTrue(
            any(q and "Currency is the invented XCR crown." in q for q in quotes),
            quotes,
        )
