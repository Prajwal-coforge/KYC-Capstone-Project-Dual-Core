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

```sh
# Ingest policies/documents and review every case listed by the service
uv run --locked python -m kyc_copilot --api-url http://127.0.0.1:8766 --out submissions/results.json

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

## Deployment (local container)

See [`DOCKER.md`](../DOCKER.md) and ADR-0005. Compose runs `mock` (loopback 8766) and `dev` (shared network namespace). State lives in the `kyc-state` volume. No cloud secrets required for the graded path.

## Retention and deletion

Application SQLite (`.state/app.sqlite`) stores policy/document text for citation checks and redacted tool evidence. It must **not** store `private_token` or review-log copies of full customer documents beyond ingested evidence. Delete or rebuild the app DB between assessment runs (`rm .state/app.sqlite` or re-ingest). Mock state is separate (`.state/mock.sqlite`) and is reset with `reset --confirm`. Do not commit either database.
