# Label acceptance (distinct candidates and clusters; generated rows never summed)

## Natural, pool = all

| scope | candidates | positives | strict neg | harmful neg | clusters | clusters w/ strict neg | clusters w/ harmful neg |
|---|---|---|---|---|---|---|---|
| rft | 238 | 235 | 3 | 3 | 235 | 3 | 3 |
| rft_v2 | 239 | 139 | 100 | 93 | 127 | 70 | 64 |
| sft | 255 | 243 | 12 | 11 | 236 | 10 | 9 |
| union | 541 | 358 | 183 | 170 | 243 | 86 | 77 |
| zeroshot | 155 | 72 | 83 | 75 | 50 | 23 | 17 |

## Natural, pool = usable

| scope | candidates | positives | strict neg | harmful neg | clusters | clusters w/ strict neg | clusters w/ harmful neg |
|---|---|---|---|---|---|---|---|
| rft | 192 | 189 | 3 | 3 | 189 | 3 | 3 |
| rft_v2 | 110 | 54 | 56 | 54 | 84 | 55 | 53 |
| sft | 196 | 193 | 3 | 2 | 189 | 3 | 2 |
| union | 282 | 216 | 66 | 63 | 189 | 61 | 59 |
| zeroshot | 16 | 12 | 4 | 4 | 15 | 4 | 4 |

## Natural, pool = calibration

| scope | candidates | positives | strict neg | harmful neg | clusters | clusters w/ strict neg | clusters w/ harmful neg |
|---|---|---|---|---|---|---|---|
| rft | 15 | 15 | 0 | 0 | 15 | 0 | 0 |
| rft_v2 | 9 | 2 | 7 | 6 | 9 | 7 | 6 |
| sft | 15 | 15 | 0 | 0 | 15 | 0 | 0 |
| union | 39 | 28 | 11 | 10 | 29 | 10 | 9 |
| zeroshot | 16 | 12 | 4 | 4 | 15 | 4 | 4 |

## Corruptor (train-only, distinct)

distinct rows 151, hard negatives 144, seed clusters 103

| type | distinct | hard negatives | seed clusters |
|---|---|---|---|
| C1 | 52 | 52 | 52 |
| C2 | 52 | 45 | 45 |
| C3 | 47 | 47 | 47 |

## Pre-registered bar (natural and corruptor reported separately)

- natural usable strict-negative clusters, POOLED over all generators: 61 vs 59: **PASS** (pooled count, see deployment line)
- natural usable strict-negative candidates: 66
- corruptor hard negatives (distinct): 144
- total 210 vs 300: **FAIL (shortfall 90)** (natural share 0.31)
- Corruptor negatives are train-only and trivially separable unless shortcut_by_type says otherwise; evaluation and calibration use natural candidates only.

## Deployment generator (sft)

- usable strict-negative clusters: 3
- calibration pool: 15 clusters, 0 strict negatives
- **NO NEGATIVES IN THE CALIBRATION POOL: the auto-apply error rate of this generator cannot be estimated from it**
- the pooled natural-cluster count includes non-deployed generators (e.g. rft_v2, zeroshot); it supports TRAINING M2 across generators, not the deployment error estimate

## Calibration pool: smallest error rate certifiable with 0 errors (binomial, delta 0.05)

| generator | clusters | min alpha |
|---|---|---|
| rft | 15 | 0.181 |
| rft_v2 | 9 | 0.283 |
| sft | 15 | 0.181 |
| zeroshot | 15 | 0.181 |

rows without answer_key: 0
