"""
ARGUS Phase 5, Step 11 - cross-check our findings against Trivy and Checkov (file-level agreement per rule).

    python -m ml.real_data.cross_check --export-dir C:\\argus_export

For every Tier C repository the .tf files at the recorded commit are written to a SHORT folder (--export-dir, keep the path short on Windows),
Trivy (`trivy config`) and Checkov (`checkov -d`) are run on it, and for each of our findings we ask: did the tool flag one of the mapped check
ids (ml/real_data/scanner_map.csv) in the same file? This is an approximate, file-level comparison, which is stated in the table.
Verify the ids in scanner_map.csv against the tools' current documentation before you quote the numbers.
A tool that is not installed is skipped (its column says 'not run').
Output: ml/real_data/out/scanner_agreement.csv and scanner_agreement.md
"""

import argparse
import csv
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from ml.mutation_engine.dataset_io import read_jsonl
from ml.real_data import gitutil
from ml.real_data.c_common import HELD_OUT_DIR, OUT_DIR, STATUS_CSV
from ml.real_data.scan_repos import usable_repos

MAP_CSV = Path(__file__).resolve().parent / "scanner_map.csv"


def load_map(path=MAP_CSV):
    out = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            out[row["rule_id"]] = {"trivy": [x for x in row["trivy_ids"].split(";") if x], "checkov": [x for x in row["checkov_ids"].split(";") if x]}
    return out


def parse_trivy(data):
    """{file: set of check ids} from `trivy config --format json` output."""
    flagged = defaultdict(set)
    for result in (data or {}).get("Results", []) or []:
        target = str(result.get("Target", "")).replace("\\", "/").lstrip("./")
        for item in result.get("Misconfigurations", []) or []:
            for key in ("ID", "AVDID"):
                if item.get(key):
                    flagged[target].add(str(item[key]))
    return flagged


def parse_checkov(data):
    """{file: set of check ids} from `checkov -o json` output (a dict, or a list of dicts when several frameworks ran)."""
    flagged = defaultdict(set)
    blocks = data if isinstance(data, list) else [data or {}]
    for block in blocks:
        for item in (block.get("results", {}) or {}).get("failed_checks", []) or []:
            flagged[str(item.get("file_path", "")).replace("\\", "/").lstrip("/")].add(str(item.get("check_id", "")))
    return flagged


def agrees(flagged_ids, wanted):
    return any(f == w or f.endswith(w) for f in flagged_ids for w in wanted)


def export_repo(row, export_dir):
    target = Path(export_dir) / str(row["repo_id"])
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    for path, text in gitutil.read_tf_files(row["path"], row["commit"]).items():
        dest = target / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8", newline="\n")
    return target


def run_tool(cmd, timeout=900):
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    text = proc.stdout.decode("utf-8", "replace")
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    return json.loads(text[start:]) if start >= 0 else None


def table(findings, mapping, trivy_flags, checkov_flags, have_trivy, have_checkov):
    per = defaultdict(lambda: {"ours": 0, "trivy_agree": 0, "checkov_agree": 0})
    for ex in findings:
        key = (ex["meta"]["repo_id"], ex["meta"]["file"])
        rule = ex["rule_id"]
        per[rule]["ours"] += 1
        if have_trivy and agrees(trivy_flags.get(key, set()), mapping.get(rule, {}).get("trivy", [])):
            per[rule]["trivy_agree"] += 1
        if have_checkov and agrees(checkov_flags.get(key, set()), mapping.get(rule, {}).get("checkov", [])):
            per[rule]["checkov_agree"] += 1
    return per


def main(argv=None):
    p = argparse.ArgumentParser(description="Cross-check our findings with Trivy and Checkov")
    p.add_argument("--export-dir", default="C:\\argus_export" if sys.platform.startswith("win") else "/tmp/argus_export")
    p.add_argument("--status-csv", default=str(STATUS_CSV))
    p.add_argument("--verifier", default=str(HELD_OUT_DIR / "tierC_verifier.jsonl"))
    o = p.parse_args(argv)
    have_trivy, have_checkov = shutil.which("trivy") is not None, shutil.which("checkov") is not None
    if not (have_trivy or have_checkov):
        print("Neither trivy nor checkov is on PATH. Install at least one (see the guide) and run again.")
        return 2
    findings = read_jsonl(o.verifier)
    if not findings:
        print("tierC_verifier.jsonl is empty or missing. Run scan_repos first.")
        return 2
    mapping = load_map()
    trivy_flags, checkov_flags = {}, {}
    repos = usable_repos(o.status_csv)
    wanted = {int(r["repo_id"]) for r in repos} & {ex["meta"]["repo_id"] for ex in findings}
    for n, row in enumerate([r for r in repos if int(r["repo_id"]) in wanted], 1):
        folder = export_repo(row, o.export_dir)
        print("[{}] {} exported to {}".format(n, row["repo"], folder), flush=True)
        if have_trivy:
            for f, ids in parse_trivy(run_tool(["trivy", "config", "--format", "json", "--quiet", str(folder)])).items():
                trivy_flags[(int(row["repo_id"]), f)] = ids
        if have_checkov:
            for f, ids in parse_checkov(run_tool(["checkov", "-d", str(folder), "--framework", "terraform", "-o", "json", "--quiet"])).items():
                checkov_flags[(int(row["repo_id"]), f)] = ids
    per = table(findings, mapping, trivy_flags, checkov_flags, have_trivy, have_checkov)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    from typing import Any

    rows: list[list[Any]] = [["rule_id", "our_findings", "trivy_agree", "checkov_agree"]]
    lines = ["# Agreement with Trivy and Checkov (file level, approximate)", "", "| rule | our findings | Trivy agrees | Checkov agrees |", "|---|---:|---:|---:|"]
    for rule in sorted(per):
        v = per[rule]
        t = "{}/{}".format(v["trivy_agree"], v["ours"]) if have_trivy else "not run"
        c = "{}/{}".format(v["checkov_agree"], v["ours"]) if have_checkov else "not run"
        rows.append([rule, v["ours"], t, c])
        lines.append("| {} | {} | {} | {} |".format(rule, v["ours"], t, c))
    with open(OUT_DIR / "scanner_agreement.csv", "w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)
    (OUT_DIR / "scanner_agreement.md").write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
