# Gate-only evidence (first gate-passing draft per cluster; non-test clusters; Clopper-Pearson one-sided, delta 0.05)

| generator | scope | clusters | strict errors | harmful errors | UCB strict | UCB harmful | clean clusters still needed (alpha 0.05) |
|---|---|---|---|---|---|---|---|
| rft | all | 189 | 1 | 1 | 0.025 | 0.025 | None |
| rft | seen | 174 | 1 | 1 | 0.027 | 0.027 | None |
| rft | unseen | 15 | 0 | 0 | 0.181 | 0.181 | 44 |
| rft_v2 | all | 84 | 50 | 48 | 0.686 | 0.663 | None |
| rft_v2 | seen | 75 | 43 | 42 | 0.670 | 0.658 | None |
| rft_v2 | unseen | 9 | 7 | 6 | 0.959 | 0.902 | None |
| sft | all | 189 | 0 | 0 | 0.016 | 0.016 | 0 |
| sft | seen | 174 | 0 | 0 | 0.017 | 0.017 | 0 |
| sft | unseen | 15 | 0 | 0 | 0.181 | 0.181 | 44 |
| zeroshot | all | 15 | 4 | 4 | 0.511 | 0.511 | None |
| zeroshot | seen | 0 | 0 | 0 | n/a | n/a | 59 |
| zeroshot | unseen | 15 | 4 | 4 | 0.511 | 0.511 | None |

seen = the generator was trained on that input (its error rate is understated); unseen is the honest column.
