"""Shared helpers for the Phase 6 Trust Engine (Shaurya's track).

Contract (all functions are pure or only touch the paths they are given):

* set_seed(seed)               -> numpy Generator; seeds ``random`` and numpy's legacy global state too.
* provenance(...)              -> JSON-ready dict describing exactly how an output was produced.
* write_provenance(out, ...)   -> writes ``<out>.provenance.json`` next to an output file.
* repo_root()                  -> absolute path of the repository root.
* cluster_key(record)          -> the Phase 5 input key; THE statistical unit of Phase 6 (hard rule 7).
* sha256_file(path)            -> hex digest, streamed.
* jsonl_iter(path)             -> lazily yields one dict per non-blank line, with line numbers in errors.
* jsonl_write_atomic(path, rows) -> all-or-nothing JSONL write (temp file, fsync, rename).
* load_inputs()                -> the 321 harvest inputs from the frozen contract.

Everything written is ASCII-only JSON with sorted keys, so identical data gives identical bytes.
"""

from __future__ import annotations

import hashlib
import importlib.metadata as importlib_metadata
import json
import logging
import os
import platform
import random
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np

from ml.mutation_engine.dataset_io import input_key as _phase5_input_key

LOG = logging.getLogger(__name__)

DEFAULT_SEED = 1337
HARVEST_INPUTS_RELPATH = Path("ml") / "train_m2" / "contract" / "harvest_inputs.jsonl"
TRACKED_PACKAGES = (
    "numpy", "scipy", "pandas", "scikit-learn", "lightgbm", "matplotlib", "joblib", "jsonschema", "pytest",
)

__all__ = [
    "DEFAULT_SEED", "set_seed", "repo_root", "sha256_file", "cluster_key", "jsonl_iter",
    "jsonl_write_atomic", "load_inputs", "provenance", "write_provenance",
]


def set_seed(seed: int = DEFAULT_SEED) -> np.random.Generator:
    """Seed every RNG this project uses and return a fresh numpy Generator.

    Prefer passing the returned Generator around over relying on global state. The global
    ``random`` and ``numpy.random`` states are seeded as well so third-party code is reproducible.
    """
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError(f"seed must be a non-negative int, got {seed!r}")
    random.seed(seed)
    np.random.seed(seed % (2**32))
    return np.random.default_rng(seed)


def repo_root() -> Path:
    """Absolute repository root, located relative to this file and sanity-checked."""
    root = Path(__file__).resolve().parents[2]
    if not (root / "ml" / "train_m2" / "OWNERS.json").is_file():
        raise RuntimeError(f"repo root guess {root} does not contain ml/train_m2/OWNERS.json")
    return root


def sha256_file(path: str | os.PathLike[str], chunk_size: int = 1 << 20) -> str:
    """SHA-256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def cluster_key(record: Mapping[str, Any]) -> str:
    """Phase 5 input key (the CLUSTER id) for a record.

    Accepts either a full example ``{"input": {rule_id, fields, resource_ref, ...}}`` or the bare
    input record ``{rule_id, fields, resource_ref, ...}`` (the shape stored in harvest_inputs.jsonl).
    It always delegates to ``ml.mutation_engine.dataset_io.input_key`` so the definition cannot drift.
    """
    example = record if "input" in record else {"input": record}
    return _phase5_input_key(example)


def jsonl_iter(path: str | os.PathLike[str]) -> Iterator[dict[str, Any]]:
    """Yield one parsed object per non-blank line; a bad line raises ValueError naming file and line."""
    with open(path, "r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                yield json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON ({exc.msg})") from exc


def _dump(row: Any) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def jsonl_write_atomic(path: str | os.PathLike[str], rows: Iterable[Any]) -> int:
    """Write rows as JSONL so that readers see either the complete old file or the complete new one.

    Rows are written to a temp file in the same directory, flushed and fsynced, then moved over the
    target with ``os.replace``. Any failure (including an exception raised by ``rows`` itself) removes
    the temp file and leaves the previous target untouched. Returns the number of rows written.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    count = 0
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(_dump(row))
                handle.write("\n")
                count += 1
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return count


def load_inputs(path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    """Load the 321 harvest inputs from the frozen contract (or from ``path`` for tests)."""
    source = Path(path) if path is not None else repo_root() / HARVEST_INPUTS_RELPATH
    return list(jsonl_iter(source))


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(repo_root()), capture_output=True, text=True, timeout=20, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError, RuntimeError):
        return "unknown"


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in TRACKED_PACKAGES:
        try:
            versions[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def provenance(
    extra: Mapping[str, Any] | None = None,
    *,
    inputs: Sequence[str | os.PathLike[str]] = (),
    seed: int | None = DEFAULT_SEED,
    argv: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Describe how an output was produced (hard rule 4).

    Records git commit and dirty flag, python and package versions, SHA-256 of every input file,
    the seed, the UTC time and the command line. ``extra`` is merged under the key ``extra``.
    """
    input_hashes = {str(p): sha256_file(p) for p in inputs}
    status = _git("status", "--porcelain")
    return {
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": None if status == "unknown" else bool(status),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": _package_versions(),
        "input_sha256": input_hashes,
        "seed": seed,
        "utc_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "argv": list(sys.argv if argv is None else argv),
        "extra": dict(extra) if extra else {},
    }


def write_provenance(output_path: str | os.PathLike[str], **kwargs: Any) -> Path:
    """Write ``<output_path>.provenance.json`` atomically and return its path."""
    out = Path(str(output_path) + ".provenance.json")
    jsonl_write_atomic(out, [provenance(**kwargs)])
    return out
