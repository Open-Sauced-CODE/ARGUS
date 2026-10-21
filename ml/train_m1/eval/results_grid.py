"""
ARGUS Phase 5, Step 21 - the results grid and paired comparisons.

    python -m ml.train_m1.eval.results_grid                      writes eval/results_grid.md
    python -m ml.train_m1.eval.results_grid --compare sft zeroshot B1    McNemar test (pass@k per distinct input) between two labels
"""

import argparse
import json
import sys
from pathlib import Path

from ml.train_m1.stats import mcnemar_exact

RUNS = Path(__file__).resolve().parent / "runs"
SETS = ("A_val", "train300", "B1", "B2", "C_verifier", "C_mined", "gold")


def load(label, set_name):
    p = RUNS / label / (set_name + ".summary.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def grid():
    labels = sorted(d.name for d in RUNS.iterdir() if d.is_dir()) if RUNS.exists() else []
    lines = ["# Results grid (gate pass: pass@1 / pass@k, count and Wilson 95% interval)", ""]
    for kind, key in (("pass@1", "pass_at_1_text"), ("pass@k", "pass_at_k_text")):
        lines += ["## " + kind, "| model | " + " | ".join(SETS) + " |", "|---|" + "---|" * len(SETS)]
        for lab in labels:
            row = [(load(lab, s) or {}).get(key, "-") for s in SETS]
            lines.append("| {} | {} |".format(lab, " | ".join(row)))
        lines.append("")
    lines += ["## Safety and escalation", "| model | set | unsafe candidates | schema-valid | hidden-ok among gate-passing | escalate P / R | median s to first pass |", "|---|---|---|---|---|---|---|"]
    for lab in labels:
        for s in SETS:
            d = load(lab, s)
            if d:
                e = d["escalate"]
                lines.append("| {} | {} | {}/{} | {}/{} | {}/{} | {} / {} | {} |".format(
                    lab, s, *d["unsafe_candidates"], *d["schema_valid_candidates"], *d["hidden_ok_among_gate_passing"],
                    "n/a" if e["precision"] is None else "%.2f" % e["precision"], "n/a" if e["recall"] is None else "%.2f" % e["recall"],
                    d["median_seconds_to_first_pass"]))
    lines += ["", "## Training-versus-held-out gap (pass@1 percentage points; investigate if above 20)"]
    for lab in labels:
        tr = load(lab, "train300")
        if tr:
            for s in ("B1", "B2", "C_verifier"):
                d = load(lab, s)
                if d:
                    gap = 100.0 * (tr["pass_at"]["1"] / tr["examples"] - d["pass_at"]["1"] / d["examples"])
                    lines.append("- {}: train300 minus {} = {:.1f} points".format(lab, s, gap))
    (Path(__file__).resolve().parent / "results_grid.md").write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")
    print("\n".join(lines))


def compare(a, b, set_name, k):
    def flags(label):
        out = {}
        for line in (RUNS / label / (set_name + ".candidates.jsonl")).read_text().splitlines():
            row = json.loads(line)
            out[row["input_key"]] = bool(row["scored"]["pass_at"].get(str(k), row["scored"]["pass_at"].get(k)))
        return out
    fa, fb = flags(a), flags(b)
    keys = sorted(set(fa) & set(fb))
    only_a = sum(1 for x in keys if fa[x] and not fb[x])
    only_b = sum(1 for x in keys if fb[x] and not fa[x])
    print("{} vs {} on {} (pass@{}, {} distinct inputs): only {} right {}, only {} right {}, McNemar p = {:.4f}".format(
        a, b, set_name, k, len(keys), a, only_a, b, only_b, mcnemar_exact(only_a, only_b)))


def main(argv=None):
    p = argparse.ArgumentParser(description="Results grid")
    p.add_argument("--compare", nargs=3, metavar=("A", "B", "SET"))
    p.add_argument("--k", type=int, default=8)
    o = p.parse_args(argv)
    if o.compare:
        compare(o.compare[0], o.compare[1], o.compare[2], o.k)
    else:
        grid()
    return 0


if __name__ == "__main__":
    sys.exit(main())
