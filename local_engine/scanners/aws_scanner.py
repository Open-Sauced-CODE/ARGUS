"""Read-only AWS control-plane scanner enforcing privacy.iam_guard BEFORE any resource read."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from local_engine.graph.inmemory_session import LocalCartographySession
from local_engine.paths import find_opa_binary, get_policy_dir
from local_engine.scanners.terraform_scanner import _fallback_eval

from privacy.iam_guard import (
    fetch_identity_policy_documents,
    find_forbidden_permissions,
    find_watchlist_permissions,
)

try:
    from ml.real_data.rego_runner import evaluate as opa_evaluate

    REGO_RUNNER_AVAILABLE = True
except Exception:
    opa_evaluate = None
    REGO_RUNNER_AVAILABLE = False


class IamGuardBlockedError(PermissionError):
    """Raised when the AWS scanner identity possesses forbidden data-plane permissions."""

    def __init__(self, message: str, forbidden: List[str], identity: str = ""):
        super().__init__(message)
        self.forbidden = forbidden
        self.identity = identity


def _build_boto_session(
    *,
    profile: Optional[str] = None,
    role_arn: Optional[str] = None,
    external_id: Optional[str] = None,
    region: str = "ap-south-1",
    boto3_module: Any = None,
):
    if boto3_module is None:
        import boto3 as boto3_module  # type: ignore

    base_session = (
        boto3_module.Session(profile_name=profile, region_name=region)
        if profile
        else boto3_module.Session(region_name=region)
    )
    if role_arn:
        sts = base_session.client("sts", region_name=region)
        assume_kwargs: Dict[str, Any] = {
            "RoleArn": role_arn,
            "RoleSessionName": "argus-local-audit",
        }
        if external_id:
            assume_kwargs["ExternalId"] = external_id
        creds = sts.assume_role(**assume_kwargs)["Credentials"]
        return boto3_module.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
            region_name=region,
        )
    return base_session


def scan_aws_account(
    *,
    profile: Optional[str] = None,
    role_arn: Optional[str] = None,
    external_id: Optional[str] = None,
    region: str = "ap-south-1",
    approved_regions: Optional[List[str]] = None,
    session: Any = None,
    use_opa: bool = True,
) -> Dict[str, Any]:
    """Run iam_guard Step Zero check, then scan AWS control-plane metadata only."""
    aws_session = session or _build_boto_session(
        profile=profile, role_arn=role_arn, external_id=external_id, region=region
    )

    # MANDATORY STEP ZERO: Verify control-plane-only IAM access BEFORE touching resources
    identity_name, policy_docs = fetch_identity_policy_documents(aws_session)
    forbidden = find_forbidden_permissions(policy_docs)
    watchlist = find_watchlist_permissions(policy_docs)
    if forbidden:
        raise IamGuardBlockedError(
            f"Scan blocked by privacy.iam_guard for identity '{identity_name}': "
            f"forbidden data-plane permissions detected ({', '.join(forbidden)}). "
            "Use a read-only SecurityAudit identity without s3:GetObject or secret read rights.",
            forbidden=forbidden,
            identity=identity_name,
        )

    approved = approved_regions or [region]
    s3 = aws_session.client("s3", region_name=region)
    ec2 = aws_session.client("ec2", region_name=region)
    iam = aws_session.client("iam", region_name=region)
    rds = aws_session.client("rds", region_name=region)
    ct = aws_session.client("cloudtrail", region_name=region)
    sts = aws_session.client("sts", region_name=region)

    caller = sts.get_caller_identity()
    account_id = str(caller.get("Account", "unknown"))

    eval_items: List[tuple[Dict[str, Any], Dict[str, Any]]] = []
    principals: List[Dict[str, Any]] = []
    keys: List[Dict[str, Any]] = []
    trusts: List[Dict[str, Any]] = []
    buckets_graph: List[Dict[str, Any]] = []
    statements_graph: List[Dict[str, Any]] = []
    net_rules_graph: List[Dict[str, Any]] = []
    sg_vpcs_graph: List[Dict[str, Any]] = []

    # 1. S3 Buckets (control-plane metadata only — zero GetObject)
    bucket_list = s3.list_buckets().get("Buckets", [])
    for b in bucket_list:
        bname = b["Name"]
        barn = f"arn:aws:s3:::{bname}"
        b_region = region
        try:
            loc = s3.get_bucket_location(Bucket=bname).get("LocationConstraint")
            b_region = loc or "us-east-1"
        except Exception:
            pass

        enc_enabled, enc_alg = False, "none"
        try:
            rules = s3.get_bucket_encryption(Bucket=bname)["ServerSideEncryptionConfiguration"]["Rules"]
            if rules:
                enc_enabled = True
                enc_alg = rules[0].get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm", "AES256")
        except Exception:
            pass

        pab = {
            "block_public_acls": False,
            "block_public_policy": False,
            "ignore_public_acls": False,
            "restrict_public_buckets": False,
        }
        try:
            cfg = s3.get_public_access_block(Bucket=bname)["PublicAccessBlockConfiguration"]
            pab = {
                "block_public_acls": bool(cfg.get("BlockPublicAcls", False)),
                "block_public_policy": bool(cfg.get("BlockPublicPolicy", False)),
                "ignore_public_acls": bool(cfg.get("IgnorePublicAcls", False)),
                "restrict_public_buckets": bool(cfg.get("RestrictPublicBuckets", False)),
            }
        except Exception:
            pass

        ver_status = "Suspended"
        try:
            ver_status = s3.get_bucket_versioning(Bucket=bname).get("Status", "Suspended") or "Suspended"
        except Exception:
            pass

        logging_enabled = False
        try:
            logging_enabled = bool(s3.get_bucket_logging(Bucket=bname).get("LoggingEnabled"))
        except Exception:
            pass

        has_lifecycle = False
        try:
            lc_rules = s3.get_bucket_lifecycle_configuration(Bucket=bname).get("Rules", [])
            has_lifecycle = any(r.get("Status") == "Enabled" and r.get("Expiration") for r in lc_rules)
        except Exception:
            pass

        personal_data = any(k in bname.lower() for k in ("pii", "kyc", "patient", "health", "citizen", "customer"))
        try:
            tags = s3.get_bucket_tagging(Bucket=bname).get("TagSet", [])
            if any(t.get("Key") == "contains_personal_data" and str(t.get("Value")).lower() == "true" for t in tags):
                personal_data = True
        except Exception:
            pass

        rego_res = {
            "resource_type": "AWSS3Bucket",
            "name": bname,
            "arn": barn,
            "region": b_region,
            "approved_regions": approved,
            "personal_data": personal_data,
            "default_encryption": enc_enabled,
            "encryption_algorithm": enc_alg,
            **pab,
            "versioning_status": ver_status,
            "logging_enabled": logging_enabled,
            "has_lifecycle_expiration": has_lifecycle,
        }
        eval_items.append(
            (
                rego_res,
                {
                    "id": barn,
                    "name": bname,
                    "source_file": f"aws://{account_id}/{b_region}/s3/{bname}",
                    "hcl_before": json.dumps({k: v for k, v in rego_res.items() if k != "approved_regions"}, indent=2),
                },
            )
        )
        buckets_graph.append({"id": barn, "name": bname, "props": {"contains_personal_data": personal_data}})

    # 2. EC2 Security Groups
    for sg in ec2.describe_security_groups().get("SecurityGroups", []):
        sgid = sg["GroupId"]
        sgname = sg.get("GroupName", sgid)
        if sg.get("VpcId"):
            sg_vpcs_graph.append({"sgid": sgid, "vpcid": sg["VpcId"]})
        for idx, perm in enumerate(sg.get("IpPermissions", [])):
            proto = str(perm.get("IpProtocol", "-1"))
            fp = int(perm.get("FromPort", 0))
            tp = int(perm.get("ToPort", 65535))
            cidrs = [r.get("CidrIp") for r in perm.get("IpRanges", []) if r.get("CidrIp")] + [
                r.get("CidrIpv6") for r in perm.get("Ipv6Ranges", []) if r.get("CidrIpv6")
            ]
            for cidr in cidrs:
                rule_id = f"{sgid}:in:{idx}:{cidr}"
                rego_res = {
                    "resource_type": "AWSIpPermissionInbound",
                    "ip_range": cidr,
                    "protocol": proto,
                    "fromport": fp,
                    "toport": tp,
                }
                eval_items.append(
                    (
                        rego_res,
                        {
                            "id": sgid,
                            "name": sgname,
                            "source_file": f"aws://{account_id}/{region}/ec2/{sgid}",
                            "hcl_before": json.dumps(rego_res, indent=2),
                        },
                    )
                )
                if cidr in ("0.0.0.0/0", "::/0"):
                    net_rules_graph.append(
                        {
                            "rgid": cidr,
                            "rgrange": cidr,
                            "ruleid": rule_id,
                            "fp": fp,
                            "tp": tp,
                            "proto": proto,
                            "sgid": sgid,
                            "sgname": sgname,
                        }
                    )

    # 3. IAM Users & Keys
    for u in iam.list_users().get("Users", []):
        uarn = u["Arn"]
        uname = u["UserName"]
        principals.append({"id": uarn, "name": uname, "labels": ["AWSPrincipal", "AWSUser"]})
        try:
            for k in iam.list_access_keys(UserName=uname).get("AccessKeyMetadata", []):
                keys.append({"uid": uarn, "kid": k["AccessKeyId"], "status": k.get("Status", "Active")})
        except Exception:
            pass

    # 4. IAM Roles & Attached Policies
    for role in iam.list_roles().get("Roles", []):
        rarn = role["Arn"]
        rname = role["RoleName"]
        principals.append({"id": rarn, "name": rname, "labels": ["AWSPrincipal", "AWSRole"]})
        assume_doc = role.get("AssumeRolePolicyDocument") or {}
        for stmt in assume_doc.get("Statement", []):
            princ = stmt.get("Principal", {}) if isinstance(stmt, dict) else {}
            if isinstance(princ, dict) and "AWS" in princ:
                aws_ps = princ["AWS"] if isinstance(princ["AWS"], list) else [princ["AWS"]]
                for p in aws_ps:
                    trusts.append({"rid": rarn, "pid": str(p)})
        try:
            for ap in iam.list_attached_role_policies(RoleName=rname).get("AttachedPolicies", []):
                pol_arn = ap["PolicyArn"]
                if pol_arn.startswith("arn:aws:iam::aws:policy/"):
                    if pol_arn.endswith("/AdministratorAccess"):
                        stmt_id = f"{pol_arn}#stmt0"
                        statements_graph.append(
                            {
                                "pid": rarn,
                                "polid": pol_arn,
                                "polname": ap.get("PolicyName", "AdministratorAccess"),
                                "stmt_id": stmt_id,
                                "stmt_sid": "AdminManaged",
                                "effect": "Allow",
                                "action": ["*"],
                                "resource": ["*"],
                            }
                        )
                        rego_res = {
                            "resource_type": "AWSPolicyStatement",
                            "effect": "Allow",
                            "action": ["*"],
                            "resource": ["*"],
                        }
                        eval_items.append(
                            (
                                rego_res,
                                {
                                    "id": stmt_id,
                                    "name": ap.get("PolicyName", "AdministratorAccess"),
                                    "source_file": f"aws://{account_id}/iam/AdministratorAccess",
                                    "hcl_before": json.dumps({"PolicyArn": pol_arn, "Role": rname}, indent=2),
                                },
                            )
                        )
                    continue
                ver = iam.get_policy(PolicyArn=pol_arn)["Policy"]["DefaultVersionId"]
                doc = iam.get_policy_version(PolicyArn=pol_arn, VersionId=ver)["PolicyVersion"]["Document"]
                for sidx, stmt in enumerate(doc.get("Statement", []) if isinstance(doc, dict) else []):
                    acts = stmt.get("Action")
                    acts = acts if isinstance(acts, list) else ([acts] if acts else [])
                    ress = stmt.get("Resource")
                    ress = ress if isinstance(ress, list) else ([ress] if ress else [])
                    stmt_id = f"{pol_arn}#stmt{sidx}"
                    statements_graph.append(
                        {
                            "pid": rarn,
                            "polid": pol_arn,
                            "polname": ap["PolicyName"],
                            "stmt_id": stmt_id,
                            "stmt_sid": stmt.get("Sid") or f"stmt{sidx}",
                            "effect": stmt.get("Effect", "Allow"),
                            "action": acts,
                            "resource": ress,
                        }
                    )
                    rego_res = {
                        "resource_type": "AWSPolicyStatement",
                        "effect": stmt.get("Effect", "Allow"),
                        "action": acts,
                        "resource": ress,
                    }
                    eval_items.append(
                        (
                            rego_res,
                            {
                                "id": stmt_id,
                                "name": ap["PolicyName"],
                                "source_file": f"aws://{account_id}/iam/{ap['PolicyName']}",
                                "hcl_before": json.dumps(stmt, indent=2),
                            },
                        )
                    )
        except Exception:
            pass
        try:
            for ip_name in iam.list_role_policies(RoleName=rname).get("PolicyNames", []):
                doc = iam.get_role_policy(RoleName=rname, PolicyName=ip_name).get("PolicyDocument") or {}
                pol_arn = f"arn:aws:iam::{account_id}:inline-policy/{rname}/{ip_name}"
                raw_stmts = doc.get("Statement", []) if isinstance(doc, dict) else []
                if isinstance(raw_stmts, dict):
                    raw_stmts = [raw_stmts]
                for sidx, stmt in enumerate(raw_stmts):
                    if not isinstance(stmt, dict):
                        continue
                    acts = stmt.get("Action")
                    acts = acts if isinstance(acts, list) else ([acts] if acts else [])
                    ress = stmt.get("Resource")
                    ress = ress if isinstance(ress, list) else ([ress] if ress else [])
                    stmt_id = f"{pol_arn}#stmt{sidx}"
                    statements_graph.append(
                        {
                            "pid": rarn,
                            "polid": pol_arn,
                            "polname": ip_name,
                            "stmt_id": stmt_id,
                            "stmt_sid": stmt.get("Sid") or f"stmt{sidx}",
                            "effect": stmt.get("Effect", "Allow"),
                            "action": acts,
                            "resource": ress,
                        }
                    )
                    rego_res = {
                        "resource_type": "AWSPolicyStatement",
                        "effect": stmt.get("Effect", "Allow"),
                        "action": acts,
                        "resource": ress,
                    }
                    eval_items.append(
                        (
                            rego_res,
                            {
                                "id": stmt_id,
                                "name": ip_name,
                                "source_file": f"aws://{account_id}/iam/{rname}/{ip_name}",
                                "hcl_before": json.dumps(stmt, indent=2),
                            },
                        )
                    )
        except Exception:
            pass

    # 5. RDS Instances
    try:
        for db in rds.describe_db_instances().get("DBInstances", []):
            dbid = db["DBInstanceIdentifier"]
            rego_res = {
                "resource_type": "AWSRDSInstance",
                "storage_encrypted": bool(db.get("StorageEncrypted", False)),
            }
            eval_items.append(
                (
                    rego_res,
                    {
                        "id": dbid,
                        "name": dbid,
                        "source_file": f"aws://{account_id}/{region}/rds/{dbid}",
                        "hcl_before": json.dumps(rego_res, indent=2),
                    },
                )
            )
    except Exception:
        pass

    # 6. CloudTrail
    try:
        trails = ct.describe_trails().get("trailList", [])
        ct_enabled = len(trails) > 0
        eval_items.append(
            (
                {
                    "resource_type": "AWSAccount",
                    "account_mfa_enabled": True,
                    "cloudtrail_enabled": ct_enabled,
                },
                {
                    "id": account_id,
                    "name": f"aws-account-{account_id}",
                    "source_file": f"aws://{account_id}/{region}/cloudtrail",
                    "hcl_before": json.dumps({"cloudtrail_trails": len(trails)}, indent=2),
                },
            )
        )
    except Exception:
        pass

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
    seen = set()
    for idx, (rego_res, meta) in enumerate(eval_items):
        if verdicts is not None:
            deny_set = set(verdicts[idx].deny)
            warn_set = set(verdicts[idx].warn)
        else:
            deny_set, warn_set = _fallback_eval(rego_res)
        for rule_id in sorted(deny_set | warn_set):
            key = (meta["id"], rule_id)
            if key in seen:
                continue
            seen.add(key)
            raw_findings.append(
                {
                    "finding_id": f"F-AWS-{len(raw_findings) + 1:03d}",
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

    session_graph = LocalCartographySession(
        principals=principals,
        keys=keys,
        trusts=trusts,
        buckets=buckets_graph,
        bucket_tags=[],
        statements=statements_graph,
        net_rules=net_rules_graph,
        sg_vpcs=sg_vpcs_graph,
    )

    return {
        "source_type": "aws",
        "target": f"aws://{account_id}/{region}",
        "account_id": account_id,
        "region": region,
        "identity": identity_name,
        "watchlist_warnings": watchlist,
        "opa_used": opa_used,
        "opa_bin": opa_bin,
        "raw_findings": raw_findings,
        "session": session_graph,
    }
