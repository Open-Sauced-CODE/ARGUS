# A_val reconciliation (rft)

A = Phase 5 recorded x group size; B = re-scored per key (must equal A); C = per example, finding_id aligned; D = per example, raw.

## phase5
- examples 361, keys 70, expected outcomes {'fixed': 317, 'escalated': 44}
- A 287  B 287  C 361  D 289  (B == A: True)
- differing examples (B vs C): 74, causes {'unexplained': 74}

## harvest
- examples 361, keys 70, expected outcomes {'fixed': 317, 'escalated': 44}
- A None  B 287  C 361  D 289  (B == A: None)
- differing examples (B vs C): 74, causes {'unexplained': 74}

