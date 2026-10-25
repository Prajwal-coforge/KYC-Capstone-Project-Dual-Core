# ADR-0002: Strict contracts and raw-source citations

## Status

Accepted

## Context

Loose dictionaries invent or drop fields. The evaluator requires exact quotes from named sources. The whiteboard shows a per-case **citation ledger** filled from successful sources and from mismatches, then copied into the packet. ENG-01 requires each differing value to be shown with its source and forbids inventing evidence for failed tools.

## Decision

### Contracts

Every handoff uses frozen dataclasses (tools, documents, CaseRecord, reason codes, packet). `private_token` is stripped in the adapter before any contract object is built.

### Citation generation (rule-driven ledger)

1. Persist full source text (and sha256) under `source_id` at ingest/fetch.  
2. After `decide()`, build ledger candidates from **reasons and facts** using fixed recipes:  
   - Markdown: whole line by known prefix (e.g. `Review date:`, `EDD monthly threshold:`).  
   - Tools: canonical JSON fragment `"key": value` (sorted-keys / standard spaces).  
3. Keep a candidate only if `quote` is a non-empty exact substring of that source’s stored text (`verify_quote`).  
4. Tool failure after retries: record failure on the case; **do not** add a citation for that source.  
5. Copy the verified ledger into packet `citations`. Side-by-side conflicts may also appear in `discrepancies`.

Optional field spans at ingest are allowed as an optimization; they are not required if recipes + verify are correct.

### Rejected alternatives (for this submission)

- LLM-proposed quotes  
- RAG / embedding search over policies  
- Paraphrasing or number reformatting

## Consequences

- Same evidence → same citations.  
- Grader and ENG-01 exact-quote rules are enforceable in unit tests.  
- Slight formatting changes to numbers break the quote — by design.
