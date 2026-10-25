"""One review: read case documents, call the four tools, apply rules, build the cited packet."""
from __future__ import annotations

import time
from dataclasses import dataclass

from .models import KnowledgeStore
from .narrator import Narrator, TemplateNarrator
from .packet import build_packet
from .redaction import canonical_json, redact
from .rules import CaseEvidence, Decision, decide
from .tools_client import TOOLS, ToolClient, ToolResult


@dataclass(frozen=True)
class CaseRun:
    packet: dict
    decision: Decision
    tool_results: dict[str, ToolResult]
    seconds: float


def gather_evidence(case_id: str, client: ToolClient, store: KnowledgeStore
                    ) -> tuple[CaseEvidence, dict[str, ToolResult], str | None]:
    reset = getattr(client, "reset_circuits", None)
    if reset is not None:
        reset()
    intake = None
    identity_present = False
    for source in store.case_documents(case_id):
        doc = store.get_document(source.source_id)
        if doc is None:
            continue
        if doc.is_intake and intake is None:
            intake = doc
        if doc.doc_type == "identity":
            identity_present = True

    results = {tool: client.fetch(case_id, tool) for tool in TOOLS}
    payloads: dict[str, dict] = {}
    failed: list[str] = []
    for tool, result in results.items():
        if not result.ok:
            failed.append(tool)
            continue
        clean = redact(result.payload)  # restricted values never go further than this line
        try:
            store.save_tool_evidence(case_id, tool, clean["source_id"], canonical_json(clean))
        except ValueError:  # a tool claimed the ID of a policy or document: do not trust it
            failed.append(tool)
            continue
        payloads[tool] = clean

    evidence = CaseEvidence(
        case_id=case_id,
        review_date=intake.review_date if intake else None,
        entity_ref=intake.entity_ref if intake else None,
        identity_status=intake.identity_status if intake else None,
        identity_document_present=identity_present,
        customer=payloads.get("customer"),
        registry=payloads.get("registry"),
        screening=payloads.get("screening"),
        transactions=payloads.get("transaction-summary"),
        failed_tools=tuple(failed),
    )
    return evidence, results, intake.source_id if intake else None


def review_case(case_id: str, client: ToolClient, store: KnowledgeStore,
                narrator: Narrator | None = None) -> CaseRun:
    started = time.monotonic()
    evidence, results, intake_id = gather_evidence(case_id, client, store)
    decision = decide(evidence, store.find_policies)
    packet = build_packet(decision, evidence, intake_id, store, narrator or TemplateNarrator())
    return CaseRun(packet, decision, results, time.monotonic() - started)
