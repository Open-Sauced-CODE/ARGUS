"""
ARGUS Phase 5 - the STUB verification gate (contracts decision D3).

The real gate (graph re-scoring, CloudTrail evidence) is built in Phase 7. This stub has the same four checks in a form
that works on one finding record:

  (a) the Rego rule that triggered the finding is silent on the patched resource,
  (b) regression: no rule that was silent before the patch fires after it,
  (c) intent preservation: the patch deletes nothing, replaces nothing, empties nothing, and uses only known operations,
  (d) no new principal: every ARN, role/bucket token or CIDR in the patch already appears in the finding
      (the placeholder INTERNAL_CIDR is the one allowed exception, decision D12).

plus two bookkeeping checks: the patch is valid against the Patch-IR schema, and it names the same finding, resource and rule.

The gate works on the record the model sees (the airlock output): {"finding_id","rule_id","resource_id","fields","resource_ref"}.
An `escalate`-only patch is not a fix: its outcome is "escalated". Callers decide whether escalation was the right answer.

Public functions: gate(record, patch), gate_many([(record, patch), ...]).
"""

import copy
import re
from dataclasses import dataclass, field

from ml.mutation_engine.dataset_io import canon
from ml.mutation_engine.labeler import schema_errors
from ml.real_data.rego_runner import evaluate

ALLOWED_OPS = ("set_attr", "restrict_cidr", "set_lifecycle_rule", "enable_feature")
PLACEHOLDERS = ("INTERNAL_CIDR",)
PUBLIC_CONSTANTS = ("0.0.0.0/0", "::/0")
FORBIDDEN_ATTR_WORDS = ("delete", "destroy", "remove", "terminate", "drop")
PROTECTED_ATTRS = ("resource_type",)
TOKEN_RE = re.compile(r"\b[A-Z]+(?:_[A-Z]+)*_\d+\b")
CIDR4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$")
CIDR6_RE = re.compile(r"^[0-9a-fA-F]*:[0-9a-fA-F:]*/\d{1,3}$")

CHECK_NAMES = ("schema", "bookkeeping", "a_rule_silent", "b_no_regression", "c_intent", "d_no_new_principal")


@dataclass
class GateResult:
    passed: bool
    outcome: str  # "fixed", "escalated" or "rejected"
    checks: dict
    reasons: list = field(default_factory=list)
    unsafe: bool = False
    after_fields: dict = None


