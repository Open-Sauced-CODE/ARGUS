"""
Tests for ml/real_data/tf_normalise.py (Phase 5, Step 4). They need python-hcl2 but no OPA and no TerraDS.

Run from the repo root (PowerShell):
    python -m pytest ml/tests/test_tf_normalise.py -v
"""

import json

import pytest

pytest.importorskip("hcl2", reason="python-hcl2 is not installed (pip install -r requirements-phase5.txt)")

from ml.real_data.tf_normalise import norm_hash, normalise_module, normalise_repo, parse_text  # noqa: E402

CLEAN_S3 = '''
resource "aws_s3_bucket" "data" {
  bucket        = "acme-secret-bucket-name"
  force_destroy = true
  tags = { Owner = "someone@example.com" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}
resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}
resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_logging" "data" {
  bucket        = aws_s3_bucket.data.id
  target_bucket = "logs"
  target_prefix = "x/"
}
'''


def norm(text, path="main.tf"):
    return normalise_repo({path: text})


def only(records, rtype):
    return [r for r in records if r["resource_type"] == rtype]


def test_clean_s3_composite_uses_the_rego_field_names():
    out = norm(CLEAN_S3)
    (rec,) = out["records"]
    assert rec["resource_type"] == "AWSS3Bucket"
    assert rec["attrs"] == {
        "default_encryption": True, "encryption_algorithm": "aws:kms", "versioning_status": "Enabled",
        "block_public_acls": True, "block_public_policy": True, "ignore_public_acls": True,
        "restrict_public_buckets": True, "logging_enabled": True, "has_lifecycle_expiration": False,
    }
    assert rec["extras"] == {"force_destroy": True}
    assert rec["source"] == {"file": "main.tf", "tf_type": "aws_s3_bucket", "tf_name": "data"}
    assert out["seen"]["aws_s3_bucket"] == 1 and not out["skips"]


def test_real_names_tags_and_emails_are_never_stored():
    blob = json.dumps(norm(CLEAN_S3)["records"])
    for secret in ("acme-secret-bucket-name", "someone@example.com", "Owner", "logs"):
        assert secret not in blob


def test_bucket_without_companions_is_recorded_as_violating_shape():
    (rec,) = norm('resource "aws_s3_bucket" "b" {\n  bucket = "x"\n}\n')["records"]
    assert rec["attrs"]["default_encryption"] is False
    assert "encryption_algorithm" not in rec["attrs"]
    assert "versioning_status" not in rec["attrs"]  # never-versioned buckets have no status, as in Cartography
    assert rec["attrs"]["block_public_acls"] is False and rec["attrs"]["logging_enabled"] is False


def test_variable_with_plain_default_is_resolved_and_without_default_is_skipped():
    text = CLEAN_S3.replace('"aws:kms"', "var.algo").replace("sse_algorithm = var.algo", "sse_algorithm = var.algo")
    with_default = 'variable "algo" {\n  default = "AES256"\n}\n' + text
    (rec,) = norm(with_default)["records"]
    assert rec["attrs"]["encryption_algorithm"] == "AES256"
    out = norm('variable "algo" {\n  type = string\n}\n' + text)
    assert out["records"] == []
    assert out["skips"]["s3:sse_algorithm_unresolved"] == 1
    assert out["seen"]["aws_s3_bucket"] == 1


def test_local_with_literal_value_is_resolved():
    text = CLEAN_S3.replace('status = "Enabled"', "status = local.v")
    (rec,) = norm('locals {\n  v = "Suspended"\n}\n' + text)["records"]
    assert rec["attrs"]["versioning_status"] == "Suspended"


def test_count_and_for_each_rules():
    base = 'resource "aws_s3_bucket" "b" {\n%s\n}\n'
    assert len(norm(base % "  count = 1")["records"]) == 1
    assert norm(base % "  count = var.create ? 1 : 0")["skips"]["s3:count_unresolved"] == 1
    assert norm(base % "  count = 0")["skips"]["s3:count_zero"] == 1
    assert norm(base % '  for_each = toset(["a"])')["skips"]["s3:for_each"] == 1


