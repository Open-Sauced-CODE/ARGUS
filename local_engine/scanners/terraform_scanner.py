"""Pure-Python Terraform (.tf / .tf.json / .tfvars) scanner mapped to ARGUS Rego schemas & Attack Graph rows."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from local_engine.graph.inmemory_session import LocalCartographySession
from local_engine.paths import find_opa_binary, get_policy_dir

try:
    import hcl2  # type: ignore

    HCL2_AVAILABLE = True
except Exception:
    hcl2 = None
    HCL2_AVAILABLE = False

try:
    from ml.real_data.rego_runner import evaluate as opa_evaluate

    REGO_RUNNER_AVAILABLE = True
except Exception:
    opa_evaluate = None
    REGO_RUNNER_AVAILABLE = False


_PUBLIC_ACL_VALUES = {"public-read", "public-read-write", "authenticated-read"}


def _extract_hcl_snippet(text: str, rtype: str, rname: str, keyword: str = "resource") -> str:
    """Extract the exact resource/data HCL block from source text by brace balancing."""
    pattern = re.compile(
        rf'{re.escape(keyword)}\s+"{re.escape(rtype)}"\s+"{re.escape(rname)}"\s*\{{'
    )
    m = pattern.search(text)
    if not m:
        return f'{keyword} "{rtype}" "{rname}" {{ ... }}'
    start = m.start()
    depth = 0
    end = len(text)
    for idx in range(m.end() - 1, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = idx + 1
                break
    return text[start:end].strip()


def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s


def _clean_hcl_obj(obj: Any) -> Any:
    """Recursively normalize python-hcl2 v8 output (strip literal quotes and __is_block__)."""
    if isinstance(obj, dict):
        return {
            _strip_quotes(str(k)): _clean_hcl_obj(v)
            for k, v in obj.items()
            if k != "__is_block__"
        }
    if isinstance(obj, list):
        return [_clean_hcl_obj(v) for v in obj]
    if isinstance(obj, str):
        return _strip_quotes(obj)
    return obj


def _unwrap_str(
    val: Any,
    default: str = "",
    tf_vars: Optional[Dict[str, str]] = None,
    tf_locals: Optional[Dict[str, str]] = None,
) -> str:
    if isinstance(val, list):
        val = val[0] if val else default
    if val is None:
        return default
    s = _strip_quotes(str(val)).strip()

    if tf_vars:
        # Handle composite interpolations like "${var.env}-citizen-kyc"
        def _repl(match: re.Match[str]) -> str:
            vname = match.group(1).strip()
            return tf_vars.get(vname, match.group(0))

        s = re.sub(r"\$\{var\.([A-Za-z0-9_-]+)\}", _repl, s)

    if tf_locals:
        def _repl_local(match: re.Match[str]) -> str:
            lname = match.group(1).strip()
            return tf_locals.get(lname, match.group(0))

        s = re.sub(r"\$\{local\.([A-Za-z0-9_-]+)\}", _repl_local, s)

    inner = s[2:-1].strip() if (s.startswith("${") and s.endswith("}")) else s
    if tf_vars and inner.startswith("var."):
        vname = inner[4:].strip()
        if vname in tf_vars:
            return tf_vars[vname]
    if tf_locals and inner.startswith("local."):
        lname = inner[6:].strip()
        if lname in tf_locals:
            return tf_locals[lname]
    return s


def _is_unresolved_expr(s: str) -> bool:
    t = s.strip()
    return "${" in t or t.startswith("var.") or t.startswith("local.")


def _az_to_region(az: str, default_region: str) -> str:
    s = (az or "").strip()
    if not s:
        return default_region
    m = re.match(r"^([a-z]{2}-[a-z-]+-\d+)[a-z]$", s)
    if m:
        return m.group(1)
    if re.match(r"^[a-z]{2}-[a-z-]+-\d+$", s):
        return s
    return default_region


def _unwrap_bool(val: Any, default: bool = False, tf_vars: Optional[Dict[str, str]] = None) -> bool:
    if isinstance(val, list):
        val = val[0] if val else default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        resolved = _unwrap_str(val, str(default).lower(), tf_vars).strip().lower()
        if resolved in ("true", "1", "yes"):
            return True
        if resolved in ("false", "0", "no"):
            return False
        return default
    return bool(val) if val is not None else default


def _safe_int(val: Any, default: int, tf_vars: Optional[Dict[str, str]] = None) -> int:
    if isinstance(val, list):
        val = val[0] if val else default
    if val is None:
        return default
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return int(val)
    try:
        resolved = _unwrap_str(val, str(default), tf_vars)
        return int(float(resolved))
    except Exception:
        return default


def _as_list(val: Any) -> List[Any]:
    if val is None:
        return []
    return list(val) if isinstance(val, list) else [val]


def _resolve_bucket_ref(
    raw_ref: Any,
    by_tf_name: Dict[str, str],
    *,
    by_dir_tf_name: Optional[Dict[Tuple[str, str], str]] = None,
    source_dir: str = "",
    tf_vars: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    s = _unwrap_str(raw_ref, "", tf_vars).strip()
    if s.startswith("${") and s.endswith("}"):
        s = s[2:-1].strip()
    if not s:
        return None
    m = re.search(r"aws_s3_bucket\.([A-Za-z0-9_-]+)(?:\[[^\]]+\])?\.", s)
    if m:
        rname = m.group(1)
        if by_dir_tf_name and (source_dir, rname) in by_dir_tf_name:
            return by_dir_tf_name[(source_dir, rname)]
        return by_tf_name.get(rname, rname)
    return s


def _convert_data_policy_doc(attrs: Dict[str, Any], tf_vars: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Convert HCL `data "aws_iam_policy_document"` block into IAM JSON document format."""
    stmts: List[Dict[str, Any]] = []
    for raw_st in _as_list(attrs.get("statement")):
        if not isinstance(raw_st, dict):
            continue
        effect = _unwrap_str(raw_st.get("effect"), "Allow", tf_vars) or "Allow"
        actions = [
            _unwrap_str(a, "", tf_vars)
            for a in (_as_list(raw_st.get("actions")) + _as_list(raw_st.get("action")))
            if _unwrap_str(a, "", tf_vars)
        ]
        resources = [
            _unwrap_str(r, "", tf_vars)
            for r in (_as_list(raw_st.get("resources")) + _as_list(raw_st.get("resource")))
            if _unwrap_str(r, "", tf_vars)
        ]
        stmt_obj: Dict[str, Any] = {
            "Sid": _unwrap_str(raw_st.get("sid"), "", tf_vars) or None,
            "Effect": effect,
            "Action": actions,
            "Resource": resources,
        }
        principals_dict: Dict[str, List[str]] = {}
        for pr in _as_list(raw_st.get("principals")):
            if not isinstance(pr, dict):
                continue
            ptype = _unwrap_str(pr.get("type"), "AWS", tf_vars) or "AWS"
            pids = [_unwrap_str(x, "", tf_vars) for x in _as_list(pr.get("identifiers")) if _unwrap_str(x, "", tf_vars)]
            if pids:
                principals_dict.setdefault(ptype, []).extend(pids)
        if principals_dict:
            stmt_obj["Principal"] = principals_dict
        stmts.append(stmt_obj)
    return {"Version": "2012-10-17", "Statement": stmts}


