"""Build the output-contract packet. Citations are exact quotes before they are kept.

Domain layer: contracts + same-layer rules only. Store I/O goes through KnowledgeStore.
"""

from __future__ import annotations

import re

from kyc_copilot.contracts.address import compare_addresses
from kyc_copilot.contracts.interfaces import KnowledgeStore, Narrator
from kyc_copilot.contracts.models import CaseEvidence, Decision, Document, Source
from kyc_copilot.contracts.redaction import json_fragment
from kyc_copilot.domain.rules import SCOPE_ID

# Short exact phrases from KYC-SCOPE-01 that justify each reason. Phrases that are not
# found in the supplied text are dropped, never invented.
SCOPE_PHRASES = {
    "unsupported_scope": (
        "use only KYC-SCOPE-01 and must escalate; classification is unsupported."
    ),
    "ownership_depth": "Ownership depth above 1 requires escalation, not invented resolution.",
    "ownership_unknown": "Ownership support: one direct level.",
    "screening_exact_match": "Exact matches require specialist review",
    "screening_near_match": "near matches remain unresolved identity candidates.",
    "screening_unrecognized_match": "Both exact and near matches must escalate.",
    "registry_unavailable": (
        "A missing registry response means owner_names is null, "
        "not an empty list or assumed owners."
    ),
    "registry_not_active": "unavailable registry",
    "owners_not_established": "not an empty list or assumed owners.",
    "customer_fields_missing": "Review date determines the applicable policy version.",
    "identity_document_missing": "Missing identity document is identity_document.",
    "address_mismatch": (
        "An address discrepancy requires address_explanation; never silently choose a source."
    ),
    "no_applicable_policy": "Review date determines the applicable policy version.",
    "multiple_policies": "Review date determines the applicable policy version.",
    "review_date_missing": "Review date determines the applicable policy version.",
    "pep_indicator": (
        "then enhanced_due_diligence for a PEP indicator or monthly amount above the policy"
    ),
    "monthly_total_above_threshold": (
        "then enhanced_due_diligence for a PEP indicator or monthly amount above the policy"
    ),
}
RETRY_PHRASE = "Retry failed tools at most twice (three total attempts), then stop and escalate."
COMPLETE_PHRASE = "otherwise complete_review."
_INSTRUCTION_LINE = re.compile(r"important|ignore previous|\bapprove\b", re.IGNORECASE)


def _line(content: str, prefix: str) -> str | None:
    for raw in content.split("\n"):
        line = raw.rstrip("\r")
        if line.startswith(prefix):
            return line
    return None


def _field_quote(content: str, prefix: str) -> str | None:
    """Exact quote starting at prefix (prefix may appear mid-line in filings)."""
    for raw in content.split("\n"):
        line = raw.rstrip("\r")
        idx = line.find(prefix)
        if idx >= 0:
            return line[idx:].rstrip()
    return None


def _case_doc(
    store: KnowledgeStore, case_id: str, doc_type: str
) -> tuple[str, Document, Source] | None:
    for source in store.case_documents(case_id):
        doc = store.get_document(source.source_id)
        if doc is None or doc.doc_type != doc_type:
            continue
        raw = store.get_source(source.source_id)
        if raw is None:
            continue
        return source.source_id, doc, raw
    return None


def _follow_up(field: str, decision: Decision, evidence: CaseEvidence) -> str:
    subject = decision.facts.get("entity_id") or evidence.case_id
    if field == "identity_document":
        return (
            f"Please provide a current identity document for the owner(s) of {subject} "
            "so the periodic review can be completed."
        )
    if field == "address_explanation":
        c = evidence.customer.get("registered_address") if evidence.customer else None
        r = evidence.registry.get("registered_address") if evidence.registry else None
        f = evidence.filing_address
        filing = f if isinstance(f, str) and f.strip() else None
        if compare_addresses(c, r) in ("same", "normalized_same") and filing is not None:
            return (
                f"Our customer and registry records list '{c}' but the corporate filing "
                f"lists '{filing}'. Please confirm which address is current and provide "
                "supporting evidence."
            )
        if filing is not None:
            return (
                f"Our records list the registered address as '{c}' while the registry "
                f"lists '{r}' and the corporate filing lists '{filing}'. "
                "Please confirm which address is current and provide supporting evidence."
            )
        return (
            f"Our records list the registered address as '{c}' while the registry lists '{r}'. "
            "Please confirm which address is current and provide supporting evidence."
        )
    return f"Please provide the missing {field.replace('_', ' ')} for {subject}."


