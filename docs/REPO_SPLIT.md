# Repo split — what lives where

**No commits are implied by this file.** When a human asks to commit, stage only the paths for the active branch purpose.

## On `main` (bare minimum both of us need)

| Path | Purpose |
|---|---|
| `AGENTS.md` | Agent mandates + git strategy |
| `.cursor/rules/kyc-copilot.mdc` | Always-on Cursor agent rule |
| `docs/ARCHITECTURE.md` | Pipeline and layer rules |
| `docs/adr/` | ADRs 0001–0005 |
| `contracts/policy_manifest.json` | Approved policy digests |
| `docs/REPO_SPLIT.md` | This split |

```sh
git checkout main
git add AGENTS.md .cursor/rules/kyc-copilot.mdc \
  docs/ARCHITECTURE.md docs/adr docs/REPO_SPLIT.md \
  contracts/policy_manifest.json
```

## On `docs/planning-distribution` (planning + lab + 50–50)

| Path | Purpose |
|---|---|
| `docs/WEEK10_LAB.md` | **Today:** Week 10 harden lab + PDF order |
| `docs/DAYWISE_PLAN.md` | Schedule (lab-first) |
| `docs/VIDHI_CHECKLIST.md` | Vidhi 50% |
| `docs/PRAJWAL_CHECKLIST.md` | Prajwal 50% |
| `docs/ALIGNMENT.md` | Whiteboard × ENG-01 |
| `docs/RULES_CATALOG.md` | Rule ↔ test index |
| `docs/RUNBOOK.md` | Ops + severe injection runbook |
| `docs/EVALUATION.md` | Scores + SLO metrics |
| `docs/LIMITATIONS_AND_ROADMAP.md` | Limits |
| `docs/CONTRIBUTIONS.md` | Who did what |
| `docs/client-updates/` | Diego drafts |

```sh
git checkout docs/planning-distribution
git add docs/WEEK10_LAB.md docs/DAYWISE_PLAN.md docs/VIDHI_CHECKLIST.md \
  docs/PRAJWAL_CHECKLIST.md docs/ALIGNMENT.md docs/RULES_CATALOG.md \
  docs/RUNBOOK.md docs/EVALUATION.md docs/LIMITATIONS_AND_ROADMAP.md \
  docs/CONTRIBUTIONS.md docs/client-updates docs/REPO_SPLIT.md
```

## Never stage

`tools/`, `data/`, `feedback/`, `examples/`, client docs listed in `AGENTS.md`.
