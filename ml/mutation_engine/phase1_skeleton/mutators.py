"""
ARGUS Phase 1 — Mutation Engine Skeleton

Each Mutator takes a known-good Terraform fixture (the "reference fix") and
introduces exactly one policy violation by flipping one unique, known line.
Because the injected value is unique in the file and the original value is
restored exactly on fix(), every mutator doubles as its own round-trip test:

    fix(mutate(good_config)) == good_config

This mirrors how the DPDP / CIS Rego rules (Phase 4) will check the same
resource: one rule, one attribute, one violation.
"""

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class Mutator:
    def __init__(self, mutator_id, rule_id, description, fixture_filename,
                 good_value, bad_value):
        self.mutator_id = mutator_id
        self.rule_id = rule_id
        self.description = description
        self.fixture_filename = fixture_filename
        self.good_value = good_value
        self.bad_value = bad_value

    def load_good_config(self):
        path = FIXTURES_DIR / self.fixture_filename
        content = path.read_text(encoding="utf-8")
        occurrences = content.count(self.good_value)
        if occurrences != 1:
            raise ValueError(
                "[{}] expected exactly 1 occurrence of {!r} in {}, found {}".format(
                    self.mutator_id, self.good_value, self.fixture_filename, occurrences
                )
            )
        return content

    def mutate(self, good_config=None):
        """Break the config the way `rule_id` checks for."""
        if good_config is None:
            good_config = self.load_good_config()
        if self.good_value not in good_config:
            raise ValueError(
                "[{}] good_value not found — config is already mutated or "
                "does not match this mutator's fixture.".format(self.mutator_id)
            )
        return good_config.replace(self.good_value, self.bad_value, 1)

    def fix(self, mutated_config):
        """The reference fix: reverses the mutation exactly."""
        if self.bad_value not in mutated_config:
            raise ValueError(
                "[{}] bad_value not found — config is not in the mutated "
                "state this mutator produces.".format(self.mutator_id)
            )
        return mutated_config.replace(self.bad_value, self.good_value, 1)


MUTATORS = [
    Mutator(
        mutator_id="s3_disable_encryption",
        rule_id="dpdp.rule6a",
        description="Removes default server-side (KMS) encryption from an S3 bucket.",
        fixture_filename="s3_bucket_good.tf",
        good_value='sse_algorithm = "aws:kms"',
        bad_value='sse_algorithm = "NONE"',
    ),
    Mutator(
        mutator_id="s3_disable_versioning",
        rule_id="dpdp.rule6_versioning",
        description="Suspends versioning on an S3 bucket (removes a recovery control).",
        fixture_filename="s3_bucket_good.tf",
        good_value='status = "Enabled"',
        bad_value='status = "Suspended"',
    ),
    Mutator(
        mutator_id="s3_disable_public_access_block",
        rule_id="cis.s3_public_access_block",
        description="Turns off the S3 bucket-level public-ACL block.",
        fixture_filename="s3_bucket_good.tf",
        good_value="block_public_acls = true",
        bad_value="block_public_acls = false",
    ),
    Mutator(
        mutator_id="sg_open_ingress",
        rule_id="cis.sg_open_ingress",
        description="Widens a security group's ingress rule from a private CIDR to 0.0.0.0/0.",
        fixture_filename="security_group_good.tf",
        good_value='cidr_blocks = ["10.0.0.0/16"] # ingress restricted to internal network',
        bad_value='cidr_blocks = ["0.0.0.0/0"] # ingress restricted to internal network',
    ),
]


def get_mutator(mutator_id):
    for m in MUTATORS:
        if m.mutator_id == mutator_id:
            return m
    raise KeyError("No mutator registered with id {!r}".format(mutator_id))
