"""Training/eval frames for M2 (Shaurya-owned).

Population: natural FIX candidates that PASSED the gate (route == fix; escalate-route inputs never reach M2).
Label: y = 1 iff oracle_class == minimal_correct (strict). Gate-pass is never the label. Features come ONLY from
ml.train_m2.features.compute (same code as inference). Corruptor rows are not used in this version.
Join key between a label row and its harvest row: (generator, input_key, sample_idx).
"""
from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from ml.train_m2.features import registry as R
from ml.train_m2.features.compute import compute_features

POS = "minimal_correct"
NEG = {"wrong", "valid_not_minimal"}          # fixed_should_escalate only occurs on escalate-route inputs (excluded)


def _jsonl(path) -> Iterable[dict]:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def load_harvest(root: Path, generator: str) -> dict[tuple[str, int], dict]:
    out: dict[tuple[str, int], dict] = {}
    for f in sorted(glob.glob(str(Path(root) / "ml" / "train_m2" / "harvest_out" / generator / "A" / "part-*.jsonl"))):
        for r in _jsonl(f):
            out[(r["input_key"], int(r["sample_idx"]))] = r
    return out


def load_routes_and_rules(root: Path) -> dict[str, dict[str, str]]:
    """{input_key: {"route": fix|escalate, "rule_id": ...}} from the dataset examples (meta.route), never from labels."""
    from ml.mutation_engine.dataset_io import input_key
    out: dict[str, dict[str, str]] = {}
    files = [Path(root) / "ml" / "mutation_engine" / "dataset" / n for n in ("train.jsonl", "val.jsonl")]
    files += [Path(root) / "ml" / "mutation_engine" / "held_out" / f"{n}.jsonl" for n in ("tierB1", "tierB2", "tierC_verifier", "gold")]
    for f in files:
        if f.exists():
            for ex in _jsonl(f):
                out.setdefault(input_key(ex), {"route": (ex.get("meta") or {}).get("route"), "rule_id": ex.get("rule_id") or ex["input"]["rule_id"]})
    return out


def build_frame(label_rows: Iterable[Mapping[str, Any]], harvest_by_gen: Mapping[str, Mapping[tuple[str, int], dict]],
                info_by_key: Mapping[str, Mapping[str, str]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """-> (X with R.names() columns, meta with input_key, generator, sample_idx, rule_id, y). Skips rows it cannot join."""
    feats, metas = [], []
    cohorts: dict[tuple[str, str], list[dict]] = {}
    n_skipped = 0
    for lr in label_rows:
        if lr.get("source") == "corruptor" or lr.get("gate_pass") is not True or lr.get("outcome") != "fixed":
            continue
        cls = lr.get("oracle_class")
        if cls != POS and cls not in NEG:
            continue
        info = info_by_key.get(lr["input_key"])
        if info is None or info.get("route") != "fix":
            continue
        gen = lr["generator"]
        hv = harvest_by_gen.get(gen, {})
        row = hv.get((lr["input_key"], int(lr["sample_idx"])))
        if row is None:
            n_skipped += 1
            continue
        ck = (gen, lr["input_key"])
        if ck not in cohorts:
            cohorts[ck] = [hv[(lr["input_key"], i)] for i in range(64) if (lr["input_key"], i) in hv]
        f = compute_features(row, cohorts[ck], {"rule_id": info["rule_id"], "route": info["route"]})
        f.pop("spec_hash")
        feats.append(f)
        metas.append({"input_key": lr["input_key"], "generator": gen, "sample_idx": int(lr["sample_idx"]),
                      "rule_id": info["rule_id"], "y": int(cls == POS), "oracle_class": cls})
    X = pd.DataFrame(feats, columns=R.names()).astype(float)
    meta = pd.DataFrame(metas, columns=["input_key", "generator", "sample_idx", "rule_id", "y", "oracle_class"])
    meta.attrs["n_unjoined_label_rows"] = n_skipped
    return X, meta


def load_partition(X: pd.DataFrame, meta: pd.DataFrame, splits: Mapping[str, Any], name: str):
    keys = set(splits["parts"][name])
    m = meta["input_key"].isin(keys).to_numpy()
    return X[m].reset_index(drop=True), meta[m].reset_index(drop=True)
