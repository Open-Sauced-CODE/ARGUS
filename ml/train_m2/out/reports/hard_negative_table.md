# Hard-negative table (corruptor, TRAIN partition)

## Pre-filter (all types)

| Type | n | gate_pass_rate | oracle_wrong_rate | unknown_count | hard_negative_rate |
| --- | --- | --- | --- | --- | --- |
| C1 | 504 | 1.000 | 1.000 | 0 | 1.000 |
| C2 | 504 | 0.845 | 1.000 | 0 | 0.845 |
| C3 | 141 | 1.000 | 1.000 | 0 | 1.000 |
| C4 | 504 | 1.000 | 0.000 | 0 | 0.000 |
| C5 | 78 | 0.000 | 1.000 | 0 | 0.000 |
| C6 | 504 | 1.000 | 0.000 | 0 | 0.000 |


**Dropped types (hard_negative_rate == 0):** C4, C5, C6

## Post-filter (kept types)

| Type | n | gate_pass_rate | oracle_wrong_rate | unknown_count | hard_negative_rate |
| --- | --- | --- | --- | --- | --- |
| C1 | 156 | 1.000 | 1.000 | 0 | 1.000 |
| C2 | 171 | 0.754 | 1.000 | 0 | 0.754 |
| C3 | 33 | 1.000 | 1.000 | 0 | 1.000 |
