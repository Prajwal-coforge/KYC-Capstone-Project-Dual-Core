# TDD and OOP Strategy — Migration to `src/kyc_copilot/`

Reference for the ENG-01 migration that moves the KYC Review Copilot from `app/` into the 7-layer package `src/kyc_copilot/` (`python -m kyc_copilot`), then retires `app/` at the end of Phase 4.

Agent rule companion: [`.cursor/rules/tdd-oop-workflow.mdc`](../.cursor/rules/tdd-oop-workflow.mdc).  
Authorities: ENG-01 → KYC-SCOPE-01 / dated policies → [`OUTPUT_CONTRACT.md`](OUTPUT_CONTRACT.md) → [`AGENTS.md`](../AGENTS.md) → ADRs → [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Environment

| Constraint | Rule |
|---|---|
| Dependencies | `pyproject.toml` `dependencies = []` — Python 3.12 **stdlib only** |
| Models / I/O | `@dataclass(frozen=True)`, `abc.ABC`, `typing.Protocol`, `urllib.request`, `sqlite3`, `unittest` |
| Never import | `pydantic`, `pytest`, `requests`, `httpx`, or any third-party library |
| Test command | `PYTHONPATH=src:. python3 -m unittest` |
| Docker tests | `docker compose exec -e PYTHONPATH=/app/src:/app dev uv run --locked python -m unittest` |
| Git | Human commits; agent never commits/pushes/amends/merges unless asked. **Open a PR before every major coding release.** |

Client-owned paths are never edited: `tools/`, `data/`, `feedback/`, `examples/`, `BRIEF.md`, `docs/API.md`, `docs/OUTPUT_CONTRACT.md`, `docs/POLICY_GUIDE.md`, `docs/ASSESSMENT.md`.

## Red → Green → Refactor

Every cycle follows this order. No exceptions.

1. **RED** — Write or update the unit test in `tests/` first. Run unittest and confirm failure for the expected reason. Do not write implementation before that proof.
2. **GREEN** — Smallest change in `src/kyc_copilot/<layer>/` so the new test and the full suite pass.
3. **REFACTOR** — Remove duplication; keep the suite green.
4. **STOP** — Summarize files changed and provide a conventional commit message. Wait for human go-ahead before the next cycle.

Phases 1–3 may keep thin `app/` re-exports so existing tests keep importing `app.*`. Phase 4 switches all imports to `kyc_copilot.*` and deletes `app/`.

## Target package layout

```
src/kyc_copilot/
  contracts/     models.py, interfaces.py
  ingestion/     parsing.py, ingest.py
  domain/        rules.py, packet.py
  narrative/     narrator.py
  observability/ tracing.py
  adapters/      redaction.py, sqlite_store.py, tools_client.py
  runner/        pipeline.py, cli.py
  __main__.py    # python -m kyc_copilot
```

### Import boundaries

| Package | May import | Must not |
|---|---|---|
| `contracts` | stdlib only | network, files, model, other layers |
| `ingestion` | `contracts` | network (`urllib`), model |
| `domain` | `contracts` | I/O, SQLite, HTTP, clock, model |
| `narrative` | `contracts` | raw documents, mock server |
| `observability` | `contracts` | domain rules, network |
| `adapters` | `contracts`, `observability` | domain rules |
| `runner` | all layers | — |

AST enforcement lives in `tests/architecture/test_boundaries.py` (added from Cycle 1.1 onward; tightened through Phase 4).

## OOP: reflective `StatutoryRule` registry

Defined in `kyc_copilot.contracts.interfaces`:

- `StatutoryRule(ABC)` with `_registry: ClassVar[dict[str, type[StatutoryRule]]] = {}`
- Concrete subclasses declare `rule_id: ClassVar[str]` and `precedence: ClassVar[int]`
- `__init_subclass__` auto-registers concrete subclasses
- `ordered_rules()` returns instances sorted by `(precedence, rule_id)`

Domain rule classes (Phase 3) include, among others:

| Class | Precedence (plan) |
|---|---|
| `ToolAvailabilityRule` | 10 |
| `CrossSourceConflictRule` | 11 |
| `ScopeAndPolicyRule` | 12 |
| `OwnershipDepthRule` | 14 |
| `ScreeningMatchRule` | 16 |
| `IdentityDocumentRule` | 20 |
| `AddressComparisonRule` | 22 |
| `EddAndPepRule` | 30 |

Routing still follows [`ARCHITECTURE.md`](ARCHITECTURE.md) scope precedence. `missing_information` fields may remain on escalated packets.

## ENG-01 guards

### Policy manifest (`contracts/policy_manifest.json`)

Handled in `ingestion/ingest.py` (PolicyManifestGuard):

- Known policy `.md` whose SHA-256 differs from the manifest → raise `IngestError` and stop the run.
- Brand-new policy file not listed in the manifest → append maintenance warning `new_policy_file_not_loaded:<source_id>` and **do not** load into active `policies`.

### Documents

- Identify by source-id suffix: `-INTAKE`, `-CORPORATE`, `-IDENTITY` (never list position).
- Parse corporate fields: `Filing jurisdiction:`, `Declared owner:`, `Registered address in supplied filing:`.
- Parse identity fields: `Name:`, `Birth year:`, `Document reference:`; detect `"not supplied"` / `"was not included"`.

### Cross-source non-address conflicts → `escalate`

If two sources give different **non-empty** values for jurisdiction (Customer vs Corporate), entity reference (Intake vs Customer), owner/holder name (Identity/Corporate vs Registry owners), or birth year:

- Route `escalate`; cite each source; do not pick a winner.
- Disputed jurisdiction → `facts["jurisdiction"] = None` and `policy_ids = ["KYC-SCOPE-01"]` (no product policy).
- Missing value on one source is **not** a conflict.

### 3-way address → `request_information`

Compare Customer, Registry, and Corporate Filing addresses (US suffix normalization). Missing corporate filing is not a difference. Differing present addresses → `missing_information` includes `address_explanation`, cite all present addresses, route `request_information` unless an escalate condition wins (missing fields may still stay on the packet).

### Identity document → `request_information`

Missing file, intake status ≠ `attached`, body saying not supplied/included, or missing holder `Name:` → `identity_document` in `missing_information`.

### Narrative DRAFT gate

Include a `DRAFT` customer request message **only** when `routing == "request_information"`.

## Four phases (cycle map)

### Phase 0 — Guardrails (this doc + agent rule)

Create `.cursor/rules/tdd-oop-workflow.mdc` and this strategy doc. No application code.

### Phase 1 — `contracts/` + `ingestion/`

| Cycle | Focus |
|---|---|
| 1.1 | Wire `src/` on `PYTHONPATH`; freeze `contracts/models.py` + `contracts/interfaces.py`; architecture boundary tests |
| 1.2 | `ingestion/parsing.py` — corporate & identity fields; suffix checks |
| 1.3 | `ingestion/ingest.py` — PolicyManifestGuard; no `urllib` in ingestion |

### Phase 2 — `observability/` + `adapters/`

| Cycle | Focus |
|---|---|
| 2.1 | `observability/tracing.py` — depends only on contracts |
| 2.2 | `adapters/` — redaction, sqlite_store (`SCHEMA_VERSION = 3`), tools_client |

### Phase 3 — `domain/` polymorphic rules

| Cycle | Focus |
|---|---|
| 3.1 | Reflective `StatutoryRule` registry; migrate existing rule behavior |
| 3.2 | `CrossSourceConflictRule` |
| 3.3 | 3-way `AddressComparisonRule` + identity holder checks |

### Phase 4 — `narrative/` + `runner/`, retire `app/`

| Cycle | Focus |
|---|---|
| 4.1 | `domain/packet.py` — discrepancy citations for corporate/identity |
| 4.2 | `narrative/narrator.py` — DRAFT request gate |
| 4.3 | `runner/` + `__main__.py`; switch tests to `kyc_copilot.*`; delete `app/`; AST lock |

## Conventional commits

Prefer layer scopes matching the package touched, for example:

- `docs(tdd): add TDD/OOP migration strategy and agent rule`
- `feat(contracts): …` / `feat(ingestion): …` / `feat(domain): …`
- `test(architecture): …`

One logical change per commit; tests for a behavior change ship with that change. Do not stage client-owned paths.

## PR discipline

- Feature work on `feat/vidhi/<slug>` or `Vidhi` / `vidhi/<slug>` as agreed with the team.
- One primary layer per PR when possible; contract changes prefer their own PR.
- **Before every major coding release, open a PR** for review. Do not push directly to `main`. Do not merge unless the human asks.
