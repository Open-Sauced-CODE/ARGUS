"""Deterministic Patch-IR to Terraform HCL diff generator & DPDP Audit Exporter."""

from __future__ import annotations

import io
import json
import re
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from local_engine.paths import get_exports_dir


def render_hcl_diff(finding: Dict[str, Any]) -> Dict[str, str]:
    """Generate deterministic Terraform HCL before/after preview from Patch-IR ops."""
    before = finding.get("hcl_before") or f'# Resource: {finding.get("resource_id", "resource")}'
    patch_ir = finding.get("patch_ir") or {}
    ops = patch_ir.get("ops") or []
    rule_id = finding.get("rule_id", "")
    raw_name = str(finding.get("resource_name") or finding.get("resource_id") or "resource").split("/")[-1].split(":")[-1]
    rname = re.sub(r"[^A-Za-z0-9_-]", "_", raw_name).strip("_") or "resource"

    if not ops:
        return {"before": before, "after": "# No patch operations proposed."}

    if finding.get("escalated") or any(op.get("op") == "escalate" for op in ops):
        esc_reasons = [str(op.get("reason", "")) for op in ops if op.get("op") == "escalate" and op.get("reason")]
        reasons = "; ".join(esc_reasons) if esc_reasons else str(finding.get("reason") or "Requires architect review")
        return {
            "before": before,
            "after": (
                f"# ARGUS Escalate Router Triggered: {rule_id}\n"
                f"# {reasons}\n"
                "# Routed to Tier 3 Security Architect Review Queue (Zero unsafe mutations)."
            ),
        }

    lines: List[str] = []
    if ("encryption" in rule_id or "rule6a" in rule_id) and "rds" not in rule_id:
        lines.append(f'resource "aws_s3_bucket_server_side_encryption_configuration" "{rname}_sse" {{')
        lines.append(f'  bucket = "{rname}"')
        lines.append("+ rule {")
        lines.append("+   apply_server_side_encryption_by_default {")
        lines.append('+     sse_algorithm = "aws:kms"')
        lines.append("+   }")
        lines.append("+   bucket_key_enabled = true")
        lines.append("+ }")
        lines.append("}")
    elif "public" in rule_id:
        lines.append(f'resource "aws_s3_bucket_public_access_block" "{rname}_pab" {{')
        lines.append(f'  bucket = "{rname}"')
        for op in ops:
            attr = op.get("attr")
            val = json.dumps(op.get("value"))
            lines.append(f"+ {attr:<24} = {val}")
        lines.append("}")
    elif "versioning" in rule_id:
        lines.append(f'resource "aws_s3_bucket_versioning" "{rname}_ver" {{')
        lines.append(f'  bucket = "{rname}"')
        lines.append("+ versioning_configuration {")
        lines.append('+   status = "Enabled"')
        lines.append("+ }")
        lines.append("}")
    elif "logging" in rule_id:
        lines.append(f'resource "aws_s3_bucket_logging" "{rname}_log" {{')
        lines.append(f'  bucket        = "{rname}"')
        lines.append('+ target_bucket = "central-dpdp-audit-logs"')
        lines.append('+ target_prefix = "s3-access-logs/"')
        lines.append("}")
    elif "lifecycle" in rule_id or "retention" in rule_id:
        lines.append(f'resource "aws_s3_bucket_lifecycle_configuration" "{rname}_lc" {{')
        lines.append(f'  bucket = "{rname}"')
        lines.append("+ rule {")
        lines.append('+   id     = "dpdp-retention"')
        lines.append('+   status = "Enabled"')
        lines.append("+   expiration { days = 180 }")
        lines.append("+ }")
        lines.append("}")
    elif "sg_open_ingress" in rule_id:
        lines.append(f'resource "aws_security_group" "{rname}" {{')
        lines.append("- cidr_blocks = [\"0.0.0.0/0\"]")
        lines.append('+ cidr_blocks = ["10.0.0.0/16"] # Restricted internal CIDR')
        lines.append("}")
    elif "rds" in rule_id:
        lines.append(f'resource "aws_db_instance" "{rname}" {{')
        lines.append("- storage_encrypted = false")
        lines.append("+ storage_encrypted = true")
        lines.append("}")
    elif "rule7_detection" in rule_id or "cloudtrail" in rule_id:
        lines.append(f'resource "aws_cloudtrail" "{rname}_trail" {{')
        lines.append("- enable_logging = false")
        lines.append("+ enable_logging = true")
        lines.append("+ enable_log_file_validation = true")
        lines.append("}")
    else:
        lines.append(f"# Verified Patch-IR for {rname} ({rule_id})")
        for op in ops:
            lines.append(f"+ {op.get('op')}: {op.get('attr', '')} = {json.dumps(op.get('value'))}")

    return {"before": before, "after": "\n".join(lines)}


def export_finding_patch(finding: Dict[str, Any], exports_dir: Optional[Path] = None) -> Path:
    """Write a unified .patch file for an approved/verified finding to disk."""
    out_dir = Path(exports_dir or get_exports_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    fid = finding.get("finding_id", "finding")
    diff = finding.get("diff") or render_hcl_diff(finding)
    source_file = finding.get("source_file", "main.tf")
    patch_path = out_dir / f"{fid}.patch"

    content = (
        f"# ARGUS Verified Remediation Patch ({fid})\n"
        f"# Rule: {finding.get('rule_id')}\n"
        f"# Resource: {finding.get('resource_id')}\n"
        f"# Source: {source_file}\n"
        f"# Generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n\n"
        f"--- a/{Path(str(source_file)).name}\n"
        f"+++ b/{Path(str(source_file)).name}\n"
        f"{diff.get('after', '')}\n"
    )
    patch_path.write_text(content, encoding="utf-8")
    return patch_path


def build_audit_bundle_zip(
    *,
    scan_id: str,
    tenant: Dict[str, Any],
    findings: List[Dict[str, Any]],
    compliance: List[Dict[str, Any]],
    receipts: List[Dict[str, Any]],
) -> bytes:
    """Create an in-memory DPDP Compliance Audit ZIP containing receipts, findings, and diffs."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "platform": "ARGUS Local Zero-Egress Engine",
            "scan_id": scan_id,
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tenant": tenant,
            "zero_data_egress_verified": all(not r.get("leaked_to_network", False) for r in receipts),
            "findings_count": len(findings),
            "receipts_count": len(receipts),
        }
        zf.writestr("audit_manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("findings.json", json.dumps(findings, indent=2))
        zf.writestr("compliance_dpdp.json", json.dumps(compliance, indent=2))
        zf.writestr("privacy_receipts.json", json.dumps(receipts, indent=2))
        for f in findings:
            diff = f.get("diff")
            if diff and diff.get("after"):
                zf.writestr(f"patches/{f.get('finding_id', 'patch')}.patch", diff["after"])
    return buf.getvalue()
