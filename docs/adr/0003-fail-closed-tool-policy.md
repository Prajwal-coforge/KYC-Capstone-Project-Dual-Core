# ADR-0003: Fail-closed tool policy

## Status

Accepted

## Context

KYC-SCOPE-01: retry failed tools at most twice (three total attempts), then stop and escalate. A missing registry response means `owner_names` is null, not an empty list.

## Decision

One shared retry policy in the HTTP adapter (`MAX_ATTEMPTS = 3`). After exhaustion the case escalates with `incomplete_reasons` naming the tool. Registry failure sets `owner_names` to `null` and does not emit registry citations. Transient 503 may recover within the three attempts; persistent faults escalate.

## Consequences

- Audit must show ≤3 attempts per tool and no write attempts.
- Partial success never clears checks that depend on a failed tool.
