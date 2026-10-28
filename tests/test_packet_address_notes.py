"""Filing-address mismatch must appear in narrative notes and citations (PR #6 review)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kyc_copilot.adapters.sqlite_store import SqliteKnowledgeStore
from kyc_copilot.adapters.tools_client import ToolClient
from kyc_copilot.domain.packet import _follow_up
from kyc_copilot.domain.rules import decide
from kyc_copilot.narrative.narrator import TemplateNarrator
from kyc_copilot.runner.ingest import ingest
from kyc_copilot.runner.pipeline import review_case
from tests.helpers import DEV, MockService
from tests.test_rules import ADDRESS, evidence


class FilingAddressNoteAndCitationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = SqliteKnowledgeStore(":memory:")
        ingest(DEV, cls.store)
        cls.find = cls.store.find_policies

    @classmethod
    def tearDownClass(cls):
        cls.store.close()

    def test_filing_only_mismatch_mentions_filing_not_customer_vs_registry(self):
        filing = "999 Other Walk, Alder."
        ev = evidence(filing_address=filing)
        decision = decide(ev, self.find)
        self.assertEqual(decision.routing, "request_information")
        note = TemplateNarrator().write(decision, ev)
        self.assertIn("filing", note.lower())
        self.assertIn(filing, note)
        self.assertNotIn(
            f"The customer record address '{ADDRESS}' differs from the registry",
            note,
        )
        question = _follow_up("address_explanation", decision, ev)
        self.assertIn(filing, question)
        self.assertIn("filing", question.lower())

    def test_missing_customer_address_names_the_source(self):
        customer = {**evidence().customer, "registered_address": None}
        registry = {**evidence().registry, "registered_address": "9 New Quay, Alder"}
        ev = evidence(
            customer=customer,
            registry=registry,
            filing_address="102 Orchard Walk, Alder.",
        )
        decision = decide(ev, self.find)
        note = TemplateNarrator().write(decision, ev)
        question = _follow_up("address_explanation", decision, ev)
        for text in (note, question):
            self.assertIn("customer record did not supply an address", text)
            self.assertNotIn("None", text)
            self.assertIn("9 New Quay, Alder", text)
            self.assertIn("102 Orchard Walk, Alder.", text)

    def test_address_mismatch_packet_cites_corporate_filing(self):
        tmp = Path(tempfile.mkdtemp())
        mock = MockService(tmp / "mock.sqlite")
        store = SqliteKnowledgeStore(tmp / "app.sqlite")
        self.addCleanup(mock.stop)
        self.addCleanup(store.close)
        ingest(DEV, store, api_url=mock.url)
        client = ToolClient(mock.url, timeout=5)
        packet = review_case("KYC-D03", client, store).packet
        self.assertIn("address_explanation", packet["missing_information"])
        corporate = [c for c in packet["citations"] if c["source_id"] == "KYC-D03-CORPORATE"]
        self.assertTrue(corporate, packet["citations"])
        self.assertTrue(
            any("Registered address in supplied filing" in c["quote"] for c in corporate)
        )
        self.assertIn("filing", packet["narrative"].lower())


if __name__ == "__main__":
    unittest.main()
