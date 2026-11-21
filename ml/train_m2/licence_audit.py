"""Licence audit scanner for dependencies, datasets, and base models (Shaurya-owned).

Scans:
  1. Python packages declared in requirements*.txt using importlib.metadata.
  2. Dataset licenses from C-mined manifest (ml/real_data/diagnostics/out/tierC_mined_v2.jsonl).
  3. Base model license (Qwen3.5 Apache-2.0).

Outputs:
  ml/train_m2/out/reports/licence_audit.md
  ml/train_m2/out/reports/licence_audit.json
  ml/train_m2/out/reports/licence_audit.json.provenance.json
"""
from __future__ import annotations

import importlib.metadata
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ml.train_m2.common import repo_root, write_provenance

LOG = logging.getLogger(__name__)

SEED = 1337

COPYLEFT_KEYWORDS = ("agpl", "gpl", "lgpl", "mpl", "epl", "eupl", "cc-by-sa", "cddl", "osl")
PERMISSIVE_KEYWORDS = (
    "mit", "apache", "bsd", "isc", "unlicense", "0bsd", "cc0", "wtfpl",
    "zlib", "psf", "python software foundation", "public domain",
)


@dataclass
class PackageLicenceInfo:
    name: str
    declared_in: list[str]
    installed_version: str | None
    license_text: str
    category: str  # permissive, copyleft, unverified


def parse_requirements(req_path: Path) -> list[str]:
    """Extract package names from a requirements.txt file."""
    if not req_path.is_file():
        return []
    pkgs: list[str] = []
    text = req_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("--") or line.startswith("-r"):
            continue
        # Extract base package name before version/environment specifiers
        m = re.match(r"^([a-zA-Z0-9_\-\.]+)", line)
        if m:
            pkgs.append(m.group(1))
    return pkgs


def categorize_license(license_str: str) -> str:
    """Categorize license string into permissive, copyleft, or unverified."""
    if not license_str or license_str.upper() in {"UNKNOWN", "UNVERIFIED", "NONE", "NOT INSTALLED"}:
        return "unverified"
    low = license_str.lower()
    for p in ("bsd", "mit", "apache", "isc", "unlicense", "0bsd", "cc0", "wtfpl", "zlib", "psf", "public domain"):
        if p in low and not any(c in low for c in ("gpl", "mpl", "cddl")):
            return "permissive"
    if any(k in low for k in COPYLEFT_KEYWORDS):
        return "copyleft"
    if any(k in low for k in PERMISSIVE_KEYWORDS):
        return "permissive"
    return "unverified"


def get_package_license(pkg_name: str) -> tuple[str | None, str, str]:
    """Inspect importlib.metadata for pkg_name.

    Returns (installed_version, license_text, category).
    """
    try:
        dist = importlib.metadata.distribution(pkg_name)
        version = dist.version
        meta = dist.metadata
    except (importlib.metadata.PackageNotFoundError, Exception):
        return None, "NOT INSTALLED", "unverified"

    lic = meta.get("License-Expression")
    if not lic:
        # Check classifiers next for standardized short license name
        classifiers = [
            c.split("::")[-1].strip()
            for c in (meta.get_all("Classifier") or [])
            if "License" in c and "OSI Approved" in c
        ]
        if classifiers:
            lic = classifiers[0]

    if not lic:
        raw_lic = meta.get("License")
        if raw_lic:
            lines = [l.strip() for l in raw_lic.splitlines() if l.strip()]
            lic = lines[0] if lines else "UNKNOWN"

    lic = lic or "UNKNOWN"
    lic = " ".join(lic.split())
    if len(lic) > 80:
        lic = lic[:77] + "..."

    category = categorize_license(lic)
    return version, lic, category


def audit_packages(root: Path) -> dict[str, Any]:
    """Scan all requirements*.txt in repo root and check package licenses."""
    req_files = sorted(root.glob("requirements*.txt"))
    pkg_to_files: dict[str, list[str]] = defaultdict(list)

    for rf in req_files:
        for pkg in parse_requirements(rf):
            pkg_to_files[pkg].append(rf.name)

    records: list[PackageLicenceInfo] = []
    category_counts: Counter[str] = Counter()

    for pkg in sorted(pkg_to_files.keys(), key=lambda s: s.lower()):
        version, lic_text, cat = get_package_license(pkg)
        records.append(
            PackageLicenceInfo(
                name=pkg,
                declared_in=pkg_to_files[pkg],
                installed_version=version,
                license_text=lic_text,
                category=cat,
            )
        )
        category_counts[cat] += 1

    return {
        "requirements_files_scanned": [rf.name for rf in req_files],
        "total_declared_packages": len(pkg_to_files),
        "category_counts": dict(category_counts),
        "unverified_packages": [
            asdict(r) for r in records if r.category == "unverified"
        ],
        "copyleft_packages": [
            asdict(r) for r in records if r.category == "copyleft"
        ],
        "all_packages": [asdict(r) for r in records],
    }


