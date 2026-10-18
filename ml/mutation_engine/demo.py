"""
ARGUS Phase 5 - print a few real-looking examples so you can SEE what the dataset will contain.

For each resource type present in the bases it builds one example (seed fixed, so the output is repeatable) and prints
the model input, the reference patch and which mutators were used. Uses a throw-away vault; nothing is written.

Run from the repo root (PowerShell):
    python -m ml.mutation_engine.demo
    python -m ml.mutation_engine.demo --seed 7 --violations 2
"""

import argparse
import json
import random
import sys

from ml.mutation_engine.examples import build_from_base
from ml.mutation_engine.project import throwaway_vault
from ml.mutation_engine.synth_bases import BASES_DIR, load_all_bases


def main(argv=None):
    p = argparse.ArgumentParser(description="Show example dataset rows")
    p.add_argument("--bases-dir", default=str(BASES_DIR))
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--violations", type=int, default=1, help="mutators per resource (1 to 4)")
    o = p.parse_args(argv)
    bases = load_all_bases(o.bases_dir)
    if not bases:
        print("No bases found in {}. Run Step 4 first.".format(o.bases_dir))
        return 2
    first_of_type = {}
    for base in bases:
        first_of_type.setdefault(base["resource_type"], base)
    rng = random.Random(o.seed)
    with throwaway_vault() as vault:
        for rtype, base in sorted(first_of_type.items()):
            examples = build_from_base(base, rng, o.violations, vault, "F-demo")
            if not examples:
                continue
            ex = examples[0]
            print("=" * 78)
            print("resource type : {}   rule: {}   route: {}".format(rtype, ex["rule_id"], ex["meta"]["route"]))
            print("mutators      : {} / variants {}".format(ex["meta"]["mutators"], ex["meta"]["variants"]))
            print("MODEL INPUT   :", json.dumps(ex["input"]))
            print("REFERENCE FIX :", json.dumps(ex["target"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
