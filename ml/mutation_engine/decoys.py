"""
ARGUS Phase 5, Step 6 - decoys: perturb ONLY attributes no Rego rule reads.

Decoys change `extras` (tags, owner notes, unrelated numbers, key order). They never touch `attrs`, so the set of
rules that fire is unchanged. Because the airlock projects only the fields a rule reads (contracts D2), decoys never
reach the model; they stress patch application and the hidden check "decoys untouched".
"""

import random

from privacy.airlock.projection import load_declarations

POOL = {
    "cost_center": ["cc-101", "cc-204", "cc-330"],
    "owner_team": ["platform", "data", "web", "payments"],
    "environment": ["dev", "stage", "prod"],
    "managed_by": ["terraform"],
    "note": ["managed by terraform", "do not edit by hand"],
}
TAG_KEYS = ["team", "env", "app", "owner"]
TAG_VALUES = ["alpha", "beta", "gamma", "delta"]
NUMERIC_KEYS = ("allocated_storage", "monitoring_interval", "backup_retention_period")


def rule_field_names():
    names = set()
    for fields in load_declarations().values():
        names |= set(fields)
    return names


def decoy_extras(extras, rng):
    """Return (new extras, names of the decoys that were added or changed)."""
    forbidden = rule_field_names()
    out = dict(extras)
    changed = []
    out["tags"] = {rng.choice(TAG_KEYS): rng.choice(TAG_VALUES) for _ in range(rng.randint(1, 3))}
    changed.append("tags")
    for key in NUMERIC_KEYS:
        value = out.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and rng.random() < 0.5:
            out[key] = max(0, value + rng.choice([-10, -1, 1, 10]))
            changed.append(key)
    for key in rng.sample(sorted(POOL), rng.randint(0, 3)):
        out[key] = rng.choice(POOL[key])
        changed.append(key)
    assert not (set(out) & forbidden), "a decoy collides with a field a rule reads"
    keys = list(out)
    rng.shuffle(keys)
    return {k: out[k] for k in keys}, sorted(set(changed))


def decoys_untouched(original, decorated):
    """True when every rule-visible attribute is identical."""
    return original.resource_type == decorated.resource_type and original.attrs == decorated.attrs
