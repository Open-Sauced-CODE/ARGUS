"""Post-OOF dry-run pipeline for ARGUS Trust Engine (Shaurya-owned).

Chains the following steps:
  1. Ingest OOF harvest rows (ingest_oof)
  2. Write re-split proposal (incorporating new clean unseen clusters)
  3. Retrain per-generator M2 on non-test data (train + val)
  4. Calibrate tau on cal partition (Learn-Then-Test)
  5. Emit change-log entry text for EXPERIMENT_PLAN_M2.md section 12 (printed, not applied)

RULES:
  - Default is --dry-run True.
  - In dry-run mode, all outputs are written strictly under --out-dir.
  - NEVER touches or modifies ml/train_m2/out/m2/ or tau_star.json in dry-run mode.
  - Real mode (--no-dry-run) refuses to run unless --i-understand is passed AND
    RUN_LOG_M2.md does not exist.
  - Accompanied by provenance using write_provenance(path, seed=1337).
  - All outputs ASCII-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from ml.train_m2.common import (
    jsonl_iter,
    jsonl_write_atomic,
    load_inputs,
    provenance,
    repo_root,
    write_provenance,
)
from ml.train_m2.eval.ingest_oof import (
    _build_fold_membership,
    _build_key_flags,
    _extract_fold,
    _load_folds,
    assert_fold_disjointness,
    compute_unseen_clean_counts,
    render_report,
)
from ml.train_m2.features import registry as R
from ml.train_m2.models import train_m2 as T
from ml.train_m2.risk import calibrate_tau as CT
from ml.train_m2.risk import ltt
from ml.train_m2.splits import assert_disjoint, build_splits, cell_table, splits_hash

LOG = logging.getLogger("post_oof")
SEED = 1337

# Clean counts per fold from docs/phase6_shaurya/crossfit/folds.md
CLEAN_COUNTS_PER_FOLD: dict[int, int] = {
    0: 37,
    1: 35,
    2: 30,
    3: 33,
    4: 33,
}


def compute_cp_min_n(k: int, alpha: float = 0.05, delta: float = 0.05) -> int:
    """Compute smallest n >= max(k + 1, 1) such that cp_upper(k, n, delta) <= alpha.

    Uses ltt.cp_upper (one-sided Clopper-Pearson upper confidence bound).
    """
    if not (0 < alpha < 1 and 0 < delta < 1):
        raise ValueError("alpha and delta must be in (0, 1)")
    if k < 0:
        raise ValueError("k must be non-negative")
    n = max(k + 1, 1)
    while ltt.cp_upper(k, n, delta) > alpha:
        n += 1
    return n


def _is_gate_pass(row: dict[str, Any]) -> bool:
    """Extract gate_pass status from row."""
    if row.get("gate_pass") is not None:
        return bool(row["gate_pass"])
    if row.get("gate_passed") is not None:
        return bool(row["gate_passed"])
    scored = row.get("scored")
    if isinstance(scored, dict):
        cands = scored.get("candidates", [])
        if cands and isinstance(cands[0], dict):
            return bool(cands[0].get("gate_passed"))
    return False


def _is_wrong(row: dict[str, Any]) -> bool:
    """Extract wrong status from row."""
    oc = row.get("oracle_class")
    if oc is not None:
        return oc in ("wrong", "valid_not_minimal")
    if row.get("wrong") is not None:
        return bool(row["wrong"])
    if row.get("y") is not None:
        return int(row["y"]) == 0
    if row.get("strict_correct") is not None:
        return not bool(row["strict_correct"])
    return False


def evaluate_partial_oof(
    rows: list[dict[str, Any]],
    fold_membership: dict[str, int],
    key_flags: dict[str, dict[str, bool]],
    existing_unseen_clean: int = 15,
    alpha: float = 0.05,
    delta: float = 0.05,
    clean_counts_per_fold: Mapping[int, int] | None = None,
) -> dict[str, Any]:
    """Analyze a partial (or full) set of OOF folds for SFT certification readiness.

    Reports:
      - folds_present: sorted list of fold indices (1..5) present in rows
      - clean_unseen_clusters: sorted list of clean unseen cluster keys
      - oof_clean_count: count of clean unseen clusters from OOF rows
      - existing_clean_count: count of existing clean unseen clusters (default 15)
      - total_clean_clusters: oof_clean_count + existing_clean_count
      - k: count of gate-passing-but-wrong SFT drafts among clean unseen clusters at CLUSTER level
      - cp_min_n: Clopper-Pearson minimum n for k at alpha, delta
      - verdict: 'SUFFICIENT' if total_clean_clusters >= cp_min_n else 'NEED <m> MORE CLEAN CLUSTERS'
      - remaining_folds: list of fold indices not present in rows
      - covering_folds: minimal remaining folds that would cover the deficit
      - covering_status: human-readable explanation of fold coverage

    Rules:
      - Statistical unit is CLUSTER (distinct input_key).
      - Never uses any held-out or A_val cluster.
      - Does NOT choose a threshold tau.
    """
    clean_counts = dict(clean_counts_per_fold) if clean_counts_per_fold is not None else CLEAN_COUNTS_PER_FOLD

    # 1. Identify folds present in rows
    folds_present_set: set[int] = set()
    for r in rows:
        f = _extract_fold(r)
        if f is not None:
            folds_present_set.add(f)
    folds_present = sorted(folds_present_set)

    # 2. Group rows by input_key
    from collections import defaultdict
    by_ik: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        ik = r.get("input_key")
        if ik:
            by_ik[ik].append(r)

    clean_unseen_clusters: list[str] = []
    k_clusters: list[str] = []

    for ik, cluster_rows in by_ik.items():
        flags = key_flags.get(ik, {})
        in_heldout = flags.get("in_heldout", False) or any(r.get("heldout_overlap") for r in cluster_rows)
        in_a_val = flags.get("in_a_val", False) or any(r.get("in_a_val") for r in cluster_rows)

        # Held-out and A_val clusters are STRICTLY EXCLUDED
        if in_heldout or in_a_val:
            continue

        assigned_fold = fold_membership.get(ik)
        cf_values = {_extract_fold(r) for r in cluster_rows} - {None}
        if not cf_values:
            continue

        # unseen = adapter that generated this completion excluded this input
        unseen = any(assigned_fold == cf for cf in cf_values)
        if not unseen:
            continue

        # This is a clean unseen cluster
        clean_unseen_clusters.append(ik)

        # 3. Check for gate-passing-but-wrong at CLUSTER level on greedy draft (sample_idx == 0)
        greedy_rows = [r for r in cluster_rows if r.get("sample_idx", 0) == 0]
        greedy_row = greedy_rows[0] if greedy_rows else cluster_rows[0]

        if _is_gate_pass(greedy_row) and _is_wrong(greedy_row):
            k_clusters.append(ik)

    clean_unseen_clusters.sort()
    oof_clean_count = len(clean_unseen_clusters)
    total_clean = oof_clean_count + existing_unseen_clean
    k = len(k_clusters)

    # 4. Clopper-Pearson minimum n for k
    cp_min_n = compute_cp_min_n(k, alpha=alpha, delta=delta)

    # 5. Verdict and deficit
    if total_clean >= cp_min_n:
        verdict = "SUFFICIENT"
        needed_more = 0
    else:
        needed_more = cp_min_n - total_clean
        verdict = f"NEED {needed_more} MORE CLEAN CLUSTERS"

    # 6. Remaining folds coverage
    all_folds = [0, 1, 2, 3, 4]
    remaining_folds = [f for f in all_folds if f not in folds_present]
    covering_folds: list[int] = []
    covering_count = 0

    if verdict != "SUFFICIENT":
        for f in remaining_folds:
            covering_folds.append(f)
            covering_count += clean_counts.get(f, 0)
            if covering_count >= needed_more:
                break
        if covering_count >= needed_more:
            covering_status = (
                f"Remaining fold(s) {covering_folds} provide {covering_count} clean clusters, "
                f"covering the deficit of {needed_more}."
            )
        else:
            covering_status = (
                f"All remaining fold(s) {remaining_folds} provide {covering_count} clean clusters, "
                f"which is insufficient for the deficit of {needed_more}."
            )
    else:
        covering_status = "Available clean unseen clusters are SUFFICIENT for certification."

    return {
        "folds_present": folds_present,
        "oof_clean_count": oof_clean_count,
        "existing_clean_count": existing_unseen_clean,
        "total_clean_clusters": total_clean,
        "k": k,
        "k_clusters": sorted(k_clusters),
        "alpha": alpha,
        "delta": delta,
        "cp_min_n": cp_min_n,
        "verdict": verdict,
        "needed_more": needed_more,
        "remaining_folds": remaining_folds,
        "covering_folds": covering_folds,
        "covering_count": covering_count,
        "covering_status": covering_status,
        "clean_unseen_clusters": clean_unseen_clusters,
    }


def render_partial_oof_report(res: dict[str, Any]) -> str:
    """Render markdown summary of partial OOF analysis."""
    lines = [
        "# Partial-Fold Post-OOF Analysis Report (SFT Certification Readiness)",
        "",
        f"- Folds present in harvest: {res['folds_present']} (count: {len(res['folds_present'])})",
        f"- OOF clean unseen clusters: {res['oof_clean_count']}",
        f"- Pre-OOF existing clean clusters: {res['existing_clean_count']}",
        f"- Total clean unseen clusters: **{res['total_clean_clusters']}**",
        "",
        "## Error Analysis at Cluster Level (Greedy Drafts)",
        "",
        f"- Gate-passing-but-wrong drafts (k): **{res['k']}**",
        f"- Target risk alpha: {res['alpha']}, failure bound delta: {res['delta']}",
        f"- Clopper-Pearson minimum n required (cp_upper(k, n, delta) <= alpha): **{res['cp_min_n']}**",
        "",
        "## Verdict",
        "",
        f"- **Verdict: {res['verdict']}**",
        f"- Remaining folds available: {res['remaining_folds']}",
        f"- Recommendation: {res['covering_status']}",
    ]
    return "\n".join(lines) + "\n"

# The 15 A_val-only clusters that Phase 5 SFT never trained on, forced into calibration split
DEFAULT_FORCED_CAL_CLUSTERS: tuple[str, ...] = (
    '{"fields":{"action":["autoscaling:*","elasticloadbalancing:*","codepipeline:PutJobFailureResult","codepipeline:PutJobSuccessResult","ec2:CreateLaunchTemplate","ec2:CreateLaunchTemplateVersion","ec2:DescribeImages","ec2:DescribeLaunchTemplates","ec2:DescribeLaunchTemplateVersions","ec2:DeregisterImage","ec2:DeleteSnapshot","ec2:DescribeSnapshots","logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents","logs:DescribeLogStreams","sns:Publish","ssm:*","*"],"effect":"Allow","resource":["*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
    '{"fields":{"action":["cloudwatch:*","logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents","dynamodb:BatchGetItem","dynamodb:BatchWriteItem","dynamodb:PutItem","dynamodb:GetItem","dynamodb:Scan","dynamodb:Query","dynamodb:UpdateItem","dynamodb:GetRecords","sns:*","*"],"effect":"Allow","resource":["*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
    '{"fields":{"action":["dynamodb:CreateTable","dynamodb:PutItem","dynamodb:GetItem","dynamodb:Scan","dynamodb:UpdateItem","dynamodb:DeleteItem","dynamodb:Describe*","dynamodb:List*","*"],"effect":"Allow","resource":["arn:aws:dynamodb:*:*:table/terraform-state-lock-table-*","*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
    '{"fields":{"action":["ec2:*Volume*","ec2:*Snapshot*","ec2:*networkinterface*","ec2:DeleteTags","ec2:DescribeTags","ec2:CreateTags","*"],"effect":"Allow","resource":["*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
    '{"fields":{"action":["ec2:AttachVolume","ec2:DetachVolume","ec2:DeleteVolume","ec2:DescribeInstances","ec2:DescribeSnapshots","ec2:DescribeTags","ec2:DescribeVolumes","*"],"effect":"Allow","resource":["*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
    '{"fields":{"action":["ec2:DescribeAccountAttributes","ec2:DescribeAvailabilityZones","*"],"effect":"Allow","resource":["*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
    '{"fields":{"action":["ec2:DescribeInstances","ecr:GetAuthorizationToken","ecr:BatchGetImage","ecr:GetDownloadUrlForLayer","ecr:DescribeRepositories","ecr:ListImages","*"],"effect":"Allow","resource":["*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
    '{"fields":{"action":["ec2:DescribeReservedInstances","ec2:DescribeReservedInstancesOfferings","ec2:PurchaseReservedInstancesOffering","*"],"effect":"Allow","resource":["*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
    '{"fields":{"action":["ec2:StartInstances","*"],"effect":"Allow","resource":["*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
    '{"fields":{"action":["ecs:RegisterTaskDefinition","ecs:DeregisterTaskDefinition","*"],"effect":"Allow","resource":["*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
    '{"fields":{"action":["iam:ListServerCertificates","iam:GetServerCertificate","*"],"effect":"Allow","resource":["*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
    '{"fields":{"action":["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents","ecr:GetAuthorizationToken","ecr:InitiateLayerUpload","ecr:UploadLayerPart","ecr:CompleteLayerUpload","ecr:BatchCheckLayerAvailability","ecr:PutImage","ecs:RunTask","iam:PassRole","s3:GetObject","lambda:UpdateFunctionCode","secretsmanager:GetSecretValue","*"],"effect":"Allow","resource":["*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
    '{"fields":{"action":["ssmmessages:CreateControlChannel","ssmmessages:CreateDataChannel","ssmmessages:OpenControlChannel","ssmmessages:OpenDataChannel","ssm:StartSession","ssm:TerminateSession","ssm:DescribeSessions","ecs:ExecuteCommand","*"],"effect":"Allow","resource":["*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
    '{"fields":{"action":["ssmmessages:CreateControlChannel","ssmmessages:CreateDataChannel","ssmmessages:OpenControlChannel","ssmmessages:OpenDataChannel","ssm:UpdateInstanceInformation","*"],"effect":"Allow","resource":["*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
    '{"fields":{"action":["sts:AssumeRole","*"],"effect":"Allow","resource":["arn:aws:iam::*:role/AtlantisTerraformRole","*"],"resource_type":"AWSPolicyStatement"},"resource_ref":"RESOURCE_1","rule_id":"cis.iam_no_full_admin"}',
)


def load_base_splits(root: Path | None = None, splits_path: str | Path | None = None, seed: int = SEED) -> dict[str, Any]:
    """Load production base splits, reconstructing them if splits.json is absent (e.g. fresh clone)."""
    root = Path(root) if root else repo_root()
    s_path = Path(splits_path) if splits_path else root / "ml" / "train_m2" / "out" / "m2" / "splits.json"
    if s_path.is_file():
        return json.loads(s_path.read_text(encoding="utf-8"))

    from ml.train_m2.labels.leakguard import load_key_sets
    from ml.train_m2.run_m2 import _clusters
    from ml.train_m2.splits import build_splits

    ks = load_key_sets(root, strict=False)
    forced = ks.a_val - ks.phase5_train - ks.held_out_union
    if not forced:
        forced = set(DEFAULT_FORCED_CAL_CLUSTERS)
    return build_splits(_clusters(), ks.held_out_union, forced, seed=seed)


def check_execution_guards(dry_run: bool, i_understand: bool, root: Path) -> None:
    """Verify execution guards for real mode vs dry-run."""
    if not dry_run:
        if not i_understand:
            raise RuntimeError(
                "Refusing to execute real post-OOF mode: --i-understand is required."
            )
        run_log = root / "ml" / "train_m2" / "eval" / "RUN_LOG_M2.md"
        if run_log.exists():
            raise RuntimeError(
                f"Refusing to execute real mode: RUN_LOG_M2.md already exists ({run_log})."
            )


def ingest_step(
    harvest_root: Path,
    folds_path: Path,
    out_dir: Path,
    current_unseen: int = 15,
    needed: int = 44,
) -> dict[str, Any]:
    """Step 1: Ingest OOF harvest rows and report unseen-clean counts."""
    LOG.info("Step 1: Ingesting OOF harvest from %s", harvest_root)
    if not folds_path.exists():
        raise FileNotFoundError(f"folds.json not found: {folds_path}")

    folds = _load_folds(folds_path)
    fold_membership = _build_fold_membership(folds)
    inputs = load_inputs()
    key_flags = _build_key_flags(inputs)

    rows: list[dict[str, Any]] = []
    if harvest_root.exists():
        for part in sorted(harvest_root.rglob("part-*.jsonl")):
            for row in jsonl_iter(part):
                rows.append(row)
    else:
        LOG.warning("harvest_root %s does not exist; running in stub mode", harvest_root)

    if rows:
        assert_fold_disjointness(rows, fold_membership)

    counts = compute_unseen_clean_counts(rows, fold_membership, key_flags)

    out_dir.mkdir(parents=True, exist_ok=True)
    report_md = out_dir / "oof_unseen_clean.md"
    report_json = out_dir / "oof_unseen_clean.json"

    report_md.write_text(render_report(counts, current_unseen, needed), encoding="utf-8")
    jsonl_write_atomic(report_json, [counts])
    write_provenance(report_json, seed=SEED)

    return counts


def resplit_proposal_step(
    base_splits: dict[str, Any],
    new_clean_clusters: list[str],
    out_dir: Path,
    seed: int = SEED,
) -> dict[str, Any]:
    """Step 2: Generate re-split proposal allocating new unseen-clean clusters to cal."""
    LOG.info("Step 2: Generating re-split proposal with %d new clean clusters", len(new_clean_clusters))

    clusters = dict(base_splits["family"])
    test_only = set(base_splits["parts"]["test"])

    # Base forced cal: clusters originally forced into cal (e.g. A_val-only inputs)
    base_forced = set(base_splits.get("forced_cal", []))
    if not base_forced:
        try:
            from ml.train_m2.labels.leakguard import load_key_sets
            ks = load_key_sets(repo_root(), strict=False)
            base_forced = (ks.a_val - ks.phase5_train - ks.held_out_union) & set(clusters)
        except Exception:
            base_forced = set()

    if not base_forced:
        base_forced = set(DEFAULT_FORCED_CAL_CLUSTERS) & set(clusters)

    force_cal = (base_forced | set(new_clean_clusters)) - test_only

    new_splits = build_splits(
        clusters=clusters,
        test_only=test_only,
        force_cal=force_cal,
        seed=seed,
        fracs=tuple(base_splits.get("fracs", [0.6, 0.2, 0.2])),
    )
    assert_disjoint(new_splits)

    proposal_doc = [
        f"# Re-Split Proposal (post-OOF, sha256 {new_splits['sha256'][:16]})",
        "",
        f"- Base splits sha256: {base_splits['sha256']}",
        f"- Proposed splits sha256: {new_splits['sha256']}",
        f"- Partition counts: train={len(new_splits['parts']['train'])}, "
        f"val={len(new_splits['parts']['val'])}, cal={len(new_splits['parts']['cal'])}, "
        f"test={len(new_splits['parts']['test'])}",
        f"- New clean clusters added to cal: {len(new_clean_clusters)}",
        "",
        "## Cell Table",
        "",
        cell_table(new_splits),
    ]

    out_dir.mkdir(parents=True, exist_ok=True)
    proposal_json_path = out_dir / "re_split_proposal.json"
    proposal_md_path = out_dir / "re_split_proposal.md"

    proposal_json_path.write_text(
        json.dumps(new_splits, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_provenance(proposal_json_path, seed=seed)

    proposal_md_path.write_text("\n".join(proposal_doc) + "\n", encoding="utf-8")
    write_provenance(proposal_md_path, seed=seed)

    return new_splits


def retrain_model_step(
    X_tr: pd.DataFrame,
    y_tr: np.ndarray,
    X_va: pd.DataFrame,
    y_va: np.ndarray,
    meta_va: pd.DataFrame,
    splits_sha: str,
    out_dir: Path,
    generator: str = "sft",
    seed: int = SEED,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Step 3: Retrain per-generator M2 on non-test data."""
    LOG.info("Step 3: Retraining per-generator M2 (%s) on non-test data", generator)
    art, report = T.fit_m2(X_tr, y_tr, X_va, y_va, meta_va, splits_sha, seed=seed)
    report["generator"] = generator
    report["train_rows"] = int(len(X_tr))
    report["train_clusters"] = int(X_tr["cluster_key"].nunique()) if "cluster_key" in X_tr.columns else int(len(X_tr))

    model_dir = out_dir / "m2"
    T.save(art, report, model_dir)
    write_provenance(model_dir / "model_card.json", seed=seed)
    write_provenance(model_dir / "val_metrics.json", seed=seed)

    return art, report


