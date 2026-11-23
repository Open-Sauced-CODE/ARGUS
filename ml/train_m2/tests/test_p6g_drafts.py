"""Tests for Phase 6 Stage 4 drafts (P6g).

Verifies:
- PENDING token is present in MODEL_CARD.md and MENTOR_REPORT.md
- No held-out metric names (AUROC on B1/B2/gold, E-SFT, E-v2) appear with numeric values in any draft doc
- No absolute paths or personal user names appear in any draft doc
- All draft docs are ASCII-only
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from ml.train_m2.common import repo_root

DRAFT_FILES = [
    "ml/train_m2/MODEL_CARD.md",
    "ml/train_m2/DATASHEET.md",
    "docs/phase6_shaurya/MENTOR_REPORT.md",
    "docs/PHASE7_HANDOFF.md",
]

FORBIDDEN_USER_NAMES = ["khannashaurya0108", "HP"]

HELDOUT_METRIC_PATTERNS = [
    r"AUROC\s+(?:on|for)?\s*B1\s*[:=]\s*\d+\.\d+",
    r"AUROC\s+(?:on|for)?\s*B2\s*[:=]\s*\d+\.\d+",
    r"AUROC\s+(?:on|for)?\s*gold\s*[:=]\s*\d+\.\d+",
    r"E-SFT\s*[:=]\s*\d+\.\d+",
    r"E-v2\s*[:=]\s*\d+\.\d+",
    r"B1\s+AUROC\s*[:=]\s*\d+\.\d+",
    r"B2\s+AUROC\s*[:=]\s*\d+\.\d+",
    r"gold\s+AUROC\s*[:=]\s*\d+\.\d+",
]


@pytest.fixture(scope="module")
def root_dir() -> Path:
    return repo_root()


def test_draft_files_exist(root_dir: Path) -> None:
    for rel_path in DRAFT_FILES:
        full_path = root_dir / rel_path
        assert full_path.is_file(), f"Draft file does not exist: {rel_path}"


def test_pending_token_present_in_model_card_and_mentor_report(root_dir: Path) -> None:
    for rel_path in ["ml/train_m2/MODEL_CARD.md", "docs/phase6_shaurya/MENTOR_REPORT.md"]:
        text = (root_dir / rel_path).read_text(encoding="utf-8")
        assert "PENDING" in text, f"Literal token PENDING missing from {rel_path}"


def test_no_heldout_metric_values_in_drafts(root_dir: Path) -> None:
    for rel_path in DRAFT_FILES:
        text = (root_dir / rel_path).read_text(encoding="utf-8")
        for pattern in HELDOUT_METRIC_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            assert match is None, (
                f"Forbidden held-out metric value found in {rel_path}: {match.group(0)}"
            )


def test_no_absolute_paths_in_drafts(root_dir: Path) -> None:
    for rel_path in DRAFT_FILES:
        text = (root_dir / rel_path).read_text(encoding="utf-8")
        assert "C:\\" not in text, f"Absolute Windows path found in {rel_path}"
        assert "c:\\" not in text, f"Absolute Windows path found in {rel_path}"
        assert "C:/" not in text, f"Absolute Windows path found in {rel_path}"
        assert "c:/" not in text, f"Absolute Windows path found in {rel_path}"
        assert "/home/" not in text, f"Absolute Linux home path found in {rel_path}"
        assert "Users\\" not in text, f"Absolute Users path found in {rel_path}"
        assert "Users/" not in text, f"Absolute Users path found in {rel_path}"
        assert "/Users/" not in text, f"Absolute Users path found in {rel_path}"


def test_no_forbidden_usernames_in_drafts(root_dir: Path) -> None:
    for rel_path in DRAFT_FILES:
        text = (root_dir / rel_path).read_text(encoding="utf-8")
        for username in FORBIDDEN_USER_NAMES:
            assert username.lower() not in text.lower(), (
                f"Personal username {username!r} found in {rel_path}"
            )


def test_all_drafts_are_ascii(root_dir: Path) -> None:
    for rel_path in DRAFT_FILES:
        text = (root_dir / rel_path).read_text(encoding="utf-8")
        assert text.isascii(), f"Non-ASCII characters found in {rel_path}"


def test_no_verified_in_audit_k13_phrase(root_dir: Path) -> None:
    for rel_path in DRAFT_FILES:
        text = (root_dir / rel_path).read_text(encoding="utf-8")
        assert "verified in audit k13" not in text.lower(), (
            f"Forbidden phrase 'verified in audit K13' found in {rel_path}"
        )


def test_every_ollama_version_in_drafts_appears_in_a_manifest(root_dir: Path) -> None:
    import json
    manifest_versions: set[str] = set()
    manifest_dir = root_dir / "ml" / "train_m2" / "harvest_manifests"
    if manifest_dir.is_dir():
        for mf in manifest_dir.glob("*.json"):
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
                if "ollama_version" in data:
                    manifest_versions.add(str(data["ollama_version"]))
                for v in data.get("ollama_versions_seen_in_files", []):
                    manifest_versions.add(str(v))
            except Exception:
                pass

    assert len(manifest_versions) > 0, "No manifest ollama versions found to validate against"

    for rel_path in DRAFT_FILES:
        text = (root_dir / rel_path).read_text(encoding="utf-8")
        # Match e.g. "Ollama 0.40.11"
        matches = re.findall(r"Ollama\s+([0-9]+\.[0-9]+(?:\.[0-9a-zA-Z_-]+)?)", text, re.IGNORECASE)
        for ver in matches:
            assert ver in manifest_versions, (
                f"Ollama version string {ver!r} in {rel_path} does not appear in any committed harvest manifest: {manifest_versions}"
            )

