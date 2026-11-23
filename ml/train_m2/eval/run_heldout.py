"""Sanctioned entry point for held-out evaluation (Shaurya-owned).

Calls preflight_heldout to verify all preconditions, data integrity,
and safety gates before permitting any held-out evaluation.
"""
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from ml.train_m2.common import repo_root
from ml.train_m2.eval.preflight_heldout import PreflightError, require_preflight_pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sanctioned held-out evaluation runner")
    parser.add_argument("--model", required=True, help="Model name (e.g. sft)")
    parser.add_argument("--set", required=True, help="Held-out set name (e.g. B1, B2, gold, C_verifier)")
    parser.add_argument("--repeat-reason", default=None, help="Reason if repeating an evaluation")
    args = parser.parse_args(argv)

    root = repo_root()
    pair = (args.model, args.set)

    print(f"Running held-out preflight verification for ({args.model}, {args.set})...")
    try:
        require_preflight_pass(root=root, pairs=[pair])
    except PreflightError as exc:
        print(f"ABORTED: Preflight check failed:\n{exc}", file=sys.stderr)
        return 1

    print("Preflight passed. Ready for one-shot held-out scoring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
