# Vidhi checklist (50%) — mirrors [`DAYWISE_PLAN.md`](DAYWISE_PLAN.md)

Lab detail: [`WEEK10_LAB.md`](WEEK10_LAB.md) · Prajwal’s list: [`PRAJWAL_CHECKLIST.md`](PRAJWAL_CHECKLIST.md)  
You always own: **demo script**, Diego, merge, escalate/request domain.  
He always owns: deployment, CI, adapters/retries.  
**Monitor:** review every `prajwal/*` PR; he reviews every `vidhi/*` PR.

```text
SUN = lab code + E2E + PDF
MON = ENG-01 + 12/12 + midpoint
TUE = finish gaps + demo script + caveats draft
WED = demo + edge cases + caveats
```

---

## Sunday 25 — Week 10 Lab (code → E2E → PDF)

**Goal (same as daywise):** Harden running KYC path E2E, then screenshot for PDF.

### Shared E2E loop
- [ ] Mock up (`tools/runtime.py serve`)
- [ ] Code on **existing** branch (do not create a new week10 branch); review his commits/PRs on his existing branch
- [ ] Run D01, D04, D07/D11, D08 + duplicate run
- [ ] Confirm logs/traces and routes
- [ ] Screenshot → lab PDF

### Your Sunday build (from daywise table)
- [ ] Failure-case → pattern **mapping** (joint) + **SLO / error budget** text
- [ ] Implement **idempotency** (ledger / skip duplicate review action)
- [ ] Prove twice-same-case in **terminal**
- [ ] Ensure **D08** injection cannot change route/approve; prove in terminal + packet
- [ ] Enforce **human boundary** in code (no records / no approve path); grep proof
- [ ] Emit decision/reason events into his trace format if needed
- [ ] **Runbook** for D08 in `RUNBOOK.md`
- [ ] Wire/run **three scenarios** with his traces (D01, D04, D07 or D08)
- [ ] Review his retry/backoff/breaker + tracing PR
- [ ] PDF pages (yours); review his pages

**Sunday done when:** E2E works on D01 + D04 + D07/D11 + D08 + duplicate; traces visible; lab PDF complete.

---

## Monday 26 — Capstone build

**Goal:** ENG-01 behavior + **12/12**; Diego midpoint.

- [ ] Escalate / request / address domain
- [ ] Packet merge; **DRAFT only** on `request_information`
- [ ] Duplicate-review product path if anything left after Sunday lab
- [ ] Native **12/12**
- [ ] Send **Diego midpoint**
- [ ] Review **all** his Mon PRs (Compose 12/12, CI, deploy runbook, latency)

**Monday done when:** 12/12; midpoint sent; mutual PR reviews done.

---

## Tuesday 27 — Capstone finish

**Goal:** Close gaps; prep Wednesday.

- [ ] Fix graded failures; domain/adversarial tests still open
- [ ] Finalize **demo script** for Wed (D01 / D04 / D07 or D08)
- [ ] Review his Tue PRs (deploy recovery, EVALUATION, ADR-0005)
- [ ] Confirm Compose still 12/12 with him
- [ ] List **caveats** for Wed (known limits)

**Tuesday done when:** 12/12 still green; demo script ready; caveat list drafted.

---

## Wednesday 28 — Demo, edge cases, caveats

**Goal:** Live demo + edge defense + honest limits; submit if due.

- [ ] Lead demo from **your script** (normal / escalate / failure-attack)
- [ ] Walk **edge cases**: D03 address, threshold equal, disputed jurisdiction, format/Source ID
- [ ] Present **caveats**: ENG-01 notify-not-load, template narrative, no fuzzy match, lab SLO ≠ bank SLA
- [ ] Hotfix only if demo breaks
- [ ] Diego submission update if freezing today
- [ ] Tag/submit **only if both signed** fresh-setup

**Wednesday done when:** Demo + edge + caveats delivered; optional tag/submit per calendar.

---

## Never cut

Sunday lab **E2E + PDF** · Monday **12/12** · Wednesday **demo / edge / caveats** · human boundary · cross-reviews  
