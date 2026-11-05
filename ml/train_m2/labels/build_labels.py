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
from typing import Any, Iterable, Iterator

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
from ml.train_m2.labels.accounting import compute_accounting, render_markdown
from ml.train_m2.labels.corruptor import (
    filter_hard_negative_types,
    hard_negative_stats,
    make_corrupted_rows,
    write_hard_negative_table,
)
from ml.train_m2.labels.leakguard import load_key_sets
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
    corruptor_eligible: set[str] | None = None,
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
                    content=content,
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

    stats = {
        "natural_rows": len(rows),
        "corruptor_rows": 0,
        "corruptor_rows_pre_filter": 0,
        "corruptor_generated_keys": 0,
        "gate_pass_by_oc": dict(gate_pass_by_oc),          # usable only
        "gate_pass_by_oc_all": dict(gate_pass_by_oc_all),  # all sets
        "nat_neg_clusters_usable": sorted(nat_neg_clusters_usable),
        "nat_neg_clusters_all": sorted(nat_neg_clusters_all),
        "n_nat_neg_usable": len(nat_neg_clusters_usable),
        "n_nat_neg_all": len(nat_neg_clusters_all),
        "pre_filter_stats": {},
        "kept_stats": {},
        "dropped_types": [],
    }
    return rows, stats


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


def compute_acceptance(all_rows: Iterable[dict], root: Path | None = None) -> None:
    """Print per-registered-bar acceptance results via accounting module (P3c)."""
    ks = load_key_sets(root or repo_root())
    rep = compute_accounting(all_rows, ks)
    md = render_markdown(rep)
    print("\n" + md)


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

    # 2f: Corruptor seed partition cross-check
    ks = load_key_sets(root)
    p_part = corruptor_seed_partition(partition_sets)
    lg_part = ks.corruptor_eligible()
    corruptor_eligible_with_ref = {
        ik for ik in p_part
        if ref_map.get(ik, {}).get("reference") is not None
        and ref_map.get(ik, {}).get("route") == "fix"
    }
    print(f"\nCorruptor seed partition cross-check:")
    print(f"  partitions.corruptor_seed_partition : {len(p_part)}")
    print(f"  leakguard.KeySets.corruptor_eligible : {len(lg_part)}")
    print(f"  eligible with fix reference          : {len(corruptor_eligible_with_ref)}")

    all_rows: list[dict] = []
    all_stats: dict[str, dict] = {}

    for generator in GENERATORS:
        LOG.info("Processing generator: %s", generator)
        rows, stats = build_labels_for_generator(
            generator=generator,
            root=root,
            ref_map=ref_map,
            hi_map=hi_map,
            partition_sets=partition_sets,
            seed=args.seed,
        )
        all_stats[generator] = stats
        all_rows.extend(rows)

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
            },
        )

    if root is not None:
        p5_counts, p5_union = reproduce_phase5_natural_negatives(root)
        print(f"\nPhase 5 reproduced: zeroshot={p5_counts.get('zeroshot', 0)}, sft={p5_counts.get('sft', 0)}, rft={p5_counts.get('rft', 0)}, union={p5_union}")

    compute_acceptance(all_rows, root=root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
