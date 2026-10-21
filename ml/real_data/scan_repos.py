"""
ARGUS Phase 5, Step 11 - harvest real violations with our own Rego rules (Tier C-verifier).

    python -m ml.real_data.scan_repos --max-per-repo 25

For every cloned Tier C repository (status ok) it reads the .tf files at the recorded commit, normalises every resource, runs ALL Rego
rules in one OPA call, and writes one record per (violating resource, fired rule), projected through the airlock, to
ml/mutation_engine/held_out/tierC_verifier.jsonl. These records have no reference patch: they are scored by the gate and hidden checks.
Also writes ml/real_data/out/tierC_scan_summary.json (the funnel) and updates held_out/tierC_base_hashes.txt.
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from ml.mutation_engine.dataset_io import canon, full_hash, input_key, sha256_text, write_jsonl
from ml.mutation_engine.model import Resource
from ml.mutation_engine.project import raw_finding, throwaway_vault
from ml.mutation_engine.routes import rule_route
from ml.real_data import gitutil
from ml.real_data.c_common import HELD_OUT_DIR, OUT_DIR, REPOS_CSV, STATUS_CSV, permalink, update_c_hashes
from ml.real_data.rego_runner import evaluate, resource_for_rules
from ml.real_data.select_tierc import BASES_DIR, train_repo_ids
from ml.real_data.tf_normalise import normalise_repo
from privacy.airlock.airlock import AirlockBlocked, run_airlock


def usable_repos(status_csv):
    with open(status_csv, newline="", encoding="utf-8") as handle:
        return [r for r in csv.DictReader(handle) if r["status"] == "ok"]


def scan_repo(row, vault, max_per_repo, policy_dir=None, opa=None):
    """Returns (findings, counters) for one repository."""
    counters = Counter()
    files = gitutil.read_tf_files(row["path"], row["commit"])
    out = normalise_repo(files)
    counters["files_parsed"] += out["files_parsed"]
    counters["parse_errors"] += out["parse_errors"]
    counters["resources_skipped_unresolved"] += sum(out["skips"].values())
    records = out["records"]
    counters["records"] += len(records)
    verdicts = evaluate([resource_for_rules(r) for r in records], policy_dir=policy_dir, opa=opa) if records else []
    items = []
    for rec, verdict in zip(records, verdicts):
        for rule in sorted(set(verdict.deny) | set(verdict.warn)):
            items.append((rec["source"]["file"], rec["source"]["tf_name"], rule, rec))
    items.sort(key=lambda t: (t[0], t[1], t[2], t[3]["norm_hash"]))
    counters["violations"] += len(items)
    findings, seen = [], set()
    for file, name, rule, rec in items:
        key = (rec["norm_hash"], rule)
        if key in seen:
            counters["duplicate_in_repo"] += 1
            continue
        seen.add(key)
        if len(findings) >= max_per_repo:
            counters["over_repo_cap"] += 1
            continue
        findings.append((rule, rec))
    return findings, counters


def to_example(n, row, rule, rec, vault):
    res = Resource(rec["resource_type"], rec["attrs"], rec["extras"])
    raw = raw_finding(res, "C-{:06d}".format(n), "tfc-" + rec["norm_hash"][:12])
    record, _receipt = run_airlock(raw, rule, vault=vault)
    plain = {"resource_type": rec["resource_type"], "attrs": rec["attrs"], "extras": rec["extras"]}
    return {
        "id": "c-{:06d}".format(n), "tier": "C-verifier", "rule_id": rule, "input": record, "target": None,
        "meta": {"route": rule_route(rule), "tier": "C-verifier", "split": "C-verifier",
                 "repo": row["repo"], "repo_id": int(row["repo_id"]), "commit": row["commit"], "license": row["license"],
                 "file": rec["source"]["file"], "tf_type": rec["source"]["tf_type"], "tf_name": rec["source"]["tf_name"],
                 "permalink": permalink(row["repo"], row["commit"], rec["source"]["file"]),
                 "base_norm_hash": rec["norm_hash"], "full_hash": full_hash(rule, plain)},
        "qa": {"mutated": plain},
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Scan the cloned Tier C repositories with the Rego rules")
    p.add_argument("--status-csv", default=str(STATUS_CSV))
    p.add_argument("--repos-csv", default=str(REPOS_CSV))
    p.add_argument("--bases-dir", default=str(BASES_DIR))
    p.add_argument("--max-per-repo", type=int, default=25)
    p.add_argument("--policy-dir", default=None)
    p.add_argument("--opa", default=None)
    p.add_argument("--out-dir", default=str(HELD_OUT_DIR))
    p.add_argument("--summary", default=str(OUT_DIR / "tierC_scan_summary.json"))
    o = p.parse_args(argv)
    if not Path(o.status_csv).exists():
        print("Missing {}. Run clone_repos first.".format(o.status_csv))
        return 2
    repos = usable_repos(o.status_csv)
    overlap = {int(r["repo_id"]) for r in repos} & train_repo_ids(o.bases_dir)
    if overlap:
        print("INTERNAL ERROR: train/val repositories among the Tier C repos: {}".format(sorted(overlap)))
        return 1
    totals, examples, seen = Counter(), [], set()
    with throwaway_vault() as vault:
        for n, row in enumerate(repos, 1):
            findings, counters = scan_repo(row, vault, o.max_per_repo, o.policy_dir, o.opa)
            totals.update(counters)
            totals["repos_scanned"] += 1
            for rule, rec in findings:
                if (rec["norm_hash"], rule) in seen:
                    totals["duplicate_across_repos"] += 1
                    continue
                seen.add((rec["norm_hash"], rule))
                try:
                    examples.append(to_example(len(examples) + 1, row, rule, rec, vault))
                except AirlockBlocked:
                    totals["blocked_by_airlock"] += 1
            print("[{}/{}] {:<45} findings so far: {}".format(n, len(repos), row["repo"], len(examples)), flush=True)
    write_jsonl(Path(o.out_dir) / "tierC_verifier.jsonl", examples)
    totals["findings_written"] = len(examples)
    totals["by_rule"] = dict(Counter(e["rule_id"] for e in examples))
    Path(o.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(o.summary).write_text(json.dumps(dict(totals), indent=2, sort_keys=True) + "\n", encoding="ascii")
    n_hash = update_c_hashes(o.out_dir)
    print("Wrote {} findings to {} ({} base hashes recorded).".format(len(examples), Path(o.out_dir) / "tierC_verifier.jsonl", n_hash))
    print("By rule:", dict(Counter(e["rule_id"] for e in examples)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
