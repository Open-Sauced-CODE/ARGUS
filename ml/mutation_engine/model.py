"""
ARGUS Phase 5, Steps 5-7 - the objects the mutation engine works on.

Resource  : one base resource as the Step 4 corpus stores it (rule-visible `attrs`, harmless `extras`).
Mutation  : what one mutator did, and the Patch-IR operations that undo it.
apply_patch: applies a Patch-IR object to a Resource (the stand-in for the Phase 7 compiler in the QA checks).
"""

import copy
from dataclasses import dataclass, field

MISSING = "<missing>"


class UnsupportedOp(ValueError):
    pass


@dataclass
class Resource:
    resource_type: str
    attrs: dict
    extras: dict = field(default_factory=dict)

    def copy(self):
        return Resource(self.resource_type, copy.deepcopy(self.attrs), copy.deepcopy(self.extras))

    def rule_view(self):
        """The dictionary the Rego rules read (input.resource)."""
        return dict(self.attrs, resource_type=self.resource_type)

    @classmethod
    def from_base(cls, base):
        return cls(base["resource_type"], copy.deepcopy(base["attrs"]), copy.deepcopy(base.get("extras", {})))


@dataclass
class Mutation:
    mutator_id: str
    variant: str
    rules_fired: list      # every rule this mutation makes fire (deny or warn)
    paths: list            # attribute names the mutation itself changed
    before: dict           # their values before (MISSING when absent)
    after: dict            # their values after (MISSING when removed)
    inverse_ops: list      # Patch-IR operations (without finding ids) that undo it
    route: str = "fix"     # "fix" or "escalate"


def get_attr(res, name):
    return res.attrs.get(name, MISSING)


def diff_attrs(original, mutated):
    """{attr: (before, after)} for every rule-visible attribute that differs (MISSING when absent)."""
    out = {}
    for key in sorted(set(original.attrs) | set(mutated.attrs)):
        a, b = original.attrs.get(key, MISSING), mutated.attrs.get(key, MISSING)
        if a != b:
            out[key] = (a, b)
    return out


def apply_patch(resource, patch_ir):
    """Apply a Patch-IR object to a copy of `resource` (attrs only). `escalate` changes nothing."""
    out = resource.copy()
    for op in patch_ir["ops"]:
        kind = op["op"]
        if kind in ("set_attr", "restrict_cidr", "set_lifecycle_rule", "enable_feature"):
            out.attrs[op["attr"]] = copy.deepcopy(op["value"])
        elif kind == "escalate":
            continue
        else:
            raise UnsupportedOp("operation {!r} is not used by Phase 5 data".format(kind))
    return out
