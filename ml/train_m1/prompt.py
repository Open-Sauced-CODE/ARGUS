"""
ARGUS Phase 5, Step 14 - the ONE fixed prompt format used for training, evaluation and serving. Never change it after training starts.
"""

import json
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "remediate" / "patch_ir" / "schema.json"

SYSTEM_PROMPT = (
    "You repair cloud misconfigurations. Reply with exactly one Patch-IR JSON object and nothing else. "
    "Allowed operations: set_attr, add_policy_statement, remove_policy_statement, restrict_cidr, enable_feature, set_lifecycle_rule, escalate. "
    "Copy finding_id and resource_ref from the finding. Set rationale_ref to the finding's rule_id. "
    "Change only the fields needed to fix the finding. Never delete a resource and never add an identifier that is not in the finding. "
    "Encryption fixes use aws:kms. A security group open to the world is narrowed with restrict_cidr to INTERNAL_CIDR. "
    "If the fix cannot be expressed with these operations, use the operation escalate and give a reason."
)


def load_schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8-sig"))


def _ordered(obj, schema):
    """Keys in the order the schema file lists them, so training text matches the order constrained decoding forces."""
    if isinstance(obj, dict) and isinstance(schema, dict) and "properties" in schema:
        order = list(schema["properties"])
        keys = [k for k in order if k in obj] + sorted(k for k in obj if k not in order)
        return {k: _ordered(obj[k], schema["properties"].get(k, {})) for k in keys}
    if isinstance(obj, list) and isinstance(schema, dict) and "items" in schema:
        return [_ordered(x, schema["items"]) for x in obj]
    return obj


def patch_json(patch):
    return json.dumps(_ordered(patch, load_schema()), separators=(",", ":"), ensure_ascii=True)


def user_message(record):
    return "Finding:\n" + json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def chat_messages(record, patch=None):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_message(record)}]
    if patch is not None:
        msgs.append({"role": "assistant", "content": patch_json(patch)})
    return msgs
