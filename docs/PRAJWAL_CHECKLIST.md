# Prajwal — 50% checklist

Your half of a **50–50** split with Vidhi. Full day map: [`DAYWISE_PLAN.md`](DAYWISE_PLAN.md).  
**You own:** policy select + EDD + non-address mismatches, ToolClient/ingest/store/citations/narrative/traces, **deployment**, CI.  
**She owns:** escalate/request domain, runner, **demo script**, Diego, merge.  
**Monitor:** you review every `vidhi/*` PR; she reviews every `prajwal/*` PR.

Do not edit client files. Do not rewrite her demo script (dry-run + file gaps).  
Do not change her escalate/address modules without a paired PR.  
ENG-01: fixed packet text; models only in ADR-0005 roadmap.

---

## 1. Domain — your 50% of rules

- [ ] Policy select by customer type/jurisdiction + intake review date (approved files only)
- [ ] EDD: PEP or monthly total **strictly above** threshold; equal does not qualify
- [ ] Currency must be XCR when transactions present
- [ ] Non-address mismatches: jurisdiction, entity ref, owner/holder, birth year; missing ≠ diff
- [ ] Disputed jurisdiction → escalate signal; **no** product policy from it
- [ ] `discrepancies` entries for his conflict fields
- [ ] Tests for the above (D04/D06/D07-style, equal-threshold, jurisdiction/birth-year)

## 2. Evidence + citations — your 50% of app plumbing

- [ ] ToolClient: 4 tools, 3 retries, fail closed
- [ ] Redact `private_token`; extra fields ignore + log
- [ ] Ingest docs/policies; source-id suffix; Source ID/heading checks
- [ ] Store content + sha256; manifest: known hash change → stop; new file → notify, **no auto-load**
- [ ] Assemble `CaseRecord` for her `decide()` / shared router
- [ ] Citation recipes + `verify_quote`; no cite on failed tool
- [ ] Template narrative + JSONL traces
- [ ] Joint **12/12** (you drive Compose; she drives native)

## 3. Deployment — your 50% of delivery

- [ ] Dockerfile + Compose + `DOCKER.md`
- [ ] RUNBOOK deployment section; clean-clone recovery; `reset --confirm`
- [ ] CI + leak scan + architecture/banned-pattern tests
- [ ] ADR-0005 + EVALUATION latency (measured) + your CONTRIBUTIONS rows
- [ ] Image/Compose matches `v1.0` on submit day

## 4. Monitor her 50%

- [ ] Review PRs: escalate/request domain, runner, packet merge, demo script
- [ ] Spot-check D01 / D03 / D08
- [ ] **Docker dry-run of her demo script**; file gaps only
- [ ] Comment on Diego drafts; sign fresh-setup / tag go/no-go

## Done when

Your half of domain + plumbing + deployment are done; her half is reviewed by you; Compose 12/12 green; both signed tag.
