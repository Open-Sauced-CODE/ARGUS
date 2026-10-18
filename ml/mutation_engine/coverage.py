"""
ARGUS Phase 5, Step 5 - coverage report.

Prints, for every Rego rule, the mutators that make it fire and how many variants they have, and (when the
bases exist) how many bases per bucket each mutator can be applied to. Exit code 1 if any rule has no mutator,
or if a mutator names a rule that does not exist.

Run from the repo root (PowerShell):
    python -m ml.mutation_engine.coverage
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

from ml.mutation_engine.model import Resource
from ml.mutation_engine.mutators import ALL_MUTATORS, rules_covered
from ml.mutation_engine.synth_bases import BASES_DIR, load_all_bases
from privacy.airlock.projection import load_declarations


def rule_coverage():
    covered = rules_covered()
    rules = sorted(load_declarations())
    return [(r, covered.get(r, [])) for r in rules], sorted(set(covered) - set(rules))


def base_availability(bases):
    """{mutator id: Counter(bucket -> number of bases with at least one applicable variant)}"""
    table = {m.mutator_id: Counter() for m in ALL_MUTATORS}
    for base in bases:
        res = Resource.from_base(base)
        for m in ALL_MUTATORS:
            if res.resource_type in m.resource_types and any(m.prepare(res, v) is not None for v in m.variants):
                table[m.mutator_id][base["source"]["bucket"]] += 1
    return table


def main(argv=None):
    p = argparse.ArgumentParser(description="Mutator coverage report")
    p.add_argument("--bases-dir", default=str(BASES_DIR))
    o = p.parse_args(argv)
    rows, unknown = rule_coverage()
    by_id = {m.mutator_id: m for m in ALL_MUTATORS}
    print("{:<30} {:<28} {}".format("rule", "mutators", "variants"))
    bad = bool(unknown)
    for rule, mutators in rows:
        variants = sum(len(by_id[i].variants) for i in mutators)
        print("{:<30} {:<28} {}".format(rule, ", ".join(mutators) or "NONE", variants))
        bad = bad or not mutators
    if unknown:
        print("Mutators name rules that do not exist: {}".format(unknown))
    bases = load_all_bases(o.bases_dir) if Path(o.bases_dir).exists() else []
    if bases:
        print()
        print("{:<28} {:>7} {:>7} {:>7}   (bases a mutator can be applied to)".format("mutator", "train", "val", "test"))
        for mid, counter in base_availability(bases).items():
            print("{:<28} {:>7} {:>7} {:>7}".format(mid, counter["train"], counter["val"], counter["test"]))
    print()
    print("RESULT: {}".format("every rule has at least one mutator" if not bad else "COVERAGE PROBLEM"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
