"""Deterministic review rules from KYC-SCOPE-01 and policy versions. No I/O, no model.

Routing precedence (KYC-SCOPE-01):
  1. escalate: unsupported scope, tool outage, cross-source conflict, deep ownership, screening
  2. request_information: missing identity document or address discrepancy
  3. enhanced_due_diligence: PEP indicator or monthly total strictly above the policy threshold
  4. complete_review
Missing-information fields are kept even when a higher rule wins.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType
from typing import Any, ClassVar

from kyc_copilot.contracts.interfaces import AddressCanonicalizer, StatutoryRule
from kyc_copilot.contracts.models import CaseEvidence, Decision, Policy

SCOPE_ID = "KYC-SCOPE-01"
SUPPORTED = {
    ("limited_company", "Alder"),
    ("limited_company", "Birch"),
    ("sole_proprietor", "Alder"),
}
KNOWN_MATCH_TYPES = ("exact", "near")
TOOL_LABELS = {
    "customer": "customer",
    "registry": "registry",
    "screening": "screening",
    "transaction-summary": "transactions",
}

# US street suffixes / directionals (ASSUMPTIONS.md 3.1). Unknown tokens stay verbatim.
_ADDRESS_TOKEN_MAP = MappingProxyType(
    {
        "st": "street",
        "ave": "avenue",
        "av": "avenue",
        "rd": "road",
        "blvd": "boulevard",
        "dr": "drive",
        "ln": "lane",
        "ct": "court",
        "pl": "place",
        "sq": "square",
        "ter": "terrace",
        "pkwy": "parkway",
        "hwy": "highway",
        "cir": "circle",
        "ste": "suite",
        "apt": "apartment",
        "n": "north",
        "s": "south",
        "e": "east",
        "w": "west",
        "ne": "northeast",
        "nw": "northwest",
        "se": "southeast",
        "sw": "southwest",
    }
)


@dataclass(frozen=True, slots=True)
class TokenMapAddressCanonicalizer:
    """Tier-1 in-memory canonicalizer: deterministic, never raises on non-US tokens."""

    def canonicalize(self, raw_address: str) -> str:
        text = unicodedata.normalize("NFKC", raw_address).casefold()
        words = re.sub(r"[^\w\s]", " ", text).split()
        return " ".join(_ADDRESS_TOKEN_MAP.get(w, w) for w in words)


DEFAULT_CANONICALIZER: AddressCanonicalizer = TokenMapAddressCanonicalizer()


def normalize_address(
    text: str, canonicalizer: AddressCanonicalizer = DEFAULT_CANONICALIZER
) -> str:
    return canonicalizer.canonicalize(text)


def compare_addresses(
    a: str | None,
    b: str | None,
    canonicalizer: AddressCanonicalizer = DEFAULT_CANONICALIZER,
) -> str:
    if not isinstance(a, str) or not isinstance(b, str) or not a.strip() or not b.strip():
        return "unknown"
    if a == b:
        return "same"
    left = canonicalizer.canonicalize(a)
    right = canonicalizer.canonicalize(b)
    return "normalized_same" if left == right else "different"


@dataclass
class _Scratch:
    find_policies: Callable[[str, str, date], list[Policy]]
    escalate: list[str] = field(default_factory=list)
    request: list[str] = field(default_factory=list)
    edd: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    incomplete: list[str] = field(default_factory=list)
    classification: str = "kyc_review"
    policy: Policy | None = None
    policy_ids: list[str] = field(default_factory=lambda: [SCOPE_ID])
    address_check: str = "unknown"
    matches: list[dict[str, Any]] = field(default_factory=list)
    pep: bool | None = None
    monthly_total: int | float | None = None
    entity_type: str | None = None
    jurisdiction: str | None = None
    entity_id: str | None = None
    jurisdiction_disputed: bool = False
    entity_ref_disputed: bool = False
    registry_inactive: bool = False
    owners_unusable: bool = False


_ACTIVE: ContextVar[_Scratch | None] = ContextVar("kyc_rule_scratch", default=None)


def _scratch() -> _Scratch:
    """Scratch for the in-flight decide() run; rules must not run outside that context."""
    active = _ACTIVE.get()
    if active is None:
        raise RuntimeError("StatutoryRule.apply requires an active decide() scratch")
    return active


def _number(value: object) -> int | float | None:
    """Accept int/float only; bool is excluded so True/False never count as amounts."""
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _registry_active(registry: dict[str, Any] | None) -> bool:
    """A registry body is usable only when it says registry_status is active."""
    return isinstance(registry, dict) and registry.get("registry_status") == "active"


def _owner_names(registry: dict[str, Any] | None) -> list[str] | None:
    """Usable owner names, or None when the registry or the owner list cannot be used."""
    if not _registry_active(registry):
        return None
    assert registry is not None
    owners = registry.get("owners")
    if not isinstance(owners, list):
        return None
    names = [
        o["name"]
        for o in owners
        if isinstance(o, dict) and isinstance(o.get("name"), str) and o["name"].strip()
    ]
    return names or None


def _present_text(value: object) -> str | None:
    """Non-blank string, else None so missing fields are not treated as conflicts."""
    if isinstance(value, str) and value.strip():
        return value
    return None


def _combine_address_checks(results: list[str]) -> str:
    """Worst pairwise result wins: different > unknown > normalized_same > same."""
    if not results:
        return "unknown"
    if "different" in results:
        return "different"
    if "unknown" in results:
        return "unknown"
    if "normalized_same" in results:
        return "normalized_same"
    return "same"


class ToolAvailabilityRule(StatutoryRule):
    rule_id: ClassVar[str] = "tool_availability"
    precedence: ClassVar[int] = 10

    def apply(self, evidence: CaseEvidence) -> None:
        """Escalate when any required read tool failed after retries."""
        scratch = _scratch()
        incomplete = [f"{TOOL_LABELS.get(t, t)}_unavailable" for t in evidence.failed_tools]
        scratch.incomplete.extend(incomplete)
        scratch.escalate.extend(incomplete)


class CrossSourceConflictRule(StatutoryRule):
    rule_id: ClassVar[str] = "cross_source_conflict"
    precedence: ClassVar[int] = 11

    def apply(self, evidence: CaseEvidence) -> None:
        """Escalate non-address conflicts; disputed jurisdiction blocks product policy selection."""
        scratch = _scratch()
        customer = evidence.customer
        registry = evidence.registry
        cust_jurisdiction = customer.get("jurisdiction") if customer else None
        filing_jurisdiction = evidence.filing_jurisdiction
        if _present_text(cust_jurisdiction) and _present_text(filing_jurisdiction):
            if cust_jurisdiction != filing_jurisdiction:
                scratch.escalate.append("jurisdiction_conflict")
                scratch.jurisdiction_disputed = True
                scratch.jurisdiction = None
                scratch.policy = None
                scratch.policy_ids = [SCOPE_ID]

        cust_entity = customer.get("entity_id") if customer else None
        if _present_text(evidence.entity_ref) and _present_text(cust_entity):
            if evidence.entity_ref != cust_entity:
                scratch.escalate.append("entity_ref_conflict")
                scratch.entity_ref_disputed = True
                scratch.entity_id = None

        cust_company = _present_text(customer.get("company_name")) if customer else None
        filing_company = _present_text(evidence.company_name)
        if cust_company and filing_company and cust_company != filing_company:
            scratch.escalate.append("company_name_conflict")

        if registry is not None and not _registry_active(registry):
            scratch.registry_inactive = True
            scratch.escalate.append("registry_not_active")
        elif registry is not None:
            owners = _owner_names(registry)
            if owners is None:
                scratch.owners_unusable = True
                scratch.escalate.append("owners_not_established")
            elif _present_text(evidence.holder_name) and evidence.holder_name not in owners:
                scratch.escalate.append("owner_name_conflict")
            elif _present_text(evidence.declared_owner) and evidence.declared_owner not in owners:
                scratch.escalate.append("owner_name_conflict")

        cust_birth = customer.get("birth_year") if customer else None
        if cust_birth is not None and evidence.birth_year is not None:
            if cust_birth != evidence.birth_year:
                scratch.escalate.append("birth_year_conflict")


class ScopeAndPolicyRule(StatutoryRule):
    rule_id: ClassVar[str] = "scope_and_policy"
    precedence: ClassVar[int] = 12

    def apply(self, evidence: CaseEvidence) -> None:
        """Select the single effective product policy, or escalate unsupported/ambiguous scope."""
        scratch = _scratch()
        customer = evidence.customer
        scratch.entity_type = customer.get("entity_type") if customer else None
        if not scratch.jurisdiction_disputed:
            scratch.jurisdiction = customer.get("jurisdiction") if customer else None
        if not scratch.entity_ref_disputed:
            scratch.entity_id = (
                customer.get("entity_id") if customer else None
            ) or evidence.entity_ref

        entity_type = scratch.entity_type
        jurisdiction = scratch.jurisdiction
        if scratch.jurisdiction_disputed:
            return
        if customer is not None and not scratch.jurisdiction_disputed:
            if _present_text(entity_type) is None or _present_text(jurisdiction) is None:
                scratch.escalate.append("customer_fields_missing")
        if entity_type and jurisdiction and (entity_type, jurisdiction) not in SUPPORTED:
            scratch.classification = "unsupported"
            scratch.escalate.append("unsupported_scope")
        elif entity_type and jurisdiction:
            if evidence.review_date is None:
                scratch.escalate.append("review_date_missing")
            else:
                found = scratch.find_policies(entity_type, jurisdiction, evidence.review_date)
                if len(found) == 1:
                    scratch.policy = found[0]
                    scratch.policy_ids = [found[0].source_id, SCOPE_ID]
                else:
                    scratch.escalate.append(
                        "no_applicable_policy" if not found else "multiple_policies"
                    )


class DocumentFaultRule(StatutoryRule):
    rule_id: ClassVar[str] = "document_faults"
    precedence: ClassVar[int] = 13

    def apply(self, evidence: CaseEvidence) -> None:
        """Escalate missing, duplicate, empty, unreadable, or self-contradictory documents."""
        scratch = _scratch()
        scratch.escalate.extend(evidence.document_faults)


class OwnershipDepthRule(StatutoryRule):
    rule_id: ClassVar[str] = "ownership_depth"
    precedence: ClassVar[int] = 14

    def apply(self, evidence: CaseEvidence) -> None:
        """Escalate when ownership depth is unknown or deeper than one layer."""
        scratch = _scratch()
        registry = evidence.registry
        if registry is None or _scratch().registry_inactive:
            return
        depth = _number(registry.get("ownership_depth"))
        if depth is None:
            scratch.escalate.append("ownership_unknown")
        elif depth > 1:
            scratch.escalate.append("ownership_depth")


class ScreeningMatchRule(StatutoryRule):
    rule_id: ClassVar[str] = "screening_match"
    precedence: ClassVar[int] = 16

    def apply(self, evidence: CaseEvidence) -> None:
        """Escalate exact/near/unrecognized screening hits and record the PEP flag."""
        scratch = _scratch()
        screening = evidence.screening
        if screening is None:
            return
        raw = screening.get("matches")
        if not isinstance(raw, list):
            scratch.escalate.append("screening_unreadable")
        else:
            matches = [m for m in raw if isinstance(m, dict)]
            scratch.matches = matches
            kinds = {m.get("match_type") for m in matches}
            if "exact" in kinds:
                scratch.escalate.append("screening_exact_match")
            if "near" in kinds:
                scratch.escalate.append("screening_near_match")
            if kinds - set(KNOWN_MATCH_TYPES) or len(matches) != len(raw):
                scratch.escalate.append("screening_unrecognized_match")
        scratch.pep = screening.get("pep_indicator") is True


class IdentityDocumentRule(StatutoryRule):
    rule_id: ClassVar[str] = "identity_document"
    precedence: ClassVar[int] = 20

    def apply(self, evidence: CaseEvidence) -> None:
        """Request identity unless name, birth year, and document reference are all supplied."""
        scratch = _scratch()
        status = (evidence.identity_status or "").strip().casefold()
        missing_holder = _present_text(evidence.holder_name) is None
        missing_reference = _present_text(evidence.document_reference) is None
        if (
            status != "attached"
            or not evidence.identity_document_present
            or evidence.identity_not_supplied
            or missing_holder
            or evidence.birth_year is None
            or missing_reference
        ):
            scratch.missing.append("identity_document")
            scratch.request.append("identity_document_missing")


class AddressComparisonRule(StatutoryRule):
    rule_id: ClassVar[str] = "address_comparison"
    precedence: ClassVar[int] = 22

    def apply(self, evidence: CaseEvidence) -> None:
        """Request address_explanation only when all three addresses are present and differ."""
        scratch = _scratch()
        customer = evidence.customer
        registry = evidence.registry
        if customer is None or not _registry_active(registry) or scratch.registry_inactive:
            scratch.address_check = "unknown"
            return

        addresses = [
            _present_text(customer.get("registered_address")),
            _present_text(registry.get("registered_address")),
            _present_text(evidence.filing_address),
        ]
        if any(value is None for value in addresses):
            scratch.address_check = "unknown"
            return

        present = [value for value in addresses if value is not None]
        pairwise = [
            compare_addresses(present[i], present[j])
            for i in range(len(present))
            for j in range(i + 1, len(present))
        ]
        scratch.address_check = _combine_address_checks(pairwise)
        if scratch.address_check == "different":
            scratch.missing.append("address_explanation")
            scratch.request.append("address_mismatch")


class EddAndPepRule(StatutoryRule):
    rule_id: ClassVar[str] = "edd_and_pep"
    precedence: ClassVar[int] = 30

    def apply(self, evidence: CaseEvidence) -> None:
        """Flag EDD for PEP or monthly total strictly above the selected policy threshold."""
        scratch = _scratch()
        if scratch.pep:
            scratch.edd.append("pep_indicator")
        transactions = evidence.transactions
        if transactions is None:
            return
        if transactions.get("currency") != "XCR":
            scratch.escalate.append("currency_mismatch")
        monthly_total = _number(transactions.get("monthly_total"))
        scratch.monthly_total = monthly_total
        if monthly_total is None:
            scratch.escalate.append("transactions_unreadable")
        elif scratch.policy is not None and monthly_total > scratch.policy.edd_threshold:
            scratch.edd.append("monthly_total_above_threshold")


def decide(ev: CaseEvidence, find_policies: Callable[[str, str, date], list[Policy]]) -> Decision:
    """Run registered rules in precedence order and collapse reasons into one routing decision."""
    scratch = _Scratch(find_policies=find_policies)
    token = _ACTIVE.set(scratch)
    try:
        for rule in StatutoryRule.ordered_rules():
            rule.apply(ev)
    finally:
        _ACTIVE.reset(token)

    if scratch.escalate:
        routing = "escalate"
    elif scratch.request:
        routing = "request_information"
    elif scratch.edd:
        routing = "enhanced_due_diligence"
    else:
        routing = "complete_review"

    facts = {
        "entity_id": scratch.entity_id,
        "entity_type": scratch.entity_type,
        "jurisdiction": scratch.jurisdiction,
        "review_date": ev.review_date.isoformat() if ev.review_date else None,
        "owner_names": (
            None
            if ev.registry is None or scratch.registry_inactive or scratch.owners_unusable
            else _owner_names(ev.registry)
        ),
    }
    return Decision(
        scratch.classification,
        routing,
        scratch.policy_ids,
        scratch.policy,
        facts,
        scratch.missing,
        scratch.escalate + scratch.request + scratch.edd,
        scratch.incomplete,
        scratch.address_check,
        scratch.matches,
        scratch.pep,
        scratch.monthly_total,
    )


__all__ = [
    "SCOPE_ID",
    "SUPPORTED",
    "CaseEvidence",
    "Decision",
    "DEFAULT_CANONICALIZER",
    "TokenMapAddressCanonicalizer",
    "compare_addresses",
    "decide",
    "normalize_address",
    "ToolAvailabilityRule",
    "CrossSourceConflictRule",
    "ScopeAndPolicyRule",
    "OwnershipDepthRule",
    "DocumentFaultRule",
    "ScreeningMatchRule",
    "IdentityDocumentRule",
    "AddressComparisonRule",
    "EddAndPepRule",
]
