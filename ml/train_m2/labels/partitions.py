"""Phase 6 partition flag builder for M2 label rows.

Contract
--------
build_partition_flags(input_key, sets_field, v2_train_keys, generator) -> dict

Returns a dict with these boolean/list fields (NO single 'partition' string):
  in_phase5_train  : bool   -- key appears in train300 (Phase 5 train set)
  in_a_val         : bool   -- key appears in A_val
  heldout_sets     : list   -- sorted list of held-out set names the key belongs to
                              (B1, B2, C_verifier, gold; C-human if present)
  in_v2_train      : bool   -- key appears in v2_train.meta.jsonl
  generator_seen   : bool   -- whether the generator saw the input during training
                              (sft/rft: in_phase5_train; rft_v2: in_v2_train;
                               zeroshot: always False)

Usage
-----
Call load_partition_sets() once to build the key sets, then call
build_partition_flags() per row.  Never import this module from held-out
scoring scripts; flags are informational only.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)

# Canonical held-out set names (order stable)
HELD_OUT_SET_NAMES = (
    "tierB1", "tierB2", "tierC_verifier", "gold", "C-human",
    "B1", "B2", "C_verifier",
)

# Harvest-inputs sets field -> canonical name mapping
_SET_NAME_MAP: dict[str, str] = {
    "B1": "tierB1",
    "B2": "tierB2",
    "C_verifier": "tierC_verifier",
    "gold": "gold",
    "C-human": "C-human",
    "tierB1": "tierB1",
    "tierB2": "tierB2",
    "tierC_verifier": "tierC_verifier",
}

# Phase 5 eval set name in the candidate-log files
PHASE5_TRAIN_SET = "train"   # key name inside harvest_inputs.jsonl sets field
PHASE5_A_VAL_SET = "A_val"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def load_partition_sets() -> dict[str, set[str]]:
    """Load all partition key sets from disk; returns a dict of set-name -> input_keys.

    Keys loaded:
      'a_val'          -- from harvest_inputs.jsonl sets['A_val']
      'phase5_train'   -- from harvest_inputs.jsonl sets['train']
      'tierB1','tierB2','tierC_verifier','gold','C-human' -- held-out sets
      'v2_train'       -- from ml/train_m1/v2/data/v2_train.meta.jsonl
    """
    root = _repo_root()
    result: dict[str, set[str]] = {
        "a_val": set(),
        "phase5_train": set(),
        "tierB1": set(),
        "tierB2": set(),
        "tierC_verifier": set(),
        "gold": set(),
        "C-human": set(),
        "v2_train": set(),
    }

    # Parse harvest_inputs.jsonl
    hi_path = root / "ml" / "train_m2" / "contract" / "harvest_inputs.jsonl"
    if hi_path.exists():
        with open(hi_path, encoding="utf-8", newline="") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                ik = row["input_key"]
                sets = row.get("sets", {})
                if PHASE5_A_VAL_SET in sets:
                    result["a_val"].add(ik)
                if PHASE5_TRAIN_SET in sets:
                    result["phase5_train"].add(ik)
                for src_name, canon_name in _SET_NAME_MAP.items():
                    if sets.get(src_name):
                        result[canon_name].add(ik)
    else:
        LOG.warning("harvest_inputs.jsonl not found at %s", hi_path)

    # Parse v2_train.meta.jsonl (Prabhav's file -- read-only)
    v2_path = root / "ml" / "train_m1" / "v2" / "data" / "v2_train.meta.jsonl"
    if v2_path.exists():
        with open(v2_path, encoding="utf-8", newline="") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                ik = row.get("input_key")
                if ik:
                    result["v2_train"].add(ik)
    else:
        LOG.warning("v2_train.meta.jsonl not found at %s; in_v2_train will be False for all rows")

    return result


def build_partition_flags(
    input_key: str,
    generator: str | None,
    partition_sets: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    """Build partition flags for a single input_key.

    Parameters
    ----------
    input_key       The cluster key for this row.
    generator       Generator name: 'zeroshot' | 'sft' | 'rft' | 'rft_v2' | None.
    partition_sets  Pre-loaded partition sets (from load_partition_sets()).
                    If None, calls load_partition_sets() (cached).

    Returns
    -------
    dict with keys:
      in_phase5_train, in_a_val, heldout_sets, in_v2_train, generator_seen
    """
    if partition_sets is None:
        partition_sets = load_partition_sets()

    in_phase5_train: bool = input_key in partition_sets["phase5_train"]
    in_a_val: bool = input_key in partition_sets["a_val"]
    in_v2_train: bool = input_key in partition_sets["v2_train"]

    heldout_sets: list[str] = sorted(
        name for name in HELD_OUT_SET_NAMES
        if input_key in partition_sets.get(name, set())
    )

    # generator_seen: whether the generator's weights saw this input during training
    #   sft, rft  -> in_phase5_train (sft_train.jsonl is the Phase 5 train set)
    #   rft_v2    -> in_v2_train
    #   zeroshot  -> never (base model, no fine-tuning)
    gen = (generator or "").lower()
    if gen in ("sft", "rft"):
        generator_seen: bool = in_phase5_train
    elif gen == "rft_v2":
        generator_seen = in_v2_train
    else:
        generator_seen = False

    return {
        "in_phase5_train": in_phase5_train,
        "in_a_val": in_a_val,
        "heldout_sets": heldout_sets,
        "in_v2_train": in_v2_train,
        "generator_seen": generator_seen,
    }


def corruptor_seed_partition(
    partition_sets: dict[str, set[str]] | None = None,
) -> set[str]:
    """Return input_keys eligible to seed the corruptor.

    Eligibility: in_phase5_train AND heldout_sets empty AND NOT in_a_val.
    Reference existence is checked separately by the corruptor caller.
    """
    if partition_sets is None:
        partition_sets = load_partition_sets()

    held_union: set[str] = set()
    for name in HELD_OUT_SET_NAMES:
        held_union |= partition_sets.get(name, set())

    eligible = (
        partition_sets["phase5_train"]
        - partition_sets["a_val"]
        - held_union
    )
    return eligible

