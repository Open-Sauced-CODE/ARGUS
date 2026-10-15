"""
ARGUS Phase 3 — Fix-finding enumerator.

Scans the Phase 2 attack graph and produces a list of ``finding`` dicts —
one per applicable fix (remove_policy_statement or restrict_cidr by default).
Each finding has a deterministic id, a cost, a delta, and a list of edges it
covers (the MILP reads these).

Public API:
    load_catalogue(path=None) -> dict
    load_config(path=None) -> dict
    enumerate_findings(G, catalogue=None, include_unsimulated=False,
                       exclude_aws_managed=None) -> list[dict]
    list_non_actionable(G, catalogue=None) -> list[dict]

Rules:
  * One ``remove_policy_statement`` finding per ``stmt`` node that has at
    least one out-edge with etype in catalogue's covers_etypes.
  * One ``restrict_cidr`` finding per ``sg`` node with at least one in-edge
    of etype RULE_TO_SG.
  * ``deactivate_key`` / ``tighten_trust`` only if include_unsimulated=True
    and ``enabled`` in the catalogue.
  * AWS-managed policy statements (id starts with a non-actionable prefix from
    config.json) are excluded by default and listed separately by
    list_non_actionable().
  * finding_id = "F-" + sha1(fix_op + "|" + target).hexdigest()[:8]
  * Output is sorted by finding_id for determinism.
  * G is never mutated.

No Neo4j imports in this file.
"""

import hashlib
import json
import math
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CATALOGUE_PATH = _HERE / "fix_catalogue.json"
_CONFIG_PATH = _HERE / "config.json"

# Phase 4 known rule ids (never invent ids outside this set)
_KNOWN_RULE_IDS = frozenset({
    "cis.iam_no_full_admin",
    "cis.s3_default_encryption",
    "cis.s3_public_access_block",
    "cis.sg_open_ingress",
    "dpdp.rule6a",
    "dpdp.rule6a_rds",
    "dpdp.rule6_sg_open_ingress",
    "dpdp.rule6_account_mfa",
    "dpdp.rule6_public_exposure",
    "dpdp.rule6_versioning",
    "dpdp.rule6_logging",
    "dpdp.rule7_detection",
    "dpdp.rule8_lifecycle",
    "dpdp.rule15_region",
})

_DELTA_MAX_FALLBACK = -math.log(1e-6)  # 13.8155...; used only if JSON missing


def load_catalogue(path=None):
    """Load and return fix_catalogue.json as a dict.

    Parameters
    ----------
    path : str or Path or None
        Override path to fix_catalogue.json.  None → package default.
    """
    p = Path(path) if path else _CATALOGUE_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    delta_max = float(raw.get("delta_max", _DELTA_MAX_FALLBACK))
    # Resolve "delta_max" strings to the numeric value
    for fix_name, fix_spec in raw.get("fixes", {}).items():
        if fix_spec.get("delta") == "delta_max":
            fix_spec["delta"] = delta_max
    return raw


def load_config(path=None):
    """Load and return config.json as a dict."""
    p = Path(path) if path else _CONFIG_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def _finding_id(fix_op, target):
    """Deterministic finding id: 'F-' + sha1(fix_op + '|' + target)[:8]."""
    digest = hashlib.sha1(
        (fix_op + "|" + str(target)).encode("utf-8")
    ).hexdigest()
    return "F-" + digest[:8]


def _is_non_actionable(node_id, prefixes):
    """Return True if node_id starts with any non-actionable prefix."""
    return any(str(node_id).startswith(p) for p in prefixes)


def _resolve_rule_ids(fix_op, covers, cfg):
    """Return (rule_ids, rule_gap) for a finding based on its covered etypes.

    Logic (per spec):
      * remove_policy_statement covering DIRECT_ADMIN → ["cis.iam_no_full_admin"]
      * remove_policy_statement covering only CAN_ESCALATE → [], rule_gap=True
      * remove_policy_statement covering only CAN_ACCESS → [], rule_gap=True
      * restrict_cidr → ["cis.sg_open_ingress", "dpdp.rule6_sg_open_ingress"]
    Never invents ids outside Phase 4's list.
    """
    fam = None
    if fix_op == "restrict_cidr":
        fam = "net_open_ingress"
    elif fix_op == "remove_policy_statement":
        etypes = {c[2] for c in covers}
        if "DIRECT_ADMIN" in etypes:
            # cis.iam_no_full_admin covers the Admin=* case
            rule_ids = ["cis.iam_no_full_admin"]
            return rule_ids, False
        # CAN_ESCALATE or CAN_ACCESS — no Rego rule yet
        return [], True
    elif fix_op == "deactivate_key":
        fam = "key_active"
    elif fix_op == "tighten_trust":
        fam = "trust_overbroad"

    if fam is None:
        return [], True

    rule_family_map = cfg.get("rule_family_to_rule_ids", {})
    ids = rule_family_map.get(fam, [])
    # Safety: strip any id not in the Phase 4 known set
    ids = [r for r in ids if r in _KNOWN_RULE_IDS]
    rule_gap = len(ids) == 0
    return ids, rule_gap


