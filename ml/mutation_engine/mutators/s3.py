"""S3 mutators (Phase 5, Step 5). Each breaks exactly what its Rego rules check."""

from ml.mutation_engine.mutators.base import Mutator

APPROVED_ALGORITHMS = ("AES256", "aws:kms", "aws:kms:dsse")
FLAGS = ("block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets")


def _set(attr, value):
    return {"op": "set_attr", "attr": attr, "value": value}


class SseOff(Mutator):
    mutator_id = "m_s3_sse_off"
    resource_types = ("AWSS3Bucket",)
    variants = {"clear": 1.0, "keep": 1.0}
    rules = ("dpdp.rule6a", "cis.s3_default_encryption")
    writes = frozenset({"default_encryption", "encryption_algorithm"})

    def prepare(self, res, variant):
        if res.resource_type not in self.resource_types or res.attrs.get("default_encryption") is not True:
            return None
        if res.attrs.get("encryption_algorithm") not in APPROVED_ALGORITHMS:
            return None
        out = res.copy()
        if variant == "clear":
            out.attrs["encryption_algorithm"] = "aws:kms"  # the value the reference fix restores
        return out

    def mutate(self, clean, variant):
        broken = clean.copy()
        broken.attrs["default_encryption"] = False
        if variant == "clear":
            broken.attrs.pop("encryption_algorithm")
            ops = [_set("default_encryption", True), _set("encryption_algorithm", "aws:kms")]
            paths = ["default_encryption", "encryption_algorithm"]
        else:
            ops, paths = [_set("default_encryption", True)], ["default_encryption"]
        return broken, self._mutation(variant, clean, broken, paths, ops)


class SseAlgo(Mutator):
    mutator_id = "m_s3_sse_algo"
    resource_types = ("AWSS3Bucket",)
    variants = {"none": 1.0, "aes128": 1.0, "kms_legacy": 1.0}
    rules = ("dpdp.rule6a",)
    writes = frozenset({"default_encryption", "encryption_algorithm"})
    _BAD = {"none": "NONE", "aes128": "AES128", "kms_legacy": "aws:kms:legacy"}

    def prepare(self, res, variant):
        if res.resource_type not in self.resource_types or res.attrs.get("default_encryption") is not True:
            return None
        if res.attrs.get("encryption_algorithm") not in APPROVED_ALGORITHMS:
            return None
        out = res.copy()
        out.attrs["encryption_algorithm"] = "aws:kms"
        return out

    def mutate(self, clean, variant):
        broken = clean.copy()
        broken.attrs["encryption_algorithm"] = self._BAD[variant]
        return broken, self._mutation(variant, clean, broken, ["encryption_algorithm"],
                                      [_set("encryption_algorithm", "aws:kms")])


class VersioningOff(Mutator):
    mutator_id = "m_s3_versioning_off"
    resource_types = ("AWSS3Bucket",)
    variants = {"suspended": 1.0, "missing": 1.0}
    rules = ("dpdp.rule6_versioning",)
    writes = frozenset({"versioning_status"})

    def prepare(self, res, variant):
        if res.resource_type not in self.resource_types:
            return None
        if res.attrs.get("personal_data") is not True or res.attrs.get("versioning_status") != "Enabled":
            return None
        return res.copy()

    def mutate(self, clean, variant):
        broken = clean.copy()
        if variant == "suspended":
            broken.attrs["versioning_status"] = "Suspended"
        else:
            broken.attrs.pop("versioning_status")
        return broken, self._mutation(variant, clean, broken, ["versioning_status"], [_set("versioning_status", "Enabled")])


class LifecycleOff(Mutator):
    mutator_id = "m_s3_lifecycle_off"
    resource_types = ("AWSS3Bucket",)
    variants = {"false": 1.0, "missing": 1.0}
    rules = ("dpdp.rule8_lifecycle",)
    writes = frozenset({"has_lifecycle_expiration"})

    def prepare(self, res, variant):
        if res.resource_type not in self.resource_types:
            return None
        if res.attrs.get("personal_data") is not True or res.attrs.get("has_lifecycle_expiration") is not True:
            return None
        return res.copy()

    def mutate(self, clean, variant):
        broken = clean.copy()
        if variant == "false":
            broken.attrs["has_lifecycle_expiration"] = False
        else:
            broken.attrs.pop("has_lifecycle_expiration")
        ops = [{"op": "set_lifecycle_rule", "attr": "has_lifecycle_expiration", "value": True}]
        return broken, self._mutation(variant, clean, broken, ["has_lifecycle_expiration"], ops)


class PublicBlockOff(Mutator):
    mutator_id = "m_s3_public_block_off"
    resource_types = ("AWSS3Bucket",)
    variants = {"one_acls": 1.0, "one_policy": 1.0, "one_ignore": 1.0, "one_restrict": 1.0, "all_off": 1.0, "missing": 1.0}
    rules = ("dpdp.rule6_public_exposure", "cis.s3_public_access_block")
    writes = frozenset(FLAGS)
    _WHICH = {"one_acls": FLAGS[:1], "one_policy": FLAGS[1:2], "one_ignore": FLAGS[2:3], "one_restrict": FLAGS[3:], "all_off": FLAGS, "missing": FLAGS}

    def prepare(self, res, variant):
        if res.resource_type not in self.resource_types or not all(res.attrs.get(f) is True for f in FLAGS):
            return None
        return res.copy()

    def mutate(self, clean, variant):
        broken = clean.copy()
        flags = self._WHICH[variant]
        for f in flags:
            if variant == "missing":
                broken.attrs.pop(f)
            else:
                broken.attrs[f] = False
        return broken, self._mutation(variant, clean, broken, list(flags), [_set(f, True) for f in flags])


class LoggingOff(Mutator):
    mutator_id = "m_s3_logging_off"
    resource_types = ("AWSS3Bucket",)
    variants = {"false": 1.0, "missing": 1.0}
    rules = ("dpdp.rule6_logging",)
    writes = frozenset({"logging_enabled"})

    def prepare(self, res, variant):
        if res.resource_type not in self.resource_types or res.attrs.get("logging_enabled") is not True:
            return None
        return res.copy()

    def mutate(self, clean, variant):
        broken = clean.copy()
        if variant == "false":
            broken.attrs["logging_enabled"] = False
        else:
            broken.attrs.pop("logging_enabled")
        return broken, self._mutation(variant, clean, broken, ["logging_enabled"], [_set("logging_enabled", True)])
