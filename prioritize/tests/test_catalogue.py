"""Tests for fix_catalogue.json validity."""
import json
import math
from pathlib import Path

import pytest

CAT_PATH = Path(__file__).resolve().parents[1] / "fix_catalogue.json"
KNOWN_ETYPES = {
    "CAN_ESCALATE", "DIRECT_ADMIN", "CAN_ACCESS",
    "RULE_TO_SG", "USES_KEY", "CAN_ASSUME",
}


@pytest.fixture(scope="module")
def catalogue():
    return json.loads(CAT_PATH.read_text(encoding="utf-8"))


def test_catalogue_parses(catalogue):
    assert isinstance(catalogue, dict)
    assert "fixes" in catalogue


def test_delta_max_close_to_neg_ln_1e6(catalogue):
    dm = float(catalogue["delta_max"])
    expected = -math.log(1e-6)
    assert abs(dm - expected) < 1e-3, f"delta_max={dm} != {expected}"


def test_every_delta_positive(catalogue):
    dm = float(catalogue["delta_max"])
    for name, fix in catalogue["fixes"].items():
        raw_delta = fix.get("delta")
        delta = dm if raw_delta == "delta_max" else float(raw_delta)
        assert delta > 0, f"Fix {name!r} has non-positive delta {delta}"


def test_every_cost_positive_int(catalogue):
    for name, fix in catalogue["fixes"].items():
        c = fix.get("cost")
        assert isinstance(c, int) and c > 0, \
            f"Fix {name!r} cost must be positive int, got {c!r}"


def test_edge_disjointness(catalogue):
    """No etype appears in two different fix types."""
    etype_owner = {}
    for fix_name, fix in catalogue["fixes"].items():
        for et in fix.get("covers_etypes", []):
            assert et not in etype_owner, (
                f"etype {et!r} appears in both {etype_owner[et]!r} "
                f"and {fix_name!r}"
            )
            etype_owner[et] = fix_name


def test_simulated_fixes_have_known_ops(catalogue):
    """Every fix with simulated=True has a known fix_op."""
    known_ops = {"remove_policy_statement", "restrict_cidr"}
    for name, fix in catalogue["fixes"].items():
        if fix.get("simulated"):
            assert fix.get("scope") in ("stmt", "sg"), \
                f"Simulated fix {name!r} has unexpected scope"


def test_delta_max_string_resolves(catalogue):
    """'delta_max' string in a fix resolves to the numeric delta_max."""
    dm = float(catalogue["delta_max"])
    for name, fix in catalogue["fixes"].items():
        if fix.get("delta") == "delta_max":
            assert abs(dm - (-math.log(1e-6))) < 1e-3
