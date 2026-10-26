"""Deterministic routing rules (KYC-SCOPE-01 and the policy versions), including edge cases."""

import unittest
from dataclasses import replace
from datetime import date

from kyc_copilot.adapters.sqlite_store import SqliteKnowledgeStore
from kyc_copilot.contracts.interfaces import AddressCanonicalizer, StatutoryRule
from kyc_copilot.domain.rules import (
    DEFAULT_CANONICALIZER,
    CaseEvidence,
    TokenMapAddressCanonicalizer,
    compare_addresses,
    decide,
    normalize_address,
)
from kyc_copilot.runner.ingest import ingest
from tests.helpers import DEV

ADDRESS = "100 Orchard Walk, Alder"
# Exact match for 3-way "same"; period-only filing diffs normalize separately.
FILING_ADDRESS = "100 Orchard Walk, Alder"

EXPECTED_RULE_ORDER = (
    "tool_availability",
    "cross_source_conflict",
    "scope_and_policy",
    "ownership_depth",
    "screening_match",
    "identity_document",
    "address_comparison",
    "edd_and_pep",
)


def evidence(**over) -> CaseEvidence:
    base = CaseEvidence(
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
            "registered_address": ADDRESS,
        },
        registry={
            "source_id": "C1-REGISTRY",
            "registered_address": ADDRESS,
            "ownership_depth": 1,
            "owners": [{"name": "Ari Vale", "share_percent": 100}],
            "registry_status": "active",
        },
        screening={"source_id": "C1-SCREENING", "matches": [], "pep_indicator": False},
        transactions={
            "source_id": "C1-TRANSACTIONS",
            "monthly_total": 12000,
            "currency": "XCR",
        },
        # filing_jurisdiction default None: missing is not a conflict (ENG-01).
        filing_jurisdiction=None,
        declared_owner="Ari Vale",
        filing_address=FILING_ADDRESS,
        holder_name="Ari Vale",
        birth_year=1985,
        identity_not_supplied=False,
    )
    return replace(base, **over)


def customer(**over):
    return {**evidence().customer, **over}


def registry(**over):
    return {**evidence().registry, **over}


def screening(*matches, pep=False):
    return {"source_id": "C1-SCREENING", "matches": list(matches), "pep_indicator": pep}


def match(kind, name="Ari Vael"):
    return {"candidate_name": name, "match_type": kind, "list": "SYNTHETIC-SCREENING-LIST"}


def total(amount):
    return {"source_id": "C1-TRANSACTIONS", "monthly_total": amount, "currency": "XCR"}


class RulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = SqliteKnowledgeStore(":memory:")
        ingest(DEV, cls.store)
        cls.find = cls.store.find_policies

    @classmethod
    def tearDownClass(cls):
        cls.store.close()

    def route(self, ev):
        return decide(ev, self.find)

    # ---- normal ------------------------------------------------------------------------

    def test_normal_case_completes_with_current_policy(self):
        d = self.route(evidence())
        self.assertEqual((d.classification, d.routing), ("kyc_review", "complete_review"))
        self.assertEqual(sorted(d.policy_ids), ["KYC-POLICY-ALDER-LTD-V2", "KYC-SCOPE-01"])
        self.assertEqual(d.missing_information, [])
        self.assertEqual(
            d.facts,
            {
                "entity_id": "ENT-1",
                "entity_type": "limited_company",
                "jurisdiction": "Alder",
                "review_date": "2026-10-01",
                "owner_names": ["Ari Vale"],
            },
        )

    def test_all_registry_owners_are_listed_in_order(self):
        owners = [{"name": "Ari Vale"}, {"name": "Bo Lin"}]
        d = self.route(evidence(registry=registry(owners=owners)))
        self.assertEqual(d.facts["owner_names"], ["Ari Vale", "Bo Lin"])

    def test_registry_with_no_owners_is_an_empty_list_not_null(self):
        d = self.route(evidence(registry=registry(owners=[])))
        self.assertEqual(d.facts["owner_names"], [])

    # ---- missing information -------------------------------------------------------------

    def test_identity_not_supplied_requests_information(self):
        d = self.route(evidence(identity_status="not supplied"))
        self.assertEqual(d.routing, "request_information")
        self.assertEqual(d.missing_information, ["identity_document"])

    def test_identity_attached_but_no_identity_document_is_missing(self):
        d = self.route(evidence(identity_document_present=False))
        self.assertEqual(d.missing_information, ["identity_document"])

    def test_identity_status_is_case_and_space_insensitive(self):
        d = self.route(evidence(identity_status="  Attached "))
        self.assertEqual(d.missing_information, [])

    def test_unknown_identity_status_is_treated_as_missing(self):
        self.assertEqual(
            self.route(evidence(identity_status=None)).missing_information, ["identity_document"]
        )

    def test_address_mismatch_requests_explanation(self):
        d = self.route(evidence(registry=registry(registered_address="9 New Quay, Alder")))
        self.assertEqual(d.routing, "request_information")
        self.assertEqual(d.missing_information, ["address_explanation"])
        self.assertEqual(d.address_check, "different")

    def test_both_missing_fields_in_stable_order(self):
        d = self.route(
            evidence(
                identity_status="not supplied",
                registry=registry(registered_address="9 New Quay, Alder"),
            )
        )
        self.assertEqual(d.missing_information, ["identity_document", "address_explanation"])

    # ---- addresses -----------------------------------------------------------------------

    def test_formatting_only_address_difference_is_same(self):
        d = self.route(evidence(customer=customer(registered_address="100  ORCHARD WALK, Alder.")))
        self.assertEqual((d.routing, d.address_check), ("complete_review", "normalized_same"))

    def test_recognized_us_suffix_abbreviation_is_same(self):
        self.assertEqual(compare_addresses("12 Main Street", "12 Main St."), "normalized_same")
        self.assertEqual(compare_addresses("5 North Oak Avenue", "5 N Oak Ave"), "normalized_same")

    def test_unrecognized_abbreviation_is_a_material_difference(self):
        self.assertEqual(compare_addresses("100 Orchard Wk", "100 Orchard Walk"), "different")

    def test_different_house_number_is_material(self):
        self.assertEqual(compare_addresses("100 Orchard Walk", "101 Orchard Walk"), "different")

    def test_missing_address_is_unknown_not_same(self):
        self.assertEqual(compare_addresses(None, ADDRESS), "unknown")
        self.assertEqual(compare_addresses("", ADDRESS), "unknown")

    def test_normalize_is_stable(self):
        self.assertEqual(normalize_address(" 12 Main St. "), normalize_address("12 MAIN STREET"))

    def test_token_map_canonicalizer_is_address_canonicalizer_strategy(self):
        canon = TokenMapAddressCanonicalizer()
        self.assertIsInstance(canon, AddressCanonicalizer)
        self.assertIsInstance(DEFAULT_CANONICALIZER, AddressCanonicalizer)

    def test_token_map_applies_nfkc_and_preserves_non_us_tokens(self):
        canon = TokenMapAddressCanonicalizer()
        # Fullwidth digits/letters fold via NFKC; Quay/Alder stay as known-unknown tokens.
        raw = "９ New Quay, Alder"
        out = canon.canonicalize(raw)
        self.assertEqual(out, "9 new quay alder")
        # Never raises on international-style place names.
        self.assertEqual(
            canon.canonicalize("100 Orchard Walk, Birch"),
            "100 orchard walk birch",
        )

    def test_compare_addresses_accepts_injected_canonicalizer(self):
        class UpperCanonicalizer:
            def canonicalize(self, raw_address: str) -> str:
                return raw_address.strip().upper()

        self.assertEqual(
            compare_addresses("12 Main St", "12 MAIN ST", canonicalizer=UpperCanonicalizer()),
            "normalized_same",
        )
        self.assertEqual(
            compare_addresses("12 Main St", "12 Main Ave", canonicalizer=UpperCanonicalizer()),
            "different",
        )

    # ---- screening -----------------------------------------------------------------------

    def test_near_match_escalates(self):
        d = self.route(evidence(screening=screening(match("near"))))
        self.assertEqual(d.routing, "escalate")
        self.assertIn("screening_near_match", d.reasons)

    def test_exact_match_escalates(self):
        d = self.route(evidence(screening=screening(match("exact", "Ari Vale"))))
        self.assertEqual(d.routing, "escalate")
        self.assertIn("screening_exact_match", d.reasons)

    def test_unrecognized_match_type_escalates(self):
        d = self.route(evidence(screening=screening(match("possible"))))
        self.assertEqual(d.routing, "escalate")

    def test_escalation_preserves_missing_information(self):
        d = self.route(
            evidence(
                screening=screening(match("near")),
                identity_status="not supplied",
                registry=registry(registered_address="9 New Quay, Alder"),
            )
        )
        self.assertEqual(d.routing, "escalate")
        self.assertEqual(d.missing_information, ["identity_document", "address_explanation"])

    # ---- thresholds and PEP --------------------------------------------------------------

    def test_total_equal_to_threshold_does_not_trigger_edd(self):
        self.assertEqual(self.route(evidence(transactions=total(50000))).routing, "complete_review")

    def test_total_above_threshold_triggers_edd(self):
        d = self.route(evidence(transactions=total(50001)))
        self.assertEqual(d.routing, "enhanced_due_diligence")
        self.assertEqual(
            self.route(evidence(transactions=total(50000.01))).routing, "enhanced_due_diligence"
        )

    def test_pep_indicator_triggers_edd(self):
        d = self.route(evidence(screening=screening(pep=True)))
        self.assertEqual(d.routing, "enhanced_due_diligence")
        self.assertIn("pep_indicator", d.reasons)

    def test_missing_information_outranks_edd(self):
        d = self.route(evidence(screening=screening(pep=True), identity_status="not supplied"))
        self.assertEqual(d.routing, "request_information")

    def test_unreadable_total_escalates(self):
        for bad in ("12000", True, None):
            with self.subTest(bad=bad):
                self.assertEqual(self.route(evidence(transactions=total(bad))).routing, "escalate")

    # ---- policy version by review date (stale-policy trap) --------------------------------

    def test_last_day_of_v1_uses_v1_threshold(self):
        d = self.route(evidence(review_date=date(2026, 8, 31), transactions=total(40000)))
        self.assertEqual(d.routing, "enhanced_due_diligence")
        self.assertIn("KYC-POLICY-ALDER-LTD-V1", d.policy_ids)

    def test_first_day_of_v2_uses_v2_threshold(self):
        d = self.route(evidence(review_date=date(2026, 9, 1), transactions=total(40000)))
        self.assertEqual(d.routing, "complete_review")
        self.assertIn("KYC-POLICY-ALDER-LTD-V2", d.policy_ids)

    def test_birch_uses_birch_threshold(self):
        ev = evidence(customer=customer(jurisdiction="Birch"), transactions=total(45000))
        d = self.route(ev)
        self.assertEqual(d.routing, "enhanced_due_diligence")
        self.assertEqual(sorted(d.policy_ids), ["KYC-POLICY-BIRCH-LTD-V1", "KYC-SCOPE-01"])

    def test_sole_proprietor_threshold_boundary(self):
        sole = customer(entity_type="sole_proprietor")
        self.assertEqual(
            self.route(evidence(customer=sole, transactions=total(25000))).routing,
            "complete_review",
        )
        self.assertEqual(
            self.route(evidence(customer=sole, transactions=total(25001))).routing,
            "enhanced_due_diligence",
        )

    def test_no_policy_for_review_date_escalates_with_scope_only(self):
        d = self.route(evidence(review_date=date(2027, 1, 1)))
        self.assertEqual((d.classification, d.routing), ("kyc_review", "escalate"))
        self.assertEqual(d.policy_ids, ["KYC-SCOPE-01"])
        self.assertIn("no_applicable_policy", d.reasons)

    def test_missing_review_date_escalates(self):
        d = self.route(evidence(review_date=None))
        self.assertEqual(d.routing, "escalate")
        self.assertIsNone(d.facts["review_date"])

    def test_overlapping_policies_escalate(self):
        two = self.find("limited_company", "Alder", "2026-10-01") * 2
        d = decide(evidence(), lambda *_: two)
        self.assertEqual(d.routing, "escalate")
        self.assertIn("multiple_policies", d.reasons)

    # ---- scope and ownership ---------------------------------------------------------------

    def test_unsupported_combination(self):
        d = self.route(
            evidence(customer=customer(entity_type="sole_proprietor", jurisdiction="Birch"))
        )
        self.assertEqual((d.classification, d.routing), ("unsupported", "escalate"))
        self.assertEqual(d.policy_ids, ["KYC-SCOPE-01"])
        self.assertEqual(d.facts["entity_type"], "sole_proprietor")

    def test_unknown_entity_type_is_unsupported(self):
        d = self.route(evidence(customer=customer(entity_type="partnership")))
        self.assertEqual(d.classification, "unsupported")

    def test_deep_ownership_escalates_and_keeps_owners(self):
        d = self.route(evidence(registry=registry(ownership_depth=2, intermediate_entity="Holdco")))
        self.assertEqual(d.routing, "escalate")
        self.assertIn("ownership_depth", d.reasons)
        self.assertEqual(d.facts["owner_names"], ["Ari Vale"])

    def test_missing_ownership_depth_escalates(self):
        reg = registry()
        del reg["ownership_depth"]
        self.assertEqual(self.route(evidence(registry=reg)).routing, "escalate")

    # ---- tool outages ----------------------------------------------------------------------

    def test_registry_unavailable(self):
        d = self.route(
            evidence(
                registry=None,
                failed_tools=("registry",),
                identity_status="not supplied",
            )
        )
        self.assertEqual(d.routing, "escalate")
        self.assertIsNone(d.facts["owner_names"])
        self.assertEqual(d.address_check, "unknown")
        self.assertEqual(d.incomplete_reasons, ["registry_unavailable"])
        self.assertEqual(d.missing_information, ["identity_document"])

    def test_screening_unavailable_is_not_treated_as_no_matches(self):
        d = self.route(evidence(screening=None, failed_tools=("screening",)))
        self.assertEqual(d.routing, "escalate")
        self.assertIsNone(d.pep)
        self.assertEqual(d.incomplete_reasons, ["screening_unavailable"])

    def test_transactions_unavailable(self):
        d = self.route(evidence(transactions=None, failed_tools=("transaction-summary",)))
        self.assertEqual(d.routing, "escalate")
        self.assertEqual(d.incomplete_reasons, ["transactions_unavailable"])

    def test_customer_unavailable_falls_back_to_intake_reference(self):
        d = self.route(evidence(customer=None, failed_tools=("customer",)))
        self.assertEqual(d.routing, "escalate")
        self.assertEqual(d.facts["entity_id"], "ENT-1")
        self.assertIsNone(d.facts["entity_type"])
        self.assertEqual(d.policy_ids, ["KYC-SCOPE-01"])


