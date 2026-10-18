"""IAM mutator (Phase 5, Step 5): widen a clean statement with a wildcard. The legitimate entries stay visible
in the projected record, so the reference fix (set the list back without "*") is learnable and exact."""

import copy

from ml.mutation_engine.mutators.base import Mutator

MAX_ACTIONS = 20
MAX_RESOURCES = 10


def _set(attr, value):
    return {"op": "set_attr", "attr": attr, "value": copy.deepcopy(value)}


class IamFullAdmin(Mutator):
    mutator_id = "m_iam_full_admin"
    resource_types = ("AWSPolicyStatement",)
    variants = {"both": 1.0, "action_only": 1.0}
    rules = ("cis.iam_no_full_admin",)
    writes = frozenset({"action", "resource"})

    def prepare(self, res, variant):
        if res.resource_type not in self.resource_types or res.attrs.get("effect") != "Allow":
            return None
        action, resource = res.attrs.get("action"), res.attrs.get("resource")
        if not (isinstance(action, list) and isinstance(resource, list)):
            return None
        if not (1 <= len(action) <= MAX_ACTIONS and 1 <= len(resource) <= MAX_RESOURCES):
            return None
        if "*" in action:
            return None
        if variant == "both" and "*" in resource:
            return None
        if variant == "action_only" and "*" not in resource:
            return None
        return res.copy()

    def mutate(self, clean, variant):
        broken = clean.copy()
        original_action, original_resource = list(clean.attrs["action"]), list(clean.attrs["resource"])
        broken.attrs["action"] = original_action + ["*"]
        ops, paths = [_set("action", original_action)], ["action"]
        if variant == "both":
            broken.attrs["resource"] = original_resource + ["*"]
            ops.append(_set("resource", original_resource))
            paths.append("resource")
        return broken, self._mutation(variant, clean, broken, paths, ops)
