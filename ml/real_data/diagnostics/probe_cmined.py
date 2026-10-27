"""H3 probe: why did the C-mined miner find 0 resource pairs on Windows?

Run (PowerShell, repo root):
    python -m ml.real_data.diagnostics.probe_cmined --repo D:\\argus_clones\\7363082

It is READ ONLY (it never changes a clone). It compares three layers on the same commits:
  1. RAW git (subprocess, bytes): exit codes, stderr, shallow clone, ownership errors, path bytes, blob bytes
  2. ml.real_data.gitutil (what the miner calls): the same questions, exceptions shown, not swallowed
  3. an independent pairing (gitutil + tf_normalise): parent records vs commit records, changed records
and prints a list of PROBLEMS FOUND with the fix to try. Output is also saved (ASCII only) to
docs/phase6_prabhav/cmined_probe_<repo>.txt. Send me that file if the problems list is empty.
"""

from __future__ import annotations

import argparse
import inspect
import locale
import platform
import subprocess
import sys
import traceback
from collections import Counter
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

OUT: List[str] = []
PROBLEMS: List[str] = []
STATE: Dict[str, int] = {"parse_errors": 0}


def say(text: str = "") -> None:
    OUT.append(text)
    print(text)


def problem(code: str, advice: str) -> None:
    if not any(p.startswith(code + ":") for p in PROBLEMS):
        PROBLEMS.append("%s: %s" % (code, advice))


def git(repo: Path, *args: str) -> Tuple[int, bytes, bytes]:
    """Run git in repo and return (exit code, stdout bytes, stderr bytes). Never decodes, never raises on exit code."""
    done = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, timeout=120)
    return done.returncode, done.stdout, done.stderr


def short(data: Any, limit: int = 260) -> str:
    return ascii(data)[:limit]


def utf8_ok(data: bytes) -> bool:
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def parse_z_names(raw: bytes) -> List[Tuple[str, bytes]]:
    """Parse `diff-tree --name-status -z` output into [(status, path bytes)]."""
    parts = raw.split(b"\0")
    out: List[Tuple[str, bytes]] = []
    i = 0
    while i < len(parts) - 1:
        status = parts[i].decode("ascii", "replace")
        if not status:
            i += 1
            continue
        if status[:1] in ("R", "C"):  # rename/copy: old and new path
            out.append((status, parts[i + 2]))
            i += 3
        else:
            out.append((status, parts[i + 1]))
            i += 2
    return out


# ---------------------------------------------------------------------------------------------------------
# section 0 and 1: environment and raw git
# ---------------------------------------------------------------------------------------------------------

def section_environment() -> None:
    say("== 0. Environment")
    say("platform            : %s" % platform.platform())
    say("python              : %s" % platform.python_version())
    say("preferred encoding  : %s   (subprocess text=True uses this; utf-8 is the safe value)" % locale.getpreferredencoding(False))
    say("filesystem encoding : %s" % sys.getfilesystemencoding())
    for package in ("python-hcl2", "jsonschema"):
        try:
            say("%-20s: %s" % (package, metadata.version(package)))
        except metadata.PackageNotFoundError:
            say("%-20s: NOT INSTALLED" % package)
    code, out, err = git(Path("."), "--version")
    say("git                 : %s" % out.decode("ascii", "replace").strip())
    if "windows" in platform.platform().lower() and locale.getpreferredencoding(False).lower() not in ("utf-8", "utf8"):
        say("NOTE: Windows default encoding is %s. Any gitutil call using text=True decodes git output with it." % locale.getpreferredencoding(False))


