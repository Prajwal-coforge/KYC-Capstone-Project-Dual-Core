# Limitations and roadmap

## Known limitations (submission)

- Template narrative only; no LLM in the graded path.
- No fuzzy name or address matching; any difference is surfaced as a mismatch (or address explanation).
- **Address strategy (2-tier):**
  - **Tier 1 (implemented):** In-memory deterministic `TokenMapAddressCanonicalizer` behind the `AddressCanonicalizer` protocol — zero network latency, never throws CRF/`RepeatedLabelError` on non-US jurisdictions like `Alder`/`Birch`, fails closed to `address_explanation` on unmapped differences.
  - **Tier 2 (future production adapter):** Pluggable postal verification (`Loqate` / Smarty USPS CASS / `libpostal`) implementing `AddressCanonicalizer`, with automatic fallback to Tier 1 on timeout or parse ambiguity.
- Address mismatch → `request_information` per written policy and D03; ADR-0004 awaits Diego confirmation.
- Local/assessor default is still single-process SQLite (`--db .state/app.sqlite`). Compose and cloud use PostgreSQL for the copilot store (Diego-approved); the mock bank remains SQLite. Not multi-region HA.
- Display detail level is not yet a separate analyst preference; packet always includes full citations and discrepancies.
- Shadow renamed-ID suite may be run manually if not in CI.

## Roadmap

1. **Output detail tuning** after Diego feedback (display setting separate from routing).
2. **Decision-model candidates** only where rules cannot encode judgment; each needs a catalog entry and eval.
3. **US-only model fallback** for narrative: cloud primary → secondary → local → template (ADR-0005).
4. **PII governance**: retention schedule, deletion tooling, no full document text in review logs.
5. **Cloud SQL / RDS hardening**: IAM auth, rotation, read replicas when concurrency needs them. Adapter already selected by `KYC_DATABASE_URL`.
6. **Admin dashboard** for policy versions (Diego: future; no UI prompt editing).

## Cut line applied

Model-fallback prototype is documented here rather than shipped if time-boxed. Copilot PostgreSQL (Compose / Cloud Run DSN) is in scope after Diego approval. Core 12-case replay, injection/leak tests, ADR-0004, runbook, and evaluation results are not cut. The mock bank stays SQLite; drafts only.
