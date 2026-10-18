"""
ARGUS Phase 5, Step 3 - HCL parser smoke test.

Parses Terraform files with python-hcl2 and reports what the parser can and cannot give us:
resource blocks, how many attribute values are literals versus unresolved references
(variables, locals, other resources, expressions), and which Terraform features that make a
resource hard to use as a base config (count, for_each, dynamic blocks).

Run from the repo root (PowerShell):
    python -m ml.real_data.hcl_smoke_test
    python -m ml.real_data.hcl_smoke_test path\\to\\a.tf path\\to\\b.tf

With no arguments it parses the Phase 1 fixtures plus every .tf file in ml/real_data/samples/.
Exit code: 0 = every file parsed, 1 = at least one file failed to parse, 2 = no files found or
python-hcl2 is not installed.
"""

import argparse
import sys
from collections import Counter
from importlib import metadata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# The Phase 1 fixtures moved to phase1_skeleton/ in Phase 5 Section 2B; both places are checked.
FIXTURES_DIRS = (
    REPO_ROOT / "ml" / "mutation_engine" / "phase1_skeleton" / "fixtures",
    REPO_ROOT / "ml" / "mutation_engine" / "fixtures",
)
FIXTURES_DIR = FIXTURES_DIRS[0]
SAMPLES_DIR = REPO_ROOT / "ml" / "real_data" / "samples"

META_ARGUMENTS = ("count", "for_each", "dynamic", "provider", "depends_on", "lifecycle")


def _hcl2():
    try:
        import hcl2
    except ImportError:
        print("python-hcl2 is not installed. Run:  pip install -r requirements-phase5.txt")
        raise SystemExit(2)
    if not hasattr(hcl2, "SerializationOptions"):
        print("This script needs python-hcl2 8.x. Run:  pip install -r requirements-phase5.txt")
        raise SystemExit(2)
    return hcl2


def parser_version():
    try:
        return metadata.version("python-hcl2")
    except metadata.PackageNotFoundError:
        return "unknown"


def parse_file(path):
    """Parse one .tf file into a plain dictionary.

    Options used: no comments, plain nested blocks, and string quotes stripped, so a literal
    "aws:kms" comes back as aws:kms and a reference such as aws_s3_bucket.data.id comes back
    as the text ${aws_s3_bucket.data.id}."""
    hcl2 = _hcl2()
    options = hcl2.SerializationOptions(
        with_comments=False, explicit_blocks=False, strip_string_quotes=True
    )
    with open(path, "r", encoding="utf-8-sig") as handle:
        return hcl2.load(handle, serialization_options=options)


def iter_resources(parsed):
    """Yield (resource_type, resource_name, body_dict) for every resource block."""
    for block in parsed.get("resource", []) or []:
        for rtype, instances in block.items():
            for name, body in instances.items():
                yield rtype, name, body


def _walk_values(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk_values(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _walk_values(value)
    else:
        yield node


def is_unresolved(value):
    """True when a parsed value still depends on something we cannot see (variable, local,
    another resource, function call, template). Literals (true, 443, "aws:kms") are resolved."""
    return isinstance(value, str) and "${" in value


def analyse_file(path):
    """Return a report dictionary for one file (never raises for a parse error)."""
    report = {
        "path": str(path),
        "ok": False,
        "error": None,
        "resources": 0,
        "resource_types": Counter(),
        "values_total": 0,
        "values_unresolved": 0,
        "resources_with": Counter(),
        "top_level": [],
    }
    try:
        parsed = parse_file(path)
    except Exception as exc:  # parse errors come in several exception types
        report["error"] = "{}: {}".format(type(exc).__name__, str(exc).splitlines()[0][:200] if str(exc) else "")
        return report

    report["ok"] = True
    report["top_level"] = sorted(parsed.keys())
    for rtype, _name, body in iter_resources(parsed):
        report["resources"] += 1
        report["resource_types"][rtype] += 1
        for key in META_ARGUMENTS:
            if key in body:
                report["resources_with"][key] += 1
        for value in _walk_values(body):
            report["values_total"] += 1
            if is_unresolved(value):
                report["values_unresolved"] += 1
    return report


def default_files():
    files = []
    for folder in FIXTURES_DIRS:
        files += sorted(folder.glob("*.tf"))
    files += sorted(SAMPLES_DIR.glob("*.tf"))
    return [p for p in files if p.is_file()]


def _pct(part, whole):
    return "n/a" if not whole else "{:.0f}%".format(100.0 * part / whole)


def print_report(report):
    print("-" * 78)
    print("File     : {}".format(report["path"]))
    if not report["ok"]:
        print("Result   : PARSE FAILED  ({})".format(report["error"]))
        return
    print("Result   : parsed OK   top-level blocks: {}".format(", ".join(report["top_level"]) or "none"))
    print("Resources: {}   distinct types: {}".format(report["resources"], len(report["resource_types"])))
    for rtype, count in report["resource_types"].most_common(5):
        print("           {:<55} x{}".format(rtype, count))
    print("Values   : {} attribute values, {} unresolved references ({})".format(
        report["values_total"], report["values_unresolved"],
        _pct(report["values_unresolved"], report["values_total"])))
    if report["resources_with"]:
        print("Features : " + ", ".join(
            "{} in {} resource(s)".format(k, v) for k, v in sorted(report["resources_with"].items())))


def main(argv=None):
    args = argparse.ArgumentParser(description="python-hcl2 smoke test for ARGUS Phase 5, Step 3")
    args.add_argument("files", nargs="*", help="Terraform files to parse (default: fixtures + samples)")
    options = args.parse_args(argv)

    _hcl2()
    paths = [Path(p) for p in options.files] if options.files else default_files()
    paths = [p for p in paths if p.is_file()]
    if not paths:
        print("No .tf files found. Put at least one file in ml/real_data/samples/ or pass paths.")
        return 2

    reports = [analyse_file(p) for p in paths]
    for report in reports:
        print_report(report)

    ok = [r for r in reports if r["ok"]]
    total_resources = sum(r["resources"] for r in ok)
    total_values = sum(r["values_total"] for r in ok)
    total_unresolved = sum(r["values_unresolved"] for r in ok)
    print("=" * 78)
    print("python-hcl2 version : {}".format(parser_version()))
    print("Files parsed        : {} of {}".format(len(ok), len(reports)))
    print("Resources found     : {}".format(total_resources))
    print("Unresolved values   : {} of {} ({})".format(total_unresolved, total_values, _pct(total_unresolved, total_values)))
    print("Paste these lines into ml/real_data/SETUP_NOTES.md (HCL parser section).")
    return 0 if len(ok) == len(reports) else 1


if __name__ == "__main__":
    sys.exit(main())
