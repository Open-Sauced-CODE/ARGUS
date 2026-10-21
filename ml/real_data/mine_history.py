"""
ARGUS Phase 5, Step 12 - mine real fixes from git history (Tier C-mined candidates).

    python -m ml.real_data.mine_history --max-commits 300

For every cloned Tier C repository: list commits that touched .tf files; for each modified directory, normalise the resources before and
after the commit and keep a resource only if it violated a Rego rule before, is silent on that rule after, and still exists. The diff of the
attributes that rule reads becomes a Patch-IR fix (same vocabulary as Step 7). A pair that cannot be expressed is counted as out-of-vocabulary.
Convention (contracts D12): a changed ip_range is written as the placeholder INTERNAL_CIDR.
Output (to be READ BY A PERSON): ml/real_data/out/tierC_mined_candidates.jsonl and the funnel ml/real_data/out/mined_funnel.json.
Only resources that are the single record of their (file, resource) are used; resources with several records (several ingress rules or
policy statements in one block) are counted as 'ambiguous_multi_record' and skipped.
"""

import argparse
import copy
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from ml.mutation_engine.dataset_io import canon, full_hash, input_key, write_jsonl
from ml.mutation_engine.labeler import schema_errors
from ml.mutation_engine.model import MISSING, Resource
from ml.mutation_engine.project import raw_finding, throwaway_vault, tokenize_ops
from ml.mutation_engine.qa.gate_stub import gate
from ml.mutation_engine.routes import rule_route
from ml.real_data import gitutil
from ml.real_data.c_common import OUT_DIR, STATUS_CSV, permalink
from ml.real_data.rego_runner import evaluate, resource_for_rules
from ml.real_data.scan_repos import usable_repos
from ml.real_data.tf_normalise import normalise_repo
from privacy.airlock.airlock import AirlockBlocked, run_airlock
from privacy.airlock.projection import load_declarations

KEYWORDS = ("encrypt", "sse_", "version", "public", "cidr", "logging", "expiration", "lifecycle", "action", "resource", "storage")
INTERNAL_CIDR = "INTERNAL_CIDR"


def _op_for(attr, value):
    if attr == "ip_range":
        return {"op": "restrict_cidr", "attr": attr, "value": INTERNAL_CIDR}
    if attr == "has_lifecycle_expiration":
        return {"op": "set_lifecycle_rule", "attr": attr, "value": value}
    return {"op": "set_attr", "attr": attr, "value": copy.deepcopy(value)}


def ops_from_diff(rule_id, before_attrs, after_attrs, declarations=None):
    """(ops, reason). ops is [] and reason names the problem when the change cannot be expressed."""
    declared = (declarations or load_declarations())[rule_id] - {"resource_type"}
    ops = []
    for attr in sorted(declared):
        a, b = before_attrs.get(attr, MISSING), after_attrs.get(attr, MISSING)
        if a == b:
            continue
        if b == MISSING:
            return [], "out_of_vocabulary_attribute_removed"
        ops.append(_op_for(attr, b))
    if not ops:
        return [], "out_of_vocabulary_no_rule_field_changed"
    return ops, None


def _index(records):
    by_key = defaultdict(list)
    for rec in records:
        by_key[(rec["source"]["file"], rec["source"]["tf_type"], rec["source"]["tf_name"])].append(rec)
    return by_key


def pairs_for_commit(path, sha, parent, counters):
    pairs = []
    changed = [(s, f) for s, f in gitutil.changed_tf_files(path, sha) if s == "M"]
    for directory in sorted({f.rpartition("/")[0] for _s, f in changed}):
        before = _index(normalise_repo(gitutil.read_tf_files(path, parent, only_dir=directory))["records"])
        after = _index(normalise_repo(gitutil.read_tf_files(path, sha, only_dir=directory))["records"])
        for key in sorted(set(before) & set(after)):
            if len(before[key]) != 1 or len(after[key]) != 1:
                counters["ambiguous_multi_record"] += 1
                continue
            b, a = before[key][0], after[key][0]
            if b["resource_type"] != a["resource_type"]:
                continue
            counters["resource_pairs"] += 1
            if b["attrs"] == a["attrs"]:
                continue
            counters["resource_pairs_changed"] += 1
            pairs.append((b, a))
    return pairs


