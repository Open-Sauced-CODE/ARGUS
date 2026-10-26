#!/usr/bin/env python3
"""Fail if any frozen path differs from the Phase 5 tag (committed, staged, unstaged or untracked).

    py tools/check_frozen.py

The list lives in tools/frozen_paths.txt. Exit code 0 = every frozen path equals the tag.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = "b5d4467"


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise SystemExit("git " + " ".join(args) + " failed: " + result.stderr.strip())
    return result.stdout


def frozen_paths() -> list[str]:
    text = (Path(__file__).with_name("frozen_paths.txt")).read_text(encoding="utf-8")
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def main() -> int:
    paths = frozen_paths()
    changed = set(git("diff", "--name-only", TAG, "--", *paths).splitlines())
    changed |= set(git("ls-files", "--others", "--exclude-standard", "--", *paths).splitlines())
    if changed:
        print("FAIL  frozen paths differ from tag " + TAG + ":")
        for name in sorted(changed):
            print("   ", name)
        print("Revert them (git checkout " + TAG + " -- <path>) or ask for an explicit unfreeze decision.")
        return 1
    print("OK    all " + str(len(paths)) + " frozen path entries equal tag " + TAG)
    return 0


if __name__ == "__main__":
    sys.exit(main())
