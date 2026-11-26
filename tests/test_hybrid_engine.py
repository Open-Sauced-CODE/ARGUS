"""Comprehensive tests for ARGUS Hybrid Deployment, Local Scanners, Dual-Mode API & Guardrails."""

from __future__ import annotations

import io
import json
import os
import threading
import time
import urllib.error
import urllib.request
import zipfile
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.api_server import ArgusAppHandler, STATE, StateManager
from local_engine.graph.inmemory_session import LocalCartographySession
from local_engine.hcl_writer import build_audit_bundle_zip, export_finding_patch
from local_engine.pipeline_orchestrator import run_local_scan_pipeline
from local_engine.scanners.aws_scanner import IamGuardBlockedError, scan_aws_account
from local_engine.scanners.terraform_scanner import scan_terraform_directory
from local_engine.state_store import LocalStateStore
from risk.attack_graph import build_attack_graph


SAMPLE_TF = """
resource "aws_s3_bucket" "citizen_kyc" {
  bucket = "swasthya-citizen-kyc-pii"
  tags = {
    contains_personal_data = "true"
  }
}

resource "aws_security_group" "bastion" {
  name   = "bastion-sg"
  vpc_id = "vpc-12345678"
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_user" "dev" {
  name = "developer-raynor"
}

resource "aws_iam_access_key" "dev_key" {
  user   = aws_iam_user.dev.name
  status = "Active"
}

resource "aws_iam_role" "app_role" {
  name = "app-deployer-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { AWS = "arn:aws:iam::local:user/developer-raynor" }
    }]
  })
}

resource "aws_iam_policy" "admin_pol" {
  name = "dev-admin-wildcard"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "AllowAll"
      Effect   = "Allow"
      Action   = ["*"]
      Resource = ["*"]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "attach_admin" {
  role       = aws_iam_role.app_role.name
  policy_arn = aws_iam_policy.admin_pol.arn
}

resource "aws_db_instance" "main_pg" {
  identifier        = "citizen-db"
  storage_encrypted = false
}
"""


def _request_json(url: str, method: str = "GET", data: dict | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    body = json.dumps(data).encode("utf-8") if data is not None else None
    try:
        with urllib.request.urlopen(req, data=body, timeout=20) as resp:
            raw = resp.read()
            return resp.status, dict(resp.headers), (json.loads(raw.decode("utf-8")) if raw else None)
    except urllib.error.HTTPError as err:
        raw = err.read()
        return err.code, dict(err.headers), (json.loads(raw.decode("utf-8")) if raw else None)


# -----------------------------------------------------------------------------
# 1. TERRAFORM SCANNER + FROZEN GRAPH + PIPELINE ORCHESTRATOR TESTS
# -----------------------------------------------------------------------------

def test_terraform_scanner_detects_dpdp_cis_and_builds_attack_graph(tmp_path):
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(SAMPLE_TF, encoding="utf-8")

    scan_res = scan_terraform_directory(tmp_path)
    assert scan_res["source_type"] == "terraform"
    assert str(tf_file) in scan_res["files_scanned"]
    if Path(r"D:\opa\opa.exe").exists():
        assert scan_res["opa_used"] is True

    rule_ids = {f["rule_id"] for f in scan_res["raw_findings"]}
    assert "dpdp.rule6a" in rule_ids
    assert "dpdp.rule6_public_exposure" in rule_ids
    assert "dpdp.rule6_versioning" in rule_ids
    assert "dpdp.rule6_logging" in rule_ids
    assert "dpdp.rule8_lifecycle" in rule_ids
    assert "dpdp.rule6_sg_open_ingress" in rule_ids
    assert "cis.iam_no_full_admin" in rule_ids
    assert "dpdp.rule6a_rds" in rule_ids

    # Verify frozen risk.attack_graph works directly on LocalCartographySession
    session = scan_res["session"]
    assert isinstance(session, LocalCartographySession)
    G = build_attack_graph(session)
    assert G.number_of_nodes() >= 6
    assert G.number_of_edges() >= 4


def test_terraform_scanner_error_paths(tmp_path):
    with pytest.raises(FileNotFoundError):
        scan_terraform_directory(tmp_path / "does-not-exist")
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(ValueError):
        scan_terraform_directory(empty_dir)


def test_local_pipeline_enforces_m2_uncertified_guardrail_and_airlock(tmp_path, monkeypatch):
    monkeypatch.setenv("ARGUS_DATA_DIR", str(tmp_path / "argus_data"))
    tf_dir = tmp_path / "infra"
    tf_dir.mkdir()
    (tf_dir / "main.tf").write_text(SAMPLE_TF, encoding="utf-8")

    scan_res = scan_terraform_directory(tf_dir)
    out = run_local_scan_pipeline(scan_res, region="ap-south-1")

    assert out["m2_status"]["certified"] is False
    assert len(out["findings"]) >= 6
    assert len(out["findings"]) == len(scan_res["raw_findings"])
    # Autonomy OFF: while tau_star.json is absent, ZERO findings may auto-apply
    for f in out["findings"]:
        assert f["certified"] is False
        assert f["auto_apply_status"] in ("NEEDS_APPROVAL", "ESCALATED")
        assert f["auto_apply_status"] != "APPROVED"
        assert f["auto_apply_status"] != "APPLIED"

    # Privacy Airlock: zero raw bucket names in projected_fields, leaked_to_network is False
    for r in out["receipts"]:
        assert r["leaked_to_network"] is False
        serialized = json.dumps(r["projected_fields"])
        assert "swasthya-citizen-kyc-pii" not in serialized


# -----------------------------------------------------------------------------
# 2. AWS SCANNER + IAM_GUARD PRE-FLIGHT TESTS (MOCKED BOTO3)
# -----------------------------------------------------------------------------

def _make_mock_aws_session(policy_doc: dict):
    sts = MagicMock()
    sts.get_caller_identity.return_value = {
        "Account": "111122223333",
        "Arn": "arn:aws:iam::111122223333:user/argus-scanner",
    }

    iam = MagicMock()
    paginator_attached = MagicMock()
    paginator_attached.paginate.return_value = [{"AttachedPolicies": [{"PolicyArn": "arn:aws:iam::111122223333:policy/TestPol", "PolicyName": "TestPol"}]}]
    paginator_inline = MagicMock()
    paginator_inline.paginate.return_value = [{"PolicyNames": []}]
    paginator_groups = MagicMock()
    paginator_groups.paginate.return_value = [{"Groups": []}]

    def get_paginator(op_name):
        if op_name == "list_attached_user_policies":
            return paginator_attached
        if op_name == "list_user_policies":
            return paginator_inline
        if op_name == "list_groups_for_user":
            return paginator_groups
        raise AssertionError(f"Unexpected paginator: {op_name}")

    iam.get_paginator.side_effect = get_paginator
    iam.get_policy.return_value = {"Policy": {"DefaultVersionId": "v1"}}
    iam.get_policy_version.return_value = {"PolicyVersion": {"Document": policy_doc}}
    iam.list_users.return_value = {"Users": []}
    iam.list_roles.return_value = {"Roles": []}

    s3 = MagicMock()
    s3.list_buckets.return_value = {"Buckets": [{"Name": "demo-pii-bucket"}]}
    s3.get_bucket_location.return_value = {"LocationConstraint": "ap-south-1"}
    s3.get_bucket_encryption.side_effect = Exception("NoEncryption")
    s3.get_public_access_block.side_effect = Exception("NoPAB")
    s3.get_bucket_versioning.return_value = {"Status": "Suspended"}
    s3.get_bucket_logging.return_value = {}
    s3.get_bucket_lifecycle_configuration.return_value = {"Rules": []}
    s3.get_bucket_tagging.return_value = {"TagSet": [{"Key": "contains_personal_data", "Value": "true"}]}

    ec2 = MagicMock()
    ec2.describe_security_groups.return_value = {"SecurityGroups": []}
    rds = MagicMock()
    rds.describe_db_instances.return_value = {"DBInstances": []}
    ct = MagicMock()
    ct.describe_trails.return_value = {"trailList": []}

    clients = {"sts": sts, "iam": iam, "s3": s3, "ec2": ec2, "rds": rds, "cloudtrail": ct}
    session = MagicMock()
    session.client.side_effect = lambda name, **kwargs: clients[name]
    return session, clients


def test_aws_scanner_blocks_forbidden_data_plane_permissions():
    bad_policy = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": ["s3:GetObject", "s3:ListAllMyBuckets"], "Resource": "*"}],
    }
    session, clients = _make_mock_aws_session(bad_policy)
    with pytest.raises(IamGuardBlockedError) as exc:
        scan_aws_account(session=session, region="ap-south-1")
    assert "s3:GetObject" in exc.value.forbidden
    # Must fail BEFORE calling s3.list_buckets or ec2/rds
    clients["s3"].list_buckets.assert_not_called()
    clients["ec2"].describe_security_groups.assert_not_called()


