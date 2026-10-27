"""Unit tests for ml.train_m2.eval.audit_harvest (synthetic data)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List

import pytest

from ml.train_m2.common import repo_root
from ml.train_m2.eval.audit_harvest import (
    canonical_answer,
    conformance,
    count_crlf,
    digest_present,
    expected_settings,
    finding_id_mismatches,
    greedy_mismatch_seen_share,
    key_set,
    match_hashes,
    mean_distinct,
    modelfile_params,
    overlap,
    read_jsonl,
    recorded_digests,
    strip_digest,
    token_report,
)


def test_token_report_hand_built() -> None:
    # 3-token valid list
    tokens = [
        {"t": "a", "lp": -0.1, "top": [["a", -0.1], ["b", -0.5], ["c", -1.0], ["d", -2.0], ["e", -3.0]]},
        {"t": "b", "lp": -0.8, "top": [["x", -0.2], ["b", -0.8], ["c", -1.0], ["d", -2.0], ["e", -3.0]]},
        {"t": "c", "lp": -0.0, "top": [["c", -0.0], ["b", -0.5], ["x", -1.0], ["d", -2.0], ["e", -3.0]]},
    ]
    rep = token_report(tokens)
    assert rep["n_tokens"] == 3
    assert rep["bad_lp"] == 0
    assert rep["min_top_width"] == 5
    assert rep["top_sorted_desc"] == 3
    assert rep["chosen_in_top"] == 3
    assert rep["chosen_is_top1"] == 2  # first and third
    assert rep["text"] == "abc"

    # Flag positive lp, NaN, width-4
    bad_tokens = [
        {"t": "x", "lp": 0.5, "top": [["x", 0.5], ["y", -0.1]]},  # positive lp, width 2
        {"t": "y", "lp": float("nan"), "top": [["y", -0.1], ["z", -0.2], ["w", -0.3], ["v", -0.4]]},  # NaN, width 4
    ]
    bad_rep = token_report(bad_tokens)
    assert bad_rep["bad_lp"] == 2
    assert bad_rep["min_top_width"] == 2


def test_greedy_mismatch_seen_share() -> None:
    # Row 1: sample_idx 0, contains mismatch where top1 was seen earlier
    rows = [
        {
            "sample_idx": 0,
            "tokens": [
                {"t": "tok1", "lp": -0.1, "top": [["tok1", -0.1]]},
                {"t": "tok2", "lp": -0.5, "top": [["tok1", -0.2]]},  # mismatch, top1 ('tok1') seen earlier
            ],
        },
        {
            "sample_idx": 1,  # Must be ignored
            "tokens": [
                {"t": "other", "lp": -0.5, "top": [["diff", -0.1]]},
            ],
        },
    ]
    res = greedy_mismatch_seen_share(rows)
    assert res["match"] == 1
    assert res["mismatch"] == 1
    assert res["mismatch_top1_seen"] == 1
    assert res["mismatch_share"] == 1.0


def test_expected_settings_and_conformance() -> None:
    # (A, 0)
    exp_a0 = expected_settings("A", 0)
    assert exp_a0 == {"temperature": 0.0, "seed": 0, "top_p": None}

    # (A, 3)
    exp_a3 = expected_settings("A", 3)
    assert exp_a3 == {"temperature": 0.7, "seed": 3, "top_p": None}

    # (B, 3)
    exp_b3 = expected_settings("B", 3)
    assert exp_b3 == {"temperature": 1.0, "seed": 1003, "top_p": 0.95}

    # Conformance flags temperature 1.0 on profile A, non-null top_p, missing seed
    bad_row_temp = {"profile": "A", "sample_idx": 1, "temperature": 1.0, "seed": 1, "top_p": None}
    assert any("temperature" in s for s in conformance(bad_row_temp))

    bad_row_topp = {"profile": "A", "sample_idx": 1, "temperature": 0.7, "seed": 1, "top_p": 0.9}
    assert any("top_p" in s for s in conformance(bad_row_topp))

    bad_row_seed = {"profile": "A", "sample_idx": 1, "temperature": 0.7, "top_p": None}
    assert any("seed" in s for s in conformance(bad_row_seed))


def test_modelfile_params_case_insensitive() -> None:
    text = (
        "FROM base\n"
        "PARAMETER presence_penalty 1.5\n"
        "parameter TEMPERATURE 1\n"
        "Parameter Top_P 0.95\n"
    )
    p = modelfile_params(text)
    assert p["presence_penalty"] == ["1.5"]
    assert p["temperature"] == ["1"]
    assert p["top_p"] == ["0.95"]


def test_digests_and_match_hashes(tmp_path: Path) -> None:
    manifest = {
        "model_digest": "sha256:02e86d0a0b5e35052997c8f4396a8c1e752d1fda7c58abbbccd111e8ea74d53e",
        "short_digest": "123456789abc",
    }
    digs = recorded_digests(manifest)
    assert "02e86d0a0b5e35052997c8f4396a8c1e752d1fda7c58abbbccd111e8ea74d53e" in digs
    assert "123456789abc" in digs

    # digest_present prefix logic
    assert digest_present(digs, "02e86d0a0b5e")
    assert not digest_present(digs, "deadbeef")

    # match_hashes returns match_after_crlf_to_lf for CRLF file whose LF hash is recorded
    lf_content = b"hello\nworld\n"
    import hashlib
    lf_hash = hashlib.sha256(lf_content).hexdigest()
    crlf_file = tmp_path / "crlf.txt"
    crlf_file.write_bytes(b"hello\r\nworld\r\n")

    full_recorded = {lf_hash, "short"}
    res = match_hashes(full_recorded, [crlf_file])
    assert res["crlf.txt"] == "match_after_crlf_to_lf"


def test_count_crlf_and_read_jsonl(tmp_path: Path) -> None:
    data_file = tmp_path / "lines.bin"
    data_file.write_bytes(b"a\r\nb\n")
    crlf, lf = count_crlf(data_file)
    assert crlf == 1
    assert lf == 1

    jsonl_file = tmp_path / "test.jsonl"
    jsonl_file.write_text('{"a": 1}\r\n\r\n{"b": 2}\n', encoding="utf-8")
    rows = list(read_jsonl(jsonl_file))
    assert len(rows) == 2
    assert rows[0] == {"a": 1}
    assert rows[1] == {"b": 2}


def test_canonical_answer() -> None:
    c1 = json.dumps({"ops": [{"op": "set_attr", "attr": "x", "value": 1}], "rationale_ref": "rule1"})
    c2 = json.dumps({"rationale_ref": "rule1", "ops": [{"value": 1, "attr": "x", "op": "set_attr"}]})
    assert canonical_answer(c1) == canonical_answer(c2)
    assert canonical_answer("bad json") == "PARSEFAIL"


def test_mean_distinct() -> None:
    rows = [
        {"input_key": "k1", "content": json.dumps({"ops": [], "rationale_ref": "r1"})},
        {"input_key": "k1", "content": json.dumps({"ops": [], "rationale_ref": "r1"})},
        {"input_key": "k2", "content": json.dumps({"ops": [1], "rationale_ref": "r1"})},
        {"input_key": "k2", "content": json.dumps({"ops": [2], "rationale_ref": "r1"})},
        {"input_key": "k3", "content": json.dumps({"ops": [1], "rationale_ref": "r1"})},
    ]
    mean_val, count = mean_distinct(rows)
    assert count == 3
    assert math.isclose(mean_val, 4 / 3, rel_tol=1e-3)

    m_filt, c_filt = mean_distinct(rows, only_keys={"k2"})
    assert c_filt == 1
    assert m_filt == 2.0


def test_finding_id_mismatches() -> None:
    examples = [
        {
            "input": {"rule_id": "rule_a", "fields": {"resource_type": "AWSAccount"}, "resource_ref": "R1", "finding_id": "F-0"},
            "rule_id": "rule_a",
        },
        {
            "input": {"rule_id": "rule_a", "fields": {"resource_type": "AWSAccount"}, "resource_ref": "R1", "finding_id": "F-1"},
            "rule_id": "rule_a",
        },
    ]
    from ml.train_m2.common import cluster_key
    k_ex0 = cluster_key(examples[0]["input"])
    inputs_by_key_test = {
        k_ex0: {"record": {"finding_id": "F-0"}},
    }
    res = finding_id_mismatches(examples, inputs_by_key_test)
    assert res.get("rule_a") == 1
    assert res.get("_total") == 1


def test_overlap_and_key_set(tmp_path: Path) -> None:
    a = {"k1", "k2", "k3"}
    b = {"k2", "k3", "k4"}
    ov = overlap(a, b)
    assert ov == {"a": 3, "b": 3, "shared": 2}

    jsonl_file = tmp_path / "keys.jsonl"
    jsonl_file.write_text(
        '{"input_key": "k1"}\n'
        '{"input": {"rule_id": "dpdp.rule6_account_mfa", "fields": {"resource_type": "AWSAccount"}, "resource_ref": "R1", "finding_id": "F-0"}}\n'
        '{"invalid": 1}\n',
        encoding="utf-8"
    )
    keys, bad = key_set(jsonl_file)
    assert "k1" in keys
    assert len(keys) == 2
    assert bad == 1


def test_report_writer_no_leaked_paths(tmp_path: Path) -> None:
    """Audit report contains no leaked absolute paths or user names."""
    from ml.train_m2.eval.audit_harvest import main

    out_prefix = tmp_path / "audit_test"
    ret = main(["--out", str(out_prefix)])
    assert ret == 0

    root_str = str(repo_root()).replace("\\", "/")
    home_str = str(Path.home()).replace("\\", "/")
    leak_patterns = [root_str, home_str, "C:/Users", "C:\\Users", "Desktop"]

    for ext in [".md", ".json", ".json.provenance.json"]:
        f = tmp_path / f"audit_test{ext}"
        if f.exists():
            content = f.read_text(encoding="utf-8", errors="ignore")
            for pat in leak_patterns:
                assert pat not in content, f"Leaked path {pat!r} found in {f.name}"
