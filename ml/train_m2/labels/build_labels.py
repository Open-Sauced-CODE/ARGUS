"""Phase 6 label builder: joins candidates with oracle labels -> per-generator JSONL files.

CLI
---
    py -m ml.train_m2.labels.build_labels [--out-dir ml/train_m2/out/labels] [--seed 1337]
    py -m ml.train_m2.labels.build_labels --help

For each generator (zeroshot, sft, rft) that has Phase 5 candidate logs, the script:
  1. Loads the Phase 5 candidate logs (A_val set; profile A).
  2. Joins each log row with the record from harvest_inputs.jsonl (via input_key).
  3. Joins with the reference patch from the dataset (train + val) where available.
  4. Calls label_candidate (using the pre-scored dict to avoid re-running OPA).
  5. Runs make_corrupted_rows on the TRAIN partition (reference required).
  6. Writes <out_dir>/<generator>.jsonl atomically (all LabelRow dicts + corruptor rows).
  7. Writes provenance JSON next to each output file.

Statistics printed:
  - count of gate-passing natural candidates where strict_correct is False
  - natural negative clusters per generator
  - hard-negative table
  - total labeled negatives vs the 300 bar

Hard rules:
  - The statistical unit is the CLUSTER (input_key); never rows.
  - Corrupted rows are capped at 35% of training rows (configurable via --corrupt-cap).
  - Corrupted rows are marked train_only=True.
  - Every output carries a provenance JSON (common.write_provenance).
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

LOG = logging.getLogger(__name__)

GENERATORS = ("zeroshot", "sft", "rft")
CANDIDATE_SET = "A_val"
RUNS_RELPATH = Path("ml") / "train_m1" / "eval" / "runs"
DATASET_PATHS = (
    Path("ml") / "mutation_engine" / "dataset" / "train.jsonl",
    Path("ml") / "mutation_engine" / "dataset" / "val.jsonl",
)
CORRUPT_CAP_FRAC = 0.35


def _load_reference_map(root: Path) -> dict[str, dict]:
    """Build input_key -> {record, reference, route} from training and val dataset files."""
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
    # Determine source_file (repo-relative)
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
            yield row


def build_labels_for_generator(
    generator: str,
    root: Path,
    ref_map: dict[str, dict],
    hi_map: dict[str, dict],
    seed: int = 1337,
    corrupt_cap_frac: float = CORRUPT_CAP_FRAC,
    corruptor_cache: dict[str, list[dict]] | None = None,
) -> tuple[list[dict], dict]:
    """Build LabelRow dicts for one generator (natural + corruptor).

    Returns (rows, stats) where stats is a dict with summary numbers.
    """
    rng_state = set_seed(seed)

    rows: list[dict] = []
    corruptor_rows: list[dict] = []
    natural_neg_clusters: set[str] = set()
    gate_pass_wrong_count = 0

    for log_row in _iter_phase5_log(root, generator, CANDIDATE_SET):
        ik = log_row.get("input_key", "")
        source_file = log_row.get("_source_file")
        contents = log_row.get("contents", [])
        scored_candidates = log_row.get("scored", {}).get("candidates", [])

        # Get record from harvest_inputs (fallback to ref_map)
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
            rows.append(row_dict)

            # Track natural negatives
            if label_row.gate_pass and label_row.oracle_class in ("wrong", "valid_not_minimal"):
                natural_neg_clusters.add(ik)

            # Count gate-passing where strict_correct is False
            if label_row.gate_pass and label_row.strict_correct is False:
                gate_pass_wrong_count += 1

            # Generate corruptor rows for TRAIN inputs with a reference
            if sample_idx == 0 and reference is not None:
                if corruptor_cache is not None and ik in corruptor_cache:
                    c_rows = [copy.deepcopy(r) for r in corruptor_cache[ik]]
                else:
                    c_rows = make_corrupted_rows(
                        record=record,
                        reference=reference,
                        route=route,
                        input_key=ik,
                        seed=seed + hash(ik) % (2**20),
                        source_file=source_file,
                    )
                    if corruptor_cache is not None:
                        corruptor_cache[ik] = [copy.deepcopy(r) for r in c_rows]
                for cr in c_rows:
                    cr["generator"] = generator
                    cr["train_only"] = True
                corruptor_rows.extend(c_rows)

    # Enforce the corrupt cap
    natural_count = len(rows)
    max_corrupt = int(natural_count * corrupt_cap_frac / (1 - corrupt_cap_frac))
    if len(corruptor_rows) > max_corrupt:
        import random

        random.seed(seed)
        corruptor_rows = random.sample(corruptor_rows, max_corrupt)

    all_rows = rows + corruptor_rows

    stats = {
        "natural_rows": natural_count,
        "corruptor_rows": len(corruptor_rows),
        "gate_pass_wrong_count": gate_pass_wrong_count,
        "natural_neg_clusters": sorted(natural_neg_clusters),
        "n_natural_neg_clusters": len(natural_neg_clusters),
    }
    return all_rows, stats


def reproduce_phase5_natural_negatives(root: Path) -> tuple[dict[str, int], int]:
    """Reproduce Phase 5 natural-negative clusters across all evaluation sets."""
    runs_dir = root / RUNS_RELPATH
    sets = ("A_val", "train300", "B1", "B2", "C_verifier", "gold")
    negs: dict[str, set[str]] = defaultdict(set)
    for g in GENERATORS:
        for s in sets:
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
    """Print acceptance criteria results."""
    print("\n=== ACCEPTANCE CRITERIA ===")
    total_neg = 0
    nat_union: set[str] = set()

    for gen, stats in all_stats.items():
        neg = stats["gate_pass_wrong_count"]
        corr = stats["corruptor_rows"]
        nat_clusters = stats["n_natural_neg_clusters"]
        print(f"\n[{gen}]")
        print(f"  (a) gate-passing natural candidates where strict_correct=False: {neg}")
        print(f"  (b) natural negative clusters in A_val: {nat_clusters}")
        total_neg += neg + corr
        nat_union.update(stats["natural_neg_clusters"])

    print(f"\n(b) Natural negative clusters in A_val union: {len(nat_union)}")

    if root is not None:
        p5_counts, p5_union = reproduce_phase5_natural_negatives(root)
        print(f"(b) Phase 5 candidate logs reproduced: zeroshot={p5_counts.get('zeroshot', 0)}, sft={p5_counts.get('sft', 0)}, rft={p5_counts.get('rft', 0)}, union={p5_union}")
        if (p5_counts.get("zeroshot"), p5_counts.get("sft"), p5_counts.get("rft"), p5_union) == (21, 4, 1, 22):
            print("    PASS: reproduced 21 / 4 / 1 / union 22 exactly")

    print(f"\n(e) Total labeled negatives: {total_neg}")
    if total_neg < 300:
        print(f"    SHORTFALL: {300 - total_neg} below the 300 bar")
        print("    Cheapest way to close: add more corruptor types or lower the corrupt_cap")
    else:
        print("    PASS: >= 300 labeled negatives")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build M2 ground-truth labels")
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

    all_stats: dict[str, dict] = {}
    all_corruptor_rows: list[dict] = []
    corruptor_cache: dict[str, list[dict]] = {}

    for generator in GENERATORS:
        LOG.info("Processing generator: %s", generator)
        rows, stats = build_labels_for_generator(
            generator=generator,
            root=root,
            ref_map=ref_map,
            hi_map=hi_map,
            seed=args.seed,
            corrupt_cap_frac=args.corrupt_cap,
            corruptor_cache=corruptor_cache,
        )
        all_stats[generator] = stats
        all_corruptor_rows.extend([r for r in rows if r.get("train_only")])

        out_path = out_dir / f"{generator}.jsonl"
        count = jsonl_write_atomic(out_path, rows)
        LOG.info("Wrote %d rows to %s", count, out_path)

        # Provenance
        input_files = [
            root / RUNS_RELPATH / generator / f"{CANDIDATE_SET}.candidates.jsonl",
        ] + [root / p for p in DATASET_PATHS]
        existing_inputs = [p for p in input_files if p.exists()]
        write_provenance(
            out_path,
            inputs=existing_inputs,
            seed=args.seed,
            extra={"generator": generator, "candidate_set": CANDIDATE_SET},
        )

    # Hard-negative table
    if all_corruptor_rows:
        hn_stats = hard_negative_stats(all_corruptor_rows)
        hn_path = out_dir / "hard_negative_table.md"
        md_text = write_hard_negative_table(hn_stats, str(hn_path))
        print("\n" + md_text)
    else:
        hn_stats = {}
        print("\n(c) No corruptor rows to compute hard-negative table")

    compute_acceptance(all_stats, root=root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
