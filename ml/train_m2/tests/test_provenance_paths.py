"""Tests verifying provenance paths are repo-relative, filename-only outside repo, leak-free, and ignore out/ for git_dirty."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ml.train_m2.common import provenance, repo_root, sha256_file


def test_provenance_inside_repo_path_relative_forward_slashes() -> None:
    """provenance() with an absolute path inside the repo gives a relative path with forward slashes."""
    inside_path = repo_root() / "ml" / "train_m2" / "common.py"
    prov = provenance(argv=["py", str(inside_path)], inputs=[inside_path])
    assert prov["argv"] == ["py", "ml/train_m2/common.py"]
    assert "ml/train_m2/common.py" in prov["input_sha256"]
    assert prov["input_sha256"]["ml/train_m2/common.py"] == sha256_file(inside_path)


def test_provenance_outside_repo_path_filename_only(tmp_path: Path) -> None:
    """An absolute path outside the repo gives only a file name."""
    outside_file = tmp_path / "external_tool.py"
    outside_file.write_text("print(1)", encoding="utf-8")
    prov = provenance(argv=["py", str(outside_file)], inputs=[outside_file])
    assert prov["argv"] == ["py", "external_tool.py"]
    assert "external_tool.py" in prov["input_sha256"]
    assert prov["input_sha256"]["external_tool.py"] == sha256_file(outside_file)


def test_provenance_no_leaked_paths_recursively(tmp_path: Path) -> None:
    """No value anywhere in the dict (recursively, as JSON text) contains repo_root, home, or Users\\."""
    inside_file = repo_root() / "ml" / "train_m2" / "common.py"
    outside_file = tmp_path / "outside_note.txt"
    outside_file.write_text("content", encoding="utf-8")

    prov = provenance(
        extra={
            "inside": inside_file,
            "outside": outside_file,
            "nested": {"deep": [str(inside_file), str(outside_file)]},
        },
        inputs=[inside_file, outside_file],
        argv=["cmd", str(inside_file), str(outside_file)],
    )

    text = json.dumps(prov)
    root = repo_root()
    home = Path.home()

    assert str(root) not in text
    assert root.as_posix() not in text
    assert str(home) not in text
    assert home.as_posix() not in text
    assert "Users\\" not in text
    assert "Users/" not in text


def test_provenance_git_dirty_ignores_out_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """git_dirty is False when the only changes are under ml/train_m2/out/ and True when a tracked source file changes."""
    # Set up a clean git repository inside tmp_path
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "shaurya@argus.local"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Shaurya"], cwd=str(tmp_path), check=True, capture_output=True)

    tracked_source = tmp_path / "source.py"
    tracked_source.write_text("initial = 1\n", encoding="utf-8")
    (tmp_path / "ml" / "train_m2" / "out").mkdir(parents=True)

    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(tmp_path), check=True, capture_output=True)

    monkeypatch.setattr("ml.train_m2.common.repo_root", lambda: tmp_path)

    # 1. Initially clean
    clean_prov = provenance()
    assert clean_prov["git_dirty"] is False

    # 2. Modify/add file inside ml/train_m2/out/ -> must still be False
    (tmp_path / "ml" / "train_m2" / "out" / "report.json").write_text("{}", encoding="utf-8")
    out_prov = provenance()
    assert out_prov["git_dirty"] is False, "changes under ml/train_m2/out/ must not mark repo dirty"

    # 3. Modify tracked file -> must become True
    tracked_source.write_text("initial = 2\n", encoding="utf-8")
    dirty_prov = provenance()
    assert dirty_prov["git_dirty"] is True, "modifying tracked source file must mark repo dirty"
