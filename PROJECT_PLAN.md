# Project plan, checklist and task split

Team: **Prajwal (P)** and **Vidhi (V)**. Last updated: Day 3 (2026-10-21).
Structure follows the delivery plan in `BRIEF.md`. Companion docs: `ASSUMPTIONS.md` (decisions and
client answers), `docs/` (API, output contract, assessment criteria).
Legend: `[x]` done, `[ ]` to do. Owner tags: **P**, **V**, **Both**.

## 1. Ownership and rotation

| Area | Primary owner | Cross-checks |
|---|---|---|
| Data: ingestion, storage, evidence, packet and trace stores, eval fixtures, redaction | **P** | V |
| AI summarization: narrator, prompt, validator, fallback, LLM adapter | **P** | V |
| Deterministic workflow: tool client, rules, routing, packet builder, review flow | **V** | P |
| Eval harness: test suites, pipeline eval, audit checks, reports | **V** | P |
| Shared: architecture record, runbook, deployment, demo, limitations | Both | n/a |

The brief asks us to **rotate integration, application/retrieval and testing/operations
responsibilities** and says every member must **explain and modify part of the system** and
document individual contributions. The brief also describes a team of three; we are two, so one
person covers more than one of those roles at a time. Ownership above stays stable, and each phase
has cross-over tasks (section 3) so both of us work in each role by the end.

| Brief role | What it covers here |
|---|---|
| Integration | Tool client, retries, review submission and polling |
| Application / retrieval | Ingestion, policy retrieval, rules, packet builder, narrative |
| Testing / operations | Eval harness, monitoring, Docker, runbook |

Load note: the workflow is the critical path and V also owns the eval harness. P takes the data work
that feeds the harness (fixtures, leak scan, metrics) so V is not blocked.

## 2. Status against the delivery plan

Working days are assumed Monday to Friday from 2026-10-19; confirm against the cohort calendar.

| Brief phase | Dates (assumed) | Brief requires | Status |
|---|---|---|---|
| Days 1-2 | Oct 19-20 | Inspect material, record assumptions and scope, reproducible startup, thin end-to-end normal case | **Done** (thin case completed on Day 3) |
| Days 3-5 | Oct 21-23 | Retrieval and tool integration, evidence output, deterministic rules, review flow; demo an ambiguous case | **In progress**: tools, rules, evidence output and draft submission done; review polling, eval command and demo remain |
| Days 6-8 | Oct 26-28 | Failures, duplicate events, hostile inputs; evaluation set; monitoring | Not started |
| Days 9-10 | Oct 29-30 | Fresh-setup rehearsal, deployment, runbook, limitations, technical defense | Not started |
| Days 11-13 | Nov 2-4 | Optional: fix core failures, improve evidence, rehearse; stretch only after core passes | Not started |

## 3. Contracts between owners (agree on Day 3, then work in parallel with fakes)

| Contract | Defined by | Used by | Shape |
|---|---|---|---|
| `KnowledgeStore` (exists, `app/models.py`) | P | V | `find_policies`, `get_source`, `case_documents`, `verify_quote` |
| `Facts` (rules output) | V | P, V | route, classification, policy IDs, fact fields, missing fields, conflicts, tool failures, `incomplete_reasons`, near/exact matches |
| `Narrator.write(facts) -> text`, `validate(text, facts) -> errors` | P | V | Template narrator first, LLM narrator second, same interface |
| `PacketStore` | P | V | `save_draft(case_id, packet)` returns the existing one on a duplicate; stores draft hash and review ID; unique per case ID |
| `TraceSink.emit(event, **fields)` | P | V | Redacts restricted values; JSON lines |
| `results.json` | `docs/OUTPUT_CONTRACT.md` | V | One object per case |

- [ ] Write the `Facts` and `PacketStore` shapes in code (classes plus docstrings) and review together **(Both)**

## 4. Checklist by delivery phase

### Days 1-2 (done, with one carry-over)

- [x] Inspect the client material **(Both)**
- [x] Record assumptions and scope; client answers captured in `ASSUMPTIONS.md` **(Both)**
- [x] Reproducible startup: pinned `uv` environment, Docker compose (`mock` + `dev`), `DOCKER.md` **(P)**
- [x] Ingestion of policies and case documents into SQLite, policy lookup by date, exact-quote check, 19 tests **(P)**
- [x] Base template on `main`; our work on branch `Prajwal` **(P)**
- [x] **Thin end-to-end normal case (D01)**: tools -> rules -> cited packet -> `evaluate.py`. Completed Day 3; all 12 dev cases also pass `evaluate.py`

### Days 3-5: retrieval and tool integration, evidence output, rules, review flow, ambiguous demo

