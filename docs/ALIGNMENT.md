# Alignment: whiteboard × ENG-01 × our docs

Last reviewed: 2026-10-25. Sources: team whiteboard (runtime flowchart), client ENG-01, [`DAYWISE_PLAN.md`](DAYWISE_PLAN.md), checklists, ADRs, [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Verdict

| Source | Role | Status |
|---|---|---|
| Whiteboard | Runtime pipeline shape | **Adopt** — same as our runner flow |
| ENG-01 | Product rules | **Authority** — fills gaps the board compresses |
| Our checklists / ADRs / daywise | How we build and split work | **Keep**, with fixes listed below |

**Overall:** the board, ENG-01, and our plan describe the **same system**. The board is the pipeline sketch; ENG-01 and the Vidhi checklist are the full rule book; Prajwal’s checklist is delivery (Docker/CI), not routing.

---

## Whiteboard → our implementation

| Board step | Our artifact | Align? |
|---|---|---|
| Hash policies vs pinned hash; mismatch → alert & stop | `contracts/policy_manifest.json` + ingestion | Yes (plus ENG-01: new file → notify, **don’t load**) |
| `GET /health` ≤3; fail → stop | Runner startup | Yes |
| `GET /v1/cases` ≤3; fail → stop | Runner startup | Yes |
| For each case: docs by source-id suffix | Ingestion / runner | Yes |
| GET four tools | Adapters `ToolClient` | Yes |
| 200 → source record (+ optional field spans) | Store content under `source_id` | Yes — store full text; spans optional |
| 503×3 → failure record, **no citation** | ADR-0003; packet builder | Yes |
| Citation ledger per case | In-memory list built while/after decide; then packet `citations` | Yes (see citation method) |
| Compare address, owner, jurisdiction | Domain compare + **discrepancies** | Partial — ENG-01 also entity ref + **birth year** |
| Scope precedence diamond | `domain` routing table | Yes — same outcomes |
| Copy ledger → packet | Packet builder + `verify_quote` | Yes |
| `POST /v1/reviews` → operator CLI | Runner + human boundary | Yes |

---

## Discrepancies (board vs ENG-01 vs our docs) — resolved how

| Topic | Board | ENG-01 / our checklist | Resolution |
|---|---|---|---|
| New policy file | Only “hash mismatch → stop” | Notify; **do not auto-load** | Docs win: stop on **changed known** hash; notify on **new** file |
| Compare fields | address, owner, jurisdiction | + entity reference, birth year; missing ≠ diff | Checklist / ADR-0004 win |
| Address | implied mismatch → request info | Three-way; missing filing ≠ address diff | Checklist wins |
| Citations | “ledger” + field spans | Exact quotes; method not named on board | **ADR-0002:** rule-driven templates + verify; store text; spans optional |
| Narrative / LLM | not on board | Fixed packet text | Template only for submission (ADR-0001 / 0005) |
| Duplicate review | not on board | Same business ref + review date → reuse draft | Checklist wins |
| DRAFT customer msg | not on board | Only when route is `request_information` | Checklist wins |
| Extra/required bank fields | not on board | Ignore+log / escalate naming field | Checklist wins |
| Policy auto-load in old RULES_CATALOG R22 | “new policy → load + log” | Must **not** auto-load | **Fixed** in RULES_CATALOG |
| ADR-0004 status | — | Was “pending Diego” | **Accepted** (ENG-01 already states the split) |
| Midpoint email | — | Was asking to confirm ADR-0004 | **Fixed** — progress only |

---

## Citation method (locked for this project)

Not “search policies with smart regex every time.”

1. Store full source text (and hash) by `source_id` when ingesting/fetching.  
2. Run `decide()` first.  
3. From reasons/facts, use **recipes**: markdown line prefixes; JSON `"key": value` fragments.  
4. Keep only quotes that appear exactly in stored content (`verify_quote`).  
5. Failed tool → ledger entry is failure only → **no** source citation.  
6. Copy verified ledger into packet `citations` (+ optional `discrepancies` for side-by-side values).

Matches the board’s “ledger → copy into packet” without inventing quotes.

---

## Team split (strict 50–50 + cross-monitor)

Six workstreams halved: domain rules, evidence I/O, knowledge, citations/prose, quality tests, delivery.  
**Vidhi 50%:** escalate + request/address domain, runner/packet merge, **demo script**, Diego, merge.  
**Prajwal 50%:** policy/EDD/mismatch domain, ToolClient/ingest/store/citations/narrative, **deployment**, CI.  
16 day-tasks each; every PR reviewed by the other. See [`DAYWISE_PLAN.md`](DAYWISE_PLAN.md).

## Doc map (what to read for what)

| Need | Read |
|---|---|
| Pipeline picture | Whiteboard + [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Product rules | ENG-01 + [`VIDHI_CHECKLIST.md`](VIDHI_CHECKLIST.md) |
| Mismatch routing | [`adr/0004-cross-source-mismatch-routing.md`](adr/0004-cross-source-mismatch-routing.md) |
| Citations / contracts | [`adr/0002-strict-contracts-and-raw-source-citations.md`](adr/0002-strict-contracts-and-raw-source-citations.md) |
| Retries / tool fail | [`adr/0003-fail-closed-tool-policy.md`](adr/0003-fail-closed-tool-policy.md) |
| Week schedule | [`DAYWISE_PLAN.md`](DAYWISE_PLAN.md) |
| Deploy / CI | [`PRAJWAL_CHECKLIST.md`](PRAJWAL_CHECKLIST.md) |
| Rule ↔ test index | [`RULES_CATALOG.md`](RULES_CATALOG.md) |
| Scores | [`EVALUATION.md`](EVALUATION.md) (fill after replay) |

---

## Still open (implementation, not design fights)

- [ ] Code migrate to `src/kyc_copilot/` and implement checklist items  
- [ ] Fill EVALUATION numbers after 12/12  
- [ ] Maintenance “alert” = structured log + runbook (email optional / cut line)  