def _parse_policy_json(
    raw_policy: Any,
    *,
    data_docs: Optional[Dict[str, Dict[str, Any]]] = None,
    tf_vars: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if isinstance(raw_policy, dict):
        return _clean_hcl_obj(raw_policy)
    s = _unwrap_str(raw_policy, "", tf_vars).strip()
    if not s:
        return {}

    # Resolve data.aws_iam_policy_document.<name>.json references
    inner_expr = s[2:-1].strip() if (s.startswith("${") and s.endswith("}")) else s
    m_doc = re.search(r"data\.aws_iam_policy_document\.([A-Za-z0-9_-]+)\.json", inner_expr)
    if m_doc and data_docs and m_doc.group(1) in data_docs:
        return data_docs[m_doc.group(1)]

    if s.startswith("${jsonencode(") and s.endswith(")}"):
        inner = s[len("${jsonencode(") : -2].strip()
        if HCL2_AVAILABLE and hcl2 is not None:
            try:
                parsed_inner = _clean_hcl_obj(hcl2.loads(f"doc = {inner}"))
                doc = parsed_inner.get("doc")
                if isinstance(doc, dict):
                    return doc
            except Exception:
                pass
        try:
            return json.loads(inner)
        except Exception:
            pass
    try:
        return json.loads(s)
    except Exception:
        return {}


def _iter_typed_blocks(block: Any) -> List[Tuple[str, str, Dict[str, Any]]]:
    out: List[Tuple[str, str, Dict[str, Any]]] = []
    if isinstance(block, dict):
        for rtype, instances in block.items():
            if isinstance(instances, dict):
                for rname, attrs in instances.items():
                    if isinstance(attrs, dict):
                        out.append((rtype, rname, attrs))
    elif isinstance(block, list):
        for item in block:
            if not isinstance(item, dict):
                continue
            for rtype, instances in item.items():
                if isinstance(instances, dict):
                    for rname, attrs in instances.items():
                        if isinstance(attrs, dict):
                            out.append((rtype, rname, attrs))
    return out


def _parse_tfvars_file(path: Path) -> Dict[str, str]:
    """Parse *.tfvars and *.tfvars.json into flat string variable overrides."""
    text = path.read_text(encoding="utf-8", errors="replace")
    parsed: Dict[str, Any] = {}
    if path.suffix == ".json" or path.name.endswith(".tfvars.json"):
        try:
            raw = json.loads(text)
            if isinstance(raw, dict):
                parsed = raw
        except Exception:
            parsed = {}
    elif HCL2_AVAILABLE and hcl2 is not None:
        try:
            parsed = _clean_hcl_obj(hcl2.loads(text))
        except Exception:
            parsed = {}
    else:
        for line in text.splitlines():
            m = re.match(r'^\s*([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"', line)
            if m:
                parsed[m.group(1)] = m.group(2)

    out: Dict[str, str] = {}
    for k, v in parsed.items():
        if isinstance(v, list) and len(v) == 1:
            v = v[0]
        if isinstance(v, bool):
            out[str(k)] = "true" if v else "false"
        elif isinstance(v, (str, int, float)):
            out[str(k)] = _strip_quotes(str(v))
    return out


def _parse_tf_file(
    path: Path,
) -> Tuple[
    List[Tuple[str, str, Dict[str, Any]]],
    List[Tuple[str, str, Dict[str, Any]]],
    Dict[str, str],
    Dict[str, str],
    Optional[str],
    str,
]:
    text = path.read_text(encoding="utf-8", errors="replace")
    parsed: Dict[str, Any] = {}
    if path.suffix == ".json" or path.name.endswith(".tf.json"):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {}
    elif HCL2_AVAILABLE and hcl2 is not None:
        try:
            parsed = _clean_hcl_obj(hcl2.loads(text))
        except Exception:
            parsed = {}

    tf_vars: Dict[str, str] = {}
    var_block = parsed.get("variable", [])
    var_dicts = [var_block] if isinstance(var_block, dict) else (var_block if isinstance(var_block, list) else [])
    for item in var_dicts:
        if not isinstance(item, dict):
            continue
        for vname, vattrs in item.items():
            if isinstance(vattrs, dict) and "default" in vattrs and vattrs["default"] is not None:
                val = vattrs["default"]
                if isinstance(val, list) and val:
                    val = val[0]
                if isinstance(val, bool):
                    tf_vars[str(vname)] = "true" if val else "false"
                elif isinstance(val, (str, int, float)):
                    tf_vars[str(vname)] = _strip_quotes(str(val))

    tf_locals: Dict[str, str] = {}
    loc_block = parsed.get("locals", [])
    loc_dicts = [loc_block] if isinstance(loc_block, dict) else (loc_block if isinstance(loc_block, list) else [])
    for item in loc_dicts:
        if not isinstance(item, dict):
            continue
        for lname, lval in item.items():
            if isinstance(lval, list) and len(lval) == 1:
                lval = lval[0]
            if isinstance(lval, bool):
                tf_locals[str(lname)] = "true" if lval else "false"
            elif isinstance(lval, (str, int, float)):
                tf_locals[str(lname)] = _strip_quotes(str(lval))

    provider_region: Optional[str] = None
    prov_block = parsed.get("provider", [])
    prov_dicts = [prov_block] if isinstance(prov_block, dict) else (prov_block if isinstance(prov_block, list) else [])
    for item in prov_dicts:
        if not isinstance(item, dict):
            continue
        aws_cfg = item.get("aws")
        for cfg in _as_list(aws_cfg):
            if isinstance(cfg, dict) and not cfg.get("alias") and cfg.get("region"):
                provider_region = _strip_quotes(str(cfg["region"]))
                break

    resources = _iter_typed_blocks(parsed.get("resource", []))
    data_blocks = _iter_typed_blocks(parsed.get("data", []))
    return resources, data_blocks, tf_vars, tf_locals, provider_region, text


def _fallback_eval(resource: Dict[str, Any]) -> Tuple[set[str], set[str]]:
    """Deterministic Python mirror used ONLY when opa binary is absent on host."""
    deny: set[str] = set()
    warn: set[str] = set()
    rtype = resource.get("resource_type")

    if rtype == "AWSS3Bucket":
        if resource.get("default_encryption") is not True:
            deny.add("dpdp.rule6a")
            deny.add("cis.s3_default_encryption")
        elif resource.get("encryption_algorithm") not in {"AES256", "aws:kms", "aws:kms:dsse"}:
            deny.add("dpdp.rule6a")
            deny.add("cis.s3_default_encryption")

        if not all(
            resource.get(k) is True
            for k in (
                "block_public_acls",
                "block_public_policy",
                "ignore_public_acls",
                "restrict_public_buckets",
            )
        ):
            deny.add("dpdp.rule6_public_exposure")
            deny.add("cis.s3_public_access_block")

        if resource.get("personal_data") is True and resource.get("versioning_status") != "Enabled":
            deny.add("dpdp.rule6_versioning")
        if resource.get("logging_enabled") is not True:
            deny.add("dpdp.rule6_logging")
        if resource.get("personal_data") is True and resource.get("has_lifecycle_expiration") is not True:
            deny.add("dpdp.rule8_lifecycle")
        approved = resource.get("approved_regions") or []
        if resource.get("personal_data") is True and approved and resource.get("region") not in approved:
            warn.add("dpdp.rule15_region")

    elif rtype == "AWSIpPermissionInbound":
        if resource.get("ip_range") in {"0.0.0.0/0", "::/0"}:
            proto = str(resource.get("protocol", ""))
            fp = int(resource.get("fromport", 0))
            tp = int(resource.get("toport", 65535))
            sensitive = {22, 3389, 3306, 5432, 1433, 27017, 6379}
            if proto == "-1" or any(fp <= p <= tp for p in sensitive):
                deny.add("dpdp.rule6_sg_open_ingress")
                deny.add("cis.sg_open_ingress")

    elif rtype == "AWSPolicyStatement":
        if str(resource.get("effect", "")).lower() == "allow":
            acts = [str(x) for x in _as_list(resource.get("action"))]
            res = [str(x) for x in _as_list(resource.get("resource"))]
            if "*" in acts and "*" in res:
                deny.add("cis.iam_no_full_admin")

    elif rtype == "AWSRDSInstance":
        if resource.get("storage_encrypted") is not True:
            deny.add("dpdp.rule6a_rds")

    elif rtype == "AWSAccount":
        if resource.get("account_mfa_enabled") is not True:
            deny.add("dpdp.rule6_account_mfa")
        if resource.get("cloudtrail_enabled") is False:
            deny.add("dpdp.rule7_detection")

    return deny, warn


def _tfvars_sort_key(path: Path) -> Tuple[int, str]:
    name = path.name.lower()
    if name.endswith(".auto.tfvars") or name.endswith(".auto.tfvars.json"):
        return (2, str(path))
    if name in ("terraform.tfvars", "terraform.tfvars.json"):
        return (1, str(path))
    return (0, str(path))


def scan_terraform_directory(
    directory: str | Path,
    *,
    approved_regions: Optional[List[str]] = None,
    use_opa: bool = True,
) -> Dict[str, Any]:
    """Scan local .tf / .tf.json / .tfvars files, evaluate via Rego, and return raw findings + LocalCartographySession."""
    root = Path(directory).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Terraform directory does not exist: {root}")

    tf_files = sorted(
        p
        for p in root.rglob("*")
        if p.is_file()
        and (p.suffix == ".tf" or p.name.endswith(".tf.json"))
        and ".terraform" not in p.parts
        and ".git" not in p.parts
    )
    if not tf_files:
        raise ValueError(f"No .tf or .tf.json files found under {root}")

    tfvars_files = sorted(
        (
            p
            for p in root.rglob("*")
            if p.is_file()
            and (p.suffix == ".tfvars" or p.name.endswith(".tfvars.json"))
            and ".terraform" not in p.parts
            and ".git" not in p.parts
        ),
        key=_tfvars_sort_key,
    )

    approved = approved_regions or ["ap-south-1", "ap-south-2"]
    default_region = approved[0]

    # Collect parsed resources, data blocks, variable defaults, locals, and provider region
    all_blocks: List[Tuple[Path, str, str, Dict[str, Any], str]] = []
    raw_data_blocks: List[Tuple[Path, str, str, Dict[str, Any]]] = []
    tf_vars: Dict[str, str] = {}
    tf_locals: Dict[str, str] = {}
    provider_region: Optional[str] = None
    for path in tf_files:
        blocks, data_blocks, file_vars, file_locals, prov_reg, text = _parse_tf_file(path)
        tf_vars.update(file_vars)
        tf_locals.update(file_locals)
        if prov_reg and not provider_region:
            provider_region = prov_reg
        for rtype, rname, attrs in blocks:
            snippet = _extract_hcl_snippet(text, rtype, rname, keyword="resource")
            all_blocks.append((path, rtype, rname, attrs, snippet))
        for dtype, dname, attrs in data_blocks:
            raw_data_blocks.append((path, dtype, dname, attrs))

    # Apply *.tfvars / *.tfvars.json overrides on top of variable defaults
    for vf in tfvars_files:
        tf_vars.update(_parse_tfvars_file(vf))

    if provider_region:
        resolved_prov = _unwrap_str(provider_region, "", tf_vars, tf_locals)
        if resolved_prov and not _is_unresolved_expr(resolved_prov):
            default_region = resolved_prov

    # Build data "aws_iam_policy_document" map once tf_vars are complete
    data_policy_docs: Dict[str, Dict[str, Any]] = {}
    for _path, dtype, dname, attrs in raw_data_blocks:
        if dtype == "aws_iam_policy_document":
            data_policy_docs[dname] = _convert_data_policy_doc(attrs, tf_vars=tf_vars)

    buckets: Dict[str, Dict[str, Any]] = {}
    bucket_by_tf_name: Dict[str, str] = {}
    bucket_by_dir_tf_name: Dict[Tuple[str, str], str] = {}
    sgs: Dict[str, Dict[str, Any]] = {}
    users: Dict[str, Dict[str, Any]] = {}
    roles: Dict[str, Dict[str, Any]] = {}
    policies: Dict[str, Dict[str, Any]] = {}
    keys: List[Dict[str, Any]] = []
    trusts: List[Dict[str, Any]] = []
    statements_graph: List[Dict[str, Any]] = []
    rds_instances: List[Dict[str, Any]] = []
    cloudtrail_enabled: Optional[bool] = None

    # Pass 1: primary entities (buckets, SGs, IAM users/roles/policies, RDS, CloudTrail)
    for path, rtype, rname, attrs, snippet in all_blocks:
        if rtype == "aws_s3_bucket":
            bname = _unwrap_str(attrs.get("bucket") or attrs.get("bucket_prefix"), rname, tf_vars, tf_locals)
            if not bname or _is_unresolved_expr(bname):
                bname = rname
            tags = attrs.get("tags") if isinstance(attrs.get("tags"), dict) else {}
            if isinstance(tags, list) and tags and isinstance(tags[0], dict):
                tags = tags[0]
            personal_data = (
                str(tags.get("contains_personal_data", "")).lower() == "true"
                or any(k in bname.lower() for k in ("pii", "kyc", "patient", "health", "citizen", "customer", "user"))
            )
            region = _unwrap_str(attrs.get("region"), default_region, tf_vars, tf_locals)
            if not region or _is_unresolved_expr(region):
                region = default_region
            inline_acl = _unwrap_str(attrs.get("acl"), "", tf_vars, tf_locals).lower()
            buckets[bname] = {
                "tf_name": rname,
                "name": bname,
                "arn": f"arn:aws:s3:::{bname}",
                "region": region,
                "approved_regions": approved,
                "personal_data": personal_data,
                "default_encryption": False,
                "encryption_algorithm": "none",
                "block_public_acls": False,
                "block_public_policy": False,
                "ignore_public_acls": False,
                "restrict_public_buckets": False,
                "public_acl": inline_acl in _PUBLIC_ACL_VALUES,
                "acl_hcl": "",
                "versioning_status": "Suspended",
                "logging_enabled": False,
                "has_lifecycle_expiration": False,
                "tags": tags,
                "source_file": str(path),
                "hcl_before": snippet,
            }
            bucket_by_tf_name[rname] = bname
            bucket_by_dir_tf_name[(str(path.parent), rname)] = bname

            # Inline versioning / logging / SSE (Terraform AWS provider v3 style)
            if attrs.get("versioning"):
                v_list = _as_list(attrs.get("versioning"))
                if v_list and isinstance(v_list[0], dict) and _unwrap_bool(v_list[0].get("enabled"), False, tf_vars):
                    buckets[bname]["versioning_status"] = "Enabled"
            if attrs.get("logging"):
                buckets[bname]["logging_enabled"] = True
            if attrs.get("server_side_encryption_configuration"):
                buckets[bname]["default_encryption"] = True
                buckets[bname]["encryption_algorithm"] = "AES256"
            if attrs.get("lifecycle_rule"):
                buckets[bname]["has_lifecycle_expiration"] = True

        elif rtype == "aws_security_group":
            sgname = _unwrap_str(attrs.get("name"), rname, tf_vars, tf_locals)
            if not sgname or _is_unresolved_expr(sgname):
                sgname = rname
            sgid = f"sg-{rname}"
            vpc_ref = _unwrap_str(attrs.get("vpc_id"), "vpc-main", tf_vars, tf_locals)
            if not vpc_ref or _is_unresolved_expr(vpc_ref):
                vpc_ref = "vpc-main"
            sgs[rname] = {
                "sgid": sgid,
                "sgname": sgname,
                "vpc_id": vpc_ref,
                "ingress": _as_list(attrs.get("ingress")),
                "source_file": str(path),
                "hcl_before": snippet,
            }

        elif rtype == "aws_iam_user":
            uname = _unwrap_str(attrs.get("name"), rname, tf_vars, tf_locals)
            if not uname or _is_unresolved_expr(uname):
                uname = rname
            uarn = f"arn:aws:iam::local:user/{uname}"
            users[rname] = {"id": uarn, "name": uname, "labels": ["AWSPrincipal", "AWSUser"]}

        elif rtype == "aws_iam_role":
            role_name = _unwrap_str(attrs.get("name"), rname, tf_vars, tf_locals)
            if not role_name or _is_unresolved_expr(role_name):
                role_name = rname
            rarn = f"arn:aws:iam::local:role/{role_name}"
            roles[rname] = {"id": rarn, "name": role_name, "labels": ["AWSPrincipal", "AWSRole"]}
            assume_doc = _parse_policy_json(
                attrs.get("assume_role_policy"), data_docs=data_policy_docs, tf_vars=tf_vars
            )
            for stmt in _as_list(assume_doc.get("Statement")):
                if not isinstance(stmt, dict):
                    continue
                princ = stmt.get("Principal")
                if isinstance(princ, dict):
                    aws_p = _as_list(princ.get("AWS"))
                    for p_ref in aws_p:
                        p_str = _unwrap_str(p_ref, "", tf_vars, tf_locals)
                        if p_str:
                            trusts.append({"rid": rarn, "pid": p_str})
            # Support inline_policy nested blocks on aws_iam_role
            for ip_idx, ip_blk in enumerate(_as_list(attrs.get("inline_policy"))):
                if not isinstance(ip_blk, dict):
                    continue
                ip_name = _unwrap_str(ip_blk.get("name"), f"{role_name}-inline-{ip_idx}", tf_vars, tf_locals)
                ip_doc = _parse_policy_json(ip_blk.get("policy"), data_docs=data_policy_docs, tf_vars=tf_vars)
                polid = f"arn:aws:iam::local:inline-policy/{role_name}/{ip_name}"
                for sidx, stmt in enumerate(_as_list(ip_doc.get("Statement"))):
                    if not isinstance(stmt, dict):
                        continue
                    statements_graph.append(
                        {
                            "pid": rarn,
                            "polid": polid,
                            "polname": ip_name,
                            "stmt_id": f"{polid}#stmt{sidx}",
                            "stmt_sid": stmt.get("Sid") or f"stmt{sidx}",
                            "effect": stmt.get("Effect", "Allow"),
                            "action": _as_list(stmt.get("Action")),
                            "resource": _as_list(stmt.get("Resource")),
                            "source_file": str(path),
                            "hcl_before": snippet,
                        }
                    )

        elif rtype == "aws_iam_policy":
            pname = _unwrap_str(attrs.get("name"), rname, tf_vars, tf_locals)
            if not pname or _is_unresolved_expr(pname):
                pname = rname
            parn = f"arn:aws:iam::local:policy/{pname}"
            doc = _parse_policy_json(attrs.get("policy"), data_docs=data_policy_docs, tf_vars=tf_vars)
            policies[rname] = {
                "polid": parn,
                "polname": pname,
                "doc": doc,
                "source_file": str(path),
                "hcl_before": snippet,
            }

        elif rtype == "aws_db_instance":
            db_id = _unwrap_str(attrs.get("identifier"), rname, tf_vars, tf_locals)
            if not db_id or _is_unresolved_expr(db_id):
                db_id = rname
            az_raw = _unwrap_str(attrs.get("availability_zone"), "", tf_vars, tf_locals)
            rds_region = _az_to_region(az_raw, default_region)
            rds_instances.append(
                {
                    "resource_type": "AWSRDSInstance",
                    "id": db_id,
                    "name": db_id,
                    "storage_encrypted": _unwrap_bool(attrs.get("storage_encrypted"), False, tf_vars),
                    "region": rds_region,
                    "approved_regions": approved,
                    "personal_data": True,
                    "source_file": str(path),
                    "hcl_before": snippet,
                }
            )

        elif rtype == "aws_cloudtrail":
            cloudtrail_enabled = _unwrap_bool(attrs.get("enable_logging"), True, tf_vars)

    # Helper lookup tables by resource name as well as TF identifier
    role_by_name = {v["name"]: v for v in roles.values()}
    user_by_name = {v["name"]: v for v in users.values()}

    # Pass 2: companion resources (v4 S3 blocks, ACLs, IAM keys, inline policies, attachments)
    for path, rtype, rname, attrs, snippet in all_blocks:
        src_dir = str(path.parent)
        if rtype == "aws_s3_bucket_public_access_block":
            bname = _resolve_bucket_ref(
                attrs.get("bucket"),
                bucket_by_tf_name,
                by_dir_tf_name=bucket_by_dir_tf_name,
                source_dir=src_dir,
                tf_vars=tf_vars,
            )
            if bname and bname in buckets:
                buckets[bname]["block_public_acls"] = _unwrap_bool(attrs.get("block_public_acls"), False, tf_vars)
                buckets[bname]["block_public_policy"] = _unwrap_bool(attrs.get("block_public_policy"), False, tf_vars)
                buckets[bname]["ignore_public_acls"] = _unwrap_bool(attrs.get("ignore_public_acls"), False, tf_vars)
                buckets[bname]["restrict_public_buckets"] = _unwrap_bool(attrs.get("restrict_public_buckets"), False, tf_vars)
                buckets[bname]["hcl_before"] = snippet
                buckets[bname]["source_file"] = str(path)

        elif rtype == "aws_s3_bucket_acl":
            bname = _resolve_bucket_ref(
                attrs.get("bucket"),
                bucket_by_tf_name,
                by_dir_tf_name=bucket_by_dir_tf_name,
                source_dir=src_dir,
                tf_vars=tf_vars,
            )
            acl_val = _unwrap_str(attrs.get("acl"), "", tf_vars).lower()
            acp_txt = json.dumps(attrs.get("access_control_policy") or {})
            is_public_grant = (
                "AllUsers" in acp_txt or "AuthenticatedUsers" in acp_txt or acl_val in _PUBLIC_ACL_VALUES
            )
            if bname and bname in buckets and is_public_grant:
                buckets[bname]["public_acl"] = True
                buckets[bname]["acl_hcl"] = snippet

        elif rtype == "aws_s3_bucket_server_side_encryption_configuration":
            bname = _resolve_bucket_ref(
                attrs.get("bucket"),
                bucket_by_tf_name,
                by_dir_tf_name=bucket_by_dir_tf_name,
                source_dir=src_dir,
                tf_vars=tf_vars,
            )
            if bname and bname in buckets:
                buckets[bname]["default_encryption"] = True
                alg = "AES256"
                for rule in _as_list(attrs.get("rule")):
                    if isinstance(rule, dict):
                        for d in _as_list(rule.get("apply_server_side_encryption_by_default")):
                            if isinstance(d, dict) and d.get("sse_algorithm"):
                                alg = _unwrap_str(d.get("sse_algorithm"), "AES256", tf_vars)
                buckets[bname]["encryption_algorithm"] = alg

        elif rtype == "aws_s3_bucket_versioning":
            bname = _resolve_bucket_ref(
                attrs.get("bucket"),
                bucket_by_tf_name,
                by_dir_tf_name=bucket_by_dir_tf_name,
                source_dir=src_dir,
                tf_vars=tf_vars,
            )
            if bname and bname in buckets:
                for cfg in _as_list(attrs.get("versioning_configuration")):
                    if isinstance(cfg, dict) and cfg.get("status"):
                        buckets[bname]["versioning_status"] = _unwrap_str(cfg.get("status"), "Suspended", tf_vars)

        elif rtype == "aws_s3_bucket_logging":
            bname = _resolve_bucket_ref(
                attrs.get("bucket"),
                bucket_by_tf_name,
                by_dir_tf_name=bucket_by_dir_tf_name,
                source_dir=src_dir,
                tf_vars=tf_vars,
            )
            if bname and bname in buckets:
                buckets[bname]["logging_enabled"] = bool(attrs.get("target_bucket"))

        elif rtype == "aws_s3_bucket_lifecycle_configuration":
            bname = _resolve_bucket_ref(
                attrs.get("bucket"),
                bucket_by_tf_name,
                by_dir_tf_name=bucket_by_dir_tf_name,
                source_dir=src_dir,
                tf_vars=tf_vars,
            )
            if bname and bname in buckets:
                for rule in _as_list(attrs.get("rule")):
                    if isinstance(rule, dict) and str(_unwrap_str(rule.get("status"), "Enabled", tf_vars)).lower() == "enabled":
                        if rule.get("expiration"):
                            buckets[bname]["has_lifecycle_expiration"] = True

        elif rtype == "aws_s3_bucket_policy":
            bname = _resolve_bucket_ref(
                attrs.get("bucket"),
                bucket_by_tf_name,
                by_dir_tf_name=bucket_by_dir_tf_name,
                source_dir=src_dir,
                tf_vars=tf_vars,
            )
            pdoc = _parse_policy_json(attrs.get("policy"), data_docs=data_policy_docs, tf_vars=tf_vars)
            for stmt in _as_list(pdoc.get("Statement")):
                if not isinstance(stmt, dict):
                    continue
                if str(stmt.get("Effect", "")).lower() != "allow":
                    continue
                princ = stmt.get("Principal")
                is_star = (
                    princ == "*"
                    or (isinstance(princ, dict) and "*" in _as_list(princ.get("AWS")))
                )
                if is_star and not stmt.get("Condition") and bname and bname in buckets:
                    buckets[bname]["policy_hcl"] = snippet

        elif rtype == "aws_vpc_security_group_ingress_rule":
            sg_ref = _unwrap_str(attrs.get("security_group_id"), rname, tf_vars, tf_locals)
            sm = re.search(r"aws_security_group\.([A-Za-z0-9_-]+)(?:\[[^\]]+\])?\.", sg_ref)
            sg_key = sm.group(1) if sm and sm.group(1) in sgs else rname
            if sg_key not in sgs:
                sgs[sg_key] = {
                    "sgid": f"sg-{sg_key}",
                    "sgname": sg_key,
                    "vpc_id": "vpc-main",
                    "ingress": [],
                    "source_file": str(path),
                    "hcl_before": snippet,
                }
            cidr4 = _unwrap_str(attrs.get("cidr_ipv4"), "", tf_vars, tf_locals)
            cidr6 = _unwrap_str(attrs.get("cidr_ipv6"), "", tf_vars, tf_locals)
            sgs[sg_key]["ingress"].append(
                {
                    "cidr_blocks": [cidr4] if cidr4 else [],
                    "ipv6_cidr_blocks": [cidr6] if cidr6 else [],
                    "from_port": _safe_int(attrs.get("from_port"), 0, tf_vars),
                    "to_port": _safe_int(attrs.get("to_port"), 65535, tf_vars),
                    "protocol": _unwrap_str(attrs.get("ip_protocol"), "-1", tf_vars, tf_locals),
                }
            )

        elif rtype == "aws_iam_access_key":
            user_ref = _unwrap_str(attrs.get("user"), "", tf_vars, tf_locals)
            m = re.search(r"aws_iam_user\.([A-Za-z0-9_-]+)(?:\[[^\]]+\])?\.", user_ref)
            uid = (
                users[m.group(1)]["id"]
                if (m and m.group(1) in users)
                else (
                    user_by_name[user_ref]["id"]
                    if user_ref in user_by_name
                    else (f"arn:aws:iam::local:user/{user_ref}" if user_ref else None)
                )
            )
            if uid:
                keys.append(
                    {
                        "uid": uid,
                        "kid": f"AKIA-{rname.upper()[:12]}",
                        "status": _unwrap_str(attrs.get("status"), "Active", tf_vars, tf_locals),
                    }
                )

        elif rtype in ("aws_iam_role_policy", "aws_iam_user_policy"):
            pname = _unwrap_str(attrs.get("name") or attrs.get("name_prefix"), rname, tf_vars, tf_locals) or rname
            doc = _parse_policy_json(attrs.get("policy"), data_docs=data_policy_docs, tf_vars=tf_vars)
            pid = None
            if rtype == "aws_iam_role_policy":
                r_ref = _unwrap_str(attrs.get("role"), "", tf_vars, tf_locals)
                rm = re.search(r"aws_iam_role\.([A-Za-z0-9_-]+)(?:\[[^\]]+\])?\.", r_ref)
                if rm and rm.group(1) in roles:
                    pid = roles[rm.group(1)]["id"]
                elif r_ref in role_by_name:
                    pid = role_by_name[r_ref]["id"]
            else:
                u_ref = _unwrap_str(attrs.get("user"), "", tf_vars, tf_locals)
                um = re.search(r"aws_iam_user\.([A-Za-z0-9_-]+)(?:\[[^\]]+\])?\.", u_ref)
                if um and um.group(1) in users:
                    pid = users[um.group(1)]["id"]
                elif u_ref in user_by_name:
                    pid = user_by_name[u_ref]["id"]

            polid = f"arn:aws:iam::local:inline-policy/{rname}"
            for idx, stmt in enumerate(_as_list(doc.get("Statement"))):
                if not isinstance(stmt, dict):
                    continue
                statements_graph.append(
                    {
                        "pid": pid,
                        "polid": polid,
                        "polname": pname,
                        "stmt_id": f"{polid}#stmt{idx}",
                        "stmt_sid": stmt.get("Sid") or f"stmt{idx}",
                        "effect": stmt.get("Effect", "Allow"),
                        "action": _as_list(stmt.get("Action")),
                        "resource": _as_list(stmt.get("Resource")),
                        "source_file": str(path),
                        "hcl_before": snippet,
                    }
                )

        elif rtype in ("aws_iam_role_policy_attachment", "aws_iam_user_policy_attachment", "aws_iam_policy_attachment"):
            pol_ref = _unwrap_str(attrs.get("policy_arn"), "", tf_vars, tf_locals)
            pm = re.search(r"aws_iam_policy\.([A-Za-z0-9_-]+)(?:\[[^\]]+\])?\.", pol_ref)
            pol = policies.get(pm.group(1)) if pm else None
            target_pids: List[str] = []
            if rtype == "aws_iam_role_policy_attachment":
                r_refs = [attrs.get("role")]
                u_refs: List[Any] = []
            elif rtype == "aws_iam_user_policy_attachment":
                r_refs = []
                u_refs = [attrs.get("user")]
            else:
                r_refs = _as_list(attrs.get("roles"))
                u_refs = _as_list(attrs.get("users"))

            for raw_r in r_refs:
                r_ref = _unwrap_str(raw_r, "", tf_vars, tf_locals)
                rm = re.search(r"aws_iam_role\.([A-Za-z0-9_-]+)(?:\[[^\]]+\])?\.", r_ref)
                if rm and rm.group(1) in roles:
                    target_pids.append(roles[rm.group(1)]["id"])
                elif r_ref in role_by_name:
                    target_pids.append(role_by_name[r_ref]["id"])

            for raw_u in u_refs:
                u_ref = _unwrap_str(raw_u, "", tf_vars, tf_locals)
                um = re.search(r"aws_iam_user\.([A-Za-z0-9_-]+)(?:\[[^\]]+\])?\.", u_ref)
                if um and um.group(1) in users:
                    target_pids.append(users[um.group(1)]["id"])
                elif u_ref in user_by_name:
                    target_pids.append(user_by_name[u_ref]["id"])

            for pid in target_pids:
                if pol:
                    for idx, stmt in enumerate(_as_list(pol["doc"].get("Statement"))):
                        if not isinstance(stmt, dict):
                            continue
                        statements_graph.append(
                            {
                                "pid": pid,
                                "polid": pol["polid"],
                                "polname": pol["polname"],
                                "stmt_id": f"{pol['polid']}#stmt{idx}",
                                "stmt_sid": stmt.get("Sid") or f"stmt{idx}",
                                "effect": stmt.get("Effect", "Allow"),
                                "action": _as_list(stmt.get("Action")),
                                "resource": _as_list(stmt.get("Resource")),
                                "source_file": pol["source_file"],
                                "hcl_before": pol["hcl_before"],
                            }
                        )
                elif pol_ref.endswith("/AdministratorAccess"):
                    statements_graph.append(
                        {
                            "pid": pid,
                            "polid": pol_ref,
                            "polname": "AdministratorAccess",
                            "stmt_id": f"{pol_ref}#stmt0",
                            "stmt_sid": "AdminManaged",
                            "effect": "Allow",
                            "action": ["*"],
                            "resource": ["*"],
                            "source_file": str(path),
                            "hcl_before": snippet,
                        }
                    )

    # Ensure public ACLs override PAB status regardless of resource order
    for b in buckets.values():
        if b.get("public_acl"):
            b["block_public_acls"] = False
            b["ignore_public_acls"] = False
            if b.get("acl_hcl") and b["acl_hcl"] not in b["hcl_before"]:
                b["hcl_before"] = f"{b['hcl_before']}\n\n{b['acl_hcl']}".strip()
        if b.get("policy_hcl") and b["policy_hcl"] not in b["hcl_before"]:
            b["hcl_before"] = f"{b['hcl_before']}\n\n{b['policy_hcl']}".strip()

    # Also capture unattached IAM policies for Rego auditing
    attached_pol_ids = {s["polid"] for s in statements_graph}
    for pol in policies.values():
        if pol["polid"] not in attached_pol_ids:
            for idx, stmt in enumerate(_as_list(pol["doc"].get("Statement"))):
                if not isinstance(stmt, dict):
                    continue
                statements_graph.append(
                    {
                        "pid": None,
                        "polid": pol["polid"],
                        "polname": pol["polname"],
                        "stmt_id": f"{pol['polid']}#stmt{idx}",
                        "stmt_sid": stmt.get("Sid") or f"stmt{idx}",
                        "effect": stmt.get("Effect", "Allow"),
                        "action": _as_list(stmt.get("Action")),
                        "resource": _as_list(stmt.get("Resource")),
                        "source_file": pol["source_file"],
                        "hcl_before": pol["hcl_before"],
                    }
                )

    # Build Rego evaluation records + LocalCartographySession
    eval_items: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for b in buckets.values():
        rego_res = {
            "resource_type": "AWSS3Bucket",
            "name": b["name"],
            "arn": b["arn"],
            "region": b["region"],
            "approved_regions": b["approved_regions"],
            "personal_data": b["personal_data"],
            "default_encryption": b["default_encryption"],
            "encryption_algorithm": b["encryption_algorithm"],
            "block_public_acls": b["block_public_acls"],
            "block_public_policy": b["block_public_policy"],
            "ignore_public_acls": b["ignore_public_acls"],
            "restrict_public_buckets": b["restrict_public_buckets"],
            "versioning_status": b["versioning_status"],
            "logging_enabled": b["logging_enabled"],
            "has_lifecycle_expiration": b["has_lifecycle_expiration"],
        }
        eval_items.append((rego_res, {"id": b["arn"], "name": b["name"], "source_file": b["source_file"], "hcl_before": b["hcl_before"]}))

    net_rules_graph: List[Dict[str, Any]] = []
    sg_vpcs_graph: List[Dict[str, Any]] = []
    for sg in sgs.values():
        sg_vpcs_graph.append({"sgid": sg["sgid"], "vpcid": sg["vpc_id"]})
        for idx, ing in enumerate(sg["ingress"]):
            if not isinstance(ing, dict):
                continue
            cidrs = _as_list(ing.get("cidr_blocks")) + _as_list(ing.get("ipv6_cidr_blocks"))
            fp = _safe_int(ing.get("from_port"), 0, tf_vars)
            tp = _safe_int(ing.get("to_port"), 65535, tf_vars)
            proto = _unwrap_str(ing.get("protocol"), "-1", tf_vars)
            for cidr_raw in cidrs:
                cidr = _unwrap_str(cidr_raw, "", tf_vars)
                if not cidr:
                    continue
                rule_id = f"{sg['sgid']}:in:{idx}:{cidr}"
                rego_res = {
                    "resource_type": "AWSIpPermissionInbound",
                    "ip_range": str(cidr),
                    "protocol": proto,
                    "fromport": fp,
                    "toport": tp,
                }
                eval_items.append(
                    (
                        rego_res,
                        {
                            "id": sg["sgid"],
                            "name": sg["sgname"],
                            "source_file": sg["source_file"],
                            "hcl_before": sg["hcl_before"],
                        },
                    )
                )
                if str(cidr) in ("0.0.0.0/0", "::/0"):
                    net_rules_graph.append(
                        {
                            "rgid": str(cidr),
                            "rgrange": str(cidr),
                            "ruleid": rule_id,
                            "fp": fp,
                            "tp": tp,
                            "proto": proto,
                            "sgid": sg["sgid"],
                            "sgname": sg["sgname"],
                        }
                    )

    for st in statements_graph:
        rego_res = {
            "resource_type": "AWSPolicyStatement",
            "effect": st["effect"],
            "action": st["action"],
            "resource": st["resource"],
        }
        eval_items.append(
            (
                rego_res,
                {
                    "id": st["stmt_id"],
                    "name": st["polname"],
                    "source_file": st["source_file"],
                    "hcl_before": st["hcl_before"],
                },
            )
        )

    for rds in rds_instances:
        eval_items.append(
            (
                {k: v for k, v in rds.items() if k not in ("source_file", "hcl_before", "id", "name")},
                {
                    "id": rds["id"],
                    "name": rds["name"],
                    "source_file": rds["source_file"],
                    "hcl_before": rds["hcl_before"],
                },
            )
        )

    if cloudtrail_enabled is not None:
        eval_items.append(
            (
                {
                    "resource_type": "AWSAccount",
                    "account_mfa_enabled": True,
                    "cloudtrail_enabled": cloudtrail_enabled,
                },
                {
                    "id": "aws-account-local",
                    "name": "aws-account-local",
                    "source_file": str(tf_files[0]),
                    "hcl_before": f"cloudtrail_enabled = {str(cloudtrail_enabled).lower()}",
                },
            )
        )

    # Run OPA Rego (if available & enabled) or deterministic fallback
    opa_used = False
    opa_bin = find_opa_binary() if use_opa else None
    rego_inputs = [item[0] for item in eval_items]
    if rego_inputs and opa_bin and REGO_RUNNER_AVAILABLE and opa_evaluate is not None:
        try:
            verdicts = opa_evaluate(rego_inputs, policy_dir=get_policy_dir(), opa=opa_bin)
            opa_used = True
        except Exception:
            verdicts = None
    else:
        verdicts = None

    raw_findings: List[Dict[str, Any]] = []
    seen_keys = set()
    for idx, (rego_res, meta) in enumerate(eval_items):
        if verdicts is not None:
            deny_set = set(verdicts[idx].deny)
            warn_set = set(verdicts[idx].warn)
        else:
            deny_set, warn_set = _fallback_eval(rego_res)

        for rule_id in sorted(deny_set | warn_set):
            key = (meta["id"], rule_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            fid = f"F-TF-{len(raw_findings) + 1:03d}"
            raw_findings.append(
                {
                    "finding_id": fid,
                    "rule_id": rule_id,
                    "resource_id": meta["id"],
                    "resource_name": meta["name"],
                    "resource_type": rego_res["resource_type"],
                    "is_warning": rule_id in warn_set and rule_id not in deny_set,
                    "source_file": meta["source_file"],
                    "hcl_before": meta["hcl_before"],
                    "attributes": dict(rego_res),
                }
            )

    session = LocalCartographySession(
        principals=list(users.values()) + list(roles.values()),
        keys=keys,
        trusts=trusts,
        buckets=[
            {"id": b["arn"], "name": b["name"], "props": {"contains_personal_data": b["personal_data"]}}
            for b in buckets.values()
        ],
        bucket_tags=[],
        statements=[s for s in statements_graph if s.get("pid")],
        net_rules=net_rules_graph,
        sg_vpcs=sg_vpcs_graph,
    )

    return {
        "source_type": "terraform",
        "target": str(root),
        "files_scanned": [str(p) for p in tf_files],
        "tfvars_loaded": [str(p) for p in tfvars_files],
        "opa_used": opa_used,
        "opa_bin": opa_bin,
        "raw_findings": raw_findings,
        "session": session,
        "resource_counts": {
            "buckets": len(buckets),
            "security_groups": len(sgs),
            "iam_principals": len(users) + len(roles),
            "iam_statements": len(statements_graph),
            "rds_instances": len(rds_instances),
        },
    }