def test_companion_with_index_reference_and_literal_name_match():
    text = CLEAN_S3.replace("aws_s3_bucket.data.id", "aws_s3_bucket.data[0].id", 1)
    assert norm(text)["records"][0]["attrs"]["default_encryption"] is True
    literal = 'resource "aws_s3_bucket" "a" {\n  bucket = "same-name"\n}\n' \
              'resource "aws_s3_bucket_logging" "l" {\n  bucket = "same-name"\n}\n'
    assert norm(literal)["records"][0]["attrs"]["logging_enabled"] is True


def test_lifecycle_expiration_and_personal_data_tag():
    text = CLEAN_S3.replace('tags = { Owner = "someone@example.com" }', 'tags = { contains_personal_data = "true" }') + '''
resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    id     = "r"
    status = "Enabled"
    expiration {
      days = 30
    }
  }
}
'''
    (rec,) = norm(text)["records"]
    assert rec["attrs"]["personal_data"] is True and rec["attrs"]["has_lifecycle_expiration"] is True


def test_modules_are_directories_a_companion_in_another_directory_does_not_link():
    enc = (
        'resource "aws_s3_bucket_server_side_encryption_configuration" "data" {\n'
        "  bucket = aws_s3_bucket.data.id\n"
        "  rule {\n    apply_server_side_encryption_by_default {\n      sse_algorithm = \"AES256\"\n    }\n  }\n}\n"
    )
    out = normalise_repo({
        "a/main.tf": 'resource "aws_s3_bucket" "data" {\n  bucket = "x"\n}\n',
        "b/enc.tf": enc,
    })
    (rec,) = out["records"]
    assert rec["source"]["file"] == "a/main.tf"
    assert rec["attrs"]["default_encryption"] is False


def test_security_group_inline_ingress_one_record_per_cidr():
    text = '''
resource "aws_security_group" "web" {
  ingress {
    from_port        = 22
    to_port          = 22
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0", "10.0.0.0/8"]
    ipv6_cidr_blocks = ["::/0"]
  }
  ingress {
    from_port   = var.p
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.1.0.0/16"]
  }
  ingress {
    from_port = 0
    to_port   = 0
    protocol  = "-1"
    cidr_blocks = var.allowed
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
'''
    out = norm(text)
    got = sorted((r["attrs"]["ip_range"], r["attrs"]["fromport"], r["attrs"]["protocol"]) for r in out["records"])
    assert got == sorted([("0.0.0.0/0", 22, "tcp"), ("10.0.0.0/8", 22, "tcp"), ("::/0", 22, "tcp")])
    assert out["skips"]["sg:port_unresolved"] == 1 and out["skips"]["sg:cidr_unresolved"] == 1
    assert all(r["extras"] == {} for r in out["records"])


def test_security_group_rule_and_vpc_ingress_rule_and_egress_ignored():
    text = '''
resource "aws_security_group_rule" "in" {
  type        = "ingress"
  from_port   = 3306
  to_port     = 3306
  protocol    = "tcp"
  cidr_blocks = ["0.0.0.0/0"]
}
resource "aws_security_group_rule" "out" {
  type        = "egress"
  from_port   = 0
  to_port     = 0
  protocol    = "-1"
  cidr_blocks = ["0.0.0.0/0"]
}
resource "aws_vpc_security_group_ingress_rule" "v" {
  cidr_ipv4   = "192.168.0.0/16"
  ip_protocol = "-1"
}
'''
    recs = norm(text)["records"]
    assert sorted((r["attrs"]["ip_range"], r["attrs"]["protocol"], r["attrs"]["fromport"]) for r in recs) == \
        [("0.0.0.0/0", "tcp", 3306), ("192.168.0.0/16", "-1", 0)]


