"""Regression test for the C-mined miner on Windows (H3).

It builds a tiny REAL git repository containing everything that differs between a clean Linux checkout and a
Windows one, then asks ml.real_data.gitutil the questions the miner asks:
  * a .tf file committed with CRLF line endings
  * a .tf file that starts with a UTF-8 BOM
  * a directory and a file name with non-ASCII letters (git quotes these unless -z is used)
  * non-ASCII text inside a file
  * a change between two commits (storage_encrypted false -> true)
If the miner fails on Windows because of one of these, this test fails on the broken gitutil and passes on the fixed one.

Run from the repo root:  python -m pytest ml/real_data/diagnostics/tests -q
"""

import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("hcl2", reason="python-hcl2 is not installed (pip install -r requirements-phase5.txt)")

from ml.real_data import gitutil  # noqa: E402
from ml.real_data.tf_normalise import normalise_repo  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not found")

DB = 'resource "aws_db_instance" "db" {\n  # caf\u00e9 na\u00efve \u2013 test\n  engine = "mysql"\n  storage_encrypted = %s\n}\n'
NAMES = {
    "mod/main.tf": "plain/main.tf",
    "mod/crlf.tf": "crlf.tf",
    "bom.tf": "bom.tf",
    "modul\u00e9/donn\u00e9es.tf": "unicode.tf",
}


def run_git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "core.autocrlf=false", "-c", "user.name=t", "-c", "user.email=t@example.com"] + list(args),
                   check=True, capture_output=True)


def write(repo, rel, text, crlf=False, bom=False):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.replace("\n", "\r\n") if crlf else text
    raw = data.encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" + raw) if bom else raw)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    run_git(r, "init", "-q")
    for flag, label in ((False, "one"), (True, "two")):
        write(r, "mod/main.tf", DB % str(flag).lower())
        write(r, "mod/crlf.tf", DB % str(flag).lower(), crlf=True)
        write(r, "bom.tf", DB % str(flag).lower(), bom=True)
        write(r, "modul\u00e9/donn\u00e9es.tf", DB % str(flag).lower())
        run_git(r, "add", "-A")
        run_git(r, "commit", "-q", "-m", label)
    return r


def test_tf_commits_and_parent(repo):
    head = gitutil.head_sha(repo)
    commits = gitutil.tf_commits(repo, head, None)
    assert len(commits) == 2 and commits[0] == head
    parent = gitutil.parent_of(repo, head)
    assert parent == commits[1] and gitutil.parent_of(repo, parent) is None


def test_changed_paths_are_plain_posix_utf8(repo):
    head = gitutil.head_sha(repo)
    paths = sorted(item[1] if isinstance(item, (tuple, list)) else item for item in gitutil.changed_tf_files(repo, head))
    assert paths == sorted(NAMES), paths  # no quotes, no octal escapes, no backslashes, exact letters


def test_files_are_read_with_exact_text(repo):
    head = gitutil.head_sha(repo)
    files = gitutil.read_tf_files(repo, head)
    assert sorted(files) == sorted(NAMES)
    for rel, text in files.items():
        assert "storage_encrypted" in text and "caf\u00e9 na\u00efve \u2013 test" in text, rel
        assert "\ufffd" not in text and "\u00c3" not in text, "%s was decoded with the wrong encoding" % rel


def test_changed_lines_mention_the_change(repo):
    assert "storage_encrypted" in gitutil.changed_lines(repo, gitutil.head_sha(repo))


def test_the_whole_pipeline_finds_the_change_in_every_variant(repo):
    head = gitutil.head_sha(repo)
    parent = gitutil.parent_of(repo, head)
    old = normalise_repo(gitutil.read_tf_files(repo, parent))
    new = normalise_repo(gitutil.read_tf_files(repo, head))
    assert old["parse_errors"] == 0 and new["parse_errors"] == 0, "HCL parser failed on CRLF/BOM/non-ASCII input"
    assert len(old["records"]) == len(new["records"]) == len(NAMES)
    by_file_old = {r["source"]["file"]: r["attrs"]["storage_encrypted"] for r in old["records"]}
    by_file_new = {r["source"]["file"]: r["attrs"]["storage_encrypted"] for r in new["records"]}
    assert set(by_file_old) == set(by_file_new) == set(NAMES)
    assert all(v is False for v in by_file_old.values()) and all(v is True for v in by_file_new.values())