def mine_repo(row, vault, args, declarations=None):
    counters = Counter()
    path = row["path"]
    out, seen = [], set()
    for sha in gitutil.tf_commits(path, row["commit"], args.max_commits):
        counters["commits_touching_tf"] += 1
        parent = gitutil.parent_of(path, sha)
        if parent is None:
            continue
        text = gitutil.changed_lines(path, sha).lower()
        if not any(k in text for k in KEYWORDS):
            counters["commits_dropped_by_keyword_prefilter"] += 1
            continue
        pairs = pairs_for_commit(path, sha, parent, counters)
        if not pairs:
            continue
        verdicts = evaluate([resource_for_rules(b) for b, _a in pairs] + [resource_for_rules(a) for _b, a in pairs], policy_dir=args.policy_dir, opa=args.opa)
        n = len(pairs)
        for i, (b, a) in enumerate(pairs):
            fired_before = set(verdicts[i].deny) | set(verdicts[i].warn)
            fired_after = set(verdicts[n + i].deny) | set(verdicts[n + i].warn)
            for rule in sorted(fired_before - fired_after):
                counters["violating_before_passing_after"] += 1
                ops, why = ops_from_diff(rule, b["attrs"], a["attrs"], declarations)
                if why:
                    counters[why] += 1
                    continue
                res = Resource(b["resource_type"], b["attrs"], b["extras"])
                raw = raw_finding(res, "M-0", "tfm-" + b["norm_hash"][:12])
                try:
                    record, _receipt = run_airlock(raw, rule, vault=vault)
                    tokenized = tokenize_ops(raw, rule, record, ops, vault)
                except (AirlockBlocked, ValueError):
                    counters["airlock_or_token_problem"] += 1
                    continue
                patch = {"finding_id": record["finding_id"], "resource_ref": record["resource_ref"], "ops": tokenized, "rationale_ref": rule}
                if schema_errors(patch):
                    counters["not_schema_valid"] += 1
                    continue
                verdict = gate(record, patch)
                if not verdict.passed or verdict.outcome != "fixed":
                    counters["gate_rejected_human_fix"] += 1
                    continue
                key = (b["norm_hash"], rule, canon(tokenized))
                if key in seen:
                    counters["duplicate"] += 1
                    continue
                seen.add(key)
                if len(out) >= args.max_per_repo:
                    counters["over_repo_cap"] += 1
                    continue
                counters["in_vocabulary_gate_passing"] += 1
                plain = {"resource_type": b["resource_type"], "attrs": b["attrs"], "extras": b["extras"]}
                out.append({
                    "tier": "C-mined", "rule_id": rule, "input": record, "target": patch,
                    "meta": {"route": "fix", "tier": "C-mined", "split": "C-mined", "repo": row["repo"], "repo_id": int(row["repo_id"]),
                             "license": row["license"], "commit_before": parent, "commit_after": sha,
                             "file": b["source"]["file"], "tf_type": b["source"]["tf_type"], "tf_name": b["source"]["tf_name"],
                             "permalink_before": permalink(row["repo"], parent, b["source"]["file"]),
                             "permalink_after": permalink(row["repo"], sha, a["source"]["file"]),
                             "base_norm_hash": b["norm_hash"], "full_hash": full_hash(rule, plain)},
                    "qa": {"mutated": plain, "after": {"resource_type": a["resource_type"], "attrs": a["attrs"], "extras": a["extras"]}},
                })
    return out, counters


def main(argv=None):
    p = argparse.ArgumentParser(description="Mine real fixes from git history")
    p.add_argument("--status-csv", default=str(STATUS_CSV))
    p.add_argument("--max-commits", type=int, default=300, help="per repository, newest first")
    p.add_argument("--max-per-repo", type=int, default=40)
    p.add_argument("--policy-dir", default=None)
    p.add_argument("--opa", default=None)
    p.add_argument("--out", default=str(OUT_DIR / "tierC_mined_candidates.jsonl"))
    p.add_argument("--funnel", default=str(OUT_DIR / "mined_funnel.json"))
    o = p.parse_args(argv)
    if not Path(o.status_csv).exists():
        print("Missing {}. Run clone_repos first.".format(o.status_csv))
        return 2
    repos = usable_repos(o.status_csv)
    totals, rows = Counter(), []
    with throwaway_vault() as vault:
        for n, row in enumerate(repos, 1):
            try:
                found, counters = mine_repo(row, vault, o)
            except gitutil.GitError as exc:
                print("[{}/{}] {} skipped: {}".format(n, len(repos), row["repo"], exc))
                totals["repos_git_error"] += 1
                continue
            totals.update(counters)
            totals["repos_scanned"] += 1
            rows.extend(found)
            print("[{}/{}] {:<45} candidates so far: {}".format(n, len(repos), row["repo"], len(rows)), flush=True)
    for i, ex in enumerate(rows, 1):
        ex["id"] = "m-{:06d}".format(i)
    write_jsonl(o.out, rows)
    Path(o.funnel).parent.mkdir(parents=True, exist_ok=True)
    Path(o.funnel).write_text(json.dumps(dict(totals), indent=2, sort_keys=True) + "\n", encoding="ascii")
    print("Wrote {} candidate pairs to {}. NEXT: read them (review_tools mined-sheet).".format(len(rows), o.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