def test_aws_scanner_succeeds_with_control_plane_only_permissions():
    clean_policy = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": ["s3:ListAllMyBuckets", "s3:GetBucket*", "ec2:Describe*"], "Resource": "*"}],
    }
    session, clients = _make_mock_aws_session(clean_policy)
    res = scan_aws_account(session=session, region="ap-south-1")
    assert res["source_type"] == "aws"
    assert res["account_id"] == "111122223333"
    clients["s3"].list_buckets.assert_called_once()
    rule_ids = {f["rule_id"] for f in res["raw_findings"]}
    assert "dpdp.rule6a" in rule_ids
    assert "dpdp.rule6_public_exposure" in rule_ids


# -----------------------------------------------------------------------------
# 3. DUAL-MODE API SERVER INTEGRATION TESTS (cloud_showcase vs local_agent)
# -----------------------------------------------------------------------------

@pytest.fixture()
def cloud_server(monkeypatch):
    monkeypatch.setenv("ARGUS_RUNTIME_MODE", "cloud_showcase")
    STATE.reset()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), ArgusAppHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()
    srv.server_close()


@pytest.fixture()
def local_server(tmp_path, monkeypatch):
    monkeypatch.setenv("ARGUS_RUNTIME_MODE", "local_agent")
    monkeypatch.setenv("ARGUS_DATA_DIR", str(tmp_path / "local_data"))
    old_store = STATE.store
    STATE.store = LocalStateStore(tmp_path / "local_data" / "argus_state.db")
    STATE.reset()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), ArgusAppHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}", tmp_path
    srv.shutdown()
    srv.server_close()
    STATE.store = old_store
    STATE.reset()


