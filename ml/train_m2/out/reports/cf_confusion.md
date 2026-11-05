# Counterfactual labeler vs reference oracle

fix-route inputs with a reference: 235

Population: reference patches (truth = correct) + every gate-passing corruption (truth = reference oracle).

| variant | correct->correct | correct->wrong | wrong->correct | wrong->wrong | recall of wrong | precision of 'wrong' | false-wrong rate on correct |
|---|---|---|---|---|---|---|---|
| strict | 369 | 104 | 50 | 630 | 0.926 | 0.858 | 0.220 |
| lenient | 473 | 0 | 445 | 235 | 0.346 | 1.000 | 0.000 |

## By corruption type (truth, counterfactual label) -> n

- C1: truth=False,cf=valid_not_minimal: 234
- C2: truth=False,cf=valid_not_minimal: 157, truth=True,cf=minimal_correct: 3
- C3: truth=False,cf=minimal_correct: 50
- C4: truth=True,cf=minimal_correct: 183, truth=True,cf=valid_not_minimal: 52
- C6: truth=False,cf=wrong: 235
- C8: truth=False,cf=valid_not_minimal: 4
- reference: truth=True,cf=minimal_correct: 183, truth=True,cf=valid_not_minimal: 52

Reading: STRICT (label == minimal_correct) is the only usable reference-free rule; LENIENT mostly re-states the gate. Reference-free labels are WEAK and must never be used for calibration or evaluation.
