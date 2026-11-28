"""Label greedy out-of-fold (OOF) predictions using P3 oracle (Shaurya-owned).

Reads greedy OOF prediction files `fold{f}_preds.jsonl` from:
  1. Explicit `--preds-dir` if specified, OR
  2. Default `ml/train_m2/harvest_out/sft_oof_greedy/` (gitignored), falling back to
     ``docs/phase6_shaurya/crossfit/oof_preds/`` then repository root if present.
If files are absent, STOPs with exit code 1 and instructs the operator to copy them from Drive.

Rules:
  - Validates file layout against ml/train_m1/score_oof.py and docs/phase6_shaurya/crossfit/folds.json.
  - Strictly excludes and NEVER scores any held-out (B1, B2, C_verifier, gold, C-human) or A_val cluster.
  - Folds listed in OOF_PREDS_MANIFEST.json as INVALID are silently skipped; they are NEVER labeled.
  - Labels each clean fold-f cluster against the reference for its own input_key (preserving record finding_id).
  - Statistical unit is CLUSTER (distinct input_key).
  - Evaluates sufficiency verdict via post_oof.evaluate_partial_oof for n = clean_oof + 15.
  - Reports counts only (zero input content) + provenance JSON.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping, Sequence

# Ensure repository root is on sys.path when invoked directly as a script
_repo_root = str(Path(__file__).resolve().parents[3])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from ml.mutation_engine.dataset_io import input_key as ds_input_key
from ml.train_m2.common import jsonl_iter, jsonl_write_atomic, load_inputs, repo_root, write_provenance
from ml.train_m2.eval.ingest_oof import _build_fold_membership, _build_key_flags, _load_folds
from ml.train_m2.eval.post_oof import evaluate_partial_oof
from ml.train_m2.labels.oracle import (
    OC_ESCALATED_OK,
    OC_ESCALATED_UNNEEDED,
    OC_FIXED_SHOULD_ESCALATE,
    OC_MINIMAL_CORRECT,
    OC_UNKNOWN,
    OC_VALID_NOT_MINIMAL,
    OC_WRONG,
    SRC_REFERENCE,
    label_candidate,
)

LOG = logging.getLogger("label_oof_greedy")
DEFAULT_PREDS_RELDIR = Path("ml") / "train_m2" / "harvest_out" / "sft_oof_greedy"
_CROSSFIT_OOF_PREDS_RELDIR = Path("docs") / "phase6_shaurya" / "crossfit" / "oof_preds"
_FOLD_FILE_RE = re.compile(r"^fold(\d+)_preds\.jsonl$")
SEED = 1337


def load_invalid_folds(manifest_path: Path | None = None) -> frozenset[int]:
    """Return the set of fold IDs marked INVALID in OOF_PREDS_MANIFEST.json (counts-only).

    Returns an empty frozenset if the manifest does not exist or has no INVALID entries.
    Never raises; logs a warning if the file cannot be parsed.
    """
    _log = logging.getLogger("label_oof_greedy.manifest")
    candidates: list[Path] = []
    if manifest_path is not None:
        candidates = [manifest_path]
    else:
        try:
            root = repo_root()
            candidates = [
                root / "docs" / "phase6_shaurya" / "crossfit" / "OOF_PREDS_MANIFEST.json",
            ]
        except Exception:
            pass

    for p in candidates:
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            folds_meta = data.get("folds", {})
            invalid: set[int] = set()
            for fold_id_str, fmeta in folds_meta.items():
                if str(fmeta.get("status", "")).upper() == "INVALID":
                    invalid.add(int(fold_id_str))
            return frozenset(invalid)
        except Exception as exc:
            _log.warning("Could not parse OOF_PREDS_MANIFEST.json at %s: %s", p, exc)
    return frozenset()


def resolve_preds_files(
    root: Path,
    preds_dir: Path | str | None = None,
) -> tuple[Path | None, dict[int, Path]]:
    """Locate fold*_preds.jsonl files without fetching anything.

    When `preds_dir` is explicitly provided, searches ONLY that directory.
    When `preds_dir` is None, searches (in order):
      1. ml/train_m2/harvest_out/sft_oof_greedy/
      2. docs/phase6_shaurya/crossfit/oof_preds/
      3. repo root
    """
    candidates: list[Path] = []
    if preds_dir is not None:
        d = Path(preds_dir)
        if not d.is_absolute():
            d = root / d
        candidates = [d]
    else:
        candidates = [
            root / DEFAULT_PREDS_RELDIR,
            root / _CROSSFIT_OOF_PREDS_RELDIR,
            root,
        ]

    for cand in candidates:
        if not cand.is_dir():
            continue
        found: dict[int, Path] = {}
        for p in sorted(cand.glob("fold*_preds.jsonl")):
            m = _FOLD_FILE_RE.match(p.name)
            if m:
                found[int(m.group(1))] = p
        if found:
            return cand, found

    return None, {}


def load_train_reference_map(root: Path) -> dict[str, dict[str, Any]]:
    """Load non-held-out training input_key -> {record, reference, route} from dataset/train.jsonl."""
    train_path = root / "ml" / "mutation_engine" / "dataset" / "train.jsonl"
    ref_map: dict[str, dict[str, Any]] = {}
    if not train_path.is_file():
        return ref_map
    for ex in jsonl_iter(train_path):
        ik = ds_input_key(ex)
        if ik not in ref_map:
            ref_map[ik] = {
                "record": ex["input"],
                "reference": ex.get("target"),
                "route": (ex.get("meta") or {}).get("route", "fix"),
            }
    return ref_map


def fold_schema_valid_fraction(
    rows: Sequence[Mapping[str, Any]],
    schema: Mapping[str, Any] | None = None,
) -> float:
    """Return fraction of rows whose ``content`` parses as JSON and passes Patch-IR schema."""
    if not rows:
        return 0.0
    if schema is None:
        schema_path = repo_root() / "remediate" / "patch_ir" / "schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    import jsonschema
    validator = jsonschema.Draft7Validator(schema)
    valid = 0
    for r in rows:
        content = r.get("content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        try:
            obj = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(obj, dict) and validator.is_valid(obj):
            valid += 1
    return valid / len(rows)


def reject_invalid_schema_folds(
    preds_by_fold: Mapping[int, list[dict[str, Any]]],
    *,
    min_schema_valid_frac: float = 0.90,
    schema: Mapping[str, Any] | None = None,
) -> tuple[dict[int, list[dict[str, Any]]], dict[int, float]]:
    """Reject any fold whose schema-valid fraction is below ``min_schema_valid_frac``.

    Returns (valid_preds_by_fold, rejected_fractions). Rejected folds are NEVER labeled.
    """
    valid: dict[int, list[dict[str, Any]]] = {}
    rejected: dict[int, float] = {}
    for f, rows in sorted(preds_by_fold.items()):
        frac = fold_schema_valid_fraction(rows, schema=schema)
        if frac < min_schema_valid_frac:
            LOG.warning(
                "Rejecting fold %d: schema-valid fraction %.3f < %.2f; will not label.",
                f, frac, min_schema_valid_frac,
            )
            rejected[f] = frac
        else:
            valid[f] = rows
    return valid, rejected


def validate_preds_layout(
    fold_paths: Mapping[int, Path],
    folds_data: Mapping[str, Any],
    invalid_folds: frozenset[int] | None = None,
    *,
    min_schema_valid_frac: float | None = None,
    schema: Mapping[str, Any] | None = None,
) -> dict[int, list[dict[str, Any]]]:
    """Validate each fold{f}_preds.jsonl against score_oof.py layout and folds.json keys.

    Folds listed in ``invalid_folds`` are silently skipped and never loaded.
    If ``min_schema_valid_frac`` is set, any loaded fold below that threshold is also
    rejected and excluded so invalid folds are never labeled.
    """
    _skip = invalid_folds or frozenset()
    preds_by_fold: dict[int, list[dict[str, Any]]] = {}
    folds_map = folds_data.get("folds", {})

    for f, p in sorted(fold_paths.items()):
        if f in _skip:
            LOG.info("Skipping fold %d: marked INVALID in manifest", f)
            continue
        rows: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for row in jsonl_iter(p):
            if "input_key" not in row or "content" not in row:
                raise ValueError(
                    f"{p.name}: missing required score_oof keys 'input_key'/'content'"
                )
            ik = row["input_key"]
            if ik in seen_keys:
                raise ValueError(f"{p.name}: duplicate input_key {ik[:40]!r}")
            seen_keys.add(ik)
            rows.append(row)

        f_str = str(f)
        if f_str in folds_map:
            expected_keys = set(folds_map[f_str]["input_keys"])
            if seen_keys != expected_keys:
                raise ValueError(
                    f"{p.name}: key set mismatch vs folds.json fold {f}: "
                    f"missing={len(expected_keys - seen_keys)}, extra={len(seen_keys - expected_keys)}"
                )
        preds_by_fold[f] = rows

    if min_schema_valid_frac is not None:
        preds_by_fold, _ = reject_invalid_schema_folds(
            preds_by_fold,
            min_schema_valid_frac=min_schema_valid_frac,
            schema=schema,
        )

    return preds_by_fold


def label_clean_oof_greedy(
    preds_by_fold: Mapping[int, Sequence[Mapping[str, Any]]],
    fold_membership: Mapping[str, int],
    key_flags: Mapping[str, Mapping[str, bool]],
    ref_map: Mapping[str, Mapping[str, Any]],
    *,
    score_fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
    existing_unseen_clean: int = 15,
    alpha: float = 0.05,
    delta: float = 0.05,
    truncate_folds: frozenset[int] | set[int] | None = None,
    schema: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Label CLEAN fold-f greedy OOF clusters using the P3 oracle.

    Strictly filters out held-out and A_val clusters BEFORE scoring. Never inspects or scores
    held-out or A_val rows. Computes partial-fold Clopper-Pearson verdict via post_oof.evaluate_partial_oof.

    If ``truncate_folds`` contains fold ``f``, candidates in fold ``f`` are truncated via
    ``oof_truncate.first_json_prefix`` as a diagnostic proxy ONLY and tagged
    ``diagnostic_truncated=True``.
    """
    if score_fn is None:
        from ml.train_m1.eval.score import score_inputs  # FROZEN Phase 5 scorer
        score_fn = score_inputs

    _trunc = frozenset(truncate_folds) if truncate_folds else frozenset()
    if _trunc:
        from ml.train_m2.eval.oof_truncate import first_json_prefix

    per_fold_counts: list[dict[str, Any]] = []
    partial_rows: list[dict[str, Any]] = []
    clean_cluster_labels: dict[str, dict[str, Any]] = {}

    total_raw = 0
    total_excluded = 0
    total_clean = 0
    total_gp = 0
    total_min_correct = 0
    total_k = 0
    total_vnm = 0
    total_wrong = 0
    total_fixed_esc = 0
    total_unknown = 0
    total_esc_ok = 0
    total_esc_unneeded = 0

    for f in sorted(preds_by_fold.keys()):
        is_trunc_fold = f in _trunc
        raw_rows = list(preds_by_fold[f])
        clean_rows: list[Mapping[str, Any]] = []
        excluded = 0

        for r in raw_rows:
            ik = r["input_key"]
            flags = key_flags.get(ik, {})
            if flags.get("in_heldout") or flags.get("in_a_val"):
                excluded += 1
                continue
            if ik not in ref_map:
                raise KeyError(f"Clean input_key missing from train reference map: {ik[:60]}")
            clean_rows.append(r)

        effective_contents: list[str] = []
        for r in clean_rows:
            raw_content = str(r.get("content", ""))
            if is_trunc_fold:
                obj, ok = first_json_prefix(raw_content, schema=schema)
                effective_contents.append(json.dumps(obj) if ok and obj is not None else "")
            else:
                effective_contents.append(raw_content)

        # Batch score ONLY clean rows via score_fn (never held-out or A_val)
        score_items = []
        for r, eff_content in zip(clean_rows, effective_contents):
            ik = r["input_key"]
            ref_entry = ref_map[ik]
            score_items.append({
                "record": ref_entry["record"],
                "route": ref_entry.get("route", "fix"),
                "reference": ref_entry.get("reference"),
                "contents": [eff_content],
            })

        scored_results = score_fn(score_items) if score_items else []
        if len(scored_results) != len(clean_rows):
            raise RuntimeError(
                f"Scorer returned {len(scored_results)} items for {len(clean_rows)} clean inputs"
            )

        f_gp = 0
        f_min_correct = 0
        f_k = 0
        f_vnm = 0
        f_wrong = 0
        f_fixed_esc = 0
        f_unknown = 0
        f_esc_ok = 0
        f_esc_unneeded = 0

        for r, content, score_res in zip(clean_rows, effective_contents, scored_results):
            ik = r["input_key"]
            ref_entry = ref_map[ik]
            record = ref_entry["record"]
            reference = ref_entry.get("reference")
            route = ref_entry.get("route", "fix")

            cands = score_res.get("candidates", [])
            scored_cand = cands[0] if cands else {"gate_passed": False, "outcome": "rejected", "hidden": None}

            try:
                parsed = json.loads(content) if isinstance(content, str) and content.strip() else None
                patch = parsed if isinstance(parsed, dict) else None
            except (json.JSONDecodeError, TypeError):
                patch = None

            label_row = label_candidate(
                record=record,
                patch=patch,
                reference=reference,
                route=route,
                scored=scored_cand,
                source=SRC_REFERENCE,
                source_file=f"fold{f}_preds.jsonl",
                generator="sft_oof",
                profile="A",
                sample_idx=0,
                input_key=ik,
                content=content,
            )

            oc = label_row.oracle_class
            gp = bool(label_row.gate_pass)
            if gp:
                f_gp += 1

            is_wrong_cluster = False
            if oc == OC_MINIMAL_CORRECT:
                f_min_correct += 1
            elif oc == OC_VALID_NOT_MINIMAL:
                f_vnm += 1
                is_wrong_cluster = gp
            elif oc == OC_WRONG:
                f_wrong += 1
                is_wrong_cluster = gp
            elif oc == OC_FIXED_SHOULD_ESCALATE:
                f_fixed_esc += 1
                is_wrong_cluster = gp
            elif oc == OC_UNKNOWN:
                f_unknown += 1
            elif oc == OC_ESCALATED_OK:
                f_esc_ok += 1
            elif oc == OC_ESCALATED_UNNEEDED:
                f_esc_unneeded += 1

            if is_wrong_cluster:
                f_k += 1

            # Partial-OOF row preserving record's finding_id
            partial_oc = OC_WRONG if oc == OC_FIXED_SHOULD_ESCALATE else oc
            partial_rows.append({
                "input_key": ik,
                "crossfit_fold": f,
                "sample_idx": 0,
                "gate_pass": gp,
                "oracle_class": partial_oc,
                "finding_id": record.get("finding_id"),
                "patch": patch,
                "diagnostic_truncated": is_trunc_fold,
            })
            clean_cluster_labels[ik] = {
                "fold": f,
                "route": route,
                "gate_pass": gp,
                "outcome": label_row.outcome,
                "oracle_class": oc,
                "strict_correct": label_row.strict_correct,
                "diagnostic_truncated": is_trunc_fold,
            }

        per_fold_counts.append({
            "fold": f,
            "diagnostic_truncated": is_trunc_fold,
            "raw_clusters": len(raw_rows),
            "excluded_heldout_or_aval": excluded,
            "clean_clusters": len(clean_rows),
            "gate_pass": f_gp,
            "minimal_correct": f_min_correct,
            "gate_pass_and_wrong_k": f_k,
            "valid_not_minimal": f_vnm,
            "wrong": f_wrong,
            "fixed_should_escalate": f_fixed_esc,
            "unknown": f_unknown,
            "escalated_ok": f_esc_ok,
            "escalated_unneeded": f_esc_unneeded,
        })

        total_raw += len(raw_rows)
        total_excluded += excluded
        total_clean += len(clean_rows)
        total_gp += f_gp
        total_min_correct += f_min_correct
        total_k += f_k
        total_vnm += f_vnm
        total_wrong += f_wrong
        total_fixed_esc += f_fixed_esc
        total_unknown += f_unknown
        total_esc_ok += f_esc_ok
        total_esc_unneeded += f_esc_unneeded

    partial_verdict = evaluate_partial_oof(
        partial_rows,
        dict(fold_membership),
        {k: dict(v) for k, v in key_flags.items()},
        existing_unseen_clean=existing_unseen_clean,
        alpha=alpha,
        delta=delta,
    )

    return {
        "diagnostic_truncated": bool(_trunc),
        "diagnostic_truncated_folds": sorted(_trunc),
        "per_fold": per_fold_counts,
        "totals": {
            "raw_clusters": total_raw,
            "excluded_heldout_or_aval": total_excluded,
            "clean_clusters": total_clean,
            "gate_pass": total_gp,
            "minimal_correct": total_min_correct,
            "gate_pass_and_wrong_k": total_k,
            "valid_not_minimal": total_vnm,
            "wrong": total_wrong,
            "fixed_should_escalate": total_fixed_esc,
            "unknown": total_unknown,
            "escalated_ok": total_esc_ok,
            "escalated_unneeded": total_esc_unneeded,
        },
        "clean_k": partial_verdict["k"],
        "existing_clean_clusters": existing_unseen_clean,
        "total_clean_n": partial_verdict["total_clean_clusters"],
        "cp_min_n": partial_verdict["cp_min_n"],
        "margin": partial_verdict["total_clean_clusters"] - partial_verdict["cp_min_n"],
        "verdict": partial_verdict["verdict"],
        "needed_more": partial_verdict["needed_more"],
        "remaining_folds": partial_verdict["remaining_folds"],
        "covering_folds": partial_verdict["covering_folds"],
        "covering_status": partial_verdict["covering_status"],
        "clean_cluster_labels": clean_cluster_labels,
    }


