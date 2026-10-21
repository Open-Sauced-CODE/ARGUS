"""
ARGUS Phase 5 - MANIFEST.sha256: the SHA-256 of every dataset and held-out file.

    python -m ml.tools.verify_manifest              check every file against ml/mutation_engine/MANIFEST.sha256 (exit 1 on a mismatch)
    python -m ml.tools.verify_manifest --update     rewrite the manifest from the files that exist now (after adding Tier C files)

Format (one line per file):  <sha256>  <path relative to ml/mutation_engine>
"""

import argparse
import sys
from pathlib import Path

from ml.mutation_engine.dataset_io import sha256_file

ME_DIR = Path(__file__).resolve().parents[1] / "mutation_engine"
PATTERNS = (("dataset", "*.jsonl"), ("held_out", "*.jsonl"), ("held_out", "*.txt"))


def manifest_path(root=None):
    return Path(root or ME_DIR) / "MANIFEST.sha256"


def list_files(root=None):
    root = Path(root or ME_DIR)
    found = []
    for folder, pattern in PATTERNS:
        found.extend(sorted((root / folder).glob(pattern)))
    return found


def write_manifest(root=None):
    root = Path(root or ME_DIR)
    lines = ["{}  {}".format(sha256_file(f), f.relative_to(root).as_posix()) for f in list_files(root)]
    manifest_path(root).write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
    return lines


def verify_manifest(root=None):
    """Returns a list of problem texts (empty = every file matches)."""
    root = Path(root or ME_DIR)
    path = manifest_path(root)
    if not path.exists():
        return ["MANIFEST.sha256 is missing: build the dataset first"]
    problems, listed = [], set()
    for line in path.read_text(encoding="ascii").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        listed.add(rel)
        target = root / rel
        if not target.exists():
            problems.append("missing file {}".format(rel))
        elif sha256_file(target) != digest:
            problems.append("changed file {}".format(rel))
    for f in list_files(root):
        if f.relative_to(root).as_posix() not in listed:
            problems.append("file not in the manifest: {}".format(f.relative_to(root).as_posix()))
    return problems


def main(argv=None):
    p = argparse.ArgumentParser(description="Check or update MANIFEST.sha256")
    p.add_argument("--update", action="store_true")
    o = p.parse_args(argv)
    if o.update:
        lines = write_manifest()
        print("Manifest written with {} files.".format(len(lines)))
        return 0
    problems = verify_manifest()
    if problems:
        print("MANIFEST CHECK FAILED:")
        for text in problems:
            print("  " + text)
        return 1
    print("Manifest check passed: every dataset and held-out file matches its recorded hash.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
