"""Tests for ml/real_data/gitutil.py on a tiny local git repository (needs git on PATH).

    python -m pytest ml/tests/test_gitutil.py -v
"""

import shutil
import subprocess

import pytest

from ml.real_data import gitutil

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not found")


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo)] + list(args), check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    (r / "mod").mkdir(parents=True)
    git(r, "init", "-q")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "t")
    (r / "mod" / "main.tf").write_text('resource "aws_db_instance" "d" {\n  storage_encrypted = false\n}\n')
    (r / "readme.md").write_text("x")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "one")
    (r / "mod" / "main.tf").write_text('resource "aws_db_instance" "d" {\n  storage_encrypted = true\n}\n')
    git(r, "commit", "-q", "-am", "two")
    return r


def test_read_without_checkout_and_history(repo):
    head = gitutil.head_sha(repo)
    assert gitutil.list_tf_files(repo, head) == ["mod/main.tf"]
    files = gitutil.read_tf_files(repo, head)
    assert "storage_encrypted = true" in files["mod/main.tf"]
    assert gitutil.read_tf_files(repo, head, only_dir="") == {}
    commits = gitutil.tf_commits(repo, head)
    assert len(commits) == 2 and commits[0] == head
    parent = gitutil.parent_of(repo, head)
    assert "storage_encrypted = false" in gitutil.read_tf_files(repo, parent)["mod/main.tf"]
    assert gitutil.parent_of(repo, commits[1]) is None
    assert gitutil.changed_tf_files(repo, head) == [("M", "mod/main.tf")]
    assert "storage_encrypted" in gitutil.changed_lines(repo, head)
    assert gitutil.has_commit(repo, head) and not gitutil.has_commit(repo, "0" * 40)
