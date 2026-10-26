"""One review: read case documents, call the four tools, apply rules, build the cited packet."""

from __future__ import annotations

import time

from kyc_copilot.adapters.redaction import canonical_json, redact
from kyc_copilot.adapters.tools_client import TOOLS, ToolClient, ToolResult
from kyc_copilot.contracts.interfaces import KnowledgeStore, Narrator
from kyc_copilot.contracts.models import CaseEvidence, CaseRun
from kyc_copilot.domain.packet import build_packet
from kyc_copilot.domain.rules import decide
from kyc_copilot.narrative.narrator import TemplateNarrator


def gather_evidence(
    case_id: str, client: ToolClient, store: KnowledgeStore
) -> tuple[CaseEvidence, dict[str, ToolResult], str | None]:
    reset = getattr(client, "reset_circuits", None)
    if reset is not None:
        reset()
    intake = None
    corporate = None
    identity = None
    for source in store.case_documents(case_id):
        doc = store.get_document(source.source_id)
        if doc is None:
            continue
        if doc.is_intake and intake is None:
            intake = doc
        if doc.doc_type == "corporate" and corporate is None:
            corporate = doc
        if doc.doc_type == "identity" and identity is None:
            identity = doc

    results = {tool: client.fetch(case_id, tool) for tool in TOOLS}
    payloads: dict[str, dict] = {}
    failed: list[str] = []
    for tool, result in results.items():
        if not result.ok:
            failed.append(tool)
            continue
        clean = redact(result.payload)  # restricted values never go further than this line
        try:
            save = store.save_tool_evidence
            save(case_id, tool, clean["source_id"], canonical_json(clean))
        except ValueError:  # a tool claimed the ID of a policy or document: do not trust it
            failed.append(tool)
            continue
        payloads[tool] = clean

    evidence = CaseEvidence(
        case_id=case_id,
        review_date=intake.review_date if intake else None,
        entity_ref=intake.entity_ref if intake else None,
        identity_status=intake.identity_status if intake else None,
        identity_document_present=identity is not None,
        customer=payloads.get("customer"),
        registry=payloads.get("registry"),
        screening=payloads.get("screening"),
        transactions=payloads.get("transaction-summary"),
        failed_tools=tuple(failed),
        filing_jurisdiction=corporate.filing_jurisdiction if corporate else None,
        declared_owner=corporate.declared_owner if corporate else None,
        filing_address=corporate.filing_address if corporate else None,
        holder_name=identity.holder_name if identity else None,
        birth_year=identity.birth_year if identity else None,
        identity_not_supplied=identity.identity_not_supplied if identity else False,
    )
    return evidence, results, intake.source_id if intake else None


def review_case(
    case_id: str,
    client: ToolClient,
    store: KnowledgeStore,
    narrator: Narrator | None = None,
) -> CaseRun:
    started = time.monotonic()
    evidence, results, intake_id = gather_evidence(case_id, client, store)
    decision = decide(evidence, store.find_policies)
    packet = build_packet(decision, evidence, intake_id, store, narrator or TemplateNarrator())
    return CaseRun(packet, decision, results, time.monotonic() - started)
