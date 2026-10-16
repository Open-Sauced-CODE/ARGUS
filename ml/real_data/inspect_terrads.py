"""
ARGUS Phase 5, Step 4 - look at your copy of TerraDS BEFORE the heavy run.

Prints the tables and columns of TerraDS.sqlite, how many repositories declare the resource types we need,
and what the extracted archive folder really looks like (nested <id>.tar.gz files or plain folders).
It changes nothing.

Run from the repo root (PowerShell):
    python -m ml.real_data.inspect_terrads --db D:\\terrads\\TerraDS.sqlite --archive-dir D:\\terrads\\archive
    python -m ml.real_data.inspect_terrads --peek-archive D:\\terrads\\TerraDS.tar.gz     (look inside without extracting)
"""

import argparse
import sys
import tarfile
from collections import Counter
from pathlib import Path

from ml.real_data import terrads_source as ts
from ml.real_data.tf_normalise import TARGET_TYPES


def inspect_db(db):
    con = ts.open_db(db)
    print("== Database: {}".format(db))
    for table, (columns, rows) in ts.describe_database(con).items():
        print("  table {:<14} rows {:>10}   columns: {}".format(table, rows, ", ".join(columns)))
    try:
        ts.require_schema(con)
    except ts.TerraDSSchemaError as exc:
        print("  PROBLEM: {}".format(exc))
        return 1
    marks = ",".join("?" for _ in TARGET_TYPES)
    print("  Resource counts for the types we use:")
    for row in con.execute("SELECT Type, COUNT(*) AS n FROM Resources WHERE Type IN ({}) GROUP BY Type ORDER BY n DESC".format(marks), list(TARGET_TYPES)):
        print("    {:<42} {:>9}".format(row["Type"], row["n"]))
    repos = ts.load_repositories(con, TARGET_TYPES)
    print("  Repositories that declare at least one of them: {}".format(len(repos)))
    for repo in repos[:5]:
        print("    sample: id={id} {full_name} license={license} commit={commit}".format(**repo))
    con.close()
    return 0


def inspect_archive_dir(folder):
    root = Path(folder)
    print("== Archive folder: {}".format(root))
    if not root.is_dir():
        print("  PROBLEM: folder not found")
        return 1
    detected = ts.detect_archive_root(root)
    print("  repositories are read from: {}".format(detected))
    root = detected
    kinds = Counter()
    names = []
    for entry in root.iterdir():
        kind = "folder" if entry.is_dir() else (entry.suffix or "no-extension")
        if entry.name.endswith(".tar.gz"):
            kind = ".tar.gz"
        kinds[kind] += 1
        if len(names) < 8:
            names.append(entry.name)
    print("  entries by kind: {}".format(dict(kinds)))
    print("  first entries : {}".format(names))
    nested = next((e for e in root.iterdir() if e.name.endswith(".tar.gz")), None)
    if nested is None and (root / "repositories").is_dir():
        nested = next((e for e in (root / "repositories").iterdir() if e.name.endswith(".tar.gz")), None)
    if nested:
        print("  looking inside {}:".format(nested.name))
        with tarfile.open(nested, "r:*") as tar:
            for i, member in enumerate(tar):
                print("    {}".format(member.name))
                if i >= 9:
                    break
    return 0


def peek_archive(path, count=15):
    print("== First entries of {} (read as a stream, nothing is extracted)".format(path))
    with tarfile.open(path, "r|gz") as tar:
        for i, member in enumerate(tar):
            print("  {:<60} {:>10} bytes".format(member.name, member.size))
            if i + 1 >= count:
                break
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Inspect TerraDS before running the Step 4 filter")
    p.add_argument("--db")
    p.add_argument("--archive-dir")
    p.add_argument("--peek-archive")
    o = p.parse_args(argv)
    if not (o.db or o.archive_dir or o.peek_archive):
        p.error("give at least one of --db, --archive-dir, --peek-archive")
    code = 0
    if o.peek_archive:
        code |= peek_archive(o.peek_archive)
    if o.db:
        code |= inspect_db(o.db)
    if o.archive_dir:
        code |= inspect_archive_dir(o.archive_dir)
    return code


if __name__ == "__main__":
    sys.exit(main())
