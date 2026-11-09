"""Single-row feature computation for M2 (Shaurya-owned). Pure, deterministic, no I/O, no label access.

compute_features(row, cohort, ctx) is the ONLY implementation; compute_matrix calls it. Phase 7 must call the same
function. Missing information is None (never a guess): U features are None without tokens; entropy and margin are None
without top-k. LEAKAGE RULE: this package never imports ml.train_m2.labels (checked by a test).

row     {"content": str|None, "tokens": list|None, "generator": str, "sample_idx": int}
cohort  every row of the same (generator, input) including `row`
ctx     {"rule_id": str, "route": "fix"|"escalate"}
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from functools import lru_cache
from typing import Any, Iterable, Mapping, Sequence

from ml.train_m2.features import registry as R

_OP_RE = re.compile(r'"op"\s*:\s*"([a-z_]+)"')
_VAL_RE = re.compile(r'"value"\s*:\s*("(?:[^"\\]|\\.)*"|true|false|null|-?\d+(?:\.\d+)?|\[[^\]]*\])')
_ATTR_OPS = {"set_attr", "enable_feature", "restrict_cidr", "set_lifecycle_rule"}


def canon(content: str | None) -> str:
    """Same meaning as labels.canon.canonical_answer (ops + rationale_ref), reimplemented to keep features label-free."""
    if not content or not str(content).strip():
        return "EMPTY"
    try:
        obj = json.loads(content)
    except (TypeError, ValueError):
        return "INVALID"
    if not isinstance(obj, dict):
        return "INVALID"
    return json.dumps({"ops": obj.get("ops"), "rationale_ref": obj.get("rationale_ref")}, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=True)


@lru_cache(maxsize=1)
def _declarations() -> dict[str, frozenset]:
    from privacy.airlock.projection import load_declarations
    return load_declarations()


def _spans(tokens: Sequence[Mapping[str, Any]]) -> list[tuple[int, int]]:
    out, pos = [], 0
    for t in tokens:
        n = len(str(t.get("t", "")))
        out.append((pos, pos + n))
        pos += n
    return out


def _lps_overlapping(tokens, spans, a: int, b: int) -> list[float]:
    return [float(t["lp"]) for t, (s, e) in zip(tokens, spans) if s < b and e > a]


def _uncertainty(row: Mapping[str, Any]) -> dict[str, float | None]:
    keys = ["lp_mean", "lp_min", "lp_p10", "lp_std", "seq_logprob", "lp_on_op_token", "lp_min_on_value_tokens",
            "entropy_mean", "top1_top2_margin_mean"]
    toks = row.get("tokens")
    if not toks:
        return {k: None for k in keys}
    lps = [float(t["lp"]) for t in toks]
    n = len(lps)
    mean = sum(lps) / n
    out: dict[str, float | None] = {
        "lp_mean": mean, "lp_min": min(lps), "lp_p10": float(sorted(lps)[max(0, int(math.floor(0.1 * (n - 1))))]),
        "lp_std": math.sqrt(sum((x - mean) ** 2 for x in lps) / n), "seq_logprob": sum(lps)}
    content = "".join(str(t.get("t", "")) for t in toks)
    spans = _spans(toks)
    op_lps = [lp for m in _OP_RE.finditer(content) for lp in _lps_overlapping(toks, spans, m.start(1), m.end(1))]
    val_lps = [lp for m in _VAL_RE.finditer(content) for lp in _lps_overlapping(toks, spans, m.start(1), m.end(1))]
    out["lp_on_op_token"] = sum(op_lps) / len(op_lps) if op_lps else None
    out["lp_min_on_value_tokens"] = min(val_lps) if val_lps else None
    ents, margins = [], []
    for t in toks:
        top = t.get("top") or []
        if len(top) >= 2:
            lp = [float(x[1]) for x in top]
            mx = max(lp)
            w = [math.exp(v - mx) for v in lp]
            z = sum(w)
            p = [x / z for x in w]
            ents.append(-sum(q * math.log(q) for q in p if q > 0))
            s = sorted(lp, reverse=True)
            margins.append(s[0] - s[1])
    out["entropy_mean"] = sum(ents) / len(ents) if ents else None
    out["top1_top2_margin_mean"] = sum(margins) / len(margins) if margins else None
    return out


def _consensus(row: Mapping[str, Any], cohort: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    keys = [canon(r.get("content")) for r in cohort]
    n = len(keys)
    mine = canon(row.get("content"))
    cnt = Counter(keys)
    valid = sum(1 for k in keys if k not in ("EMPTY", "INVALID"))
    modal_key, modal_n = cnt.most_common(1)[0]
    greedy = next((canon(r.get("content")) for r in cohort if r.get("sample_idx") == 0), None)
    ent = -sum((c / n) * math.log(c / n) for c in cnt.values())
    return {"agreement_rate": cnt[mine] / n, "n_distinct_patches": float(len(cnt)), "modal_share": modal_n / n,
            "greedy_is_modal": None if greedy is None else float(cnt[greedy] == modal_n),
            "cluster_entropy_norm": (ent / math.log(n)) if n > 1 else 0.0, "n_valid_over_n_requested": valid / n}


def _structure(row: Mapping[str, Any], rule_id: str) -> dict[str, float | None]:
    content = row.get("content") or ""
    out: dict[str, float | None] = {f"n_{o}": 0.0 for o in R.OP_TYPES}
    out.update({"n_ops": 0.0, "writes_only_rule_fields_frac": None, "patch_chars": float(len(content)),
                "uses_placeholder": float("INTERNAL_CIDR" in content)})
    try:
        obj = json.loads(content)
        ops = obj.get("ops") if isinstance(obj, dict) else None
    except (TypeError, ValueError):
        ops = None
    if not isinstance(ops, list):
        return out
    out["n_ops"] = float(len(ops))
    attr_ops = []
    for o in ops:
        if isinstance(o, dict):
            if o.get("op") in R.OP_TYPES:
                out[f"n_{o['op']}"] += 1.0
            if o.get("op") in _ATTR_OPS and o.get("attr") is not None:
                attr_ops.append(o["attr"])
    fields = _declarations().get(rule_id)
    if attr_ops and fields is not None:
        out["writes_only_rule_fields_frac"] = sum(a in fields for a in attr_ops) / len(attr_ops)
    return out


def _rule_gen(row: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, float | None]:
    rid = ctx.get("rule_id", "")
    fields = _declarations().get(rid)
    out: dict[str, float | None] = {
        "rule_is_dpdp": float(rid.startswith("dpdp.")),
        "rule_code": float(R.KNOWN_RULES.index(rid)) if rid in R.KNOWN_RULES else -1.0,
        "n_rule_fields": float(len(fields)) if fields is not None else None,
        "route_is_escalate": float(ctx.get("route") == "escalate")}
    for g in R.GENERATORS:
        out[f"gen_{g}"] = float(row.get("generator") == g)
    return out


def compute_features(row: Mapping[str, Any], cohort: Sequence[Mapping[str, Any]], ctx: Mapping[str, Any]) -> dict[str, Any]:
    feats: dict[str, Any] = {}
    feats.update(_uncertainty(row))
    feats.update(_consensus(row, cohort))
    feats.update(_structure(row, ctx.get("rule_id", "")))
    feats.update(_rule_gen(row, ctx))
    missing = [n for n in R.names() if n not in feats]
    if missing:
        raise KeyError(f"feature(s) not produced: {missing}")
    out = {n: feats[n] for n in R.names()}
    out["spec_hash"] = R.spec_hash()
    return out


def compute_matrix(items: Iterable[tuple[Mapping[str, Any], Sequence[Mapping[str, Any]], Mapping[str, Any]]]):
    """DataFrame (columns = R.names()) built by calling compute_features per row; NaN for None."""
    import pandas as pd
    rows = [compute_features(r, c, x) for r, c, x in items]
    return pd.DataFrame([{k: (float("nan") if v is None else v) for k, v in d.items() if k != "spec_hash"} for d in rows],
                        columns=R.names())
