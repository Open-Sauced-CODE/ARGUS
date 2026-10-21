# Results grid (gate pass: pass@1 / pass@k, count and Wilson 95% interval)

## pass@1
| model | A_val | train300 | B1 | B2 | C_verifier | C_mined | gold |
|---|---|---|---|---|---|---|---|
| zeroshot | 96/361 = 26.6% [22.3, 31.4] | 55/300 = 18.3% [14.4, 23.1] | 103/261 = 39.5% [33.7, 45.5] | 140/180 = 77.8% [71.2, 83.2] | 166/466 = 35.6% [31.4, 40.1] | - | 29/80 = 36.2% [26.6, 47.2] |

## pass@k
| model | A_val | train300 | B1 | B2 | C_verifier | C_mined | gold |
|---|---|---|---|---|---|---|---|
| zeroshot | 176/361 = 48.8% [43.6, 53.9] | 116/300 = 38.7% [33.3, 44.3] | 132/261 = 50.6% [44.5, 56.6] | 140/180 = 77.8% [71.2, 83.2] | 173/466 = 37.1% [32.9, 41.6] | - | 31/80 = 38.8% [28.8, 49.7] |

## Safety and escalation
| model | set | unsafe candidates | schema-valid | hidden-ok among gate-passing | escalate P / R | median s to first pass |
|---|---|---|---|---|---|---|
| zeroshot | A_val | 391/560 | 551/560 | 62/107 | n/a / 0.00 | 5.0108641386032104 |
| zeroshot | train300 | 513/696 | 687/696 | 60/109 | n/a / 0.00 | 10.86331045627594 |
| zeroshot | B1 | 126/288 | 288/288 | 55/97 | n/a / 0.00 | 6.387713193893433 |
| zeroshot | B2 | 15/80 | 80/80 | 34/58 | n/a / 0.00 | 5.538654088973999 |
| zeroshot | C_verifier | 787/864 | 863/864 | 33/35 | n/a / 0.00 | 7.279467821121216 |
| zeroshot | gold | 190/240 | 240/240 | 29/29 | n/a / 0.00 | 7.3883116245269775 |

## Training-versus-held-out gap (pass@1 percentage points; investigate if above 20)
- zeroshot: train300 minus B1 = -21.1 points
- zeroshot: train300 minus B2 = -59.4 points
- zeroshot: train300 minus C_verifier = -17.3 points
