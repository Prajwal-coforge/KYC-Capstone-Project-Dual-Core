# Evaluation

Two checks, and they stay separate.

The first is a deterministic checker. It compares a packet to `feedback/dev_gold.json` and to the source text in `data/dev/dataset.json`. Route, facts, policy, deadline, and citations are either equal or they are not. The second is a person reading the note. The checker only asks that the note is a string of at least 20 characters. It does not score the prose.

Nothing in this project asks a model to grade a packet. The names below are the ones used in retrieval and agent evals. The right-hand column is the check this repo actually runs.

## How to run it

The copilot writes packets. The grader is a separate command. There is no `--evaluate` flag on `python -m kyc_copilot`.

```sh
uv run --locked python -m pytest tests -q
uv run --locked python -m kyc_copilot --api-url http://127.0.0.1:8766 --out submissions/results.json
uv run --locked python tools/evaluate.py \
  --data data/dev \
  --gold feedback/dev_gold.json \
  --submission submissions/results.json
```

`tools/evaluate.py` exits 0 only when every case passes and there are no format errors. The mock has to be up for the copilot command (`tools/runtime.py serve --port 8766`, or `docker compose`).

## What each metric is

| Name you will see in write-ups | What it usually means | What we compute |
|---|---|---|
| Faithfulness / groundedness | Share of claims in the answer that the retrieved text supports. RAGAS does this with a model. | `verify_quote`: a citation is kept only when the quote is an exact substring of the stored source. A lowercased sentence is rejected. A changed number is rejected. This is stricter than a model judge, and it only covers the quote, not every sentence of the note. |
| Context recall | Did the answer use the sources that should have been used? | The gold file lists `evidence_groups`. Every group must show up as a `source_id` on a valid citation. |
| Correctness | Did the answer match the labeled outcome? | Classification, routing, `policy_ids`, fact keys, `missing_information`, and `deadline` must match the gold row. Routing is membership in the allowed set. Policy ids are compared as a sorted list. |
| Citation validity | Is each citation attributable to a real source? | Every citation needs a string `source_id` and a non-blank quote, the id has to be in the dataset, and the quote has to occur in that source. One bad citation fails the case. |
| Answer relevancy | Embedding similarity between the question and the answer. Needs a model. | Not computed. A person reads the note. |
| Safety | Did the system leak a secret, follow an instruction in a document, or take an action it must not take? | Gates, not a blended score. `restricted_values` must be absent from the packet. The mock audit for the dev run contains `tool_read` only, no `POST /v1/records`. The D08 injection stays in the file as untrusted text and does not change the route. |
| Latency | p50, p95, p99, and max. The mean hides the slow case. | Wall time from the start of a case to the packet. The SLO uses the last 20 decision lines: success rate and p95. A packet inside 15 seconds is a success, including an escalation. Alert when success rate is under 0.95 or p95 is over 15,000 ms. |
| Retry bound | How many times a failed call is tried. | Shared cap of 3 attempts. After that the tool is failed and the case escalates. It does not guess the missing fact. |

## Dev set results

Measured 27 October 2026 on this machine. The checker is `tools/evaluate.py` against `feedback/dev_gold.json`. The heavy column is 30 repeats of the same 12 cases, 360 decisions, one process, one SQLite file.

| Metric | One dev-set pass | 30 repeats |
|---|---|---|
| Cases passed / total | 12 / 12 | 360 / 360 decisions, 0 route changes |
| Format errors | 0 | 0 |
| Audit write attempts (`POST /v1/records`) | 0. The mock audit for that run contains only `tool_read`. | same bound |
| Max attempts per tool | 3. KYC-D07 registry returns 503, 503, 503, then the case escalates. | same bound |
| Mean / p95 time to packet | p95 of the metrics window 165.7 ms | mean 18.6 ms, p50 4.9 ms, p95 167.2 ms, p99 170.4 ms, max 195.7 ms |
| Restricted token leaks in packet or the SQLite file | 0 | 0 |
| SLO | success rate 100%, alert false, line is 15 seconds | 360 / 360 inside the line |

KYC-D07 is the slow case. The registry is down, so the client waits out three attempts and then escalates. Its p95 across the 30 repeats is 171 ms. The other eleven cases sit between 4 ms and 8 ms. Escalation still counts as a packet, which is why the success rate stays at 100%.

The SLO line is 15 seconds for 95% of the last 20 cases. The measured p95 is 167 ms.

## Adversarial checks

| Scenario | Expected | Result |
|---|---|---|
| D03 address mismatch | `request_information` + `address_explanation`; cites each address source | Pass. Dev-set packet and the address tests. |
| Jurisdiction conflict (D03-like) | `escalate`; no product policy from disputed jurisdiction | Pass. `test_jurisdiction_conflict_cites_customer_and_corporate`. |
| D08 injection | `complete_review`; instruction not obeyed | Pass. The note does not contain the instruction or the private token. |
| D07 registry outage | escalate; `owner_names` null; no registry cite | Pass. Three attempts, then escalate. No registry citation. |
| Shuffled document list | same packet | Pass. `test_shuffled_document_order_does_not_change_the_packet` runs KYC-D01 with the document list reversed and the packets are equal. |
| Mismatched Source ID line | warning, and the header id is the one that is stored | Pass, with that behavior. `parse_file` warns that the header id differs from the filename and keeps the header id. It does not drop the file and it does not escalate on its own. |
| Known policy hash tampered | run stops / alert | Pass. Ingest raises and names `KYC-SCOPE-01`. |
| New policy file on disk | notify; not used in `policy_ids` | Pass. `KYC-POLICY-NEW-UNLISTED` is warned and not stored. The Alder threshold stays 30000. |
| Citation paraphrase / `12000.0` | `verify_quote` drops a quote that is not an exact excerpt | Pass. `test_verify_quote` rejects a lowercased sentence, a blank quote, and a quote from the wrong source. The exact excerpt `"monthly_total": 12000` is kept. A changed screening count is rejected. The dev-set grader accepted every quote that the packet kept. |
| Models off | routes unchanged; template narrative | Pass. No model is on the path. Thirty repeats produced the same twelve routes. |
| Renamed case IDs | still routes; no `KYC-Dnn` hardcoding | Pass. `test_renamed_case_id_still_completes` uses `CASE-RENAMED-77` with the same evidence shape and gets `complete_review` with owner Ari Vale. |

## Suite

173 tests, `uv run --locked python -m pytest tests -q`. Statement coverage of `src/kyc_copilot` is 1,332 statements, 0 missed, 100%. Coverage is measured with `coverage` added for the run (`uv run --with coverage`). It is not a project dependency and CI does not gate on it.

The 12-case gold comparison is the smoke path. The rest of the suite is the regression pass: ingest guards, the three-attempt client, the ledger, the template branches, and the rows in the table above.

## What these numbers say

The route is computed by `domain/rules.py`. The note is filled in by the template. A second pass of the same case comes out with the same route. A model on the decision path would add a network call and a way for the route to move between runs. This path has neither.

A failed tool does not become a fast wrong answer. KYC-D07 stops after three registry attempts, leaves `owner_names` null, and escalates. That case is the slowest one in the set. The mock audit shows no `POST /v1/records`. The restricted token is absent from the packet and from the SQLite file.

## What the checker does not prove

`tools/evaluate.py` says this in its own result: the automated checks do not establish semantic grounding of the prose, safe wording, human approval, tool correctness, or readiness. Review the narrative and the server audit separately. We did not compute a RAGAS score, an embedding relevancy score, or a model-judged faithfulness score.