def enumerate_findings(G, catalogue=None, include_unsimulated=False,
                       exclude_aws_managed=None):
    """Enumerate applicable fix-findings from the attack graph.

    Parameters
    ----------
    G : nx.DiGraph
        Phase 2 attack graph (never mutated).
    catalogue : dict or None
        Loaded catalogue (load_catalogue()).  None → load from package default.
    include_unsimulated : bool
        If True, also include deactivate_key and tighten_trust findings.
    exclude_aws_managed : bool or None
        If None or True: exclude stmt nodes whose id starts with a prefix
        from config.json non_actionable_stmt_prefixes.
        If False: include them (use list_non_actionable() instead).

    Returns
    -------
    list[dict]
        Sorted by finding_id.  Each dict matches the frozen finding shape.
    """
    if catalogue is None:
        catalogue = load_catalogue()
    cfg = load_config()
    fixes = catalogue.get("fixes", {})
    delta_max = float(catalogue.get("delta_max", _DELTA_MAX_FALLBACK))
    non_act_prefixes = cfg.get("non_actionable_stmt_prefixes", [])
    if exclude_aws_managed is None:
        exclude_aws_managed = True

    findings = []
    # Track covered edges to enforce disjointness within this enumeration
    covered_edges = {}

    # ------------------------------------------------------------------ #
    # 1. remove_policy_statement (stmt nodes)
    # ------------------------------------------------------------------ #
    fix_spec = fixes.get("remove_policy_statement", {})
    if fix_spec.get("enabled", True):
        covers_etypes = set(fix_spec.get("covers_etypes",
                                         ["CAN_ESCALATE", "DIRECT_ADMIN", "CAN_ACCESS"]))
        delta_val = float(fix_spec.get("delta", delta_max))
        cost_val = int(fix_spec.get("cost", 2))
        rule_family = fix_spec.get("rule_family", "iam_privilege_escalation")

        for node, attrs in G.nodes(data=True):
            if attrs.get("kind") != "stmt":
                continue
            if exclude_aws_managed and _is_non_actionable(node, non_act_prefixes):
                continue
            # Collect out-edges with matching etype
            covered = []
            for _, v, edata in G.out_edges(node, data=True):
                if edata.get("etype") in covers_etypes:
                    covered.append([node, v, edata["etype"]])
            if not covered:
                continue
            fid = _finding_id("remove_policy_statement", node)
            rule_ids, rule_gap = _resolve_rule_ids(
                "remove_policy_statement", covered, cfg
            )
            findings.append({
                "finding_id": fid,
                "fix_op": "remove_policy_statement",
                "target": node,
                "target_label": attrs.get("label", str(node)),
                "covers": covered,
                "delta": delta_val,
                "cost": cost_val,
                "rule_family": rule_family,
                "rule_ids": rule_ids,
                "rule_gap": rule_gap,
                "simulated": bool(fix_spec.get("simulated", True)),
            })
            for _, v, etype in covered:
                covered_edges[(node, v)] = fid

    # ------------------------------------------------------------------ #
    # 2. restrict_cidr (sg nodes)
    # ------------------------------------------------------------------ #
    fix_spec = fixes.get("restrict_cidr", {})
    if fix_spec.get("enabled", True):
        covers_etypes = set(fix_spec.get("covers_etypes", ["RULE_TO_SG"]))
        delta_val = float(fix_spec.get("delta", 2.3026))
        cost_val = int(fix_spec.get("cost", 1))
        rule_family = fix_spec.get("rule_family", "net_open_ingress")

        for node, attrs in G.nodes(data=True):
            if attrs.get("kind") != "sg":
                continue
            covered = []
            for u, _, edata in G.in_edges(node, data=True):
                if edata.get("etype") in covers_etypes:
                    covered.append([u, node, edata["etype"]])
            if not covered:
                continue
            fid = _finding_id("restrict_cidr", node)
            rule_ids, rule_gap = _resolve_rule_ids(
                "restrict_cidr", covered, cfg
            )
            findings.append({
                "finding_id": fid,
                "fix_op": "restrict_cidr",
                "target": node,
                "target_label": attrs.get("label", str(node)),
                "covers": covered,
                "delta": delta_val,
                "cost": cost_val,
                "rule_family": rule_family,
                "rule_ids": rule_ids,
                "rule_gap": rule_gap,
                "simulated": bool(fix_spec.get("simulated", True)),
            })
            for u, _, etype in covered:
                covered_edges[(u, node)] = fid

    # ------------------------------------------------------------------ #
    # 3. Unsimulated fixes (off by default)
    # ------------------------------------------------------------------ #
    if include_unsimulated:
        # deactivate_key
        fix_spec = fixes.get("deactivate_key", {})
        if fix_spec.get("enabled", False):
            covers_etypes = set(fix_spec.get("covers_etypes", ["USES_KEY"]))
            delta_val = float(fix_spec.get("delta", delta_max))
            cost_val = int(fix_spec.get("cost", 1))
            rule_family = fix_spec.get("rule_family", "key_active")
            for node, attrs in G.nodes(data=True):
                if attrs.get("kind") != "key":
                    continue
                covered = []
                for _, v, edata in G.out_edges(node, data=True):
                    if edata.get("etype") in covers_etypes:
                        covered.append([node, v, edata["etype"]])
                if not covered:
                    continue
                fid = _finding_id("deactivate_key", node)
                rule_ids, rule_gap = _resolve_rule_ids("deactivate_key", covered, cfg)
                findings.append({
                    "finding_id": fid,
                    "fix_op": "deactivate_key",
                    "target": node,
                    "target_label": attrs.get("label", str(node)),
                    "covers": covered,
                    "delta": delta_val,
                    "cost": cost_val,
                    "rule_family": rule_family,
                    "rule_ids": rule_ids,
                    "rule_gap": rule_gap,
                    "simulated": bool(fix_spec.get("simulated", False)),
                })

        # tighten_trust
        fix_spec = fixes.get("tighten_trust", {})
        if fix_spec.get("enabled", False):
            covers_etypes = set(fix_spec.get("covers_etypes", ["CAN_ASSUME"]))
            delta_val = float(fix_spec.get("delta", 2.3026))
            cost_val = int(fix_spec.get("cost", 2))
            rule_family = fix_spec.get("rule_family", "trust_overbroad")
            for node, attrs in G.nodes(data=True):
                if attrs.get("kind") != "role":
                    continue
                covered = []
                for u, _, edata in G.in_edges(node, data=True):
                    if edata.get("etype") in covers_etypes:
                        covered.append([u, node, edata["etype"]])
                if not covered:
                    continue
                fid = _finding_id("tighten_trust", node)
                rule_ids, rule_gap = _resolve_rule_ids("tighten_trust", covered, cfg)
                findings.append({
                    "finding_id": fid,
                    "fix_op": "tighten_trust",
                    "target": node,
                    "target_label": attrs.get("label", str(node)),
                    "covers": covered,
                    "delta": delta_val,
                    "cost": cost_val,
                    "rule_family": rule_family,
                    "rule_ids": rule_ids,
                    "rule_gap": rule_gap,
                    "simulated": bool(fix_spec.get("simulated", False)),
                })

    # Sort by finding_id for determinism
    findings.sort(key=lambda f: f["finding_id"])
    return findings


