# Submission update for Diego (draft)

Subject: KYC Review Copilot — submission (2026-10-28)

Diego,

**Delivered**

- Working copilot: tools → deterministic rules → cited packet → optional human review submit/poll.
- Evaluation: see `docs/EVALUATION.md` and `reports/dev.json` (actual numbers only).
- Architecture and ADRs under `docs/`; runbook for fresh setup and recovery.
- Behavior follows ENG-01 (including address vs other-field mismatch routing; fixed-code packet text; new policies reported, not auto-loaded).

**How to run**

```sh
uv sync --locked
uv run --locked python tools/runtime.py serve --port 8766
uv run --locked python -m kyc_copilot --evaluate
```

**Limitations / roadmap:** template narrative; address vs other-mismatch split as proposed; output detail and US-model fallback on the roadmap; PII retention in the runbook.

Vidhi
