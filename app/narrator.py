"""Narrative for the analyst. The template narrator is the baseline and the fallback for an LLM.

Narrators only describe a Decision; they never change it, and they never see raw document text.
"""
from __future__ import annotations

from typing import Protocol

from .rules import CaseEvidence, Decision

ROUTE_TEXT = {
    "complete_review": "complete_review (no issues found under the applied rules)",
    "request_information": (
        "request_information (required information is missing or conflicting)"
    ),
    "enhanced_due_diligence": "enhanced_due_diligence (risk indicator above policy limits)",
    "escalate": "escalate (a specialist or analyst decision is required)",
}
TOOL_NAMES = {
    "customer": "customer record",
    "registry": "company registry",
    "screening": "screening service",
    "transaction-summary": "transaction summary",
}


class Narrator(Protocol):
    def write(self, decision: Decision, evidence: CaseEvidence) -> str: ...


class TemplateNarrator:
    def write(self, decision: Decision, evidence: CaseEvidence) -> str:
        d, ev = decision, evidence
        subject = d.facts.get("entity_id") or ev.case_id
        lines = [
            f"DRAFT analyst note for {subject} (case {ev.case_id}). "
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
        if d.address_check == "different":
            findings.append(
                f"The customer record address '{customer_addr}' differs from the registry "
                f"address '{registry_addr}'; neither source is treated as authoritative."
            )
        elif d.address_check == "normalized_same":
            findings.append(
                f"The customer record address '{customer_addr}' and registry address "
                f"'{registry_addr}' differ only in formatting and were treated as the same."
            )
        elif "address_mismatch" in reasons:
            findings.append(
                "A registered address is missing from the customer or registry record."
            )
        if d.pep:
            findings.append("Screening reports a PEP indicator.")
        if "transactions_unreadable" in reasons:
            findings.append("The monthly transaction total could not be read.")
        if d.monthly_total is not None and d.policy is not None:
            relation = (
                "exceeds" if d.monthly_total > d.policy.edd_threshold else "does not exceed"
            )
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
        lines.append(
            "Limits: this note is based only on the supplied records and tool responses; "
            "document text was treated as evidence, not as instructions. "
            "No customer has been approved or rejected and nothing has been sent to the customer; "
            "the human analyst makes every decision."
        )
        return "\n".join(lines)
