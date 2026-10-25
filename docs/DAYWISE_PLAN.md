# Daywise plan — Sun lab · Mon–Tue build · Wed demo

> Planning stays on **`docs/planning-distribution`**. Rules on **`main`**.  
> **Do not create new branches for lab/capstone tasks** — keep working on existing team branches.  
> Lab detail: [`WEEK10_LAB.md`](WEEK10_LAB.md) · Checklists: [`VIDHI_CHECKLIST.md`](VIDHI_CHECKLIST.md) · [`PRAJWAL_CHECKLIST.md`](PRAJWAL_CHECKLIST.md)

```text
SUN 25  = Week 10 Lab only (all parts, PDF ready)
MON 26  = Capstone build (ENG-01, 12/12, midpoint)
TUE 27  = Capstone finish (gaps, deploy polish, eval numbers)
WED 28  = Demo + edge cases + caveats / limitations
```

## Ownership

| | Vidhi | Prajwal |
|---|---|---|
| Always | Demo script, Diego, merge, escalate/request domain | Deployment, CI, adapters/retries |
| Cross-review | Reviews every `prajwal/*` PR | Reviews every `vidhi/*` PR |

---

## Sunday 25 — Week 10 Lab only (code + prove + PDF)

**Goal:** Harden the **running** KYC path end-to-end, then screenshot for the PDF.  
Not docs-only: implement → run mock → run copilot → show terminal/trace → PDF.

**E2E Sunday loop (both, same machine or Compose):**
1. Mock up (`tools/runtime.py serve`)
2. Code the hardenings below on **existing** branches (no new lab-only branches)
3. Run real cases: D01, D04, D07/D11, D08 (+ duplicate run)
4. Confirm logs/traces and routes
5. Screenshot → assemble lab PDF

| Vidhi (code + prove) | Prajwal (code + prove) |
|---|---|
| Mapping + SLO/error budget text | Mapping; implement **retries + exponential backoff + circuit breaker** in tool client |
| Implement **idempotency** (ledger / skip duplicate review action); prove twice-same-case in terminal | Prove **D11 recovers** and **D07 escalates** (no hang) in terminal |
| Ensure D08 injection cannot change route/approve; prove in terminal + packet | Implement **structured tracing/logging** on every tool call + decision event |
| Enforce human boundary in code (no records/approve path); grep proof | Metrics collector (success rate, p95) + alert threshold config/docs; secrets scan |
| Runbook D08; wire/run **three scenarios** with his traces | Compose/Docker E2E of same three scenarios; capture traces |
| PDF pages; review his | PDF pages; review hers |

**Done Sunday when:** Hardened code runs E2E on D01 + D04 + D07/D11 + D08 + duplicate; traces visible; lab PDF complete.  
Detail: [`WEEK10_LAB.md`](WEEK10_LAB.md).

---

## Monday 26 — Capstone build

**Goal:** ENG-01 behavior + **12/12**; Diego midpoint.

| Vidhi | Prajwal |
|---|---|
| Escalate/request/address domain; packet merge; DRAFT-only-on-request_info | ToolClient/ingest/store/citations as needed; policy/EDD/mismatch half |
| Duplicate-review product path if not done in lab; native 12/12 | Compose 12/12; CI + leak scan; RUNBOOK deploy section |
| Send Diego midpoint | Latency rows in EVALUATION; review her midpoint draft |
| Review all his Mon PRs | Review all her Mon PRs; spot-check D01/D03/D07 |

**Done Monday when:** 12/12; midpoint sent; mutual PR reviews done.

---

## Tuesday 27 — Capstone finish

**Goal:** Close gaps; polish deploy; measured eval; prep Wed.

| Vidhi | Prajwal |
|---|---|
| Fix graded failures; domain/adversarial tests still open | Clean-clone deploy recovery; architecture/banned tests if open |
| Finalize **demo script** for Wed (D01 / D04 / D07 or D08) | Finalize ADR-0005 + LIMITATIONS deploy notes; EVALUATION numbers |
| Review his Tue PRs | Docker dry-run of her demo script; file gaps |
| List **caveats** for Wed (known limits) | Same — deploy/observability caveats |

**Done Tuesday when:** 12/12 still green; demo script ready; caveat list drafted.

---

## Wednesday 28 — Demo, edge cases, caveats

**Goal:** Live demo + edge-case defense + honest limits; submit if due.

| Vidhi | Prajwal |
|---|---|
| Lead demo from **her script** (normal / escalate / failure-attack) | Run **Docker deploy** path in parallel; show traces/metrics from lab |
| Walk **edge cases**: D03 address, threshold equal, disputed jurisdiction, format/Source ID | Walk **edge cases**: D07/D11 retries+breaker, secrets/redaction, Compose recovery |
| Present **caveats** / limitations (ENG-01 notify-not-load, template narrative, no fuzzy match, lab SLO not production SLA) | Same — call out deploy/local-only, circuit breaker scope, measured vs estimated |
| Hotfix only if demo breaks; Diego submission update if freezing today | Standby deploy/CI hotfix; confirm image/tag if submitting |
| Tag/submit only if both signed fresh-setup | Sign go/no-go |

**Done Wednesday when:** Demo + edge + caveats delivered; optional tag/submit per cohort calendar.

---

## Cut line

1. Renamed-case CI → manual  
2. Cloud → local Docker  
3. Fancy maintenance email → log + runbook  

**Never cut:** Sunday lab PDF · Mon 12/12 · Wed demo/edge/caveats · human boundary · cross-reviews  
