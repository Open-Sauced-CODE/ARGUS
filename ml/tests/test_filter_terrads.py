"""
End-to-end test of the Step 4 pipeline on a tiny fake TerraDS (a SQLite file plus archives in three layouts).
Needs OPA (skipped if not found).

Run from the repo root (PowerShell):
    python -m pytest ml/tests/test_filter_terrads.py -v
"""

import csv
import io
import json
import os
import shutil
import sqlite3
import tarfile
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("hcl2", reason="python-hcl2 is not installed (pip install -r requirements-phase5.txt)")

from ml.real_data import inspect_terrads  # noqa: E402
from ml.real_data.buckets import bucket_of  # noqa: E402
from ml.real_data.filter_terrads import run  # noqa: E402
from ml.real_data.rego_runner import evaluate, resource_for_rules  # noqa: E402
from ml.real_data.terrads_source import TerraDSSchemaError, open_db, read_repo_files, require_schema  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (os.environ.get("OPA_BIN") or shutil.which("opa")),
    reason="OPA not found (put opa on PATH or set OPA_BIN)",
)

CLEAN_S3 = '''
resource "aws_s3_bucket" "{name}" {{
  bucket = "very-secret-bucket-{name}"
}}
resource "aws_s3_bucket_server_side_encryption_configuration" "{name}" {{
  bucket = aws_s3_bucket.{name}.id
  rule {{
    apply_server_side_encryption_by_default {{
      sse_algorithm = "{algo}"
    }}
  }}
}}
resource "aws_s3_bucket_public_access_block" "{name}" {{
  bucket                  = aws_s3_bucket.{name}.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}}
resource "aws_s3_bucket_logging" "{name}" {{
  bucket        = aws_s3_bucket.{name}.id
  target_bucket = "logs"
  target_prefix = "p/"
}}
'''
BAD_S3 = 'resource "aws_s3_bucket" "bad" {\n  bucket = "very-secret-bad-bucket"\n}\n'


def sg(cidr, port, name="g"):
    return ('resource "aws_security_group" "%s" {\n  ingress {\n    from_port = %d\n    to_port = %d\n'
            '    protocol = "tcp"\n    cidr_blocks = ["%s"]\n  }\n}\n' % (name, port, port, cidr))


def rds(extra=""):
    return 'resource "aws_db_instance" "db" {\n  storage_encrypted = true\n  engine = "mysql"\n%s}\n' % extra


def name_for(bucket, prefix):
    i = 0
    while bucket_of("{}/repo{}".format(prefix, i)) != bucket:
        i += 1
    return "{}/repo{}".format(prefix, i)


def add_tar(path, files):
    with tarfile.open(path, "w:gz") as tar:
        for name, text in files.items():
            raw = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))


