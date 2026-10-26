"""
ARGUS Phase 4 - the privacy airlock.

    run_airlock(raw_finding, rule_id) -> (tokenized_scrubbed_record, privacy_receipt)

This is the ONLY way any generation tier (T0, T1, T2) may see a finding.
Pipeline, always in this order:
    1. project   - keep only the fields the triggering Rego rule reads (default-deny)
    2. tokenize  - real identifiers -> typed tokens, real values go to the encrypted vault
    3. scrub     - redact secrets / personal-data patterns (Presidio + secret scanner)
    4. leak-check- final hard-block backstop; raises AirlockBlocked on any finding

Control-plane-only IAM access (the "step zero" of the design) is enforced separately by
privacy/iam_guard.py.
"""

import hashlib
import json

from privacy.airlock.leakcheck import LeakDetected, leak_check
from privacy.airlock.projection import project
from privacy.scrubbers.scrubbers import scrub
from privacy.vault.tokenizer import tokenize
from privacy.vault.vault import get_default_vault


class AirlockBlocked(Exception):
    """The leak-check refused to release the payload. `.receipt` documents the block."""

    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt = receipt


def _sha256(record):
    blob = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def run_airlock(raw_finding, rule_id, *, vault=None, policy_dir=None):
    vault = vault or get_default_vault()

    projected = project(raw_finding, rule_id, policy_dir)
    tokenized, vault_refs = tokenize(projected, vault=vault)
    clean, scrub_result = scrub(tokenized)

    receipt = {
        "finding_id": clean["finding_id"],
        "rule_id": rule_id,
        "projected_fields": clean["fields"],
        "tokens": dict(vault_refs),
        "scrub_result": dict(scrub_result),
        "tier_used": None,  # set to "T0" | "T1" | "T2" by the Phase 7 pipeline
        "leaked_to_network": False,  # Phase 7 sets True only if T2 fires
        "record_sha256": _sha256(clean),
        "leak_check": None,
        "blocked": False,
    }

    try:
        receipt["leak_check"] = leak_check(clean, vault.values_for(vault_refs.values()))
    except LeakDetected as exc:
        receipt["leak_check"] = dict(exc.summary)
        receipt["blocked"] = True
        raise AirlockBlocked(str(exc), receipt) from exc

    return clean, receipt
