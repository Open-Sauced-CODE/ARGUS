"""
ARGUS Phase 5, Step 20 - T0 deterministic templates.   match(finding) -> Patch-IR dict | None

`finding` is what the airlock returns: {"finding_id","rule_id","resource_id","fields","resource_ref"}.
A template reads ONLY the finding's fields and the rule's declared fields, and returns the single-attribute fix the dataset uses as reference
(same operations, same values). It returns None when the rule has no template or nothing needs changing.
"""

from privacy.airlock.projection import load_declarations

APPROVED_ALGORITHMS = ("AES256", "aws:kms", "aws:kms:dsse")
PUBLIC_FLAGS = ("block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets")
T0_RULES = ("dpdp.rule6a", "cis.s3_default_encryption", "dpdp.rule6_versioning", "dpdp.rule8_lifecycle",
            "dpdp.rule6_public_exposure", "cis.s3_public_access_block", "dpdp.rule6_logging")


def _set(attr, value):
    return {"op": "set_attr", "attr": attr, "value": value}


def _encryption(fields, declared):
    ops = []
    if fields.get("default_encryption") is not True:
        ops.append(_set("default_encryption", True))
    if "encryption_algorithm" in declared and fields.get("encryption_algorithm") not in APPROVED_ALGORITHMS:
        ops.append(_set("encryption_algorithm", "aws:kms"))
    return ops


def _public(fields, declared):
    return [_set(flag, True) for flag in PUBLIC_FLAGS if flag in declared and fields.get(flag) is not True]


def _versioning(fields, declared):
    return [] if fields.get("versioning_status") == "Enabled" else [_set("versioning_status", "Enabled")]


def _lifecycle(fields, declared):
    if fields.get("has_lifecycle_expiration") is True:
        return []
    return [{"op": "set_lifecycle_rule", "attr": "has_lifecycle_expiration", "value": True}]


def _logging(fields, declared):
    return [] if fields.get("logging_enabled") is True else [_set("logging_enabled", True)]


_TEMPLATES = {
    "dpdp.rule6a": _encryption, "cis.s3_default_encryption": _encryption,
    "dpdp.rule6_versioning": _versioning, "dpdp.rule8_lifecycle": _lifecycle,
    "dpdp.rule6_public_exposure": _public, "cis.s3_public_access_block": _public, "dpdp.rule6_logging": _logging,
}


def match(finding):
    rule_id = finding.get("rule_id")
    build = _TEMPLATES.get(rule_id)
    if build is None:
        return None
    declared = load_declarations().get(rule_id, set())
    ops = build(finding.get("fields", {}), declared)
    if not ops:
        return None
    return {"finding_id": finding["finding_id"], "resource_ref": finding["resource_ref"], "ops": ops, "rationale_ref": rule_id}
