"""
ARGUS Phase 5, Steps 10-12 - read files out of a git repository WITHOUT checking it out.

Clones are made with --no-checkout, so there is no working folder, no Windows long-path problem and no odd file names.
Everything is read with git plumbing commands (ls-tree, cat-file --batch, log, diff-tree, show).
"""

import os
import subprocess

TF_SUFFIX = ".tf"


class GitError(RuntimeError):
    pass


def _env():
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def run_git(repo, *args, timeout=600):
    """Run `git -C repo args` and return stdout as bytes. Raises GitError on a non-zero exit."""
    proc = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, timeout=timeout, env=_env())
    if proc.returncode != 0:
        raise GitError("git {} failed: {}".format(" ".join(args[:3]), proc.stderr.decode("utf-8", "replace")[:300]))
    return proc.stdout


def has_commit(repo, sha):
    proc = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", sha + "^{commit}"], capture_output=True, env=_env())
    return proc.returncode == 0


def head_sha(repo):
    return run_git(repo, "rev-parse", "HEAD").decode().strip()


def list_tf_files(repo, rev):
    raw = run_git(repo, "ls-tree", "-r", "-z", "--name-only", rev)
    names = [p.decode("utf-8", "replace") for p in raw.split(b"\0") if p]
    return [n for n in names if n.lower().endswith(TF_SUFFIX)]


class BlobReader:
    """One `git cat-file --batch` process that answers many 'rev:path' requests."""

    def __init__(self, repo):
        self.proc = subprocess.Popen(["git", "-C", str(repo), "cat-file", "--batch"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=_env())

    def read(self, spec):
        """Bytes of the object named by `spec` (for example 'abc123:path/main.tf'), or None if it does not exist."""
        if "\n" in spec or self.proc.stdin is None or self.proc.stdout is None:
            return None
        self.proc.stdin.write((spec + "\n").encode("utf-8"))
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().decode("utf-8", "replace").strip()
        parts = header.split()
        if len(parts) < 3 or parts[-1] == "missing":
            return None
        size = int(parts[2])
        data = self.proc.stdout.read(size)
        self.proc.stdout.read(1)  # the newline git prints after every object
        return data

    def close(self):
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
        except Exception:
            pass
        self.proc.wait(timeout=30)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


def read_tf_files(repo, rev, max_file_bytes=400_000, only_dir=None):
    """{path: text} for the .tf files at `rev` (optionally only the ones directly inside `only_dir`).
    Files larger than max_file_bytes are skipped."""
    paths = list_tf_files(repo, rev)
    if only_dir is not None:
        paths = [p for p in paths if p.rpartition("/")[0] == only_dir]
    files = {}
    with BlobReader(repo) as reader:
        for path in paths:
            data = reader.read("{}:{}".format(rev, path))
            if data is None or len(data) > max_file_bytes:
                continue
            files[path] = data.decode("utf-8-sig", errors="replace")
    return files


def tf_commits(repo, rev="HEAD", limit=None):
    """Commit ids (newest first, first parent only) that touched a .tf file."""
    args = ["log", "--first-parent", "--format=%H"]
    if limit:
        args += ["-n", str(int(limit))]
    args += [rev, "--", "*.tf"]
    return [line for line in run_git(repo, *args).decode().split() if line]


def parent_of(repo, sha):
    out = run_git(repo, "rev-list", "--parents", "-n", "1", sha).decode().split()
    return out[1] if len(out) >= 2 else None


def changed_tf_files(repo, sha):
    """[(status, path)] of .tf files changed by one commit, compared with its first parent."""
    raw = run_git(repo, "diff-tree", "--no-commit-id", "--name-status", "-r", "-z", "-m", "--first-parent", sha)
    parts = [p.decode("utf-8", "replace") for p in raw.split(b"\0") if p]
    out, i = [], 0
    while i + 1 < len(parts):
        status, path = parts[i], parts[i + 1]
        i += 2
        if status.startswith(("R", "C")) and i < len(parts):  # rename or copy lists two paths
            path = parts[i]
            i += 1
        if path.lower().endswith(TF_SUFFIX):
            out.append((status[0], path))
    return out


def changed_lines(repo, sha):
    """Text of the added and removed lines of the commit's .tf changes (for a cheap keyword prefilter)."""
    raw = run_git(repo, "show", "--format=", "-U0", "--first-parent", "-m", sha, "--", "*.tf")
    return raw.decode("utf-8", "replace")
