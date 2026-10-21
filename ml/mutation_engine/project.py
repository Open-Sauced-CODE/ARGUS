"""
ARGUS Phase 5, Step 7 - thin wrapper over the Phase 4 airlock.

The model input of every example is EXACTLY what privacy.airlock.airlock.run_airlock returns for the raw finding.
Nothing here re-implements projection, tokenization, scrubbing or the leak-check.

The reference patch must speak the same token language as the input (BUCKET_1 ...). Its values are therefore
tokenized together with the projected fields, in one session, so that a token in the patch is the same token that
the input shows. A guard checks that the shared session really reproduced the airlock's own tokens.
"""

import tempfile
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet

from privacy.airlock.airlock import run_airlock
from privacy.airlock.projection import project
from privacy.scrubbers.scrubbers import scrub
from privacy.vault.tokenizer import tokenize
from privacy.vault.vault import TokenVault


@contextmanager
def throwaway_vault():
    """A temporary encrypted vault with a fresh key. The real privacy/vault/vault.db is never touched."""
    with tempfile.TemporaryDirectory() as tmp:
        yield TokenVault(db_path=Path(tmp) / "dataset_vault.db", key=Fernet.generate_key())


def raw_finding(res, finding_id, resource_id):
    attributes = dict(res.extras)
    attributes.update(res.attrs)
    return {"finding_id": finding_id, "resource_id": resource_id, "resource_type": res.resource_type, "attributes": attributes}


def model_input(raw, rule_id, vault):
    """(record, receipt) from the deployed airlock."""
    return run_airlock(raw, rule_id, vault=vault)


def tokenize_ops(raw, rule_id, record, ops, vault):
    """The reference operations written in the same tokens as `record`."""
    joint, _refs = tokenize(dict(project(raw, rule_id), target_ops=ops), vault=vault)
    joint, _ = scrub(joint)
    if joint["fields"] != record["fields"] or joint["resource_ref"] != record["resource_ref"]:
        raise ValueError("token mismatch between the model input and its reference patch")
    return joint["target_ops"]
