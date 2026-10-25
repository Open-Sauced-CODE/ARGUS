"""
ARGUS Phase 5, Step 4 - build the base-config corpus from TerraDS.

What it does (in this order):
  1. Selects the repositories that declare the AWS resource types our rules touch (from TerraDS.sqlite).
  2. Assigns EVERY selected repository to one bucket by hashing its name (0-69 train, 70-79 val, 80-99 test);
     CloudGoat/TerraGoat repositories are "reserved" (Phase 10 testbed) and never feed train or validation.
  3. Reads each repository's .tf files, normalises every resource into a record with the Rego field names
     (ml/real_data/tf_normalise.py). Resources whose rule-relevant values are unresolved are skipped and counted.
  4. Runs the Phase 4 Rego rules (through OPA) on every record.
       zero violations      -> candidate Tier A base
       violations, test repo -> Tier C candidate (kept for Stage C, never used for training)
       violations, train repo -> only counted (violation frequencies for the Step 5 mutator weights)
  5. Removes near-duplicates (same normalised hash; first repository in Id order wins, so the same shape can
     never sit in two buckets).
  6. Writes bases.jsonl, manifest.csv, counts.csv, repo_buckets.csv, funnel.json, and the Tier C and
     frequency files; then re-checks that every kept base is clean.

Run from the repo root (PowerShell), after `python -m ml.real_data.inspect_terrads` looked right:
    python -m ml.real_data.filter_terrads --db D:\\terrads\\TerraDS.sqlite --archive-dir D:\\terrads\\archive --limit 300
"""

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ml.real_data import terrads_source as ts
from ml.real_data.buckets import RESERVED_SUBSTRINGS, bucket_of
from ml.real_data.rego_runner import evaluate, resource_for_rules
from ml.real_data.repo_worker import process_repo
from ml.real_data.tf_normalise import TARGET_TYPES

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASES_OUT = REPO_ROOT / "ml" / "mutation_engine" / "bases"
DEFAULT_REAL_OUT = REPO_ROOT / "ml" / "real_data" / "out"
EXTRA_ID_START = 9_000_001
FLUSH_EVERY = 2000


def _git_head(path):
    try:
        out = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else "unknown"
    except Exception:
        return "unknown"


def build_jobs(repos, archive_root, extras, reserved, max_file_bytes):
    """repos: list of dicts from load_repositories. extras: [(name, license, path)]. Returns (jobs, repo_rows)."""
    all_repos = list(repos)
    for n, (name, lic, path) in enumerate(extras):
        all_repos.append({"id": EXTRA_ID_START + n, "full_name": name, "license": lic,
                          "commit": _git_head(path), "local_dir": str(path)})
    jobs = []
    for repo in all_repos:
        jobs.append({
            "id": repo["id"], "full_name": repo["full_name"], "license": repo["license"], "commit": repo["commit"],
            "bucket": bucket_of(repo["full_name"], reserved), "archive_root": str(archive_root) if archive_root else None,
            "local_dir": repo.get("local_dir"), "max_file_bytes": max_file_bytes,
        })
    return jobs