def section_raw_health(repo: Path) -> Optional[str]:
    say("")
    say("== 1. Raw git health of %s" % repo)
    code, out, err = git(repo, "rev-parse", "HEAD")
    say("rev-parse HEAD      : exit %d  stdout %s  stderr %s" % (code, short(out.strip()), short(err.strip(), 200)))
    if code != 0:
        if b"dubious ownership" in err or b"safe.directory" in err:
            problem("SAFE_DIRECTORY", "Git refuses repos owned by another Windows user. Run: git config --global --add safe.directory \"*\"   "
                    "(this also explains 'zero everything': every git call fails and the miner swallowed the error).")
        else:
            problem("GIT_FAILS", "git rev-parse HEAD fails in this clone (see stderr above); every later step fails too.")
        return None
    head = out.strip().decode("ascii", "replace")
    for label, args in (("is-shallow", ["rev-parse", "--is-shallow-repository"]), ("core.quotepath", ["config", "--get", "core.quotepath"]),
                        ("core.autocrlf", ["config", "--get", "core.autocrlf"]), ("commit count", ["rev-list", "--count", "HEAD"])):
        c, o, e = git(repo, *args)
        say("%-20s: %s" % (label, short(o.strip() or e.strip(), 80)))
        if label == "is-shallow" and o.strip() == b"true":
            problem("SHALLOW_CLONE", "The clone is shallow: parent commits are missing, so no (parent, commit) pair can be built. Run: git -C <clone> fetch --unshallow")
    c, o, e = git(repo, "log", "--format=%H", "--", "*.tf")
    raw_tf = [x for x in o.decode("ascii", "replace").split() if x]
    say("commits touching *.tf (raw git log): %d" % len(raw_tf))
    section_raw_health.raw_tf = raw_tf  # type: ignore[attr-defined]
    return head


# ---------------------------------------------------------------------------------------------------------
# section 2: raw plumbing on sample commits
# ---------------------------------------------------------------------------------------------------------

def section_raw_commits(repo: Path, commits: Sequence[str]) -> None:
    say("")
    say("== 2. Raw plumbing on the first %d commits touching *.tf" % len(commits))
    seen_nonascii = seen_backslash = seen_crlf = seen_bom = seen_non_utf8 = 0
    no_parent = 0
    for sha in commits:
        c, parent, e = git(repo, "rev-parse", "--verify", "-q", sha + "^")
        if c != 0:
            no_parent += 1
            continue
        c, raw, e = git(repo, "diff-tree", "--no-commit-id", "--name-status", "-r", "-z", sha)
        names = parse_z_names(raw)
        for status, path in names:
            if not path.endswith(b".tf"):
                continue
            if not utf8_ok(path):
                seen_non_utf8 += 1
            if any(b > 127 for b in path):
                seen_nonascii += 1
            if b"\\" in path:
                seen_backslash += 1
            if status[:1] != "D":
                c, blob, e = git(repo, "show", "%s:%s" % (sha, path.decode("utf-8", "replace")))
                if c == 0:
                    seen_crlf += blob.count(b"\r\n") > 0
                    seen_bom += blob.startswith(b"\xef\xbb\xbf")
                    if not utf8_ok(blob):
                        seen_non_utf8 += 1
        if len(commits) <= 3:
            say("  %s parent %s names %s" % (sha[:10], parent.strip()[:10].decode("ascii", "replace"), short(names, 300)))
    say("commits without a parent among the sample : %d" % no_parent)
    say("tf paths with non-ASCII bytes             : %d" % seen_nonascii)
    say("tf paths containing a backslash           : %d" % seen_backslash)
    say("tf blobs with CRLF line endings           : %d" % seen_crlf)
    say("tf blobs starting with a UTF-8 BOM        : %d" % seen_bom)
    say("tf paths or blobs that are not valid UTF-8: %d" % seen_non_utf8)
    section_raw_commits.facts = {"nonascii": seen_nonascii, "crlf": seen_crlf, "bom": seen_bom, "non_utf8": seen_non_utf8}  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------------------------------------
# section 3: gitutil as the miner calls it
# ---------------------------------------------------------------------------------------------------------

def attempt(label: str, fn, *args: Any, **kwargs: Any) -> Tuple[bool, Any]:
    try:
        return True, fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - the whole point is to show what the miner swallowed
        say("  EXCEPTION in %s: %s: %s" % (label, type(exc).__name__, str(exc)[:300]))
        tb = traceback.extract_tb(exc.__traceback__)[-1]
        say("    at %s line %d: %s" % (Path(tb.filename).name, tb.lineno, (tb.line or "").strip()[:160]))
        problem("GITUTIL_EXCEPTION", "%s raises %s on this clone (the miner probably catches it and counts nothing). See the lines above for the exact line." % (label, type(exc).__name__))
        return False, None


