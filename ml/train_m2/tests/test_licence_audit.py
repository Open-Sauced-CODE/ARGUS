"""Unit tests for ml/train_m2/licence_audit.py (P6f Stage 2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.train_m2.common import repo_root
from ml.train_m2.licence_audit import (
    audit_base_model,
    audit_dataset_licenses,
    audit_packages,
    categorize_license,
    get_package_license,
    parse_requirements,
    render_markdown,
    run_licence_audit,
)


def test_parse_requirements_synthetic(tmp_path: Path):
    req_file = tmp_path / "requirements-test.txt"
    req_file.write_text(
        "# Comment line\n"
        "\n"
        "pytest>=8.0.0\n"
        "scikit-learn==1.5.0; python_version >= '3.10'\n"
        "requests\n"
        "--extra-index-url https://example.com\n"
        "-r other-reqs.txt\n"
        "package_with.dots-and_dashes>=1.0\n",
        encoding="utf-8",
    )
    pkgs = parse_requirements(req_file)
    assert pkgs == ["pytest", "scikit-learn", "requests", "package_with.dots-and_dashes"]


def test_categorize_license():
    assert categorize_license("MIT") == "permissive"
    assert categorize_license("Apache-2.0") == "permissive"
    assert categorize_license("BSD-3-Clause") == "permissive"
    assert categorize_license("Python Software Foundation License") == "permissive"
    assert categorize_license("LGPL-2.1-or-later") == "copyleft"
    assert categorize_license("MPL-2.0") == "copyleft"
    assert categorize_license("GPL-3.0") == "copyleft"
    assert categorize_license("UNKNOWN") == "unverified"
    assert categorize_license("NOT INSTALLED") == "unverified"
    assert categorize_license("") == "unverified"


def test_get_package_license_installed():
    version, lic, cat = get_package_license("pytest")
    assert version is not None
    assert "MIT" in lic.upper()
    assert cat == "permissive"

    v_none, lic_none, cat_none = get_package_license("nonexistent_package_xyz_123")
    assert v_none is None
    assert lic_none == "NOT INSTALLED"
    assert cat_none == "unverified"


def test_audit_base_model():
    bm = audit_base_model()
    assert bm["license"] == "Apache-2.0"
    assert bm["commercial_use_allowed"] is True
    assert bm["status"] == "APPROVED"


def test_audit_dataset_licenses():
    root = repo_root()
    ds = audit_dataset_licenses(root)
    assert ds["present"] is True
    assert ds["total_rows"] > 0
    assert "MIT" in ds["licenses"]
    assert "Apache-2.0" in ds["licenses"]
    # Check that MPL-2.0 copyleft row is flagged
    assert ds["copyleft_count"] >= 1
    assert any(r["license"] == "MPL-2.0" for r in ds["copyleft_rows"])


def test_audit_packages_and_render_markdown():
    root = repo_root()
    audit = run_licence_audit(root)
    assert "dependencies" in audit
    assert "c_mined_dataset" in audit
    assert "base_model" in audit

    deps = audit["dependencies"]
    assert deps["total_declared_packages"] >= 200
    assert deps["category_counts"]["permissive"] > 200

    md = render_markdown(audit)
    assert "# ARGUS Licence Audit Report" in md
    assert "Qwen3.5" in md
    assert "C-mined" in md
    # ASCII only assertion
    assert md.isascii()
