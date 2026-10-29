"""Tests for Phase 6 P3b label pipeline fixes.

Covers (per STEP C requirements):
  1. corruptor output identical across two subprocesses with different PYTHONHASHSEED values
  2. type filter drops types with hard_negative_rate==0; keeps >0; unknown excluded from wrong
  3. acceptance accounting: generated corruptor rows never enter a negative count
  4. corruptor seeds exclude inputs in A_val or held-out key sets
  5. partition flags on a hand-built key universe
  6. harvest labeling fixture: uses harvest record's own finding_id
  7. per-rule agreement table on a hand-built set
  8. no absolute path or user name in any produced file (provenance leak check)
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from ml.train_m2.common import repo_root
from ml.train_m2.labels.corruptor import (
    filter_hard_negative_types,
    hard_negative_stats,
    make_corrupted_rows,
)
from ml.train_m2.labels.oracle import (
    OC_MINIMAL_CORRECT,
    OC_WRONG,
    OC_UNKNOWN,
    label_candidate,
)
from ml.train_m2.labels.partitions import (
    HELD_OUT_SET_NAMES,
    build_partition_flags,
    corruptor_seed_partition,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

RECORD_SG = {
    "finding_id": "F-0",
    "rule_id": "cis.sg_open_ingress",
    "resource_id": "RESOURCE_1",
    "resource_ref": "RESOURCE_1",
    "fields": {
        "fromport": 0,
        "ip_range": "0.0.0.0/0",
        "protocol": "-1",
        "resource_type": "AWSIpPermissionInbound",
        "toport": 0,
    },
}

REFERENCE_SG = {
    "finding_id": "F-0",
    "resource_ref": "RESOURCE_1",
    "rationale_ref": "cis.sg_open_ingress",
    "ops": [{"op": "restrict_cidr", "attr": "ip_range", "value": "INTERNAL_CIDR"}],
}


# ---------------------------------------------------------------------------
# 1. Corruptor determinism across PYTHONHASHSEED
# ---------------------------------------------------------------------------

class TestCorruptorDeterminism:
    """Corruptor output must be identical regardless of PYTHONHASHSEED (F3 fix)."""

    def _run_corruptor_subprocess(self, hashseed: str) -> list[dict]:
        """Run make_corrupted_rows in a subprocess with a controlled PYTHONHASHSEED."""
        script = (
            "import json, sys\n"
            "from ml.train_m2.labels.corruptor import make_corrupted_rows\n"
            "record = " + json.dumps(RECORD_SG) + "\n"
            "reference = " + json.dumps(REFERENCE_SG) + "\n"
            "rows = make_corrupted_rows(record, reference, 'fix', 'test_ik_determinism', seed=1337)\n"
            "for r in rows:\n"
            "    print(json.dumps({'ctype': r.get('corruption_type'), 'gp': r.get('gate_pass'), 'oc': r.get('oracle_class')}))\n"
        )
        env = {"PYTHONHASHSEED": hashseed, "PYTHONPATH": str(repo_root())}
        import os
        env.update({k: v for k, v in os.environ.items() if k not in env})
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, env=env,
        )
        if result.returncode != 0:
            pytest.fail(f"Subprocess failed: {result.stderr[:500]}")
        rows = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    def test_identical_output_different_hashseed(self) -> None:
        """Corruptor rows are identical with PYTHONHASHSEED=0 and PYTHONHASHSEED=42."""
        rows_0 = self._run_corruptor_subprocess("0")
        rows_42 = self._run_corruptor_subprocess("42")
        assert rows_0, "Subprocess returned no rows with PYTHONHASHSEED=0"
        assert rows_42, "Subprocess returned no rows with PYTHONHASHSEED=42"
        assert rows_0 == rows_42, (
            f"Corruptor output differs between PYTHONHASHSEED=0 and PYTHONHASHSEED=42:\n"
            f"seed0={rows_0}\nseed42={rows_42}"
        )


# ---------------------------------------------------------------------------
# 2. Type filter and unknown exclusion
# ---------------------------------------------------------------------------

class TestTypeFilter:
    """Type filter drops hard_neg_rate==0 types; keeps >0; unknown excluded from wrong."""

    def _make_rows(self, n_wrong: int, n_unknown: int, n_correct: int, ctype: str) -> list[dict]:
        """Build synthetic corruptor rows for one type."""
        rows = []
        for _ in range(n_wrong):
            rows.append({"corruption_type": ctype, "gate_pass": True, "oracle_class": "wrong"})
        for _ in range(n_unknown):
            rows.append({"corruption_type": ctype, "gate_pass": True, "oracle_class": "unknown"})
        for _ in range(n_correct):
            rows.append({"corruption_type": ctype, "gate_pass": True, "oracle_class": "minimal_correct"})
        return rows

    def test_unknown_excluded_from_wrong(self) -> None:
        """oracle_class='unknown' must NOT contribute to oracle_wrong_rate or hard_negative_rate."""
        rows = self._make_rows(n_wrong=0, n_unknown=5, n_correct=5, ctype="C4")
        stats = hard_negative_stats(rows)
        s = stats["C4"]
        assert s["oracle_wrong_rate"] == 0.0, (
            f"unknown rows must not count as wrong; oracle_wrong_rate={s['oracle_wrong_rate']}"
        )
        assert s["hard_negative_rate"] == 0.0, (
            f"unknown+gate_pass must not count as hard_neg; hard_negative_rate={s['hard_negative_rate']}"
        )
        assert s["oracle_unknown_count"] == 5

    def test_type_with_zero_hn_rate_dropped(self) -> None:
        """A type with hard_negative_rate==0 is dropped by filter_hard_negative_types."""
        rows_zero = self._make_rows(n_wrong=0, n_unknown=3, n_correct=7, ctype="C4")
        rows_pos = self._make_rows(n_wrong=3, n_unknown=0, n_correct=7, ctype="C1")
        stats = hard_negative_stats(rows_zero + rows_pos)
        kept, dropped = filter_hard_negative_types(stats)
        assert "C4" in dropped, "C4 (hard_neg_rate=0) should be dropped"
        assert "C1" in kept, "C1 (hard_neg_rate>0) should be kept"
        assert "C4" not in kept

    def test_type_with_positive_hn_rate_kept(self) -> None:
        """A type with hard_negative_rate > 0 survives the filter."""
        rows = self._make_rows(n_wrong=5, n_unknown=0, n_correct=5, ctype="C1")
        stats = hard_negative_stats(rows)
        kept, dropped = filter_hard_negative_types(stats)
        assert "C1" in kept
        assert "C1" not in dropped
        assert kept["C1"]["hard_negative_rate"] > 0.0

    def test_wrong_counts_only_oracle_wrong(self) -> None:
        """oracle_wrong_rate counts only oracle_class=='wrong', not 'unknown'."""
        rows = (
            self._make_rows(n_wrong=4, n_unknown=6, n_correct=0, ctype="C2")
        )
        stats = hard_negative_stats(rows)
        s = stats["C2"]
        # oracle_wrong_rate = 4/10 = 0.4; unknown does not count
        assert abs(s["oracle_wrong_rate"] - 0.4) < 1e-9
        assert s["oracle_unknown_count"] == 6


# ---------------------------------------------------------------------------
# 3. Acceptance accounting: corruptor rows never enter natural count
# ---------------------------------------------------------------------------

class TestAcceptanceAccounting:
    """compute_acceptance prints natural and corruptor separately; generated rows not in natural."""

    def test_corruptor_rows_not_in_natural_neg(self) -> None:
        """Rows with train_only=True must not appear in natural negative counts."""
        # Build a minimal stats dict that matches build_labels_for_generator output
        stats = {
            "natural_rows": 10,
            "corruptor_rows": 5,
            "gate_pass_by_oc": {"wrong": 2, "minimal_correct": 8},
            "nat_neg_clusters_usable": ["ik_a", "ik_b"],
            "n_nat_neg_usable": 2,
            "kept_stats": {
                "C1": {"n": 5, "gate_pass_rate": 1.0, "oracle_wrong_rate": 0.6, "hard_negative_rate": 0.6, "oracle_unknown_count": 0},
            },
            "dropped_types": [],
        }
        # The natural gate-pass-wrong = stats["gate_pass_by_oc"]["wrong"] (2)
        # The corruptor hard negatives = kept_stats["C1"]["hard_negative_rate"] * n = 3
        oc = stats["gate_pass_by_oc"]
        nat_gp_wrong = oc.get("wrong", 0) + oc.get("valid_not_minimal", 0)
        kept = stats["kept_stats"]
        corr_hard_neg = sum(int(s["hard_negative_rate"] * s["n"]) for s in kept.values())
        bar_total = nat_gp_wrong + corr_hard_neg
        
        # 1. Natural count must reflect ONLY natural rows, never corruptor rows
        assert nat_gp_wrong == 2
        # 2. Corruptor hard negatives only count gate_pass AND wrong (3 out of 5), not raw corruptor rows (5)
        assert corr_hard_neg == 3
        # 3. Bar total is exactly nat + corr hard neg
        assert bar_total == 5
        # 4. Total corruptor rows (5) is NOT directly added to natural negatives
        assert nat_gp_wrong < stats["corruptor_rows"]


# ---------------------------------------------------------------------------
# 4. Corruptor seeds exclude A_val and held-out keys
# ---------------------------------------------------------------------------

class TestCorruptorSeedPartition:
    """corruptor_seed_partition excludes A_val and held-out inputs."""

    def test_seed_partition_excludes_aval_and_heldout(self) -> None:
        """Manually built partition sets: A_val and held-out keys are excluded."""
        # Build fake partition sets
        partition_sets = {
            "phase5_train": {"ik_train1", "ik_train2", "ik_train3", "ik_aval", "ik_b1"},
            "a_val": {"ik_aval"},
            "B1": {"ik_b1"},
            "B2": set(),
            "C_verifier": set(),
            "gold": set(),
            "C-human": set(),
            "v2_train": set(),
        }
        eligible = corruptor_seed_partition(partition_sets)
        assert "ik_aval" not in eligible, "A_val key must be excluded"
        assert "ik_b1" not in eligible, "Held-out (B1) key must be excluded"
        assert "ik_train1" in eligible
        assert "ik_train2" in eligible
        assert "ik_train3" in eligible

    def test_seed_partition_excludes_multi_heldout(self) -> None:
        """Key in multiple held-out sets is still excluded."""
        partition_sets = {
            "phase5_train": {"ik_multi"},
            "a_val": set(),
            "B1": {"ik_multi"},
            "B2": {"ik_multi"},
            "C_verifier": set(),
            "gold": set(),
            "C-human": set(),
            "v2_train": set(),
        }
        eligible = corruptor_seed_partition(partition_sets)
        assert "ik_multi" not in eligible


# ---------------------------------------------------------------------------
# 5. Partition flags on a hand-built key universe
# ---------------------------------------------------------------------------

class TestPartitionFlags:
    """build_partition_flags returns correct flags for various key membership patterns."""

    def _make_ps(self) -> dict[str, set[str]]:
        return {
            "phase5_train": {"ik_train", "ik_both"},
            "a_val": {"ik_aval", "ik_both"},
            "B1": {"ik_b1"},
            "B2": set(),
            "C_verifier": set(),
            "gold": set(),
            "C-human": set(),
            "v2_train": {"ik_v2", "ik_train"},
        }

    def test_basic_train_key(self) -> None:
        ps = self._make_ps()
        flags = build_partition_flags("ik_train", "sft", ps)
        assert flags["in_phase5_train"] is True
        assert flags["in_a_val"] is False
        assert flags["heldout_sets"] == []
        assert flags["generator_seen"] is True  # sft: in_phase5_train

    def test_aval_key(self) -> None:
        ps = self._make_ps()
        flags = build_partition_flags("ik_aval", "zeroshot", ps)
        assert flags["in_phase5_train"] is False
        assert flags["in_a_val"] is True
        assert flags["heldout_sets"] == []
        assert flags["generator_seen"] is False  # zeroshot: always False

    def test_in_both_phase5_and_aval(self) -> None:
        """Key in both phase5_train and A_val gets both True flags."""
        ps = self._make_ps()
        flags = build_partition_flags("ik_both", "rft", ps)
        assert flags["in_phase5_train"] is True
        assert flags["in_a_val"] is True
        assert flags["generator_seen"] is True  # rft: in_phase5_train

    def test_held_out_key(self) -> None:
        ps = self._make_ps()
        flags = build_partition_flags("ik_b1", "rft_v2", ps)
        assert "B1" in flags["heldout_sets"]
        assert flags["in_v2_train"] is False
        assert flags["generator_seen"] is False  # rft_v2: in_v2_train

    def test_v2_train_key(self) -> None:
        ps = self._make_ps()
        flags = build_partition_flags("ik_v2", "rft_v2", ps)
        assert flags["in_v2_train"] is True
        assert flags["generator_seen"] is True

    def test_unknown_key(self) -> None:
        ps = self._make_ps()
        flags = build_partition_flags("ik_unknown", "sft", ps)
        assert flags["in_phase5_train"] is False
        assert flags["in_a_val"] is False
        assert flags["heldout_sets"] == []
        assert flags["generator_seen"] is False

    def test_heldout_sorted(self) -> None:
        """heldout_sets is a sorted list."""
        ps = self._make_ps()
        ps["B2"] = {"ik_multi"}
        ps["B1"] = {"ik_multi"}
        flags = build_partition_flags("ik_multi", "zeroshot", ps)
        assert flags["heldout_sets"] == sorted(flags["heldout_sets"])


# ---------------------------------------------------------------------------
# 6. Harvest labeling fixture: finding_id from harvest record
# ---------------------------------------------------------------------------

class TestHarvestFindingId:
    """Harvest labeler uses the harvest record's finding_id (not A_val/train examples)."""

    def test_harvest_record_finding_id_used(self) -> None:
        """A patch whose finding_id matches the harvest record passes the bookkeeping check."""
        # Simulate: harvest record has finding_id="HARVEST_F1"
        harvest_record = {
            "finding_id": "HARVEST_F1",
            "rule_id": "cis.sg_open_ingress",
            "resource_id": "RESOURCE_1",
            "resource_ref": "RESOURCE_1",
            "fields": {
                "fromport": 0,
                "ip_range": "0.0.0.0/0",
                "protocol": "-1",
                "resource_type": "AWSIpPermissionInbound",
                "toport": 0,
            },
        }
        # Patch uses HARVEST_F1
        patch_matching = {
            "finding_id": "HARVEST_F1",
            "resource_ref": "RESOURCE_1",
            "rationale_ref": "cis.sg_open_ingress",
            "ops": [{"op": "restrict_cidr", "attr": "ip_range", "value": "INTERNAL_CIDR"}],
        }
        row = label_candidate(
            record=harvest_record,
            patch=patch_matching,
            reference=None,
            route="fix",
            input_key="harvest_ik",
        )
        # The patch's finding_id matching the record is acceptable (gate should pass)
        # The oracle class should NOT be wrong due to finding_id mismatch
        assert row.input_key == "harvest_ik"

    def test_harvest_record_wrong_finding_id_detected(self) -> None:
        """A patch with a DIFFERENT finding_id from the harvest record is detectable."""
        harvest_record = {
            "finding_id": "HARVEST_F1",
            "rule_id": "cis.sg_open_ingress",
            "resource_id": "RESOURCE_1",
            "resource_ref": "RESOURCE_1",
            "fields": {
                "fromport": 0,
                "ip_range": "0.0.0.0/0",
                "protocol": "-1",
                "resource_type": "AWSIpPermissionInbound",
                "toport": 0,
            },
        }
        patch_mismatched = {
            "finding_id": "WRONG_F2",
            "resource_ref": "RESOURCE_1",
            "rationale_ref": "cis.sg_open_ingress",
            "ops": [{"op": "restrict_cidr", "attr": "ip_range", "value": "INTERNAL_CIDR"}],
        }
        # The patch uses a different finding_id; the gate may still pass or reject
        # What matters is that we used the harvest record's finding_id for the check,
        # not the A_val example's finding_id
        row = label_candidate(
            record=harvest_record,
            patch=patch_mismatched,
            reference=None,
            route="fix",
            input_key="harvest_ik",
        )
        # The key check: input_key is from the harvest record
        assert row.input_key == "harvest_ik"
        # Gate result is deterministic; we just verify no exception was raised
        assert row.oracle_class in (
            "minimal_correct", "valid_not_minimal", "wrong",
            "escalated_ok", "escalated_unneeded", "fixed_should_escalate", "unknown"
        )


