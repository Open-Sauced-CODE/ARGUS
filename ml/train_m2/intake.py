"""Phase 6 intake: reproduce and extend the Phase 5 numbers from the real files. Read-only; no models, no network.

    py -m ml.train_m2.intake [--root .] [--out ml/train_m2/out/reports/intake_report] [--allow-missing]

It answers, with numbers computed from the files themselves:
  * does the Phase 5 dataset manifest still verify (sha256 of every dataset file)?
  * per set: rows, DISTINCT inputs (the real sample size), routes, escalate rows, distinct inputs per rule
  * how much do the sets overlap (the share of each held-out set's inputs that are also in train)
  * per generator and set: candidates, gate-passing, gate-passing-but-hidden-fail, empty replies, how many different
    answers the 8 samples give, whether logprobs were saved, and pass@1 / pass@8 recomputed and compared with the summaries
  * natural negatives: distinct inputs where a gate-passing candidate was still wrong (the scarce resource of Phase 6)
  * is contract/harvest_inputs.jsonl exactly the set of distinct inputs of all sets?
  * licences of the source repositories (copyleft share)

Exit code 0 = report written; 3 = required files missing (unless --allow-missing).
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from ml.train_m2.common import cluster_key, jsonl_iter, load_inputs, repo_root, sha256_file, write_provenance
from ml.train_m2.labels.canon import distinct_answers, is_escalate_only

DATASET_SETS = (
    ("train", "dataset/train.jsonl"),
    ("A_val", "dataset/val.jsonl"),
    ("B1", "held_out/tierB1.jsonl"),
    ("B2", "held_out/tierB2.jsonl"),
    ("C_verifier", "held_out/tierC_verifier.jsonl"),
    ("gold", "held_out/gold.jsonl"),
    ("C_mined", "held_out/tierC_mined.jsonl"),
)
CANDIDATE_SETS = ("A_val", "train300", "B1", "B2", "C_verifier", "gold")
GENERATORS = ("zeroshot", "sft", "rft")
COPYLEFT = ("agpl", "gpl", "lgpl", "mpl", "epl", "eupl", "cc-by-sa", "cddl", "osl")
PASS_AT_TOLERANCE = 0.005
ME_RELPATH = Path("ml") / "mutation_engine"
RUNS_RELPATH = Path("ml") / "train_m1" / "eval" / "runs"
HARVEST_INPUTS_RELPATH = Path("ml") / "train_m2" / "contract" / "harvest_inputs.jsonl"


def verify_manifest(me_root: Path) -> dict[str, Any]:
    """Check every line of ml/mutation_engine/MANIFEST.sha256: '<sha256>  <path relative to me_root>'."""
    manifest = me_root / "MANIFEST.sha256"
    if not manifest.is_file():
        return {"present": False, "results": [], "ok": 0, "problems": 0}
    results = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        digest, name = parts[0], parts[1].lstrip("*").strip()
        path = me_root / name
        if not path.is_file():
            results.append({"file": name, "status": "missing"})
        elif sha256_file(path) != digest:
            results.append({"file": name, "status": "mismatch"})
        else:
            results.append({"file": name, "status": "ok"})
    ok = sum(1 for r in results if r["status"] == "ok")
    return {"present": True, "results": results, "ok": ok, "problems": len(results) - ok}


def load_dataset_sets(me_root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Per set: rows, input-key counter, routes, escalate rows, rule -> distinct input keys. Plus the missing files."""
    sets: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for name, rel in DATASET_SETS:
        path = me_root / rel
        if not path.is_file():
            missing.append(str(rel))
            continue
        keys: Counter[str] = Counter()
        routes: Counter[str] = Counter()
        rules: dict[str, set[str]] = defaultdict(set)
        escalate = rows = 0
        for row in jsonl_iter(path):
            rows += 1
            key = cluster_key(row)
            keys[key] += 1
            rules[row.get("rule_id", "?")].add(key)
            route = str((row.get("meta") or {}).get("route", "?"))
            routes[route] += 1
            escalate += int(route == "escalate" or is_escalate_only((row.get("target") or {}).get("ops")))
        sets[name] = {"rows": rows, "keys": keys, "routes": routes, "escalate_rows": escalate, "rules": rules}
    return sets, missing