def _iter_results(jobs, workers):
    if workers <= 1:
        for job in jobs:
            yield process_repo(job)
        return
    with ProcessPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(process_repo, jobs, chunksize=4)


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def run(db, archive_root, bases_out=DEFAULT_BASES_OUT, real_out=DEFAULT_REAL_OUT, policy_dir=None, opa=None,
        limit=None, workers=1, extras=(), max_file_kb=400, reserved=RESERVED_SUBSTRINGS, progress=True):
    bases_out, real_out = Path(bases_out), Path(real_out)
    bases_out.mkdir(parents=True, exist_ok=True)
    real_out.mkdir(parents=True, exist_ok=True)
    max_file_bytes = max_file_kb * 1000

    con = ts.open_db(db) if db else None
    repos = ts.load_repositories(con, TARGET_TYPES, limit) if con else []
    if con:
        con.close()
    if archive_root:
        archive_root = ts.detect_archive_root(archive_root)
    jobs = build_jobs(repos, archive_root, extras, reserved, max_file_bytes)
    if not jobs:
        raise SystemExit("No repositories selected. Check --db and the resource types in the database.")

    # a repository must be in exactly one bucket
    buckets_by_id = {}
    for job in jobs:
        assert job["id"] not in buckets_by_id, "repository id used twice: {}".format(job["id"])
        buckets_by_id[job["id"]] = job["bucket"]

    funnel = Counter()
    funnel["repos_selected"] = len(jobs)
    for b in buckets_by_id.values():
        if b is not None:
            funnel["repos_bucket_" + str(b)] += 1
    skips, seen = Counter(), Counter()
    seen_hashes = {}  # norm_hash -> base_id of the kept base
    tierc_hashes = set()
    bases, tierc = [], []
    violations_train = Counter()
    repo_rows = []
    buffer = []

    def flush():
        if not buffer:
            return
        results = evaluate([resource_for_rules(r) for r in buffer], policy_dir=policy_dir, opa=opa)
        for rec, res in zip(buffer, results):
            bucket = rec["source"]["bucket"]
            funnel["records_evaluated"] += 1
            if res.deny:
                funnel["records_with_violation"] += 1
                if bucket == "train":
                    for rule_id in res.deny:
                        violations_train[rule_id] += 1
                if bucket == "test":
                    if rec["norm_hash"] in tierc_hashes:
                        funnel["tierC_duplicates_dropped"] += 1
                    else:
                        tierc_hashes.add(rec["norm_hash"])
                        tierc.append(dict(rec, rules_fired=sorted(res.deny)))
                continue
            if res.warn:
                funnel["records_with_warning_dropped"] += 1
                continue
            funnel["records_clean"] += 1
            if bucket == "reserved":
                funnel["clean_reserved_not_used"] += 1
                continue
            if rec["norm_hash"] in seen_hashes:
                funnel["duplicates_dropped"] += 1
                continue
            seen_hashes[rec["norm_hash"]] = True
            rec = dict(rec, base_id="b-" + rec["norm_hash"][:12])
            bases.append(rec)
        buffer.clear()

    job_by_id = {j["id"]: j for j in jobs}
    for n, result in enumerate(_iter_results(jobs, workers), 1):
        job = job_by_id[result["id"]]
        if result["error"]:
            funnel["repos_worker_error"] += 1
        elif not result["found"]:
            funnel["repos_archive_missing"] += 1
        else:
            funnel["repos_read"] += 1
        funnel["files_parsed"] += result["files_parsed"]
        funnel["files_parse_errors"] += result["parse_errors"]
        funnel["files_too_large"] += result["too_large"]
        skips.update(result["skips"])
        seen.update(result["seen"])
        buffer.extend(result["records"])
        if len(buffer) >= FLUSH_EVERY:
            flush()
        repo_rows.append([job["id"], job["full_name"], job["bucket"], job["license"], job["commit"],
                          sum(result["seen"].values()), len(result["records"])])
        if progress and n % 500 == 0:
            print("  processed {} / {} repositories".format(n, len(jobs)), file=sys.stderr, flush=True)
    flush()

    funnel["resources_seen"] = sum(seen.values())
    funnel["resources_skipped_unresolved"] = sum(skips.values())
    funnel["bases_kept"] = len(bases)
    funnel["tierC_candidates"] = len(tierc)

    # ---- final self-check: every kept base passes every rule ---------------------------------------------------
    if bases:
        verdicts = evaluate([resource_for_rules(b) for b in bases], policy_dir=policy_dir, opa=opa)
        dirty = [b["base_id"] for b, v in zip(bases, verdicts) if not v.clean]
        if dirty:
            raise SystemExit("INTERNAL ERROR: bases that violate a rule: {}".format(dirty[:5]))
    # ---- no hash in two buckets, no repository in two buckets ---------------------------------------------------
    hash_bucket = {}
    for b in bases:
        previous = hash_bucket.setdefault(b["norm_hash"], b["source"]["bucket"])
        if previous != b["source"]["bucket"]:
            raise SystemExit("INTERNAL ERROR: one shape in two buckets: " + b["base_id"])

    # ---- write outputs ---------------------------------------------------------------------------------------------
    with open(bases_out / "bases.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for b in bases:
            handle.write(json.dumps(b, sort_keys=True, ensure_ascii=True) + "\n")
    _write_csv(bases_out / "manifest.csv",
               ["base_id", "resource_type", "bucket", "repo_id", "repo", "commit", "license", "file", "tf_type", "tf_name", "norm_hash"],
               [[b["base_id"], b["resource_type"], b["source"]["bucket"], b["source"]["repo_id"], b["source"]["repo"],
                 b["source"]["commit"], b["source"]["license"], b["source"]["file"], b["source"]["tf_type"],
                 b["source"]["tf_name"], b["norm_hash"]] for b in bases])
    counts = Counter((b["resource_type"], b["source"]["bucket"]) for b in bases)
    types = sorted({t for t, _ in counts})
    _write_csv(bases_out / "counts.csv", ["resource_type", "train", "val", "test", "total"],
               [[t] + [counts[(t, k)] for k in ("train", "val", "test")] + [sum(counts[(t, k)] for k in ("train", "val", "test"))] for t in types])
    kept_per_repo = Counter(b["source"]["repo_id"] for b in bases)
    _write_csv(bases_out / "repo_buckets.csv",
               ["repo_id", "repo", "bucket", "license", "commit", "resources_seen", "records_made", "bases_kept"],
               [row + [kept_per_repo[row[0]]] for row in repo_rows])
    with open(bases_out / "funnel.json", "w", encoding="utf-8", newline="\n") as handle:
        json.dump({"funnel": dict(funnel), "skip_reasons": dict(sorted(skips.items())),
                   "resources_seen_by_tf_type": dict(sorted(seen.items()))}, handle, indent=2, sort_keys=True)
        handle.write("\n")
    with open(real_out / "tierC_candidates.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for rec in tierc:
            handle.write(json.dumps(rec, sort_keys=True, ensure_ascii=True) + "\n")
    _write_csv(real_out / "violation_counts_train.csv", ["rule_id", "violating_records_in_train_repos"],
               sorted(violations_train.items()))
    return {"funnel": funnel, "skips": skips, "seen": seen, "counts": counts, "bases": bases, "tierc": tierc,
            "bases_out": bases_out, "real_out": real_out}


def print_summary(summary):
    f, counts = summary["funnel"], summary["counts"]
    print()
    print("=== STEP 4 SUMMARY ===")
    for key in ("repos_selected", "repos_bucket_train", "repos_bucket_val", "repos_bucket_test", "repos_bucket_reserved",
                "repos_read", "repos_archive_missing", "repos_worker_error", "files_parsed", "files_parse_errors",
                "files_too_large", "resources_seen", "resources_skipped_unresolved", "records_evaluated",
                "records_clean", "records_with_violation", "duplicates_dropped", "bases_kept", "tierC_candidates"):
        print("{:<32} {}".format(key, f.get(key, 0)))
    print()
    print("Top skip reasons:")
    for reason, n in summary["skips"].most_common(8):
        print("  {:<36} {}".format(reason, n))
    print()
    print("| resource type | train | val | test | total |")
    print("|---|---:|---:|---:|---:|")
    for t in sorted({t for t, _ in counts}):
        row = [counts[(t, k)] for k in ("train", "val", "test")]
        print("| {} | {} | {} | {} | {} |".format(t, row[0], row[1], row[2], sum(row)))
    print()
    print("Written to: {}".format(summary["bases_out"]))
    print("Self-check passed: every kept base is clean under all rules; no shape sits in two buckets.")


def main(argv=None):
    p = argparse.ArgumentParser(description="ARGUS Phase 5, Step 4: build the base-config corpus from TerraDS")
    p.add_argument("--db", required=True, help="path to TerraDS.sqlite")
    p.add_argument("--archive-dir", required=True, help="folder where TerraDS.tar.gz was extracted")
    p.add_argument("--bases-out", default=str(DEFAULT_BASES_OUT))
    p.add_argument("--real-out", default=str(DEFAULT_REAL_OUT))
    p.add_argument("--policy-dir", default=None)
    p.add_argument("--opa", default=None, help="path to opa.exe (else OPA_BIN, else PATH)")
    p.add_argument("--limit", type=int, default=None, help="only the first N selected repositories (quick trial run)")
    p.add_argument("--workers", type=int, default=1, help="parallel parser processes")
    p.add_argument("--max-file-kb", type=int, default=400)
    p.add_argument("--extra", nargs=3, action="append", default=[], metavar=("NAME", "LICENSE", "PATH"),
                   help="add a local clone, e.g. --extra terraform-aws-modules/terraform-aws-s3-bucket Apache-2.0 D:\\clones\\s3")
    p.add_argument("--reserved-substr", action="append", default=[], help="extra repository-name parts to reserve")
    options = p.parse_args(argv)
    summary = run(options.db, options.archive_dir, options.bases_out, options.real_out, options.policy_dir,
                  options.opa, options.limit, options.workers, [tuple(e) for e in options.extra], options.max_file_kb,
                  tuple(RESERVED_SUBSTRINGS) + tuple(s.lower() for s in options.reserved_substr))
    print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
