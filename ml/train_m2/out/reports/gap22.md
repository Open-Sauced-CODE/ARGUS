# A_val reconciliation (sft)

A = Phase 5 recorded x group size; B = re-scored per key (must equal A); C = per example, finding_id aligned; D = per example, raw.

## phase5
- examples 361, keys 70, expected outcomes {'fixed': 317, 'escalated': 44}
- A 349  B 349  C 349  D 286  (B == A: True)
- differing examples (B vs C): 0, causes {}

## harvest
- examples 361, keys 70, expected outcomes {'fixed': 317, 'escalated': 44}
- A None  B 281  C 351  D 282  (B == A: None)
- differing examples (B vs C): 70, causes {'unexplained': 70}

