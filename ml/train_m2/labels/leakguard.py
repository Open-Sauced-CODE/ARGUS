"""Leak guards for M2 ground-truth and training data (Shaurya-owned).

Contract
--------
* load_key_sets builds the cluster-level (input_key) universes every guard uses: the held-out sets, A_val,
  the Phase 5 train inputs and the rft_v2 train inputs.
* audit_label_rows RE-DERIVES every partition flag from those key sets (a flag already stored in a row is only
  cross-checked, never trusted) and reports violations; raise_if_violations makes them a hard error.
* assert_training_safe is the only gate through which rows may reach M2 training: no held-out input, and
  corruptor rows only from eligible seeds (Phase 5 train inputs that are neither held-out nor A_val).
Held-out sets are used for set membership only; nothing is scored here.
"""
from __future__ import annotations


import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from ml.mutation_engine.dataset_io import input_key as example_key

LOG = logging.getLogger(__name__)

HELD_OUT_REQUIRED = ("tierB1", "tierB2", "tierC_verifier", "gold")
HELD_OUT_OPTIONAL = ("C_human",)
REQUIRED_FIELDS = ("input_key", "generator", "source", "gate_pass", "oracle_class")
REQUIRED_FIELDS_CORRUPTOR = ("input_key", "source", "gate_pass", "oracle_class")   # corruptions are generator-independent
CORRUPTOR = "corruptor"


class LeakError(AssertionError):
    """Raised when data would cross a held-out boundary or a required guard input is missing."""


def _read_jsonl(path: Path) -> Iterator[dict]:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for line in fh:
            s = line.strip()
            if s:
                yield json.loads(s)


def _keys(path: Path) -> set[str]:
    out: set[str] = set()
    for row in _read_jsonl(path):
        k = row.get("input_key")
        out.add(k if k is not None else example_key(row))
    return out


@dataclass
class KeySets:
    held_out: dict[str, set[str]]
    a_val: set[str]
    phase5_train: set[str]
    v2_train: set[str]
    missing: list[str] = field(default_factory=list)

    @property
    def held_out_union(self) -> set[str]:
        return set().union(*self.held_out.values()) if self.held_out else set()

    def heldout_sets_of(self, key: str) -> list[str]:
        return sorted(n for n, s in self.held_out.items() if key in s)

    def generator_seen(self, generator: str, key: str) -> bool:
        """True if the generator's weights were trained on this input (cluster)."""
        if generator in ("sft", "rft"):
            return key in self.phase5_train
        if generator == "rft_v2":
            return key in self.v2_train
        if generator == "zeroshot":
            return False
        raise ValueError(f"unknown generator {generator!r}")

    def corruptor_eligible(self) -> set[str]:
        return self.phase5_train - self.held_out_union - self.a_val


def load_key_sets(root: Path, strict: bool = True) -> KeySets:
    root = Path(root)
    missing: list[str] = []
    held: dict[str, set[str]] = {}
    for name in HELD_OUT_REQUIRED + HELD_OUT_OPTIONAL:
        p = root / "ml" / "mutation_engine" / "held_out" / f"{name}.jsonl"
        if p.exists():
            held[name] = _keys(p)
        elif name in HELD_OUT_REQUIRED:
            missing.append(str(p.relative_to(root).as_posix()))

    def _first(*rels: str) -> set[str]:
        for rel in rels:
            p = root / rel
            if p.exists():
                return _keys(p)
        missing.append(rels[0])
        return set()

    ks = KeySets(
        held_out=held,
        a_val=_first("ml/mutation_engine/dataset/val.jsonl"),
        phase5_train=_first("ml/mutation_engine/dataset/train.jsonl", "ml/train_m1/data/sft_train.jsonl"),
        v2_train=_first("ml/train_m1/v2/data/v2_train.meta.jsonl"),
        missing=missing,
    )
    if missing and strict:
        raise LeakError("missing guard inputs: " + ", ".join(missing))
    return ks


def _seed_key(row: Mapping[str, Any]) -> str:
    return row.get("source_input_key") or row.get("input_key")


def short(key: Any) -> str:
    """8-hex digest of an input_key (the raw key is a long JSON string whose prefix is identical everywhere)."""
    return hashlib.sha1(str(key).encode("utf-8")).hexdigest()[:8]


