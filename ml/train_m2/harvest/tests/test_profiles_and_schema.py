"""Profiles must be exactly the contract; the fixture and the schema validator must agree.

Run from the repo root:  python -m pytest ml/train_m2/harvest/tests -q
"""

import json
from dataclasses import astuple

import pytest

from ml.train_m2.harvest.paths import FIXTURE_PATH
from ml.train_m2.harvest.profiles import sample_params
from ml.train_m2.harvest.schema import HarvestSchemaError, text_equals_tokens, validate_line


def test_profile_a_matches_the_contract():
    assert astuple(sample_params("A", 0)) == (0.0, None, 0)
    for idx in range(1, 8):
        assert astuple(sample_params("A", idx)) == (0.7, None, idx)


def test_profile_b_matches_the_contract():
    assert astuple(sample_params("B", 0)) == (0.0, None, 0)
    for idx in range(1, 8):
        assert astuple(sample_params("B", idx)) == (1.0, 0.95, 1000 + idx)


def test_temperature_override_only_touches_samples_1_to_7():
    assert sample_params("B", 0, 1.4).temperature == 0.0
    assert sample_params("B", 3, 1.4).temperature == 1.4
    assert sample_params("B", 3, 1.4).top_p == 0.95


@pytest.mark.parametrize("bad", [(-1), 8, 100])
def test_bad_sample_index_is_rejected(bad):
    with pytest.raises(ValueError):
        sample_params("A", bad)


def test_bad_profile_is_rejected():
    with pytest.raises(ValueError):
        sample_params("C", 0)


def good_line():
    return {"schema_version": "m2.harvest.v1", "input_key": "{}", "generator": "sft", "profile": "A", "sample_idx": 0,
            "temperature": 0.0, "top_p": None, "seed": 0, "model": "m", "model_digest": None, "ollama_version": "1",
            "content": "ab", "error": None, "eval_count": 1, "seconds": 0.5, "done_reason": "stop",
            "tokens": [{"t": "ab", "lp": -0.1, "top": [["ab", -0.1], ["x", -2.0]]}]}


def test_a_good_line_validates_and_text_equals_tokens():
    line = good_line()
    validate_line(line)
    assert text_equals_tokens(line)


def test_bad_lines_are_rejected():
    for change in ({"profile": "Z"}, {"sample_idx": 8}, {"tokens": []}, {"content": ""}, {"unexpected": 1}):
        line = dict(good_line(), **change)
        with pytest.raises(HarvestSchemaError):
            validate_line(line)
    line = good_line()
    line["tokens"][0]["lp"] = 0.5
    with pytest.raises(HarvestSchemaError):
        validate_line(line)
    err = dict(good_line(), error="timeout", content="")
    with pytest.raises(HarvestSchemaError):  # error line must have no tokens
        validate_line(err)
    err["tokens"] = []
    validate_line(err)


@pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="contract fixture not present")
def test_contract_fixture_lines_validate():
    lines = [json.loads(raw) for raw in FIXTURE_PATH.read_text(encoding="utf-8").splitlines() if raw.strip()]
    assert lines
    for line in lines:
        validate_line(line)
        assert text_equals_tokens(line)
