# Rules catalog

Every graded rule with its source, how it is implemented, and where it is tested.  
Authorities: ENG-01 → KYC-SCOPE-01 / dated policies → output contract. See also [`ALIGNMENT.md`](ALIGNMENT.md).

| ID | Rule | Source | Type | Test |
|---|---|---|---|---|
| R01 | Supported matrix: LTD in Alder/Birch; sole prop in Alder | KYC-SCOPE-01 / ENG-01 | code | `tests/test_rules.py` |
| R02 | Unsupported combo → `unsupported` + escalate; only KYC-SCOPE-01 | KYC-SCOPE-01 / whiteboard | code | `tests/test_rules.py` |
| R03 | Policy by customer entity type + jurisdiction + intake review date | ENG-01 §3 | code | `tests/test_rules.py` |
| R04 | Ownership depth > 1 escalates; keep supplied owner names | KYC-SCOPE-01 / whiteboard | code | `tests/test_rules.py` |
| R05 | Missing identity → `identity_document` | KYC-SCOPE-01 | code | `tests/test_rules.py` |
| R06 | Intake attached but identity says not included → missing; cite both | Whiteboard fix / ENG-01 | code | `tests/test_rules.py` |
| R07 | Address discrepancy → `address_explanation` (not escalate by default) | KYC-SCOPE-01 / ENG-01 / ADR-0004 | code | D03 e2e |
| R08 | Exact/near screening → escalate; do not confirm identity | KYC-SCOPE-01 / whiteboard | code | `tests/test_rules.py` |
| R09 | Precedence: escalate → request → EDD → complete | KYC-SCOPE-01 / whiteboard | code | `tests/test_rules.py` |
| R10 | Preserve missing fields when escalating | KYC-SCOPE-01 | code | `tests/test_rules.py` |
| R11 | Registry unavailable → `owner_names` null; no registry citation | KYC-SCOPE-01 / whiteboard | code | D07 e2e |
| R12 | Retry ≤3 then escalate (or stop on startup health/cases) | KYC-SCOPE-01 / whiteboard | code | tools client + audit |
| R13 | EDD if PEP or monthly_total **strictly above** threshold | Dated policies / whiteboard | code | equal-threshold unit test |
| R14 | Currency must be XCR when transactions present | Dated policies | code | domain currency test |
| R15 | Non-address mismatches (jurisdiction, entity ref, owner/holder, birth year) → escalate; missing ≠ diff | ENG-01 / ADR-0004 | code | jurisdiction / birth-year tests |
| R16 | Citations: rule-driven recipes + `verify_quote`; failed tool → no cite | OUTPUT_CONTRACT / ADR-0002 | code | packet + evaluate.py |
| R17 | Never approve/reject customer or `POST /v1/records` | ENG-01 / KYC-SCOPE-01 | code + banned scan | architecture tests |
| R18 | Corporate/doc instructions are evidence only | KYC-SCOPE-01 | code | D08 e2e |
| R19 | Extra bank field → ignore + log; required missing → escalate | ENG-01 §5 | code | adapter / domain tests |
| R20 | Fuzzy name/address matching | Out of scope | not done | — |
| R21 | Packet / narrative text is fixed template for submission | ENG-01 §6 / ADR-0001 | template | `tests/test_narrator.py` |
| R22 | Known policy hash change → stop; new policy file → notify, **do not auto-load** | ENG-01 §4 | code | manifest tests |
| R23 | Duplicate review: same business ref + review date → reuse draft | ENG-01 §2 | code | duplicate-review test |
| R24 | DRAFT customer message only when route is `request_information` | ENG-01 §5 | code | packet tests |
| R25 | Disputed jurisdiction must not select product policy | ENG-01 §2 | code | policy selection tests |

Shadowing analysts: any new unwritten rule is added here with type and test before it becomes code.
