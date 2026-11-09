"""Leak-proof cluster-level splits for M2 (Shaurya-owned).

Contract: every input_key (cluster) lands in exactly ONE of train / val / cal / test.
 * any cluster that is in B1, B2, C_verifier, gold or C_human is test-only (reported, with its cost);
 * clusters in `force_cal` (inputs the deployment generator never trained on, e.g. A_val-only inputs) go to cal first;
 * the rest is assigned per rule family by a seeded hash, in `fracs` proportions (train, val, cal);
 * deterministic; written with a sha256 so later scripts can refuse a different split.
LOFO: lofo_splits(splits, family) puts one family in test and removes it from train/val/cal.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

PARTS = ("train", "val", "cal", "test")


def _h(seed: int, key: str) -> int:
    return int(hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest(), 16)


def build_splits(clusters: Mapping[str, str], test_only: Iterable[str], force_cal: Iterable[str] = (),
                 seed: int = 1337, fracs: tuple[float, float, float] = (0.6, 0.2, 0.2)) -> dict[str, Any]:
    """clusters: {input_key: family}. Returns {"parts": {part: [keys]}, "family": {...}, "seed", "fracs", "sha256"}."""
    if abs(sum(fracs) - 1.0) > 1e-9:
        raise ValueError("fracs must sum to 1")
    test_only, force_cal = set(test_only), set(force_cal)
    parts: dict[str, list[str]] = {p: [] for p in PARTS}
    by_fam: dict[str, list[str]] = defaultdict(list)
    for k, fam in sorted(clusters.items()):
        if k in test_only:
            parts["test"].append(k)
        elif k in force_cal:
            parts["cal"].append(k)
        else:
            by_fam[fam].append(k)
    for fam, keys in sorted(by_fam.items()):
        keys.sort(key=lambda k: _h(seed, k))
        n = len(keys)
        n_tr = int(round(fracs[0] * n))
        n_va = int(round(fracs[1] * n))
        if n >= 3:                                   # every family with >= 3 free clusters shows up in val and cal
            n_va = max(n_va, 1)
            n_tr = min(n_tr, n - n_va - 1)
        parts["train"] += keys[:n_tr]
        parts["val"] += keys[n_tr:n_tr + n_va]
        parts["cal"] += keys[n_tr + n_va:]
    for p in PARTS:
        parts[p] = sorted(parts[p])
    counts: dict[str, dict[str, int]] = {p: defaultdict(int) for p in PARTS}
    for p in PARTS:
        for k in parts[p]:
            counts[p][clusters[k]] += 1
    out = {"parts": parts, "family": {k: clusters[k] for k in sorted(clusters)}, "seed": seed, "fracs": list(fracs),
           "counts": {p: dict(sorted(c.items())) for p, c in counts.items()},
           "n_test_only_forced": len(test_only & set(clusters))}
    out["sha256"] = splits_hash(out)
    assert_disjoint(out)
    return out


def splits_hash(splits: Mapping[str, Any]) -> str:
    body = {"parts": splits["parts"], "seed": splits["seed"], "fracs": splits["fracs"]}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def assert_disjoint(splits: Mapping[str, Any]) -> None:
    seen: dict[str, str] = {}
    for p in PARTS:
        for k in splits["parts"][p]:
            if k in seen:
                raise AssertionError(f"cluster in two partitions: {seen[k]} and {p}")
            seen[k] = p
    if set(seen) != set(splits["family"]):
        raise AssertionError("partitions do not cover exactly the cluster universe")


def lofo_splits(splits: Mapping[str, Any]) -> Iterator[tuple[str, dict[str, list[str]]]]:
    """Yield (family, parts) where `family` is test-only and absent from train/val/cal."""
    fam = splits["family"]
    for f in sorted(set(fam.values())):
        parts = {p: [k for k in splits["parts"][p] if fam[k] != f] for p in ("train", "val", "cal")}
        parts["test"] = sorted(k for p in PARTS for k in splits["parts"][p] if fam[k] == f)
        yield f, parts


def cell_table(splits: Mapping[str, Any], threshold: int = 59) -> str:
    fams = sorted(set(splits["family"].values()))
    L = ["| family | " + " | ".join(PARTS) + " |", "|---|" + "---|" * len(PARTS)]
    for f in fams:
        cells = []
        for p in PARTS:
            n = splits["counts"][p].get(f, 0)
            cells.append(f"{n}{'*' if n < threshold else ''}")
        L.append(f"| {f} | " + " | ".join(cells) + " |")
    return "\n".join(L) + f"\n\n(* = fewer than {threshold} clusters: the rule of 59 cannot be met in that cell)\n"


def write_splits(path: str | Path, splits: Mapping[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(splits, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def read_splits(path: str | Path) -> dict[str, Any]:
    s = json.loads(Path(path).read_text(encoding="utf-8"))
    if s["sha256"] != splits_hash(s):
        raise AssertionError("splits.json hash does not match its content")
    assert_disjoint(s)
    return s
