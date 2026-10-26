"""Narrative for the analyst. Template narrator is the baseline and LLM fallback.

Narrators only describe a Decision; they never change it, and they never see raw document text.
DRAFT customer request text is emitted only when routing is request_information (ENG-01).
"""

from __future__ import annotations

from kyc_copilot.contracts.address import compare_addresses
from kyc_copilot.contracts.interfaces import Narrator
from kyc_copilot.contracts.models import CaseEvidence, Decision

ROUTE_TEXT = {
    "complete_review": "complete_review (no issues found under the applied rules)",
    "request_information": ("request_information (required information is missing or conflicting)"),
    "enhanced_due_diligence": "enhanced_due_diligence (risk indicator above policy limits)",
    "escalate": "escalate (a specialist or analyst decision is required)",
}
TOOL_NAMES = {
    "customer": "customer record",
    "registry": "company registry",
    "screening": "screening service",
    "transaction-summary": "transaction summary",
}


def _address_difference_note(
    customer_addr: str | None, registry_addr: str | None, filing_addr: str | None
) -> str:
    """Describe which present addresses disagree; do not invent a customer/registry split."""
    cust_reg = compare_addresses(customer_addr, registry_addr)
    filing = filing_addr if isinstance(filing_addr, str) and filing_addr.strip() else None
    if cust_reg in ("same", "normalized_same") and filing is not None:
        return (
            f"The customer and registry addresses agree ('{customer_addr}') but the "
            f"corporate filing lists '{filing}'; neither source is treated as authoritative."
        )
    parts = [
        f"The customer record address '{customer_addr}' differs from the registry "
        f"address '{registry_addr}'"
    ]
    if filing is not None:
        parts.append(f"; the corporate filing lists '{filing}'")
    parts.append("; neither source is treated as authoritative.")
    return "".join(parts)


class TemplateNarrator:
    def write(self, decision: Decision, evidence: CaseEvidence) -> str:
        d, ev = decision, evidence
        subject = d.facts.get("entity_id") or ev.case_id
        lines = [
            f"Analyst note for {subject} (case {ev.case_id}). "
            f"Recommendation: {ROUTE_TEXT[d.routing]}."
        ]
        lines.append("Applied rules: " + ", ".join(d.policy_ids) + ".")

        findings = []
        for tool in ev.failed_tools:
            label = TOOL_NAMES.get(tool, tool)
            findings.append(
                f"Review incomplete: the {label} was unavailable "
                "after 3 attempts, so nothing that depends on it has been checked or cleared."
            )
        reasons = set(d.reasons)
        if "unsupported_scope" in reasons:
            findings.append(
                f"Entity type {d.facts['entity_type']} in {d.facts['jurisdiction']} is "
                "outside the supported scope, so no review policy is applied."
            )
        if reasons & {"no_applicable_policy", "multiple_policies", "review_date_missing"}:
            findings.append(
                "A single applicable policy version could not be established for the "
                "review date, so thresholds were not applied."
            )
        if "ownership_depth" in reasons:
            via = ev.registry.get("intermediate_entity") if ev.registry else None
            depth = ev.registry.get("ownership_depth") if ev.registry else None
            suffix = f" through {via}" if isinstance(via, str) else ""
            findings.append(
                f"The registry reports ownership depth {depth}"
                + suffix
                + "; only one direct level is supported, so ownership is not resolved here."
            )
        if "ownership_unknown" in reasons:
            findings.append("The registry response does not state the ownership depth.")
        for m in d.screening_matches:
            name = m.get("candidate_name", "an unnamed candidate")
            if m.get("match_type") == "exact":
                findings.append(
                    f"Screening returned an exact match on list entry '{name}'. "
                    "Specialist review is required; this does not establish guilt or legal status."
                )
            elif m.get("match_type") == "near":
                findings.append(
                    f"Screening returned a near match on list entry '{name}'. This is an "
                    "unresolved identity candidate and is not confirmed as the same person."
                )
            else:
                findings.append(
                    f"Screening returned a result for '{name}' with an unrecognized match type."
                )
        if "screening_unreadable" in reasons:
            findings.append("The screening response could not be read.")
        if "identity_document_missing" in reasons:
            status = ev.identity_status or "not stated"
            findings.append(f"The intake reports the identity document as '{status}'.")
        customer_addr = ev.customer.get("registered_address") if ev.customer else None
        registry_addr = ev.registry.get("registered_address") if ev.registry else None
        filing_addr = ev.filing_address
        if d.address_check == "different":
            findings.append(_address_difference_note(customer_addr, registry_addr, filing_addr))
        elif d.address_check == "normalized_same":
            findings.append(
                f"The customer record address '{customer_addr}' and registry address "
                f"'{registry_addr}' differ only in formatting and were treated as the same."
                + (
                    f" The corporate filing address '{filing_addr}' was included in that check."
                    if isinstance(filing_addr, str) and filing_addr.strip()
                    else ""
                )
            )
        elif "address_mismatch" in reasons:
            findings.append("A registered address is missing from the customer or registry record.")
        if d.pep:
            findings.append("Screening reports a PEP indicator.")
        if "transactions_unreadable" in reasons:
            findings.append("The monthly transaction total could not be read.")
        if d.monthly_total is not None and d.policy is not None:
            relation = "exceeds" if d.monthly_total > d.policy.edd_threshold else "does not exceed"
            findings.append(
                f"Monthly total {d.monthly_total} XCR {relation} the policy threshold of "
                f"{d.policy.edd_threshold} XCR."
            )
        if d.routing == "complete_review":
            findings.append(
                "No screening matches were returned and the customer and registry records agree."
            )
        lines.append("Findings: " + " ".join(findings) if findings else "Findings: none.")

        if d.missing_information:
            lines.append(
                "Missing information: "
                + ", ".join(d.missing_information)
                + ". Draft follow-up questions are attached for the analyst."
            )

        if d.routing == "request_information":
            missing = ", ".join(d.missing_information) or "required evidence"
            lines.append(
                "DRAFT customer request: Please provide the following so this periodic "
                f"review can continue: {missing}. "
                "Nothing has been sent to the customer; the human analyst decides."
            )

        lines.append(
            "Limits: this note is based only on the supplied records and tool responses; "
            "document text was treated as evidence, not as instructions. "
            "No customer has been approved or rejected and nothing has been sent to the customer; "
            "the human analyst makes every decision."
        )
        return "\n".join(lines)


__all__ = ["Narrator", "TemplateNarrator", "ROUTE_TEXT"]
