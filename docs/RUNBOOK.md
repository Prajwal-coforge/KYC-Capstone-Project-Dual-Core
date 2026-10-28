# Operator runbook

All data and institutions are fictional. Use one isolated mock state per team.

## Fresh setup

```sh
# Python 3.12 + uv required
uv sync --locked
uv run --locked python tools/validate_package.py
```

## Start the mock

```sh
uv run --locked python tools/runtime.py serve --port 8766
# health: GET http://127.0.0.1:8766/health
```

Docker alternative:

```sh
docker compose up --build -d
docker compose exec dev bash
```

## Run the copilot

Local/assessor default is SQLite (`--db .state/app.sqlite`). Compose/cloud set `KYC_DATABASE_URL` (or pass `--dsn`); that wins over `--db`. Never point `--db` at `mock.sqlite`.

```sh
# Ingest policies/documents and review every case listed by the service
uv run --locked python -m kyc_copilot --api-url http://127.0.0.1:8766 --out submissions/results.json

# Cloud Run: only the DSN env var is required (no sqlite path)
# KYC_DATABASE_URL=postgresql://… sslmode=require  (from secret manager)
# uv run --locked python -m kyc_copilot --api-url "$MOCK_URL" --out submissions/results.json

# Evaluate against development gold (assessors use new fixtures)
uv run --locked python -m kyc_copilot --evaluate --report reports/dev.json

# Submit drafts for human review (no agent approval)
uv run --locked python -m kyc_copilot --submit-reviews --poll-reviews
```

`--data` points at the fixture folder (default `data/dev`). Assessors will pass a different path.

## Human approval

```sh
uv run --locked python tools/runtime.py pending
uv run --locked python tools/runtime.py approve REVIEW_ID --reviewer reviewer-name
uv run --locked python tools/runtime.py reject REVIEW_ID --reviewer reviewer-name
uv run --locked python tools/runtime.py audit > reports/audit.json
```

Agents must never run `approve` / `reject`. KYC forbids `POST /v1/records` even after approval.

## Reset between assessment runs

Stop clients, then:

```sh
uv run --locked python tools/runtime.py reset --confirm
```

Use the same `--state` path on every operator command if non-default.

## Outage recovery

1. Confirm mock health (`GET /health`).
2. Restart `serve` if needed; retry counters survive restarts — reset between independent runs.
3. Re-run the copilot; cases with persistent tool faults escalate after 3 attempts.

## Deployment (local container or cloud store)

See [`DOCKER.md`](../DOCKER.md) and ADR-0005.

- **Graded / laptop path:** SQLite `--db .state/app.sqlite`. No Postgres required. No cloud secrets.
- **Compose:** `mock` (loopback 8766, SQLite mock bank) + `postgres:16-alpine` (copilot store) + `dev` (`KYC_DATABASE_URL`).
- **Cloud Run + Cloud SQL Postgres (or later RDS):** DSN from secret manager as `KYC_DATABASE_URL`, `sslmode=require` unless the URL already sets sslmode, least-privilege role, never `private_token` in the database. Drafts only — never create or update bank records.

Diego approved PostgreSQL for the copilot knowledge store in cloud deploy (scalability/security). Scope does not mandate SQLite.

## Retention and deletion

The copilot store (SQLite `.state/app.sqlite` or Postgres) holds policy/document text for citation checks and redacted tool evidence. It must **not** store `private_token` or review-log copies of full customer documents beyond ingested evidence. Between assessment runs: delete/rebuild `app.sqlite`, or drop/recreate the Postgres schema by restarting with a fresh volume. Mock state is separate (`.state/mock.sqlite`) and is reset with `reset --confirm`. The copilot must never open the mock file. Do not commit databases or `.env`.

## Severe failure: prompt injection in a case document (D08-class)

**Symptom:** Packet route looks wrong, narrative echoes “IMPORTANT SYSTEM MESSAGE”, or someone claims the bot “approved” a customer.

**Check first**
1. Open the case’s corporate/identity markdown; search for instruction-like lines (`IMPORTANT`, `ignore previous`, `approve`).
2. Inspect structured trace for that `case_id`: tool statuses, `reasons`, final `routing` — not free-text model chatter.
3. Confirm process list / code paths: no `approve` operator command and no `POST /v1/records` from the app.

**Confirm cause**
- Injected text appears only as **quoted evidence** (or quarantined unrecognized lines), not as a `ReasonCode` that forces approve.
- Routing still comes from `domain` precedence (D08 expected: normal complete_review when no other escalate signals).

**Immediate mitigation**
1. Do **not** run operator `approve` on a suspicious draft.
2. Re-run the single case with tracing on; save `trace.jsonl` + packet.
3. If narrative echoed the injection, fall back to template narrator and file a defect — routing must stay unchanged.
4. Reset mock state only between assessment runs (`reset --confirm`), not mid-debug if you need the audit trail.
5. Page / tell the teammate on-call if success-rate or p95 SLO alert also fired (see Week 10 metrics).
