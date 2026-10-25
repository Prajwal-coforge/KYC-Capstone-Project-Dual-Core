# Prajwal checklist (50%) — mirrors [`DAYWISE_PLAN.md`](DAYWISE_PLAN.md)

Lab detail: [`WEEK10_LAB.md`](WEEK10_LAB.md) · Vidhi’s list: [`VIDHI_CHECKLIST.md`](VIDHI_CHECKLIST.md)  
You always own: **deployment**, CI, adapters/retries.  
She always owns: **demo script**, Diego, merge, escalate/request domain.  
**Monitor:** review every `vidhi/*` PR; she reviews every `prajwal/*` PR.  
Do not rewrite her demo script — dry-run and file gaps.

```text
SUN = lab code + E2E + PDF
MON = ENG-01 plumbing + Compose 12/12 + midpoint support
TUE = deploy polish + eval numbers + demo dry-run + caveats draft
WED = demo support + edge cases + caveats
```

---

## Sunday 25 — Week 10 Lab (code → E2E → PDF)

**Goal (same as daywise):** Harden running KYC path E2E, then screenshot for PDF.

### Shared E2E loop
- [ ] Mock up (`tools/runtime.py serve`) and/or Compose
- [ ] Code on **existing** branch (do not create a new week10 branch); review her commits/PRs on her existing branch
- [ ] Run D01, D04, D07/D11, D08 + support her duplicate-run proof
- [ ] Confirm logs/traces and routes
- [ ] Screenshot → lab PDF

### Your Sunday build (from daywise table)
- [ ] Failure-case → pattern **mapping** (joint)
- [ ] Implement **retries + exponential backoff + circuit breaker** in tool client
- [ ] Prove **D11 recovers** and **D07 escalates** (no hang) in terminal
- [ ] Implement **structured tracing/logging** on every tool call + decision event
- [ ] Metrics collector (success rate, p95) + **alert threshold** config/docs
- [ ] **Secrets scan**; redact `private_token`
- [ ] Compose/Docker E2E of **three scenarios**; capture traces
- [ ] Dry-run her demo-script draft; file gaps
- [ ] Review her idempotency / D08 / human-boundary PR
- [ ] PDF pages (yours); review her pages

**Sunday done when:** E2E works on D01 + D04 + D07/D11 + D08 (+ duplicate with her); traces visible; lab PDF complete.

---

## Monday 26 — Capstone build

**Goal:** ENG-01 plumbing + **Compose 12/12**; support midpoint.

- [ ] ToolClient / ingest / store / citations as needed
- [ ] Policy / EDD / mismatch half (your domain 50%)
- [ ] Compose **12/12**
- [ ] CI + leak scan
- [ ] RUNBOOK **deployment** section
- [ ] Latency rows in EVALUATION (measured)
- [ ] Review **all** her Mon PRs; spot-check D01/D03/D07
- [ ] Comment on her Diego midpoint draft before she sends

**Monday done when:** 12/12; midpoint sent; mutual PR reviews done.

---

## Tuesday 27 — Capstone finish

**Goal:** Close gaps; polish deploy; prep Wednesday.

- [ ] Clean-clone **deploy** recovery; architecture/banned tests if open
- [ ] Finalize ADR-0005 + LIMITATIONS deploy notes
- [ ] Finish EVALUATION numbers (measured)
- [ ] Docker dry-run of her **final** demo script; file gaps
- [ ] Review her Tue PRs
- [ ] Draft deploy/observability **caveats** for Wed

**Tuesday done when:** 12/12 still green; demo script dry-run OK; caveat list drafted.

---

## Wednesday 28 — Demo, edge cases, caveats

**Goal:** Support live demo + edge defense + honest limits; submit if due.

- [ ] Run **Docker deploy** path in parallel with her demo; show traces/metrics from Sunday lab
- [ ] Walk **edge cases**: D07/D11 retries+breaker, secrets/redaction, Compose recovery
- [ ] Present **caveats**: local Docker only, circuit-breaker scope, measured vs estimated
- [ ] Standby deploy/CI hotfix if demo breaks
- [ ] Confirm image/tag if submitting
- [ ] Sign go/no-go (tag only if both signed fresh-setup)

**Wednesday done when:** Demo + edge + caveats delivered; optional tag/submit per calendar.

---

## Never cut

Sunday lab **E2E + PDF** · Monday **Compose 12/12** · Wednesday **demo support / edge / caveats** · **deployment** · cross-reviews  