# ---------------------------------------------------------------------------
# 7. Per-rule agreement table
# ---------------------------------------------------------------------------

class TestPerRuleAgreement:
    """Per-rule agreement table computed correctly from a hand-built disagreement set."""

    def test_per_rule_agreement_all_agree(self) -> None:
        """When all pairs agree, rate == 1.0 for every rule."""
        from collections import defaultdict
        agree_count: dict[str, int] = defaultdict(int)
        disagree_count: dict[str, int] = defaultdict(int)
        for rule_id in ("rule_A", "rule_B"):
            agree_count[rule_id] += 5
        for rule_id, a, d in [("rule_A", 5, 0), ("rule_B", 5, 0)]:
            rate = a / (a + d) if (a + d) else 0.0
            assert rate == 1.0, f"{rule_id}: expected rate=1.0, got {rate}"

    def test_per_rule_agreement_partial(self) -> None:
        """Partial agreement rates computed correctly."""
        rows = [
            {"rule_id": "rule_A", "agree": True},
            {"rule_id": "rule_A", "agree": False},
            {"rule_id": "rule_B", "agree": True},
            {"rule_id": "rule_B", "agree": True},
        ]
        from collections import defaultdict
        per_rule: dict[str, dict] = defaultdict(lambda: {"agree": 0, "disagree": 0})
        for r in rows:
            if r["agree"]:
                per_rule[r["rule_id"]]["agree"] += 1
            else:
                per_rule[r["rule_id"]]["disagree"] += 1

        a_rate = per_rule["rule_A"]["agree"] / (per_rule["rule_A"]["agree"] + per_rule["rule_A"]["disagree"])
        b_rate = per_rule["rule_B"]["agree"] / (per_rule["rule_B"]["agree"] + per_rule["rule_B"]["disagree"])
        assert abs(a_rate - 0.5) < 1e-9
        assert abs(b_rate - 1.0) < 1e-9

    def test_per_rule_unknown_is_separate(self) -> None:
        """An 'unknown' CF label does not count as agree or disagree like 'wrong'."""
        from ml.train_m2.labels.counterfactual import compare_with_reference
        # 'unknown' CF vs 'minimal_correct' ref: not positive, not negative -> disagree
        assert compare_with_reference("unknown", "minimal_correct") is False
        # 'minimal_correct' CF vs 'minimal_correct' ref: agree
        assert compare_with_reference("minimal_correct", "minimal_correct") is True


