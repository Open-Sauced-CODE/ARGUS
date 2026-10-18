"""
Round-trip tests for every registered mutator.

Phase 1 checklist requirement: "For each mutator, write a tiny round-trip
test proving that applying the mutator and then its reference fix
reproduces the original config."

Run with:
    pytest ml/mutation_engine/test_mutators.py -v
"""

import pytest

from mutators import MUTATORS


@pytest.mark.parametrize("mutator", MUTATORS, ids=[m.mutator_id for m in MUTATORS])
def test_round_trip(mutator):
    good_config = mutator.load_good_config()

    mutated_config = mutator.mutate(good_config)
    assert mutator.good_value not in mutated_config
    assert mutator.bad_value in mutated_config
    assert mutated_config != good_config

    fixed_config = mutator.fix(mutated_config)
    assert fixed_config == good_config


def test_mutator_ids_are_unique():
    ids = [m.mutator_id for m in MUTATORS]
    assert len(ids) == len(set(ids))


def test_every_mutator_has_a_rule_id():
    for m in MUTATORS:
        assert m.rule_id, "{} is missing a rule_id".format(m.mutator_id)
