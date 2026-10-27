# Phase 6 pilot report (handoff H1)

Ollama version: 0.40.11. Generated from `pilot_results.json`; every number below is measured, none estimated.

## Profile A pilot (20 stratified inputs, top-5 logprobs)

| Generator | Model | Model digest | Inputs | Lines | Errors | Error rate | Text/token mismatches | Mean s per generation | Mean tokens |
|---|---|---|---|---|---|---|---|---|---|
| rft | argus-m1-rft | sha256:02e86d0a0b5e | 20 | 165 | 0 | 0.0% | 0 | 5.557 | 56.5 |
| sft | argus-m1-sft | sha256:ded5fad28aad | 20 | 160 | 0 | 0.0% | 0 | 4.873 | 55.6 |
| zeroshot | qwen3.5:4b | sha256:d8b0f5e9760c | 20 | 160 | 0 | 0.0% | 0 | 10.15 | 106.4 |

## Throughput

| Label | Model | Threads | Generations | Errors | Wall seconds | Generations per hour |
|---|---|---|---|---|---|---|
| parallel4 | argus-m1-sft | 1 | 60 | 0 | 77.1 | 2802 |
| parallel4 | argus-m1-sft | 2 | 60 | 0 | 72.8 | 2969 |
| parallel4 | argus-m1-sft | 4 | 60 | 0 | 74.5 | 2899 |

Full job: 7,704 lines (profile A, three generators) plus 5,136 (profile B, sft and rft). Divide by the best generations-per-hour above to plan the overnight runs.

## Replication against the Phase 5 candidate logs

Exact = identical text. Canonical = same ops and rationale_ref (finding_id ignored). Sample 0 is greedy.

| Generator | Compared | Exact (all) | Canonical (all) | Exact sample 0 | Canonical sample 0 |
|---|---|---|---|---|---|
| rft | 160 | 100.0% | 100.0% | 100.0% | 100.0% |
| sft | 160 | 65.0% | 95.0% | 65.0% | 95.0% |
| zeroshot | 160 | 70.0% | 79.4% | 70.0% | 95.0% |

Per sample index (canonical match):

| Generator | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| rft | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sft | 95.0% | 95.0% | 95.0% | 95.0% | 95.0% | 95.0% | 95.0% | 95.0% |
| zeroshot | 95.0% | 80.0% | 75.0% | 80.0% | 75.0% | 80.0% | 75.0% | 75.0% |

## Diversity (mean distinct canonical answers out of 8, profile A)

| Generator | Measured now | Phase 5 |
|---|---|---|
| rft | 1.00 | 1.00-1.06 |
| sft | 1.45 | 1.1-1.9 |
| zeroshot | 7.05 | 5.7-7.8 |

## Profile B check (local experiment for 1.2 and 1.4; only 1.0 is the contract)

| Generator | Temperature | Mean distinct of 8 | Schema-valid share | Error rate |
|---|---|---|---|---|
| rft | 1.0 | 1.10 | 100.0% | 0.0% |
| rft | 1.2 | 1.10 | 100.0% | 0.0% |
| rft | 1.4 | 1.15 | 100.0% | 0.0% |
| sft | 1.0 | 1.45 | 100.0% | 0.0% |
| sft | 1.2 | 1.60 | 100.0% | 0.0% |
| sft | 1.4 | 1.75 | 100.0% | 0.0% |

## Verdict

READY for the full harvest. SFT at T=1.0 gives only 1.45 distinct answers (below 1.5): propose a profile B change to Shaurya by pull request.

