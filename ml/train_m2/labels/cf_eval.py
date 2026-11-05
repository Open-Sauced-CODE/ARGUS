"""Measure the reference-free counterfactual labeler against the reference oracle (Shaurya-owned).

Contract
--------
Agreement on reference patches alone says nothing (a labeler that calls everything correct scores 100%).
evaluate_cf scores the counterfactual labeler on a population of gate-passing candidates: the reference
patches (truth = correct) plus every gate-passing corruption (truth from the reference oracle). It reports,
for the STRICT rule (label == minimal_correct) and the LENIENT rule (label in {minimal_correct,
valid_not_minimal}), the confusion matrix, recall of wrong, precision of "wrong", and per corruption type.
Run it on the real train and val references; no held-out set is touched.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

ACC = {"minimal_correct", "valid_not_minimal"}


def _rates(c: Counter) -> dict[str, Any]:
    tp, fn, fp, tn = c[(True, True)], c[(True, False)], c[(False, True)], c[(False, False)]
    return {"correct_called_correct": tp, "correct_called_wrong": fn, "wrong_called_correct": fp,
            "wrong_called_wrong": tn, "recall_of_wrong": tn / (tn + fp) if tn + fp else None,
            "precision_of_wrong": tn / (tn + fn) if tn + fn else None,
            "false_wrong_rate_on_correct": fn / (tp + fn) if tp + fn else None}


def evaluate_cf(items: Iterable[tuple[str, Mapping[str, Any], Mapping[str, Any]]], seed: int = 1337) -> dict[str, Any]:
    """items: (input_key, record, reference) for fix-route inputs. Needs OPA on PATH (gate and CF use it)."""
    from ml.train_m2.labels import corruptor as cor
    from ml.train_m2.labels.counterfactual import CounterfactualOracle

    conf = {"strict": Counter(), "lenient": Counter()}
    by_type: dict[str, Counter] = defaultdict(Counter)
    for key, record, ref in items:
        cf = CounterfactualOracle(record["rule_id"]).classify(record, ref)
        conf["strict"][(True, cf.label == "minimal_correct")] += 1
        conf["lenient"][(True, cf.label in ACC)] += 1
        by_type["reference"][(True, cf.label)] += 1
        for row in cor.make_corrupted_rows(record, ref, "fix", key, seed=seed):
            if not row.get("gate_pass"):
                continue
            patch = cor.corrupt(record, ref, row["corruption_type"], seed=seed)
            if patch is None:
                continue
            truth = row["oracle_class"] in ACC
            cf = CounterfactualOracle(record["rule_id"]).classify(record, patch)
            conf["strict"][(truth, cf.label == "minimal_correct")] += 1
            conf["lenient"][(truth, cf.label in ACC)] += 1
            by_type[row["corruption_type"]][(truth, cf.label)] += 1
    return {"strict": _rates(conf["strict"]), "lenient": _rates(conf["lenient"]),
            "by_type": {t: {f"truth={k[0]},cf={k[1]}": v for k, v in sorted(c.items(), key=str)}
                        for t, c in sorted(by_type.items())}}
