# Vidhi — 50% checklist

Your half of a **50–50** split with Prajwal. Full day map: [`DAYWISE_PLAN.md`](DAYWISE_PLAN.md).  
**You own:** escalate + request_information domain, runner/batch, packet merge, **demo script**, Diego, merge.  
**He owns:** policy/EDD/mismatches domain, ToolClient/ingest/store/citations/narrative, **deployment**/CI.  
**Monitor:** he reviews every `vidhi/*` PR; you review every `prajwal/*` PR.

Do not edit client files. Do not take over Docker unless he is blocked (then pair).  
Authority: ENG-01 → policies → output contract.

---

## 1. Domain — your 50% of rules

- [ ] Unsupported matrix → escalate, `unsupported`, only `KYC-SCOPE-01`
- [ ] Tool unavailable after 3 → escalate (consume his failure flags)
- [ ] Ownership depth > 1 → escalate
- [ ] Exact/near screening → escalate; do not confirm identity
- [ ] Identity missing / not included → `identity_document`; preserve when escalating
- [ ] Address three-way → `address_explanation`; missing filing ≠ address diff
- [ ] Routing precedence integration with **his** EDD/mismatch signals (agree call order in code)
- [ ] Tests for the above (D01 complete path, D02/D03-style identity/address)

## 2. Runner / packet — your 50% of app shell

- [ ] CLI: health → cases → batch; duplicate key (business ref + review date)
- [ ] Merge his citations + your Decision into OUTPUT_CONTRACT packet
- [ ] DRAFT customer message only when route is `request_information`
- [ ] `POST /v1/reviews` + poll; no `POST /v1/records`
- [ ] Joint **12/12** ownership with him (you drive native; he drives Compose)

## 3. Demo + client — your 50% of delivery

- [ ] **Demo script** D01 / D04 / D07 or D08
- [ ] Fix gaps from his Docker dry-run
- [ ] Lead rehearsal + live demo
- [ ] Diego midpoint + submission emails
- [ ] Merge to `main` only after his review; tag after both sign fresh-setup

## 4. Monitor his 50%

- [ ] Review PRs: ToolClient, ingest, manifest, citations, EDD/mismatch domain, Docker, CI, EVALUATION
- [ ] Confirm Compose 12/12 matches native
- [ ] Sign his deploy recovery before submit

## Done when

Your half of domain + runner + demo + Diego are done; his half is reviewed by you; 12/12 green; both signed tag.