def _tag(row: Mapping[str, Any]) -> str:
    return f"{row.get('generator')}:{short(row.get('input_key'))}:{row.get('sample_idx')}"


def audit_label_rows(rows: Iterable[Mapping[str, Any]], ks: KeySets) -> dict[str, Any]:
    """Return {"n_rows": int, "violations": {name: {"count": n, "examples": [..5]}}}."""
    viol: dict[str, list[str]] = defaultdict(list)
    n = 0
    nat_seen: set[tuple] = set()
    cor_seen: set[tuple] = set()
    eligible = ks.corruptor_eligible()
    held = ks.held_out_union
    for row in rows:
        n += 1
        tag = _tag(row)
        req = REQUIRED_FIELDS_CORRUPTOR if row.get("source") == CORRUPTOR else REQUIRED_FIELDS
        miss = [f for f in req if row.get(f) is None]
        if miss:
            viol["missing_field:" + "+".join(miss)].append(tag)
            continue
        if row.get("answer_key") is None:
            viol["missing_answer_key"].append(tag)
        if "patch" not in row:
            viol["missing_patch_field"].append(tag)
        k = row["input_key"]
        if "heldout_sets" in row and sorted(row["heldout_sets"] or []) != ks.heldout_sets_of(k):
            viol["flag_heldout_sets_wrong"].append(tag)
        if "in_a_val" in row and ks.a_val and bool(row["in_a_val"]) != (k in ks.a_val):
            viol["flag_in_a_val_wrong"].append(tag)
        if "generator_seen" in row and row["source"] != CORRUPTOR:
            if bool(row["generator_seen"]) != ks.generator_seen(row["generator"], k):
                viol["flag_generator_seen_wrong"].append(tag)
        if row["source"] == CORRUPTOR:
            sk = _seed_key(row)
            if sk not in eligible:
                viol["corruptor_seed_not_eligible"].append(tag)
            if sk in held:
                viol["corruptor_seed_heldout"].append(tag)
            if sk in ks.a_val:
                viol["corruptor_seed_a_val"].append(tag)
            if row.get("train_only") is not True:
                viol["corruptor_not_train_only"].append(tag)
            key = (sk, row.get("corruption_type"), row.get("answer_key"))
            if key in cor_seen:
                viol["duplicate_corruptor_row"].append(tag)
            cor_seen.add(key)
        else:
            key = (row["source"], row.get("source_file"), row["generator"], row.get("profile"), k,
                   row.get("sample_idx"))
            if key in nat_seen:
                viol["duplicate_natural_row"].append(tag)
            nat_seen.add(key)
    return {"n_rows": n, "violations": {k: {"count": len(v), "examples": v[:5]} for k, v in viol.items()}}


def raise_if_violations(report: Mapping[str, Any]) -> None:
    v = report["violations"]
    if v:
        raise LeakError("label audit failed: " + "; ".join(f"{k}={d['count']}" for k, d in sorted(v.items())))


def training_rows(rows: Iterable[Mapping[str, Any]], ks: KeySets) -> Iterator[Mapping[str, Any]]:
    """Rows M2 may train on: not held-out; corruptor rows only from eligible seeds."""
    held = ks.held_out_union
    eligible = ks.corruptor_eligible()
    for row in rows:
        k = row["input_key"]
        if k in held:
            continue
        if row.get("source") == CORRUPTOR and _seed_key(row) not in eligible:
            continue
        yield row


def assert_training_safe(rows: Iterable[Mapping[str, Any]], ks: KeySets) -> int:
    """Raise LeakError if any row is unsafe for training; return the number of rows checked."""
    held = ks.held_out_union
    eligible = ks.corruptor_eligible()
    bad_h = bad_c = n = 0
    for row in rows:
        n += 1
        if row["input_key"] in held:
            bad_h += 1
        if row.get("source") == CORRUPTOR and _seed_key(row) not in eligible:
            bad_c += 1
    if bad_h or bad_c:
        raise LeakError(f"unsafe training rows: held_out={bad_h}, corruptor_seed_not_eligible={bad_c}")
    return n