def test_cloud_showcase_endpoints_and_local_blocks(cloud_server):
    code, _, health = _request_json(f"{cloud_server}/api/health")
    assert code == 200
    assert health["runtime_mode"] == "cloud_showcase"
    assert health["can_scan_local"] is False
    assert health["m2_certified"] is False

    code, _, rel = _request_json(f"{cloud_server}/api/releases")
    assert code == 200
    assert rel["latest_version"] == "v2.0.0"
    assert rel["desktop_build_status"] in ("PLACEHOLDER_PENDING_BUILD", "READY", "PARTIAL")
    if rel["desktop_build_status"] == "READY":
        for art in rel["current_release"]["artifacts"]:
            assert art["download_ready"] is True
            assert len(art["sha256"]) == 64
            assert art["download_url"]
    else:
        assert rel["current_release"]["artifacts"][0]["download_ready"] is False

    code, _, bench = _request_json(f"{cloud_server}/api/benchmarks")
    assert code == 200
    assert bench["headline_metrics"]["oof_pass_at_1_pct"] == 94.48
    assert bench["headline_metrics"]["clean_unseen_clusters"] == 150
    assert bench["m2_ltt_governance"]["certified"] is False

    code, _, docs = _request_json(f"{cloud_server}/api/docs")
    assert code == 200
    assert len(docs["dpdp_rule_matrix"]) >= 6

    # Local-only routes MUST return 403 Forbidden in cloud_showcase mode
    for method, ep, body in [
        ("GET", "/api/local/status", None),
        ("GET", "/api/local/aws-profiles", None),
        ("GET", "/api/local/models/discovered", None),
        ("GET", "/api/local/models/pull-status", None),
        ("POST", "/api/local/models/pull", {"model": "qwen3.5:4b"}),
        ("POST", "/api/local/ollama/start", {}),
        ("POST", "/api/local/dialog/folder", {}),
        ("POST", "/api/local/dialog/file", {}),
        ("POST", "/api/scan/terraform", {"directory": str(REPO_ROOT)}),
        ("POST", "/api/scan/github", {"repoUrl": "https://github.com/org/repo.git"}),
        ("POST", "/api/scan/aws", {"profile": "default"}),
        ("POST", "/api/approvals/F-b42cc0f7/export-patch", {}),
        ("GET", "/api/audit/export", None),
    ]:
        code, _, err = _request_json(f"{cloud_server}{ep}", method=method, data=body)
        assert code == HTTPStatus.FORBIDDEN
        assert err["code"] == "LOCAL_ENGINE_REQUIRED"

    # New SPA routes serve index.html
    for route in ["/results", "/docs", "/downloads"]:
        with urllib.request.urlopen(f"{cloud_server}{route}", timeout=10) as resp:
            assert resp.status == 200
            assert "<!doctype html>" in resp.read().decode("utf-8").lower()


def test_local_agent_cors_pna_and_terraform_scan_and_export(local_server):
    base_url, tmp_path = local_server

    # Private Network Access preflight from EC2 portal origin
    req = urllib.request.Request(f"{base_url}/api/local/status", method="OPTIONS")
    req.add_header("Origin", "http://13.201.224.53")
    req.add_header("Access-Control-Request-Private-Network", "true")
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 204
        assert resp.headers.get("Access-Control-Allow-Origin") == "http://13.201.224.53"
        assert resp.headers.get("Access-Control-Allow-Private-Network") == "true"

    code, _, loc = _request_json(f"{base_url}/api/local/status")
    assert code == 200
    assert loc["runtime_mode"] == "local_agent"
    assert loc["can_scan_local"] is True
    assert loc["m2_status"]["certified"] is False

    # Missing directory -> 400
    code, _, bad = _request_json(f"{base_url}/api/scan/terraform", method="POST", data={"directory": str(tmp_path / "missing")})
    assert code == 400
    assert "error" in bad

    # Valid Terraform directory scan -> updates findings, graph, receipts, persists to SQLite
    tf_dir = tmp_path / "sample_tf"
    tf_dir.mkdir()
    (tf_dir / "main.tf").write_text(SAMPLE_TF, encoding="utf-8")

    code, _, scan = _request_json(
        f"{base_url}/api/scan/terraform",
        method="POST",
        data={"directory": str(tf_dir), "region": "ap-south-1", "orgName": "Campus Cloud Demo"},
    )
    assert code == 200
    assert scan["success"] is True
    assert scan["findings_count"] >= 6
    assert scan["nodes_count"] >= 6

    code, _, findings = _request_json(f"{base_url}/api/findings")
    assert code == 200
    assert len(findings) == scan["findings_count"]
    fid = findings[0]["finding_id"]

    # Export .patch
    code, _, patch_res = _request_json(f"{base_url}/api/approvals/{fid}/export-patch", method="POST", data={})
    assert code == 200
    assert patch_res["success"] is True
    assert Path(patch_res["patch_path"]).exists()

    # Export DPDP Audit ZIP
    with urllib.request.urlopen(f"{base_url}/api/audit/export", timeout=10) as resp:
        assert resp.status == 200
        assert "application/zip" in resp.headers.get("Content-Type", "")
        zbytes = resp.read()
    with zipfile.ZipFile(io.BytesIO(zbytes)) as zf:
        names = set(zf.namelist())
        assert {"audit_manifest.json", "findings.json", "compliance_dpdp.json", "privacy_receipts.json"} <= names


def test_cloud_showcase_works_with_zero_optional_deps(monkeypatch):
    """Simulate AWS EC2 Free Tier stdlib-only runtime (no local_engine/airlock/ollama/gate)."""
    import backend.api_server as srv_mod

    monkeypatch.setenv("ARGUS_RUNTIME_MODE", "cloud_showcase")
    monkeypatch.setattr(srv_mod, "AIRLOCK_AVAILABLE", False)
    monkeypatch.setattr(srv_mod, "MODEL_AVAILABLE", False)
    monkeypatch.setattr(srv_mod, "GATE_AVAILABLE", False)
    monkeypatch.setattr(srv_mod, "LOCAL_ENGINE_AVAILABLE", False)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), ArgusAppHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{port}"
        for ep in ["/api/health", "/api/releases", "/api/benchmarks", "/api/docs", "/api/architecture", "/api/overview"]:
            code, _, payload = _request_json(f"{base}{ep}")
            assert code == 200
            assert payload is not None
        code, _, pipe = _request_json(f"{base}/api/pipeline/run", method="POST", data={"scenario": "public"})
        assert code == 200
        assert pipe["success"] is True
        assert pipe["receipt"]["leaked_to_network"] is False
    finally:
        srv.shutdown()
        srv.server_close()