class StatutoryRuleRegistryTests(unittest.TestCase):
    """Cycle 3.1: reflective StatutoryRule registry ordering."""

    def test_ordered_rules_are_sorted_by_precedence_then_rule_id(self):
        import kyc_copilot.domain.rules  # noqa: F401 — register concrete subclasses

        rules = StatutoryRule.ordered_rules()
        self.assertEqual([r.rule_id for r in rules], list(EXPECTED_RULE_ORDER))
        precedences = [type(r).precedence for r in rules]
        self.assertEqual(precedences, sorted(precedences))
        self.assertEqual(precedences, [10, 11, 12, 14, 16, 20, 22, 30])


class CrossSourceConflictTests(unittest.TestCase):
    """Cycle 3.2: non-address cross-source conflicts escalate without picking a winner."""

    @classmethod
    def setUpClass(cls):
        cls.store = SqliteKnowledgeStore(":memory:")
        ingest(DEV, cls.store)
        cls.find = cls.store.find_policies

    @classmethod
    def tearDownClass(cls):
        cls.store.close()

    def route(self, ev):
        return decide(ev, self.find)

    def test_disputed_jurisdiction_escalates_without_product_policy(self):
        d = self.route(evidence(filing_jurisdiction="Birch"))
        self.assertEqual(d.routing, "escalate")
        self.assertIn("jurisdiction_conflict", d.reasons)
        self.assertIsNone(d.facts["jurisdiction"])
        self.assertEqual(d.policy_ids, ["KYC-SCOPE-01"])

    def test_entity_ref_conflict_escalates(self):
        d = self.route(evidence(entity_ref="ENT-OTHER"))
        self.assertEqual(d.routing, "escalate")
        self.assertIn("entity_ref_conflict", d.reasons)
        self.assertIsNone(d.facts["entity_id"])

    def test_holder_name_not_in_registry_owners_escalates(self):
        d = self.route(evidence(holder_name="Not An Owner"))
        self.assertEqual(d.routing, "escalate")
        self.assertIn("owner_name_conflict", d.reasons)

    def test_declared_owner_not_in_registry_owners_escalates(self):
        d = self.route(evidence(declared_owner="Not An Owner"))
        self.assertEqual(d.routing, "escalate")
        self.assertIn("owner_name_conflict", d.reasons)

    def test_birth_year_conflict_escalates(self):
        d = self.route(evidence(customer=customer(birth_year=1990), birth_year=1985))
        self.assertEqual(d.routing, "escalate")
        self.assertIn("birth_year_conflict", d.reasons)

    def test_missing_filing_jurisdiction_is_not_a_conflict(self):
        d = self.route(evidence(filing_jurisdiction=None))
        self.assertEqual(d.routing, "complete_review")
        self.assertNotIn("jurisdiction_conflict", d.reasons)

    def test_missing_holder_name_alone_is_not_owner_conflict(self):
        d = self.route(evidence(holder_name=None))
        self.assertNotIn("owner_name_conflict", d.reasons)