def _append_conflict_document_citations(
    candidates: list[tuple[str, str, str | None]],
    decision: Decision,
    evidence: CaseEvidence,
    store: KnowledgeStore,
) -> None:
    reasons = set(decision.reasons)
    case_id = evidence.case_id

    need_corporate_address = (
        "address_explanation" in decision.missing_information
        or decision.address_check == "different"
    )
    need_corporate_jurisdiction = "jurisdiction_conflict" in reasons
    need_corporate_owner = "owner_name_conflict" in reasons and evidence.declared_owner
    if need_corporate_address or need_corporate_jurisdiction or need_corporate_owner:
        found = _case_doc(store, case_id, "corporate")
        if found is not None:
            sid, _doc, raw = found
            if need_corporate_address:
                candidates.append(
                    (
                        "Corporate filing registered address",
                        sid,
                        _field_quote(raw.content, "Registered address in supplied filing:"),
                    )
                )
            if need_corporate_jurisdiction:
                candidates.append(
                    (
                        "Corporate filing jurisdiction",
                        sid,
                        _field_quote(raw.content, "Filing jurisdiction:"),
                    )
                )
            if need_corporate_owner:
                candidates.append(
                    (
                        "Corporate declared owner",
                        sid,
                        _field_quote(raw.content, "Declared owner:"),
                    )
                )

    if "owner_name_conflict" in reasons or "birth_year_conflict" in reasons:
        found = _case_doc(store, case_id, "identity")
        if found is not None:
            sid, _doc, raw = found
            if "owner_name_conflict" in reasons:
                candidates.append(("Identity holder name", sid, _field_quote(raw.content, "Name:")))
            if "birth_year_conflict" in reasons:
                candidates.append(
                    ("Identity birth year", sid, _field_quote(raw.content, "Birth year:"))
                )

    if "entity_ref_conflict" in reasons:
        found = _case_doc(store, case_id, "intake")
        if found is not None:
            sid, _doc, raw = found
            candidates.append(
                (
                    "Intake entity reference",
                    sid,
                    _field_quote(raw.content, "Entity reference:"),
                )
            )