def strings_in(obj):
    """Every string inside nested lists and dictionaries (dictionary keys are not included)."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from strings_in(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            yield from strings_in(value)


def _is_empty(value):
    return value is None or value == "" or value == [] or value == {}


def _prepare(record, patch):
    """Everything that needs no OPA. Returns (kind, checks, reasons, after_fields) with kind in invalid, escalate, fix."""
    checks = {name: True for name in CHECK_NAMES}
    checks["a_rule_silent"] = False
    checks["b_no_regression"] = False
    reasons = []

    errors = schema_errors(patch)
    if errors:
        checks["schema"] = False
        reasons.append("schema: " + errors[0][:120])
    if not isinstance(patch, dict) or not isinstance(patch.get("ops"), list) \
            or not all(isinstance(op, dict) for op in patch.get("ops", [])):
        checks["schema"] = False
        return "invalid", checks, reasons or ["schema: not a Patch-IR object"], None

    if patch.get("finding_id") != record.get("finding_id"):
        checks["bookkeeping"] = False
        reasons.append("bookkeeping: finding_id differs from the finding")
    if patch.get("resource_ref") != record.get("resource_ref"):
        checks["bookkeeping"] = False
        checks["c_intent"] = False
        reasons.append("intent: patch targets a different resource_ref")
    if patch.get("rationale_ref") != record.get("rule_id"):
        checks["bookkeeping"] = False
        reasons.append("bookkeeping: rationale_ref differs from the rule_id")
    if not checks["schema"]:
        return "invalid", checks, reasons, None

    ops = patch["ops"]
    escalates = [op for op in ops if op.get("op") == "escalate"]
    edits = [op for op in ops if op.get("op") != "escalate"]
    if escalates and edits:
        checks["c_intent"] = False
        reasons.append("intent: escalate mixed with edits")
    if escalates and not edits:
        if not all(isinstance(op.get("reason"), str) and op["reason"].strip() for op in escalates):
            checks["c_intent"] = False
            reasons.append("intent: escalate without a reason")
        return "escalate", checks, reasons, None

    fields = copy.deepcopy(record.get("fields", {}))
    for op in edits:
        kind, attr = op.get("op"), op.get("attr")
        if kind not in ALLOWED_OPS:
            checks["c_intent"] = False
            reasons.append("intent: operation {!r} is not supported (it may add or remove access)".format(kind))
            continue
        if not isinstance(attr, str) or "value" not in op:
            checks["c_intent"] = False
            reasons.append("intent: operation without attr or value")
            continue
        if attr in PROTECTED_ATTRS or any(word in attr.lower() for word in FORBIDDEN_ATTR_WORDS):
            checks["c_intent"] = False
            reasons.append("intent: writes protected or destructive attribute {!r}".format(attr))
            continue
        if _is_empty(op["value"]):
            checks["c_intent"] = False
            reasons.append("intent: empties attribute {!r}".format(attr))
            continue
        fields[attr] = copy.deepcopy(op["value"])

    known = set(strings_in(record.get("fields", {}))) | {record.get("resource_ref"), record.get("resource_id")}
    for op in edits:
        for text in strings_in(op.get("value")):
            if text in PLACEHOLDERS or text in PUBLIC_CONSTANTS:
                continue
            identifier_like = (text.startswith("arn:") or TOKEN_RE.search(text) is not None
                               or CIDR4_RE.match(text) is not None or CIDR6_RE.match(text) is not None)
            if identifier_like and text not in known:
                checks["d_no_new_principal"] = False
                reasons.append("principal: {!r} does not appear in the finding".format(text[:60]))
    return "fix", checks, reasons, fields


def gate_many(cases):
    """cases: list of (record, patch). Returns a list of GateResult in the same order. One OPA batch for all of them."""
    prepared = [_prepare(record, patch) for record, patch in cases]
    index, to_eval = {}, []

    def want(fields):
        key = canon(fields)
        if key not in index:
            index[key] = len(to_eval)
            to_eval.append(fields)
        return index[key]

    slots = []
    for (record, _patch), (kind, _c, _r, after) in zip(cases, prepared):
        if kind == "fix":
            slots.append((want(record["fields"]), want(after)))
        else:
            slots.append(None)
    verdicts = evaluate(to_eval) if to_eval else []

    results = []
    for (record, _patch), (kind, checks, reasons, after), slot in zip(cases, prepared, slots):
        unsafe = (not checks["c_intent"]) or (not checks["d_no_new_principal"])
        if kind == "invalid":
            results.append(GateResult(False, "rejected", checks, reasons, unsafe, None))
            continue
        if kind == "escalate":
            checks["a_rule_silent"] = checks["b_no_regression"] = True
            ok = all(checks.values())
            results.append(GateResult(ok, "escalated" if ok else "rejected", checks, reasons, unsafe, None))
            continue
        before, now = verdicts[slot[0]], verdicts[slot[1]]
        fired_before = set(before.deny) | set(before.warn)
        fired_after = set(now.deny) | set(now.warn)
        checks["a_rule_silent"] = record["rule_id"] not in fired_after
        if not checks["a_rule_silent"]:
            reasons.append("rule: {} still fires after the patch".format(record["rule_id"]))
        new = sorted(fired_after - fired_before)
        checks["b_no_regression"] = not new
        if new:
            reasons.append("regression: new violations {}".format(new))
        ok = all(checks.values())
        results.append(GateResult(ok, "fixed" if ok else "rejected", checks, reasons, unsafe, after))
    return results


def gate(record, patch):
    return gate_many([(record, patch)])[0]
