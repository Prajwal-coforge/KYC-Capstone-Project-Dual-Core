# ADR-0005: Model and deployment strategy

## Status

Accepted (submission scope)

## Context

The brief allows an LLM where it helps, with cohort-approved access. Only US-built models are allowed if used. Deployment must be reproducible; a local container is sufficient if cloud access is unavailable. Diego approved PostgreSQL for the copilot knowledge store in cloud deploy (scalability/security); the mock bank remains SQLite. Scope does not mandate SQLite. Recommendations stay drafts only — never create or update bank records.

## Decision

### Narrative models

- **Submission (ENG-01):** fixed/template packet text only — no live model.
- **Future (roadmap):** if approved, US-built only; fallback cloud primary → secondary → local → template. Routing and citations never depend on a model.
- CI must fail if an unapproved model name appears in config (when config exists).

### Deployment

- Target for submission: **local Docker Compose** (`mock` + `postgres` + `dev`) as in [`docker-compose.yml`](../../docker-compose.yml). Assessors may still run the CLI with default SQLite and no Compose.
- Copilot store: **SQLite** (`--db .state/app.sqlite`) locally; **PostgreSQL** via `--dsn` or `KYC_DATABASE_URL` in Compose / Cloud Run. The factory refuses `mock.sqlite`.
- Cloud Run + Cloud SQL Postgres (or later RDS): DSN from secret manager, default `sslmode=require` unless the URL sets sslmode or the host is localhost, least-privilege role.
- Runtime image: Python 3.12; `pydantic` + `psycopg[binary]`; `uv` for lockfile sync. No SQLAlchemy, asyncpg, requests, or httpx.
- Secrets: none required for the graded SQLite path; never store `private_token` or full document text in the knowledge store or review logs.

## Consequences

- Assessors can run without model credentials or Postgres.
- Cloud store is selectable without changing domain rules.
- Cloud deployment and model-fallback prototype remain optional; Postgres for the copilot store is now in scope after Diego's approval.
