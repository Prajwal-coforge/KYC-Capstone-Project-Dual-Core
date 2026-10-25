# Agent instructions — KYC Review Copilot

Read before editing. Policy and the output contract win over this file.

These rules live on **`main`**. Team planning and task distribution live on branch **`docs/planning-distribution`** (see [`docs/REPO_SPLIT.md`](docs/REPO_SPLIT.md)).

## Read first

1. [`docs/OUTPUT_CONTRACT.md`](docs/OUTPUT_CONTRACT.md)
2. [`data/dev/policies/KYC-SCOPE-01.md`](data/dev/policies/KYC-SCOPE-01.md)
3. [`docs/API.md`](docs/API.md)
4. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and every file under [`docs/adr/`](docs/adr/)
5. Models under [`src/kyc_copilot/contracts/`](src/kyc_copilot/contracts/) (once present)

## Layer map

| Folder | May use | Must not use |
|---|---|---|
| `contracts/` | nothing inside the app | network, files, model |
| `domain/` | `contracts` | network, files, clock, model |
| `ingestion/` | `contracts` | network, model |
| `adapters/` | `contracts`, traces | domain rules |
| `narrative/` | `contracts` only | raw documents, mock server |
| `observability/` | `contracts` | domain rules, network |
| `runner/` | all of the above | — |

Stay inside one layer per change unless a person approved a multi-layer pull request.

## Never edit (client package)

- `tools/`, `data/`, `feedback/`, `examples/`
- Client docs: `docs/API.md`, `docs/OUTPUT_CONTRACT.md`, `docs/POLICY_GUIDE.md`, `docs/ASSESSMENT.md`, `BRIEF.md`

## Banned

- Reading `dataset.json`, `feedback/dev_gold.json`, or mock fault settings to decide a case
- `POST /v1/records` (KYC is read-only)
- Hardcoding case IDs such as `KYC-D01`
- Using `date.today()` / `datetime.now()` for review dates (dates come from intake; exercise year is 2026)
- Letting a language model choose route, policy, or facts
- Loose `dict` handoffs between pipeline steps (use contracts)
- Printing or logging `private_token`
- Retrying outside the shared rule: 3 attempts, then escalate

## Documents

- Identify documents by the suffix of the source ID (`-INTAKE`, `-CORPORATE`, `-IDENTITY`), never by list position
- For intake, prefer `intake_source` from `GET /v1/cases`
- Check file contents: inner `Source ID:` must match the requested ID; heading must match the type
- Exactly one of each type per case; missing, duplicate, or unknown → escalate

## Mismatch routing (ADR-0004 / ENG-01)

- Address (customer / registry / filing): `request_information` + `address_explanation`; missing filing is not an address difference
- Jurisdiction, entity reference, owner/holder name, birth year: `escalate`; missing value is not a difference; cite each source; do not pick one
- Disputed jurisdiction must not select a product policy
- New policy files: notify / log for maintenance — do **not** auto-load into rules

## Git strategy (agents must follow)

### Branches

- Default integration branch is **`main`**. Do not push directly to `main` unless a human explicitly asks.
- **Shared rules / ADRs / architecture** ship via PRs into `main` (this file, `docs/adr/`, `docs/ARCHITECTURE.md`, contracts manifest, agent rules).
- **Team planning and task distribution** ship on **`docs/planning-distribution`** (or a PR from that branch into `main` only when humans ask to publish plans).
- Feature work: `feat/<person>/<slug>` or `agent/<human-owner>/<slug>`.
- Deploy/CI work: `prajwal/<slug>` or `feat/prajwal/<slug>`.
- Application/domain work: `vidhi/<slug>` or `feat/vidhi/<slug>`.
- One primary layer per branch/PR when possible. Contract changes get their own PR.

### Commits

- **Do not create commits unless the human explicitly asks** in the current turn.
- Never update git config, never `--force` to `main`, never skip hooks unless the human asks.
- Conventional commits with layer scope: `feat(domain): …`, `test(architecture): …`, `docs(adr): …`.
- One logical change per commit; tests for a behavior change go in the same commit.
- Do not commit client-owned paths, secrets, `.env`, or `private_token` values.
- If a commit fails hooks, fix and create a **new** commit (do not amend unless the human asks and amend rules are met).

### Pull requests

- Open a PR for review; do not merge your own PR unless the human asks.
- Vidhi merges to `main` after review. Prajwal’s PRs need Vidhi’s review; Vidhi’s app PRs need Prajwal’s review (50–50 monitor rule).
- Prefer squash merges to `main` when the team uses that policy.
- PR description: what / why / how to test. No invented eval numbers.

### What agents may stage

| On `main` (rules) | On `docs/planning-distribution` |
|---|---|
| `AGENTS.md`, `.cursor/rules/**` | `docs/DAYWISE_PLAN.md`, checklists, `ALIGNMENT.md` |
| `docs/ARCHITECTURE.md`, `docs/adr/**` | `docs/EVALUATION.md`, `RUNBOOK.md`, `CONTRIBUTIONS.md`, `LIMITATIONS_*`, `RULES_CATALOG.md`, `client-updates/**` |
| `contracts/policy_manifest.json` | planning-only notes |

Never stage `tools/`, `data/`, `feedback/`, `examples/`, or client docs listed above.

## Stop and ask a person before

- Changing contracts / models, routing order, or policy selection
- Adding dependencies, changing CI, or editing more than one layer at once
- Weakening a test to go green
- A case that does not fit the written rules
- Committing, pushing, force-pushing, or merging without an explicit human request
- Mixing planning-only files into a rules PR (or rules into a planning-only PR) without asking

## Tests

Any behavior change ships with a test in the same commit. Prefer small commits: `feat(domain): …`, `test(architecture): …`.
