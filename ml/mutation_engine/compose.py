"""
ARGUS Phase 5, Step 6 - multi-violation composition and conflict rules.

compose(res, rng, k) picks up to k mutator variants for one base resource and applies them. Two chosen
mutators may never
  * write the same attribute,
  * make the same rule fire (so every fired rule has exactly ONE responsible mutator, which makes the
    reference patch of each finding unambiguous),
  * be the same mutator.
"""

import csv
from pathlib import Path

from ml.mutation_engine.mutators import ALL_MUTATORS


def applicable_pairs(res, mutators=ALL_MUTATORS):
    pairs = []
    for m in mutators:
        if res.resource_type not in m.resource_types:
            continue
        for variant in m.variants:
            if m.prepare(res, variant) is not None:
                pairs.append((m, variant))
    return pairs


def conflicts(a, b):
    (ma, va), (mb, vb) = a, b
    return (ma.mutator_id == mb.mutator_id
            or bool(ma.writes & mb.writes)
            or bool(set(ma.rules_for(va)) & set(mb.rules_for(vb))))


def compose(res, rng, k=1, weights=None, mutators=ALL_MUTATORS):
    """Returns (clean, broken, mutations) or None when no mutator applies to `res`.
    `clean` is the base with canonical values set (compliant); `broken` has k violations."""
    weights = weights or {}
    pool = applicable_pairs(res, mutators)
    chosen = []
    while pool and len(chosen) < k:
        w = [m.variants[v] * weights.get(m.mutator_id, 1.0) for m, v in pool]
        pick = rng.choices(pool, weights=w, k=1)[0]
        chosen.append(pick)
        pool = [p for p in pool if not conflicts(pick, p)]
    if not chosen:
        return None
    clean, steps = res.copy(), []
    for m, v in chosen:
        prepared = m.prepare(clean, v)
        if prepared is None:  # an earlier canonicalisation made this variant impossible: drop it
            continue
        clean = prepared
        steps.append((m, v))
    if not steps:
        return None
    broken, mutations = clean, []
    for m, v in steps:
        broken, mutation = m.mutate(broken, v)
        mutations.append(mutation)
    return clean.copy(), broken, mutations


def load_violation_counts(path):
    """{rule_id: count} from ml/real_data/out/violation_counts_train.csv (train-bucket repositories only)."""
    counts = {}
    p = Path(path)
    if p.exists():
        with open(p, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                counts[row["rule_id"]] = int(row["violating_records_in_train_repos"])
    return counts


def mutator_weights(counts, mutators=ALL_MUTATORS):
    """Sampling multiplier per mutator from how often its rules are violated in real train-bucket code
    (add-one smoothed, so a rule never seen in real code is still sampled)."""
    raw = {m.mutator_id: 1.0 + sum(counts.get(r, 0) for r in m.rules) for m in mutators}
    mean = sum(raw.values()) / len(raw)
    return {k: v / mean for k, v in raw.items()}