def section_gitutil(repo: Path, head: str, raw_tf: List[str], sample: int) -> Dict[str, Any]:
    say("")
    say("== 3. ml.real_data.gitutil on the same clone")
    result: Dict[str, Any] = {"commits": []}
    try:
        from ml.real_data import gitutil
    except Exception as exc:  # noqa: BLE001
        say("  cannot import ml.real_data.gitutil: %s: %s" % (type(exc).__name__, exc))
        problem("GITUTIL_IMPORT", "ml.real_data.gitutil does not import: %s" % exc)
        return result
    ok, g_head = attempt("head_sha", gitutil.head_sha, repo)
    say("head_sha           : %s (raw git says %s) %s" % (short(g_head, 50), head[:12], "same" if g_head == head else "DIFFERENT"))
    ok, g_commits = attempt("tf_commits", gitutil.tf_commits, repo, head, None)
    if ok:
        g_commits = list(g_commits)
        say("tf_commits         : %d commits (raw git log says %d)" % (len(g_commits), len(raw_tf)))
        if set(g_commits) != set(raw_tf):
            problem("TF_COMMITS_MISMATCH", "gitutil.tf_commits returns %d commits but git log -- '*.tf' lists %d. Compare the git arguments used in tf_commits (pathspec, --first-parent, --no-merges)." % (len(g_commits), len(raw_tf)))
    else:
        g_commits = raw_tf
    result["commits"] = g_commits
    bad_parent = bad_changed = bad_read = replacement = backslash_paths = non_posix = 0
    parents: Dict[str, Optional[str]] = {}
    for sha in g_commits[:sample]:
        ok, parent = attempt("parent_of(%s)" % sha[:8], gitutil.parent_of, repo, sha)
        parents[sha] = parent if ok else None
        if ok and parent is None:
            bad_parent += 1
        ok, changed = attempt("changed_tf_files(%s)" % sha[:8], gitutil.changed_tf_files, repo, sha)
        if ok:
            if not changed:
                bad_changed += 1
            for item in changed:
                path = item[1] if isinstance(item, (tuple, list)) else item
                if "\\" in path:
                    backslash_paths += 1
                if path.startswith('"') or "\\3" in path:
                    non_posix += 1
        ok, files = attempt("read_tf_files(%s)" % sha[:8], gitutil.read_tf_files, repo, sha)
        if ok:
            if not files:
                bad_read += 1
            if any("\ufffd" in text for text in files.values() if isinstance(text, str)):
                replacement += 1
    n = min(sample, len(g_commits))
    say("over %d sampled commits: parent_of returned None for %d; changed_tf_files empty for %d; read_tf_files empty for %d"
        % (n, bad_parent, bad_changed, bad_read))
    say("paths with backslashes %d, quoted/escaped paths %d, files containing U+FFFD (decode damage) %d" % (backslash_paths, non_posix, replacement))
    if n and bad_parent == n:
        problem("NO_PARENTS", "parent_of returns None for every sampled commit. If the clone is not shallow, check the rev-parse call in parent_of.")
    if n and bad_changed == n:
        problem("NO_CHANGED_FILES", "changed_tf_files is empty for every sampled commit: look at the diff-tree arguments and how the -z output is split.")
    if n and bad_read == n:
        problem("NO_FILES_READ", "read_tf_files returns nothing for every sampled commit: look at how blobs are listed/read (ls-tree, cat-file, show).")
    if backslash_paths:
        problem("BACKSLASH_PATHS", "gitutil returns paths with backslashes. Git paths must stay POSIX: build them with str(PurePosixPath(...)) and never with os.path.join or Path on the git side.")
    if non_posix:
        problem("QUOTED_PATHS", "gitutil returns quoted/octal-escaped paths: use -z (NUL separated) output or -c core.quotepath=false, and decode as UTF-8.")
    if replacement:
        problem("DECODE_DAMAGE", "file text contains U+FFFD: git output is decoded with the wrong encoding. Decode bytes explicitly with utf-8 (errors='replace' is fine) instead of text=True.")
    result["parents"] = parents
    return result


# ---------------------------------------------------------------------------------------------------------
# section 4: independent pairing
# ---------------------------------------------------------------------------------------------------------

def record_key(rec: Dict[str, Any]) -> Tuple[Any, ...]:
    src = rec.get("source", {})
    return (rec.get("resource_type"), src.get("file"), src.get("tf_type"), src.get("tf_name"))