def build_citations(
    decision: Decision,
    evidence: CaseEvidence,
    intake_id: str | None,
    store: KnowledgeStore,
) -> list[dict]:
    d, ev = decision, evidence
    candidates: list[tuple[str, str, str | None]] = []  # (claim, source_id, quote)

    if intake_id:
        intake = store.get_source(intake_id)
        if intake:
            candidates.append(
                (
                    "Review date for this periodic review",
                    intake_id,
                    _line(intake.content, "Review date:"),
                )
            )
            candidates.append(
                (
                    "Identity document status reported at intake",
                    intake_id,
                    _line(intake.content, "Identity document:"),
                )
            )

    scope = store.get_procedure(SCOPE_ID)
    if scope:
        candidates.append(
            (
                "Supported entity types and jurisdictions",
                SCOPE_ID,
                _line(scope.content, "Supported matrix:"),
            )
        )
        candidates.append(
            (
                "Routing precedence applied",
                SCOPE_ID,
                _line(scope.content, "Routing precedence:"),
            )
        )
        for reason in dict.fromkeys(d.reasons):
            if reason in SCOPE_PHRASES:
                candidates.append(
                    (f"Rule for {reason.replace('_', ' ')}", SCOPE_ID, SCOPE_PHRASES[reason])
                )
        if d.incomplete_reasons:
            candidates.append(("Bounded retries, then escalation", SCOPE_ID, RETRY_PHRASE))
        if d.routing == "complete_review":
            candidates.append(("No higher-priority rule applies", SCOPE_ID, COMPLETE_PHRASE))

    if d.policy:
        policy = store.get_source(d.policy.source_id)
        if policy:
            for prefix, claim in (
                ("Effective from:", "Policy version in force on the review date"),
                ("Effective through:", "Policy version in force on the review date"),
                ("EDD monthly threshold:", "Monthly threshold for enhanced due diligence"),
            ):
                candidates.append((claim, d.policy.source_id, _line(policy.content, prefix)))
            if "currency_mismatch" in d.reasons:
                candidates.append(
                    (
                        "Currency must be XCR",
                        d.policy.source_id,
                        _field_quote(policy.content, "Currency is the invented XCR crown."),
                    )
                )

    if ev.customer:
        sid = ev.customer["source_id"]
        for key in ("entity_id", "entity_type", "jurisdiction", "registered_address"):
            if key in ev.customer:
                candidates.append(
                    (
                        f"Customer record {key.replace('_', ' ')}",
                        sid,
                        json_fragment(key, ev.customer[key]),
                    )
                )
    if ev.registry:
        sid = ev.registry["source_id"]
        for key in ("registered_address", "ownership_depth", "intermediate_entity"):
            if key in ev.registry:
                candidates.append(
                    (
                        f"Registry {key.replace('_', ' ')}",
                        sid,
                        json_fragment(key, ev.registry[key]),
                    )
                )
        for name in d.facts.get("owner_names") or []:
            candidates.append(("Registry owner", sid, json_fragment("name", name)))

    _append_conflict_document_citations(candidates, d, ev, store)
    for source in store.case_documents(ev.case_id):
        for raw in source.content.split("\n"):
            line = raw.rstrip("\r")
            if line.strip() and _INSTRUCTION_LINE.search(line):
                candidates.append(
                    ("Untrusted instruction in a case document", source.source_id, line)
                )

    if ev.screening:
        sid = ev.screening["source_id"]
        if not d.screening_matches and ev.screening.get("matches") == []:
            candidates.append(("No screening matches returned", sid, json_fragment("matches", [])))
        for m in d.screening_matches:
            for key in ("candidate_name", "match_type"):
                if key in m:
                    candidates.append(
                        (
                            f"Screening {key.replace('_', ' ')} (unresolved)",
                            sid,
                            json_fragment(key, m[key]),
                        )
                    )
        if "pep_indicator" in ev.screening:
            candidates.append(
                (
                    "PEP indicator from screening",
                    sid,
                    json_fragment("pep_indicator", ev.screening["pep_indicator"]),
                )
            )
    if ev.transactions and "monthly_total" in ev.transactions:
        candidates.append(
            (
                "Monthly transaction total",
                ev.transactions["source_id"],
                json_fragment("monthly_total", ev.transactions["monthly_total"]),
            )
        )

    citations, seen = [], set()
    for claim, sid, quote in candidates:
        if quote and (sid, quote) not in seen and store.verify_quote(sid, quote):
            seen.add((sid, quote))
            citations.append({"claim": claim, "source_id": sid, "quote": quote})
    return citations


def build_packet(
    decision: Decision,
    evidence: CaseEvidence,
    intake_id: str | None,
    store: KnowledgeStore,
    narrator: Narrator,
) -> dict:
    return {
        "case_id": evidence.case_id,
        "classification": decision.classification,
        "routing": decision.routing,
        "policy_ids": decision.policy_ids,
        "facts": decision.facts,
        "missing_information": decision.missing_information,
        "deadline": None,
        "citations": build_citations(decision, evidence, intake_id, store),
        "follow_up_questions": [
            {"field": f, "question": _follow_up(f, decision, evidence)}
            for f in decision.missing_information
        ],
        "narrative": narrator.write(decision, evidence),
        "incomplete_reasons": decision.incomplete_reasons,
    }


__all__ = [
    "SCOPE_PHRASES",
    "build_citations",
    "build_packet",
    "_follow_up",
]
