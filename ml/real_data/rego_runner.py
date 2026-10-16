"""
ARGUS Phase 5 - run the Phase 4 Rego rules over many resources with ONE call to OPA.

    evaluate(resources) -> list of RuleResult(deny=frozenset(rule ids), warn=frozenset(rule ids))

`resources` are dictionaries shaped like the Rego input.resource (they include "resource_type").
The Rego files under policy/ are the only source of truth: nothing is reimplemented in Python.
Every rule package found under policy/ is evaluated (both `deny` and `warn` sets) with
`with input as {"resource": r}`, so rules added later are picked up automatically.

Finding the OPA program: the opa= argument, else the OPA_BIN environment variable, else `opa` on PATH.
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_DIR = REPO_ROOT / "policy"

_RULE_ID_RE = re.compile(r"^\s*#\s*rule_id:\s*(\S+)\s*$", re.MULTILINE)
_PACKAGE_RE = re.compile(r"^package\s+([A-Za-z0-9_.]+)\s*$", re.MULTILINE)
_KIND_RE = re.compile(r"^(deny|warn)\s+contains\b", re.MULTILINE)


class OpaNotFound(RuntimeError):
    pass


class OpaError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuleResult:
    deny: frozenset
    warn: frozenset

    @property
    def clean(self):
        return not self.deny and not self.warn


def find_opa(opa=None):
    candidate = opa or os.environ.get("OPA_BIN") or shutil.which("opa")
    if not candidate or not Path(candidate).exists() and not shutil.which(candidate):
        raise OpaNotFound(
            "OPA was not found. Put opa.exe on PATH, or set the OPA_BIN environment variable to its full path "
            "(PowerShell:  $env:OPA_BIN = 'C:\\path\\to\\opa.exe')."
        )
    return candidate


def discover_rules(policy_dir=None):
    """[(rule_id, package, kinds)] for every rule file under policy/ (test files excluded)."""
    root = Path(policy_dir or DEFAULT_POLICY_DIR)
    rules = []
    for path in sorted(root.rglob("*.rego")):
        if path.name.endswith("_test.rego"):
            continue
        text = path.read_text(encoding="utf-8-sig")
        ids = _RULE_ID_RE.findall(text)
        packages = _PACKAGE_RE.findall(text)
        kinds = sorted(set(_KIND_RE.findall(text)))
        if len(ids) == 1 and len(packages) == 1 and kinds:
            rules.append((ids[0], packages[0], kinds))
    return rules


def build_query(rules):
    """One Rego comprehension: for every input resource, the rule ids that fired in each deny / warn set."""
    def union_of(kind):
        parts = []
        for rule_id, package, kinds in rules:
            if kind in kinds:
                parts.append(
                    '{{object.get(m, "rule_id", "{rid}") | some m in data.{pkg}.{kind} '
                    'with input as {{"resource": r}}}}'.format(rid=rule_id, pkg=package, kind=kind)
                )
        return "union({" + ", ".join(parts) + "})" if parts else "set()"

    return ('[{"i": i, "deny": d, "warn": w} | r := input.resources[i]; '
            "d := " + union_of("deny") + "; w := " + union_of("warn") + "]")


def evaluate(resources, policy_dir=None, opa=None, chunk=1500):
    """Evaluate every rule on every resource. Returns a list of RuleResult aligned with `resources`."""
    resources = list(resources)
    policy_dir = Path(policy_dir or DEFAULT_POLICY_DIR)
    rules = discover_rules(policy_dir)
    if not rules:
        raise OpaError("no rule files found under {}".format(policy_dir))
    query = build_query(rules)
    binary = find_opa(opa)
    results = []
    for start in range(0, len(resources), chunk):
        batch = resources[start:start + chunk]
        proc = subprocess.run(
            [binary, "eval", "--format", "json", "--data", str(policy_dir), "--stdin-input", query],
            input=json.dumps({"resources": batch}), capture_output=True, text=True, encoding="utf-8",
        )
        if proc.returncode != 0:
            raise OpaError("opa eval failed (exit {}): {}".format(proc.returncode, (proc.stderr or proc.stdout)[:600]))
        rows = json.loads(proc.stdout)["result"][0]["expressions"][0]["value"]
        by_index = {row["i"]: row for row in rows}
        for i in range(len(batch)):
            row = by_index[i]
            results.append(RuleResult(frozenset(row["deny"]), frozenset(row["warn"])))
    return results


def resource_for_rules(record):
    """The dictionary the rules read: the record's attrs plus its resource_type."""
    return dict(record["attrs"], resource_type=record["resource_type"])
