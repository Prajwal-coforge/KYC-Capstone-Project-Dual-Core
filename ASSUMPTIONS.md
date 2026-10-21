# Assumptions, scope and decisions

Last updated: 2026-10-21 (Day 3). Sources: BRIEF.md, docs/, and Diego's reply to our Day 2 email.
Rule of precedence: the supplied policy files (`KYC-SCOPE-01` and the policy versions) and the
output contract win over any assumption below. If they conflict, we follow the supplied rules and
raise it with the facilitator.

## 1. Confirmed with the client (Diego)

| # | Topic | Our proposal | Diego's answer | What we build |
|---|---|---|---|---|
| 1 | Address differences | Minor formatting differences = same address; material differences are shown side by side for the analyst, no source is authoritative | Aligns with their process | Conservative normalizer (see 3.1). Material difference -> `address_explanation` |
| 2 | Retrieval failure (sanctions or activity data) | Route as incomplete, never clear on partial checks | Yes, but surface that the review is incomplete **for that reason** | Escalate per KYC-SCOPE-01 and state the failed tool in the narrative (see 3.2) |
| 3 | Near-match names | Show both names, flag for analyst, internal only, never customer-facing | Yes | Packet lists both names, says "unresolved identity candidate" |
| 4 | Threshold change notification | Ask how they will notify us | Out of scope now; they want an admin dashboard later | Thresholds come only from versioned policy files. Dashboard goes in the roadmap |
| 5 | Multiple owners | Include and screen all owners | Yes | `owner_names` lists every registry owner |
| 6 | Duplicates | Keep the original packet, set aside repeats, similar names stay separate | Yes. **Use the supplied case/review ID to identify the review** | Dedupe key = case ID only. No fuzzy matching on names |
| 7 | AI-written summary | AI drafts the narrative, rules decide routing, analysts decide | OK | See 3.4 |
| 8 | Success measure | Time savings, issue detection, or both | **Time is the main concern, but we must not miss things by going faster** | Primary KPI: time per review. Guardrail: no missed escalations (see 4) |

## 2. Scope

In scope: limited companies in Alder or Birch, and sole proprietors in Alder; one direct ownership
level; the four read tools; draft packets for a human analyst; human approval step; evaluation,
monitoring, runbook and Docker deployment.

Out of scope (per brief): OCR, fine-tuning, complex entity resolution, external APIs, production
identity, polished UI, adjudication, any record creation (KYC is read-only).
Out of scope (per Diego): an admin dashboard for threshold or policy updates (future work).

Address and name handling: **US-style addresses only** (Diego's guidance). Names are compared only
through the screening service's `match_type`; we do no name matching ourselves. Dates are ISO
`YYYY-MM-DD` strings with no time zones, and the review date comes from the case, never today's date.

## 3. Design decisions that follow

### 3.1 Address comparison
- Normalize both strings: case, whitespace, punctuation, and recognized US street-suffix and
  directional abbreviations (for example St/Street, Ave/Avenue).
- Equal after normalization -> same address. We still record the event and cite both strings.
- Anything else, including abbreviations we do not recognize, is a **material** difference: show every
  version, require `address_explanation`, and never choose a source.
- Risk: KYC-SCOPE-01 does not mention normalization. Dev data has only identical or clearly
  different addresses, so this does not change dev results. Confirm with the facilitator.

### 3.2 "Incomplete" reviews
- A tool that still fails after 3 total attempts -> route `escalate` (KYC-SCOPE-01).
- The narrative must say the review is **incomplete because `<tool>` was unavailable**, that nothing
  was cleared, and that facts depending on it are unknown (`null`). No fabricated citations.
- Proposed extra output field `incomplete_reasons` (for example `["screening_unavailable"]`). The
  contract allows extra fields, which are inspected for leaks.

### 3.3 Linear, rules, or agent
| Part | Approach | Why |
|---|---|---|
| Fetch four tools, retries | Linear code | Fixed steps, bounded attempts |
| Policy selection, thresholds, routing precedence, missing fields | Rules (deterministic) | Auditable, testable, no hallucination |
| Duplicate detection | Rules on case ID | Fuzzy deduping is fragile |
| Narrative and follow-up wording | LLM or template, validated | Language is the only part that needs it |
| Approval | Human | Required boundary |

### 3.4 AI-written narrative standards (Diego: "these things write awfully")
- Input is the computed facts only, never raw document text.
- Fixed section order: recommendation, key facts, issues and conflicts, missing information,
  uncertainty and limits. Hard length cap. Plain, specific sentences; no boilerplate or filler.
- Validator rejects the draft and falls back to a template if it: changes the route, adds facts not in
  the input, includes `private_token` values, approves or rejects the customer, promises anything,
  or calls a near-match a confirmed identity.
- Review a sample of outputs by hand regularly (the first ten, then periodically).

## 4. Metrics: anything that skips normal work gets counted (Diego's advice)

Recorded as structured, redacted trace events and summarized per run:

| Metric | Why |
|---|---|
| Tool retries and tool failures that ended in escalation | Reliability of upstream systems |
| Addresses treated as same after normalization / material mismatches | How often the normalizer "decides" |
| Exact and near screening matches escalated | Escalation drivers |
| Unsupported scope, no policy for date, deep ownership escalations | Coverage gaps |
| Duplicate submissions set aside | Duplicate rate |
| Narrative fell back to template / validator rejections (with reason) | AI quality and cost of the AI path |
| Route distribution (complete / request / EDD / escalate) | Always-escalate or never-escalate drift |
| Seconds per case, tool calls per case, LLM tokens if used | Time KPI; measured, never invented |

**Baseline:** no baseline exists at the bank. Our first run on the dev set is the baseline; real
time savings need a pilot with analysts. Guardrail for "do not miss things": on dev gold, no case
may be routed less severely than expected.

## 5. Still open

| Topic | Owner | Current default |
|---|---|---|
| LLM access approved? | Facilitator | Template narrative; LLM only if approved |
| Is address normalization OK under the graded rules? | Facilitator | Conservative normalization, both strings cited |
| Pass bar (proposed 70/100 plus critical gates) | Facilitator | Assume proposed bar |
| Proposed `incomplete_reasons` field acceptable? | Facilitator | Include it, and keep the narrative explicit as well |

## 6. Roadmap notes (not building now)

- Admin dashboard for policy and threshold versions. Negotiate scope: policy versions and effective
  dates yes; agent prompts and scoring rubrics for regulatory review should not be freely editable.
- Postgres adapter behind the storage interface; queue and workers for volume.
- Pilot with real analysts to establish time-saved and detection baselines.
