"""Automated Integration & Unit Tests for ARGUS Backend API Engine
Verifies all REST API endpoints, real pipeline execution (Ollama + Airlock + Rego),
DPDP compliance state management, and SPA static routing.
"""

from __future__ import annotations

import json
import threading
import time
from http import HTTPStatus
from http.server import HTTPServer
from pathlib import Path
import urllib.request
import urllib.error

import pytest

# Add repo root
import sys
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.api_server import (
    ArgusAppHandler,
    StateManager,
    execute_pipeline_scenario,
    get_architecture_payload,
    STATE
)


class ServerContext:
    """Spins up a real ephemeral HTTP server on an available test port."""
    def __init__(self, port=8888):
        self.port = port
        self.server = None
        self.thread = None

    def start(self):
        self.server = HTTPServer(("127.0.0.1", self.port), ArgusAppHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        time.sleep(0.2)

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()


@pytest.fixture(scope="module")
def live_server():
    ctx = ServerContext(port=8899)
    ctx.start()
    yield f"http://127.0.0.1:8899"
    ctx.stop()


def fetch_json(url: str, method: str = "GET", data: dict = None, timeout: int = 30):
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    body = json.dumps(data).encode("utf-8") if data else None
    with urllib.request.urlopen(req, data=body, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


# -----------------------------------------------------------------------------
# 1. HEALTH & METADATA TESTS
# -----------------------------------------------------------------------------

def test_api_health(live_server):
    status, data = fetch_json(f"{live_server}/api/health")
    assert status == HTTPStatus.OK
    assert data["status"] == "healthy"
    assert "ARGUS" in data["platform"]
    assert data["zero_data_egress_enforced"] is True
    assert any("DPDP" in eng for eng in data["compliance_engines"])
    assert "argus-m1-sft (QLoRA 4B Q4_K_M)" in data["active_models"]


def test_api_architecture(live_server):
    status, data = fetch_json(f"{live_server}/api/architecture")
    assert status == HTTPStatus.OK
    assert "SwasthyaPay" in data["case_study"]["startup_name"]
    assert "ap-south-1" in data["case_study"]["cloud_region"]
    assert len(data["pipeline_layers"]) == 6
    assert len(data["deployment_options"]) >= 3


# -----------------------------------------------------------------------------
# 2. OVERVIEW & GRAPH TESTS
# -----------------------------------------------------------------------------

def test_api_overview_budget_variations(live_server):
    # Test default budget = 3
    status, data = fetch_json(f"{live_server}/api/overview?budget=3")
    assert status == HTTPStatus.OK
    assert "exposure" in data["headline"]
    assert data["interdiction"]["budget"] == 3
    assert data["region"] == "ap-south-1 (Mumbai, India)"
    assert len(data["waiting_findings"]) <= 4
    assert data["graph_summary"]["total_nodes"] > 0

    # Test budget = 1
    status, data1 = fetch_json(f"{live_server}/api/overview?budget=1")
    assert status == HTTPStatus.OK
    assert data1["interdiction"]["budget"] == 1


def test_api_graph(live_server):
    status, data = fetch_json(f"{live_server}/api/graph")
    assert status == HTTPStatus.OK
    nodes = data["nodes"]
    edges = data["edges"]
    assert len(nodes) >= 8
    assert len(edges) >= 8

    # Verify Entry point and Crown Jewel nodes
    entry_nodes = [n for n in nodes if n.get("isEntry")]
    crown_jewels = [n for n in nodes if n.get("isCrownJewel")]
    assert len(entry_nodes) >= 1
    assert len(crown_jewels) >= 1
    assert any(n["label"] == "customer-data" for n in crown_jewels)


# -----------------------------------------------------------------------------
# 3. COMPLIANCE & FINDINGS TESTS
# -----------------------------------------------------------------------------

def test_api_compliance_rules(live_server):
    status, rules = fetch_json(f"{live_server}/api/compliance")
    assert status == HTTPStatus.OK
    assert len(rules) >= 5
    rule_ids = [r["rule_id"] for r in rules]
    assert "dpdp.rule6_public_exposure" in rule_ids
    assert "dpdp.rule6_encryption" in rule_ids
    assert "dpdp.rule15_residency" in rule_ids

    # Rule 15 is a residency visibility flag
    r15 = next(r for r in rules if r["rule_id"] == "dpdp.rule15_residency")
    assert r15["is_visibility_flag"] is True
    assert r15["status"] == "FLAGGED"


def test_api_findings_and_detail(live_server):
    status, findings = fetch_json(f"{live_server}/api/findings")
    assert status == HTTPStatus.OK
    assert len(findings) >= 10

    first_id = findings[0]["finding_id"]
    status, detail = fetch_json(f"{live_server}/api/findings/{first_id}")
    assert status == HTTPStatus.OK
    assert detail["finding_id"] == first_id
    assert "patch_ir" in detail

    # Test non-existent finding returns 404
    req = urllib.request.Request(f"{live_server}/api/findings/non-existent-999")
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == HTTPStatus.NOT_FOUND


# -----------------------------------------------------------------------------
# 4. APPROVAL WORKFLOW & STATE TRANSITION TESTS
# -----------------------------------------------------------------------------

def test_api_approvals_and_action(live_server):
    # Fetch initial approvals
    status, pending = fetch_json(f"{live_server}/api/approvals")
    assert status == HTTPStatus.OK
    initial_pending_count = len(pending)
    assert initial_pending_count > 0

    target_finding = pending[0]["finding_id"]

    # Approve finding
    status, res = fetch_json(
        f"{live_server}/api/approvals/{target_finding}/approve",
        method="POST",
        data={"finding_id": target_finding}
    )
    assert status == HTTPStatus.OK
    assert res["success"] is True
    assert res["finding"]["auto_apply_status"] == "APPLIED"

    # Pending count should have decreased
    assert res["pending_count"] == initial_pending_count - 1

    # Cryptographic receipt should now exist for approved finding
    status, receipts = fetch_json(f"{live_server}/api/receipts")
    assert status == HTTPStatus.OK
    assert any(r["finding_id"] == target_finding for r in receipts)


# -----------------------------------------------------------------------------
# 5. LIVE PIPELINE ENGINE & SCENARIO EXECUTION
# -----------------------------------------------------------------------------

def test_live_pipeline_execution(live_server):
    # Run public bucket exposure scenario
    status, res = fetch_json(
        f"{live_server}/api/pipeline/run",
        method="POST",
        data={"scenario": "public"}
    )
    assert status == HTTPStatus.OK
    assert res["success"] is True
    assert res["scenario"] == "public"
    assert res["total_latency_ms"] > 0
    assert len(res["stages"]) == 6
    assert all(st["status"] in ("SUCCESS", "PASSED") for st in res["stages"])
    assert "patch_ir" in res
    assert "diff" in res
    assert res["receipt"]["leaked_to_network"] is False

    # Verify receipt is persisted to STATE.receipts
    rcpt_id = res["receipt"]["receipt_id"]
    status, receipts = fetch_json(f"{live_server}/api/receipts")
    assert status == HTTPStatus.OK
    assert any(r["receipt_id"] == rcpt_id for r in receipts)

    # Verify receipt can be fetched via /api/receipts/{id}
    status, single_rcpt = fetch_json(f"{live_server}/api/receipts/{rcpt_id}")
    assert status == HTTPStatus.OK
    assert single_rcpt["receipt_id"] == rcpt_id
    assert single_rcpt["finding_id"] == "F-LIVE-12"

    # Verify finding is persisted to STATE.findings
    status, findings = fetch_json(f"{live_server}/api/findings")
    assert status == HTTPStatus.OK
    live_f = next((f for f in findings if f["finding_id"] == "F-LIVE-12"), None)
    assert live_f is not None
    assert live_f["auto_apply_status"] == "APPROVED"
    assert live_f["status"] == "APPLIED"


def test_live_pipeline_admin_scenario(live_server):
    # Run IAM wildcard admin scenario - verifies OPA Rego gate evaluation (fix or escalate)
    status, res = fetch_json(
        f"{live_server}/api/pipeline/run",
        method="POST",
        data={"scenario": "admin"}
    )
    assert status == HTTPStatus.OK
    assert res["success"] is True
    assert res["scenario"] == "admin"

    # Verify that the finding is persisted to STATE
    status, findings = fetch_json(f"{live_server}/api/findings")
    assert status == HTTPStatus.OK
    admin_f = next((f for f in findings if f["finding_id"] == "F-LIVE-89"), None)
    assert admin_f is not None
    assert admin_f["status"] in ("APPLIED", "ESCALATED")
    assert admin_f["auto_apply_status"] in ("APPROVED", "ESCALATED")

    # Verify receipt is in /api/receipts
    status, receipts = fetch_json(f"{live_server}/api/receipts")
    assert status == HTTPStatus.OK
    assert any(r["finding_id"] == "F-LIVE-89" for r in receipts)


def test_receipt_detail_404(live_server):
    req = urllib.request.Request(f"{live_server}/api/receipts/non-existent-rcpt-999")
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == HTTPStatus.NOT_FOUND


def test_live_pipeline_logging_scenario(live_server):
    status, res = fetch_json(
        f"{live_server}/api/pipeline/run",
        method="POST",
        data={"scenario": "logging"}
    )
    assert status == HTTPStatus.OK
    assert res["success"] is True
    assert res["scenario"] == "logging"
    assert len(res["stages"]) == 6

    # Verify stage 4 generated logging patch
    s4 = next(s for s in res["stages"] if s["stage"] == 4)
    assert s4["status"] == "SUCCESS"
    assert "patch_ir" in s4
    ops = s4["patch_ir"]["ops"]
    assert any(op.get("attr") == "logging_enabled" for op in ops)


def test_live_pipeline_unknown_scenario_fallback(live_server):
    # Passing an unknown scenario key safely defaults to encryption without crashing
    status, res = fetch_json(
        f"{live_server}/api/pipeline/run",
        method="POST",
        data={"scenario": "unknown_scenario_xyz"}
    )
    assert status == HTTPStatus.OK
    assert res["success"] is True
    assert res["scenario"] == "encryption"
    assert len(res["stages"]) == 6


def test_pipeline_reset(live_server):
    status, res = fetch_json(f"{live_server}/api/pipeline/reset", method="POST")
    assert status == HTTPStatus.OK
    assert res["success"] is True

    # After reset, initial findings count is restored (live scenario findings removed)
    status, pending = fetch_json(f"{live_server}/api/approvals")
    assert len(pending) == 9

    status, findings = fetch_json(f"{live_server}/api/findings")
    assert not any(f["finding_id"] == "F-LIVE-12" for f in findings)
    assert not any(f["finding_id"] == "F-LIVE-89" for f in findings)


def test_tenant_connect_and_status(live_server):
    # Test GET /api/tenant/status
    status, t_initial = fetch_json(f"{live_server}/api/tenant/status")
    assert status == HTTPStatus.OK
    assert "SwasthyaPay" in t_initial["org_name"]
    assert t_initial["region"] == "ap-south-1"

    # Test POST /api/tenant/connect
    payload = {
        "orgName": "BharatHealth Care Pvt Ltd",
        "awsAccountId": "112233445566",
        "region": "ap-south-1",
        "iamRoleArn": "arn:aws:iam::112233445566:role/argus-audit-role",
        "externalId": "argus-tnt-bharat-01",
        "ollamaEndpoint": "http://localhost:11434"
    }
    status, res = fetch_json(f"{live_server}/api/tenant/connect", method="POST", data=payload)
    assert status == HTTPStatus.OK
    assert res["success"] is True
    assert res["tenant"]["org_name"] == "BharatHealth Care Pvt Ltd"
    assert res["tenant"]["aws_account_id"] == "112233445566"

    # Verify status reflects connected tenant (supporting both snake_case and camelCase)
    status, t_updated = fetch_json(f"{live_server}/api/tenant/status")
    assert status == HTTPStatus.OK
    assert t_updated["aws_account_id"] == "112233445566"
    assert t_updated["awsAccountId"] == "112233445566"
    assert t_updated["orgName"] == "BharatHealth Care Pvt Ltd"


# -----------------------------------------------------------------------------
# 6. STATIC SPA ROUTING FALLBACK
# -----------------------------------------------------------------------------

def test_spa_route_fallbacks(live_server):
    # Requesting an SPA route should return HTML (index.html)
    for route in ["/map", "/plan", "/compliance", "/approvals", "/architecture", "/pipeline"]:
        req = urllib.request.Request(f"{live_server}{route}")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == HTTPStatus.OK
            content = resp.read().decode("utf-8")
            assert "<!DOCTYPE html>" in content or "<html" in content

