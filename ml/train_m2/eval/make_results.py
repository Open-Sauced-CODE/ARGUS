"""Generator for docs/PHASE6_RESULTS.md reading run logs and out reports (Shaurya-owned).

RULES:
  - If held-out run log does not exist or is empty, writes "held-out: not yet run".
  - No hand-typed numbers: every number in the output must come from an input file.
  - Accompanied by provenance using write_provenance(path, seed=1337).
  - All outputs ASCII-only.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from ml.train_m2.common import repo_root, write_provenance

LOG = logging.getLogger(__name__)

SEED = 1337


def load_baseline_tests(root: Path) -> dict[str, str]:
    """Load baseline test numbers from p6f_baseline_tests.txt."""
    path = root / "ml" / "train_m2" / "out" / "reports" / "p6f_baseline_tests.txt"
    if not path.is_file():
        # Fallback to older baseline report if p6f not yet written
        path = root / "ml" / "train_m2" / "out" / "reports" / "a1s_baseline_tests.txt"
    if not path.is_file():
        return {}
    results = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if ":" in line:
            k, v = line.split(":", 1)
            results[k.strip()] = v.strip()
    return results


def load_crossfit_folds(root: Path) -> dict[str, Any]:
    """Load folds.json from docs/phase6_shaurya/crossfit/folds.json."""
    path = root / "docs" / "phase6_shaurya" / "crossfit" / "folds.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_tau_star(root: Path) -> dict[str, Any]:
    """Load tau_star.json."""
    path = root / "ml" / "train_m2" / "out" / "tau_star.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_mc_guarantee(root: Path) -> list[dict[str, Any]]:
    """Load mc_guarantee.json (jsonl format)."""
    path = root / "ml" / "train_m2" / "out" / "reports" / "mc_guarantee.json"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load_parity_check(root: Path) -> dict[str, Any]:
    """Load parity_500.json."""
    path = root / "ml" / "train_m2" / "out" / "reports" / "parity_500.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_licence_audit(root: Path) -> dict[str, Any]:
    """Load licence_audit.json."""
    path = root / "ml" / "train_m2" / "out" / "reports" / "licence_audit.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_heldout_results(root: Path) -> dict[str, Any] | None:
    """Check if held-out evaluation results exist and are non-empty."""
    candidates = [
        root / "ml" / "train_m2" / "out" / "reports" / "heldout_results.json",
        root / "ml" / "train_m2" / "out" / "heldout_results.json",
        root / "ml" / "train_m2" / "out" / "reports" / "heldout_eval.json",
    ]
    for p in candidates:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data:
                    return data
            except Exception:
                pass
    return None


def render_phase6_results(root: Path) -> str:
    """Assemble PHASE6_RESULTS.md with no hand-typed numbers."""
    baseline = load_baseline_tests(root)
    folds = load_crossfit_folds(root)
    tau = load_tau_star(root)
    mc = load_mc_guarantee(root)
    parity = load_parity_check(root)
    lic = load_licence_audit(root)
    heldout = load_heldout_results(root)

    lines = [
        "# Phase 6 Results Summary",
        "",
        "## 1. Held-Out Evaluation Status",
        "",
    ]

    if heldout is None:
        lines += [
            "held-out: not yet run",
            "",
            "> Per Hard Rule 5 and stop rule S4: held-out test sets remain sealed and un-opened.",
            "> Held-out evaluation will be run only after OOF harvest ingestion is completed.",
            "",
        ]
    else:
        lines += [
            "### Held-Out Evaluation Results",
            "",
            f"```json\n{json.dumps(heldout, indent=2)}\n```",
            "",
        ]

    lines += [
        "## 2. Baseline Test Verification",
        "",
        "| Test Suite | Result |",
        "|---|---|",
    ]
    for suite, result in sorted(baseline.items()):
        lines.append(f"| {suite} | {result} |")

    lines += [
        "",
        "## 3. Cross-Fit Folds Package (P6f-1)",
        "",
    ]
    if folds:
        lines += [
            f"- Seed: {folds.get('seed')}",
            f"- K: {folds.get('K')}",
            f"- Total train inputs: {folds.get('total_train_inputs')}",
            "",
            "| Fold | Total Inputs | Heldout Overlap | In A_val |",
            "|---|---|---|---|",
        ]
        for f_idx, counts in sorted(folds.get("counts_per_fold", {}).items()):
            lines.append(
                f"| {f_idx} | {counts.get('total')} | "
                f"{counts.get('heldout_overlap')} | {counts.get('in_a_val')} |"
            )
    else:
        lines.append("Cross-fit folds report not available.")

    lines += [
        "",
        "## 4. Calibration & LTT Guarantee Status (tau_star.json)",
        "",
    ]
    if tau:
        lines += [
            f"- Certified: {tau.get('certified')}",
            f"- Alpha: {tau.get('alpha')}",
            f"- Delta: {tau.get('delta')}",
            f"- Calibration clusters available (n_total): {tau.get('n_total')}",
            f"- Minimum clusters required (n_min): {tau.get('n_min')}",
            f"- Tau threshold: {tau.get('tau')}",
            f"- Message: {tau.get('message')}",
        ]
    else:
        lines.append("tau_star.json not available.")

    lines += [
        "",
        "## 5. Monte Carlo Guarantee Simulation (mc_guarantee.json)",
        "",
    ]
    if mc:
        lines += [
            f"Regimes evaluated: {len(mc)}  |  Reps per regime: {mc[0].get('reps')}",
            "",
            "| Regime | n_cal | true_err | certified_frac | LTT_coverage | CRC_coverage | CRC_exceeds_alpha | max_cond_error |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in mc:
            lines.append(
                f"| {r.get('name')} | {r.get('n_cal')} | {r.get('true_error_rate')} | "
                f"{r.get('ltt_certified_frac')} | {r.get('ltt_coverage')} | "
                f"{r.get('crc_coverage')} | {r.get('crc_exceeds_alpha')} | "
                f"{r.get('crc_max_cond_error')} |"
            )
    else:
        lines.append("mc_guarantee.json not available.")

    lines += [
        "",
        "## 6. Feature Parity Check (parity_500.json)",
        "",
    ]
    if parity:
        lines += [
            f"- Status: **{parity.get('status')}**",
            f"- Rows checked: {parity.get('total_rows_checked')}",
            f"- Mismatches: {parity.get('total_mismatches')}",
        ]
    else:
        lines.append("parity_500.json not available.")

    lines += [
        "",
        "## 7. Licence Audit (licence_audit.json)",
        "",
    ]
    if lic:
        deps = lic.get("dependencies", {})
        ds = lic.get("c_mined_dataset", {})
        bm = lic.get("base_model", {})
        lines += [
            f"- Total declared packages: {deps.get('total_declared_packages')}",
            f"  - Permissive: {deps.get('category_counts', {}).get('permissive', 0)}",
            f"  - Copyleft: {deps.get('category_counts', {}).get('copyleft', 0)}",
            f"  - Unverified / Not Installed: {deps.get('category_counts', {}).get('unverified', 0)}",
            f"- Base model ({bm.get('model_name')}): {bm.get('license')} ({bm.get('status')})",
            f"- C-mined dataset rows: {ds.get('total_rows', 0)} (Copyleft rows: {ds.get('copyleft_count', 0)})",
        ]
    else:
        lines.append("licence_audit.json not available.")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    root = repo_root()
    md_content = render_phase6_results(root)

    out_path = root / "docs" / "PHASE6_RESULTS.md"
    out_path.write_text(md_content, encoding="utf-8")
    write_provenance(out_path, seed=SEED)

    LOG.info("Written: %s", out_path)
    print(md_content)


if __name__ == "__main__":
    main()
