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
    assert bm["model_name"] == "unsloth/Qwen3.5-4B"
    assert bm["license"] == "UNVERIFIED"
    assert bm["commercial_use_allowed"] is False
    assert bm["status"] == "UNVERIFIED"
    # Ensure Qwen2.5 is not present anywhere in the base model audit
    assert "Qwen2.5" not in json.dumps(bm)


def test_audit_base_model_with_declared_manifest(tmp_path: Path):
    """When a harvest manifest explicitly declares a permissive license for the model, it is approved."""
    # Create fake notebook
    nb_dir = tmp_path / "ml" / "train_m1" / "notebooks"
    nb_dir.mkdir(parents=True)
    nb_path = nb_dir / "01_sft.ipynb"
    nb_content = {
        "cells": [
            {
                "cell_type": "code",
                "source": ['BASE_MODEL = "custom/test-model-4b"\n'],
            }
        ]
    }
    nb_path.write_text(json.dumps(nb_content), encoding="utf-8")

    # Before manifest: should be UNVERIFIED
    bm_unverified = audit_base_model(root=tmp_path)
    assert bm_unverified["model_name"] == "custom/test-model-4b"
    assert bm_unverified["license"] == "UNVERIFIED"
    assert bm_unverified["status"] == "UNVERIFIED"

    # Add manifest declaring Apache-2.0
    man_dir = tmp_path / "harvest_manifests"
    man_dir.mkdir(parents=True)
    man_path = man_dir / "test_manifest.json"
    man_path.write_text(
        json.dumps({"base_model": "custom/test-model-4b", "license": "Apache-2.0"}),
        encoding="utf-8",
    )

    bm_approved = audit_base_model(root=tmp_path)
    assert bm_approved["model_name"] == "custom/test-model-4b"
    assert bm_approved["license"] == "Apache-2.0"
    assert bm_approved["commercial_use_allowed"] is True
    assert bm_approved["status"] == "APPROVED"


def test_no_qwen25_in_licence_audit():
    """Ensure Qwen2.5 text is completely removed from licence_audit module and report."""
    from ml.train_m2 import licence_audit
    import inspect
    source = inspect.getsource(licence_audit)
    assert "Qwen2.5" not in source

    root = repo_root()
    audit = run_licence_audit(root)
    md = render_markdown(audit)
    assert "Qwen2.5" not in md


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