def test_builtin_sample_dpdp_infra_scan_and_budget_table():
    sample_dir = REPO_ROOT / "testbeds" / "sample_dpdp_infra"
    assert sample_dir.exists()
    scan_res = scan_terraform_directory(str(sample_dir), approved_regions=["ap-south-1"])
    assert len(scan_res["raw_findings"]) >= 5
    pipe = run_local_scan_pipeline(scan_res, region="ap-south-1")
    interdiction = pipe["interdiction"]
    budget_table = interdiction.get("budget_table", {})
    assert {"0", "1", "2", "3", "6", "10"} <= set(budget_table.keys())
    assert interdiction["baseline_likelihood"] > 0.0
    assert interdiction["residual_likelihood"] < interdiction["baseline_likelihood"]
    assert len(interdiction["selected_fixes"]) >= 1
    assert len(interdiction["edges_interdicted"]) >= 1
    assert "arn:aws:" not in interdiction["selected_fixes"][0]["edge_cut"]
    assert any(e.get("isAttackPath") for e in pipe["graph"]["edges"])
    assert len(budget_table["1"]["selected_fixes"]) <= 1
    assert len(budget_table["6"]["selected_fixes"]) >= len(budget_table["1"]["selected_fixes"])
    assert pipe["m2_status"]["certified"] is False
    assert len(pipe["findings"]) >= 5
    for f in pipe["findings"]:
        assert f["m2_confidence"] is None
        assert f["confidence"] == "n/a"
        assert f["certified"] is False
        assert f["auto_apply_status"] in ("NEEDS_APPROVAL", "ESCALATED")


def test_terraform_var_resolution_sg_rule_and_hcl_sanitization(tmp_path):
    tf_dir = tmp_path / "var_test"
    tf_dir.mkdir()
    (tf_dir / "main.tf").write_text(
        '''
variable "known_bucket" {
  default = "resolved-dpdp-bucket"
}

resource "aws_s3_bucket" "with_default" {
  bucket = var.known_bucket
}

resource "aws_s3_bucket" "unresolved_var" {
  bucket = "${var.dynamic_bucket}"
}

resource "aws_vpc_security_group_ingress_rule" "open_ssh" {
  security_group_id = "sg-01"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 22
  ip_protocol       = "tcp"
  to_port           = 22
}
''',
        encoding="utf-8",
    )
    scan_res = scan_terraform_directory(str(tf_dir))
    rnames = [f["resource_name"] for f in scan_res["raw_findings"]]
    assert any(r == "resolved-dpdp-bucket" for r in rnames)
    assert any(r == "unresolved_var" for r in rnames)
    assert all("${var." not in r for r in rnames)
    assert any(
        f["rule_id"] in ("dpdp.rule6_sg_open_ingress", "cis.sg_open_ingress")
        for f in scan_res["raw_findings"]
    )

    pipe = run_local_scan_pipeline(scan_res, region="ap-south-1")
    for finding in pipe["findings"]:
        out_path = export_finding_patch(finding, exports_dir=tmp_path / "patches")
        patch_txt = out_path.read_text(encoding="utf-8")
        assert "${" not in patch_txt


def test_interdiction_budget_query_param_slices_both_modes(cloud_server, local_server):
    for budget in (1, 5):
        code, _, data = _request_json(f"{cloud_server}/api/interdiction?budget={budget}")
        assert code == 200
        assert data["budget"] == budget
        assert len(data["selected_fixes"]) <= budget

    local_url, tmp_path = local_server
    tf_dir = tmp_path / "budget_tf"
    tf_dir.mkdir()
    (tf_dir / "main.tf").write_text(SAMPLE_TF, encoding="utf-8")
    code, _, scan = _request_json(
        f"{local_url}/api/scan/terraform",
        method="POST",
        data={"directory": str(tf_dir), "region": "ap-south-1"},
    )
    assert code == 200 and scan["success"] is True

    code1, _, b1 = _request_json(f"{local_url}/api/interdiction?budget=1")
    code4, _, b4 = _request_json(f"{local_url}/api/interdiction?budget=4")
    assert code1 == 200 and code4 == 200
    assert b1["budget"] == 1
    assert b4["budget"] == 4
    assert len(b1["selected_fixes"]) <= 1
    assert len(b4["selected_fixes"]) >= len(b1["selected_fixes"])


def test_local_agent_pipeline_run_enforces_m2_uncertified_guardrail(local_server):
    local_url, _ = local_server
    code, _, pipe = _request_json(
        f"{local_url}/api/pipeline/run",
        method="POST",
        data={"scenario": "public"},
    )
    assert code == 200
    assert pipe["success"] is True
    assert pipe["runtime_mode"] == "local_agent"
    code_f, _, findings = _request_json(f"{local_url}/api/findings")
    assert code_f == 200 and len(findings) >= 1
    latest = findings[0]
    assert latest["certified"] is False
    assert latest["auto_apply_status"] == "NEEDS_APPROVAL"
    assert latest["m2_confidence"] is None
    assert latest["confidence"] == "n/a"


def test_deploy_dashboard_local_binds_loopback_by_default(monkeypatch):
    import backend.api_server as srv_mod
    import deploy_dashboard

    calls = []
    monkeypatch.setattr(srv_mod, "run_server", lambda host=None, port=8000: calls.append((host, port)))

    # Record original env value in pytest monkeypatch BEFORE deploy_dashboard mutates os.environ
    monkeypatch.setenv("ARGUS_RUNTIME_MODE", "cloud_showcase")
    monkeypatch.delenv("ARGUS_RUNTIME_MODE", raising=False)
    monkeypatch.setattr(sys, "argv", ["deploy_dashboard.py", "--local"])
    deploy_dashboard.main()

    monkeypatch.setenv("ARGUS_RUNTIME_MODE", "cloud_showcase")
    monkeypatch.setattr(sys, "argv", ["deploy_dashboard.py", "80"])
    deploy_dashboard.main()

    assert calls == [("127.0.0.1", 8742), ("0.0.0.0", 80)]


