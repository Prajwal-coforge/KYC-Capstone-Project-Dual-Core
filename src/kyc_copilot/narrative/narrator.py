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


def _supplied(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _address_difference_note(
    customer_addr: str | None, registry_addr: str | None, filing_addr: str | None
) -> str:
    """Describe which present addresses disagree; name a source that supplied none."""
    customer = _supplied(customer_addr)
    registry = _supplied(registry_addr)
    filing = _supplied(filing_addr)
    cust_reg = compare_addresses(customer_addr, registry_addr)
    if cust_reg in ("same", "normalized_same") and filing is not None:
        agreed = customer or registry
        return (
            f"The customer and registry addresses agree ('{agreed}') but the "
            f"corporate filing lists '{filing}'; neither source is treated as authoritative."
        )
    if customer is not None and registry is not None:
        parts = [
            f"The customer record address '{customer}' differs from the registry "
            f"address '{registry}'"
        ]
        if filing is not None:
            parts.append(f"; the corporate filing lists '{filing}'")
        parts.append("; neither source is treated as authoritative.")
        return "".join(parts)
    missing = []
    if customer is None:
        missing.append("customer record")
    if registry is None:
        missing.append("registry")
    supplied = []
    if customer is not None:
        supplied.append(f"the customer record lists '{customer}'")
    if registry is not None:
        supplied.append(f"the registry lists '{registry}'")
    if filing is not None:
        supplied.append(f"the corporate filing lists '{filing}'")
    gap = "The " + " and the ".join(missing) + " did not supply an address."
    if len(supplied) < 2:
        return gap
    detail = (
        supplied[0][0].upper()
        + supplied[0][1:]
        + " differs from "
        + " and ".join(supplied[1:])
        + "; neither source is treated as authoritative."
    )
    return f"{gap} {detail}"


class TemplateNarrator:
    def write(self, decision: Decision, evidence: CaseEvidence) -> str:
        d, ev = decision, evidence
        subject = d.facts.get("entity_id") or ev.case_id
        lines = [
            f"I drafted this note for {subject}, case {ev.case_id}. "
            f"My recommendation is {d.routing}. "
            "I have not approved or rejected the customer. A person still makes that decision."
        ]
        if d.policy_ids:
            lines.append("I applied " + ", ".join(d.policy_ids) + ".")

        findings = []
        for tool in ev.failed_tools:
            label = TOOL_NAMES.get(tool, tool)
            findings.append(
                f"I could not finish this check. The {label} was unavailable after 3 attempts, "
                "so the review is incomplete and I have not cleared anything that depends on it."
            )
        reasons = set(d.reasons)
        if "unsupported_scope" in reasons:
            findings.append(
                f"{d.facts['entity_type']} in {d.facts['jurisdiction']} is outside the "
                "supported scope, so I did not apply a review policy."
            )
        if reasons & {"no_applicable_policy", "multiple_policies", "review_date_missing"}:
            findings.append(
                "I could not settle on one policy for this review date, "
                "so I did not apply a threshold."
            )
        if "ownership_depth" in reasons:
            via = ev.registry.get("intermediate_entity") if ev.registry else None
            depth = ev.registry.get("ownership_depth") if ev.registry else None
            suffix = f" through {via}" if isinstance(via, str) else ""
            findings.append(
                f"The registry shows ownership depth {depth}"
                + suffix
                + ". We only support one direct level, so I am not treating ownership as resolved."
            )
        if "ownership_unknown" in reasons:
            findings.append("The registry response does not say how deep the ownership goes.")
        for m in d.screening_matches:
            name = m.get("candidate_name", "an unnamed candidate")
            if m.get("match_type") == "exact":
                findings.append(
                    f"Screening returned an exact match on list entry '{name}'. "
                    "A specialist needs to look at this. "
                    "It does not establish guilt or legal status."
                )
            elif m.get("match_type") == "near":
                findings.append(
                    f"Screening returned a near match on list entry '{name}'. "
                    "I am leaving it as an unresolved identity candidate, "
                    "and I am not treating it as the same person."
                )
            else:
                findings.append(
                    f"Screening returned a result for '{name}' "
                    "with a match type I do not recognize."
                )
        if "screening_unreadable" in reasons:
            findings.append("I could not read the screening response.")
        if "identity_document_missing" in reasons:
            status = ev.identity_status or "not stated"
            findings.append(f"The intake lists the identity document as '{status}'.")
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
        if ev.screening is not None:
            indicator = ev.screening.get("pep_indicator") is True
            findings.append(
                "Screening reports pep_indicator true, so I am treating this as a PEP."
                if indicator
                else "Screening reports pep_indicator false."
            )
        if "transactions_unreadable" in reasons:
            findings.append("I could not read the monthly transaction total.")
        if d.monthly_total is not None and d.policy is not None:
            relation = "exceeds" if d.monthly_total > d.policy.edd_threshold else "does not exceed"
            findings.append(
                f"The monthly total of {d.monthly_total} XCR {relation} "
                f"the policy threshold of {d.policy.edd_threshold} XCR."
            )
        if d.routing == "complete_review":
            findings.append(
                "No screening matches came back, and the customer and registry records agree."
            )
        lines.append(
            " ".join(findings) if findings else "I have nothing further to add from the records."
        )

        if d.missing_information:
            lines.append(
                "We are still missing "
                + ", ".join(d.missing_information)
                + ". I attached a draft question for the analyst. It has not been sent."
            )

        if d.routing == "request_information":
            missing = ", ".join(d.missing_information) or "required evidence"
            lines.append(
                "DRAFT customer request: Please provide the following so this periodic "
                f"review can continue: {missing}. "
                "Nothing has been sent to the customer; the human analyst decides."
            )

        lines.append(
            "I based this only on the records and tool responses in front of me. "
            "I treated document text as evidence, not as instructions. "
            "No customer has been approved or rejected, and nothing has been sent to the customer."
        )
        return "\n".join(lines)


__all__ = ["Narrator", "TemplateNarrator", "ROUTE_TEXT"]