def list_non_actionable(G, catalogue=None):
    """Return findings for AWS-managed statements (excluded from enumerate_findings).

    These are reported but not actionable directly — the real fix is to detach
    the AWS-managed policy from the principal.

    Returns
    -------
    list[dict]
        Same shape as enumerate_findings() output, simulated=False.
    """
    if catalogue is None:
        catalogue = load_catalogue()
    cfg = load_config()
    fixes = catalogue.get("fixes", {})
    delta_max = float(catalogue.get("delta_max", _DELTA_MAX_FALLBACK))
    non_act_prefixes = cfg.get("non_actionable_stmt_prefixes", [])

    fix_spec = fixes.get("remove_policy_statement", {})
    covers_etypes = set(fix_spec.get("covers_etypes",
                                     ["CAN_ESCALATE", "DIRECT_ADMIN", "CAN_ACCESS"]))
    delta_val = float(fix_spec.get("delta", delta_max))
    cost_val = int(fix_spec.get("cost", 2))
    rule_family = fix_spec.get("rule_family", "iam_privilege_escalation")

    findings = []
    for node, attrs in G.nodes(data=True):
        if attrs.get("kind") != "stmt":
            continue
        if not _is_non_actionable(node, non_act_prefixes):
            continue
        covered = []
        for _, v, edata in G.out_edges(node, data=True):
            if edata.get("etype") in covers_etypes:
                covered.append([node, v, edata["etype"]])
        if not covered:
            continue
        fid = _finding_id("remove_policy_statement", node)
        rule_ids, rule_gap = _resolve_rule_ids("remove_policy_statement", covered, cfg)
        findings.append({
            "finding_id": fid,
            "fix_op": "remove_policy_statement",
            "target": node,
            "target_label": attrs.get("label", str(node)),
            "covers": covered,
            "delta": delta_val,
            "cost": cost_val,
            "rule_family": rule_family,
            "rule_ids": rule_ids,
            "rule_gap": rule_gap,
            "simulated": False,  # AWS-managed: not directly actionable
            "non_actionable": True,
            "note": "AWS-managed policy statement; fix is to detach the policy from the principal",
        })
    findings.sort(key=lambda f: f["finding_id"])
    return findings
