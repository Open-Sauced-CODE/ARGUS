"""
ARGUS Phase 5, Step 8 - the eight QA checks on every dataset example.

    1  the target rule fires on the mutated resource
    2  the original resource is clean under ALL rules
    3  applying the reference fix to the mutated resource restores exactly what the mutator broke
       (and the stored patch agrees with the mutator's declared inverse, up to airlock tokens)
    4  the reference patch clears the stub gate (D3): "fixed" for fix examples, "escalated" for escalate examples
    5  the reference patch is valid against the Patch-IR schema
    6  decoys: original and mutated resource carry the same extras, no extra collides with a rule field,
       and the attribute diff is exactly the declared paths
    7  the model input is byte-identical to a fresh run of the deployed airlock, and holds no "tf-" resource id
    8  leakage (contracts D10): the hash of the FULL mutated resource is unique inside a split and never shared between splits

Public: run_checks(splits, recheck_airlock=True, log=None) -> dict(failures, counts, stats)
"""

import json
from collections import Counter, defaultdict

from ml.mutation_engine.dataset_io import canon, full_hash, input_key, target_key
from ml.mutation_engine.decoys import rule_field_names
from ml.mutation_engine.examples import resource_from_plain
from ml.mutation_engine.labeler import schema_errors
from ml.mutation_engine.model import MISSING, apply_patch, diff_attrs
from ml.mutation_engine.mutators import BY_ID
from ml.mutation_engine.qa.gate_stub import TOKEN_RE, gate_many
from ml.real_data.rego_runner import evaluate

CHECK_LABELS = {
    1: "target rule fires on the mutated resource",
    2: "original resource is clean under all rules",
    3: "reference fix restores exactly what was broken",
    4: "reference patch clears the stub gate",
    5: "reference patch is schema-valid",
    6: "decoys untouched, diff equals declared paths",
    7: "input identical to a fresh airlock run",
    8: "no full-resource hash shared inside or between splits",
}


def reconstruct_mutation(example):
    """Rebuild the responsible Mutation (its inverse ops and paths) from what the example stores."""
    clean = resource_from_plain(example["qa"]["original"])
    mutator = BY_ID[example["meta"]["responsible_mutator"]]
    _broken, mutation = mutator.mutate(clean, example["meta"]["responsible_variant"])
    return mutation


def _value_agrees(target, reference):
    if target == reference:
        return True
    if isinstance(target, list) and isinstance(reference, list) and len(target) == len(reference):
        return all(_value_agrees(t, r) for t, r in zip(target, reference))
    return (
        isinstance(target, str)
        and isinstance(reference, str)
        and (TOKEN_RE.search(target) is not None or "[REDACTED_" in target)
    )


def ops_agree(target_ops, reference_ops):
    """Same operations; values equal, or equal up to airlock tokens (a tokenized string stands for a real one)."""
    if len(target_ops) != len(reference_ops):
        return False
    for t, r in zip(target_ops, reference_ops):
        if t.get("op") != r.get("op") or t.get("attr") != r.get("attr") or t.get("reason") != r.get("reason"):
            return False
        if ("value" in t) != ("value" in r) or not _value_agrees(t.get("value"), r.get("value")):
            return False
    return True


def check_roundtrip(example):
    """Check 3. Returns a list of problem texts."""
    problems = []
    mutation = reconstruct_mutation(example)
    original = resource_from_plain(example["qa"]["original"])
    mutated = resource_from_plain(example["qa"]["mutated"])
    if not ops_agree(example["target"]["ops"], mutation.inverse_ops):
        problems.append("stored patch does not agree with the mutator's declared inverse")
    fixed = apply_patch(mutated, {"ops": mutation.inverse_ops})
    for key in sorted(set(original.attrs) | set(mutated.attrs) | set(fixed.attrs)):
        got = fixed.attrs.get(key, MISSING)
        if mutation.route == "fix" and key in mutation.paths:
            want = original.attrs.get(key, MISSING)
        else:
            want = mutated.attrs.get(key, MISSING)
        if got != want:
            problems.append("attribute {} is {!r} after the fix, expected {!r}".format(key, got, want))
    return problems