Retrieval and evidence
- [ ] Walk V through the ingestion code (what it does, how to change it) **(P)**
- [x] Evidence capture: save each tool response as a source, keeping its `source_id`, JSON normalized with sorted keys and standard spaces, so citations to tool data can be checked **(P)**
- [ ] `PacketStore`: one draft per case ID (unique constraint), draft hash, review ID, status **(P)**

Tool integration
- [x] Tool client for the four read tools: at most 3 total attempts, tells 503 from 404 and bad input, per-tool result with status (`app/tools_client.py`) **(V to review)**
- [x] Tool client tests with a fake server (transient and persistent failure) and the real mock **(V to review)**

Deterministic rules (write tests first from the 12 dev cases plus boundaries), `app/rules.py`
- [x] Scope check: supported matrix; ownership depth above 1 escalates **(V to review)**
- [x] Policy selection through `KnowledgeStore`; handle none found and several found **(V to review)**
- [x] Threshold comparison (strictly greater than) and PEP indicator **(V to review)**
- [x] Screening: exact and near both escalate; candidate names shown **(V to review)**
- [x] Missing information: `identity_document`, `address_explanation` **(V to review)**
- [x] Address comparison with US-style normalization (`ASSUMPTIONS.md` 3.1) **(V to review)**
- [x] Routing precedence from `KYC-SCOPE-01` **(V to review)**

Evidence output
- [x] Packet builder: facts, policy IDs, exact-quote citations via `verify_quote`, deterministic follow-up question per missing field, `deadline` null (`app/packet.py`) **(V to review)**
- [x] `Narrator` interface and template narrator (baseline and later fallback) (`app/narrator.py`) **(P)**
- [ ] Confirm approved LLM access with the facilitator **(P)**; until then stay on the template

Review flow
- [x] `POST /v1/reviews` via `app.run --submit-reviews`; no approve or `POST /v1/records` code exists **(V to review)**
- [ ] Poll `GET /v1/reviews/ID` and show the human decision **(V)**
- [x] Runner command: run chosen cases, write `submissions/results.json` (`app/run.py`) **(V to review)**

Evaluation (thin)
- [ ] Pipeline eval command: one command that runs cases, writes `results.json`, runs `tools/evaluate.py` and saves the report. Today this is two commands (README) plus `tests/test_pipeline.py` **(V)**
- [x] Rules tests table-driven with boundaries (`tests/test_rules.py`, 38 cases) and all 12 dev cases end to end (`tests/test_pipeline.py`) **(V to review)**

Demo and cross-over
- [ ] **Ambiguous-case demo**: D03 (address mismatch), D04 (near-match), D05 (exact match) route correctly with cited evidence **(Both)**
- [ ] Cross-over: P writes tests for the tool client; V adds one ingestion test or policy fixture **(swap)**

Gate to leave this phase: D01 to D06 and D10 to D12 pass `evaluate.py`; a draft goes through `POST /v1/reviews` and a teammate approves it from the operator CLI; the ambiguous cases are demonstrable.

### Days 6-8: failures, duplicates, hostile inputs, evaluation set, monitoring

Failures
- [x] Outage handling: persistent failure (D07) retries 3 times then escalates, `owner_names` null, review marked incomplete with the failed tool named; transient failure (D11) recovers. Checked against the mock audit **(V to review)**
- [x] Unsupported scope and no policy for the date: classification `unsupported` or escalate using only `KYC-SCOPE-01`. Unit-tested only; needs `data/eval/` fixtures for an end-to-end check **(V to review)**

Duplicates and concurrency
- [ ] Duplicate handling in the runner using `PacketStore`; same case ID keeps the original **(V uses, P owns store)**
- [ ] Store safe for 5 concurrent writers (WAL, short transactions, busy timeout) and a test for it **(P)**

Hostile inputs and AI
- [ ] Injection resistance: D08 and variants; documents are only quoted, never obeyed. D08 passes and is tested; variants still to do **(V)**
- [ ] Validator (pure code) for AI text: route matches; no invented names, IDs, dates, amounts or addresses; required uncertainty present; no approve/reject or commitments; no restricted values; no echoed instructions; draft labels **(P)**
- [ ] LLM adapter (if approved): timeouts, token and latency capture, key from environment only; retry once with the errors, then template fallback **(P)**
- [ ] Hand-review the first 10 narratives, then a sample each run; compare AI against template **(P, with V)**

Evaluation set
- [ ] Fixtures in `data/eval/` (same shape as `data/dev`; do not edit `data/dev`): unsupported scope, no policy for the date, deep ownership, near-match plus outage, duplicate submission, injection variants, boundary totals **(P)**
- [ ] Own scenario eval on those fixtures **(V)**
- [ ] Audit checks from `runtime.py audit`: at most 3 attempts per failing tool, no write attempts, no agent approvals. Started in `tests/test_pipeline.py` for the dev set **(V)**
- [ ] Extra checks: each citation supports its claim; routing never less severe than expected; narrative has no forbidden claims **(V)**
- [ ] Concurrency test: 5 cases in parallel, real latency recorded **(V)**

