"""Cycle 4.2 RED: DRAFT customer request only when routing is request_information."""

from __future__ import annotations

import unittest
from datetime import date

from kyc_copilot.contracts.models import CaseEvidence, Decision, Policy
from kyc_copilot.narrative.narrator import TemplateNarrator


def _evidence(**over) -> CaseEvidence:
    base = dict(
        case_id="C1",
        review_date=date(2026, 10, 1),
        entity_ref="ENT-1",
        identity_status="attached",
        identity_document_present=True,
        customer={
            "source_id": "C1-CUSTOMER",
            "entity_id": "ENT-1",
            "entity_type": "limited_company",
            "jurisdiction": "Alder",
            "registered_address": "100 Orchard Walk, Alder",
        },
        registry={
            "source_id": "C1-REGISTRY",
            "registered_address": "100 Orchard Walk, Alder",
            "ownership_depth": 1,
            "owners": [{"name": "Ari Vale"}],
            "registry_status": "active",
        },
        screening={"source_id": "C1-SCREENING", "matches": [], "pep_indicator": False},
        transactions={"source_id": "C1-TX", "monthly_total": 12000, "currency": "XCR"},
        failed_tools=(),
        holder_name="Ari Vale",
    )
    base.update(over)
    return CaseEvidence(**base)


def _decision(**over) -> Decision:
    policy = Policy(
        "KYC-POLICY-ALDER-LTD-V2",
        "limited_company",
        "Alder",
        date(2026, 9, 1),
        date(2026, 12, 31),
        50000,
    )
    base = dict(
        classification="kyc_review",
        routing="complete_review",
        policy_ids=["KYC-POLICY-ALDER-LTD-V2", "KYC-SCOPE-01"],
        policy=policy,
        facts={
            "entity_id": "ENT-1",
            "entity_type": "limited_company",
            "jurisdiction": "Alder",
            "review_date": "2026-10-01",
            "owner_names": ["Ari Vale"],
        },
        missing_information=[],
        reasons=[],
        incomplete_reasons=[],
        address_check="same",
        screening_matches=[],
        pep=False,
        monthly_total=12000,
    )
    base.update(over)
    return Decision(**base)


class DraftCustomerRequestGateTests(unittest.TestCase):
    def setUp(self):
        self.narrator = TemplateNarrator()

    def test_request_information_includes_draft_customer_request_block(self):
        note = self.narrator.write(
            _decision(
                routing="request_information",
                missing_information=["address_explanation"],
                reasons=["address_mismatch"],
                address_check="different",
            ),
            _evidence(),
        )
        self.assertIn("DRAFT customer request:", note)
        self.assertIn("address_explanation", note)

    def test_escalate_with_missing_info_has_no_draft_customer_request(self):
        note = self.narrator.write(
            _decision(
                routing="escalate",
                missing_information=["identity_document", "address_explanation"],
                reasons=["screening_near_match", "identity_document_missing", "address_mismatch"],
                address_check="different",
                screening_matches=[
                    {
                        "candidate_name": "Ari Vael",
                        "match_type": "near",
                        "list": "SYNTHETIC-SCREENING-LIST",
                    }
                ],
            ),
            _evidence(identity_status="not supplied"),
        )
        self.assertNotIn("DRAFT customer request:", note)
        self.assertIn("identity_document", note)
        self.assertIn("address_explanation", note)

    def test_complete_review_has_no_draft_customer_request(self):
        note = self.narrator.write(_decision(), _evidence())
        self.assertNotIn("DRAFT customer request:", note)
        self.assertIn("complete_review", note)
        self.assertIn("pep_indicator false", note)

    def test_enhanced_due_diligence_has_no_draft_customer_request(self):
        note = self.narrator.write(
            _decision(
                routing="enhanced_due_diligence",
                reasons=["pep_indicator"],
                pep=True,
            ),
            _evidence(),
        )
        self.assertNotIn("DRAFT customer request:", note)


if __name__ == "__main__":
    unittest.main()
