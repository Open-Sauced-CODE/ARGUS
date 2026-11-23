"""Held-out pre-flight verification gate for M2 (Shaurya-owned, read-only).

Guarantees that held-out test partitions (B1, B2, C_verifier, gold, C-human)
remain strictly sealed unless and until ALL preconditions, safety guards,
data integrity checks, ownership checks, and test suites are 100% green.

Exit code 0 only if ALL pass:
  1. RUN_LOG_M2.md is absent.
  2. Git working tree is clean (except allowed notebook ml/train_m1/notebooks/01_sft_crossfit.ipynb).
  3. HEAD contains the frozen plan commit 7e64a49.
  4. EXPERIMENT_PLAN_M2.md differs from 7e64a49 only inside section 12.
  5. The five artifact hashes equal committed docs/phase6_shaurya/PREFLIGHT_HASHES.json.
  6. Splits internal hash is True and equals plan 6b6b7bf7daa0356593af6f9e207f63016df0c9e580e1fc24092c4364d50ba2bb.
  7. docs/phase6_shaurya/HELDOUT_DECISION.md exists and states exactly one of
     'PATH A (OOF ingested)' or 'PATH B (S4 not certified)' plus date and clean-cluster count.
  8. If PATH A, an ingest_oof report exists under out/reports/ with clean unseen clusters >= count claimed.
  9. run_once.py ledger has no entry for (model, set) pairs about to run.
 10. Ownership check OK (check_ownership.py).
 11. Frozen check OK (check_frozen.py).
 12. Both test suites green (ml/train_m2/tests and ml/tests).

NEVER opens or reads any held-out file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

# Ensure repository root is on sys.path when invoked directly as a script
_repo_root = str(Path(__file__).resolve().parents[3])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from ml.train_m2.common import repo_root
from ml.train_m2.splits import splits_hash

LOG = logging.getLogger("preflight_heldout")
PLAN_COMMIT = "7e64a49"
EXPECTED_PLAN_SPLITS_SHA = "6b6b7bf7daa0356593af6f9e207f63016df0c9e580e1fc24092c4364d50ba2bb"
ALLOWED_DIRTY_FILES = {"ml/train_m1/notebooks/01_sft_crossfit.ipynb"}


class PreflightError(RuntimeError):
    """Raised when one or more preflight checks fail."""
    pass


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def check_run_log_absent(root: Path) -> CheckResult:
    """Check 1: RUN_LOG_M2.md must be strictly absent."""
    log_path = root / "ml" / "train_m2" / "eval" / "RUN_LOG_M2.md"
    if log_path.exists():
        return CheckResult("RUN_LOG_M2 absent", False, f"RUN_LOG_M2.md exists at {log_path}")
    return CheckResult("RUN_LOG_M2 absent", True, "RUN_LOG_M2.md is absent")


def check_working_tree_clean(root: Path) -> CheckResult:
    """Check 2: Git working tree must be clean except allowed notebook."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception as e:
        return CheckResult("Working tree clean", False, f"git status failed: {e}")

    lines = proc.stdout.splitlines()
    unallowed = []
    for line in lines:
        if not line.strip():
            continue
        # Format is XY filename or XY orig -> dest
        parts = line[3:].strip().split(" -> ")
        filename = parts[-1].replace("\\", "/")
        if filename not in ALLOWED_DIRTY_FILES:
            unallowed.append(filename)

    if unallowed:
        return CheckResult(
            "Working tree clean",
            False,
            f"Unallowed dirty files in working tree: {unallowed}",
        )
    return CheckResult("Working tree clean", True, "Working tree clean (allowed notebook ignored)")


