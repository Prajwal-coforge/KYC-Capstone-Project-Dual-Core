"""Cycle 4.1 RED: domain packet cites every conflicting source (corporate + identity)."""

from __future__ import annotations

import unittest

from kyc_copilot.runner.ingest import ingest

from kyc_copilot.adapters.sqlite_store import SqliteKnowledgeStore
from kyc_copilot.contracts.models import CaseEvidence
from kyc_copilot.contracts.redaction import canonical_json
from kyc_copilot.domain.packet import build_citations, build_packet
from kyc_copilot.domain.rules import decide
from kyc_copilot.narrative.narrator import TemplateNarrator
from tests.helpers import DEV
from tests.test_rules import evidence


def _quotes_by_source(citations: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c in citations:
        out.setdefault(c["source_id"], []).append(c["quote"])
    return out


def _seed_tool_evidence(store: SqliteKnowledgeStore, ev: CaseEvidence) -> None:
    """Persist customer/registry payloads so json_fragment citations verify."""
    if ev.customer is not None:
        store.save_tool_evidence(
            ev.case_id, "customer", ev.customer["source_id"], canonical_json(ev.customer)
        )
    if ev.registry is not None:
        store.save_tool_evidence(
            ev.case_id, "registry", ev.registry["source_id"], canonical_json(ev.registry)
        )


class DomainPacketDiscrepancyCitationTests(unittest.TestCase):
    """When sources disagree, cite each side with an exact verified quote."""

    @classmethod
    def setUpClass(cls):
        cls.store = SqliteKnowledgeStore(":memory:")
        ingest(DEV, cls.store)
        cls.find = cls.store.find_policies

    @classmethod
    def tearDownClass(cls):
        cls.store.close()

    def test_domain_packet_exports_build_helpers(self):
        self.assertTrue(callable(build_citations))
        self.assertTrue(callable(build_packet))

    def test_jurisdiction_conflict_cites_customer_and_corporate(self):
        ev = evidence(
            case_id="KYC-D01",
            filing_jurisdiction="Birch",
            customer={
                "source_id": "KYC-D01-CUSTOMER",
                "entity_id": "ENT-D01",
                "entity_type": "limited_company",
                "jurisdiction": "Alder",
                "registered_address": "100 Orchard Walk, Alder",
            },
            registry={
                "source_id": "KYC-D01-REGISTRY",
                "registered_address": "100 Orchard Walk, Alder",
                "ownership_depth": 1,
                "owners": [{"name": "Ari Vale", "share_percent": 100}],
                "registry_status": "active",
            },
        )
        _seed_tool_evidence(self.store, ev)
        decision = decide(ev, self.find)
        self.assertEqual(decision.routing, "escalate")
        self.assertIn("jurisdiction_conflict", decision.reasons)
        packet = build_packet(decision, ev, "KYC-D01-INTAKE", self.store, TemplateNarrator())
        by_src = _quotes_by_source(packet["citations"])
        self.assertIn("KYC-D01-CUSTOMER", by_src)
        self.assertTrue(
            any("jurisdiction" in q and "Alder" in q for q in by_src["KYC-D01-CUSTOMER"]),
            by_src["KYC-D01-CUSTOMER"],
        )
        self.assertIn("KYC-D01-CORPORATE", by_src)
        self.assertTrue(
            any("Filing jurisdiction:" in q for q in by_src["KYC-D01-CORPORATE"]),
            by_src["KYC-D01-CORPORATE"],
        )
        for c in packet["citations"]:
            self.assertTrue(self.store.verify_quote(c["source_id"], c["quote"]), c)

    def test_owner_name_conflict_cites_identity_and_registry(self):
        ev = evidence(
            case_id="KYC-D01",
            holder_name="Not An Owner",
            customer={
                "source_id": "KYC-D01-CUSTOMER",
                "entity_id": "ENT-D01",
                "entity_type": "limited_company",
                "jurisdiction": "Alder",
                "registered_address": "100 Orchard Walk, Alder",
            },
            registry={
                "source_id": "KYC-D01-REGISTRY",
                "registered_address": "100 Orchard Walk, Alder",
                "ownership_depth": 1,
                "owners": [{"name": "Ari Vale", "share_percent": 100}],
                "registry_status": "active",
            },
        )
        _seed_tool_evidence(self.store, ev)
        decision = decide(ev, self.find)
        self.assertIn("owner_name_conflict", decision.reasons)
        packet = build_packet(decision, ev, "KYC-D01-INTAKE", self.store, TemplateNarrator())
        by_src = _quotes_by_source(packet["citations"])
        self.assertIn("KYC-D01-IDENTITY", by_src)
        self.assertTrue(
            any(q.startswith("Name:") for q in by_src["KYC-D01-IDENTITY"]),
            by_src["KYC-D01-IDENTITY"],
        )
        self.assertIn("KYC-D01-REGISTRY", by_src)
        self.assertTrue(
            any("Ari Vale" in q for q in by_src["KYC-D01-REGISTRY"]),
            by_src["KYC-D01-REGISTRY"],
        )
        for c in packet["citations"]:
            self.assertTrue(self.store.verify_quote(c["source_id"], c["quote"]), c)

    def test_address_mismatch_cites_customer_registry_and_corporate(self):
        ev = evidence(
            case_id="KYC-D03",
            filing_address="102 Orchard Walk, Alder.",
            customer={
                "source_id": "KYC-D03-CUSTOMER",
                "entity_id": "ENT-D03",
                "entity_type": "limited_company",
                "jurisdiction": "Alder",
                "registered_address": "102 Orchard Walk, Alder",
            },
            registry={
                "source_id": "KYC-D03-REGISTRY",
                "registered_address": "9 New Quay, Alder",
                "ownership_depth": 1,
                "owners": [{"name": "Remy Lane", "share_percent": 100}],
                "registry_status": "active",
            },
        )
        _seed_tool_evidence(self.store, ev)
        decision = decide(ev, self.find)
        self.assertIn("address_explanation", decision.missing_information)
        cites = build_citations(decision, ev, "KYC-D03-INTAKE", self.store)
        ids = {c["source_id"] for c in cites}
        self.assertIn("KYC-D03-CUSTOMER", ids)
        self.assertIn("KYC-D03-REGISTRY", ids)
        self.assertIn("KYC-D03-CORPORATE", ids)
        corporate = [c for c in cites if c["source_id"] == "KYC-D03-CORPORATE"]
        self.assertTrue(
            any("Registered address in supplied filing" in c["quote"] for c in corporate)
        )
        for c in cites:
            self.assertTrue(self.store.verify_quote(c["source_id"], c["quote"]), c)


if __name__ == "__main__":
    unittest.main()