def section_pairing(repo: Path, info: Dict[str, Any], sample: int) -> None:
    say("")
    say("== 4. Independent pairing (gitutil + tf_normalise), first %d commits with a parent" % sample)
    try:
        from ml.real_data import gitutil
        from ml.real_data.tf_normalise import normalise_repo
    except Exception as exc:  # noqa: BLE001
        say("  cannot import: %s: %s" % (type(exc).__name__, exc))
        problem("NORMALISE_IMPORT", "tf_normalise or gitutil does not import: %s" % exc)
        return
    tot = Counter()
    for sha in info.get("commits", [])[:sample * 3]:
        parent = info.get("parents", {}).get(sha)
        if parent is None:
            ok, parent = attempt("parent_of", gitutil.parent_of, repo, sha)
            if not ok or parent is None:
                continue
        if tot["commits_used"] >= sample:
            break
        tot["commits_used"] += 1
        old: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        new: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        ok_a, files_a = attempt("read_tf_files(parent)", gitutil.read_tf_files, repo, parent)
        ok_b, files_b = attempt("read_tf_files(commit)", gitutil.read_tf_files, repo, sha)
        if not (ok_a and ok_b):
            continue
        for label, files in (("parent", files_a), ("commit", files_b)):
            ok, norm = attempt("normalise_repo(%s)" % label, normalise_repo, files)
            if not ok:
                continue
            tot["records_" + label] += len(norm["records"])
            tot["parse_errors"] += norm.get("parse_errors", 0)
            tot["files_parsed"] += norm.get("files_parsed", 0)
            for reason, count in norm.get("skips", {}).items():
                tot["skip:" + reason] += count
            if label == "parent":
                old = {record_key(r): r for r in norm["records"]}
            else:
                new = {record_key(r): r for r in norm["records"]}
        common = set(old) & set(new)
        tot["common_keys"] += len(common)
        tot["changed_records"] += sum(1 for k in common if old[k].get("attrs") != new[k].get("attrs") or old[k].get("extras") != new[k].get("extras"))
        tot["pairs_if_any_attr_same_key"] += len(common)
    STATE["parse_errors"] = tot["parse_errors"]
    for key in sorted(tot):
        say("  %-32s %d" % (key, tot[key]))
    if tot["commits_used"] and tot["records_parent"] + tot["records_commit"] == 0:
        problem("NO_RECORDS", "tf_normalise produced 0 records from files that gitutil returned. Either the files are empty/undecodable (see section 3) or HCL parsing fails (parse_errors above).")
    if tot["parse_errors"] and tot["files_parsed"] == 0:
        problem("HCL_PARSE_FAILS", "python-hcl2 fails on every file. Check CRLF and BOM below; try text.replace('\\r\\n', '\\n') and text.lstrip('\\ufeff') before parsing.")
    if tot["commits_used"] and tot["common_keys"] == 0 and tot["records_parent"] and tot["records_commit"]:
        problem("NO_COMMON_KEYS", "records exist on both sides but no record key is shared: path separators or file names differ between the parent and commit reads.")


def section_crlf_check(repo: Path, head: str) -> None:
    """Does python-hcl2 parse a CRLF / BOM copy of a real file of this clone as well as the LF copy?"""
    say("")
    say("== 5. CRLF and BOM against python-hcl2 (real file from the clone)")
    try:
        import hcl2
    except ImportError:
        say("  python-hcl2 is not installed")
        problem("HCL2_MISSING", "pip install python-hcl2 (Phase 5 requirements-phase5.txt)")
        return
    c, out, e = git(repo, "ls-tree", "-r", "--name-only", "-z", head)
    names = [n for n in out.split(b"\0") if n.endswith(b".tf")]
    if not names:
        say("  no .tf file at HEAD")
        return
    name = names[0].decode("utf-8", "replace")
    c, blob, e = git(repo, "show", "%s:%s" % (head, name))
    text = blob.decode("utf-8", "replace")
    variants = {"as stored": text, "LF": text.replace("\r\n", "\n"), "CRLF": text.replace("\r\n", "\n").replace("\n", "\r\n"),
                "BOM + LF": "\ufeff" + text.replace("\r\n", "\n")}
    results = {}
    for label, variant in variants.items():
        try:
            hcl2.loads(variant)
            results[label] = "parses"
        except Exception as exc:  # noqa: BLE001
            results[label] = "FAILS (%s)" % type(exc).__name__
    say("  file %s: %s" % (ascii(name), results))
    facts = getattr(section_raw_commits, "facts", {})
    if results["LF"] == "parses" and results["CRLF"] != "parses" and facts.get("crlf"):
        problem("CRLF_PARSE", "python-hcl2 fails on CRLF text but parses LF. Normalise newlines (text.replace('\\r\\n', '\\n')) in gitutil.read_tf_files or tf_normalise.parse_text.")
    if results["BOM + LF"] != "parses":
        say("  note: python-hcl2 cannot parse a BOM by itself; that only matters if gitutil/tf_normalise do not strip it.")
    if results["LF"] == "parses" and results["BOM + LF"] != "parses" and facts.get("bom") and STATE["parse_errors"]:
        problem("BOM_PARSE", "python-hcl2 fails on text starting with a BOM. Decode blobs with utf-8-sig (or strip \\ufeff) before parsing.")


