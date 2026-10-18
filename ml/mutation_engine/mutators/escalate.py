"""Mutators whose correct answer is `escalate` (the fix is outside the Patch-IR vocabulary)."""

from ml.mutation_engine.mutators.base import Mutator

APPROVED_REGIONS = ["ap-south-1", "ap-south-2"]


class RdsUnencrypted(Mutator):
    mutator_id = "m_rds_unencrypted"
    resource_types = ("AWSRDSInstance",)
    variants = {"false": 1.0, "missing": 1.0}
    rules = ("dpdp.rule6a_rds",)
    writes = frozenset({"storage_encrypted"})
    route = "escalate"
    reason = "An existing RDS instance cannot be encrypted in place; it needs a snapshot copy and restore, which Patch-IR cannot express."

    def prepare(self, res, variant):
        if res.resource_type not in self.resource_types or res.attrs.get("storage_encrypted") is not True:
            return None
        return res.copy()

    def mutate(self, clean, variant):
        broken = clean.copy()
        if variant == "false":
            broken.attrs["storage_encrypted"] = False
        else:
            broken.attrs.pop("storage_encrypted")
        return broken, self._mutation(variant, clean, broken, ["storage_encrypted"], self._escalate_ops())


class AccountMfaOff(Mutator):
    mutator_id = "m_account_mfa_off"
    resource_types = ("AWSAccount",)
    variants = {"false": 1.0, "missing": 1.0}
    rules = ("dpdp.rule6_account_mfa",)
    writes = frozenset({"account_mfa_enabled"})
    route = "escalate"
    reason = "Enabling account-level MFA is a human action and cannot be expressed as a Terraform change."

    def prepare(self, res, variant):
        if res.resource_type not in self.resource_types or res.attrs.get("account_mfa_enabled") is not True:
            return None
        return res.copy()

    def mutate(self, clean, variant):
        broken = clean.copy()
        if variant == "false":
            broken.attrs["account_mfa_enabled"] = False
        else:
            broken.attrs.pop("account_mfa_enabled")
        return broken, self._mutation(variant, clean, broken, ["account_mfa_enabled"], self._escalate_ops())


class AccountDetectionOff(Mutator):
    mutator_id = "m_account_detection_off"
    resource_types = ("AWSAccount",)
    variants = {"cloudtrail_off": 1.0, "guardduty_off": 1.0, "both_off": 1.0}
    rules = ("dpdp.rule7_detection",)
    writes = frozenset({"cloudtrail_enabled", "guardduty_enabled"})
    route = "escalate"
    reason = "CloudTrail and GuardDuty would be new resources, which Patch-IR cannot create."
    _OFF = {"cloudtrail_off": ("cloudtrail_enabled",), "guardduty_off": ("guardduty_enabled",),
            "both_off": ("cloudtrail_enabled", "guardduty_enabled")}

    def prepare(self, res, variant):
        if res.resource_type not in self.resource_types:
            return None
        if res.attrs.get("cloudtrail_enabled") is not True or res.attrs.get("guardduty_enabled") is not True:
            return None
        return res.copy()

    def mutate(self, clean, variant):
        broken = clean.copy()
        for flag in self._OFF[variant]:
            broken.attrs[flag] = False
        return broken, self._mutation(variant, clean, broken, list(self._OFF[variant]), self._escalate_ops())


class RegionOutsideApproved(Mutator):
    mutator_id = "m_region_outside_approved"
    resource_types = ("AWSRDSInstance",)
    variants = {"us_east_1": 1.0, "eu_west_1": 1.0, "us_west_2": 1.0}
    rules = ("dpdp.rule15_region",)
    writes = frozenset({"personal_data", "region", "approved_regions"})
    route = "escalate"
    reason = "Moving personal data to another region is a data migration, which Patch-IR cannot express."
    _REGION = {"us_east_1": "us-east-1", "eu_west_1": "eu-west-1", "us_west_2": "us-west-2"}

    def prepare(self, res, variant):
        if res.resource_type not in self.resource_types:
            return None
        if any(k in res.attrs for k in self.writes):
            return None
        return res.copy()

    def mutate(self, clean, variant):
        broken = clean.copy()
        broken.attrs["personal_data"] = True
        broken.attrs["region"] = self._REGION[variant]
        broken.attrs["approved_regions"] = list(APPROVED_REGIONS)
        return broken, self._mutation(variant, clean, broken, ["personal_data", "region", "approved_regions"], self._escalate_ops())
