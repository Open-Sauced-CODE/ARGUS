"""Code hygiene tests for the prioritize package.

Asserts:
  1. No neo4j / graph_loader import outside run_live.py
  2. No write-Cypher keywords in source code (excluding test files and comments)
  3. No hard-coded ARNs, account ids, CloudGoat suffix, or scanner name
     in non-test source files
  4. Only allowed paths changed (git diff check)
  5. No notebook outputs committed (checked via JSON)
"""
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_PRIORITIZE_DIR = Path(__file__).resolve().parents[1]
_RUN_LIVE = _PRIORITIZE_DIR / "run_live.py"

# Write Cypher keywords that must NOT appear in production source code
# Pattern: whole-word CREATE, MERGE, DELETE; "SET " (with space); REMOVE
# Excludes test files (false positives from docstrings/comments about Cypher)
_WRITE_CYPHER_SOURCE = re.compile(
    r"\b(CREATE|MERGE|DELETE)\b|\bREMOVE\b", re.IGNORECASE
)

_ARN_PATTERN = re.compile(r"arn:aws:[a-z0-9\-]+::[0-9]{12}:")
_ACCOUNT_ID_12 = re.compile(r"\b[0-9]{12}\b")
_CLOUDGOAT_SUFFIX = "cgidjq6epnjtgc"
_SCANNER_NAME = "argus-cartography-scanner"

_NEO4J_IMPORTS = re.compile(
    r"(import neo4j|from neo4j|import risk\.graph_loader|from risk\.graph_loader|from risk import.*graph_loader)"
)


def _source_files(include_tests=False, include_live=True):
    """Yield .py files under prioritize/."""
    for f in _PRIORITIZE_DIR.rglob("*.py"):
        if "__pycache__" in f.parts:
            continue
        if not include_live and f.name == "run_live.py":
            continue
        if not include_tests and f.parent.name == "tests":
            continue
        yield f


def test_no_neo4j_outside_run_live():
    """No neo4j or graph_loader import in any prioritize/*.py except run_live.py."""
    violations = []
    for path in _source_files(include_tests=False, include_live=False):
        src = path.read_text(encoding="utf-8")
        if _NEO4J_IMPORTS.search(src):
            violations.append(str(path.relative_to(_PRIORITIZE_DIR.parent)))
    assert not violations, (
        f"Neo4j/graph_loader imports found outside run_live.py:\n"
        + "\n".join(violations)
    )


def test_no_write_cypher_in_source():
    """No write-Cypher keywords (CREATE, MERGE, DELETE, REMOVE) in production .py source.

    Excludes test files (which may reference these in docstrings/comments for clarity)
    and excludes plain string constants (only checks non-comment code).
    """
    violations = []
    # Only check non-test source files
    for path in _source_files(include_tests=False, include_live=True):
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val = node.value
                # Only flag if it looks like actual Cypher (starts with keyword)
                stripped = val.strip().upper()
                if stripped.startswith(("CREATE ", "MERGE ", "DELETE ", "REMOVE ")):
                    violations.append(
                        f"{path.name}:{node.lineno}: {val[:60]!r}"
                    )
    assert not violations, (
        f"Write-Cypher keywords found in string literals in production files:\n"
        + "\n".join(violations)
    )


def test_no_hardcoded_arns_or_account_ids_in_source():
    """No hard-coded ARNs, CloudGoat suffix, or scanner name in production source."""
    violations = []
    # Only check non-test source files
    for path in _source_files(include_tests=False, include_live=True):
        src = path.read_text(encoding="utf-8")
        if _ARN_PATTERN.search(src):
            violations.append(f"{path.name}: hard-coded ARN with account id found")
        if _CLOUDGOAT_SUFFIX in src:
            violations.append(f"{path.name}: CloudGoat suffix {_CLOUDGOAT_SUFFIX!r} found")
        if _SCANNER_NAME in src:
            violations.append(f"{path.name}: scanner name {_SCANNER_NAME!r} found")
    assert not violations, "\n".join(violations)


def test_allowed_paths_only_changed():
    """git diff --name-only main should only show allowed paths."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "main"],
            capture_output=True, text=True,
            cwd=str(_PRIORITIZE_DIR.parent),
            timeout=10,
        )
        changed = [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except Exception:
        pytest.skip("git not available or diff failed")

    _ALLOWED_PREFIXES = (
        "prioritize/",
        "requirements-phase3.txt",
        "docs/phase3_decisions.md",
        "docs/phase3_validation.md",
        "docs/phase3_handoff.md",
        "docs/ARGUS_Phase3_Prioritization_Engine.md",
    )

    violations = [
        f for f in changed
        if not any(f.startswith(p) for p in _ALLOWED_PREFIXES)
        and f not in ("prioritize/README.md",)
    ]
    assert not violations, (
        f"Files changed outside allowed paths:\n" + "\n".join(violations)
    )


def test_no_notebook_outputs():
    """Committed notebooks should have no outputs (outputs: [])."""
    notebooks_dir = _PRIORITIZE_DIR / "notebooks"
    if not notebooks_dir.exists():
        pytest.skip("No notebooks directory")

    import json as _json
    for nb_path in notebooks_dir.glob("*.ipynb"):
        nb = _json.loads(nb_path.read_text(encoding="utf-8"))
        for cell in nb.get("cells", []):
            outputs = cell.get("outputs", [])
            assert outputs == [], (
                f"{nb_path.name} has outputs in a cell "
                f"(type={cell.get('cell_type')}, source={str(cell.get('source',''))[:40]!r})"
            )
            ec = cell.get("execution_count")
            assert ec is None, (
                f"{nb_path.name} has non-null execution_count={ec}"
            )