# -----------------------------------------------------------------------------
# 4. WINDOWS .EXE PACKAGING READINESS, GITHUB REPO, GGUF & TFVARS TESTS
# -----------------------------------------------------------------------------

def test_terraform_scanner_tfvars_data_policy_inline_role_and_s3_acl(tmp_path):
    tf_dir = tmp_path / "company_tf"
    sub = tf_dir / "modules" / "storage"
    sub.mkdir(parents=True)

    (tf_dir / "variables.tf").write_text(
        '''
variable "env" {
  default = "dev"
}
variable "bucket_suffix" {
  default = "default-suffix"
}
''',
        encoding="utf-8",
    )
    (tf_dir / "terraform.tfvars").write_text(
        '''
env = "prod"
bucket_suffix = "citizen-kyc-vault"
''',
        encoding="utf-8",
    )
    (sub / "main.tf").write_text(
        '''
resource "aws_s3_bucket" "kyc" {
  bucket = "${var.env}-${var.bucket_suffix}"
}

resource "aws_s3_bucket_public_access_block" "kyc_pab" {
  bucket                  = aws_s3_bucket.kyc.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_acl" "kyc_acl" {
  bucket = aws_s3_bucket.kyc.id
  acl    = "public-read"
}

resource "aws_iam_role" "worker" {
  name = "worker-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { AWS = "arn:aws:iam::local:user/ci" } }]
  })
}

data "aws_iam_policy_document" "wildcard_doc" {
  statement {
    sid       = "FullStar"
    effect    = "Allow"
    actions   = ["*"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "worker_inline" {
  name   = "worker-inline-admin"
  role   = aws_iam_role.worker.name
  policy = data.aws_iam_policy_document.wildcard_doc.json
}
''',
        encoding="utf-8",
    )

    res = scan_terraform_directory(tf_dir)
    assert any(p.endswith("terraform.tfvars") for p in res["tfvars_loaded"])
    names = {f["resource_name"] for f in res["raw_findings"]}
    assert "prod-citizen-kyc-vault" in names
    rule_ids = {f["rule_id"] for f in res["raw_findings"]}
    assert "dpdp.rule6_public_exposure" in rule_ids
    assert "cis.iam_no_full_admin" in rule_ids

    # Inline policy statement must attach to the IAM role in the Cartography session
    assert any(
        st.get("pid") == "arn:aws:iam::local:role/worker-role" and "*" in st.get("action", [])
        for st in res["session"].statements
    )


def test_register_local_gguf_is_exe_safe_and_synthesizes_without_base(tmp_path, monkeypatch):
    import subprocess
    from local_engine import ollama_manager

    monkeypatch.setenv("ARGUS_DATA_DIR", str(tmp_path / "argus_data"))
    gguf_file = tmp_path / "Qwen3.5-4B-SFT.Q4_K_M.gguf"
    gguf_file.write_bytes(b"GGUF" + b"\x00" * 64)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        # Fail `ollama show qwen3.5:4b --modelfile` to prove base model is NOT required
        if len(cmd) >= 2 and cmd[1] == "show":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="Error: model not found")
        if len(cmd) >= 2 and cmd[1] == "create":
            return subprocess.CompletedProcess(cmd, 0, stdout="success\n", stderr="")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    monkeypatch.setattr(ollama_manager, "find_ollama_binary", lambda: r"C:\Fake\ollama.exe")
    monkeypatch.setattr(ollama_manager.subprocess, "run", fake_run)

    res = ollama_manager.register_local_gguf(gguf_file, model_name="argus-m1-sft", base_model="qwen3.5:4b")
    assert res["success"] is True
    assert res["template_source"] == "synthesized_qwen35_template"
    modelfile_path = Path(res["modelfile_path"])
    assert modelfile_path.exists()
    mf_text = modelfile_path.read_text(encoding="utf-8")
    assert f"FROM {gguf_file.resolve()}" in mf_text
    assert "RENDERER qwen3.5" in mf_text
    assert "PARSER qwen3.5" in mf_text

    # Must NEVER invoke sys.executable -m (which recursively launches ARGUS.exe in PyInstaller)
    assert all(cmd[0] != sys.executable for cmd in calls)
    assert any(cmd[:3] == [r"C:\Fake\ollama.exe", "create", "argus-m1-sft"] for cmd in calls)

    # Validation edge cases
    with pytest.raises(ValueError):
        ollama_manager.register_local_gguf(gguf_file, model_name="bad name;rm")
    bad_ext = tmp_path / "not_gguf.bin"
    bad_ext.write_bytes(b"123")
    with pytest.raises(ValueError):
        ollama_manager.register_local_gguf(bad_ext, model_name="argus-m1-sft")
    with pytest.raises(FileNotFoundError):
        ollama_manager.register_local_gguf(tmp_path / "missing.gguf", model_name="argus-m1-sft")


