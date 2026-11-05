"""Single-feature shortcut diagnostic per corruption type (Shaurya-owned).

Contract
--------
auc(pos, neg) is the Mann-Whitney AUC with ties counted 0.5. separability() reports, per corruption type and
per feature (n_ops, patch_json_len), max(AUC, 1 - AUC) of that type's hard negatives against natural
minimal_correct candidates. A value above THRESHOLD means the type is trivially separable.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence

THRESHOLD = 0.95


def auc(pos: Sequence[float], neg: Sequence[float]) -> float:
    if not pos or not neg:
        return float("nan")
    allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    ranks: dict[int, float] = {}
    i = 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for t in range(i, j + 1):
            ranks[t] = avg
        i = j + 1
    r_pos = sum(ranks[t] for t, (_, lab) in enumerate(allv) if lab == 1)
    n_p, n_n = len(pos), len(neg)
    return (r_pos - n_p * (n_p + 1) / 2.0) / (n_p * n_n)


def features(row: Mapping[str, Any]) -> dict[str, float]:
    p = row.get("patch")
    ops = p.get("ops", []) if isinstance(p, dict) else []
    return {"n_ops": float(len(ops)), "patch_json_len": float(len(json.dumps(p, sort_keys=True)))}


def separability(corruptor_rows: Iterable[Mapping[str, Any]], natural_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    nat = [features(r) for r in natural_rows]
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in corruptor_rows:
        by_type[str(r.get("corruption_type"))].append(features(r))
    out: dict[str, Any] = {}
    for t, rows in sorted(by_type.items()):
        res: dict[str, Any] = {"n": len(rows)}
        for f in ("n_ops", "patch_json_len"):
            a = auc([x[f] for x in rows], [x[f] for x in nat])
            res[f] = max(a, 1 - a) if a == a else float("nan")
        res["trivially_separable"] = any(res[f] > THRESHOLD for f in ("n_ops", "patch_json_len"))
        out[t] = res
    return out