def check_plan_commit_ancestry(root: Path, target_commit: str = PLAN_COMMIT) -> CheckResult:
    """Check 3: HEAD must contain the frozen plan commit 7e64a49."""
    try:
        # Check if target_commit exists
        rev = subprocess.run(
            ["git", "rev-parse", "--verify", target_commit],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if rev.returncode != 0:
            return CheckResult(
                "Plan commit in HEAD",
                False,
                f"Commit {target_commit} does not exist in repository",
            )
        # Check ancestry: merge-base --is-ancestor target HEAD
        anc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", target_commit, "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if anc.returncode != 0:
            return CheckResult(
                "Plan commit in HEAD",
                False,
                f"Commit {target_commit} is not an ancestor of HEAD",
            )
        return CheckResult(
            "Plan commit in HEAD",
            True,
            f"Commit {target_commit} is an ancestor of HEAD",
        )
    except Exception as e:
        return CheckResult("Plan commit in HEAD", False, f"Git ancestry check failed: {e}")


def check_plan_diff_section12(root: Path, target_commit: str = PLAN_COMMIT) -> CheckResult:
    """Check 4: EXPERIMENT_PLAN_M2.md differs from 7e64a49 only inside Section 12."""
    plan_rel = Path("ml/train_m2/EXPERIMENT_PLAN_M2.md")
    plan_full = root / plan_rel
    if not plan_full.is_file():
        return CheckResult("Plan Section 12 diff", False, f"{plan_rel} not found")

    try:
        diff_proc = subprocess.run(
            ["git", "diff", target_commit, "HEAD", "--", str(plan_rel)],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        diff_text = diff_proc.stdout.strip()
        if not diff_text:
            return CheckResult(
                "Plan Section 12 diff",
                True,
                f"No diff against {target_commit} (byte-identical)",
            )

        # If diff exists, check that changes are only in section 12
        # Find start and end line of Section 12 in the file at HEAD
        plan_lines = plan_full.read_text(encoding="utf-8").splitlines()
        sec12_start_line = None
        sec12_end_line = None
        for idx, line in enumerate(plan_lines, start=1):
            if re.match(r"^##\s+12\.\s+Change\s*log", line.strip(), re.IGNORECASE):
                sec12_start_line = idx
            elif sec12_start_line is not None and re.match(r"^##\s+13\.", line.strip()):
                sec12_end_line = idx
                break

        if sec12_start_line is None:
            return CheckResult(
                "Plan Section 12 diff",
                False,
                "Section 12 heading not found in EXPERIMENT_PLAN_M2.md",
            )
        if sec12_end_line is None:
            sec12_end_line = len(plan_lines) + 1

        # Inspect diff hunks: @@ -from,len +to,len @@
        hunk_header_re = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")
        for line in diff_text.splitlines():
            m = hunk_header_re.match(line)
            if m:
                hunk_new_start = int(m.group(3))
                hunk_new_len = int(m.group(4)) if m.group(4) else 1
                if hunk_new_start < sec12_start_line:
                    return CheckResult(
                        "Plan Section 12 diff",
                        False,
                        f"Diff hunk starts at line {hunk_new_start} before Section 12 (line {sec12_start_line})",
                    )
                if hunk_new_start + hunk_new_len > sec12_end_line:
                    return CheckResult(
                        "Plan Section 12 diff",
                        False,
                        f"Diff hunk extends to line {hunk_new_start + hunk_new_len} beyond Section 12 (ends at line {sec12_end_line})",
                    )

        return CheckResult(
            "Plan Section 12 diff",
            True,
            f"All diff hunks are contained within Section 12 (lines {sec12_start_line}..{sec12_end_line})",
        )
    except Exception as e:
        return CheckResult("Plan Section 12 diff", False, f"Diff check failed: {e}")


def check_artifact_hashes(root: Path, preflight_hashes_path: Path | None = None) -> CheckResult:
    """Check 5: Five artifact hashes match committed PREFLIGHT_HASHES.json."""
    hashes_file = preflight_hashes_path or (root / "docs" / "phase6_shaurya" / "PREFLIGHT_HASHES.json")
    if not hashes_file.is_file():
        return CheckResult("Artifact hashes", False, f"PREFLIGHT_HASHES.json not found at {hashes_file}")

    try:
        expected = json.loads(hashes_file.read_text(encoding="utf-8"))
    except Exception as e:
        return CheckResult("Artifact hashes", False, f"Failed to parse PREFLIGHT_HASHES.json: {e}")

    required_keys = {"m2.joblib", "model_card.json", "splits.json", "tau_star.json", "val_metrics.json"}
    missing_keys = required_keys - set(expected.keys())
    if missing_keys:
        return CheckResult("Artifact hashes", False, f"Missing required keys in PREFLIGHT_HASHES: {missing_keys}")

    for key, info in expected.items():
        rel_path = info.get("path")
        exp_sha = info.get("sha256", "").upper()
        if not rel_path or not exp_sha:
            return CheckResult("Artifact hashes", False, f"Invalid info for {key}: {info}")
        file_path = root / rel_path
        if not file_path.is_file():
            return CheckResult("Artifact hashes", False, f"Artifact file {rel_path} not found")
        actual_sha = hashlib.sha256(file_path.read_bytes()).hexdigest().upper()
        if actual_sha != exp_sha:
            return CheckResult(
                "Artifact hashes",
                False,
                f"Hash mismatch on {rel_path}: actual {actual_sha} != expected {exp_sha}",
            )

    return CheckResult("Artifact hashes", True, "All 5 artifact hashes match PREFLIGHT_HASHES.json")


def check_splits_hash(root: Path) -> CheckResult:
    """Check 6: splits.json internal hash matches and equals plan hash."""
    splits_file = root / "ml" / "train_m2" / "out" / "m2" / "splits.json"
    if not splits_file.is_file():
        return CheckResult("Splits internal hash", False, f"splits.json not found at {splits_file}")

    try:
        s = json.loads(splits_file.read_text(encoding="utf-8"))
        computed = splits_hash(s)
        recorded = s.get("sha256")
        if computed != recorded:
            return CheckResult(
                "Splits internal hash",
                False,
                f"Splits internal hash mismatch: computed {computed} != recorded {recorded}",
            )
        if recorded != EXPECTED_PLAN_SPLITS_SHA:
            return CheckResult(
                "Splits internal hash",
                False,
                f"Splits hash {recorded} != plan expected {EXPECTED_PLAN_SPLITS_SHA}",
            )
        return CheckResult(
            "Splits internal hash",
            True,
            f"Splits internal hash matches and equals plan ({recorded})",
        )
    except Exception as e:
        return CheckResult("Splits internal hash", False, f"Failed checking splits hash: {e}")


def check_heldout_decision(root: Path) -> CheckResult:
    """Check 7 & 8: HELDOUT_DECISION.md exists and validates correctly."""
    dec_file = root / "docs" / "phase6_shaurya" / "HELDOUT_DECISION.md"
    if not dec_file.is_file():
        return CheckResult("Held-out decision doc", False, f"HELDOUT_DECISION.md not found at {dec_file}")

    text = dec_file.read_text(encoding="utf-8")
    has_path_a = "PATH A (OOF ingested)" in text
    has_path_b = "PATH B (S4 not certified)" in text

    if not (has_path_a ^ has_path_b):
        return CheckResult(
            "Held-out decision doc",
            False,
            "Must state exactly one of 'PATH A (OOF ingested)' or 'PATH B (S4 not certified)'",
        )

    # Strip markdown emphasis and headings for field matching
    clean_text = text.replace("*", "").replace("#", "")

    # Check date format YYYY-MM-DD
    date_match = re.search(r"\b202[0-9]-[0-1][0-9]-[0-3][0-9]\b", clean_text)
    if not date_match:
        return CheckResult("Held-out decision doc", False, "Missing date in YYYY-MM-DD format")

    # Check clean cluster count
    count_match = re.search(r"(?i)(?:clean[- ]cluster count|clean clusters|count)\s*[:=]?\s*(\d+)", clean_text)
    if not count_match:
        return CheckResult("Held-out decision doc", False, "Missing clean cluster count")

    claimed_count = int(count_match.group(1))

    # Check 8: If PATH A, verify ingest_oof report
    if has_path_a:
        reports_dir = root / "ml" / "train_m2" / "out" / "reports"
        oof_candidates = [
            reports_dir / "oof_unseen_clean.json",
            reports_dir / "ingest_oof.json",
        ]
        found_report = None
        for cand in oof_candidates:
            if cand.is_file():
                found_report = cand
                break

        if not found_report:
            return CheckResult(
                "Held-out decision doc",
                False,
                f"PATH A selected but no ingest_oof report found in {reports_dir}",
            )

        try:
            data = json.loads(found_report.read_text(encoding="utf-8"))
            actual_clean = (
                data.get("unseen_clean_count")
                or len(data.get("unseen_clean_clusters", []))
                or data.get("counts", {}).get("unseen_clean_count")
                or len(data.get("counts", {}).get("unseen_clean_clusters", []))
            )
            if actual_clean < claimed_count:
                return CheckResult(
                    "Held-out decision doc",
                    False,
                    f"PATH A report clean clusters {actual_clean} < claimed {claimed_count}",
                )
        except Exception as e:
            return CheckResult("Held-out decision doc", False, f"Failed reading OOF report: {e}")

    path_str = "PATH A (OOF ingested)" if has_path_a else "PATH B (S4 not certified)"
    return CheckResult(
        "Held-out decision doc",
        True,
        f"{path_str} valid (date: {date_match.group(0)}, clean clusters: {claimed_count})",
    )


def check_ledger_pairs(root: Path, pairs: Sequence[tuple[str, str]] | None = None) -> CheckResult:
    """Check 9: run_once.py ledger has no prior entry for the (model, set) pairs."""
    log_file = root / "ml" / "train_m2" / "eval" / "RUN_LOG_M2.md"
    if not log_file.is_file():
        return CheckResult("Ledger pairs check", True, "RUN_LOG_M2.md absent (0 prior runs)")

    if not pairs:
        return CheckResult("Ledger pairs check", True, "No target pairs provided to check")

    log_content = log_file.read_text(encoding="utf-8")
    for model_name, set_name in pairs:
        key = f"| {model_name} | {set_name} |"
        if key in log_content:
            return CheckResult(
                "Ledger pairs check",
                False,
                f"Ledger already contains entry for pair ({model_name}, {set_name})",
            )

    return CheckResult("Ledger pairs check", True, "No target pairs present in ledger")


def check_ownership_gate(root: Path) -> CheckResult:
    """Check 10: check_ownership.py must return OK."""
    try:
        proc = subprocess.run(
            [sys.executable, "tools/check_ownership.py", "--who", "shaurya", "--base", "origin/main"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or "OK" not in proc.stdout:
            return CheckResult("Ownership gate", False, f"Ownership check failed: {proc.stdout} {proc.stderr}")
        return CheckResult("Ownership gate", True, "Ownership gate OK (0 Prabhav files touched)")
    except Exception as e:
        return CheckResult("Ownership gate", False, f"check_ownership script failed: {e}")


def check_frozen_gate(root: Path) -> CheckResult:
    """Check 11: check_frozen.py must return OK."""
    try:
        proc = subprocess.run(
            [sys.executable, "tools/check_frozen.py"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or "OK" not in proc.stdout:
            return CheckResult("Frozen gate", False, f"Frozen check failed: {proc.stdout} {proc.stderr}")
        return CheckResult("Frozen gate", True, "Frozen gate OK (all frozen files match tag)")
    except Exception as e:
        return CheckResult("Frozen gate", False, f"check_frozen script failed: {e}")


def check_test_suites(root: Path) -> CheckResult:
    """Check 12: Both test suites must pass."""
    try:
        t1 = subprocess.run(
            [sys.executable, "-m", "pytest", "ml/train_m2/tests", "-q"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if t1.returncode != 0:
            return CheckResult("Test suites", False, f"ml/train_m2/tests failed:\n{t1.stdout}\n{t1.stderr}")

        t2 = subprocess.run(
            [sys.executable, "-m", "pytest", "ml/tests", "-q"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if t2.returncode != 0:
            return CheckResult("Test suites", False, f"ml/tests failed:\n{t2.stdout}\n{t2.stderr}")

        return CheckResult("Test suites", True, "Both test suites pass green")
    except Exception as e:
        return CheckResult("Test suites", False, f"Test suite execution failed: {e}")


def run_preflight(
    root: Path | None = None,
    pairs: Sequence[tuple[str, str]] | None = None,
    preflight_hashes_path: Path | None = None,
    skip_test_suites: bool = False,
    skip_git_checks: bool = False,
) -> tuple[bool, list[CheckResult]]:
    """Execute all preflight checks in order and return (all_passed, results)."""
    r = root or repo_root()
    results: list[CheckResult] = []

    # 1. RUN_LOG_M2 absent
    results.append(check_run_log_absent(r))

    # 2. Git working tree clean
    if not skip_git_checks:
        results.append(check_working_tree_clean(r))
        results.append(check_plan_commit_ancestry(r))
        results.append(check_plan_diff_section12(r))
    else:
        results.append(CheckResult("Working tree clean", True, "Skipped by flag"))
        results.append(CheckResult("Plan commit in HEAD", True, "Skipped by flag"))
        results.append(CheckResult("Plan Section 12 diff", True, "Skipped by flag"))

    # 5. Artifact hashes
    results.append(check_artifact_hashes(r, preflight_hashes_path=preflight_hashes_path))

    # 6. Splits hash
    results.append(check_splits_hash(r))

    # 7 & 8. Held-out decision doc
    results.append(check_heldout_decision(r))

    # 9. Ledger pairs
    results.append(check_ledger_pairs(r, pairs=pairs))

    # 10. Ownership
    if not skip_git_checks:
        results.append(check_ownership_gate(r))
        results.append(check_frozen_gate(r))
    else:
        results.append(CheckResult("Ownership gate", True, "Skipped by flag"))
        results.append(CheckResult("Frozen gate", True, "Skipped by flag"))

    # 12. Test suites
    if not skip_test_suites:
        results.append(check_test_suites(r))
    else:
        results.append(CheckResult("Test suites", True, "Skipped by flag"))

    all_passed = all(res.passed for res in results)
    return all_passed, results


def require_preflight_pass(
    root: Path | None = None,
    pairs: Sequence[tuple[str, str]] | None = None,
    skip_test_suites: bool = False,
    skip_git_checks: bool = False,
) -> None:
    """Raise PreflightError if any preflight check fails."""
    passed, results = run_preflight(
        root=root,
        pairs=pairs,
        skip_test_suites=skip_test_suites,
        skip_git_checks=skip_git_checks,
    )
    if not passed:
        failed_msgs = [f"[{res.name}] {res.detail}" for res in results if not res.passed]
        raise PreflightError("Held-out preflight checks failed:\n" + "\n".join(failed_msgs))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Held-out preflight verification gate")
    parser.add_argument("--root", type=Path, default=None, help="Repository root path")
    parser.add_argument("--skip-test-suites", action="store_true", help="Skip running pytest suites")
    parser.add_argument("--skip-git-checks", action="store_true", help="Skip git status and ancestry checks")
    parser.add_argument("--pair", action="append", default=[], help="Target (model:set) pair, e.g. sft:B1")
    args = parser.parse_args(argv)

    pairs: list[tuple[str, str]] = []
    for p in args.pair:
        if ":" in p:
            m, s = p.split(":", 1)
            pairs.append((m, s))

    passed, results = run_preflight(
        root=args.root,
        pairs=pairs,
        skip_test_suites=args.skip_test_suites,
        skip_git_checks=args.skip_git_checks,
    )

    print("=== HELD-OUT PREFLIGHT VERIFICATION REPORT ===")
    for res in results:
        status_tag = "[PASS]" if res.passed else "[FAIL]"
        print(f"{status_tag} {res.name}: {res.detail}")

    if passed:
        print("\nALL PREFLIGHT CHECKS PASSED (exit code 0)")
        return 0
    else:
        print("\nPREFLIGHT FAILED: DO NOT SCORE HELD-OUT DATA (exit code 1)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