def test_discover_local_ggufs_and_pull_validation(tmp_path, monkeypatch):
    from local_engine import ollama_manager

    scan_dir = tmp_path / "models"
    scan_dir.mkdir()
    (scan_dir / "Qwen3.5-4B.Q4_K_M.gguf").write_bytes(b"A" * 2048)
    (scan_dir / "argus-m1-rft-v2.Q4_K_M.gguf").write_bytes(b"B" * 4096)
    (scan_dir / "empty.gguf").write_bytes(b"")
    (scan_dir / "readme.txt").write_text("ignore", encoding="utf-8")

    found = ollama_manager.discover_local_ggufs(extra_dirs=[scan_dir])
    names = {g["name"]: g for g in found}
    assert "Qwen3.5-4B.Q4_K_M.gguf" in names
    assert "argus-m1-rft-v2.Q4_K_M.gguf" in names
    assert "empty.gguf" not in names
    assert names["argus-m1-rft-v2.Q4_K_M.gguf"]["suggested_model_name"] == "argus-m1-rft"
    assert names["Qwen3.5-4B.Q4_K_M.gguf"]["suggested_model_name"] == "argus-m1-sft"

    with pytest.raises(ValueError):
        ollama_manager.start_pull_ollama_model("bad model;whoami")
    monkeypatch.setattr(ollama_manager, "check_ollama_status", lambda endpoint=ollama_manager.DEFAULT_OLLAMA_URL, timeout=1.5: {"running": False, "error": "offline"})
    with pytest.raises(RuntimeError):
        ollama_manager.start_pull_ollama_model("hf.co/user/argus-m1-sft:Q4_K_M")


def test_list_aws_cli_profiles_never_returns_secrets(tmp_path):
    from local_engine.repo_manager import list_aws_cli_profiles

    aws_dir = tmp_path / ".aws"
    aws_dir.mkdir()
    (aws_dir / "credentials").write_text(
        "[default]\naws_access_key_id = AKIASECRETKEY123456\naws_secret_access_key = SUPER_SECRET_DO_NOT_LEAK\n\n"
        "[argus-ro]\naws_access_key_id = AKIAOTHERKEY999999\naws_secret_access_key = ANOTHER_SECRET_VALUE\n",
        encoding="utf-8",
    )
    (aws_dir / "config").write_text(
        "[default]\nregion = ap-south-1\n\n[profile staging-audit]\nregion = ap-south-2\n",
        encoding="utf-8",
    )

    profiles = list_aws_cli_profiles(aws_dir=aws_dir)
    assert profiles == ["default", "argus-ro", "staging-audit"]
    serialized = json.dumps(profiles)
    assert "AKIASECRETKEY" not in serialized
    assert "SUPER_SECRET" not in serialized
    assert "ANOTHER_SECRET" not in serialized


def test_clone_terraform_repo_validation_and_bare_git_scan(tmp_path, local_server):
    import subprocess
    from local_engine.repo_manager import clone_terraform_repo, validate_git_url

    base_url, _ = local_server

    # Reject flag injection, invalid schemes, and traversal
    for bad in ["", "--upload-pack=calc", "ftp://example.com/a.git", "https://github.com/only-host", "https://x.com/a.git;calc"]:
        with pytest.raises(ValueError):
            validate_git_url(bad)

    assert validate_git_url("https://github.com/Prabhav-020108/ARGUS.git").startswith("https://")
    assert validate_git_url("git@github.com:Prabhav-020108/ARGUS.git").startswith("git@")

    # Create a real local bare git repo with Terraform inside a subdir
    src_repo = tmp_path / "src_repo"
    (src_repo / "infra").mkdir(parents=True)
    (src_repo / "infra" / "main.tf").write_text(SAMPLE_TF, encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=src_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "ci@argus.local"], cwd=src_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "ARGUS CI"], cwd=src_repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=src_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=src_repo, check=True, capture_output=True)

    bare_repo = tmp_path / "remote.git"
    subprocess.run(["git", "clone", "--bare", str(src_repo), str(bare_repo)], check=True, capture_output=True)
    file_url = bare_repo.resolve().as_uri()

    # Subpath traversal must be blocked
    with pytest.raises(ValueError):
        clone_terraform_repo(file_url, subpath="../outside", dest_root=tmp_path / "clones")

    cloned = clone_terraform_repo(file_url, subpath="infra", dest_root=tmp_path / "clones")
    assert cloned["tf_count"] >= 1
    assert Path(cloned["scan_dir"]).exists()

    # Exercise /api/scan/github end-to-end against local_server
    code, _, gh_res = _request_json(
        f"{base_url}/api/scan/github",
        method="POST",
        data={"repoUrl": file_url, "subpath": "infra", "region": "ap-south-1"},
    )
    assert code == 200
    assert gh_res["success"] is True
    assert gh_res["findings_count"] >= 6

    # Verify /api/local/aws-profiles and /api/local/models/discovered in local_agent
    code_p, _, prof_res = _request_json(f"{base_url}/api/local/aws-profiles")
    assert code_p == 200 and isinstance(prof_res["profiles"], list)
    code_d, _, disc_res = _request_json(f"{base_url}/api/local/models/discovered")
    assert code_d == 200 and "ggufs" in disc_res


def test_downloads_files_streaming_and_traversal_protection(cloud_server, tmp_path, monkeypatch):
    import backend.api_server as srv_mod

    fake_files_dir = tmp_path / "rel_files"
    fake_files_dir.mkdir()
    sample_bin = fake_files_dir / "ARGUS-Test-Setup.exe"
    sample_bin.write_bytes(b"MZ" + b"ARGUS" * 1024)
    monkeypatch.setattr(srv_mod, "RELEASES_FILES_DIR", fake_files_dir)

    with urllib.request.urlopen(f"{cloud_server}/downloads/files/ARGUS-Test-Setup.exe", timeout=10) as resp:
        assert resp.status == 200
        assert "attachment" in resp.headers.get("Content-Disposition", "")
        assert resp.read() == sample_bin.read_bytes()

    # Missing file -> 404; traversal -> 400/404 (never serves files outside RELEASES_FILES_DIR)
    for bad_path in ["/downloads/files/does-not-exist.exe", "/downloads/files/..%2Fmanifest.json", "/downloads/files/sub/x.exe"]:
        code, _, _ = _request_json(f"{cloud_server}{bad_path}")
        assert code in (400, 404)


