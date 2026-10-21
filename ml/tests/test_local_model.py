"""Tests for remediate/local_model (Ollama is faked, nothing is sent anywhere).

    python -m pytest ml/tests/test_local_model.py -v
"""

import json

import remediate.local_model as lm

GOOD = {"finding_id": "F-0", "resource_ref": "BUCKET_1", "rationale_ref": "dpdp.rule6_logging",
        "ops": [{"op": "set_attr", "attr": "logging_enabled", "value": True}]}
FINDING = {"finding_id": "F-0", "rule_id": "dpdp.rule6_logging", "resource_id": "BUCKET_1", "resource_ref": "BUCKET_1", "fields": {}}


def test_generate_keeps_only_valid_candidates_and_stats(monkeypatch):
    replies = [json.dumps(GOOD), "not json", json.dumps({"finding_id": "x"}), json.dumps(GOOD)]
    calls = {"n": 0}

    def fake(model, record, temperature=0.0, seed=0, **kw):
        text = replies[calls["n"] % len(replies)]
        calls["n"] += 1
        return {"content": text, "seconds": 0.1, "logprobs": [{"token": "a", "logprob": -0.1}, {"token": "b", "logprob": -0.3}], "error": None}

    monkeypatch.setattr(lm, "chat_once", fake)
    assert lm.generate(FINDING, n=4, model="m") == [GOOD, GOOD]
    cands, stats = lm.generate_with_stats(FINDING, n=4, model="m")
    assert len(cands) == 2 and stats["n_valid"] == 2 and stats["agreement_rate"] == 1.0
    assert abs(stats["logprob_mean"] + 0.2) < 1e-9 and stats["logprob_min"] == -0.3
