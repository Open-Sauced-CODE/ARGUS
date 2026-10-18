"""
ARGUS Phase 5, Step 7 - the labeler: (clean, broken, mutations, rule) -> Patch-IR.

It diffs the two resources, checks that the diff is exactly what the mutators declared, takes the inverse operations of
the ONE mutator responsible for the finding's rule, and validates the result against remediate/patch_ir/schema.json.
"""

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from ml.mutation_engine.model import MISSING, apply_patch, diff_attrs

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "remediate" / "patch_ir" / "schema.json"
_VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8-sig")))


class LabelError(ValueError):
    pass


def schema_errors(patch):
    return sorted(e.message for e in _VALIDATOR.iter_errors(patch))


def label(clean, broken, mutations, rule_id, finding_id, resource_ref):
    responsible = [m for m in mutations if rule_id in m.rules_fired]
    if len(responsible) != 1:
        raise LabelError("rule {} has {} responsible mutators (need exactly 1)".format(rule_id, len(responsible)))
    mutation = responsible[0]
    changed = diff_attrs(clean, broken)
    declared = {p for m in mutations for p in m.paths}
    if set(changed) != declared:
        raise LabelError("diff {} does not match declared paths {}".format(sorted(changed), sorted(declared)))
    patch = {"finding_id": finding_id, "resource_ref": resource_ref,
             "ops": copy.deepcopy(mutation.inverse_ops), "rationale_ref": rule_id}
    errors = schema_errors(patch)
    if errors:
        raise LabelError("patch is not schema-valid: {}".format(errors))
    if mutation.route == "fix":
        fixed = apply_patch(broken, patch)
        for path in mutation.paths:
            if fixed.attrs.get(path, MISSING) != clean.attrs.get(path, MISSING):
                raise LabelError("patch does not restore {}".format(path))
    return patch