def test_desktop_main_smoke_test_function(tmp_path):
    from local_engine.desktop_main import run_smoke_test

    smoke_log = tmp_path / "smoke.log"
    rc = run_smoke_test(smoke_log=str(smoke_log))
    assert rc == 0
    assert "ARGUS DESKTOP SMOKE TEST PASSED" in smoke_log.read_text(encoding="utf-8")


def test_terraform_count_indexed_refs_locals_az_and_composite_unresolved(tmp_path):
    tf_dir = tmp_path / "count_az_tf"
    tf_dir.mkdir()
    (tf_dir / "main.tf").write_text(
        '''
provider "aws" {
  region = "ap-south-1"
}

locals {
  compliant_name = "compliant-pii-vault"
}

resource "aws_s3_bucket" "this" {
  count  = 1
  bucket = local.compliant_name
}

resource "aws_s3_bucket_public_access_block" "this" {
  count                   = 1
  bucket                  = aws_s3_bucket.this[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  count  = 1
  bucket = aws_s3_bucket.this[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_versioning" "this" {
  count  = 1
  bucket = aws_s3_bucket.this[0].id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_logging" "this" {
  count         = 1
  bucket        = aws_s3_bucket.this[0].id
  target_bucket = "central-logs"
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  count  = 1
  bucket = aws_s3_bucket.this[0].id
  rule {
    id     = "expire"
    status = "Enabled"
    expiration { days = 180 }
  }
}

resource "aws_s3_bucket" "unresolved_composite" {
  bucket = "${var.missing_prefix}-citizen-pii"
}

resource "aws_db_instance" "sg_db" {
  identifier        = "mydb"
  availability_zone = "ap-southeast-1a"
  storage_encrypted = false
}
''',
        encoding="utf-8",
    )

    res = scan_terraform_directory(tf_dir, approved_regions=["ap-south-1"])
    by_name = {}
    for f in res["raw_findings"]:
        by_name.setdefault(f["resource_name"], []).append(f)

    # Compliant count[0] bucket must produce ZERO false-positive findings
    assert "compliant-pii-vault" not in by_name
    # Composite unresolved ${var.missing_prefix}-citizen-pii must fall back cleanly without leaking ${
    assert all("${" not in f["resource_name"] for f in res["raw_findings"])
    assert "unresolved_composite" in by_name
    # ap-southeast-1a must strip trailing zone letter cleanly, not truncate to ap-southea
    assert "mydb" in by_name
    assert by_name["mydb"][0]["attributes"]["region"] == "ap-southeast-1"


