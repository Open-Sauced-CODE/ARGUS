"""
ARGUS Phase 5, Step 10 - clone the Tier C repositories (full history, no checkout).

    python -m ml.real_data.clone_repos --clone-dir D:\\argus_clones

Writes ml/real_data/tierC_clone_status.csv (ok / failed + reason). Repositories that are gone or private are reported, not fatal.
A repository whose recorded commit no longer exists is marked 'commit_missing' and skipped by the later steps.
Needs git on PATH. A clone can be hundreds of MB: check free disk space first.
"""

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

from ml.real_data.gitutil import has_commit, _env

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOS_CSV = REPO_ROOT / "ml" / "real_data" / "tierC_repos.csv"
STATUS_CSV = REPO_ROOT / "ml" / "real_data" / "tierC_clone_status.csv"
DEFAULT_CLONE_DIR = REPO_ROOT / "ml" / "real_data" / "clones"


def clone_url(repo):
    return "https://github.com/{}.git".format(repo)


def clone_one(row, clone_dir, url_for=clone_url, timeout=1800):
    target = Path(clone_dir) / str(row["repo_id"])
    if (target / "HEAD").exists() or (target / ".git").exists():
        status = "ok" if has_commit(target, row["commit"]) else "commit_missing"
        return status, target
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    try:
        proc = subprocess.run(["git", "clone", "--no-checkout", url_for(row["repo"]), str(target)],
                              capture_output=True, timeout=timeout, env=_env())
    except subprocess.TimeoutExpired:
        shutil.rmtree(target, ignore_errors=True)
        return "timeout", target
    if proc.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        return "clone_failed: " + proc.stderr.decode("utf-8", "replace").strip().splitlines()[-1][:120], target
    return ("ok" if has_commit(target, row["commit"]) else "commit_missing"), target


def main(argv=None):
    p = argparse.ArgumentParser(description="Clone the Tier C repositories")
    p.add_argument("--clone-dir", default=str(DEFAULT_CLONE_DIR))
    p.add_argument("--repos-csv", default=str(REPOS_CSV))
    p.add_argument("--status-csv", default=str(STATUS_CSV))
    p.add_argument("--limit", type=int, default=None, help="only the first N repositories (trial run)")
    o = p.parse_args(argv)
    if shutil.which("git") is None:
        print("git was not found on PATH.")
        return 2
    Path(o.clone_dir).mkdir(parents=True, exist_ok=True)
    with open(o.repos_csv, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if o.limit:
        rows = rows[: o.limit]
    out = []
    for n, row in enumerate(rows, 1):
        status, target = clone_one(row, o.clone_dir)
        print("[{}/{}] {:<50} {}".format(n, len(rows), row["repo"], status), flush=True)
        out.append([row["repo_id"], row["repo"], row["commit"], row["license"], status, str(target)])
    with open(o.status_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["repo_id", "repo", "commit", "license", "status", "path"])
        writer.writerows(out)
    ok = sum(1 for r in out if r[4] == "ok")
    print("Cloned or found: {} ok, {} not usable. Status: {}".format(ok, len(out) - ok, o.status_csv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
