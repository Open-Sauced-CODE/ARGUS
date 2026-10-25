#!/usr/bin/env python3
"""Phase 6 ownership guard.

    python tools/check_ownership.py --who prabhav [--base origin/main]

Fails (exit 1) if the commits on HEAD that are not on --base touch a path owned by the OTHER person.
Paths owned by nobody and not shared are reported as warnings so the owner map can be extended.
The longest matching prefix in ml/train_m2/OWNERS.json decides who owns a path.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def owner_of(path: str, owners: dict) -> str | None:
    best, who = -1, None
    for name in ("shaurya", "prabhav", "shared"):
        for prefix in owners.get(name, []):
            if path == prefix or (prefix.endswith("/") and path.startswith(prefix)) or (not prefix.endswith("/") and path.startswith(prefix) and prefix.endswith("_")):
                if len(prefix) > best:
                    best, who = len(prefix), name
    return who


def changed_files(base: str) -> list[str]:
    out = subprocess.check_output(["git", "diff", "--name-only", f"{base}...HEAD"], text=True)
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", required=True, choices=["shaurya", "prabhav"])
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--owners", default="ml/train_m2/OWNERS.json")
    args = ap.parse_args(argv)
    owners = json.loads(Path(args.owners).read_text(encoding="utf-8"))
    other = "prabhav" if args.who == "shaurya" else "shaurya"
    bad, unowned = [], []
    for f in changed_files(args.base):
        o = owner_of(f, owners)
        if o == other:
            bad.append(f)
        elif o is None:
            unowned.append(f)
    for f in unowned:
        print(f"WARN  unowned path (add it to OWNERS.json): {f}")
    if bad:
        print(f"FAIL  {args.who} touched files owned by {other}:")
        for f in bad:
            print("   ", f)
        print("Ask the owner to make the change, or move your code into a path you own.")
        return 1
    print(f"OK    {args.who}: no files owned by {other} were touched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