def test_aws_scanner_propagates_account_id_and_inline_admin_roles(tmp_path, monkeypatch):
    monkeypatch.setenv("ARGUS_DATA_DIR", str(tmp_path / "aws_data"))
    clean_policy = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": ["s3:ListAllMyBuckets", "ec2:Describe*", "iam:List*"], "Resource": "*"}],
    }
    session, clients = _make_mock_aws_session(clean_policy)
    clients["iam"].list_roles.return_value = {
        "Roles": [
            {
                "Arn": "arn:aws:iam::111122223333:role/ci-admin",
                "RoleName": "ci-admin",
                "AssumeRolePolicyDocument": {"Statement": []},
            }
        ]
    }
    clients["iam"].list_attached_role_policies.return_value = {
        "AttachedPolicies": [
            {"PolicyArn": "arn:aws:iam::aws:policy/AdministratorAccess", "PolicyName": "AdministratorAccess"}
        ]
    }
    clients["iam"].list_role_policies.return_value = {"PolicyNames": ["InlineWildcard"]}
    clients["iam"].get_role_policy.return_value = {
        "PolicyDocument": {"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}
    }

    scan_res = scan_aws_account(session=session, region="ap-south-1")
    assert scan_res["account_id"] == "111122223333"
    assert any(f["rule_id"] == "cis.iam_no_full_admin" for f in scan_res["raw_findings"])

    pipe = run_local_scan_pipeline(scan_res, region="ap-south-1")
    assert pipe["account_id"] == "111122223333"
    mgr = StateManager(persist_store=LocalStateStore(tmp_path / "aws_state.db"))
    mgr.apply_scan_payload(pipe, org_name="Acme AWS", region="ap-south-1")
    assert mgr.tenant["aws_account_id"] == "111122223333"


def test_github_tree_url_normalization_and_desktop_instance_probe(local_server):
    from local_engine.desktop_main import _is_instance_running
    from local_engine.repo_manager import _normalize_github_browser_url

    base_repo, branch, subpath = _normalize_github_browser_url(
        "https://github.com/acme/cloud-infra/tree/main/terraform/aws",
        None,
        None,
    )
    assert base_repo == "https://github.com/acme/cloud-infra.git"
    assert branch == "main"
    assert subpath == "terraform/aws"

    base_url, _ = local_server
    port = int(base_url.rsplit(":", 1)[1])
    assert _is_instance_running(port) is True


def test_ollama_pull_normalization_local_argus_tags_and_start_endpoint(tmp_path, local_server, monkeypatch):
    import backend.api_server as srv_mod
    from local_engine import ollama_manager
    from local_engine.repo_manager import _resolve_initial_dir, pick_local_path

    base_url, _ = local_server

    assert ollama_manager.normalize_model_ref('  ollama pull "qwen3.5:4b"  ') == "qwen3.5:4b"
    assert ollama_manager.normalize_model_ref("ollama run argus-m1-sft") == "argus-m1-sft"

    # Case 1: local argus-m1-sft already registered -> verifies locally without 404 from registry.ollama.ai
    monkeypatch.setattr(
        ollama_manager,
        "check_ollama_status",
        lambda endpoint=ollama_manager.DEFAULT_OLLAMA_URL, timeout=1.5: {
            "running": True,
            "ollama_installed": True,
            "models": ["argus-m1-sft:latest"],
        },
    )
    snap = ollama_manager.start_pull_ollama_model("ollama pull argus-m1-sft")
    assert snap["model"] == "argus-m1-sft"
    for _ in range(40):
        st = ollama_manager.get_pull_status()
        if not st["active"]:
            break
        time.sleep(0.05)
    assert st["success"] is True
    assert "verified argus-m1-sft ready" in st["status"]

    # Case 2: local argus-m1-sft not yet in Ollama, but matching .gguf on disk -> auto-registers it
    gguf_file = tmp_path / "Qwen3.5-4B.Q4_K_M.gguf"
    gguf_file.write_bytes(b"GGUF" + b"\x00" * 128)
    monkeypatch.setattr(
        ollama_manager,
        "check_ollama_status",
        lambda endpoint=ollama_manager.DEFAULT_OLLAMA_URL, timeout=1.5: {
            "running": True,
            "ollama_installed": True,
            "models": [],
        },
    )
    monkeypatch.setattr(
        ollama_manager,
        "discover_local_ggufs",
        lambda: [{"name": gguf_file.name, "path": str(gguf_file), "size_bytes": 132, "suggested_model_name": "argus-m1-sft"}],
    )
    reg_calls = []
    monkeypatch.setattr(
        ollama_manager,
        "register_local_gguf",
        lambda p, model_name="argus-m1-sft", **kw: reg_calls.append((p, model_name)) or {"success": True, "model_name": model_name},
    )
    ollama_manager.start_pull_ollama_model("argus-m1-sft")
    for _ in range(40):
        st2 = ollama_manager.get_pull_status()
        if not st2["active"]:
            break
        time.sleep(0.05)
    assert st2["success"] is True
    assert reg_calls == [(str(gguf_file), "argus-m1-sft")]

    # Case 3: local argus-m1-rft missing both in Ollama and on disk -> clear actionable error
    monkeypatch.setattr(ollama_manager, "discover_local_ggufs", lambda: [])
    ollama_manager.start_pull_ollama_model("argus-m1-rft")
    for _ in range(40):
        st3 = ollama_manager.get_pull_status()
        if not st3["active"]:
            break
        time.sleep(0.05)
    assert st3["success"] is False
    assert "Browse .gguf" in (st3["error"] or "")

    # /api/local/ollama/start endpoint (200 when running, 503 when offline)
    monkeypatch.setattr(srv_mod, "ensure_ollama_running", lambda endpoint="http://127.0.0.1:11434", start_timeout=8.0: {"running": True, "version": "0.40.18", "models": []})
    code, _, body = _request_json(f"{base_url}/api/local/ollama/start", method="POST", data={})
    assert code == 200 and body["success"] is True

    monkeypatch.setattr(srv_mod, "ensure_ollama_running", lambda endpoint="http://127.0.0.1:11434", start_timeout=8.0: {"running": False, "error": "not running"})
    code_off, _, _ = _request_json(f"{base_url}/api/local/ollama/start", method="POST", data={})
    assert code_off == 503

    # Native dialog validation & headless safety
    with pytest.raises(ValueError):
        pick_local_path(mode="invalid")
    monkeypatch.setenv("ARGUS_HEADLESS", "1")
    assert pick_local_path(mode="gguf") is None
    assert _resolve_initial_dir("gguf", str(gguf_file)) == str(tmp_path.resolve())


def test_ollama_pull_multilayer_monotonic_progress_and_argus_m1_alias(monkeypatch):
    from local_engine import ollama_manager

    # 1. Generic "argus-m1" alias must resolve locally to argus-m1-sft without hitting Ollama Hub 404
    monkeypatch.setattr(
        ollama_manager,
        "check_ollama_status",
        lambda endpoint=ollama_manager.DEFAULT_OLLAMA_URL, timeout=1.5: {
            "running": True,
            "ollama_installed": True,
            "models": ["argus-m1-sft:latest"],
        },
    )
    ollama_manager.start_pull_ollama_model("ollama pull argus-m1")
    for _ in range(40):
        st_alias = ollama_manager.get_pull_status()
        if not st_alias["active"]:
            break
        time.sleep(0.05)
    assert st_alias["success"] is True
    assert "verified argus-m1-sft ready" in st_alias["status"]

    # 2. Multi-digest streaming pull must stay monotonic (never jump 100% -> 0% on a trailing metadata blob)
    seen_percents = []

    class FakeResp:
        status_code = 200
        text = ""

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_lines(self, decode_unicode=True):
            lines = [
                json.dumps({"status": "pulling manifest"}),
                json.dumps({"status": "pulling d1", "digest": "sha256:d1", "total": 1000, "completed": 500}),
                json.dumps({"status": "pulling d1", "digest": "sha256:d1", "total": 1000, "completed": 1000}),
                json.dumps({"status": "pulling d2", "digest": "sha256:d2", "total": 200, "completed": 0}),
                json.dumps({"status": "pulling d2", "digest": "sha256:d2", "total": 200, "completed": 200}),
                json.dumps({"status": "verifying sha256 digest"}),
                json.dumps({"status": "success"}),
            ]
            for ln in lines:
                yield ln
                seen_percents.append(ollama_manager.get_pull_status()["percent"])

    class FakeSess:
        trust_env = True

        def post(self, *args, **kwargs):
            return FakeResp()

    monkeypatch.setattr(ollama_manager.requests, "Session", lambda: FakeSess())
    ollama_manager.start_pull_ollama_model("qwen3.5:4b")
    for _ in range(40):
        st_multi = ollama_manager.get_pull_status()
        if not st_multi["active"]:
            break
        time.sleep(0.05)
    assert st_multi["success"] is True
    assert st_multi["percent"] == 100.0
    # Ensure monotonic non-decreasing progress across digests (e.g. 100% -> 83.3% regression is prevented)
    assert seen_percents == sorted(seen_percents)
    assert 50.0 in seen_percents
    assert seen_percents[-1] == 100.0





