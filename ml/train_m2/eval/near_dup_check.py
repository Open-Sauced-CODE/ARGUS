"""Read-only near-duplicate check between clean OOF clusters and fold training sets (Shaurya-owned).

For each clean OOF cluster in fold f:
  - Normalizes its input record (tokens with identifiers/numbers replaced by placeholders, same rule_id)
  - Compares against every cluster in the TRAINING part of fold f (all other folds)
  - Reports counts ONLY (never raw input content):
      * clusters with identical normalized signature in training
      * distribution of max Jaccard similarity on token shingles (binned)
      * OOF pass rate breakdown for clusters with vs without a near-duplicate in training
      * if any near-duplicate rate > 20%, prints the warning banner and remaining cluster count.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import re
import sys
from typing import AbstractSet, Any, Mapping, Sequence

# Ensure repository root is on sys.path when invoked directly as a script
_repo_root = str(Path(__file__).resolve().parents[3])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from ml.train_m2.common import jsonl_write_atomic, load_inputs, repo_root, write_provenance
from ml.train_m2.eval.ingest_oof import _build_fold_membership, _build_key_flags, _load_folds

LOG = logging.getLogger("near_dup_check")
SEED = 1337

_ARN_RE = re.compile(r"^arn:[^\s]+$", re.IGNORECASE)
_CIDR_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?$")
_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_PLACEHOLDER_RE = re.compile(r"^(?:RESOURCE|ACCOUNT|ROLE|USER|BUCKET|KEY|VPC|SUBNET|SG)_\d+$", re.IGNORECASE)
_HEX_RE = re.compile(r"^[0-9a-f]{12,}$", re.IGNORECASE)
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)

SIMILARITY_BINS: tuple[tuple[str, float, float], ...] = (
    ("[0.0, 0.2)", 0.0, 0.2),
    ("[0.2, 0.4)", 0.2, 0.4),
    ("[0.4, 0.6)", 0.4, 0.6),
    ("[0.6, 0.8)", 0.6, 0.8),
    ("[0.8, 1.0)", 0.8, 1.0),
    ("1.0", 1.0, 1.01),
)


def _normalize_scalar_token(val: Any) -> list[str]:
    """Normalize a single scalar value into placeholder-aware tokens."""
    if val is None:
        return ["<NULL>"]
    if isinstance(val, bool):
        return ["<TRUE>" if val else "<FALSE>"]
    if isinstance(val, (int, float)):
        return ["<NUM>"]

    s = str(val).strip()
    if not s:
        return ["<EMPTY>"]
    if _ARN_RE.match(s):
        return ["<ARN>"]
    if _CIDR_RE.match(s):
        # Preserve wildcard 0.0.0.0/0 as structural risk pattern; other CIDRs become <CIDR>
        if s == "0.0.0.0/0":
            return ["0.0.0.0/0"]
        return ["<CIDR>"]
    if _NUM_RE.match(s):
        return ["<NUM>"]
    if _PLACEHOLDER_RE.match(s):
        return ["<ID>"]
    if _UUID_RE.match(s) or _HEX_RE.match(s):
        return ["<ID>"]
    if s == "*":
        return ["*"]

    # Split compound strings (e.g. ec2:DescribeInstances, table/my-bucket-123)
    parts = [p for p in re.split(r"[\s,/.\[\]{}()\"'=]+", s) if p]
    out: list[str] = []
    for p in parts:
        if _NUM_RE.match(p):
            out.append("<NUM>")
        elif _PLACEHOLDER_RE.match(p) or _UUID_RE.match(p) or _HEX_RE.match(p):
            out.append("<ID>")
        else:
            out.append(p.lower())
    return out or ["<EMPTY>"]


def _flatten_fields(obj: Any, prefix: str = "") -> list[str]:
    """Deterministically extract normalized tokens from nested dict/list fields."""
    tokens: list[str] = []
    if isinstance(obj, Mapping):
        for k in sorted(obj.keys()):
            # Skip instance-identifying keys while preserving policy/schema attributes
            kl = str(k).lower()
            if kl in {"finding_id", "resource_id", "resource_ref", "account_id"}:
                tokens.append(f"k:{kl}=<ID>")
                continue
            tokens.append(f"k:{kl}")
            tokens.extend(_flatten_fields(obj[k], prefix=kl))
    elif isinstance(obj, (list, tuple)):
        # Sort normalized elements for order-insensitive comparison (e.g. action lists)
        sub_tokens = [tuple(_flatten_fields(item, prefix=prefix)) for item in obj]
        for st in sorted(sub_tokens):
            tokens.extend(st)
    else:
        tokens.extend(_normalize_scalar_token(obj))
    return tokens


def normalize_input_tokens(record: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    """Return (rule_id, normalized_tokens) replacing identifiers/numbers with placeholders."""
    rule_id = str(record.get("rule_id") or "")
    fields = record.get("fields") or {}
    tokens = tuple(_flatten_fields(fields))
    return rule_id, tokens


def normalized_signature(record: Mapping[str, Any]) -> tuple[str, str]:
    """Return (rule_id, sha256_hex_of_normalized_tokens). Never exposes raw content."""
    rule_id, toks = normalize_input_tokens(record)
    payload = json.dumps({"rule_id": rule_id, "tokens": list(toks)}, separators=(",", ":"))
    sig = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return rule_id, sig


def token_shingles(tokens: Sequence[str], k: int = 3) -> frozenset[tuple[str, ...]]:
    """Construct token k-shingles (falling back to min(k, len(tokens))-grams for short sequences)."""
    n = len(tokens)
    if n == 0:
        return frozenset()
    eff_k = min(k, n)
    return frozenset(tuple(tokens[i:i + eff_k]) for i in range(n - eff_k + 1))


def jaccard_similarity(a: AbstractSet[Any], b: AbstractSet[Any]) -> float:
    """Compute Jaccard similarity |A & B| / |A | B|."""
    if not a and not b:
        return 1.0
    union = len(a | b)
    if union == 0:
        return 0.0
    return len(a & b) / union


def _bin_label(sim: float) -> str:
    if sim >= 1.0 - 1e-12:
        return "1.0"
    for label, lo, hi in SIMILARITY_BINS:
        if lo <= sim < hi:
            return label
    return "[0.0, 0.2)"


def analyze_near_duplicates(
    folds_data: Mapping[str, Any],
    records_by_key: Mapping[str, Mapping[str, Any]],
    key_flags: Mapping[str, Mapping[str, bool]],
    *,
    clean_labels: Mapping[str, Mapping[str, Any]] | None = None,
    folds_subset: Sequence[int] | None = None,
    threshold: float = 0.80,
    k_shingle: int = 3,
) -> dict[str, Any]:
    """Compare each clean OOF cluster against all training clusters (all other folds) of same rule_id.

    Returns counts-only summary dictionary (zero input text).
    """
    folds_map = folds_data.get("folds", {})
    all_fold_ids = sorted(int(f) for f in folds_map.keys())
    target_folds = sorted(folds_subset) if folds_subset is not None else all_fold_ids

    # Precompute normalized signatures & shingles for all fold keys
    norm_sigs: dict[str, tuple[str, str]] = {}
    norm_shingles: dict[str, frozenset[tuple[str, ...]]] = {}
    for f in all_fold_ids:
        for ik in folds_map[str(f)]["input_keys"]:
            if ik not in norm_sigs and ik in records_by_key:
                rec = records_by_key[ik]
                rule_id, toks = normalize_input_tokens(rec)
                norm_sigs[ik] = normalized_signature(rec)
                norm_shingles[ik] = token_shingles(toks, k=k_shingle)

    bin_counts = {label: 0 for label, _, _ in SIMILARITY_BINS}
    per_fold_stats: list[dict[str, Any]] = []

    total_clean = 0
    total_exact_norm = 0
    total_near_dup = 0

    pass_with_nd = {"total": 0, "gate_pass": 0, "gate_fail": 0, "minimal_correct": 0, "wrong_k": 0}
    pass_without_nd = {"total": 0, "gate_pass": 0, "gate_fail": 0, "minimal_correct": 0, "wrong_k": 0}

    for f in target_folds:
        f_keys = list(folds_map.get(str(f), {}).get("input_keys", []))
        # Clean OOF clusters: not held-out and not A_val
        clean_keys = [
            ik for ik in f_keys
            if not key_flags.get(ik, {}).get("in_heldout", False)
            and not key_flags.get(ik, {}).get("in_a_val", False)
        ]

        # Training part of fold f = all clusters from all other folds
        train_keys = [
            ik for g in all_fold_ids if g != f
            for ik in folds_map.get(str(g), {}).get("input_keys", [])
        ]

        f_exact = 0
        f_near = 0
        for ik in clean_keys:
            if ik not in norm_sigs:
                continue
            c_rule, c_sig = norm_sigs[ik]
            c_shing = norm_shingles[ik]

            same_rule_train = [tk for tk in train_keys if tk in norm_sigs and norm_sigs[tk][0] == c_rule]
            exact_match = any(norm_sigs[tk][1] == c_sig for tk in same_rule_train)
            max_sim = max(
                (jaccard_similarity(c_shing, norm_shingles[tk]) for tk in same_rule_train),
                default=0.0,
            )

            bin_counts[_bin_label(max_sim)] += 1
            is_nd = exact_match or (max_sim >= threshold)
            if exact_match:
                f_exact += 1
            if is_nd:
                f_near += 1

            # OOF pass rate breakdown if label is available
            if clean_labels and ik in clean_labels:
                lbl = clean_labels[ik]
                bucket = pass_with_nd if is_nd else pass_without_nd
                bucket["total"] += 1
                if lbl.get("gate_pass"):
                    bucket["gate_pass"] += 1
                else:
                    bucket["gate_fail"] += 1
                if lbl.get("oracle_class") == "minimal_correct":
                    bucket["minimal_correct"] += 1
                elif lbl.get("gate_pass") and lbl.get("oracle_class") in ("wrong", "valid_not_minimal", "fixed_should_escalate"):
                    bucket["wrong_k"] += 1

        n_c = len(clean_keys)
        total_clean += n_c
        total_exact_norm += f_exact
        total_near_dup += f_near
        per_fold_stats.append({
            "fold": f,
            "clean_clusters": n_c,
            "exact_norm_matches": f_exact,
            "near_dup_count": f_near,
            "near_dup_rate": (f_near / n_c) if n_c else 0.0,
            "remaining_independent": n_c - f_near,
        })

    exact_rate = (total_exact_norm / total_clean) if total_clean else 0.0
    near_dup_rate = (total_near_dup / total_clean) if total_clean else 0.0
    any_fold_over_20 = any(r["near_dup_rate"] > 0.20 for r in per_fold_stats)
    alert_triggered = (exact_rate > 0.20) or (near_dup_rate > 0.20) or any_fold_over_20
    remaining_after_removal = total_clean - total_near_dup

    def _rates(d: dict[str, int]) -> dict[str, Any]:
        tot = d["total"]
        return {
            **d,
            "gate_pass_rate": (d["gate_pass"] / tot) if tot else None,
            "strict_correct_rate": (d["minimal_correct"] / tot) if tot else None,
        }

    nd_rate_out = _rates(pass_with_nd)
    non_nd_rate_out = _rates(pass_without_nd)
    pass_rate_diff = None
    if nd_rate_out["gate_pass_rate"] is not None and non_nd_rate_out["gate_pass_rate"] is not None:
        pass_rate_diff = nd_rate_out["gate_pass_rate"] - non_nd_rate_out["gate_pass_rate"]

    return {
        "folds_analyzed": target_folds,
        "similarity_threshold": threshold,
        "shingle_k": k_shingle,
        "total_clean_clusters": total_clean,
        "identical_norm_signature_count": total_exact_norm,
        "identical_norm_signature_rate": exact_rate,
        "near_duplicate_count": total_near_dup,
        "near_duplicate_rate": near_dup_rate,
        "remaining_after_removal": remaining_after_removal,
        "alert_triggered": alert_triggered,
        "alert_message": (
            "OOF clusters are not independent of training; clean counts overstate unseen clusters"
            if alert_triggered
            else None
        ),
        "max_similarity_bins": bin_counts,
        "per_fold": per_fold_stats,
        "oof_pass_comparison": {
            "with_near_dup": nd_rate_out,
            "without_near_dup": non_nd_rate_out,
            "gate_pass_rate_diff": pass_rate_diff,
        },
    }


def render_near_dup_report(summary: Mapping[str, Any]) -> str:
    """Render counts-only near-duplicate markdown report (zero input content)."""
    lines = [
        "# Near-Duplicate Check: Clean OOF Clusters vs Fold Training Sets",
        "",
        f"- Folds analyzed: {summary['folds_analyzed']}",
        f"- Clean OOF clusters analyzed: **{summary['total_clean_clusters']}**",
        f"- Identical normalized signature in training: **{summary['identical_norm_signature_count']}** ({summary['identical_norm_signature_rate']:.1%})",
        f"- Near-duplicates (identical normalized sig OR Jaccard >= {summary['similarity_threshold']:.2f}): **{summary['near_duplicate_count']}** ({summary['near_duplicate_rate']:.1%})",
        f"- Remaining clean clusters after removing near-duplicates: **{summary['remaining_after_removal']}**",
        "",
    ]
    if summary["alert_triggered"]:
        lines.extend([
            f"> **WARNING:** {summary['alert_message']}",
            f"> Remaining independent clean clusters after removal: **{summary['remaining_after_removal']}** / {summary['total_clean_clusters']}",
            "",
        ])

    lines.extend([
        "## Per-Fold Breakdown (Counts Only)",
        "",
        "| Fold | Clean Clusters | Identical Norm Sig | Near-Dups (Exact or >= thr) | Near-Dup Rate | Remaining |",
        "|---|---|---|---|---|---|",
    ])
    for r in summary["per_fold"]:
        lines.append(
            f"| {r['fold']} | {r['clean_clusters']} | {r['exact_norm_matches']} | "
            f"{r['near_dup_count']} | {r['near_dup_rate']:.1%} | {r['remaining_independent']} |"
        )

    lines.extend([
        "",
        "## Max Jaccard Similarity Distribution (Token Shingles, Same Rule)",
        "",
        "| Similarity Bin | Cluster Count |",
        "|---|---|",
    ])
    for b_label, cnt in summary["max_similarity_bins"].items():
        lines.append(f"| {b_label} | {cnt} |")

    comp = summary["oof_pass_comparison"]
    w_nd = comp["with_near_dup"]
    wo_nd = comp["without_near_dup"]
    lines.extend([
        "",
        "## OOF Gate Pass Rate Comparison (Counts Only)",
        "",
        "| Subset | Clusters | Gate-Pass | Gate-Fail | Minimal Correct | Wrong (k) | Gate-Pass Rate |",
        "|---|---|---|---|---|---|---|",
    ])
    for name, d in (("With Near-Duplicate", w_nd), ("Without Near-Duplicate", wo_nd)):
        rate_s = f"{d['gate_pass_rate']:.1%}" if d["gate_pass_rate"] is not None else "n/a (no labels)"
        lines.append(
            f"| {name} | {d['total']} | {d['gate_pass']} | {d['gate_fail']} | "
            f"{d['minimal_correct']} | {d['wrong_k']} | {rate_s} |"
        )
    if comp["gate_pass_rate_diff"] is not None:
        lines.append(f"\n- Gate-pass rate difference (with - without): {comp['gate_pass_rate_diff']:+.1%}")

    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    p = argparse.ArgumentParser(description="Read-only near-duplicate check for clean OOF clusters")
    p.add_argument("--folds", default="docs/phase6_shaurya/crossfit/folds.json", help="Path to folds.json")
    p.add_argument("--preds-dir", default=None, help="Optional dir with fold*_preds.jsonl for pass rate comparison")
    p.add_argument("--threshold", type=float, default=0.80, help="Jaccard near-duplicate threshold (default: 0.80)")
    p.add_argument("--shingle-k", type=int, default=3, help="Token shingle length k (default: 3)")
    p.add_argument("--out-dir", default="ml/train_m2/out/reports", help="Output report directory")
    p.add_argument("--seed", type=int, default=SEED, help="Seed (default 1337)")
    args = p.parse_args(argv)

    root = repo_root()
    folds_path = Path(args.folds)
    if not folds_path.is_absolute():
        folds_path = root / folds_path
    folds_data = _load_folds(folds_path)

    inputs = load_inputs()
    records_by_key = {r["input_key"]: r["record"] for r in inputs}
    key_flags = _build_key_flags(inputs)
    fold_membership = _build_fold_membership(folds_data)

    # Optionally check OOF greedy predictions if available for pass-rate comparison
    clean_labels: dict[str, dict[str, Any]] | None = None
    folds_subset: list[int] | None = None
    from ml.train_m2.eval.label_oof_greedy import (
        label_clean_oof_greedy,
        load_train_reference_map,
        resolve_preds_files,
        validate_preds_layout,
    )
    resolved_dir, fold_paths = resolve_preds_files(root, preds_dir=args.preds_dir)
    if fold_paths:
        folds_subset = sorted(fold_paths.keys())
        ref_map = load_train_reference_map(root)
        preds_by_fold = validate_preds_layout(fold_paths, folds_data)
        greedy_res = label_clean_oof_greedy(preds_by_fold, fold_membership, key_flags, ref_map)
        clean_labels = greedy_res["clean_cluster_labels"]

    summary = analyze_near_duplicates(
        folds_data,
        records_by_key,
        key_flags,
        clean_labels=clean_labels,
        folds_subset=folds_subset,
        threshold=args.threshold,
        k_shingle=args.shingle_k,
    )

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    rep_md = out_dir / "near_dup_oof.md"
    rep_json = out_dir / "near_dup_oof.json"
    md_text = render_near_dup_report(summary)
    rep_md.write_text(md_text, encoding="utf-8", newline="\n")
    jsonl_write_atomic(rep_json, [summary])
    write_provenance(
        rep_json,
        inputs=[folds_path, root / "ml" / "train_m2" / "contract" / "harvest_inputs.jsonl"],
        seed=args.seed,
        extra={"threshold": args.threshold, "shingle_k": args.shingle_k},
    )

    if summary["alert_triggered"]:
        print(summary["alert_message"])
        print(f"Remaining clean clusters after removal: {summary['remaining_after_removal']}")
    print(md_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
