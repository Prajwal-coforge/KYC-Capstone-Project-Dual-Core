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
        self.assertIn("I drafted this note for ENT-1", note)
        self.assertIn("I have not approved or rejected the customer", note)
        self.assertNotIn("Findings:", note)
        self.assertNotIn("Limits:", note)

    def test_a_quiet_case_says_there_is_nothing_further(self):
        note = self.narrator.write(
            _decision(routing="escalate", monthly_total=None, reasons=[]),
            _evidence(screening=None, transactions=None),
        )
        self.assertIn("nothing further to add", note)
        self.assertNotIn("pep_indicator", note)

    def test_unreadable_total_is_said_in_plain_language(self):
        note = self.narrator.write(
            _decision(routing="escalate", reasons=["transactions_unreadable"], monthly_total=None),
            _evidence(),
        )
        self.assertIn("I could not read the monthly transaction total", note)

    def test_exact_match_asks_for_a_specialist(self):
        note = self.narrator.write(
            _decision(
                routing="escalate",
                reasons=["screening_exact_match"],
                screening_matches=[
                    {"candidate_name": "Ari Vale", "match_type": "exact", "list": "L"}
                ],
            ),
            _evidence(),
        )
        self.assertIn("exact match on list entry 'Ari Vale'", note)
        self.assertIn("does not establish guilt", note)

    def test_near_match_stays_an_unresolved_candidate(self):
        note = self.narrator.write(
            _decision(
                routing="escalate",
                reasons=["screening_near_match"],
                screening_matches=[
                    {"candidate_name": "Ari Vael", "match_type": "near", "list": "L"}
                ],
            ),
            _evidence(),
        )
        self.assertIn("unresolved identity candidate", note)
        self.assertNotIn("confirmed match", note)

    def test_registry_outage_says_the_review_is_incomplete(self):
        note = self.narrator.write(
            _decision(routing="escalate", incomplete_reasons=["registry_unavailable"]),
            _evidence(failed_tools=("registry",), registry=None),
        )
        self.assertIn("incomplete", note.lower())
        self.assertIn("company registry", note)

    def test_each_conflict_shows_both_values_and_chooses_neither(self):
        ev = _evidence(
            customer={**_evidence().customer, "birth_year": 1990, "company_name": "Acme"},
            filing_jurisdiction="Birch",
            entity_ref="ENT-9",
            holder_name="Ari Vael",
            declared_owner="Bo Lin",
            birth_year=1985,
            company_name="Acme Ltd",
        )
        reasons = [
            "jurisdiction_conflict",
            "entity_ref_conflict",
            "company_name_conflict",
            "owner_name_conflict",
            "birth_year_conflict",
        ]
        note = self.narrator.write(_decision(routing="escalate", reasons=reasons), ev)
        for text in (
            "jurisdiction 'Alder' but the corporate filing gives 'Birch'",
            "entity reference 'ENT-9' does not match the customer record entity 'ENT-1'",
            "names the company 'Acme' but the corporate filing names it 'Acme Ltd'",
            "identity document holder 'Ari Vael' is not among the registry owners ('Ari Vale')",
            "declared owner in the corporate filing 'Bo Lin' is not among",
            "birth year 1990 but the identity document gives 1985",
        ):
            self.assertIn(text, note)

    def test_registry_and_customer_gaps_are_named(self):
        note = self.narrator.write(
            _decision(
                routing="escalate",
                reasons=[
                    "registry_not_active",
                    "owners_not_established",
                    "customer_fields_missing",
                ],
            ),
            _evidence(registry={**_evidence().registry, "registry_status": "dissolved"}),
        )
        self.assertIn("registry status is 'dissolved', not active", note)
        self.assertIn("did not supply usable owner names", note)
        self.assertIn("could not select a policy", note)

    def test_document_faults_are_named(self):
        note = self.narrator.write(
            _decision(
                routing="escalate",
                reasons=["missing_corporate", "duplicate_identity", "heading_mismatch"],
            ),
            _evidence(),
        )
        self.assertIn("The corporate filing is missing from the case.", note)
        self.assertIn("more than one identity document", note)
        self.assertIn("heading does not match its document type", note)
        self.assertIn("A person needs to check the case documents.", note)

    def test_a_foreign_currency_total_is_not_compared_as_xcr(self):
        note = self.narrator.write(
            _decision(routing="escalate", reasons=["currency_mismatch"]),
            _evidence(
                transactions={"source_id": "C1-TX", "monthly_total": 12000, "currency": "USD"}
            ),
        )
        self.assertIn("'USD', not XCR", note)
        self.assertNotIn("12000 XCR", note)

    def test_formatting_only_differences_list_each_address_once(self):
        note = self.narrator.write(
            _decision(address_check="normalized_same"),
            _evidence(filing_address="100 Orchard Walk, Alder."),
        )
        self.assertIn(
            "The registered addresses '100 Orchard Walk, Alder', '100 Orchard Walk, Alder.' "
            "differ only in formatting",
            note,
        )

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
