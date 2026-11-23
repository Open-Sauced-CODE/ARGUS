"""Sanctioned entry point for held-out evaluation (Shaurya-owned).

Calls preflight_heldout to verify all preconditions, data integrity,
and safety gates before permitting any held-out evaluation.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure repository root is on sys.path when invoked directly as a script
_repo_root = str(Path(__file__).resolve().parents[3])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from typing import Sequence

from ml.train_m2.common import repo_root
from ml.train_m2.eval.preflight_heldout import PreflightError, require_preflight_pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sanctioned held-out evaluation runner")
    parser.add_argument("--model", required=True, help="Model name (e.g. sft)")
    parser.add_argument("--set", required=True, help="Held-out set name (e.g. B1, B2, gold, C_verifier)")
    parser.add_argument("--repeat-reason", default=None, help="Reason if repeating an evaluation")
    parser.add_argument("--skip-test-suites", action="store_true", help="Skip running pytest suites if certified immediately prior")
    args = parser.parse_args(argv)

    root = repo_root()
    pair = (args.model, args.set)

    print(f"Running held-out preflight verification for ({args.model}, {args.set})...")
    try:
        require_preflight_pass(root=root, pairs=[pair], skip_test_suites=args.skip_test_suites)
    except PreflightError as exc:
        print(f"ABORTED: Preflight check failed:\n{exc}", file=sys.stderr)
        return 1

    print("Preflight passed. Ready for one-shot held-out scoring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