def section_miner_signature(repo: Path, info: Dict[str, Any]) -> None:
    say("")
    say("== 6. mine_history.pairs_for_commit (signature, and one best-effort call)")
    try:
        from ml.real_data import mine_history
        fn = mine_history.pairs_for_commit
    except Exception as exc:  # noqa: BLE001
        say("  cannot import pairs_for_commit: %s: %s" % (type(exc).__name__, exc))
        return
    sig = inspect.signature(fn)
    say("  signature: pairs_for_commit%s" % sig)
    commits = info.get("commits", [])
    if not commits:
        return
    sha = commits[0]
    parent = info.get("parents", {}).get(sha)
    known = {"repo": repo, "repo_dir": repo, "d": repo, "clone": repo, "path": repo, "repo_path": repo,
             "sha": sha, "commit": sha, "commit_sha": sha, "c": sha, "parent": parent, "parent_sha": parent,
             "counters": Counter(), "counter": Counter(), "funnel": Counter(), "stats": Counter()}
    kwargs: Dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name in known:
            kwargs[name] = known[name]
        elif param.default is inspect.Parameter.empty and param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY):
            say("  cannot call automatically: required argument %r is unknown to this probe. Call it by hand with the repo %s and commit %s and paste me the result." % (name, repo, sha[:10]))
            return
    try:
        value = fn(**kwargs)
        say("  call on %s returned %s: %s" % (sha[:10], type(value).__name__, short(value, 300)))
        for name in ("counters", "counter", "funnel", "stats"):
            if name in kwargs:
                say("  %s after the call: %s" % (name, dict(kwargs[name])))
    except Exception as exc:  # noqa: BLE001
        say("  EXCEPTION: %s: %s" % (type(exc).__name__, str(exc)[:300]))
        problem("MINER_EXCEPTION", "pairs_for_commit raises %s on the first commit (see above)." % type(exc).__name__)


# ---------------------------------------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="H3 probe for the C-mined miner on Windows")
    p.add_argument("--repo", required=True, type=Path, help=r"clone folder, e.g. D:\argus_clones\7363082")
    p.add_argument("--sample", type=int, default=25, help="commits to examine in depth (default 25)")
    p.add_argument("--save", type=Path, default=None, help="output file (default docs/phase6_prabhav/cmined_probe_<folder>.txt)")
    args = p.parse_args(list(sys.argv[1:] if argv is None else argv))
    OUT.clear()
    PROBLEMS.clear()
    repo = args.repo
    if not (repo / ".git").exists() and not (repo / "HEAD").exists():
        print("%s is not a git clone (no .git inside)." % repo)
        return 2
    section_environment()
    head = section_raw_health(repo)
    if head is not None:
        raw_tf = getattr(section_raw_health, "raw_tf", [])
        section_raw_commits(repo, raw_tf[: args.sample])
        facts = getattr(section_raw_commits, "facts", {})
        if facts.get("non_utf8"):
            problem("NON_UTF8", "some paths or files are not valid UTF-8; read them as bytes and decode with errors='replace'.")
        info = section_gitutil(repo, head, raw_tf, args.sample)
        section_pairing(repo, info, args.sample)
        section_crlf_check(repo, head)
        section_miner_signature(repo, info)
    say("")
    say("== PROBLEMS FOUND: %d" % len(PROBLEMS))
    for item in PROBLEMS:
        say("  - " + item)
    if not PROBLEMS:
        say("  none detected by this probe. Send the saved file; the cause is in the miner's own logic (mine_history.pairs_for_commit / _index).")
    save = args.save or (Path("docs") / "phase6_prabhav" / ("cmined_probe_%s.txt" % repo.name))
    save.parent.mkdir(parents=True, exist_ok=True)
    save.write_bytes(("\n".join(OUT) + "\n").encode("ascii", "replace"))
    print("Saved to %s" % save.resolve())
    return 1 if PROBLEMS else 0


if __name__ == "__main__":
    sys.exit(main())