def audit_dataset_licenses(root: Path) -> dict[str, Any]:
    """Scan C-mined manifest for repository licenses."""
    cmined_path = root / "ml" / "real_data" / "diagnostics" / "out" / "tierC_mined_v2.jsonl"
    if not cmined_path.is_file():
        return {
            "present": False,
            "path": str(cmined_path.relative_to(root)),
            "reason": "File not found",
            "licenses": {},
            "copyleft_count": 0,
        }

    counts: Counter[str] = Counter()
    total_rows = 0
    copyleft_rows: list[dict[str, Any]] = []

    for line in cmined_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        total_rows += 1
        lic = str(row.get("meta", {}).get("license") or "unknown").strip()
        counts[lic] += 1
        cat = categorize_license(lic)
        if cat == "copyleft":
            copyleft_rows.append({
                "id": row.get("id"),
                "repo": row.get("meta", {}).get("repo"),
                "license": lic,
            })

    return {
        "present": True,
        "path": str(cmined_path.relative_to(root)).replace("\\", "/"),
        "total_rows": total_rows,
        "licenses": dict(counts),
        "copyleft_count": len(copyleft_rows),
        "copyleft_rows": copyleft_rows,
    }


def audit_base_model() -> dict[str, Any]:
    """Return base model licensing information."""
    return {
        "model_name": "Qwen3.5-4B / Qwen2.5",
        "license": "Apache-2.0",
        "commercial_use_allowed": True,
        "status": "APPROVED",
        "notes": "Permissive Apache-2.0 license compatible with commercial redistribution and research.",
    }


def run_licence_audit(root: Path | None = None) -> dict[str, Any]:
    """Run full license audit across dependencies, datasets, and base model."""
    root = root or repo_root()
    pkg_audit = audit_packages(root)
    dataset_audit = audit_dataset_licenses(root)
    base_model_audit = audit_base_model()

    return {
        "dependencies": pkg_audit,
        "c_mined_dataset": dataset_audit,
        "base_model": base_model_audit,
    }


def render_markdown(audit: dict[str, Any]) -> str:
    """Render markdown report for license audit."""
    deps = audit["dependencies"]
    ds = audit["c_mined_dataset"]
    bm = audit["base_model"]

    lines = [
        "# ARGUS Licence Audit Report",
        "",
        "## 1. Summary",
        "",
        f"- Scanned requirements files: {', '.join(deps['requirements_files_scanned'])}",
        f"- Total declared packages: {deps['total_declared_packages']}",
        f"  - Permissive: {deps['category_counts'].get('permissive', 0)}",
        f"  - Copyleft: {deps['category_counts'].get('copyleft', 0)}",
        f"  - Unverified / Not Installed: {deps['category_counts'].get('unverified', 0)}",
        f"- Base model ({bm['model_name']}): {bm['license']} ({bm['status']})",
        f"- C-mined dataset rows: {ds.get('total_rows', 0)} (Copyleft rows: {ds.get('copyleft_count', 0)})",
        "",
        "## 2. Base Model Licence",
        "",
        f"- **Model**: {bm['model_name']}",
        f"- **Licence**: {bm['license']}",
        f"- **Commercial Use**: {'Yes' if bm['commercial_use_allowed'] else 'No'}",
        f"- **Notes**: {bm['notes']}",
        "",
        "## 3. Dataset Licences (C-Mined Manifest)",
        "",
    ]

    if ds.get("present"):
        lines += [
            f"Manifest file: `{ds['path']}` (total rows: {ds['total_rows']})",
            "",
            "| Licence | Count | Category |",
            "|---|---|---|",
        ]
        for lic, count in sorted(ds["licenses"].items(), key=lambda kv: -kv[1]):
            cat = categorize_license(lic)
            lines.append(f"| {lic} | {count} | {cat} |")

        if ds.get("copyleft_rows"):
            lines += [
                "",
                "### Copyleft dataset rows (flagged for review)",
                "",
                "| ID | Repository | Licence |",
                "|---|---|---|",
            ]
            for r in ds["copyleft_rows"]:
                lines.append(f"| {r['id']} | {r['repo']} | {r['license']} |")
    else:
        lines.append("C-mined manifest not found on disk.")

    lines += [
        "",
        "## 4. Package Licences (Declared in requirements*.txt)",
        "",
        "### Copyleft Packages",
        "",
    ]
    if deps["copyleft_packages"]:
        lines += [
            "| Package | Version | Licence | Declared In |",
            "|---|---|---|---|",
        ]
        for p in deps["copyleft_packages"]:
            lines.append(
                f"| {p['name']} | {p['installed_version'] or 'N/A'} | "
                f"{p['license_text']} | {', '.join(p['declared_in'])} |"
            )
    else:
        lines.append("No copyleft packages identified.")

    lines += [
        "",
        "### Unverified / Not Installed Packages",
        "",
    ]
    if deps["unverified_packages"]:
        lines += [
            "| Package | Version | Licence / Reason | Declared In |",
            "|---|---|---|---|",
        ]
        for p in deps["unverified_packages"]:
            lines.append(
                f"| {p['name']} | {p['installed_version'] or 'N/A'} | "
                f"{p['license_text']} | {', '.join(p['declared_in'])} |"
            )
    else:
        lines.append("None. All packages verified.")

    return "\n".join(lines) + "\n"


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    root = repo_root()
    out_dir = root / "ml" / "train_m2" / "out" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = run_licence_audit(root)
    md = render_markdown(result)

    md_path = out_dir / "licence_audit.md"
    md_path.write_text(md, encoding="utf-8")
    write_provenance(md_path, seed=SEED)

    json_path = out_dir / "licence_audit.json"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    write_provenance(json_path, seed=SEED)

    LOG.info("Written: %s, %s", md_path, json_path)
    print(md)


if __name__ == "__main__":
    main()
