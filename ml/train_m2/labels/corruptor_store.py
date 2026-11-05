"""Generate-once, de-duplicated, capped corruptor store (Shaurya-owned).

Contract
--------
Corruptions depend only on (seed, input_key, corruption type), never on a generator, so they are produced ONCE
and stored in one file. Rows are de-duplicated on (seed input_key, corruption_type, answer_key), restricted to
the kept types, then capped so corruptor rows are at most `frac` of the final training set. Selection under the
cap is deterministic (sha256 order) and round-robin across types so one type cannot dominate.
"""
from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Collection, Iterable, Mapping, Sequence

from ml.train_m2 import common


def cap_for(n_natural: int, frac: float) -> int:
    """Largest number of corruptor rows c with c / (n_natural + c) <= frac."""
    if not 0.0 <= frac < 1.0:
        raise ValueError("frac must be in [0, 1)")
    return int(math.floor(frac / (1.0 - frac) * n_natural + 1e-9))


def _h(*parts: object) -> int:
    return int(hashlib.sha256(":".join(map(str, parts)).encode("utf-8")).hexdigest(), 16)


def seed_key(row: Mapping[str, Any]) -> str:
    return row.get("source_input_key") or row["input_key"]


def dedupe(rows: Iterable[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in rows:
        k = (seed_key(r), r.get("corruption_type"), r.get("answer_key"))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def select_capped(rows: Sequence[dict], max_n: int, seed: int) -> list[dict]:
    """Deterministic round-robin selection of at most max_n rows across corruption types."""
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_type[str(r.get("corruption_type"))].append(r)
    for t in by_type:
        by_type[t].sort(key=lambda r: _h(seed, seed_key(r), t, r.get("answer_key")))
    out: list[dict] = []
    idx = {t: 0 for t in by_type}
    types = sorted(by_type)
    while len(out) < max_n and any(idx[t] < len(by_type[t]) for t in types):
        for t in types:
            if idx[t] < len(by_type[t]) and len(out) < max_n:
                out.append(by_type[t][idx[t]])
                idx[t] += 1
    return out


def build_store(
    seed_items: Iterable[tuple[str, Mapping[str, Any], Mapping[str, Any], str]],
    make_rows: Callable[..., list[dict]],
    keep_types: Collection[str],
    n_natural: int,
    frac: float = 0.35,
    seed: int = 1337,
) -> tuple[list[dict], dict[str, Any]]:
    """seed_items: (input_key, record, reference, route) for ELIGIBLE seeds only (see leakguard)."""
    generated: list[dict] = []
    for ik, record, reference, route in sorted(seed_items, key=lambda x: x[0]):
        for row in make_rows(record, reference, route, ik, seed):
            row = dict(row)
            row["source_input_key"] = ik
            row["train_only"] = True
            row["source"] = "corruptor"
            generated.append(row)
    kept_t = [r for r in generated if r.get("corruption_type") in set(keep_types)]
    uniq = dedupe(kept_t)
    cap = cap_for(n_natural, frac)
    final = select_capped(uniq, cap, seed)
    per_type: dict[str, int] = defaultdict(int)
    for r in final:
        per_type[str(r.get("corruption_type"))] += 1
    report = {
        "generated": len(generated),
        "after_type_filter": len(kept_t),
        "after_dedupe": len(uniq),
        "n_natural": n_natural,
        "frac": frac,
        "cap": cap,
        "kept": len(final),
        "kept_per_type": dict(sorted(per_type.items())),
        "distinct_seed_inputs": len({seed_key(r) for r in final}),
    }
    return final, report


def write_store(path: str | Path, rows: Sequence[dict]) -> int:
    return common.jsonl_write_atomic(path, rows)
