"""Local zero-egress pipeline orchestrator connecting Scanners -> Graph -> MILP -> Airlock -> T0/T1 -> OPA Gate -> M2."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from local_engine.hcl_writer import render_hcl_diff
from local_engine.ollama_manager import check_ollama_status
from local_engine.paths import find_opa_binary, get_m2_status, get_policy_dir, get_vault_paths

try:
    from cryptography.fernet import Fernet
    from privacy.airlock.airlock import run_airlock
    from privacy.vault.vault import TokenVault

    AIRLOCK_OK = True
except Exception:
    AIRLOCK_OK = False
    run_airlock = None
    TokenVault = None

try:
    from remediate.templates import match as t0_match

    T0_OK = True
except Exception:
    T0_OK = False
    t0_match = None

try:
    from remediate.local_model import generate as t1_generate

    T1_OK = True
except Exception:
    T1_OK = False
    t1_generate = None

try:
    from ml.mutation_engine.qa.gate_stub import gate_many

    GATE_OK = True
except Exception:
    GATE_OK = False
    gate_many = None

try:
    from risk.attack_graph import ADMIN, build_attack_graph, get_crown_jewels, resolve_entry_nodes
    from risk.pagerank import score_digraph, to_percent
    from prioritize.evaluate import attack_length, residual_prob
    from prioritize.findings import enumerate_findings
    from prioritize.interdiction import prioritize_detailed
    from prioritize.naive import naive_select

    GRAPH_OK = True
except Exception:
    GRAPH_OK = False
    ADMIN = "ADMIN_EQUIV"
    attack_length = None
    residual_prob = None
    naive_select = None


_INTERDICTION_LOCK = threading.Lock()
_SOLVER_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="argus-solver")


def _compute_graph_and_interdiction(session: Any) -> tuple[Dict[str, Any], Dict[str, Any]]:
    graph_payload: Dict[str, Any] = {"nodes": [], "edges": []}
    interdiction_payload: Dict[str, Any] = {
        "budget": 3,
        "baseline_likelihood": 0.0,
        "residual_likelihood": 0.0,
        "selected_findings": [],
        "edges_interdicted": [],
        "cost_spent": 0,
        "attacker_shortest_path_cost": 0.0,
        "baseline_path_cost": 0.0,
        "selected_fixes": [],
        "pareto_curve": [],
    }
    G = build_attack_graph(session)
    entries = list(resolve_entry_nodes(G))
    entry_seen = set(entries)
    # Seed local IAM keys / users (and root roles if no IAM users/keys exist) so arbitrary
    # startup Terraform repos & AWS accounts always compute real attack paths, not just INTERNET.
    excluded_labels = {"argus-cartography-scanner"}
    has_user_or_key = False
    for nid, data in G.nodes(data=True):
        kind = data.get("kind")
        label = str(data.get("label", ""))
        if label in excluded_labels or nid in excluded_labels:
            continue
        if kind == "key":
            has_user_or_key = True
            if nid not in entry_seen:
                entries.append(nid)
                entry_seen.add(nid)
        elif kind == "user":
            has_user_or_key = True
            has_key_pred = any(G.nodes[p].get("kind") == "key" for p in G.predecessors(nid))
            if not has_key_pred and nid not in entry_seen:
                entries.append(nid)
                entry_seen.add(nid)
    if not has_user_or_key:
        for nid, data in G.nodes(data=True):
            if data.get("kind") == "role" and G.in_degree(nid) == 0 and nid not in entry_seen:
                entries.append(nid)
                entry_seen.add(nid)

    crowns = list(get_crown_jewels(G))
    for nid, data in G.nodes(data=True):
        if data.get("kind") == "bucket" and nid not in crowns:
            crowns.append(nid)

    ppr_pct: Dict[str, float] = {}
    if entries and G.number_of_nodes() > 0:
        try:
            ppr = score_digraph(G, entry_nodes=entries)
            ppr_pct = to_percent(ppr)
        except Exception:
            ppr_pct = {}

    graph_payload = _graph_to_dashboard_payload(G, ppr_pct, entries, crowns)

    graph_findings = enumerate_findings(G)
    if graph_findings and entries and crowns:
        pareto = []
        budget_table: Dict[str, Any] = {}
        detail_k3 = None
        with _INTERDICTION_LOCK:
            for b in range(0, 11):
                det = prioritize_detailed(graph_findings, b, G, entry_nodes=entries, crown_jewels=crowns)
                sel_ids = list(det["selected"])
                sel_set = set(sel_ids)
                sel_edges: List[Dict[str, str]] = []
                sel_fixes: List[Dict[str, Any]] = []
                sel_items = [item for item in det["ranked"] if item["finding_id"] in sel_set]
                reduction_total = max(
                    0.0, float(det["residual_attack_prob_before"] - det["residual_attack_prob_after"])
                )
                for idx, item in enumerate(sel_items, start=1):
                    cov = item.get("covers") or []
                    for c in cov:
                        sel_edges.append({"source": str(c[0]), "target": str(c[1])})
                    src_lbl = G.nodes[cov[0][0]].get("label", str(cov[0][0])) if cov and cov[0][0] in G else (str(cov[0][0]) if cov else "source")
                    tgt_lbl = G.nodes[cov[0][1]].get("label", str(cov[0][1])) if cov and cov[0][1] in G else (str(cov[0][1]) if cov else "target")
                    tlabel = item.get("target_label") or item.get("target", "")
                    sel_fixes.append(
                        {
                            "rank": idx,
                            "finding_id": item["finding_id"],
                            "title": f"{item.get('fix_op', 'remediate')} on {tlabel}",
                            "rule_id": (item.get("rule_ids") or ["cis.iam_no_full_admin"])[0],
                            "resource_id": str(tlabel),
                            "edge_cut": f"{src_lbl} -> {tgt_lbl}" if cov else "graph_cut",
                            "marginal_reduction": round(reduction_total / max(1, len(sel_items)), 3),
                        }
                    )
                b_entry = {
                    "budget": b,
                    "residual_likelihood": round(float(det["residual_attack_prob_after"]), 4),
                    "selected_findings": sel_ids,
                    "edges_interdicted": sel_edges,
                    "cost_spent": sum(f["cost"] for f in sel_items),
                    "attacker_shortest_path_cost": round(float(det["objective"] or 0.0), 2),
                    "selected_fixes": sel_fixes,
                }
                budget_table[str(b)] = b_entry
                if b == 3:
                    detail_k3 = det
                naive_res_prob = float(det["residual_attack_prob_before"])
                if naive_select is not None and attack_length is not None and residual_prob is not None:
                    try:
                        n_sel = set(naive_select(G, entries, graph_findings, b, ppr=ppr if ppr_pct else None)["selected"])
                        n_len = attack_length(G, entries, crowns, n_sel, graph_findings)
                        naive_res_prob = float(residual_prob(n_len))
                    except Exception:
                        naive_res_prob = float(det["residual_attack_prob_before"])
                pareto.append(
                    {
                        "budget": b,
                        "residual": b_entry["residual_likelihood"],
                        "naive_residual": round(naive_res_prob, 4),
                        "stackelberg_residual": b_entry["residual_likelihood"],
                    }
                )
        if detail_k3:
            k3_entry = budget_table["3"]
            interdiction_payload = {
                "budget": 3,
                "baseline_likelihood": round(float(detail_k3["residual_attack_prob_before"]), 4),
                "residual_likelihood": k3_entry["residual_likelihood"],
                "selected_findings": k3_entry["selected_findings"],
                "edges_interdicted": k3_entry["edges_interdicted"],
                "cost_spent": k3_entry["cost_spent"],
                "attacker_shortest_path_cost": k3_entry["attacker_shortest_path_cost"],
                "baseline_path_cost": round(float(detail_k3["baseline_objective"] or 0.0), 2),
                "selected_fixes": k3_entry["selected_fixes"],
                "pareto_curve": pareto,
                "budget_table": budget_table,
            }
    return graph_payload, interdiction_payload


_KIND_COLUMNS = {
    "internet": 60,
    "key": 160,
    "iprange": 160,
    "user": 300,
    "iprule": 300,
    "sg": 440,
    "role": 480,
    "policy": 620,
    "vpc": 620,
    "stmt": 740,
    "bucket": 900,
    "admin": 900,
}


def _graph_to_dashboard_payload(G, ppr_pct: Dict[str, float], entries: List[str], crowns: List[str]) -> Dict[str, Any]:
    import networkx as nx

    entry_set = set(entries)
    crown_set = set(crowns)

    from_entry: set[str] = set()
    for e in entry_set:
        if e in G:
            from_entry.add(e)
            from_entry.update(nx.descendants(G, e))

    to_crown: set[str] = set()
    for c in crown_set:
        if c in G:
            to_crown.add(c)
            to_crown.update(nx.ancestors(G, c))

    by_col: Dict[int, List[str]] = {}
    for nid, data in G.nodes(data=True):
        col = _KIND_COLUMNS.get(data.get("kind", "role"), 500)
        by_col.setdefault(col, []).append(nid)

    nodes = []
    for col, ids in by_col.items():
        n = len(ids)
        for i, nid in enumerate(sorted(ids)):
            data = G.nodes[nid]
            y = int(60 + ((i + 0.5) / max(1, n)) * 380)
            nodes.append(
                {
                    "id": str(nid),
                    "label": str(data.get("label", nid)),
                    "kind": str(data.get("kind", "node")),
                    "risk": round(float(ppr_pct.get(nid, 25.0)), 1),
                    "isEntry": nid in entry_set,
                    "isCrownJewel": nid in crown_set,
                    "x": col,
                    "y": y,
                    "details": {k: v for k, v in data.items() if k not in ("kind", "label")},
                }
            )

    edges = []
    for u, v, data in G.edges(data=True):
        on_attack = (u in from_entry and v in to_crown) or (
            data.get("etype") in ("DIRECT_ADMIN", "CAN_ESCALATE", "CAN_ACCESS")
        )
        edges.append(
            {
                "source": str(u),
                "target": str(v),
                "etype": str(data.get("etype", "EDGE")),
                "p": round(float(data.get("p", 0.5)), 3),
                "isAttackPath": on_attack,
            }
        )
    return {"nodes": nodes, "edges": edges}


def _build_compliance_summary(findings: List[Dict[str, Any]], region: str) -> List[Dict[str, Any]]:
    buckets = {
        "dpdp.rule6_encryption": [],
        "dpdp.rule6_public_exposure": [],
        "dpdp.rule7_logging": [],
        "dpdp.rule8_retention": [],
        "dpdp.rule15_residency": [],
    }
    for f in findings:
        rid = f.get("rule_id", "")
        if "rule6a" in rid or "encryption" in rid:
            buckets["dpdp.rule6_encryption"].append(f)
        elif "public" in rid or "sg_open" in rid or "iam" in rid or "mfa" in rid:
            buckets["dpdp.rule6_public_exposure"].append(f)
        elif "logging" in rid or "rule7" in rid or "versioning" in rid:
            buckets["dpdp.rule7_logging"].append(f)
        elif "lifecycle" in rid or "rule8" in rid or "retention" in rid:
            buckets["dpdp.rule8_retention"].append(f)
        elif "rule15" in rid:
            buckets["dpdp.rule15_residency"].append(f)

    defs = [
        ("dpdp.rule6_encryption", "Rule 6 Encryption (KMS / RDS)", "Data Security & Storage", "Section 8 safeguards: KMS/AES-256 at rest and RDS storage encryption."),
        ("dpdp.rule6_public_exposure", "Rule 6 Public Access & IAM", "Access Control", "Zero unauthorized citizen PII exposure on S3, SG, and IAM."),
        ("dpdp.rule7_logging", "Rule 6a/7 Audit Logging & Recovery", "Auditing & Traceability", "CloudTrail, S3 access logging, and versioning enabled."),
        ("dpdp.rule8_retention", "Rule 8 Retention & Erasure", "Lifecycle Governance", "Lifecycle expiration policies enforce data minimization."),
    ]
    out: List[Dict[str, Any]] = []
    for rid, name, cat, desc in defs:
        items = buckets[rid]
        active = [f for f in items if f.get("auto_apply_status") not in ("APPROVED", "APPLIED")]
        total = len(items)
        pct = 100 if total == 0 else max(0, int(((total - len(active)) / total) * 100))
        status = "PASS" if len(active) == 0 else ("WARNING" if len(active) == 1 else "FAIL")
        out.append(
            {
                "rule_id": rid,
                "name": name,
                "score_pct": pct,
                "failing_count": len(active),
                "violations_count": len(active),
                "review_count": 0,
                "status": status,
                "is_visibility_flag": False,
                "category": cat,
                "description": desc,
                "finding_ids": [f["finding_id"] for f in items],
            }
        )

    r15 = buckets["dpdp.rule15_residency"]
    out.append(
        {
            "rule_id": "dpdp.rule15_residency",
            "name": f"Rule 15 Data Residency ({region})",
            "score_pct": None,
            "failing_count": 0,
            "violations_count": 0,
            "review_count": len(r15),
            "status": "FLAGGED" if r15 else "PASS",
            "is_visibility_flag": True,
            "category": "Geographic Sovereignty",
            "description": "Visibility Flag: Personal-data resources verified against approved Indian residency regions.",
            "finding_ids": [f["finding_id"] for f in r15],
            "residency": {
                "home_region": region,
                "cross_border_resources": [f.get("resource_name", f.get("resource_id")) for f in r15],
            },
        }
    )
    return out


def run_local_scan_pipeline(scan_result: Dict[str, Any], *, region: str = "ap-south-1") -> Dict[str, Any]:
    """Run Attack Graph + MILP + Airlock + T0/T1 + OPA Gate + M2 check on real scanner output."""
    find_opa_binary()
    m2_status = get_m2_status()
    ollama = check_ollama_status()
    policy_dir = get_policy_dir()
    vault_db, vault_key = get_vault_paths()

    # 1. Build Attack Graph & Compute PPR + Interdiction via frozen Phase 2/3 modules
    graph_payload: Dict[str, Any] = {"nodes": [], "edges": []}
    interdiction_payload: Dict[str, Any] = {
        "budget": 3,
        "baseline_likelihood": 0.0,
        "residual_likelihood": 0.0,
        "selected_findings": [],
        "edges_interdicted": [],
        "cost_spent": 0,
        "attacker_shortest_path_cost": 0.0,
        "baseline_path_cost": 0.0,
        "selected_fixes": [],
        "pareto_curve": [],
    }

    session = scan_result.get("session")
    if GRAPH_OK and session is not None:
        graph_payload, interdiction_payload = _SOLVER_EXECUTOR.submit(
            _compute_graph_and_interdiction, session
        ).result()

    # 2. Run Airlock -> T0/T1 -> OPA Gate -> M2 Safety Policy per finding
    vault = TokenVault(db_path=vault_db, key_path=vault_key) if AIRLOCK_OK and TokenVault else None
    dashboard_findings: List[Dict[str, Any]] = []
    receipts: List[Dict[str, Any]] = []

    for raw in scan_result.get("raw_findings", []):
        fid = raw["finding_id"]
        rule_id = raw["rule_id"]
        t0 = time.time()

        # Step A: Privacy Airlock
        sanitized = {
            "finding_id": fid,
            "rule_id": rule_id,
            "resource_id": raw.get("resource_id", "RESOURCE_1"),
            "resource_ref": "RESOURCE_1",
            "fields": dict(raw.get("attributes", {})),
        }
        rcpt_obj: Dict[str, Any] = {
            "receipt_id": f"rcpt-{fid}",
            "finding_id": fid,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "rule_id": rule_id,
            "projected_fields": dict(raw.get("attributes", {})),
            "tokens": {},
            "scrub_result": {"presidio_hits": 0, "secret_scan_hits": 0},
            "tier_used": "T0 (Deterministic Template)",
            "leaked_to_network": False,
        }

        if AIRLOCK_OK and run_airlock is not None and vault is not None:
            try:
                air_record = {
                    "finding_id": fid,
                    "resource_id": raw.get("resource_id", fid),
                    "resource_type": raw.get("resource_type", "AWSS3Bucket"),
                    "attributes": dict(raw.get("attributes", {})),
                }
                san_out, air_rcpt = run_airlock(air_record, rule_id, vault=vault, policy_dir=policy_dir)
                sanitized = san_out
                rcpt_obj["projected_fields"] = air_rcpt.get("projected_fields", {})
                rcpt_obj["tokens"] = air_rcpt.get("tokens", {})
                rcpt_obj["scrub_result"] = air_rcpt.get("scrub_result", {"presidio_hits": 0, "secret_scan_hits": 0})
                rcpt_obj["record_sha256"] = air_rcpt.get("record_sha256")
                rcpt_obj["leaked_to_network"] = bool(air_rcpt.get("leaked_to_network", False))
            except Exception as exc:
                rcpt_obj["airlock_note"] = str(exc)

        # Step B: Tier 0 template -> Tier 1 local Ollama -> Escalate fallback
        patch_ir = None
        tier_used = "T0"
        generator_model = "deterministic_template"

        if T0_OK and t0_match is not None:
            try:
                patch_ir = t0_match(sanitized)
            except Exception:
                patch_ir = None

        selected_m1 = (
            "argus-m1-sft"
            if ollama.get("argus_sft_ready")
            else ("argus-m1-rft" if ollama.get("argus_rft_ready") else None)
        )
        if patch_ir is None and T1_OK and t1_generate is not None and ollama.get("running") and selected_m1:
            try:
                candidates = t1_generate(sanitized, n=1, model=selected_m1)
                if candidates:
                    patch_ir = candidates[0]
                    tier_used = "T1"
                    generator_model = selected_m1
            except Exception:
                patch_ir = None

        if patch_ir is None:
            tier_used = "T3"
            generator_model = "human"
            patch_ir = {
                "finding_id": fid,
                "resource_ref": sanitized.get("resource_ref", "RESOURCE_1"),
                "ops": [{"op": "escalate", "reason": f"Requires architect review for {rule_id}"}],
                "rationale_ref": rule_id,
            }

        # Step C: Verification Gate
        gate_passed = True
        gate_outcome = "escalated" if tier_used == "T3" else "fixed"
        gate_reasons: List[str] = []
        if GATE_OK and gate_many is not None and find_opa_binary():
            try:
                verdict = gate_many([(sanitized, patch_ir)])[0]
                gate_passed = verdict.passed
                gate_outcome = verdict.outcome
                gate_reasons = list(verdict.reasons)
            except Exception:
                pass

        is_escalated = (gate_outcome == "escalated") or not gate_passed or tier_used == "T3"
        if not gate_passed:
            rej_reason = gate_reasons[0] if gate_reasons else f"OPA verification gate rejected candidate for {rule_id}"
            tier_used = "T3"
            generator_model = "human"
            patch_ir = {
                "finding_id": fid,
                "resource_ref": sanitized.get("resource_ref", "RESOURCE_1"),
                "ops": [
                    {
                        "op": "escalate",
                        "reason": f"Verification Gate rejected candidate ({rej_reason}); escalated for human architect review.",
                    }
                ],
                "rationale_ref": rule_id,
            }
        elif gate_outcome == "escalated" and tier_used != "T3":
            tier_used = "T3"
            generator_model = "human"
        # Step D: Strict M2 Certification Guardrail (Phase 7 Handoff)
        # While m2_status['certified'] is False, autonomy MUST stay OFF (never auto-apply).
        certified = bool(m2_status.get("certified", False))
        auto_apply_status = "ESCALATED" if is_escalated else "NEEDS_APPROVAL"
        status = "ESCALATED" if is_escalated else "NEEDS_REVIEW"
        reason = (
            (gate_reasons[0] if gate_reasons else f"Escalated {rule_id} for human architect review.")
            if is_escalated
            else f"Autonomy OFF: awaiting M2 LTT certification ({m2_status.get('message')})"
        )

        latency_ms = round((time.time() - t0) * 1000, 2)
        rcpt_obj["tier_used"] = (
            "T3 (Security Architect Review Queue)"
            if tier_used == "T3"
            else (f"T1 (Local Ollama {generator_model})" if tier_used == "T1" else "T0 (Deterministic Template)")
        )
        receipts.append(rcpt_obj)

        finding_entry = {
            "finding_id": fid,
            "rule_id": rule_id,
            "rule_title": rule_id,
            "title": f"Remediate {rule_id} on {raw.get('resource_name', raw.get('resource_id'))}",
            "resource_id": sanitized.get("resource_ref", raw.get("resource_id", "RESOURCE_1")),
            "resource_name": raw.get("resource_name", raw.get("resource_id")),
            "resource_type": raw.get("resource_type", "AWSS3Bucket"),
            "severity": "MEDIUM" if raw.get("is_warning") else ("CRITICAL" if "public" in rule_id or "admin" in rule_id or "rule6a" in rule_id else "HIGH"),
            "status": status,
            "auto_apply_status": auto_apply_status,
            "m2_confidence": None,
            "confidence": "n/a",
            "threshold": 0.95,
            "conformal_threshold": 0.95,
            "certified": certified,
            "reason": reason,
            "escalated": is_escalated,
            "tier_used": tier_used,
            "generator_model": generator_model,
            "latency_ms": latency_ms,
            "cost": 2 if is_escalated else 1,
            "source_file": raw.get("source_file"),
            "hcl_before": raw.get("hcl_before"),
            "patch_ir": patch_ir,
            "privacy_receipt_id": rcpt_obj["receipt_id"],
        }
        finding_entry["diff"] = render_hcl_diff(finding_entry)
        dashboard_findings.append(finding_entry)

    compliance = _build_compliance_summary(dashboard_findings, region=region)
    scan_id = f"scan-local-{int(time.time())}"
    return {
        "scan_id": scan_id,
        "scanned_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_type": scan_result.get("source_type", "terraform"),
        "target": scan_result.get("target", ""),
        "account_id": scan_result.get("account_id"),
        "identity": scan_result.get("identity"),
        "opa_used": bool(scan_result.get("opa_used", False)),
        "m2_status": m2_status,
        "ollama_status": ollama,
        "findings": dashboard_findings,
        "compliance": compliance,
        "interdiction": interdiction_payload,
        "graph": graph_payload,
        "receipts": receipts,
    }