def render_label_oof_greedy_report(summary: Mapping[str, Any]) -> str:
    """Render counts-only markdown summary (zero input content)."""
    is_diag = bool(summary.get("diagnostic_truncated"))
    nd_summary = summary.get("near_dup_summary")

    if is_diag:
        title = (
            "# DIAGNOSTIC ESTIMATE, folds 2 and 4 truncated at first JSON; "
            "not evidence for certification; replace with regenerated preds"
        )
        nd_by_fold = {
            r["fold"]: r for r in (nd_summary.get("per_fold", []) if nd_summary else [])
        }
        lines = [
            title,
            "",
            "| Fold | Diagnostic Truncated | Raw | Excluded (Heldout/A_val) | Clean Clusters | Gate-Pass | Minimal Correct | Gate-Pass-and-Wrong (k) | valid_not_minimal | unknown | Near-Dups | Remaining Clean |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in summary["per_fold"]:
            nd_r = nd_by_fold.get(r["fold"], {})
            nd_cnt = nd_r.get("near_dup_count", 0)
            rem_cnt = nd_r.get("remaining_independent", r["clean_clusters"] - nd_cnt)
            lines.append(
                f"| {r['fold']} | {bool(r.get('diagnostic_truncated'))} | {r['raw_clusters']} | "
                f"{r['excluded_heldout_or_aval']} | {r['clean_clusters']} | {r['gate_pass']} | "
                f"{r['minimal_correct']} | {r['gate_pass_and_wrong_k']} | {r['valid_not_minimal']} | "
                f"{r['unknown']} | {nd_cnt} | {rem_cnt} |"
            )
        t = summary["totals"]
        tot_nd = nd_summary.get("near_duplicate_count", 0) if nd_summary else 0
        tot_rem = nd_summary.get("remaining_after_removal", t["clean_clusters"] - tot_nd) if nd_summary else t["clean_clusters"]
        lines.append(
            f"| **Total** | **True** | **{t['raw_clusters']}** | **{t['excluded_heldout_or_aval']}** | "
            f"**{t['clean_clusters']}** | **{t['gate_pass']}** | **{t['minimal_correct']}** | "
            f"**{t['gate_pass_and_wrong_k']}** | **{t['valid_not_minimal']}** | **{t['unknown']}** | "
            f"**{tot_nd}** | **{tot_rem}** |"
        )
        cert = nd_summary.get("certification_comparison") if nd_summary else None
        if cert:
            lines.extend([
                "",
                "## Diagnostic Clopper-Pearson Estimate (alpha=0.05, delta=0.05, NOT for certification)",
                "",
                "| Version | OOF Clean | Existing | Total n | k | cp_min_n | Margin | Verdict |",
                "|---|---|---|---|---|---|---|---|",
            ])
            for label, key in (
                ("(a) All clean clusters", "all_clean"),
                ("(b) After removing near-duplicates", "after_removing_near_dups"),
            ):
                c = cert[key]
                lines.append(
                    f"| {label} | {c['oof_clean']} | {c['existing_clean']} | {c['n']} | "
                    f"{c['k']} | {c['cp_min_n']} | {c['margin']:+d} | {c['verdict']} |"
                )
            lines.append(f"\n> {cert['note']}")
        return "\n".join(lines) + "\n"

    lines = [
        "# OOF Greedy Predictions P3 Oracle Summary (Clean Clusters Only)",
        "",
        "| Fold | Raw | Excluded (Heldout/A_val) | Clean Clusters | Gate-Pass | Minimal Correct | Gate-Pass-and-Wrong (k) | valid_not_minimal | unknown |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in summary["per_fold"]:
        lines.append(
            f"| {r['fold']} | {r['raw_clusters']} | {r['excluded_heldout_or_aval']} | "
            f"{r['clean_clusters']} | {r['gate_pass']} | {r['minimal_correct']} | "
            f"{r['gate_pass_and_wrong_k']} | {r['valid_not_minimal']} | {r['unknown']} |"
        )
    t = summary["totals"]
    lines.append(
        f"| **Total** | **{t['raw_clusters']}** | **{t['excluded_heldout_or_aval']}** | "
        f"**{t['clean_clusters']}** | **{t['gate_pass']}** | **{t['minimal_correct']}** | "
        f"**{t['gate_pass_and_wrong_k']}** | **{t['valid_not_minimal']}** | **{t['unknown']}** |"
    )
    margin = summary.get("margin", summary["total_clean_n"] - summary["cp_min_n"])
    lines.extend([
        "",
        "## Certification Verdict (Partial-Fold Post-OOF)",
        "",
        f"- Clean OOF clusters: {t['clean_clusters']}",
        f"- Existing clean clusters: {summary['existing_clean_clusters']}",
        f"- Total clean clusters n: **{summary['total_clean_n']}**",
        f"- Clean gate-pass-and-wrong count k: **{summary['clean_k']}**",
        f"- Clopper-Pearson minimum n required (alpha=0.05, delta=0.05): **{summary['cp_min_n']}**",
        f"- Margin (n - cp_min_n): **{margin:+d}**",
        f"- **Verdict: {summary['verdict']}**",
        f"- Remaining folds: {summary['remaining_folds']}",
        f"- Coverage: {summary['covering_status']}",
        "- Note: the certificate depends on accepted drafts at tau, so the effective n is smaller; do not estimate it.",
    ])
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    p = argparse.ArgumentParser(description="Label greedy OOF predictions via P3 oracle")
    p.add_argument("--preds-dir", default=None, help="Directory with fold{f}_preds.jsonl (default checks harvest_out/sft_oof_greedy then oof_preds/ then repo root)")
    p.add_argument("--folds", default="docs/phase6_shaurya/crossfit/folds.json", help="Path to folds.json")
    p.add_argument("--manifest", default=None, help="Path to OOF_PREDS_MANIFEST.json (default: auto-discovered)")
    p.add_argument("--out-dir", default="ml/train_m2/out/reports", help="Output directory for counts-only report")
    p.add_argument(
        "--truncate-first-json",
        action="store_true",
        default=False,
        help="Diagnostic only: label INVALID folds on their first-JSON prefix (writes separate diagnostic report; never mixes with certified counts).",
    )
    p.add_argument("--seed", type=int, default=SEED, help="Seed (default 1337)")
    args = p.parse_args(argv)

    root = repo_root()
    resolved_dir, fold_paths = resolve_preds_files(root, preds_dir=args.preds_dir)
    if not fold_paths:
        msg = (
            "STOP: Greedy OOF predictions (fold{0..4}_preds.jsonl) are absent under "
            f"{args.preds_dir or DEFAULT_PREDS_RELDIR.as_posix()}. "
            "Please copy them from Google Drive (/content/drive/MyDrive/argus/out_crossfit/) "
            "into ml/train_m2/harvest_out/sft_oof_greedy/ (do not fetch automatically)."
        )
        print(msg, file=sys.stderr)
        return 1

    # Load invalid folds from manifest
    manifest_path = Path(args.manifest) if args.manifest else None
    if manifest_path and not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    invalid_folds = load_invalid_folds(manifest_path)

    folds_path = Path(args.folds)
    if not folds_path.is_absolute():
        folds_path = root / folds_path
    folds_data = _load_folds(folds_path)
    fold_membership = _build_fold_membership(folds_data)
    inputs = load_inputs()
    key_flags = _build_key_flags(inputs)
    ref_map = load_train_reference_map(root)

    if args.truncate_first_json:
        # Diagnostic mode: load all folds, truncate ONLY invalid/sub-threshold folds at first JSON
        preds_by_fold = validate_preds_layout(
            fold_paths,
            folds_data,
            invalid_folds=frozenset(),
            min_schema_valid_frac=None,
        )
        sub_threshold = {
            f for f, rows in preds_by_fold.items()
            if fold_schema_valid_fraction(rows) < 0.90
        }
        truncate_folds = frozenset(set(invalid_folds) | sub_threshold)
        LOG.info("Diagnostic --truncate-first-json active; truncating folds: %s", sorted(truncate_folds))
    else:
        if invalid_folds:
            LOG.info("Folds marked INVALID in manifest (will not be labeled): %s", sorted(invalid_folds))
        preds_by_fold = validate_preds_layout(
            fold_paths,
            folds_data,
            invalid_folds=invalid_folds,
            min_schema_valid_frac=0.90,
        )
        truncate_folds = frozenset()

    summary = label_clean_oof_greedy(
        preds_by_fold,
        fold_membership,
        key_flags,
        ref_map,
        truncate_folds=truncate_folds,
    )

    if args.truncate_first_json:
        from ml.train_m2.eval.near_dup_check import analyze_near_duplicates

        records_by_key = {r["input_key"]: r["record"] for r in inputs}
        nd_summary = analyze_near_duplicates(
            folds_data,
            records_by_key,
            key_flags,
            clean_labels=summary["clean_cluster_labels"],
            folds_subset=sorted(preds_by_fold.keys()),
        )
        summary["near_dup_summary"] = nd_summary

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Counts-only output JSON; never mix diagnostic output into oof_greedy_labels.*
    report_payload = {k: v for k, v in summary.items() if k != "clean_cluster_labels"}
    if args.truncate_first_json:
        report_md = out_dir / "oof_greedy_labels_diagnostic.md"
        report_json = out_dir / "oof_greedy_labels_diagnostic.json"
    else:
        report_md = out_dir / "oof_greedy_labels.md"
        report_json = out_dir / "oof_greedy_labels.json"

    md_text = render_label_oof_greedy_report(summary)
    report_md.write_text(md_text, encoding="utf-8", newline="\n")
    jsonl_write_atomic(report_json, [report_payload])
    rel_dir = resolved_dir.relative_to(root).as_posix() if resolved_dir and resolved_dir.is_relative_to(root) else "."
    write_provenance(
        report_json,
        inputs=list(fold_paths.values()),
        seed=args.seed,
        extra={
            "preds_source_dir": rel_dir,
            "folds": sorted(fold_paths.keys()),
            "invalid_folds": sorted(invalid_folds),
            "diagnostic_truncated": bool(args.truncate_first_json),
            "diagnostic_truncated_folds": sorted(truncate_folds),
            "valid_folds": sorted(f for f in fold_paths if f not in invalid_folds),
        },
    )

    print(md_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