def _chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def run_checks(splits, recheck_airlock=True, log=None):
    """splits: {"train": [examples], "val": [...], "B1": [...], "B2": [...]}"""
    log = log or (lambda *_a: None)
    failures = []
    counts = Counter()

    def fail(check, example, text, split):
        failures.append({"check": check, "split": split, "id": example.get("id", "?"), "detail": text})

    flat = [(name, ex) for name in splits for ex in splits[name]]
    counts["examples"] = len(flat)

    # ---- checks 1 and 2 (one batch through OPA) --------------------------------------------------------------
    log("checks 1-2: running the Rego rules on {} originals and mutated resources".format(len(flat)))
    mutated_views = [resource_from_plain(ex["qa"]["mutated"]).rule_view() for _n, ex in flat]
    original_views = [resource_from_plain(ex["qa"]["original"]).rule_view() for _n, ex in flat]
    verdicts = evaluate(mutated_views + original_views)
    n = len(flat)
    for i, (name, ex) in enumerate(flat):
        fired = set(verdicts[i].deny) | set(verdicts[i].warn)
        if ex["rule_id"] not in fired:
            fail(1, ex, "rule {} does not fire on the mutated resource (fires: {})".format(ex["rule_id"], sorted(fired)), name)
        if not verdicts[n + i].clean:
            fail(2, ex, "original is not clean: {}".format(sorted(set(verdicts[n + i].deny) | set(verdicts[n + i].warn))), name)

    # ---- checks 3, 5, 6 (pure Python) -------------------------------------------------------------------------
    forbidden = rule_field_names()
    for name, ex in flat:
        try:
            for problem in check_roundtrip(ex):
                fail(3, ex, problem, name)
        except Exception as exc:  # a broken example must be reported, never crash the run
            fail(3, ex, "round trip raised {}: {}".format(type(exc).__name__, str(exc)[:120]), name)
        errors = schema_errors(ex["target"])
        if errors:
            fail(5, ex, errors[0][:140], name)
        original = resource_from_plain(ex["qa"]["original"])
        mutated = resource_from_plain(ex["qa"]["mutated"])
        if original.extras != mutated.extras:
            fail(6, ex, "extras differ between original and mutated", name)
        if set(mutated.extras) & forbidden:
            fail(6, ex, "an extra collides with a rule field: {}".format(sorted(set(mutated.extras) & forbidden)), name)
        if set(diff_attrs(original, mutated)) != set(ex["qa"]["paths"]):
            fail(6, ex, "attribute diff {} differs from declared paths {}".format(
                sorted(diff_attrs(original, mutated)), ex["qa"]["paths"]), name)

    # ---- check 4: the reference clears the stub gate ----------------------------------------------------------
    log("check 4: running the stub gate on {} reference patches".format(n))
    results = gate_many([(ex["input"], ex["target"]) for _n, ex in flat])
    for (name, ex), res in zip(flat, results):
        want = "escalated" if ex["meta"]["route"] == "escalate" else "fixed"
        if not res.passed or res.outcome != want:
            fail(4, ex, "gate outcome {} (wanted {}): {}".format(res.outcome, want, "; ".join(res.reasons)[:160]), name)

    # ---- check 7: byte-identical to a fresh airlock run -------------------------------------------------------
    if recheck_airlock:
        from ml.mutation_engine.project import raw_finding, throwaway_vault
        from privacy.airlock.airlock import AirlockBlocked, run_airlock

        log("check 7: re-running the airlock on {} examples".format(n))
        with throwaway_vault() as vault:
            for name, ex in flat:
                if "tf-" in json.dumps(ex["input"]):
                    fail(7, ex, "a 'tf-' resource id is visible in the input", name)
                raw = raw_finding(resource_from_plain(ex["qa"]["mutated"]), ex["input"]["finding_id"], "tf-" + ex["meta"]["base_id"])
                try:
                    again, _receipt = run_airlock(raw, ex["rule_id"], vault=vault)
                except AirlockBlocked as exc:
                    fail(7, ex, "airlock now blocks this record: {}".format(str(exc)[:100]), name)
                    continue
                if canon(again) != canon(ex["input"]):
                    fail(7, ex, "stored input differs from a fresh airlock run", name)

    # ---- check 8: leakage by full hash -------------------------------------------------------------------------
    owner = {}
    for name, ex in flat:
        h = full_hash(ex["rule_id"], ex["qa"]["mutated"])
        if ex["meta"].get("full_hash") not in (None, h):
            fail(8, ex, "meta.full_hash does not match the stored resource", name)
        if h in owner:
            other = owner[h]
            where = "inside split " + name if other[0] == name else "between {} and {}".format(other[0], name)
            fail(8, ex, "same full-resource hash {} ({}; also {})".format(h[:12], where, other[1]), name)
        else:
            owner[h] = (name, ex.get("id", "?"))

    return {"failures": failures, "counts": dict(counts), "stats": distribution_stats(splits)}


def distribution_stats(splits):
    """Numbers for the QA report and the dataset card."""
    stats = {"splits": {}, "input_overlap_with_train": {}}
    train_inputs = {input_key(ex) for ex in splits.get("train", [])}
    for name, rows in splits.items():
        by_rule = Counter(ex["rule_id"] for ex in rows)
        by_mutator = Counter(ex["meta"]["responsible_mutator"] for ex in rows)
        by_family_route = Counter(ex["meta"]["route"] for ex in rows)
        n_ops = Counter(len(ex["target"]["ops"]) for ex in rows)
        n_viol = Counter(ex["meta"]["n_violations"] for ex in rows)
        targets_per_input = defaultdict(set)
        for ex in rows:
            targets_per_input[input_key(ex)].add(target_key(ex))
        distinct = defaultdict(set)
        for ex in rows:
            distinct[ex["rule_id"]].add(input_key(ex))
        chars = sorted(len(canon(ex["input"])) + len(canon(ex["target"])) for ex in rows)
        stats["splits"][name] = {
            "examples": len(rows),
            "distinct_inputs": len(targets_per_input),
            "ambiguous_inputs": sum(1 for t in targets_per_input.values() if len(t) > 1),
            "by_rule": dict(sorted(by_rule.items())),
            "distinct_inputs_by_rule": {k: len(v) for k, v in sorted(distinct.items())},
            "by_mutator": dict(sorted(by_mutator.items())),
            "by_route": dict(by_family_route),
            "ops_per_patch": dict(sorted(n_ops.items())),
            "violations_per_resource": dict(sorted(n_viol.items())),
            "approx_tokens_p50_p99_max": [chars[len(chars) // 2] // 3, chars[int(len(chars) * 0.99)] // 3, chars[-1] // 3] if chars else [0, 0, 0],
        }
        if name != "train":
            seen = sum(1 for ex in rows if input_key(ex) in train_inputs)
            stats["input_overlap_with_train"][name] = {"examples_with_input_seen_in_train": seen, "examples": len(rows)}
    return stats
