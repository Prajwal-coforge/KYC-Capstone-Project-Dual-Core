"""Thirty synthetic discrepancy cases. These are not the graded dev set.

Each case is built from aligned evidence, then one discrepancy is applied. Routing
comes from decide(), not from the case id. The same evidence is decided twice.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import date

from kyc_copilot.adapters.sqlite_store import SqliteKnowledgeStore
from kyc_copilot.domain.packet import build_packet
from kyc_copilot.domain.rules import decide
from kyc_copilot.narrative.narrator import TemplateNarrator
from kyc_copilot.runner.ingest import ingest
from tests.helpers import DEV
from tests.test_rules import customer, evidence, match, registry, screening, total

ALLOWED_MISSING = {"identity_document", "address_explanation"}


def _without_depth():
    body = registry()
    del body["ownership_depth"]
    return evidence(case_id="SYN-19", registry=body)


def _pep_string():
    return evidence(
        case_id="SYN-06",
        screening={
            "source_id": "C1-SCREENING",
            "matches": [],
            "pep_indicator": "true",
        },
    )


CASES = (
    ("SYN-01", "aligned sources", lambda: evidence(case_id="SYN-01"), "complete_review", None),
    (
        "SYN-02",
        "near screening match",
        lambda: evidence(case_id="SYN-02", screening=screening(match("near"))),
        "escalate",
        "screening_near_match",
    ),
    (
        "SYN-03",
        "exact screening match",
        lambda: evidence(case_id="SYN-03", screening=screening(match("exact"))),
        "escalate",
        "screening_exact_match",
    ),
    (
        "SYN-04",
        "exact and near matches together",
        lambda: evidence(
            case_id="SYN-04",
            screening=screening(match("exact"), match("near", "Bo Lin")),
        ),
        "escalate",
        "screening_exact_match",
    ),
    (
        "SYN-05",
        "PEP flag is boolean true",
        lambda: evidence(case_id="SYN-05", screening=screening(pep=True)),
        "enhanced_due_diligence",
        "pep_indicator",
    ),
    ("SYN-06", "PEP flag is the text true", _pep_string, "complete_review", None),
    (
        "SYN-07",
        "monthly total equal to the Alder threshold",
        lambda: evidence(case_id="SYN-07", transactions=total(50000)),
        "complete_review",
        None,
    ),
    (
        "SYN-08",
        "monthly total one unit above the Alder threshold",
        lambda: evidence(case_id="SYN-08", transactions=total(50001)),
        "enhanced_due_diligence",
        "monthly_total_above_threshold",
    ),
    (
        "SYN-09",
        "customer and registry addresses differ",
        lambda: evidence(
            case_id="SYN-09",
            registry=registry(registered_address="200 Other Road, Alder"),
        ),
        "request_information",
        "address_mismatch",
    ),
    (
        "SYN-10",
        "address differs only by punctuation",
        lambda: evidence(case_id="SYN-10", filing_address="100 Orchard Walk Alder"),
        "complete_review",
        None,
    ),
    (
        "SYN-11",
        "customer jurisdiction and filing jurisdiction differ",
        lambda: evidence(case_id="SYN-11", filing_jurisdiction="Birch"),
        "escalate",
        "jurisdiction_conflict",
    ),
    (
        "SYN-12",
        "intake entity reference differs from the customer record",
        lambda: evidence(case_id="SYN-12", entity_ref="ENT-OTHER"),
        "escalate",
        "entity_ref_conflict",
    ),
    (
        "SYN-13",
        "identity holder is not a registry owner",
        lambda: evidence(case_id="SYN-13", holder_name="Bo Lin"),
        "escalate",
        "owner_name_conflict",
    ),
    (
        "SYN-14",
        "declared owner is not a registry owner",
        lambda: evidence(case_id="SYN-14", declared_owner="Bo Lin"),
        "escalate",
        "owner_name_conflict",
    ),
    (
        "SYN-15",
        "registry tool failed",
        lambda: evidence(case_id="SYN-15", registry=None, failed_tools=("registry",)),
        "escalate",
        "registry_unavailable",
    ),
    (
        "SYN-16",
        "registry is dissolved",
        lambda: evidence(case_id="SYN-16", registry=registry(registry_status="dissolved")),
        "escalate",
        "registry_not_active",
    ),
    (
        "SYN-17",
        "registry lists no owners",
        lambda: evidence(case_id="SYN-17", registry=registry(owners=[])),
        "escalate",
        "owners_not_established",
    ),
    (
        "SYN-18",
        "ownership is two layers deep",
        lambda: evidence(case_id="SYN-18", registry=registry(ownership_depth=2)),
        "escalate",
        "ownership_depth",
    ),
    ("SYN-19", "ownership depth was not supplied", _without_depth, "escalate", "ownership_unknown"),
    (
        "SYN-20",
        "identity document was not attached",
        lambda: evidence(case_id="SYN-20", identity_status="missing"),
        "request_information",
        "identity_document_missing",
    ),
    (
        "SYN-21",
        "identity document was marked not supplied",
        lambda: evidence(case_id="SYN-21", identity_not_supplied=True),
        "request_information",
        "identity_document_missing",
    ),
    (
        "SYN-22",
        "identity document has a blank holder name",
        lambda: evidence(case_id="SYN-22", holder_name="   "),
        "request_information",
        "identity_document_missing",
    ),
    (
        "SYN-23",
        "PEP and an address mismatch; the request outranks EDD",
        lambda: evidence(
            case_id="SYN-23",
            screening=screening(pep=True),
            registry=registry(registered_address="200 Other Road, Alder"),
        ),
        "request_information",
        "address_mismatch",
    ),
    (
        "SYN-24",
        "missing identity and a total above threshold; the request outranks EDD",
        lambda: evidence(
            case_id="SYN-24",
            identity_status="missing",
            transactions=total(50001),
        ),
        "request_information",
        "identity_document_missing",
    ),
    (
        "SYN-25",
        "exact screening match and an address mismatch; escalation keeps the gap",
        lambda: evidence(
            case_id="SYN-25",
            screening=screening(match("exact")),
            registry=registry(registered_address="200 Other Road, Alder"),
        ),
        "escalate",
        "screening_exact_match",
    ),
    (
        "SYN-26",
        "transactions are not in XCR",
        lambda: evidence(
            case_id="SYN-26",
            transactions={**total(12000), "currency": "USD"},
        ),
        "escalate",
        "currency_mismatch",
    ),
    (
        "SYN-27",
        "jurisdiction is outside the supported set",
        lambda: evidence(case_id="SYN-27", customer=customer(jurisdiction="Cedar")),
        "escalate",
        "unsupported_scope",
    ),
    (
        "SYN-28",
        "sole proprietor total equal to its threshold",
        lambda: evidence(
            case_id="SYN-28",
            customer=customer(entity_type="sole_proprietor"),
            transactions=total(25000),
        ),
        "complete_review",
        None,
    ),
    (
        "SYN-29",
        "sole proprietor total one unit above its threshold",
        lambda: evidence(
            case_id="SYN-29",
            customer=customer(entity_type="sole_proprietor"),
            transactions=total(25001),
        ),
        "enhanced_due_diligence",
        "monthly_total_above_threshold",
    ),
    (
        "SYN-30",
        "review date is the last day of the earlier Alder policy",
        lambda: evidence(
            case_id="SYN-30",
            review_date=date(2026, 8, 31),
            transactions=total(40000),
        ),
        "enhanced_due_diligence",
        "monthly_total_above_threshold",
    ),
)


class SyntheticEdgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = SqliteKnowledgeStore(":memory:")
        ingest(DEV, cls.store)

    @classmethod
    def tearDownClass(cls):
        cls.store.close()

    def test_thirty_synthetic_discrepancies_route_twice_the_same_way(self):
        self.assertEqual(len(CASES), 30)
        seen = set()
        for case_id, _label, build, routing, reason in CASES:
            self.assertNotIn(case_id, seen)
            seen.add(case_id)
            ev = build()
            self.assertEqual(ev.case_id, case_id)
            first = decide(ev, self.store.find_policies)
            second = decide(ev, self.store.find_policies)
            self.assertEqual(first.routing, second.routing, case_id)
            self.assertEqual(first.reasons, second.reasons, case_id)
            self.assertEqual(first.facts, second.facts, case_id)
            self.assertEqual(first.missing_information, second.missing_information, case_id)
            self.assertEqual(first.routing, routing, case_id)
            if reason is None:
                self.assertEqual(first.reasons, [], case_id)
            else:
                self.assertIn(reason, first.reasons, case_id)
            self.assertTrue(set(first.missing_information) <= ALLOWED_MISSING, case_id)
            renamed = decide(
                replace(ev, case_id=case_id + "-RENAMED"),
                self.store.find_policies,
            )
            self.assertEqual(renamed.routing, first.routing, case_id)

    def test_registry_gaps_leave_owner_names_null(self):
        for case_id in ("SYN-15", "SYN-16", "SYN-17"):
            ev = next(build() for cid, _label, build, _routing, _reason in CASES if cid == case_id)
            decision = decide(ev, self.store.find_policies)
            self.assertIsNone(decision.facts["owner_names"], case_id)

    def test_packets_keep_the_route_and_omit_the_restricted_token(self):
        narrator = TemplateNarrator()
        for case_id, _label, build, routing, _reason in CASES:
            ev = build()
            decision = decide(ev, self.store.find_policies)
            packet = build_packet(decision, ev, None, self.store, narrator)
            self.assertEqual(packet["case_id"], case_id)
            self.assertEqual(packet["routing"], routing)
            self.assertGreaterEqual(len(packet["narrative"]), 20, case_id)
            self.assertNotIn("private_token", json.dumps(packet))

    def test_exact_and_near_are_both_recorded(self):
        ev = next(build() for cid, _label, build, _r, _reason in CASES if cid == "SYN-04")
        decision = decide(ev, self.store.find_policies)
        self.assertIn("screening_exact_match", decision.reasons)
        self.assertIn("screening_near_match", decision.reasons)

    def test_a_disputed_jurisdiction_does_not_select_a_product_policy(self):
        ev = next(build() for cid, _label, build, _r, _reason in CASES if cid == "SYN-11")
        decision = decide(ev, self.store.find_policies)
        self.assertEqual(decision.policy_ids, ["KYC-SCOPE-01"])
        self.assertIsNone(decision.facts["jurisdiction"])

    def test_the_earlier_alder_policy_is_the_one_on_its_last_day(self):
        ev = next(build() for cid, _label, build, _r, _reason in CASES if cid == "SYN-30")
        decision = decide(ev, self.store.find_policies)
        self.assertIn("KYC-POLICY-ALDER-LTD-V1", decision.policy_ids)

    def test_an_unsupported_jurisdiction_is_classified_unsupported(self):
        ev = next(build() for cid, _label, build, _r, _reason in CASES if cid == "SYN-27")
        decision = decide(ev, self.store.find_policies)
        self.assertEqual(decision.classification, "unsupported")
