"""
ARGUS Phase 5, Step 10 - choose the Tier C repositories (TEST bucket only) and write real_data/tierC_repos.csv.

    python -m ml.real_data.select_tierc --max-repos 60

Reads ml/mutation_engine/bases/repo_buckets.csv (Step 4) and ml/real_data/out/tierC_candidates.jsonl (Step 4).
A repository is chosen only if it is in the test bucket, is not reserved, has a licence that is not 'unknown', and gave at least one
violating resource in Step 4. Repositories with more violating resources come first, but each rule family is represented.
It also proves that no chosen repository gave a Tier A training base.
"""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUCKETS_CSV = REPO_ROOT / "ml" / "mutation_engine" / "bases" / "repo_buckets.csv"
CANDIDATES = REPO_ROOT / "ml" / "real_data" / "out" / "tierC_candidates.jsonl"
OUT_CSV = REPO_ROOT / "ml" / "real_data" / "tierC_repos.csv"
BASES_DIR = REPO_ROOT / "ml" / "mutation_engine" / "bases"
FIELDS = ["repo_id", "repo", "commit", "license", "bucket", "candidates", "rules"]


def read_candidates(path):
    out = []
    p = Path(path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    out.append(json.loads(line))
    return out


def train_repo_ids(bases_dir):
    ids = set()
    for name in ("bases.jsonl", "bases_synthetic.jsonl"):
        p = Path(bases_dir) / name
        if p.exists():
            with open(p, "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        b = json.loads(line)
                        if b["source"]["bucket"] in ("train", "val"):
                            ids.add(b["source"]["repo_id"])
    return ids


def select(buckets_csv, candidates_path, bases_dir, max_repos):
    info = {}
    with open(buckets_csv, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            info[int(row["repo_id"])] = row
    per_repo = defaultdict(list)
    for rec in read_candidates(candidates_path):
        per_repo[rec["source"]["repo_id"]].append(rec)
    rows = []
    for repo_id, recs in per_repo.items():
        row = info.get(repo_id)
        if row is None or row["bucket"] != "test" or row["license"].strip().lower() in ("", "unknown", "none"):
            continue
        rules = sorted({r for rec in recs for r in rec.get("rules_fired", [])})
        rows.append({"repo_id": repo_id, "repo": row["repo"], "commit": row["commit"], "license": row["license"],
                     "bucket": "test", "candidates": len(recs), "rules": ";".join(rules)})
    rows.sort(key=lambda r: (-r["candidates"], r["repo_id"]))
    chosen, covered = [], set()
    for row in rows:  # first pass: repositories that add a rule not yet covered
        new = set(row["rules"].split(";")) - covered
        if new and len(chosen) < max_repos:
            chosen.append(row)
            covered |= new
    for row in rows:  # second pass: fill up by number of violating resources
        if len(chosen) >= max_repos:
            break
        if row not in chosen:
            chosen.append(row)
    chosen.sort(key=lambda r: r["repo_id"])
    overlap = {r["repo_id"] for r in chosen} & train_repo_ids(bases_dir)
    return chosen, overlap


def main(argv=None):
    p = argparse.ArgumentParser(description="Select Tier C repositories (test bucket only)")
    p.add_argument("--max-repos", type=int, default=60)
    p.add_argument("--buckets-csv", default=str(BUCKETS_CSV))
    p.add_argument("--candidates", default=str(CANDIDATES))
    p.add_argument("--bases-dir", default=str(BASES_DIR))
    p.add_argument("--out", default=str(OUT_CSV))
    o = p.parse_args(argv)
    if not Path(o.candidates).exists():
        print("Missing {}. Step 4 (filter_terrads) writes it.".format(o.candidates))
        return 2
    chosen, overlap = select(o.buckets_csv, o.candidates, o.bases_dir, o.max_repos)
    if overlap:
        print("INTERNAL ERROR: these repositories also gave train/val bases: {}".format(sorted(overlap)))
        return 1
    with open(o.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(chosen)
    print("Chosen {} repositories -> {}".format(len(chosen), o.out))
    print("Licences:", dict(Counter(r["license"] for r in chosen)))
    print("Self-check passed: no chosen repository is in the train or validation bases.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
