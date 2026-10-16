"""
ARGUS Phase 5, Step 4 - repository buckets.

Every repository goes to exactly one bucket, decided only by its name:
    hash(full name) mod 100:  0-69 train, 70-79 validation, 80-99 test
Repositories that belong to the Phase 10 testbed (CloudGoat, TerraGoat) are "reserved": they never
feed train or validation, and they are not used for Tier C either.
"""

import hashlib

TRAIN_MAX = 69
VAL_MAX = 79
RESERVED_SUBSTRINGS = ("cloudgoat", "terragoat")


def bucket_number(full_name):
    digest = hashlib.sha256(full_name.strip().lower().encode("utf-8")).hexdigest()
    return int(digest, 16) % 100


def bucket_of(full_name, reserved_substrings=RESERVED_SUBSTRINGS):
    lowered = full_name.strip().lower()
    if any(s in lowered for s in reserved_substrings):
        return "reserved"
    n = bucket_number(full_name)
    if n <= TRAIN_MAX:
        return "train"
    if n <= VAL_MAX:
        return "val"
    return "test"
