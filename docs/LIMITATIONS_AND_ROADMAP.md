# Limitations and roadmap

## Known limitations (submission)

- Template narrative only; no LLM in the graded path.
- No fuzzy name or address matching; any difference is surfaced as a mismatch (or address explanation).
- Address mismatch → `request_information` per written policy and D03; ADR-0004 awaits Diego confirmation.
- Single-process SQLite knowledge store sized for a handful of concurrent reviewers, not multi-host HA.
- Display detail level is not yet a separate analyst preference; packet always includes full citations and discrepancies.
- Shadow renamed-ID suite may be run manually if not in CI.

## Roadmap

1. **Output detail tuning** after Diego feedback (display setting separate from routing).
2. **Decision-model candidates** only where rules cannot encode judgment; each needs a catalog entry and eval.
3. **US-only model fallback** for narrative: cloud primary → secondary → local → template (ADR-0005).
4. **PII governance**: retention schedule, deletion tooling, no full document text in review logs.
5. **Postgres adapter** behind `KnowledgeStore` when concurrency or multi-host requires it.
6. **Admin dashboard** for policy versions (Diego: future; no UI prompt editing).

## Cut line applied

Model-fallback prototype and cloud deploy are documented here rather than shipped if time-boxed. Core 12-case replay, injection/leak tests, ADR-0004, runbook, and evaluation results are not cut.
