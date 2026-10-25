# ADR-0005: Model and deployment strategy

## Status

Accepted (submission scope)

## Context

The brief allows an LLM where it helps, with cohort-approved access. Only US-built models are allowed if used. Deployment must be reproducible; a local container is sufficient if cloud access is unavailable.

## Decision

### Narrative models

- **Submission (ENG-01):** fixed/template packet text only — no live model.
- **Future (roadmap):** if approved, US-built only; fallback cloud primary → secondary → local → template. Routing and citations never depend on a model.
- CI must fail if an unapproved model name appears in config (when config exists).

### Deployment

- Target for submission: **local Docker Compose** (`mock` + `dev` sharing network namespace) as in [`docker-compose.yml`](../../docker-compose.yml).
- Runtime image: Python 3.12, stdlib application dependencies only; `uv` for lockfile sync.
- Secrets: none required for the graded path; never store `private_token` or full document text in review logs.

## Consequences

- Assessors can run without model credentials.
- Cloud deployment and model-fallback prototype are cut-line items; documented in the roadmap if not shipped.
