# Phase 6 intake report

## Dataset manifest

10 files verified, 0 problem(s)

## Sets: rows versus distinct inputs (the real sample size)

| set | rows | distinct inputs | max rows per input | escalate rows | routes |
|---|---|---|---|---|---|
| train | 2507 | 230 | 80 | 360 | {'fix': 2147, 'escalate': 360} |
| A_val | 361 | 70 | 20 | 44 | {'fix': 317, 'escalate': 44} |
| B1 | 261 | 36 | 20 | 80 | {'fix': 181, 'escalate': 80} |
| B2 | 180 | 10 | 40 | 40 | {'fix': 140, 'escalate': 40} |
| C_verifier | 466 | 108 | 74 | 51 | {'fix': 415, 'escalate': 51} |
| gold | 80 | 30 | 10 | 9 | {'fix': 71, 'escalate': 9} |
| C_mined | 0 | 0 | 0 | 0 | {} |

## Share of each set's distinct inputs that is also in train

| set | distinct | also in train | share |
|---|---|---|---|
| A_val | 70 | 55 | 79% |
| B1 | 36 | 36 | 100% |
| B2 | 10 | 10 | 100% |
| C_verifier | 108 | 32 | 30% |
| gold | 30 | 14 | 47% |

## Candidate logs by generator and set

| generator | set | inputs | candidates | gate-passing | passing but hidden-fail | empty replies | mean distinct answers of 8 |
|---|---|---|---|---|---|---|---|
| zeroshot | A_val | 70 | 560 | 107 | 45 | 0 | 7.243 |
| zeroshot | train300 | 87 | 696 | 109 | 49 | 0 | 7.437 |
| zeroshot | B1 | 36 | 288 | 97 | 42 | 0 | 6.778 |
| zeroshot | B2 | 10 | 80 | 58 | 24 | 0 | 5.7 |
| zeroshot | C_verifier | 108 | 864 | 35 | 2 | 0 | 7.833 |
| zeroshot | gold | 30 | 240 | 29 | 0 | 0 | 7.533 |
| sft | A_val | 70 | 560 | 550 | 4 | 8 | 1.114 |
| sft | train300 | 87 | 696 | 694 | 11 | 0 | 1.138 |
| sft | B1 | 36 | 288 | 286 | 11 | 0 | 1.167 |
| sft | B2 | 10 | 80 | 79 | 11 | 0 | 1.5 |
| sft | C_verifier | 108 | 864 | 849 | 0 | 0 | 1.648 |
| sft | gold | 30 | 240 | 231 | 0 | 0 | 1.933 |
| rft | A_val | 70 | 560 | 489 | 0 | 0 | 1.0 |
| rft | train300 | 87 | 696 | 656 | 8 | 0 | 1.046 |
| rft | B1 | 36 | 288 | 182 | 8 | 0 | 1.056 |
| rft | B2 | 10 | 80 | 56 | 8 | 0 | 1.0 |
| rft | C_verifier | 108 | 864 | 840 | 0 | 0 | 1.019 |
| rft | gold | 30 | 240 | 224 | 0 | 0 | 1.0 |

Logprobs saved in the Phase 5 logs: **False**

Natural negatives (distinct inputs with a gate-passing but hidden-check-failing candidate): zeroshot 21, sft 4, rft 1, union 22

## pass@k recomputed from the logs versus the Phase 5 summaries

36 comparisons, 0 differ by more than 0.5 point

## contract/harvest_inputs.jsonl

321 inputs in the list; 321 distinct inputs across all sets; identical sets: **True** (missing from list 0, extra in list 0)

## Source-repository licences

13155 bases; copyleft: 1808 (13.7%) {'GPL-3.0': 1164, 'MPL-2.0': 451, 'GPL-2.0': 76, 'AGPL-3.0': 75, 'CC-BY-SA-4.0': 28, 'LGPL-3.0': 6, 'EPL-2.0': 3, 'EUPL-1.2': 3, 'EPL-1.0': 1, 'LGPL-2.1': 1}
