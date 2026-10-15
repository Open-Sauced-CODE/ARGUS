"""
Guards ml/README_contracts.md (Phase 5, Step 1).

The contracts file is only useful if it stays true. These tests fail if:
  * a Rego rule exists that the contracts table does not list (or the reverse),
  * a rule row has no valid family, route or mutator ID,
  * the held-out family is missing or is not one of the families in the table,
  * the Patch-IR schema file changed without the fingerprint being updated,
  * a Phase 4 function signature changed without the contracts file being updated,
  * the Phase 4 commit hash was never filled in.

Run from the repo root (PowerShell):
    python -m pytest ml/tests/test_contracts_doc.py -v
"""

import ast
import json
import re
from pathlib import Path

import pytest

from ml.tools.list_rules import SCHEMA_PATH, schema_fingerprint
from privacy.airlock.projection import REPO_ROOT, load_declarations

CONTRACTS = REPO_ROOT / "ml" / "README_contracts.md"

FAMILIES = {
    "encryption-at-rest",
    "versioning-and-retention",
    "public-exposure",
    "network-exposure",
    "iam-and-access",
    "logging-and-detection",
    "data-residency",
}
ROUTES = {"T0", "M1", "ESC"}
MUTATOR_ID_RE = re.compile(r"`(m_[a-z0-9_]+)`")

EXPECTED_SIGNATURES = [
    ("privacy/airlock/projection.py", "project", "raw_finding, rule_id, policy_dir=None"),
    ("privacy/airlock/airlock.py", "run_airlock", "raw_finding, rule_id, *, vault=None, policy_dir=None"),
    ("privacy/airlock/leakcheck.py", "leak_check", "payload, vault_values=()"),
    ("privacy/scrubbers/scrubbers.py", "scrub", "record, engine='auto'"),
    ("privacy/vault/tokenizer.py", "tokenize", "record, vault=None"),
    ("privacy/vault/tokenizer.py", "rehydrate", "obj, vault_refs, vault=None"),
]


@pytest.fixture(scope="module")
def text():
    assert CONTRACTS.exists(), "ml/README_contracts.md is missing"
    return CONTRACTS.read_text(encoding="utf-8-sig")


def _rule_rows(doc):
    """Parse the rule table (the table whose header starts with '| Rule ID |') into a list of dicts."""
    lines = doc.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("| Rule ID |")), None)
    assert start is not None, "rule table (header '| Rule ID |') not found in ml/README_contracts.md"
    header = [c.strip() for c in lines[start].strip().strip("|").split("|")]
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        assert len(cells) == len(header), "table row has the wrong number of columns: {}".format(line[:80])
        rows.append(dict(zip(header, cells)))
    return rows


def test_every_rego_rule_is_in_the_table_and_nothing_else(text):
    in_table = [r["Rule ID"].strip("`") for r in _rule_rows(text)]
    assert len(in_table) == len(set(in_table)), "a rule appears twice in the contracts table"
    in_rego = set(load_declarations())
    missing = sorted(in_rego - set(in_table))
    extra = sorted(set(in_table) - in_rego)
    assert not missing, "Rego rules missing from ml/README_contracts.md: {}".format(missing)
    assert not extra, "rules in ml/README_contracts.md with no .rego file: {}".format(extra)


def test_every_row_has_valid_family_route_and_mutator(text):
    for row in _rule_rows(text):
        rule = row["Rule ID"]
        assert row["Family"] in FAMILIES, "{}: unknown family {!r}".format(rule, row["Family"])
        assert row["Route"] in ROUTES, "{}: route must be one of {}".format(rule, sorted(ROUTES))
        assert MUTATOR_ID_RE.findall(row["Mutator ID(s)"]), "{}: no mutator ID like `m_something`".format(rule)


def test_escalate_rules_are_marked_and_totals_match(text):
    rows = _rule_rows(text)
    routes = [r["Route"] for r in rows]
    assert routes.count("T0") + routes.count("M1") + routes.count("ESC") == len(rows)
    claimed = re.search(r"Totals: (\d+) rules, (\d+) families, (\d+) mutators\. T0 covers (\d+) rules, "
                        r"M1 drafts (\d+), (\d+) are escalate cases", text)
    assert claimed, "the 'Totals:' sentence under the rule table is missing or was reworded"
    n_rules, n_fam, n_mut, n_t0, n_m1, n_esc = (int(x) for x in claimed.groups())
    mutators = {m for r in rows for m in MUTATOR_ID_RE.findall(r["Mutator ID(s)"])}
    assert (n_rules, n_fam, n_mut) == (len(rows), len({r["Family"] for r in rows}), len(mutators))
    assert (n_t0, n_m1, n_esc) == (routes.count("T0"), routes.count("M1"), routes.count("ESC"))


def test_one_held_out_family_is_declared_and_exists(text):
    found = re.findall(r"^Held-out family \(Tier B2\): \*\*([a-z\-]+)\*\*\s*$", text, re.MULTILINE)
    assert len(found) == 1, "exactly one line 'Held-out family (Tier B2): **<family>**' is required"
    assert found[0] in {r["Family"] for r in _rule_rows(text)}


def test_patch_ir_schema_fingerprint_matches(text):
    recorded = re.search(r"Patch-IR schema fingerprint \(canonical SHA-256\): `([0-9a-f]{64})`", text)
    assert recorded, "fingerprint line missing from ml/README_contracts.md"
    assert recorded.group(1) == schema_fingerprint(), (
        "remediate/patch_ir/schema.json changed. If that was intended, tell the team, update the "
        "fingerprint and add a row to the change log. Run: python -m ml.tools.list_rules"
    )


def test_every_patch_ir_operation_is_listed(text):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8-sig"))
    ops = schema["properties"]["ops"]["items"]["properties"]["op"]["enum"]
    for op in ops:
        assert op in text, "operation {} from the schema is not listed in the contracts file".format(op)
    assert "(closed vocabulary, {})".format(len(ops)) in text


def _source_signature(relative_path, function_name):
    tree = ast.parse((REPO_ROOT / relative_path).read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return ast.unparse(node.args)
    return None


@pytest.mark.parametrize("path,name,expected", EXPECTED_SIGNATURES, ids=[e[1] for e in EXPECTED_SIGNATURES])
def test_phase4_signatures_unchanged_and_documented(text, path, name, expected):
    actual = _source_signature(path, name)
    assert actual is not None, "{} not found in {}".format(name, path)
    assert actual == expected, "{}() in {} changed to ({}). Phase 4 owns it: tell the team.".format(name, path, actual)
    assert "`{}({})`".format(name, expected) in text, "{} is not documented in ml/README_contracts.md".format(name)


def test_phase4_commit_hash_is_filled_in(text):
    match = re.search(r"^Phase 4 commit: `([^`]+)`", text, re.MULTILINE)
    assert match, "line 'Phase 4 commit: `<hash>`' missing"
    assert re.fullmatch(r"[0-9a-f]{7,40}", match.group(1)), (
        "ml/README_contracts.md still has the placeholder. Put the output of "
        "'git rev-parse --short HEAD' between the backticks (guide, Step 1)."
    )