Monitoring
- [x] Redaction helper for `private_token` and other restricted values (`app/redaction.py`; tool payloads are redacted before storage or use) **(P)**
- [ ] `TraceSink` with structured JSON lines and the metric events from `ASSUMPTIONS.md` section 4 **(P)**
- [ ] Leak scan over database, traces and `results.json`. Database and packets covered in `tests/test_pipeline.py`; traces still to do **(P)**
- [ ] Metrics summary command: counts, seconds per case, retries, fallbacks, route mix **(P)**

Cross-over
- [ ] P runs and extends the audit checks; V adds a trace event and a leak-scan case **(swap)**

Gate to leave this phase: all 12 dev cases pass; own scenarios pass; audit checks clean; leak scan clean; metrics report produced with real numbers.

### Days 9-10: fresh setup, deployment, runbook, limitations, technical defense

- [ ] Fresh-setup rehearsal from a clean clone using only the docs **(Both)**
- [ ] Deployment: app service in Docker compose; health check; restart and recovery **(P)**
- [ ] Operator runbook: start, health, reset, approve, outage recovery **(Both)**
- [ ] Architecture and decision record: deterministic core, where AI is used, storage choice, alternatives rejected **(Both)**
- [ ] Known limitations and future-state roadmap (admin dashboard, Postgres adapter, queue and workers, pilot baseline) **(Both)**
- [ ] Redacted traces export for the assessors **(P)**
- [ ] Eval report with actual results; no invented cost or accuracy claims **(V)**
- [ ] Client demo script: normal case, ambiguity requiring escalation, assessor-selected failure or attack **(Both)**
- [ ] Technical defense rehearsal: each person explains the other's area and makes a small live change **(Both)**
- [ ] Individual contributions table completed (section 7) **(Both)**

### Days 11-13 (optional): only after the core gates pass

- [ ] Fix any remaining core failures **(Both)**
- [ ] Improve evidence quality (citation relevance, clearer narratives) **(Both)**
- [ ] Agree stretch work with the facilitator first, for example a Postgres adapter behind a flag **(P)**
- [ ] Final rehearsal **(Both)**

## 5. Deliverables tracker (from `BRIEF.md`)

| Deliverable | Status |
|---|---|
| Source repo with environment pins and setup commands | Done (`uv.lock`, `DOCKER.md`, run command in `README.md`) |
| Working application and deployment instructions | Thin version runs locally and in Docker; app service in compose still to do |
| Architecture and decision record | Not started |
| JSON outputs using the contract | Done for the dev set (`submissions/results.json`, 12 of 12 pass) |
| Evaluation command and actual results | Supplied `evaluate.py` passes 12 of 12 dev cases; own scenarios still to do |
| Redacted traces | Not started |
| Operator runbook | Not started |
| Limitations and future-state roadmap | Draft notes in `ASSUMPTIONS.md` section 6 |
| Client-facing demonstration | Not started |

## 6. How we work together

- Branches: `Prajwal` and one for V (for example `Vidhi`); pull requests into `main`; the other person reviews.
- Test first: write the failing test, then the code. Run the eval command before opening a PR.
- Small PRs per checklist item. Tick the box in this file in the same PR.
- Never edit `data/dev/` or the supplied tools; add new fixtures under `data/eval/`.
- Secrets (LLM keys) only in environment variables; run the leak scan before every push.
- Update `ASSUMPTIONS.md` when a decision changes; keep client answers dated.

## 7. Individual contributions (fill in as we go)

| Person | Built | Can explain | Changed in the other's area |
|---|---|---|---|
| P | | | |
| V | | | |

Walkthroughs, 30 minutes each: P explains data and ingestion to V (Days 3-5); V explains rules and
workflow to P (Days 3-5); later each explains their second area (AI, eval). Each person then makes
one small change in the other's code.

## 8. Risks and open items

| Item | Owner | Note |
|---|---|---|
| Workflow code was written on P's branch, in V's area | V | V reviews the PR and walks P through any changes, so both can explain it |
| Brief describes three associates; we are two | Both | Confirm expectations with the facilitator |
| LLM access not confirmed | P | Template path keeps us unblocked |
| Address normalization vs graded rules | V | Conservative rule; confirm with facilitator |
| Workflow is the critical path | Both | Pair on the first end-to-end run |
| Hidden cases combine failures | V and P | Cover with `data/eval/` scenarios early |
| Calendar dates are assumed | Both | Confirm against the cohort calendar |
