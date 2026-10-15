"""
ARGUS Phase 5 - print the facts that ml/README_contracts.md must agree with.

It reads the real Rego files (the single source of truth) and prints, for every rule:
rule id, kind (deny or warn), the .rego file, and the input.resource fields the rule reads.
It also prints the Patch-IR schema fingerprint recorded in the contracts file.

Run from the repo root (PowerShell):
    python -m ml.tools.list_rules
"""

import hashlib
import json
import re
from pathlib import Path

from privacy.airlock.projection import DEFAULT_POLICY_DIR, REPO_ROOT, load_declarations

SCHEMA_PATH = REPO_ROOT / "remediate" / "patch_ir" / "schema.json"

_RULE_ID_RE = re.compile(r"^\s*#\s*rule_id:\s*(\S+)\s*$", re.MULTILINE)
_KIND_RE = re.compile(r"^(deny|warn)\s+contains\b", re.MULTILINE)


def schema_fingerprint(path=SCHEMA_PATH):
    """SHA-256 of the schema as canonical JSON (sorted keys, no whitespace), so Windows/Linux
    line endings and indentation can never change the value."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def rule_files(policy_dir=None):
    """{rule_id: (relative file path, 'deny' or 'warn' or 'deny+warn')}"""
    root = Path(policy_dir or DEFAULT_POLICY_DIR)
    out = {}
    for path in sorted(root.rglob("*.rego")):
        if path.name.endswith("_test.rego"):
            continue
        text = path.read_text(encoding="utf-8")
        ids = _RULE_ID_RE.findall(text)
        if len(ids) != 1:
            continue
        kinds = sorted(set(_KIND_RE.findall(text)))
        out[ids[0]] = (path.relative_to(root.parent).as_posix(), "+".join(kinds) or "none")
    return out


def main():
    declarations = load_declarations()
    files = rule_files()
    width = max(len(r) for r in declarations)
    print("Rules found in policy/: {}".format(len(declarations)))
    print()
    for rule_id in sorted(declarations):
        path, kind = files.get(rule_id, ("?", "?"))
        print("{:<{w}}  {:<5}  {}".format(rule_id, kind, path, w=width))
        print("{:<{w}}         reads: {}".format("", ", ".join(sorted(declarations[rule_id])), w=width))
    print()
    print("Patch-IR schema file       : {}".format(SCHEMA_PATH.relative_to(REPO_ROOT).as_posix()))
    print("Schema fingerprint (SHA256): {}".format(schema_fingerprint()))


if __name__ == "__main__":
    main()