class ThreeWayAddressAndIdentityTests(unittest.TestCase):
    """Cycle 3.3: 3-way address compare + identity holder / not-included checks."""

    @classmethod
    def setUpClass(cls):
        cls.store = SqliteKnowledgeStore(":memory:")
        ingest(DEV, cls.store)
        cls.find = cls.store.find_policies

    @classmethod
    def tearDownClass(cls):
        cls.store.close()

    def route(self, ev):
        return decide(ev, self.find)

    def test_filing_address_mismatch_requests_explanation(self):
        d = self.route(evidence(filing_address="999 Other Walk, Alder."))
        self.assertEqual(d.routing, "request_information")
        self.assertIn("address_explanation", d.missing_information)
        self.assertEqual(d.address_check, "different")

    def test_missing_corporate_filing_address_is_not_a_difference(self):
        d = self.route(evidence(filing_address=None))
        self.assertEqual(d.routing, "complete_review")
        self.assertNotIn("address_explanation", d.missing_information)

    def test_three_present_addresses_same_completes(self):
        d = self.route(evidence())
        self.assertEqual(d.routing, "complete_review")
        self.assertEqual(d.address_check, "same")

    def test_missing_holder_name_requests_identity_document(self):
        d = self.route(
            evidence(
                holder_name=None,
                identity_status="attached",
                identity_document_present=True,
                identity_not_supplied=False,
            )
        )
        self.assertEqual(d.routing, "request_information")
        self.assertIn("identity_document", d.missing_information)

    def test_identity_not_supplied_flag_requests_identity_document(self):
        d = self.route(
            evidence(
                identity_not_supplied=True,
                identity_status="attached",
                identity_document_present=True,
                holder_name=None,
            )
        )
        self.assertEqual(d.routing, "request_information")
        self.assertIn("identity_document", d.missing_information)


if __name__ == "__main__":
    unittest.main()
