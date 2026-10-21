"""
ARGUS Phase 5, Step 12 - write ml/real_data/funnel_report.md (the numbers behind Tier C).

    python -m ml.real_data.funnel_report
"""

import json
import sys
from pathlib import Path

from ml.mutation_engine.dataset_io import read_jsonl
from ml.real_data.c_common import HELD_OUT_DIR, OUT_DIR, REPO_ROOT

OUT = REPO_ROOT / "ml" / "real_data" / "funnel_report.md"


def load(path):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main(argv=None):
    scan = load(OUT_DIR / "tierC_scan_summary.json")
    mined = load(OUT_DIR / "mined_funnel.json")
    kept = len(read_jsonl(HELD_OUT_DIR / "tierC_mined.jsonl"))
    cands = len(read_jsonl(OUT_DIR / "tierC_mined_candidates.jsonl"))
    lines = ["# Tier C funnel", "", "## Tier C-verifier (our rules on real repositories)", "| step | count |", "|---|---:|"]
    for key in ("repos_scanned", "files_parsed", "parse_errors", "records", "resources_skipped_unresolved", "violations", "duplicate_in_repo",
                "over_repo_cap", "duplicate_across_repos", "blocked_by_airlock", "findings_written"):
        lines.append("| {} | {} |".format(key, scan.get(key, 0)))
    lines += ["", "Findings by rule: {}".format(scan.get("by_rule", {})), "", "## Tier C-mined (real fixes from git history)", "| step | count |", "|---|---:|"]
    for key in ("repos_scanned", "repos_git_error", "commits_touching_tf", "commits_dropped_by_keyword_prefilter", "ambiguous_multi_record",
                "resource_pairs", "resource_pairs_changed", "violating_before_passing_after", "out_of_vocabulary_attribute_removed",
                "out_of_vocabulary_no_rule_field_changed", "airlock_or_token_problem", "not_schema_valid", "gate_rejected_human_fix", "duplicate",
                "over_repo_cap", "in_vocabulary_gate_passing"):
        lines.append("| {} | {} |".format(key, mined.get(key, 0)))
    lines += ["| candidates written for review | {} |".format(cands), "| reviewed and kept by a person | {} |".format(kept), "",
              "Each drop is informative: a large out-of-vocabulary count says how often real fixes need operations Patch-IR does not have.", ""]
    OUT.write_text("\n".join(lines), encoding="ascii", errors="replace")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
