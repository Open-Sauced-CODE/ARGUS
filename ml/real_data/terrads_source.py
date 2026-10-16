"""
ARGUS Phase 5, Step 4 - reading TerraDS.

TerraDS has two parts (Zenodo record 20339474, version v2):
  * TerraDS.sqlite : tables Repositories, Modules, Resources (metadata only)
  * TerraDS.tar.gz : the source code. Extract it once; each repository then appears as
                     <archive_root>/<Repositories.Id>.tar.gz (one small archive per repository)
                     or as a plain folder <archive_root>/<Repositories.Id>/ .
Both layouts are supported by read_repo_files(). Run `python -m ml.real_data.inspect_terrads` first: it shows
what your copy really looks like before the heavy filter run.
"""

import posixpath
import re
import sqlite3
import tarfile
import zipfile
from pathlib import Path


class TerraDSSchemaError(RuntimeError):
    pass


def open_db(db_path):
    """Open the SQLite file read-only (it is never modified)."""
    path = Path(db_path).resolve()
    if not path.exists():
        raise TerraDSSchemaError("database file not found: {}".format(path))
    con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def table_columns(con, table):
    return [row["name"] for row in con.execute('PRAGMA table_info("{}")'.format(table))]


def describe_database(con):
    """{table: (columns, row count)} for every table in the file."""
    tables = [r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {t: (table_columns(con, t), con.execute('SELECT COUNT(*) FROM "{}"'.format(t)).fetchone()[0]) for t in tables}


def require_schema(con):
    need = {"Repositories": ("Id", "FullName"), "Modules": ("Id", "RepositoryId"), "Resources": ("ModuleId", "Type")}
    for table, columns in need.items():
        have = table_columns(con, table)
        if not have:
            raise TerraDSSchemaError("table {} not found. Tables present: {}".format(table, list(describe_database(con))))
        missing = [c for c in columns if c not in have]
        if missing:
            raise TerraDSSchemaError("table {} lacks column(s) {}. Columns present: {}".format(table, missing, have))


def load_repositories(con, resource_types, limit=None):
    """Repositories that declare at least one of `resource_types`, sorted by Id.
    Returns [{"id", "full_name", "license", "commit"}]."""
    require_schema(con)
    marks = ",".join("?" for _ in resource_types)
    ids = [r[0] for r in con.execute(
        "SELECT DISTINCT m.RepositoryId FROM Resources s JOIN Modules m ON m.Id = s.ModuleId "
        "WHERE s.Type IN ({}) ORDER BY m.RepositoryId".format(marks), list(resource_types))]
    have = set(table_columns(con, "Repositories"))
    license_col = "License" if "License" in have else "NULL"
    commit_col = "LatestCommitSha" if "LatestCommitSha" in have else "NULL"
    repos = []
    for repo_id in ids:
        row = con.execute(
            "SELECT Id, FullName, {} AS lic, {} AS sha FROM Repositories WHERE Id = ?".format(license_col, commit_col),
            (repo_id,)).fetchone()
        if row is None or not row["FullName"]:
            continue
        repos.append({"id": int(row["Id"]), "full_name": str(row["FullName"]),
                      "license": row["lic"] or "unknown", "commit": row["sha"] or "unknown"})
        if limit and len(repos) >= limit:
            break
    return repos


_NUMERIC_ENTRY_RE = re.compile(r"^\d+(\.tar\.gz|\.tgz|\.tar|\.zip)?$")


def detect_archive_root(folder, max_depth=3):
    """Find the folder that really holds the per-repository entries (names like 123.tar.gz or 123/).
    TerraDS may extract into an extra top-level folder, so look a few levels down. Returns a Path, or the
    given folder unchanged when nothing better is found."""
    start = Path(folder)
    level = [start]
    for _ in range(max_depth + 1):
        next_level = []
        for directory in level:
            if not directory.is_dir():
                continue
            entries = list(directory.iterdir())
            numeric = [e for e in entries if _NUMERIC_ENTRY_RE.match(e.name)]
            if len(numeric) >= 1 and len(numeric) >= len(entries) // 2:
                return directory
            next_level.extend(e for e in entries if e.is_dir() and not _NUMERIC_ENTRY_RE.match(e.name))
        level = sorted(next_level)
    return start


def _clean_name(name, repo_id):
    name = name.replace("\\", "/").lstrip("./")
    parts = name.split("/")
    if parts and parts[0] == str(repo_id):
        parts = parts[1:]
    return posixpath.join(*parts) if parts else ""


def _decode(raw):
    return raw.decode("utf-8-sig", errors="replace")


def read_repo_files(archive_root, repo_id, max_file_bytes=400_000):
    """{relative path: text} for every .tf file of one repository, or None if the repository is not found.
    Files larger than max_file_bytes are left out and counted under the key '__too_large__' (an int)."""
    root = Path(archive_root)
    files, too_large = {}, 0
    for base in (root, root / "repositories"):
        for suffix in (".tar.gz", ".tgz", ".tar"):
            archive = base / (str(repo_id) + suffix)
            if archive.is_file():
                with tarfile.open(archive, "r:*") as tar:
                    for member in tar:
                        if not member.isfile() or not member.name.lower().endswith(".tf"):
                            continue
                        if member.size > max_file_bytes:
                            too_large += 1
                            continue
                        name = _clean_name(member.name, repo_id)
                        if name:
                            files[name] = _decode(tar.extractfile(member).read())
                return _finish(files, too_large)
        archive = base / (str(repo_id) + ".zip")
        if archive.is_file():
            with zipfile.ZipFile(archive) as z:
                for info in z.infolist():
                    if info.is_dir() or not info.filename.lower().endswith(".tf"):
                        continue
                    if info.file_size > max_file_bytes:
                        too_large += 1
                        continue
                    name = _clean_name(info.filename, repo_id)
                    if name:
                        files[name] = _decode(z.read(info))
            return _finish(files, too_large)
        folder = base / str(repo_id)
        if folder.is_dir():
            return read_dir_files(folder, max_file_bytes)
    return None


def read_dir_files(folder, max_file_bytes=400_000):
    """Same result as read_repo_files, for a plain folder (used for local clones and extra repositories)."""
    folder = Path(folder)
    files, too_large = {}, 0
    for path in sorted(folder.rglob("*.tf")):
        if not path.is_file() or ".terraform" in path.parts or ".git" in path.parts:
            continue
        if path.stat().st_size > max_file_bytes:
            too_large += 1
            continue
        files[path.relative_to(folder).as_posix()] = _decode(path.read_bytes())
    return _finish(files, too_large)


def _finish(files, too_large):
    files = dict(files)
    files["__too_large__"] = too_large
    return files
