"""
ARGUS Phase 5, Steps 6-7 - build the examples of ONE base resource.

A base is mutated (1 to 4 violations), decorated with decoys, and produces ONE example per rule that fires
(each shows only that rule's fields, contracts D2). Everything is a pure function of (base, rng).
"""

import copy

from ml.mutation_engine.compose import compose
from ml.mutation_engine.decoys import decoy_extras
from ml.mutation_engine.labeler import label
from ml.mutation_engine.model import Resource
from ml.mutation_engine.project import model_input, raw_finding, tokenize_ops
from privacy.airlock.airlock import AirlockBlocked


def _plain(res):
    return {"resource_type": res.resource_type, "attrs": copy.deepcopy(res.attrs), "extras": copy.deepcopy(res.extras)}


def build_from_base(base, rng, k, vault, finding_prefix="F", weights=None, mutators=None):
    """Returns a list of example dicts (possibly empty). Keys: rule_id, input, target, meta, qa."""
    res = Resource.from_base(base)
    kwargs = {} if mutators is None else {"mutators": mutators}
    composed = compose(res, rng, k, weights, **kwargs)
    if composed is None:
        return []
    clean, broken, mutations = composed
    extras, decoy_names = decoy_extras(res.extras, rng)
    clean.extras, broken.extras = copy.deepcopy(extras), copy.deepcopy(extras)
    rules = sorted({r for m in mutations for r in m.rules_fired})
    out = []
    for n, rule_id in enumerate(rules):
        finding_id = "{}-{}".format(finding_prefix, n)
        raw = raw_finding(broken, finding_id, "tf-" + base["base_id"])
        try:
            record, receipt = model_input(raw, rule_id, vault)
        except AirlockBlocked:
            continue
        responsible = next(m for m in mutations if rule_id in m.rules_fired)
        patch = label(clean, broken, mutations, rule_id, finding_id, record["resource_ref"])
        patch["ops"] = tokenize_ops(raw, rule_id, record, patch["ops"], vault)
        out.append({
            "rule_id": rule_id,
            "input": record,
            "target": patch,
            "meta": {
                "base_id": base["base_id"], "bucket": base["source"]["bucket"],
                "mutators": [m.mutator_id for m in mutations], "variants": [m.variant for m in mutations],
                "responsible_mutator": responsible.mutator_id, "responsible_variant": responsible.variant,
                "n_violations": len(rules), "decoys": decoy_names, "route": responsible.route,
                "synthetic": base["source"].get("synthetic"),
            },
            "qa": {
                "original": _plain(clean), "mutated": _plain(broken), "rules_violated": rules,
                "paths": sorted({p for m in mutations for p in m.paths}),
                "mutations": [{"mutator_id": m.mutator_id, "variant": m.variant, "paths": m.paths} for m in mutations],
                "receipt_sha256": receipt["record_sha256"],
            },
        })
    return out


def resource_from_plain(plain):
    return Resource(plain["resource_type"], copy.deepcopy(plain["attrs"]), copy.deepcopy(plain["extras"]))
