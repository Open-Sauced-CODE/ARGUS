"""Phase 6 harvest labeler: scores and labels harvest_out rows via the FROZEN Phase 5 scorer.

F6 fix: labels all harvest rows (zeroshot, sft, rft, rft_v2; profile A; all 321 inputs).

Contract
--------
label_harvest(generator, root, ref_map, hi_map, partition_sets, out_dir, seed) -> dict
    Writes ml/train_m2/out/labels/harvest/<generator>.jsonl + provenance.
    Returns stats dict.

Notes
-----
- Scores each harvest row's content JSON with the FROZEN ml.train_m1.eval.score.score_inputs.
- Uses the harvest input record's own finding_id (never an A_val/train example).
- route: uses ref_map route when a reference exists; else None (escalate-only bypass M2).
- counterfactual oracle result (cf_class) computed for rows without a reference.
- strict_correct from counterfactual when no reference exists.
- Temp dir used for OPA; deleted after.
- Wall time reported.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from ml.train_m2.common import (
    jsonl_iter,
    jsonl_write_atomic,
    load_inputs,
    repo_root,
    write_provenance,
)
from ml.train_m2.labels.oracle import (
    ESC_RULE_IDS,
    SRC_SCORED_LOG,
    label_candidate,
)
from ml.train_m2.labels.partitions import build_partition_flags, load_partition_sets

LOG = logging.getLogger(__name__)

HARVEST_GENERATORS = ("zeroshot", "sft", "rft", "rft_v2")
HARVEST_PROFILE = "A"


def _iter_harvest_rows(
    root: Path,
    generator: str,
    profile: str = HARVEST_PROFILE,
) -> list[dict]:
    """Load all harvest rows for a generator/profile; sorted by (input_key, sample_idx)."""
    harvest_dir = root / "ml" / "train_m2" / "harvest_out" / generator / profile
    if not harvest_dir.exists():
        LOG.warning("Harvest dir missing: %s", harvest_dir)
        return []
    rows = []
    for part_file in sorted(harvest_dir.glob("part-*.jsonl")):
        for row in jsonl_iter(part_file):
            rows.append(row)
    rows.sort(key=lambda r: (r.get("input_key", ""), r.get("sample_idx", 0)))
    return rows


def label_harvest(
    generator: str,
    root: Path,
    ref_map: dict[str, dict],
    hi_map: dict[str, dict],
    partition_sets: dict[str, set[str]],
    out_dir: Path,
    seed: int = 1337,
) -> dict[str, Any]:
    """Score and label all harvest rows for one generator.

    Returns a stats dict with counts per category.
    """
    from ml.train_m1.eval.score import score_inputs  # FROZEN scorer

    t0 = time.time()
    harvest_rows = _iter_harvest_rows(root, generator)
    if not harvest_rows:
        LOG.warning("No harvest rows for generator %s", generator)
        return {}

    # Group by input_key so we can score all samples together (efficient OPA batching)
    by_input: dict[str, list[dict]] = defaultdict(list)
    for row in harvest_rows:
        ik = row.get("input_key", "")
        by_input[ik].append(row)

    labeled_rows: list[dict] = []
    stats: dict[str, Any] = {
        "rows": 0,
        "gate_pass": 0,
        "strict_correct_true": 0,
        "strict_correct_false": 0,
        "strict_correct_none": 0,
        "oracle_class_counts": defaultdict(int),
        "nat_neg_clusters": set(),
        # Restricted to generator_seen == False AND heldout_sets == []
        "restricted_rows": 0,
        "restricted_gate_pass": 0,
        "restricted_sc_true": 0,
        "restricted_sc_false": 0,
        "restricted_sc_none": 0,
        "restricted_oracle_class_counts": defaultdict(int),
        "nat_neg_clusters_unseen_unheldout": set(),
        "greedy_gate_pass": 0,
        "greedy_total": 0,
    }

    # CF oracle (lazy-loaded per rule_id)
    cf_oracles: dict[str, Any] = {}

    # Prepare batch score items for all inputs (FROZEN scorer efficient batching)
    ordered_keys = [ik for ik in sorted(by_input.keys()) if hi_map.get(ik) is not None]
    score_items: list[dict] = []
    item_metadata: list[tuple] = []
    for ik in ordered_keys:
        samples = sorted(by_input[ik], key=lambda r: r.get("sample_idx", 0))
        record = hi_map[ik]
        ref_entry = ref_map.get(ik, {})
        reference = ref_entry.get("reference")
        if reference is not None:
            route = ref_entry.get("route", "fix")
        else:
            rule_id = record.get("rule_id", "")
            route = "escalate" if rule_id in ESC_RULE_IDS else None
        contents = [r.get("content", "") for r in samples]
        score_items.append({
            "record": record,
            "route": route or "fix",
            "reference": reference,
            "contents": contents,
        })
        item_metadata.append((ik, samples, record, reference, route))

    try:
        all_score_results = score_inputs(score_items)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("batch score_inputs failed: %s; falling back per-item", exc)
        all_score_results = [score_inputs([it])[0] for it in score_items]

    for (ik, samples, record, reference, route), score_res in zip(item_metadata, all_score_results):
        partition_flags = build_partition_flags(ik, generator, partition_sets)
        scored_candidates = score_res.get("candidates", [])

        for sample_row, scored_cand in zip(samples, scored_candidates):
            sample_idx = sample_row.get("sample_idx", 0)
            content = sample_row.get("content", "")
            source_file = (
                "ml/train_m2/harvest_out/"
                + generator + "/" + HARVEST_PROFILE + "/<part>"
            )

            try:
                patch = json.loads(content) if content.strip() else None
            except (json.JSONDecodeError, AttributeError):
                patch = None

            # CF oracle for rows without reference
            cf_class: str | None = None
            if reference is None and route is None:
                # escalate-only: bypass M2
                cf_class = "escalated_ok" if route == "escalate" else None
            elif reference is None and patch is not None and scored_cand.get("gate_passed"):
                rule_id = record.get("rule_id", "")
                if rule_id not in cf_oracles:
                    try:
                        from ml.train_m2.labels.counterfactual import CounterfactualOracle
                        cf_oracles[rule_id] = CounterfactualOracle(rule_id)
                    except Exception:  # noqa: BLE001
                        cf_oracles[rule_id] = None
                cf_oracle = cf_oracles.get(rule_id)
                if cf_oracle is not None:
                    try:
                        cf_result = cf_oracle.classify(record, patch)
                        cf_class = cf_result.label
                    except Exception:  # noqa: BLE001
                        cf_class = "unknown"

            label_row = label_candidate(
                record=record,
                patch=patch,
                reference=reference,
                route=route or "fix",
                scored=scored_cand,
                source=SRC_SCORED_LOG,
                source_file=source_file,
                generator=generator,
                profile=HARVEST_PROFILE,
                sample_idx=sample_idx,
                input_key=ik,
            )

            # For no-reference rows: override strict_correct from CF
            row_dict = label_row.to_dict()
            row_dict["cf_class"] = cf_class
            if reference is None and cf_class is not None:
                # strict_correct from counterfactual when no reference
                row_dict["strict_correct"] = cf_class in ("minimal_correct", "valid_not_minimal")

            row_dict["train_only"] = False
            row_dict["patch_ops"] = (patch or {}).get("ops", [])
            row_dict["candidate_set"] = "harvest"
            row_dict.update(partition_flags)

            labeled_rows.append(row_dict)

            # Stats
            is_unseen_unheld = (not partition_flags["generator_seen"]) and (not partition_flags["heldout_sets"])
            stats["rows"] += 1
            if sample_idx == 0:
                stats["greedy_total"] += 1
                if label_row.gate_pass:
                    stats["greedy_gate_pass"] += 1

            if is_unseen_unheld:
                stats["restricted_rows"] += 1

            if label_row.gate_pass:
                stats["gate_pass"] += 1
                if is_unseen_unheld:
                    stats["restricted_gate_pass"] += 1

                if label_row.oracle_class in ("wrong", "valid_not_minimal"):
                    stats["nat_neg_clusters"].add(ik)
                    if is_unseen_unheld:
                        stats["nat_neg_clusters_unseen_unheldout"].add(ik)

            sc = row_dict.get("strict_correct")
            if sc is True:
                stats["strict_correct_true"] += 1
                if is_unseen_unheld:
                    stats["restricted_sc_true"] += 1
            elif sc is False:
                stats["strict_correct_false"] += 1
                if is_unseen_unheld:
                    stats["restricted_sc_false"] += 1
            else:
                stats["strict_correct_none"] += 1
                if is_unseen_unheld:
                    stats["restricted_sc_none"] += 1

            stats["oracle_class_counts"][label_row.oracle_class] += 1
            if is_unseen_unheld:
                stats["restricted_oracle_class_counts"][label_row.oracle_class] += 1

    # Write output
    harvest_out_dir = out_dir / "harvest"
    harvest_out_dir.mkdir(parents=True, exist_ok=True)
    out_path = harvest_out_dir / f"{generator}.jsonl"
    jsonl_write_atomic(out_path, labeled_rows)

    elapsed = time.time() - t0
    LOG.info("Harvest labeling for %s: %d rows, %.1fs", generator, len(labeled_rows), elapsed)

    # Provenance
    harvest_dir = root / "ml" / "train_m2" / "harvest_out" / generator / HARVEST_PROFILE
    input_files = sorted(harvest_dir.glob("part-*.jsonl")) if harvest_dir.exists() else []
    input_files.append(root / "ml" / "train_m2" / "contract" / "harvest_inputs.jsonl")
    write_provenance(
        out_path,
        inputs=[p for p in input_files if p.exists()],
        seed=seed,
        extra={
            "generator": generator,
            "profile": HARVEST_PROFILE,
            "wall_time_s": round(elapsed, 2),
        },
    )

    # Finalize stats
    stats["nat_neg_clusters"] = len(stats["nat_neg_clusters"])
    stats["nat_neg_clusters_unseen_unheldout"] = len(stats["nat_neg_clusters_unseen_unheldout"])
    stats["oracle_class_counts"] = dict(stats["oracle_class_counts"])
    stats["restricted_oracle_class_counts"] = dict(stats["restricted_oracle_class_counts"])
    stats["wall_time_s"] = round(elapsed, 2)

    return stats


def compare_harvest_with_phase5_greedy(
    generator: str,
    harvest_stats: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    """Compare harvest greedy gate-pass rate on 321 inputs with Phase 5 candidate logs."""
    from ml.train_m2.common import jsonl_iter

    p5_greedy_pass = 0
    p5_greedy_total = 0
    runs_dir = root / "ml" / "train_m1" / "eval" / "runs" / generator

    # Read all Phase 5 candidate logs for this generator
    if runs_dir.exists():
        seen_p5_keys = set()
        for cand_file in runs_dir.glob("*.candidates.jsonl"):
            for row in jsonl_iter(cand_file):
                ik = row.get("input_key")
                if ik and ik not in seen_p5_keys:
                    seen_p5_keys.add(ik)
                    cands = row.get("scored", {}).get("candidates", [])
                    if cands:
                        p5_greedy_total += 1
                        if cands[0].get("gate_passed"):
                            p5_greedy_pass += 1

    h_pass = harvest_stats.get("greedy_gate_pass", 0)
    h_tot = harvest_stats.get("greedy_total", 0)
    h_rate = h_pass / h_tot if h_tot else 0.0
    p5_rate = p5_greedy_pass / p5_greedy_total if p5_greedy_total else 0.0
    diff = h_rate - p5_rate

    print(f"\n[{generator}] Greedy gate-pass comparison on 321 inputs:")
    print(f"  Harvest greedy gate-pass: {h_pass}/{h_tot} ({h_rate:.3%})")
    print(f"  Phase 5 greedy gate-pass: {p5_greedy_pass}/{p5_greedy_total} ({p5_rate:.3%})")
    print(f"  Difference: {diff:+.3%} (due to Ollama client sampling, presence_penalty, and finding_id normalization)")

    return {
        "harvest_rate": h_rate,
        "phase5_rate": p5_rate,
        "diff": diff,
    }


def print_harvest_summary(generator: str, stats: dict[str, Any]) -> None:
    """Print per-generator harvest label summary (all and restricted)."""
    if not stats:
        print(f"[{generator}] No harvest stats.")
        return
    print(f"\n=== [{generator}] HARVEST LABEL SUMMARY ===")
    print("  [ALL ROWS]")
    print(f"    rows          : {stats.get('rows', 0)}")
    print(f"    gate_pass     : {stats.get('gate_pass', 0)}")
    print(f"    strict_correct: True={stats.get('strict_correct_true', 0)}"
          f"  False={stats.get('strict_correct_false', 0)}"
          f"  None={stats.get('strict_correct_none', 0)}")
    print(f"    oracle_classes: {stats.get('oracle_class_counts', {})}")
    print(f"    nat_neg_clusters (all): {stats.get('nat_neg_clusters', 0)}")

    print("  [RESTRICTED: generator_seen=False AND heldout_sets=[]]")
    print(f"    restricted_rows          : {stats.get('restricted_rows', 0)}")
    print(f"    restricted_gate_pass     : {stats.get('restricted_gate_pass', 0)}")
    print(f"    restricted_strict_correct: True={stats.get('restricted_sc_true', 0)}"
          f"  False={stats.get('restricted_sc_false', 0)}"
          f"  None={stats.get('restricted_sc_none', 0)}")
    print(f"    restricted_oracle_classes: {stats.get('restricted_oracle_class_counts', {})}")
    print(f"    restricted_nat_neg_clusters: {stats.get('nat_neg_clusters_unseen_unheldout', 0)}")
    print(f"  Wall time: {stats.get('wall_time_s', '?')}s")


if __name__ == "__main__":
    import argparse
    from ml.train_m2.labels.build_labels import _load_harvest_inputs_map, _load_reference_map

    parser = argparse.ArgumentParser(description="Label all harvest files (P3b F6)")
    parser.add_argument("--out-dir", default="ml/train_m2/out/labels")
    parser.add_argument("--generators", nargs="+", default=list(HARVEST_GENERATORS))
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()

    root = repo_root()
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    hi_map = _load_harvest_inputs_map(root)
    ref_map = _load_reference_map(root)
    partition_sets = load_partition_sets()

    all_stats = {}
    for gen in args.generators:
        stats = label_harvest(
            generator=gen,
            root=root,
            ref_map=ref_map,
            hi_map=hi_map,
            partition_sets=partition_sets,
            out_dir=out_dir,
            seed=args.seed,
        )
        print_harvest_summary(gen, stats)
        compare_harvest_with_phase5_greedy(gen, stats, root)
        all_stats[gen] = stats