@pytest.fixture
def terrads(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    repos = {
        1: (name_for("train", "a"), {"1/main.tf": CLEAN_S3.format(name="one", algo="aws:kms") + sg("10.0.0.0/16", 443) + BAD_S3}),
        4: (name_for("test", "d"), {"repo/infra/main.tf": CLEAN_S3.format(name="four", algo="AES256") + sg("10.0.0.0/16", 443) + sg("0.0.0.0/0", 22, "open")}),
        5: ("RhinoSecurityLabs/cloudgoat", None),
        6: (name_for("train", "f"), None),
    }
    add_tar(archive / "1.tar.gz", repos[1][1])
    add_tar(archive / "4.tar.gz", repos[4][1])
    (archive / "2" / "modules").mkdir(parents=True)  # plain folder layout
    (archive / "2" / "modules" / "main.tf").write_text(
        CLEAN_S3.format(name="dup", algo="aws:kms") + rds('  multi_az = true\n'), encoding="utf-8")
    with zipfile.ZipFile(archive / "3.zip", "w") as z:  # zip layout
        z.writestr("main.tf", sg("172.16.0.0/12", 8080))
    add_tar(archive / "5.tar.gz", {"5/main.tf": rds('  multi_az = false\n')})
    all_repos = {
        1: repos[1][0], 2: name_for("train", "b"), 3: name_for("val", "c"), 4: repos[4][0],
        5: repos[5][0], 6: repos[6][0], 7: name_for("train", "g"),
    }
    db = tmp_path / "TerraDS.sqlite"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE Repositories (Id INTEGER PRIMARY KEY, Name TEXT, FullName TEXT, License TEXT, LatestCommitSha TEXT, StarCount INTEGER);"
        "CREATE TABLE Modules (Id INTEGER PRIMARY KEY, RepositoryId INTEGER, Path TEXT);"
        "CREATE TABLE Resources (Id INTEGER PRIMARY KEY, ModuleId INTEGER, ResourceType INTEGER, Name TEXT, Type TEXT, Provider TEXT);"
    )
    types = {1: "aws_s3_bucket", 2: "aws_s3_bucket", 3: "aws_security_group", 4: "aws_security_group",
             5: "aws_db_instance", 6: "aws_s3_bucket", 7: "aws_lambda_function"}
    for rid, full in all_repos.items():
        con.execute("INSERT INTO Repositories VALUES (?,?,?,?,?,?)", (rid, full.split("/")[1], full, "MIT", "c0ffee{:02d}".format(rid), 5))
        con.execute("INSERT INTO Modules VALUES (?,?,?)", (rid, rid, "."))
        con.execute("INSERT INTO Resources VALUES (?,?,?,?,?,?)", (rid, rid, 0, "x", types[rid], "aws"))
    con.commit()
    con.close()
    return db, archive, tmp_path


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def test_pipeline_end_to_end(terrads):
    db, archive, tmp = terrads
    summary = run(db, archive, tmp / "bases", tmp / "out", workers=1, progress=False)
    f = summary["funnel"]
    assert f["repos_selected"] == 6  # repo 7 only declares a Lambda
    assert f["repos_archive_missing"] == 1 and f["repos_read"] == 5
    assert f["repos_bucket_reserved"] == 1

    bases = read_jsonl(tmp / "bases" / "bases.jsonl")
    kinds = sorted((b["resource_type"], b["source"]["bucket"]) for b in bases)
    assert kinds == sorted([
        ("AWSS3Bucket", "train"), ("AWSIpPermissionInbound", "train"), ("AWSRDSInstance", "train"),
        ("AWSIpPermissionInbound", "val"), ("AWSS3Bucket", "test"),
    ])
    assert f["duplicates_dropped"] == 2  # same S3 shape in repo 2, same SG shape in repo 4
    assert f["clean_reserved_not_used"] == 1

    # every base is clean, no shape is in two buckets, buckets follow the name hash
    verdicts = evaluate([resource_for_rules(b) for b in bases])
    assert all(v.clean for v in verdicts)
    assert len({b["norm_hash"] for b in bases}) == len(bases)
    for b in bases:
        assert b["source"]["bucket"] == bucket_of(b["source"]["repo"])
        assert b["source"]["license"] == "MIT" and b["source"]["commit"].startswith("c0ffee")

    # no real identifier leaks into the stored bases
    text = (tmp / "bases" / "bases.jsonl").read_text(encoding="utf-8")
    assert "very-secret" not in text

    # Tier C comes from the test bucket only; train violations are only counted
    tierc = read_jsonl(tmp / "out" / "tierC_candidates.jsonl")
    assert len(tierc) == 1 and tierc[0]["source"]["bucket"] == "test"
    assert set(tierc[0]["rules_fired"]) == {"cis.sg_open_ingress", "dpdp.rule6_sg_open_ingress"}
    with open(tmp / "out" / "violation_counts_train.csv", newline="", encoding="utf-8") as handle:
        counted = {row["rule_id"]: int(row["violating_records_in_train_repos"]) for row in csv.DictReader(handle)}
    assert counted["dpdp.rule6a"] == 1 and "cis.sg_open_ingress" not in counted

    # manifest and counts
    with open(tmp / "bases" / "manifest.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(bases) and {"repo", "commit", "license", "file", "bucket"} <= set(rows[0])
    with open(tmp / "bases" / "counts.csv", newline="", encoding="utf-8") as handle:
        counts = {r["resource_type"]: r for r in csv.DictReader(handle)}
    assert counts["AWSS3Bucket"]["total"] == "2" and counts["AWSIpPermissionInbound"]["total"] == "2"
    with open(tmp / "bases" / "repo_buckets.csv", newline="", encoding="utf-8") as handle:
        repo_rows = list(csv.DictReader(handle))
    assert len({r["repo_id"] for r in repo_rows}) == len(repo_rows) == 6  # one row, so one bucket, per repository
    assert json.loads((tmp / "bases" / "funnel.json").read_text())["skip_reasons"] == {}


def test_same_result_with_one_or_two_workers(terrads):
    db, archive, tmp = terrads
    run(db, archive, tmp / "b1", tmp / "o1", workers=1, progress=False)
    run(db, archive, tmp / "b2", tmp / "o2", workers=2, progress=False)
    for name in ("bases.jsonl", "manifest.csv", "counts.csv", "repo_buckets.csv"):
        assert (tmp / "b1" / name).read_bytes() == (tmp / "b2" / name).read_bytes(), name
    assert (tmp / "o1" / "tierC_candidates.jsonl").read_bytes() == (tmp / "o2" / "tierC_candidates.jsonl").read_bytes()


def test_limit_and_extra_local_repository(terrads):
    db, archive, tmp = terrads
    clone = tmp / "clone"
    (clone / "examples").mkdir(parents=True)
    (clone / "examples" / "main.tf").write_text(rds('  multi_az = true\n  allocated_storage = 20\n'), encoding="utf-8")
    summary = run(db, archive, tmp / "b", tmp / "o", limit=2, extras=[("terraform-aws-modules/x", "Apache-2.0", clone)],
                  workers=1, progress=False)
    assert summary["funnel"]["repos_selected"] == 3  # 2 from the database + 1 extra
    extra_bases = [b for b in summary["bases"] if b["source"]["repo"] == "terraform-aws-modules/x"]
    assert len(extra_bases) == 1 and extra_bases[0]["source"]["license"] == "Apache-2.0"
    assert extra_bases[0]["source"]["file"] == "examples/main.tf"


def test_reader_layouts_and_schema_errors(terrads, tmp_path):
    db, archive, tmp = terrads
    nested = read_repo_files(archive, 1)
    assert set(nested) == {"main.tf", "__too_large__"}  # the leading "1/" is stripped
    assert "repo/infra/main.tf" in read_repo_files(archive, 4)  # a first folder that is not the repository id is kept
    assert "modules/main.tf" in read_repo_files(archive, 2)  # plain folder
    assert "main.tf" in read_repo_files(archive, 3)  # zip
    assert read_repo_files(archive, 999) is None
    assert read_repo_files(archive, 1, max_file_bytes=10)["__too_large__"] == 1
    broken = tmp_path / "broken.sqlite"
    con = sqlite3.connect(broken)
    con.execute("CREATE TABLE Repositories (Id INTEGER)")
    con.commit()
    con.close()
    with pytest.raises(TerraDSSchemaError):
        require_schema(open_db(broken))


def test_inspect_script_runs(terrads, capsys):
    db, archive, _tmp = terrads
    assert inspect_terrads.main(["--db", str(db), "--archive-dir", str(archive)]) == 0
    out = capsys.readouterr().out
    assert "Repositories that declare at least one of them: 6" in out and "Resources" in out
    assert ".tar.gz" in out


def test_archive_root_is_found_below_an_extra_top_level_folder(tmp_path):
    from ml.real_data.terrads_source import detect_archive_root

    deep = tmp_path / "TerraDS" / "repositories"
    deep.mkdir(parents=True)
    for n in (1, 2, 3):
        add_tar(deep / "{}.tar.gz".format(n), {"main.tf": rds()})
    assert detect_archive_root(tmp_path) == deep
    assert detect_archive_root(deep) == deep
    empty = tmp_path / "empty"
    empty.mkdir()
    assert detect_archive_root(empty) == empty