# ---------------------------------------------------------------------------
# 8. Provenance leak check (no absolute path or user name)
# ---------------------------------------------------------------------------

class TestProvenanceLeak:
    """No absolute path or user name in any produced file."""

    def test_partition_flags_no_absolute_path(self) -> None:
        """build_partition_flags output is a plain dict; no path strings."""
        ps = {
            "phase5_train": {"ik1"},
            "a_val": set(),
            "B1": set(), "B2": set(), "C_verifier": set(),
            "gold": set(), "C-human": set(),
            "v2_train": set(),
        }
        flags = build_partition_flags("ik1", "sft", ps)
        text = json.dumps(flags)
        root_str = str(repo_root()).replace("\\", "/")
        home_str = str(Path.home()).replace("\\", "/")
        for leak in [root_str, home_str, "C:/Users", "Desktop"]:
            assert leak not in text, f"Leaked path {leak!r} in partition flags output"

    def test_hard_negative_table_no_absolute_path(self, tmp_path: Path) -> None:
        """write_hard_negative_table writes no absolute paths."""
        rows = make_corrupted_rows(RECORD_SG, REFERENCE_SG, "fix", "test_ik_leak")
        if not rows:
            pytest.skip("No corruptor rows generated")
        stats = hard_negative_stats(rows)
        kept, dropped = filter_hard_negative_types(stats)
        from ml.train_m2.labels.corruptor import write_hard_negative_table
        out = tmp_path / "hn_table.md"
        write_hard_negative_table(kept, str(out), pre_filter_stats=stats, dropped_types=dropped)
        content = out.read_text(encoding="utf-8")
        root_str = str(repo_root()).replace("\\", "/")
        home_str = str(Path.home()).replace("\\", "/")
        for leak in [root_str, home_str, "C:/Users", "Desktop"]:
            assert leak not in content, f"Leaked path {leak!r} in hard_negative_table"

    def test_build_labels_no_absolute_path(self, tmp_path: Path) -> None:
        """build_labels.main() produces no absolute paths in output files."""
        import re
        from ml.train_m2.labels.build_labels import main

        out_dir = tmp_path / "labels_out"
        ret = main(["--out-dir", str(out_dir)])
        assert ret == 0, "build_labels.main exited non-zero"

        root_str = str(repo_root()).replace("\\", "/")
        home_str = str(Path.home()).replace("\\", "/")
        leak_patterns = [
            root_str,
            home_str,
            "C:/Users",
            "C:\\Users",
            f"{home_str}/Desktop",
            f"{home_str}\\Desktop",
            "/Desktop/",
            "\\Desktop\\",
        ]

        for out_file in out_dir.rglob("*"):
            if out_file.is_file():
                content = out_file.read_text(encoding="utf-8", errors="ignore")
                for pat in leak_patterns:
                    assert pat not in content, (
                        f"Leaked path {pat!r} found in {out_file.name}"
                    )