def overlap_report(sets: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    names = [n for n in sets if sets[n]["rows"]]
    pairs = {}
    for a, b in itertools.combinations(names, 2):
        both = len(set(sets[a]["keys"]) & set(sets[b]["keys"]))
        if both:
            pairs[f"{a}&{b}"] = both
    in_train = {}
    if "train" in sets:
        train_keys = set(sets["train"]["keys"])
        for n in names:
            if n == "train":
                continue
            keys = set(sets[n]["keys"])
            in_train[n] = {"distinct": len(keys), "also_in_train": len(keys & train_keys),
                           "share": round(len(keys & train_keys) / len(keys), 4) if keys else 0.0}
    return {"pairs": pairs, "share_in_train": in_train}


def candidate_stats(runs_dir: Path) -> tuple[dict[str, Any], list[str]]:
    """Per generator and set statistics from Phase 5 candidate logs, with pass@k recomputed from the per-input flags."""
    out: dict[str, Any] = {"cells": [], "natural_negative_clusters": {}, "pass_at_checks": [], "logprobs_present": False}
    missing: list[str] = []
    negatives: dict[str, set[str]] = defaultdict(set)
    for generator in GENERATORS:
        for set_name in CANDIDATE_SETS:
            path = runs_dir / generator / f"{set_name}.candidates.jsonl"
            if not path.is_file():
                missing.append(f"{generator}/{set_name}.candidates.jsonl")
                continue
            inputs = examples = cands = gate_pass = gp_hidden_fail = gp_escalated = empty = 0
            distinct: list[int] = []
            p1 = p8 = 0
            for row in jsonl_iter(path):
                inputs += 1
                weight = max(1, len(row.get("example_ids", [])))
                examples += weight
                scored = row["scored"]
                if scored.get("pass_at", {}).get("1"):
                    p1 += weight
                if scored.get("pass_at", {}).get("8"):
                    p8 += weight
                if "tokens" in row or "logprobs" in row:
                    out["logprobs_present"] = True
                contents = row.get("contents", [])
                empty += sum(1 for c in contents if not c)
                distinct.append(distinct_answers(contents))
                found_negative = False
                for cand in scored["candidates"]:
                    cands += 1
                    if cand.get("gate_passed"):
                        gate_pass += 1
                        gp_escalated += int(bool(cand.get("escalated")))
                        if cand.get("hidden_ok") is False:
                            gp_hidden_fail += 1
                            found_negative = True
                if found_negative:
                    negatives[generator].add(row["input_key"])
            out["cells"].append({
                "generator": generator, "set": set_name, "inputs": inputs, "examples": examples, "candidates": cands,
                "gate_passing": gate_pass, "gate_passing_hidden_fail": gp_hidden_fail, "gate_passing_escalated": gp_escalated,
                "empty_replies": empty, "mean_distinct_answers": round(sum(distinct) / len(distinct), 3) if distinct else 0.0,
                "pass_at_1_examples": p1, "pass_at_8_examples": p8,
            })
            summary_path = runs_dir / generator / f"{set_name}.summary.json"
            if summary_path.is_file():
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                for k, got in (("1", p1), ("8", p8)):
                    want = int(summary.get("pass_at", {}).get(k, -1))
                    total = int(summary.get("examples", examples)) or 1
                    diff = (got - want) / total
                    out["pass_at_checks"].append({
                        "generator": generator, "set": set_name, "k": int(k), "recomputed": got, "summary": want,
                        "examples": total, "diff_points": round(100 * diff, 2), "flag": abs(diff) > PASS_AT_TOLERANCE,
                    })
    for generator in GENERATORS:
        out["natural_negative_clusters"][generator] = len(negatives.get(generator, set()))
    out["natural_negative_clusters"]["union"] = len(set().union(*negatives.values())) if negatives else 0
    return out, missing


def harvest_inputs_check(inputs_path: Path, sets: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if not inputs_path.is_file():
        return {"present": False}
    keys = {row["input_key"] for row in load_inputs(inputs_path)}
    union: set[str] = set()
    for info in sets.values():
        union |= set(info["keys"])
    return {
        "present": True, "harvest_inputs": len(keys), "distinct_inputs_all_sets": len(union),
        "equal": keys == union, "missing_from_list": len(union - keys), "extra_in_list": len(keys - union),
    }


def licence_summary(me_root: Path) -> dict[str, Any]:
    path = me_root / "bases" / "manifest.csv"
    if not path.is_file():
        return {"present": False}
    counts: Counter[str] = Counter()
    with open(path, "r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            counts[(row.get("license") or "unknown").strip() or "unknown"] += 1
    copyleft = {name: n for name, n in counts.items() if any(tok in name.lower() for tok in COPYLEFT)}
    total = sum(counts.values())
    return {
        "present": True, "bases": total, "licences": dict(counts.most_common()),
        "copyleft_bases": sum(copyleft.values()), "copyleft_share": round(sum(copyleft.values()) / total, 4) if total else 0.0,
        "copyleft_by_licence": dict(sorted(copyleft.items(), key=lambda kv: -kv[1])),
    }


def build_report(root: Path) -> tuple[dict[str, Any], list[str]]:
    me_root = root / ME_RELPATH
    sets, missing = load_dataset_sets(me_root)
    candidates, missing_candidates = candidate_stats(root / RUNS_RELPATH)
    report = {
        "manifest": verify_manifest(me_root),
        "sets": {
            n: {
                "rows": s["rows"], "distinct_inputs": len(s["keys"]), "max_rows_per_input": max(s["keys"].values(), default=0),
                "routes": dict(s["routes"]), "escalate_rows": s["escalate_rows"],
                "distinct_inputs_per_rule": {r: len(k) for r, k in sorted(s["rules"].items())},
            }
            for n, s in sets.items()
        },
        "overlap": overlap_report(sets),
        "candidates": candidates,
        "harvest_inputs": harvest_inputs_check(root / HARVEST_INPUTS_RELPATH, sets),
        "licences": licence_summary(me_root),
    }
    return report, missing + missing_candidates


def render_markdown(report: Mapping[str, Any], missing: Sequence[str]) -> str:
    L: list[str] = ["# Phase 6 intake report", ""]
    m = report["manifest"]
    L += ["## Dataset manifest", "", "not found" if not m["present"] else f"{m['ok']} files verified, {m['problems']} problem(s)"]
    for r in m["results"]:
        if r["status"] != "ok":
            L.append(f"- {r['status'].upper()}: {r['file']}")
    L += ["", "## Sets: rows versus distinct inputs (the real sample size)", "",
          "| set | rows | distinct inputs | max rows per input | escalate rows | routes |", "|---|---|---|---|---|---|"]
    for n, s in report["sets"].items():
        L.append(f"| {n} | {s['rows']} | {s['distinct_inputs']} | {s['max_rows_per_input']} | {s['escalate_rows']} | {s['routes']} |")
    L += ["", "## Share of each set's distinct inputs that is also in train", "", "| set | distinct | also in train | share |", "|---|---|---|---|"]
    for n, v in report["overlap"]["share_in_train"].items():
        L.append(f"| {n} | {v['distinct']} | {v['also_in_train']} | {v['share']:.0%} |")
    L += ["", "## Candidate logs by generator and set", "",
          "| generator | set | inputs | candidates | gate-passing | passing but hidden-fail | empty replies | mean distinct answers of 8 |",
          "|---|---|---|---|---|---|---|---|"]
    for c in report["candidates"]["cells"]:
        L.append(f"| {c['generator']} | {c['set']} | {c['inputs']} | {c['candidates']} | {c['gate_passing']} | "
                 f"{c['gate_passing_hidden_fail']} | {c['empty_replies']} | {c['mean_distinct_answers']} |")
    L += ["", f"Logprobs saved in the Phase 5 logs: **{report['candidates']['logprobs_present']}**", "",
          "Natural negatives (distinct inputs with a gate-passing but hidden-check-failing candidate): "
          + ", ".join(f"{k} {v}" for k, v in report["candidates"]["natural_negative_clusters"].items()), ""]
    flagged = [c for c in report["candidates"]["pass_at_checks"] if c["flag"]]
    L += ["## pass@k recomputed from the logs versus the Phase 5 summaries", "",
          f"{len(report['candidates']['pass_at_checks'])} comparisons, {len(flagged)} differ by more than 0.5 point"]
    for c in flagged:
        L.append(f"- {c['generator']}/{c['set']} pass@{c['k']}: recomputed {c['recomputed']}, summary {c['summary']} ({c['diff_points']:+} points)")
    h = report["harvest_inputs"]
    L += ["", "## contract/harvest_inputs.jsonl", ""]
    if not h["present"]:
        L.append("not found")
    else:
        L.append(f"{h['harvest_inputs']} inputs in the list; {h['distinct_inputs_all_sets']} distinct inputs across all sets; "
                 f"identical sets: **{h['equal']}** (missing from list {h['missing_from_list']}, extra in list {h['extra_in_list']})")
    lic = report["licences"]
    L += ["", "## Source-repository licences", ""]
    if not lic["present"]:
        L.append("not found")
    else:
        L.append(f"{lic['bases']} bases; copyleft: {lic['copyleft_bases']} ({lic['copyleft_share']:.1%}) {lic['copyleft_by_licence']}")
    if missing:
        L += ["", "## Missing files", ""] + [f"- {name}" for name in missing]
    return "\n".join(L) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=repo_root())
    parser.add_argument("--out", type=Path, default=None, help="output path without extension")
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args(argv)
    out = args.out or (args.root / "ml" / "train_m2" / "out" / "reports" / "intake_report")
    report, missing = build_report(args.root)
    out.parent.mkdir(parents=True, exist_ok=True)
    md = render_markdown(report, missing)
    Path(str(out) + ".md").write_text(md, encoding="utf-8", newline="\n")
    json_path = Path(str(out) + ".json")
    json_path.write_text(json.dumps({"report": report, "missing": list(missing)}, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                         encoding="utf-8", newline="\n")
    write_provenance(json_path, extra={"tool": "intake", "missing": list(missing)})
    print(md)
    print(f"report written: {out}.md and {out}.json")
    if missing and not args.allow_missing:
        print(f"MISSING {len(missing)} required file(s); copy the git-ignored data from ml.zip first (see list above)")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