def test_dynamic_ingress_is_counted():
    text = 'resource "aws_security_group" "g" {\n  dynamic "ingress" {\n    for_each = var.x\n    content {\n      from_port = 1\n    }\n  }\n}\n'
    out = norm(text)
    assert out["records"] == [] and out["skips"]["sg:dynamic_ingress"] == 1


def test_rds_instance_drops_secrets_and_keeps_harmless_extras():
    text = 'resource "aws_db_instance" "db" {\n  engine = "postgres"\n  storage_encrypted = true\n  password = "hunter2"\n  username = "admin"\n  multi_az = false\n}\n'
    (rec,) = norm(text)["records"]
    assert rec["resource_type"] == "AWSRDSInstance" and rec["attrs"] == {"storage_encrypted": True}
    assert rec["extras"] == {"engine": "postgres", "multi_az": False}
    assert "hunter2" not in json.dumps(rec) and "admin" not in json.dumps(rec)


IAM = '''
resource "aws_iam_policy" "enc" {
  name   = "p1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject", "s3:ListBucket"], Resource = "arn:aws:s3:::foo/*" },
      { Effect = "Allow", Action = "*", Resource = "*" }
    ]
  })
}
resource "aws_iam_policy" "heredoc" {
  policy = <<EOT
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["ec2:Describe*"], "Resource": "*"}]}
EOT
}
resource "aws_iam_policy" "ref" {
  policy = data.aws_iam_policy_document.d.json
}
resource "aws_iam_policy" "notaction" {
  policy = jsonencode({ Statement = [{ Effect = "Allow", NotAction = ["iam:*"], Resource = "*" }] })
}
data "aws_iam_policy_document" "d" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["*"]
  }
}
'''


def test_iam_statements_from_jsonencode_heredoc_and_policy_document():
    out = norm(IAM)
    stmts = sorted((tuple(r["attrs"]["action"]), tuple(r["attrs"]["resource"])) for r in only(out["records"], "AWSPolicyStatement"))
    assert stmts == sorted([
        (("s3:GetObject", "s3:ListBucket"), ("arn:aws:s3:::foo/*",)),
        (("*",), ("*",)),
        (("ec2:Describe*",), ("*",)),
        (("s3:GetObject",), ("*",)),
    ])
    assert out["skips"]["iam:not_action_or_resource"] == 1
    assert all(r["attrs"]["effect"] == "Allow" for r in out["records"])


def test_norm_hash_ignores_names_and_tags_but_not_attributes():
    a = norm('resource "aws_db_instance" "one" {\n  storage_encrypted = true\n  engine = "mysql"\n  tags = { A = "1" }\n}\n')["records"][0]
    b = norm('resource "aws_db_instance" "two" {\n  storage_encrypted = true\n  engine = "mysql"\n  tags = { B = "2" }\n}\n')["records"][0]
    c = norm('resource "aws_db_instance" "one" {\n  storage_encrypted = false\n  engine = "mysql"\n}\n')["records"][0]
    assert a["norm_hash"] == b["norm_hash"] != c["norm_hash"]
    assert a["norm_hash"] == norm_hash(a["resource_type"], a["attrs"], a["extras"])


def test_unparseable_file_is_counted_not_fatal():
    out = normalise_repo({"bad.tf": 'resource "aws_s3_bucket" "x" {\n  bucket = \n', "ok.tf": 'resource "aws_db_instance" "d" {\n  storage_encrypted = true\n}\n'})
    assert out["parse_errors"] == 1 and out["files_parsed"] == 1 and len(out["records"]) == 1


def test_normalise_module_accepts_pre_parsed_files():
    records, skips, seen = normalise_module([("m.tf", parse_text('resource "aws_db_instance" "d" {\n  storage_encrypted = true\n}\n'))])
    assert len(records) == 1 and not skips and seen["aws_db_instance"] == 1