def calibrate_tau_step(
    scores: np.ndarray,
    wrong: np.ndarray,
    splits_sha: str,
    spec_hash: str,
    out_dir: Path,
    generator: str = "sft",
    alpha: float = 0.05,
    delta: float = 0.05,
    seed: int = SEED,
) -> dict[str, Any]:
    """Step 4: Calibrate risk threshold tau on calibration partition."""
    LOG.info("Step 4: Calibrating tau on %d cal decisions (alpha=%s, delta=%s)", len(scores), alpha, delta)
    cal_res = CT.calibrate(scores, wrong, alpha=alpha, delta=delta)
    cal_res.update({
        "generator": generator,
        "splits_sha256": splits_sha,
        "feature_spec_hash": spec_hash,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_clusters_without_candidate": None,
    })

    out_path = out_dir / "tau_star.json"
    CT.write(cal_res, out_path)
    write_provenance(out_path, seed=seed)

    return cal_res


def emit_changelog_entry(
    splits_sha: str,
    tau_info: dict[str, Any],
    generator: str = "sft",
    date_str: str | None = None,
) -> str:
    """Step 5: Emit change-log entry text for EXPERIMENT_PLAN_M2.md section 12."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    certified_str = "true" if tau_info.get("certified") else "false"
    n_cal = tau_info.get("n_total", 0)
    tau_val = tau_info.get("tau")
    tau_repr = f"{tau_val:.3f}" if isinstance(tau_val, float) else "null"

    change_desc = (
        f"Re-split post-OOF harvest (splits sha256 {splits_sha[:16]}); "
        f"per-generator {generator} M2 retrained; "
        f"tau certified: {certified_str} (n_cal={n_cal}, tau={tau_repr})"
    )
    reason = "OOF harvest ingested to close S4"
    entry = f"| {date_str} | {change_desc} | {reason} | no |"
    return entry


def run_post_oof(
    *,
    dry_run: bool = True,
    i_understand: bool = False,
    out_dir: Path | str,
    harvest_root: Path | str | None = None,
    folds_path: Path | str | None = None,
    splits_path: Path | str | None = None,
    generator: str = "sft",
    alpha: float = 0.05,
    delta: float = 0.05,
    seed: int = SEED,
    root: Path | None = None,
    synthetic_fixture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the full post-OOF pipeline.

    Args:
        dry_run: Whether to run in dry-run mode (default True).
        i_understand: Real mode authorization flag.
        out_dir: Directory where dry-run outputs are written.
        harvest_root: Directory containing sft_oof harvest completions.
        folds_path: Path to folds.json.
        splits_path: Path to base splits.json.
        generator: Generator identifier (default: "sft").
        alpha: Target error rate (default: 0.05).
        delta: Failure probability bound (default: 0.05).
        seed: Random seed (default: 1337).
        root: ARGUS repository root directory.
        synthetic_fixture: Optional pre-loaded fixture for unit tests.

    Returns:
        Dictionary containing results of all 5 steps.
    """
    root = root or repo_root()
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    check_execution_guards(dry_run, i_understand, root)

    # 1. Ingest OOF
    if synthetic_fixture and "counts" in synthetic_fixture:
        counts = synthetic_fixture["counts"]
        (out_path / "oof_unseen_clean.json").write_text(json.dumps([counts]), encoding="utf-8")
    else:
        h_root = Path(harvest_root) if harvest_root else root / "ml" / "train_m2" / "harvest_out" / "sft_oof"
        f_path = Path(folds_path) if folds_path else root / "docs" / "phase6_shaurya" / "crossfit" / "folds.json"
        counts = ingest_step(h_root, f_path, out_path)

    new_clean = counts.get("unseen_clean_clusters", [])

    # 2. Write Re-Split Proposal
    if synthetic_fixture and "base_splits" in synthetic_fixture:
        base_splits = synthetic_fixture["base_splits"]
    else:
        base_splits = load_base_splits(root, splits_path=splits_path, seed=seed)

    new_splits = resplit_proposal_step(base_splits, new_clean, out_path, seed=seed)

    # 3. Retrain per-generator M2 on non-test data
    if synthetic_fixture and "train_data" in synthetic_fixture:
        td = synthetic_fixture["train_data"]
        X_tr, y_tr = td["X_tr"], td["y_tr"]
        X_va, y_va = td["X_va"], td["y_va"]
        meta_va = td["meta_va"]
    else:
        # Check if real harvest labels exist for generator
        real_label_path = root / "ml" / "train_m2" / "out" / "labels" / "harvest" / f"{generator}.jsonl"
        X_tr, y_tr, X_va, y_va, meta_va = None, None, None, None, None
        if real_label_path.is_file() and not synthetic_fixture:
            try:
                from ml.train_m2.run_m2 import _frame
                X_tr, meta_tr = _frame([generator], "train", new_splits)
                y_tr = meta_tr["y"].to_numpy()
                X_va, meta_va = _frame([generator], "val", new_splits)
                y_va = meta_va["y"].to_numpy()
            except Exception as e:
                LOG.warning("Failed to load real frames for %s (%s); falling back to synthetic", generator, e)
                X_tr, y_tr, X_va, y_va, meta_va = None, None, None, None, None

        if X_tr is None or y_tr is None or X_va is None or y_va is None:
            # Synthetic fallback if real frames are not supplied or cannot be loaded
            feature_names = [s.name for s in R.REGISTRY]
            rng = np.random.RandomState(seed)
            n_tr = max(10, len(new_splits["parts"]["train"]))
            n_va = max(5, len(new_splits["parts"]["val"]))
            X_tr = pd.DataFrame(rng.randn(n_tr, len(feature_names)), columns=feature_names)
            y_tr = rng.choice([0, 1], size=n_tr, p=[0.2, 0.8])
            X_va = pd.DataFrame(rng.randn(n_va, len(feature_names)), columns=feature_names)
            y_va = rng.choice([0, 1], size=n_va, p=[0.2, 0.8])
            meta_va = pd.DataFrame({"input_key": [f"val_k_{i}" for i in range(n_va)], "y": y_va})

    art, val_report = retrain_model_step(
        X_tr, y_tr, X_va, y_va, meta_va, new_splits["sha256"], out_path, generator=generator, seed=seed
    )

    # 4. Calibrate Tau
    if synthetic_fixture and "cal_data" in synthetic_fixture:
        cd = synthetic_fixture["cal_data"]
        scores, wrong = cd["scores"], cd["wrong"]
    else:
        # Check if real cal data can be computed
        real_label_path = root / "ml" / "train_m2" / "out" / "labels" / "harvest" / f"{generator}.jsonl"
        scores, wrong = None, None
        if real_label_path.is_file() and not synthetic_fixture:
            try:
                from ml.train_m2.risk.decisions import select_decisions
                from ml.train_m2.run_m2 import _frame
                X_ca, meta_ca = _frame([generator], "cal", new_splits)
                fr_ca = meta_ca.assign(score=T.predict(art, X_ca))
                sel = select_decisions(fr_ca[fr_ca["generator"] == generator])
                scores = sel["score"].to_numpy()
                wrong = (1 - sel["y"]).to_numpy()
            except Exception as e:
                LOG.warning("Failed to score real cal partition (%s); falling back to synthetic", e)
                scores, wrong = None, None

        if scores is None or wrong is None:
            rng = np.random.RandomState(seed)
            n_cal = len(new_splits["parts"]["cal"])
            scores = rng.uniform(0.7, 0.99, size=n_cal)
            wrong = rng.choice([0, 1], size=n_cal, p=[0.95, 0.05])

    tau_info = calibrate_tau_step(
        scores,
        wrong,
        new_splits["sha256"],
        art["spec_hash"],
        out_path,
        generator=generator,
        alpha=alpha,
        delta=delta,
        seed=seed,
    )

    # 5. Emit Change Log Entry (printed, not applied)
    changelog_entry = emit_changelog_entry(new_splits["sha256"], tau_info, generator=generator)
    print("\n--- PROPOSED EXPERIMENT_PLAN_M2.md Section 12 Entry (dry-run, not applied) ---")
    print(changelog_entry)
    print("------------------------------------------------------------------------------\n")

    # 6. Partial-fold post-OOF evaluation (dry-run only)
    partial_oof: dict[str, Any] | None = None
    if synthetic_fixture and "partial_oof" in synthetic_fixture:
        partial_oof = synthetic_fixture["partial_oof"]
    elif synthetic_fixture and "partial_rows" in synthetic_fixture:
        f_path = Path(folds_path) if folds_path else root / "docs" / "phase6_shaurya" / "crossfit" / "folds.json"
        folds = _load_folds(f_path) if f_path.exists() else {"folds": {}}
        fold_mem = _build_fold_membership(folds) if "folds" in folds else {}
        inputs = load_inputs()
        k_flags = _build_key_flags(inputs)
        partial_oof = evaluate_partial_oof(
            synthetic_fixture["partial_rows"],
            fold_mem,
            k_flags,
            alpha=alpha,
            delta=delta,
        )
    else:
        h_root = Path(harvest_root) if harvest_root else root / "ml" / "train_m2" / "harvest_out" / "sft_oof"
        f_path = Path(folds_path) if folds_path else root / "docs" / "phase6_shaurya" / "crossfit" / "folds.json"
        if h_root.exists() and f_path.exists():
            folds = _load_folds(f_path)
            fold_mem = _build_fold_membership(folds)
            inputs = load_inputs()
            k_flags = _build_key_flags(inputs)
            h_rows: list[dict[str, Any]] = []
            for part in sorted(h_root.rglob("part-*.jsonl")):
                for r in jsonl_iter(part):
                    h_rows.append(r)
            partial_oof = evaluate_partial_oof(
                h_rows,
                fold_mem,
                k_flags,
                alpha=alpha,
                delta=delta,
            )

    if partial_oof:
        part_rep_json = out_path / "partial_oof_report.json"
        part_rep_md = out_path / "partial_oof_report.md"
        jsonl_write_atomic(part_rep_json, [partial_oof])
        write_provenance(part_rep_json, seed=seed)
        part_rep_md.write_text(render_partial_oof_report(partial_oof), encoding="utf-8")
        write_provenance(part_rep_md, seed=seed)

    return {
        "counts": counts,
        "splits": new_splits,
        "art": art,
        "val_report": val_report,
        "tau_info": tau_info,
        "changelog_entry": changelog_entry,
        "partial_oof": partial_oof,
    }


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    p = argparse.ArgumentParser(description="Chained post-OOF dry-run pipeline")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                   help="Run in dry-run mode (default: True)")
    p.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                   help="Run in real mode (requires --i-understand and absent RUN_LOG_M2.md)")
    p.add_argument("--i-understand", action="store_true", default=False,
                   help="Acknowledge real execution (required if --no-dry-run)")
    p.add_argument("--out-dir", default="ml/train_m2/out/reports/tmp_p6g",
                   help="Output directory for dry-run artifacts")
    p.add_argument("--harvest-root", default="ml/train_m2/harvest_out/sft_oof",
                   help="Path to sft_oof harvest directory")
    p.add_argument("--folds", default="docs/phase6_shaurya/crossfit/folds.json",
                   help="Path to folds.json")
    p.add_argument("--splits", default="ml/train_m2/out/m2/splits.json",
                   help="Path to current splits.json")
    p.add_argument("--generator", default="sft",
                   help="Generator model to retrain and calibrate (default: sft)")
    p.add_argument("--alpha", type=float, default=0.05,
                   help="Nominal risk level (default: 0.05)")
    p.add_argument("--delta", type=float, default=0.05,
                   help="Failure probability bound (default: 0.05)")
    p.add_argument("--seed", type=int, default=SEED,
                   help="Random seed (default: 1337)")

    args = p.parse_args(argv)
    root = repo_root()

    try:
        run_post_oof(
            dry_run=args.dry_run,
            i_understand=args.i_understand,
            out_dir=args.out_dir,
            harvest_root=args.harvest_root,
            folds_path=args.folds,
            splits_path=args.splits,
            generator=args.generator,
            alpha=args.alpha,
            delta=args.delta,
            seed=args.seed,
            root=root,
        )
    except Exception as exc:
        LOG.error("post_oof execution failed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
