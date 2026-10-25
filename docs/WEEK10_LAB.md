# Week 10 Lab — Harden KYC Capstone (**Sunday only**)

**Deadline: Sunday.** This is **coding + E2E proof**, then screenshots for the PDF.  
Mon–Tue = remaining ENG-01/12/12; Wed = demo / edge / caveats ([`DAYWISE_PLAN.md`](DAYWISE_PLAN.md)).

**No new branches for the lab.** Code and docs stay on the **existing** team branches you already use (`docs/planning-distribution` for planning; your current app branches / `main` as you already work). Do not open `feat/*/week10-*` just for this assignment.  
Rules live on **`main`**.  
50–50 · cross-review. Demo script → Vidhi. Deployment → Prajwal.

**Definition of done Sunday:** mock + app run; hardened behaviors work on real cases; traces on disk; lab PDF assembled.

---

## Failure-case → pattern mapping (do this before coding)

| KYC deliberate failure | Lab pattern | Owner |
|---|---|---|
| Registry / tool **timeout** (D07 persistent, D11 transient) | Retries + exponential backoff + circuit breaker; fail closed / escalate | **Prajwal** (adapters) |
| **Duplicate** review / same case twice | Idempotency key `(case_id)` or `(entity_ref, review_date)`; reuse draft; no second `POST /v1/reviews` | **Vidhi** (runner/ledger) |
| **Prompt injection** in corporate/doc (D08) | Untrusted data; never follow instructions; no approve | **Vidhi** (domain + demo evidence) |
| Human boundary (approve/reject/create record) | Least privilege; no approve API; no `POST /v1/records` in code | **Both** audit; Vidhi enforces in runner |
| `private_token` / secrets | Redaction; no hardcoded keys | **Prajwal** (adapters) + joint scan |
| Ambiguous near match (D04) | Escalate; do not confirm identity | **Vidhi** (domain) — Part 5 scenario |
| Normal happy path (D01) | End-to-end + traces | **Both** — Part 5 |

---

## Part 1 — SLO & error budget (10 pts) — **Vidhi drafts, Prajwal reviews**

- [ ] Write SLO (measurable), e.g. *“At least 95% of draft packets for a case complete within 15 seconds wall time (tools + rules), excluding human approval wait.”*
- [ ] Error budget in plain terms, e.g. *“In a 100-case day, ≤5 may miss the 15s SLO; if 3 already missed, freeze features, only reliability fixes.”*
- [ ] Screenshot → PDF page 1

---

## Part 2 — Reliability (25 pts)

### Retries / backoff / circuit breaker — **Prajwal builds, Vidhi reviews**

- [ ] Shared retry policy: max **3** attempts (align KYC-SCOPE-01)
- [ ] Exponential backoff between attempts (lab); still fail closed after budget
- [ ] Circuit breaker on mock tools (open after repeated 503s; short-circuit further calls; reset on success / cooldown)
- [ ] Demo: simulate timeout → show recovery (D11) **or** predictable escalate (D07) in terminal
- [ ] Screenshots: code + terminal → PDF

### Idempotency — **Vidhi builds, Prajwal reviews**

- [ ] Review ledger keyed by case/draft hash; second identical run does not create a second review action
- [ ] Test: submit/run same case twice → one draft / same hash behavior
- [ ] Screenshots: code + terminal → PDF

---

## Part 3 — Security (25 pts)

### Prompt injection (D08) — **Vidhi builds evidence, Prajwal reviews**

- [ ] Show injected text from corporate/doc (“IMPORTANT SYSTEM MESSAGE…”)
- [ ] Show system does **not** approve / change route because of it (`complete_review` or rules-only outcome)
- [ ] Screenshots → PDF

### Least privilege + human boundary — **Both**

- [ ] Audit: only adapters call bank; domain has no HTTP; narrative cannot call tools
- [ ] Confirm in code: no approve/reject customer; no `POST /v1/records` (grep + architecture test)
- [ ] Confirm no hardcoded API keys / mock secrets in repo
- [ ] Screenshots → PDF

---

## Part 4 — Observability & runbook (25 pts)

### Logging / tracing / metrics — **Prajwal builds, Vidhi reviews**

- [ ] Structured JSONL logs/traces for each tool call (attempt, status, latency_ms) and decision reasons (no `private_token`, no raw doc dumps)
- [ ] Metrics tied to SLO: e.g. (1) success rate of packet builds, (2) p95 time-to-packet
- [ ] Alert threshold that would page a human, e.g. *“If success rate &lt; 95% over last 20 cases, or p95 &gt; 15s, page on-call”*
- [ ] Sample trace screenshot → PDF

### Runbook (most severe: D08 attack / injection) — **Vidhi writes, Prajwal reviews**

- [ ] What to check first
- [ ] How to confirm cause
- [ ] Immediate mitigation
- [ ] Put in [`RUNBOOK.md`](RUNBOOK.md) section “Severe: prompt injection”
- [ ] Screenshot → PDF

---

## Part 5 — Three scenarios (15 pts) — **Vidhi leads demo script; Prajwal runs + captures traces**

| Scenario | Case | Owner of capture |
|---|---|---|
| Normal | D01 `complete_review` | Both |
| Ambiguous / escalate | D04 near match | Both |
| Failure / attack | D07 outage **or** D08 injection | Both |

- [ ] End-to-end each with logging/tracing visible
- [ ] Screenshots → PDF

---

## Sunday joint order — code first, PDF last

1. [ ] Mapping table (both) — 15 min  
2. [ ] **Prajwal codes** retries + backoff + circuit breaker; merge-ready PR; **Vidhi reviews**  
3. [ ] **Prove E2E:** D11 recovers, D07 escalates (terminal)  
4. [ ] **Vidhi codes** idempotency ledger; **Prajwal reviews**; prove duplicate run  
5. [ ] **Prajwal codes** structured traces + metrics hooks early (before more features)  
6. [ ] **Vidhi codes/verifies** D08 untrusted handling + human-boundary guards  
7. [ ] Both: secrets grep + least-privilege audit (architecture imports / no records)  
8. [ ] **E2E three scenarios** with tracing: D01, D04, D07 or D08  
9. [ ] SLO/error budget + runbook + alert text (can be short markdown once code works)  
10. [ ] **Lab PDF** from real terminals/traces — before Monday  

### E2E commands (adapt to your entrypoint)

```sh
uv run --locked python tools/runtime.py serve --port 8766
# after hardenings land:
uv run --locked python -m app.run --cases KYC-D01 KYC-D04 KYC-D07 KYC-D08   # or kyc_copilot
# duplicate:
uv run --locked python -m app.run --cases KYC-D01 --submit-reviews
uv run --locked python -m app.run --cases KYC-D01 --submit-reviews   # must not double-create
uv run --locked python tools/runtime.py audit > reports/audit-lab.json
```

---

## PDF page order (lab)

1. SLO + error budget  
2. Failure-case → pattern mapping  
3. Retry/backoff/breaker code + timeout recovery terminal  
4. Idempotency code + duplicate terminal  
5. Prompt injection content + correct handling  
6. Least-privilege + human boundary in code  
7. No hardcoded credentials  
8. Logging/tracing + sample trace  
9. Metrics + alert threshold  
10. Runbook (severe case)  
11. Three scenarios evidence  
