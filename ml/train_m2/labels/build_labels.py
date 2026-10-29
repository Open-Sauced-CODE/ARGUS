"""Phase 6 label builder (P3b): joins candidates with oracle labels -> per-generator JSONL files.

P3b fixes applied
-----------------
F1  compute_acceptance: natural and corruptor counts reported separately; bar is gate-passing-and-wrong
    rows (natural + corruptor); natural-cluster threshold (59) checked separately.
F2  Type filter: only corruption types with hard_negative_rate > 0 kept; others written to the
    hard_negative_table.md with a 'dropped' section.
F3  Corruptor seed: uses hashlib.sha256(f"{seed}:{ik}:{ctype}") not python hash(ik) (fixed in
    corruptor.py -> make_corrupted_rows).
F4  All Phase 5 candidate sets labeled (A_val, train300, B1, B2, C_verifier, gold), not just A_val.
    Held-out rows carry heldout_sets non-empty; never used in statistics for choices.
F5  Corruptor seeds: only inputs with in_phase5_train AND heldout_sets empty AND NOT in_a_val.
F6  Harvest labels written to ml/train_m2/out/labels/harvest/<generator>.jsonl.
F7  hard_negative_stats excludes 'unknown' from wrong (fixed in corruptor.py).
F9  valid_not_minimal is reported separately in acceptance accounting.

CLI
---
    py -m ml.train_m2.labels.build_labels [--out-dir ml/train_m2/out/labels] [--seed 1337]
    py -m ml.train_m2.labels.build_labels --help

Hard rules:
  - Statistical unit is the CLUSTER (input_key); never rows.
  - Corrupted rows capped at 35% of TRAIN-eligible natural + corruptor rows.
  - Corrupted rows marked train_only=True.
  - Held-out rows labeled but never used in statistics for model/threshold choices.
  - Every output carries a provenance JSON.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

from ml.train_m2.common import (
    cluster_key,
    jsonl_iter,
    jsonl_write_atomic,
    load_inputs,
    provenance,
    repo_root,
    set_seed,
    sha256_file,
    write_provenance,
)
from ml.train_m2.labels.corruptor import (
    filter_hard_negative_types,
    hard_negative_stats,
    make_corrupted_rows,
    write_hard_negative_table,
)
from ml.train_m2.labels.oracle import (
    ESC_RULE_IDS,
    LabelRow,
    SRC_SCORED_LOG,
    label_candidate,
)
from ml.train_m2.labels.partitions import (
    HELD_OUT_SET_NAMES,
    build_partition_flags,
    corruptor_seed_partition,
    load_partition_sets,
)

LOG = logging.getLogger(__name__)

GENERATORS = ("zeroshot", "sft", "rft")
HARVEST_GENERATORS = ("zeroshot", "sft", "rft", "rft_v2")

# All Phase 5 candidate sets
ALL_CANDIDATE_SETS = ("A_val", "train300", "B1", "B2", "C_verifier", "gold")

RUNS_RELPATH = Path("ml") / "train_m1" / "eval" / "runs"
DATASET_PATHS = (
    Path("ml") / "mutation_engine" / "dataset" / "train.jsonl",
    Path("ml") / "mutation_engine" / "dataset" / "val.jsonl",
)
CORRUPT_CAP_FRAC = 0.35

# Expected natural-negative clusters per spec
EXPECTED_NEG_CLUSTERS = {"zeroshot": 21, "sft": 4, "rft": 1}
EXPECTED_UNION = 22

# Pre-registered bar
BAR_TOTAL_NEGATIVES = 300
NATURAL_CLUSTER_THRESHOLD = 59


def _load_reference_map(root: Path) -> dict[str, dict]:
    """Build input_key -> {record, reference, route} from training and val dataset files.

    Note: for F4 / F7, we use the FIRST occurrence of each input_key from train+val.
    """
    ref_map: dict[str, dict] = {}
    from ml.mutation_engine.dataset_io import input_key as _ik

    for rel in DATASET_PATHS:
        p = root / rel
        if not p.exists():
            continue
        with open(p, encoding="utf-8", newline="") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                ik = _ik(row)
                if ik not in ref_map:
                    ref_map[ik] = {
                        "record": row["input"],
                        "reference": row.get("target"),
                        "route": row["meta"].get("route", "fix"),
                    }
    return ref_map


def _load_harvest_inputs_map(root: Path) -> dict[str, dict]:
    """Build input_key -> record from harvest_inputs.jsonl."""
    hi_map: dict[str, dict] = {}
    for row in load_inputs():
        ik = row["input_key"]
        hi_map[ik] = row["record"]
    return hi_map


def _iter_phase5_log(
    root: Path, generator: str, candidate_set: str
) -> Iterator[dict[str, Any]]:
    """Yield rows from a Phase 5 candidate log file."""
    log_path = root / RUNS_RELPATH / generator / f"{candidate_set}.candidates.jsonl"
    if not log_path.exists():
        return
    try:
        source_file = log_path.relative_to(root).as_posix()
    except ValueError:
        source_file = log_path.name
    with open(log_path, encoding="utf-8", newline="") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            row["_source_file"] = source_file
            row["_candidate_set"] = candidate_set
            yield row


def build_labels_for_generator(
    generator: str,
    root: Path,
    ref_map: dict[str, dict],
    hi_map: dict[str, dict],
    partition_sets: dict[str, set[str]],
    corruptor_eligible: set[str],
    seed: int = 1337,
    corrupt_cap_frac: float = CORRUPT_CAP_FRAC,
    corruptor_cache: dict[str, list[dict]] | None = None,
) -> tuple[list[dict], dict]:
    """Build LabelRow dicts for one generator across ALL Phase 5 candidate sets.

    F4 fix: labels all sets, not just A_val.
    F5 fix: corruptor seeded only from eligible inputs (phase5_train, not a_val, not held-out).
    Held-out rows are labeled but carry heldout_sets non-empty.

    Returns (rows, stats).
    """
    set_seed(seed)

    rows: list[dict] = []
    corruptor_rows: list[dict] = []

    # Tracked for acceptance (usable = heldout_sets empty)
    nat_neg_clusters_usable: set[str] = set()
    nat_neg_clusters_all: set[str] = set()
    gate_pass_by_oc: dict[str, int] = defaultdict(int)  # oracle_class -> count (usable)
    gate_pass_by_oc_all: dict[str, int] = defaultdict(int)

    for candidate_set in ALL_CANDIDATE_SETS:
        for log_row in _iter_phase5_log(root, generator, candidate_set):
            ik = log_row.get("input_key", "")
            source_file = log_row.get("_source_file")
            contents = log_row.get("contents", [])
            scored_candidates = log_row.get("scored", {}).get("candidates", [])

            # Record from harvest_inputs (fallback to ref_map)
            record = hi_map.get(ik)
            if record is None:
                ref_entry = ref_map.get(ik, {})
                record = ref_entry.get("record")
            if record is None:
                LOG.warning("No record found for input_key %s; skipping", ik[:60])
                continue

            ref_entry = ref_map.get(ik, {})
            reference = ref_entry.get("reference")
            route = ref_entry.get("route", "fix")

            # Partition flags (F4: now covers all sets)
            pflags = build_partition_flags(ik, generator, partition_sets)
            is_heldout = bool(pflags["heldout_sets"])

            # Label each scored candidate
            for sample_idx, (content, scored_cand) in enumerate(
                zip(contents, scored_candidates)
            ):
                try:
                    patch = json.loads(content) if content.strip() else None
                except (json.JSONDecodeError, AttributeError):
                    patch = None

                label_row = label_candidate(
                    record=record,
                    patch=patch,
                    reference=reference,
                    route=route,
                    scored=scored_cand,
                    source=SRC_SCORED_LOG,
                    source_file=source_file,
                    generator=generator,
                    profile="A",
                    sample_idx=sample_idx,
                    input_key=ik,
                )

                row_dict = label_row.to_dict()
                row_dict["train_only"] = False
                row_dict["patch_ops"] = (patch or {}).get("ops", [])
                row_dict["candidate_set"] = candidate_set
                row_dict.update(pflags)
                rows.append(row_dict)

                # Track natural negatives for usable (non-held-out) rows
                if label_row.gate_pass and label_row.oracle_class in ("wrong", "valid_not_minimal"):
                    nat_neg_clusters_all.add(ik)
                    if not is_heldout:
                        nat_neg_clusters_usable.add(ik)

                # Acceptance accounting (gate-pass oracle class)
                if label_row.gate_pass:
                    gate_pass_by_oc_all[label_row.oracle_class] += 1
                    if not is_heldout:
                        gate_pass_by_oc[label_row.oracle_class] += 1

    # F5 fix: Generate corruptor rows on the 168 clean TRAIN seeds (phase5_train, not A_val, not held-out)
    corruptor_seeded_clusters: set[str] = set()
    for ik in sorted(corruptor_eligible):
        ref_entry = ref_map.get(ik, {})
        reference = ref_entry.get("reference")
        if reference is None:
            continue
        record = hi_map.get(ik) or ref_entry.get("record")
        if record is None:
            continue
        route = ref_entry.get("route", "fix")
        pflags = build_partition_flags(ik, generator, partition_sets)

        if corruptor_cache is not None and ik in corruptor_cache:
            c_rows = [copy.deepcopy(r) for r in corruptor_cache[ik]]
        else:
            c_rows = make_corrupted_rows(
                record=record,
                reference=reference,
                route=route,
                input_key=ik,
                seed=seed,
                source_file="ml/train_m1/eval/runs/zeroshot/train300.candidates.jsonl",
            )
            if corruptor_cache is not None:
                corruptor_cache[ik] = [copy.deepcopy(r) for r in c_rows]

        if c_rows:
            corruptor_seeded_clusters.add(ik)
        for cr in c_rows:
            cr["generator"] = generator
            cr["train_only"] = True
            cr["source_input_key"] = ik
            cr["candidate_set"] = "train300"
            cr.update(pflags)
        corruptor_rows.extend(c_rows)

    # Type filter (F2): compute stats on seed partition, keep only types with hard_neg_rate > 0
    pre_filter_stats = hard_negative_stats(corruptor_rows)
    kept_stats, dropped_types = filter_hard_negative_types(pre_filter_stats)
    kept_ctypes = set(kept_stats.keys())

    # Filter corruptor rows
    corruptor_rows = [r for r in corruptor_rows if r.get("corruption_type") in kept_ctypes]

    # Cap corruptor rows: cap = 35% of final TRAIN-eligible natural + corruptor rows
    # TRAIN-eligible = heldout_sets empty AND not A_val
    train_eligible_natural = [
        r for r in rows
        if not r.get("heldout_sets") and not r.get("in_a_val")
        and not r.get("train_only")
    ]
    n_train_natural = len(train_eligible_natural)
    max_corrupt = int(n_train_natural * corrupt_cap_frac / (1.0 - corrupt_cap_frac))
    if len(corruptor_rows) > max_corrupt:
        import random
        random.seed(seed)
        corruptor_rows = random.sample(corruptor_rows, max_corrupt)

    all_rows = rows + corruptor_rows

    stats = {
        "natural_rows": len(rows),
        "corruptor_rows": len(corruptor_rows),
        "corruptor_rows_pre_filter": sum(pre_filter_stats[ct]["n"] for ct in pre_filter_stats),
        "corruptor_generated_keys": len(corruptor_seeded_clusters),
        "gate_pass_by_oc": dict(gate_pass_by_oc),          # usable only
        "gate_pass_by_oc_all": dict(gate_pass_by_oc_all),  # all sets
        "nat_neg_clusters_usable": sorted(nat_neg_clusters_usable),
        "nat_neg_clusters_all": sorted(nat_neg_clusters_all),
        "n_nat_neg_usable": len(nat_neg_clusters_usable),
        "n_nat_neg_all": len(nat_neg_clusters_all),
        "pre_filter_stats": pre_filter_stats,
        "kept_stats": kept_stats,
        "dropped_types": dropped_types,
    }
    return all_rows, stats


def reproduce_phase5_natural_negatives(root: Path) -> tuple[dict[str, int], int]:
    """Reproduce Phase 5 natural-negative clusters across all evaluation sets."""
    runs_dir = root / RUNS_RELPATH
    negs: dict[str, set[str]] = defaultdict(set)
    for g in GENERATORS:
        for s in ALL_CANDIDATE_SETS:
            p = runs_dir / g / f"{s}.candidates.jsonl"
            if p.is_file():
                for row in jsonl_iter(p):
                    for c in row.get("scored", {}).get("candidates", []):
                        if c.get("gate_passed") and c.get("hidden_ok") is False:
                            negs[g].add(row["input_key"])
    union_cnt = len(set().union(*negs.values()))
    counts = {g: len(negs[g]) for g in GENERATORS}
    return counts, union_cnt


def compute_acceptance(all_stats: dict[str, dict], root: Path | None = None) -> None:
    """Print per-registered-bar acceptance results (F1 fix).

    Reports natural and corruptor SEPARATELY. Never adds generated rows to a
    natural count. Flags shortfall; prints cheapest honest remedy.
    """
    print("\n=== ACCEPTANCE CRITERIA ===")

    total_nat_gp_wrong_usable = 0   # gate-passing AND wrong (natural only, usable)
    total_nat_gp_wrong_all = 0      # gate-passing AND wrong (natural only, all sets)
    total_corr_hard_neg = 0         # corruptor hard negatives (gate-pass AND wrong, usable)
    total_corr_generated = 0
    total_corr_gate_pass = 0
    total_corr_oracle_wrong = 0
    nat_union_usable: set[str] = set()
    nat_union_all: set[str] = set()

    for gen, stats in all_stats.items():
        oc_usable = stats.get("gate_pass_by_oc", {})
        oc_all = stats.get("gate_pass_by_oc_all", {})
        corr_rows = stats.get("corruptor_rows", 0)
        corr_gen = stats.get("corruptor_rows_pre_filter", 0)
        corr_keys = stats.get("corruptor_generated_keys", 0)
        nat_neg_usable = stats.get("n_nat_neg_usable", 0)
        nat_neg_all = stats.get("n_nat_neg_all", 0)

        # Natural gate-passing-and-wrong = wrong + valid_not_minimal
        nat_gp_wrong_usable = oc_usable.get("wrong", 0) + oc_usable.get("valid_not_minimal", 0)
        nat_gp_wrong_all = oc_all.get("wrong", 0) + oc_all.get("valid_not_minimal", 0)

        pre_stats = stats.get("pre_filter_stats", {})
        corr_gp = sum(int(round(s["gate_pass_rate"] * s["n"])) for s in pre_stats.values())
        corr_ow = sum(int(round(s["oracle_wrong_rate"] * s["n"])) for s in pre_stats.values())

        # Corruptor hard negatives from kept_stats
        kept_stats = stats.get("kept_stats", {})
        corr_hard_neg = sum(
            int(round(s["hard_negative_rate"] * s["n"]))
            for s in kept_stats.values()
        )
        dropped_types = stats.get("dropped_types", [])

        print(f"\n[{gen}]")
        print("  Natural gate-passing candidates:")
        print(f"    USABLE (heldout empty):")
        print(f"      minimal_correct       : {oc_usable.get('minimal_correct', 0)}")
        print(f"      valid_not_minimal     : {oc_usable.get('valid_not_minimal', 0)}")
        print(f"      wrong                 : {oc_usable.get('wrong', 0)}")
        print(f"      unknown               : {oc_usable.get('unknown', 0)}")
        print(f"      gate-pass-not-strict  : {nat_gp_wrong_usable}")
        print(f"      natural neg clusters  : {nat_neg_usable}")
        print(f"    ALL SETS (including held-out):")
        print(f"      minimal_correct       : {oc_all.get('minimal_correct', 0)}")
        print(f"      valid_not_minimal     : {oc_all.get('valid_not_minimal', 0)}")
        print(f"      wrong                 : {oc_all.get('wrong', 0)}")
        print(f"      unknown               : {oc_all.get('unknown', 0)}")
        print(f"      gate-pass-not-strict  : {nat_gp_wrong_all}")
        print(f"      natural neg clusters  : {nat_neg_all}")
        print("  Corruptor:")
        print(f"    generated             : {corr_gen}")
        print(f"    gate-passing          : {corr_gp}")
        print(f"    oracle-wrong          : {corr_ow}")
        print(f"    hard negatives        : {corr_hard_neg} (gate-pass AND wrong)")
        print(f"    clusters seeded       : {corr_keys}")
        print(f"    kept rows (post-filter): {corr_rows}")
        print(f"    dropped types (hn=0)  : {dropped_types}")

        total_nat_gp_wrong_usable += nat_gp_wrong_usable
        total_nat_gp_wrong_all += nat_gp_wrong_all
        total_corr_hard_neg += corr_hard_neg
        total_corr_generated += corr_gen
        total_corr_gate_pass += corr_gp
        total_corr_oracle_wrong += corr_ow
        nat_union_usable.update(stats.get("nat_neg_clusters_usable", []))
        nat_union_all.update(stats.get("nat_neg_clusters_all", []))

    print("\n--- TOTALS ACROSS GENERATORS ---")
    print(f"Natural negative clusters (usable union): {len(nat_union_usable)}")
    print(f"Natural negative clusters (all sets union): {len(nat_union_all)}")
    print(f"  Natural cluster threshold {NATURAL_CLUSTER_THRESHOLD}: "
          f"{'PASS' if len(nat_union_usable) >= NATURAL_CLUSTER_THRESHOLD else 'BELOW THRESHOLD (shortfall: ' + str(NATURAL_CLUSTER_THRESHOLD - len(nat_union_usable)) + ')'}")
    print(f"Corruptor totals: generated={total_corr_generated}, gate-passing={total_corr_gate_pass}, "
          f"oracle-wrong={total_corr_oracle_wrong}, hard-negatives={total_corr_hard_neg}")

    if root is not None:
        p5_counts, p5_union = reproduce_phase5_natural_negatives(root)
        expected = (21, 4, 1, 22)
        actual = (p5_counts.get("zeroshot", 0), p5_counts.get("sft", 0), p5_counts.get("rft", 0), p5_union)
        print(f"\nPhase 5 reproduced: zeroshot={actual[0]}, sft={actual[1]}, rft={actual[2]}, union={actual[3]}")
        if actual == expected:
            print("  PASS: reproduced 21 / 4 / 1 / union 22 exactly")
        else:
            print(f"  FAIL: expected {expected}, got {actual}")

    # Pre-registered bar: >= 300 total gate-passing-and-wrong labeled negatives
    bar_natural_usable = total_nat_gp_wrong_usable
    bar_natural_all = total_nat_gp_wrong_all
    bar_corruptor = total_corr_hard_neg
    bar_total_usable = bar_natural_usable + bar_corruptor
    bar_total_all = bar_natural_all + bar_corruptor
    print(f"\n=== PRE-REGISTERED BAR ===")
    print(f"  Natural gate-passing-and-wrong (usable, non-heldout): {bar_natural_usable}")
    print(f"  Natural gate-passing-and-wrong (all sets):            {bar_natural_all}")
    print(f"  Corruptor hard negatives (est):                       {bar_corruptor}")
    print(f"  Total toward bar (usable nat + corr):                 {bar_total_usable}  (bar >= {BAR_TOTAL_NEGATIVES})")
    print(f"  Total toward bar (all nat + corr):                    {bar_total_all}  (bar >= {BAR_TOTAL_NEGATIVES})")

    if bar_total_usable < BAR_TOTAL_NEGATIVES:
        shortfall = BAR_TOTAL_NEGATIVES - bar_total_usable
        print(f"  *** SHORTFALL: {shortfall} below the {BAR_TOTAL_NEGATIVES} bar ***")
        print("  Cheapest honest ways to close shortfall:")
        print("    1. Add new corruptor types (C_new) with demonstrated hard_negative_rate > 0")
        print("    2. Add more harvest inputs with references (increases corruptor seed pool)")
        print("    3. Commission human labels on gate-passing harvest rows without references")
        print("    NOTE: do NOT lower the bar or count escalated_ok rows.")
    else:
        print(f"  PASS: >= {BAR_TOTAL_NEGATIVES} labeled negatives")

    if len(nat_union_usable) < NATURAL_CLUSTER_THRESHOLD:
        shortfall_c = NATURAL_CLUSTER_THRESHOLD - len(nat_union_usable)
        print(f"  *** NATURAL CLUSTER SHORTFALL: {shortfall_c} below {NATURAL_CLUSTER_THRESHOLD} threshold ***")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build M2 ground-truth labels (P3b)")
    parser.add_argument("--out-dir", default="ml/train_m2/out/labels")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--corrupt-cap", type=float, default=CORRUPT_CAP_FRAC)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    root = repo_root()
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    ref_map = _load_reference_map(root)
    hi_map = _load_harvest_inputs_map(root)

    # Build partition sets once
    partition_sets = load_partition_sets()

    # F5: corruptor eligible inputs
    corruptor_eligible = corruptor_seed_partition(partition_sets)
    # Filter to those with a reference
    corruptor_eligible_with_ref = {
        ik for ik in corruptor_eligible
        if ref_map.get(ik, {}).get("reference") is not None
    }
    LOG.info(
        "Corruptor eligible inputs (phase5_train, not A_val, not held-out, has ref): %d",
        len(corruptor_eligible_with_ref),
    )
    print(f"\nCorruptor eligible inputs: {len(corruptor_eligible_with_ref)}")

    all_stats: dict[str, dict] = {}
    corruptor_cache: dict[str, list[dict]] = {}
    all_pre_filter_stats: dict[str, dict] = {}
    all_dropped_types: list[str] = []

    for generator in GENERATORS:
        LOG.info("Processing generator: %s", generator)
        rows, stats = build_labels_for_generator(
            generator=generator,
            root=root,
            ref_map=ref_map,
            hi_map=hi_map,
            partition_sets=partition_sets,
            corruptor_eligible=corruptor_eligible_with_ref,
            seed=args.seed,
            corrupt_cap_frac=args.corrupt_cap,
            corruptor_cache=corruptor_cache,
        )
        all_stats[generator] = stats
        # Accumulate pre-filter stats for table
        for ctype, s in stats.get("pre_filter_stats", {}).items():
            if ctype not in all_pre_filter_stats:
                all_pre_filter_stats[ctype] = dict(s)
            else:
                existing = all_pre_filter_stats[ctype]
                n_old, n_new = existing["n"], s["n"]
                n_total = n_old + n_new
                if n_total:
                    existing["gate_pass_rate"] = (
                        existing["gate_pass_rate"] * n_old + s["gate_pass_rate"] * n_new
                    ) / n_total
                    existing["oracle_wrong_rate"] = (
                        existing["oracle_wrong_rate"] * n_old + s["oracle_wrong_rate"] * n_new
                    ) / n_total
                    existing["hard_negative_rate"] = (
                        existing["hard_negative_rate"] * n_old + s["hard_negative_rate"] * n_new
                    ) / n_total
                    existing["oracle_unknown_count"] = (
                        existing.get("oracle_unknown_count", 0) + s.get("oracle_unknown_count", 0)
                    )
                existing["n"] = n_total
        for t in stats.get("dropped_types", []):
            if t not in all_dropped_types:
                all_dropped_types.append(t)

        out_path = out_dir / f"{generator}.jsonl"
        jsonl_write_atomic(out_path, rows)
        LOG.info("Wrote %d rows to %s", len(rows), out_path)

        # Provenance
        input_files = [
            root / RUNS_RELPATH / generator / f"{s}.candidates.jsonl"
            for s in ALL_CANDIDATE_SETS
        ] + [root / p for p in DATASET_PATHS]
        existing_inputs = [p for p in input_files if p.exists()]
        write_provenance(
            out_path,
            inputs=existing_inputs,
            seed=args.seed,
            extra={
                "generator": generator,
                "candidate_sets": list(ALL_CANDIDATE_SETS),
                "corruptor_eligible_count": len(corruptor_eligible_with_ref),
            },
        )

    # Hard-negative table (F2: pre and post filter)
    # Collect all corruptor rows from output files for the final table
    all_corruptor_rows: list[dict] = []
    for generator in GENERATORS:
        out_path = out_dir / f"{generator}.jsonl"
        if out_path.exists():
            for r in jsonl_iter(out_path):
                if r.get("train_only") and r.get("corruption_type"):
                    all_corruptor_rows.append(r)

    if all_corruptor_rows:
        post_filter_stats = hard_negative_stats(all_corruptor_rows)
        _, dropped = filter_hard_negative_types(all_pre_filter_stats)
        hn_path = out_dir / "hard_negative_table.md"
        md_text = write_hard_negative_table(
            post_filter_stats,
            str(hn_path),
            pre_filter_stats=all_pre_filter_stats,
            dropped_types=sorted(set(all_dropped_types)),
        )
        print("\n" + md_text)
    else:
        print("\n(c) No corruptor rows to compute hard-negative table")

    compute_acceptance(all_stats, root=root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
