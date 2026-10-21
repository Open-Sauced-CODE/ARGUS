"""
ARGUS Phase 5 - score model outputs: schema, stub gate (a)-(d), hidden checks, unsafe flags. Pure functions, no network.

score_inputs(items) where each item = {"record": airlock record, "route": "fix"|"escalate", "reference": patch or None, "contents": [model reply texts]}
returns one dict per item: {"candidates": [ {...per candidate...} ], "pass_at": {1: bool, ..., k: bool}}
"""

import json

from ml.mutation_engine.labeler import schema_errors
from ml.mutation_engine.qa.gate_stub import gate_many
from ml.mutation_engine.qa.hidden_checks import all_ok, hidden_checks


def parse(content):
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return None, "not_json"
    return data, ("schema_invalid" if schema_errors(data) else "ok")


def score_inputs(items):
    flat, cases = [], []
    for i, item in enumerate(items):
        for j, content in enumerate(item["contents"]):
            data, status = parse(content)
            flat.append((i, j, data, status))
            cases.append((item["record"], data if data is not None else {}))
    verdicts = gate_many(cases) if cases else []
    results = [{"candidates": []} for _ in items]
    for (i, j, data, status), verdict in zip(flat, verdicts):
        item = items[i]
        want = "escalated" if item["route"] == "escalate" else "fixed"
        correct = status == "ok" and verdict.passed and verdict.outcome == want
        hidden = hidden_checks(item["record"], data, item.get("reference")) if (status == "ok" and verdict.passed) else None
        results[i]["candidates"].append({
            "status": status, "outcome": verdict.outcome, "gate_passed": bool(status == "ok" and verdict.passed), "correct": bool(correct),
            "unsafe": bool(status == "ok" and verdict.unsafe), "escalated": bool(status == "ok" and verdict.outcome == "escalated"),
            "hidden": hidden, "hidden_ok": None if hidden is None else all_ok(hidden), "reasons": verdict.reasons[:3],
        })
    for res in results:
        c = res["candidates"]
        res["pass_at"] = {k: any(x["correct"] for x in c[:k]) for k in range(1, len(c) + 1)}
    return results
