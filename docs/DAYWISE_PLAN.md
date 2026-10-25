# Daywise plan — Sun 25 Oct → Wed 28 Oct 2026

> Lives on branch **`docs/planning-distribution`**. Shared agent/git rules live on **`main`** (`AGENTS.md`, ADRs, `ARCHITECTURE.md`). See [`REPO_SPLIT.md`](REPO_SPLIT.md).

**50–50 split.** Same number of workstreams, same hours target, mutual PR review.  
Demo script → **Vidhi**. Deployment → **Prajwal**.  
Checklists: [`VIDHI_CHECKLIST.md`](VIDHI_CHECKLIST.md) · [`PRAJWAL_CHECKLIST.md`](PRAJWAL_CHECKLIST.md) · [`ALIGNMENT.md`](ALIGNMENT.md)

```text
Sun 25 → Mon 26 → Tue 27 → Wed 28
```

## 50–50 ownership map

| # | Workstream | Vidhi 50% | Prajwal 50% |
|---|---|---|---|
| 1 | Domain | Escalate + request_information paths (unsupported, depth, screening, tool fail, identity, **address**) | Policy select + EDD path (thresholds, PEP, currency) + **non-address mismatches** + discrepancies |
| 2 | Evidence I/O | Runner: health, cases, batch loop, review submit/poll, duplicate-review key | ToolClient + retries + redaction + CaseRecord assembly from tools/docs |
| 3 | Knowledge | Contracts for Decision / packet fields her routes need | Ingest, store, policy manifest (hash stop / new-file notify no load), doc suffix checks |
| 4 | Citations & prose | Packet assembly: attach her decision + his citation list; DRAFT only on request_info | Citation recipes + `verify_quote` + template narrative + traces |
| 5 | Quality | Unit/e2e tests for **her** domain + demo cases D01/D03/D08 | Unit/e2e tests for **his** domain + client/ingest + D04/D06/D07 |
| 6 | Delivery | **Demo script** + Diego emails + merge to `main` + tag | **Deployment** (Docker/Compose/runbook) + CI + leak scan + ADR-0005 + EVALUATION latency |

**Cross-monitor (both, every PR):** review the other’s PR before merge; dry-run each other’s critical path (she runs his Compose once; he dry-runs her demo on Docker). Tag only with both signatures.

Shared interface: his `CaseRecord` + citation helpers in; her `Decision` out; both agree OUTPUT_CONTRACT fields. Neither edits client files.

---

## Sunday — 4 + 4

| Vidhi | Prajwal |
|---|---|
| Contracts + `decide()` escalate/request stubs | ToolClient (3 tries) + redaction |
| Address + identity missing logic (unit tests) | Ingest + store + manifest hash gate |
| Runner CLI: health → cases → one-case hook | Dockerfile + Compose + `DOCKER.md` |
| Review his PR; try D01 with his client when ready | Review her PR; ADR-0005 draft; smoke her decide() tests |

**Done when:** Each has 4 items done or blocked with a written handoff; both reviews posted.

---

## Monday — 5 + 5

| Vidhi | Prajwal |
|---|---|
| Finish escalate/request ENG-01 rules; preserve missing fields | Policy select + EDD/PEP/currency; non-address mismatches + discrepancies |
| Duplicate review + DRAFT-on-request_info only | CaseRecord wiring; failure → no citation |
| Packet merge of Decision + his citations; drive joint **12/12** | Citation verify_quote + template narrative + traces |
| Midpoint email to Diego | CI + leak scan + RUNBOOK **deploy** section + EVALUATION latency |
| Review all his Mon PRs; confirm Compose 12/12 | Review all her Mon PRs; spot-check D01/D03/D07; comment on midpoint draft |

**Done when:** 12/12; midpoint sent; 5/5 each; mutual reviews done.

---

## Tuesday — 4 + 4

| Vidhi | Prajwal |
|---|---|
| Tests/fixes for her domain (D03 address, D08, threshold handoff with him) | Tests/fixes for his domain (D04/D06/D07, equal-threshold with her) |
| **Write demo script** (D01 / D04 / D07 or D08) | Clean-clone **deployment** recovery; architecture + banned-pattern tests |
| Graded fixes; keep 12/12 | Finalize ADR-0005 + LIMITATIONS; finish EVALUATION numbers |
| Review his PRs; watch deploy dry-run | Review her PRs; **Docker dry-run of her demo script**; file gaps |

**Evening:** Joint rehearsal — she leads demo; he runs deploy path; both sign.

---

## Wednesday — 3 + 3

| Vidhi | Prajwal |
|---|---|
| Native fresh-setup; final `reports/dev.json`; tag prep | Docker fresh-setup; audit export; image = tag |
| Lead live demo from **her script**; hotfix her domain only | Live standby on **deploy/CI**; hotfix his lanes only |
| Diego submission email; merge after his review | Review email + her last PR; sign go/no-go on tag |

---

## Scoreboard (50–50)

| | Sun | Mon | Tue | Wed | Total |
|---|---|---|---|---|---|
| Vidhi | 4 | 5 | 4 | 3 | **16** |
| Prajwal | 4 | 5 | 4 | 3 | **16** |

Six workstreams each (table above). Neither person is “only docs” or “only ops.”

## Cut line (joint)

1. Renamed-case CI → manual  
2. Cloud → local Docker  
3. Maintenance email → log + runbook  

**Never cut:** both halves of domain, 12/12, demo script (Vidhi), deployment (Prajwal), mutual review, Diego updates.
