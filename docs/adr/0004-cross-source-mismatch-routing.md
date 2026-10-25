# ADR-0004: Cross-source mismatch routing

## Status

Accepted (aligned with client ENG-01, 23 October 2026)

## Context

KYC-SCOPE-01 and practice case D03 require address discrepancies to request an explanation, not to escalate by default. ENG-01 states the same split explicitly. Silently picking one address is forbidden.

## Decision

| Mismatch | Route | Notes |
|---|---|---|
| Registered address (customer, registry, corporate filing) | `request_information` + `address_explanation` | Show all present addresses with sources; choose none. Missing corporate filing is not an address difference; still compare customer vs registry. |
| Jurisdiction, entity reference, owner/holder name, birth year | `escalate` | Show each value with its source; choose none. A missing value is not a difference. |
| Corporate filing jurisdiction ≠ customer | `escalate` | Neither value is used as jurisdiction for product-policy selection. |

Business type comes from the customer record; review date from the intake. A name agrees when it is one of the registry owner names.

## Consequences

- D03 and similar cases follow ENG-01 and KYC-SCOPE-01.
- Changing this split requires a new ENG-01 / policy version, not a quiet code change.
