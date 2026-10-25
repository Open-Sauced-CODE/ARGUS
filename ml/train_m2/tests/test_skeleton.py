"""Skeleton tests for the Phase 6 Trust Engine: imports, seeding, atomic IO, cluster keys, input list."""

from __future__ import annotations

import importlib
import json
import os
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from ml.train_m2 import common
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

SUBPACKAGES = ("labels", "features", "models", "risk", "monitor", "eval", "tests")
RECORD = {
    "rule_id": "dpdp.rule6_account_mfa",
    "fields": {"account_mfa_enabled": False, "resource_type": "AWSAccount"},
    "resource_ref": "RESOURCE_1",
    "finding_id": "F-0",
}


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_imports(name: str) -> None:
    module = importlib.import_module(f"ml.train_m2.{name}")
    assert module.__doc__


def test_configs_is_not_a_package() -> None:
    assert not (repo_root() / "ml" / "train_m2" / "configs" / "__init__.py").exists()


def test_no_init_in_phase1_skeleton() -> None:
    """Hard rule 3."""
    assert not (repo_root() / "ml" / "mutation_engine" / "phase1_skeleton" / "__init__.py").exists()


def test_set_seed_is_deterministic() -> None:
    first = (set_seed(7).random(5).tolist(), random.random(), float(np.random.rand()))
    second = (set_seed(7).random(5).tolist(), random.random(), float(np.random.rand()))
    other = (set_seed(8).random(5).tolist(), random.random(), float(np.random.rand()))
    assert first == second
    assert first != other


@pytest.mark.parametrize("bad", [-1, 1.5, "7", True, None])
def test_set_seed_rejects_bad_seed(bad: object) -> None:
    with pytest.raises(ValueError):
        set_seed(bad)  # type: ignore[arg-type]


def test_sha256_file_known_value(tmp_path: Path) -> None:
    path = tmp_path / "abc.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * 3_000_000)
    assert sha256_file(big, chunk_size=1000) == sha256_file(big)


def test_jsonl_round_trip_is_ascii_sorted_and_lf(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    rows = [{"b": 1, "a": "caf\u00e9"}, {"z": [1, 2], "y": None}]
    assert jsonl_write_atomic(path, rows) == 2
    raw = path.read_bytes()
    raw.decode("ascii")
    assert b"\r" not in raw
    assert raw.splitlines()[0] == b'{"a":"caf\\u00e9","b":1}'
    assert list(jsonl_iter(path)) == rows


def test_jsonl_iter_skips_blank_lines_and_names_bad_line(tmp_path: Path) -> None:
    path = tmp_path / "b.jsonl"
    path.write_text('{"a":1}\n\n   \n{"a":\n', encoding="utf-8")
    it = jsonl_iter(path)
    assert next(it) == {"a": 1}
    with pytest.raises(ValueError, match=r"b\.jsonl:4"):
        next(it)


def test_atomic_write_keeps_old_file_if_rename_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "keep.jsonl"
    jsonl_write_atomic(path, [{"v": "old"}])
    before = path.read_bytes()

    def boom(src: str, dst: str) -> None:
        raise OSError("simulated crash between temp write and rename")

    monkeypatch.setattr(common.os, "replace", boom)
    with pytest.raises(OSError):
        jsonl_write_atomic(path, [{"v": "new"}])
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keep.jsonl"], "temp file must be cleaned up"


def test_atomic_write_keeps_old_file_if_rows_raise_midway(tmp_path: Path) -> None:
    path = tmp_path / "keep2.jsonl"
    jsonl_write_atomic(path, [{"v": "old"}])
    before = path.read_bytes()

    def rows():
        yield {"v": 1}
        raise RuntimeError("generator failed")

    with pytest.raises(RuntimeError):
        jsonl_write_atomic(path, rows())
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keep2.jsonl"]


def test_atomic_write_creates_parent_dirs_and_replaces(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "er" / "x.jsonl"
    jsonl_write_atomic(path, [{"n": 1}])
    jsonl_write_atomic(path, [{"n": 2}, {"n": 3}])
    assert [r["n"] for r in jsonl_iter(path)] == [2, 3]


def test_cluster_key_accepts_bare_record_and_full_example() -> None:
    assert cluster_key(RECORD) == cluster_key({"input": RECORD})
    assert cluster_key(RECORD) == cluster_key({**RECORD, "finding_id": "F-999"}), "finding_id must not matter"
    changed = {**RECORD, "fields": {**RECORD["fields"], "account_mfa_enabled": True}}
    assert cluster_key(changed) != cluster_key(RECORD)


def test_cluster_key_stable_across_processes() -> None:
    code = (
        "import json,sys;from ml.train_m2.common import cluster_key;"
        "print(cluster_key(json.loads(sys.argv[1])))"
    )
    results = set()
    for hash_seed in ("0", "1", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        out = subprocess.run(
            [sys.executable, "-c", code, json.dumps(RECORD)],
            cwd=str(repo_root()), env=env, capture_output=True, text=True, check=True,
        )
        results.add(out.stdout.strip())
    assert results == {cluster_key(RECORD)}


def test_harvest_inputs_are_the_frozen_321() -> None:
    inputs = load_inputs()
    assert len(inputs) == 321
    keys = [r["input_key"] for r in inputs]
    assert len(set(keys)) == 321
    for row in inputs:
        assert cluster_key(row["record"]) == row["input_key"], row["input_key"][:80]


def test_load_inputs_matches_file_line_count() -> None:
    path = repo_root() / common.HARVEST_INPUTS_RELPATH
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == len(load_inputs()) == 321


def test_provenance_has_required_fields(tmp_path: Path) -> None:
    src = tmp_path / "in.txt"
    src.write_bytes(b"abc")
    prov = provenance({"task": "t"}, inputs=[src], seed=42, argv=["prog", "--x"])
    assert prov["input_sha256"][str(src)] == sha256_file(src)
    assert prov["seed"] == 42 and prov["argv"] == ["prog", "--x"] and prov["extra"] == {"task": "t"}
    assert prov["utc_time"].endswith("Z") and len(prov["utc_time"]) == 20
    assert prov["python"].startswith("3.")
    assert "numpy" in prov["packages"] and "pytest" in prov["packages"]
    assert prov["git_commit"] == "unknown" or len(prov["git_commit"]) == 40
    json.dumps(prov)


def test_write_provenance_lands_next_to_output(tmp_path: Path) -> None:
    out = tmp_path / "result.json"
    out.write_text("{}", encoding="utf-8")
    written = write_provenance(out, extra={"k": 1}, argv=["x"])
    assert written == tmp_path / "result.json.provenance.json"
    assert json.loads(written.read_text(encoding="utf-8"))["extra"] == {"k": 1}


def test_owned_python_files_are_ascii_only() -> None:
    """Style rule: ASCII-only sources in Shaurya's package."""
    root = repo_root() / "ml" / "train_m2"
    offenders = []
    for path in root.rglob("*.py"):
        if "harvest" in path.parts:
            continue
        try:
            path.read_bytes().decode("ascii")
        except UnicodeDecodeError:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
