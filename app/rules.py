"""Deterministic review rules from KYC-SCOPE-01 and the policy versions. No I/O, no model.

Routing precedence (KYC-SCOPE-01):
  1. escalate: unsupported scope, unavailable tool data, deep ownership, any exact/near match
  2. request_information: missing identity document or address discrepancy
  3. enhanced_due_diligence: PEP indicator or monthly total strictly above the policy threshold
  4. complete_review
Missing-information fields are kept even when a higher rule wins.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from .models import Policy

SCOPE_ID = "KYC-SCOPE-01"
SUPPORTED = {("limited_company", "Alder"), ("limited_company", "Birch"), ("sole_proprietor", "Alder")}
KNOWN_MATCH_TYPES = ("exact", "near")
TOOL_LABELS = {"customer": "customer", "registry": "registry", "screening": "screening",
               "transaction-summary": "transactions"}

# US street suffixes and directionals (ASSUMPTIONS.md 3.1). Anything else is compared literally,
# so an unrecognized abbreviation counts as a material difference.
_ABBREVIATIONS = {
    "st": "street", "ave": "avenue", "av": "avenue", "rd": "road", "blvd": "boulevard",
    "dr": "drive", "ln": "lane", "ct": "court", "pl": "place", "sq": "square", "ter": "terrace",
    "pkwy": "parkway", "hwy": "highway", "cir": "circle", "ste": "suite", "apt": "apartment",
    "n": "north", "s": "south", "e": "east", "w": "west",
    "ne": "northeast", "nw": "northwest", "se": "southeast", "sw": "southwest",
}


@dataclass(frozen=True)
class CaseEvidence:
    case_id: str
    review_date: date | None
    entity_ref: str | None
    identity_status: str | None
    identity_document_present: bool
    customer: dict | None
    registry: dict | None
    screening: dict | None
    transactions: dict | None
    failed_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class Decision:
    classification: str
    routing: str
    policy_ids: list[str]
    policy: Policy | None
    facts: dict
    missing_information: list[str]
    reasons: list[str]
    incomplete_reasons: list[str]
    address_check: str  # same | normalized_same | different | unknown
    screening_matches: list[dict] = field(default_factory=list)
    pep: bool | None = None
    monthly_total: int | float | None = None


def normalize_address(text: str) -> str:
    words = re.sub(r"[^\w\s]", " ", text.casefold()).split()
    return " ".join(_ABBREVIATIONS.get(w, w) for w in words)


def compare_addresses(a: str | None, b: str | None) -> str:
    if not isinstance(a, str) or not isinstance(b, str) or not a.strip() or not b.strip():
        return "unknown"
    if a == b:
        return "same"
    return "normalized_same" if normalize_address(a) == normalize_address(b) else "different"


def _number(value) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _owner_names(registry: dict | None) -> list[str] | None:
    if registry is None:
        return None  # KYC-SCOPE-01: missing registry response means null, not an empty list
    owners = registry.get("owners")
    if not isinstance(owners, list):
        return None
    return [o["name"] for o in owners if isinstance(o, dict) and isinstance(o.get("name"), str)]


def decide(ev: CaseEvidence, find_policies: Callable[[str, str, date], list[Policy]]) -> Decision:
    escalate: list[str] = []
    request: list[str] = []
    edd: list[str] = []
    missing: list[str] = []
    incomplete = [f"{TOOL_LABELS.get(t, t)}_unavailable" for t in ev.failed_tools]
    escalate += incomplete

    customer, registry, screening, transactions = ev.customer, ev.registry, ev.screening, ev.transactions
    entity_type = customer.get("entity_type") if customer else None
    jurisdiction = customer.get("jurisdiction") if customer else None
    entity_id = (customer.get("entity_id") if customer else None) or ev.entity_ref

    # Scope and policy
    classification = "kyc_review"
    policy: Policy | None = None
    policy_ids = [SCOPE_ID]
    if entity_type and jurisdiction and (entity_type, jurisdiction) not in SUPPORTED:
        classification = "unsupported"
        escalate.append("unsupported_scope")
    elif entity_type and jurisdiction:
        if ev.review_date is None:
            escalate.append("review_date_missing")
        else:
            found = find_policies(entity_type, jurisdiction, ev.review_date)
            if len(found) == 1:
                policy = found[0]
                policy_ids = [policy.source_id, SCOPE_ID]
            else:
                escalate.append("no_applicable_policy" if not found else "multiple_policies")

    # Ownership
    if registry is not None:
        depth = _number(registry.get("ownership_depth"))
        if depth is None:
            escalate.append("ownership_unknown")
        elif depth > 1:
            escalate.append("ownership_depth")

    # Screening: exact and near both escalate; never resolved here
    matches: list[dict] = []
    pep: bool | None = None
    if screening is not None:
        raw = screening.get("matches")
        if not isinstance(raw, list):
            escalate.append("screening_unreadable")
        else:
            matches = [m for m in raw if isinstance(m, dict)]
            kinds = {m.get("match_type") for m in matches}
            if "exact" in kinds:
                escalate.append("screening_exact_match")
            if "near" in kinds:
                escalate.append("screening_near_match")
            if kinds - set(KNOWN_MATCH_TYPES) or len(matches) != len(raw):
                escalate.append("screening_unrecognized_match")
        pep = screening.get("pep_indicator") is True

    # Missing information
    status = (ev.identity_status or "").strip().casefold()
    if status != "attached" or not ev.identity_document_present:
        missing.append("identity_document")
        request.append("identity_document_missing")
    address_check = "unknown"
    if customer is not None and registry is not None:
        address_check = compare_addresses(customer.get("registered_address"),
                                          registry.get("registered_address"))
        if address_check in ("different", "unknown"):
            missing.append("address_explanation")
            request.append("address_mismatch")

    # Enhanced due diligence
    monthly_total = None
    if pep:
        edd.append("pep_indicator")
    if transactions is not None:
        monthly_total = _number(transactions.get("monthly_total"))
        if monthly_total is None:
            escalate.append("transactions_unreadable")
        elif policy is not None and monthly_total > policy.edd_threshold:
            edd.append("monthly_total_above_threshold")

    if escalate:
        routing = "escalate"
    elif request:
        routing = "request_information"
    elif edd:
        routing = "enhanced_due_diligence"
    else:
        routing = "complete_review"

    facts = {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "jurisdiction": jurisdiction,
        "review_date": ev.review_date.isoformat() if ev.review_date else None,
        "owner_names": _owner_names(registry),
    }
    return Decision(classification, routing, policy_ids, policy, facts, missing,
                    escalate + request + edd, incomplete, address_check, matches, pep, monthly_total)
