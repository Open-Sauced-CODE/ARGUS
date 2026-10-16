"""
ARGUS Phase 5, Step 4 - Terraform normaliser.

Turns the .tf files of one repository into "base records": one record per resource, written with the
SAME field names that the Phase 4 Rego rules read (default_encryption, versioning_status, ip_range, ...).

A record looks like:
    {
      "resource_type": "AWSS3Bucket",            # the Rego resource_type
      "attrs":  {...},                           # every field some Rego rule reads (rule-visible)
      "extras": {...},                           # harmless real attributes no rule reads (decoy material)
      "source": {"file": "...", "tf_type": "aws_s3_bucket", "tf_name": "data"},
      "norm_hash": "<sha256>",                   # same hash = same resource shape (names and tags are never stored)
    }

Rules of this module (from the Phase 5 plan, Step 4):
  * A variable or local is resolved ONLY when it is an exact reference (${var.x} / ${local.x}) whose value is
    a plain literal. Anything else that a rule needs stays unresolved.
  * If an attribute that a rule reads is unresolved, the resource is SKIPPED and the skip is counted
    under a named reason. Nothing is guessed.
  * Real names, tags, descriptions and every secret-like attribute are never stored. `extras` is an
    allow-list of harmless scalar attributes only.

Public functions: parse_text, normalise_module, normalise_repo, norm_hash.
"""

import hashlib
import json
import posixpath
import re
from collections import Counter

# ---------------------------------------------------------------------------------------------
# Which Terraform resource types we read
# ---------------------------------------------------------------------------------------------

S3_BUCKET = "aws_s3_bucket"
S3_COMPANIONS = (
    "aws_s3_bucket_server_side_encryption_configuration",
    "aws_s3_bucket_versioning",
    "aws_s3_bucket_public_access_block",
    "aws_s3_bucket_logging",
    "aws_s3_bucket_lifecycle_configuration",
)
SG_TYPES = ("aws_security_group", "aws_security_group_rule", "aws_vpc_security_group_ingress_rule")
RDS_TYPES = ("aws_db_instance",)
IAM_POLICY_TYPES = ("aws_iam_policy", "aws_iam_role_policy", "aws_iam_user_policy", "aws_iam_group_policy")
IAM_DOC = "aws_iam_policy_document"

# Used by the TerraDS filter: repositories that declare at least one of these are worth parsing.
TARGET_TYPES = (S3_BUCKET,) + SG_TYPES + RDS_TYPES + IAM_POLICY_TYPES

PUBLIC_FLAGS = ("block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets")

# Harmless attributes we keep as `extras` (resolved literals only). Everything else is dropped.
EXTRAS_ALLOW = {
    "AWSS3Bucket": ("force_destroy", "object_lock_enabled", "acl", "request_payer"),
    "AWSRDSInstance": (
        "engine", "engine_version", "instance_class", "allocated_storage", "multi_az", "publicly_accessible",
        "backup_retention_period", "skip_final_snapshot", "deletion_protection", "storage_type",
        "auto_minor_version_upgrade", "iam_database_authentication_enabled", "copy_tags_to_snapshot",
        "performance_insights_enabled", "monitoring_interval",
    ),
}

_VAR_RE = re.compile(r"^\$\{var\.([A-Za-z0-9_\-]+)\}$")
_LOCAL_RE = re.compile(r"^\$\{local\.([A-Za-z0-9_\-]+)\}$")
_BUCKET_REF_RE = re.compile(r"^\$\{aws_s3_bucket\.([A-Za-z0-9_\-]+)(?:\[[^\]]*\])?\.(?:id|bucket)\}$")
_POLICY_DOC_REF_RE = re.compile(r"^\$\{data\.aws_iam_policy_document\.")
_JSONENCODE_RE = re.compile(r"^\$\{jsonencode\((.*)\)\}$", re.DOTALL)


class Unresolved(Exception):
    """A value a rule needs is not a plain literal. `reason` is the named skip reason."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------------------------

def _options():
    import hcl2

    return hcl2.SerializationOptions(with_comments=False, explicit_blocks=False, strip_string_quotes=True)


def parse_text(text):
    """Parse the text of one .tf file into a dictionary (python-hcl2 8.x)."""
    import hcl2

    return hcl2.loads(text, serialization_options=_options())


def _parse_expression(expr):
    """Parse an HCL object/list expression such as {Version = "2012-10-17", ...} into Python."""
    parsed = parse_text("x = " + expr + "\n")
    return parsed["x"]


# ---------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------

def _has_interpolation(value):
    if isinstance(value, str):
        return "${" in value
    if isinstance(value, dict):
        return any(_has_interpolation(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_interpolation(v) for v in value)
    return False


def _blocks(body, key):
    """Nested blocks come back from python-hcl2 as a list of dicts. Return that list ([] if absent)."""
    value = body.get(key)
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _as_list(value):
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def norm_hash(resource_type, attrs, extras):
    """Hash of a resource's SHAPE. Names, tags, descriptions and comments are never part of a record, so two
    resources with the same rule-visible and extra attributes get the same hash."""
    canonical = json.dumps(
        {"resource_type": resource_type, "attrs": attrs, "extras": extras},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class _Resource:
    __slots__ = ("file", "rtype", "name", "body")

    def __init__(self, file, rtype, name, body):
        self.file = file
        self.rtype = rtype
        self.name = name
        self.body = body


class _Module:
    """All .tf files of ONE directory: variables, locals, resources and data blocks."""

    def __init__(self, parsed_files):
        self.variables = {}
        self.locals = {}
        self.resources = []
        self.docs = []  # (file, name, body) of data "aws_iam_policy_document"
        self.docs_by_name = {}
        for relpath, parsed in parsed_files:
            for block in parsed.get("variable", []) or []:
                for name, body in block.items():
                    if isinstance(body, dict) and "default" in body and not _has_interpolation(body["default"]):
                        if body["default"] is not None:
                            self.variables[name] = body["default"]
            for block in parsed.get("locals", []) or []:
                for name, value in block.items():
                    self.locals[name] = value
            for block in parsed.get("resource", []) or []:
                for rtype, instances in block.items():
                    for name, body in instances.items():
                        if isinstance(body, dict):
                            self.resources.append(_Resource(relpath, rtype, name, body))
            for block in parsed.get("data", []) or []:
                for dtype, instances in block.items():
                    if dtype != IAM_DOC:
                        continue
                    for name, body in instances.items():
                        if isinstance(body, dict):
                            self.docs.append((relpath, name, body))
                            self.docs_by_name[name] = body

    # -- resolution ----------------------------------------------------------------------------
    def resolve(self, value, depth=0):
        if isinstance(value, str):
            if depth < 5:
                m = _VAR_RE.match(value)
                if m and m.group(1) in self.variables:
                    return self.resolve(self.variables[m.group(1)], depth + 1)
                m = _LOCAL_RE.match(value)
                if m and m.group(1) in self.locals:
                    return self.resolve(self.locals[m.group(1)], depth + 1)
            return value
        if isinstance(value, list):
            return [self.resolve(v, depth) for v in value]
        if isinstance(value, dict):
            return {k: self.resolve(v, depth) for k, v in value.items()}
        return value

    def literal(self, value, reason):
        """Resolved plain literal or raise Unresolved(reason)."""
        resolved = self.resolve(value)
        if _has_interpolation(resolved):
            raise Unresolved(reason)
        return resolved

    def boolean(self, value, reason):
        v = self.literal(value, reason)
        if isinstance(v, bool):
            return v
        if isinstance(v, str) and v.lower() in ("true", "false"):
            return v.lower() == "true"
        raise Unresolved(reason)

    def integer(self, value, reason):
        v = self.literal(value, reason)
        if isinstance(v, bool):
            raise Unresolved(reason)
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, str) and re.fullmatch(r"-?\d+", v.strip()):
            return int(v.strip())
        raise Unresolved(reason)

    def string(self, value, reason):
        v = self.literal(value, reason)
        if isinstance(v, str) and v != "":
            return v
        raise Unresolved(reason)

    def check_multiplicity(self, body, prefix):
        """for_each makes the number of resources unknown. count must resolve to an integer >= 1."""
        if "for_each" in body:
            raise Unresolved(prefix + ":for_each")
        if "count" in body:
            n = self.integer(body["count"], prefix + ":count_unresolved")
            if n < 1:
                raise Unresolved(prefix + ":count_zero")


def _extras(module, rtype, body):
    out = {}
    for key in EXTRAS_ALLOW.get(rtype, ()):
        if key in body:
            value = module.resolve(body[key])
            if isinstance(value, (bool, int, float, str)) and not _has_interpolation(value):
                out[key] = value
    return out


def _record(rtype, attrs, extras, resource, tf_type=None):
    return {
        "resource_type": rtype,
        "attrs": attrs,
        "extras": extras,
        "source": {"file": resource.file, "tf_type": tf_type or resource.rtype, "tf_name": resource.name},
        "norm_hash": norm_hash(rtype, attrs, extras),
    }


# ---------------------------------------------------------------------------------------------
# S3 bucket (one record per bucket, assembled from the bucket plus its companion resources)
# ---------------------------------------------------------------------------------------------

def _points_to(module, companion, bucket):
    ref = companion.body.get("bucket")
    if isinstance(ref, str):
        m = _BUCKET_REF_RE.match(ref)
        if m:
            return m.group(1) == bucket.name
        own = module.resolve(bucket.body.get("bucket"))
        theirs = module.resolve(ref)
        return (isinstance(own, str) and own != "" and not _has_interpolation(own) and own == theirs)
    return False


def _s3_record(module, bucket, companions):
    module.check_multiplicity(bucket.body, "s3")
    mine = {t: [c for c in companions[t] if _points_to(module, c, bucket)] for t in S3_COMPANIONS}
    attrs = {}

    # encryption
    sse = []
    for comp in mine["aws_s3_bucket_server_side_encryption_configuration"]:
        found = [d for rule in _blocks(comp.body, "rule") for d in _blocks(rule, "apply_server_side_encryption_by_default")]
        if not found:
            raise Unresolved("s3:sse_block_unparsed")
        sse.extend(found)
    for cfg in _blocks(bucket.body, "server_side_encryption_configuration"):
        sse.extend(d for rule in _blocks(cfg, "rule") for d in _blocks(rule, "apply_server_side_encryption_by_default"))
    if sse:
        attrs["default_encryption"] = True
        attrs["encryption_algorithm"] = module.string(sse[0].get("sse_algorithm"), "s3:sse_algorithm_unresolved")
    else:
        attrs["default_encryption"] = False

    # versioning (a never-versioned bucket has NO versioning_status, as in Cartography)
    for comp in mine["aws_s3_bucket_versioning"]:
        vc = _blocks(comp.body, "versioning_configuration")
        if not vc:
            raise Unresolved("s3:versioning_block_unparsed")
        attrs["versioning_status"] = module.string(vc[0].get("status"), "s3:versioning_status_unresolved")
    if "versioning_status" not in attrs:
        for inline in _blocks(bucket.body, "versioning"):
            if module.boolean(inline.get("enabled", False), "s3:versioning_enabled_unresolved"):
                attrs["versioning_status"] = "Enabled"

    # public access block (flags default to false, as in AWS)
    pab = mine["aws_s3_bucket_public_access_block"]
    for flag in PUBLIC_FLAGS:
        attrs[flag] = module.boolean(pab[0].body.get(flag, False), "s3:public_flag_unresolved") if pab else False

    # logging
    attrs["logging_enabled"] = bool(mine["aws_s3_bucket_logging"] or _blocks(bucket.body, "logging"))

    # lifecycle expiration
    expiration = False
    for comp in mine["aws_s3_bucket_lifecycle_configuration"]:
        rules = _blocks(comp.body, "rule")
        if not rules:
            raise Unresolved("s3:lifecycle_unparsed")
        for rule in rules:
            status = module.string(rule.get("status"), "s3:lifecycle_status_unresolved")
            if status.lower() == "enabled" and _blocks(rule, "expiration"):
                expiration = True
    for rule in _blocks(bucket.body, "lifecycle_rule"):
        if module.boolean(rule.get("enabled", False), "s3:lifecycle_status_unresolved") and _blocks(rule, "expiration"):
            expiration = True
    attrs["has_lifecycle_expiration"] = expiration

    # personal-data tag (same tag name as risk/config.json crown_jewel_tag)
    tags = module.resolve(bucket.body.get("tags"))
    if isinstance(tags, dict) and "contains_personal_data" in tags:
        tag = tags["contains_personal_data"]
        if _has_interpolation(tag):
            raise Unresolved("s3:personal_data_tag_unresolved")
        if tag is True or str(tag).lower() == "true":
            attrs["personal_data"] = True

    return _record("AWSS3Bucket", attrs, _extras(module, "AWSS3Bucket", bucket.body), bucket)


# ---------------------------------------------------------------------------------------------
# Security group ingress rules (one record per CIDR)
# ---------------------------------------------------------------------------------------------

def _protocol(module, value):
    v = module.literal(value, "sg:protocol_unresolved")
    if isinstance(v, bool):
        raise Unresolved("sg:protocol_unresolved")
    if isinstance(v, (int, float)):
        v = str(int(v))
    if not isinstance(v, str) or v == "":
        raise Unresolved("sg:protocol_unresolved")
    v = v.strip().lower()
    return "-1" if v in ("all", "-1") else v


def _sg_records(module, resource, skips):
    """Records for the ingress rules of one security-group resource. An ingress rule that cannot be read is
    skipped and counted in `skips`; the other rules of the same resource are still used."""
    body, rtype = resource.body, resource.rtype
    out = []

    def emit(cidrs, protocol, fp, tp):
        for cidr in cidrs:
            attrs = {"ip_range": cidr, "protocol": protocol, "fromport": fp, "toport": tp}
            out.append(_record("AWSIpPermissionInbound", attrs, {}, resource))

    def ports(src, protocol):
        if "from_port" not in src and "to_port" not in src and protocol == "-1":
            return 0, 0
        return (module.integer(src.get("from_port"), "sg:port_unresolved"),
                module.integer(src.get("to_port"), "sg:port_unresolved"))

    def cidr_list(src, key):
        if key not in src:
            return []
        values = _as_list(module.literal(src[key], "sg:cidr_unresolved"))
        if not all(isinstance(v, str) and v for v in values):
            raise Unresolved("sg:cidr_unresolved")
        return values

    def one_rule(src, protocol_key):
        protocol = _protocol(module, src.get(protocol_key))
        fp, tp = ports(src, protocol)
        cidrs = cidr_list(src, "cidr_blocks") + cidr_list(src, "ipv6_cidr_blocks")
        if rtype == "aws_vpc_security_group_ingress_rule":
            cidrs = [module.string(src[k], "sg:cidr_unresolved") for k in ("cidr_ipv4", "cidr_ipv6") if k in src]
        if not cidrs:
            raise Unresolved("sg:no_cidr_rule")
        emit(cidrs, protocol, fp, tp)

    if rtype == "aws_security_group":
        if "dynamic" in body:
            skips["sg:dynamic_ingress"] += 1
        for ing in _blocks(body, "ingress"):
            try:
                one_rule(ing, "protocol")
            except Unresolved as exc:
                skips[exc.reason] += 1
    elif rtype == "aws_security_group_rule":
        if str(module.resolve(body.get("type"))).lower() == "ingress":
            module.check_multiplicity(body, "sg")
            one_rule(body, "protocol")
    elif rtype == "aws_vpc_security_group_ingress_rule":
        module.check_multiplicity(body, "sg")
        one_rule(body, "ip_protocol")
    return out


# ---------------------------------------------------------------------------------------------
# RDS instance
# ---------------------------------------------------------------------------------------------

def _rds_record(module, resource):
    module.check_multiplicity(resource.body, "rds")
    attrs = {"storage_encrypted": module.boolean(resource.body.get("storage_encrypted", False), "rds:encrypted_unresolved")}
    return _record("AWSRDSInstance", attrs, _extras(module, "AWSRDSInstance", resource.body), resource)


# ---------------------------------------------------------------------------------------------
# IAM policy statements (one record per statement)
# ---------------------------------------------------------------------------------------------

def _string_list(module, value, reason):
    values = _as_list(module.literal(value, reason))
    if not values or not all(isinstance(v, str) and v for v in values):
        raise Unresolved(reason)
    return values


def _statement_record(module, resource, effect, actions, resources):
    attrs = {"effect": effect, "action": actions, "resource": resources}
    return _record("AWSPolicyStatement", attrs, {}, resource)


def _json_statements(module, resource, text):
    """Statements from a JSON policy given as heredoc, plain JSON, or jsonencode(...)."""
    policy = None
    if isinstance(text, str):
        stripped = text.strip()
        m = _JSONENCODE_RE.match(stripped)
        if m:
            try:
                policy = _parse_expression(m.group(1))
            except Exception:
                raise Unresolved("iam:jsonencode_unparsed")
        elif stripped.startswith("<<"):
            lines = stripped.splitlines()
            body = "\n".join(lines[1:-1])
            if "${" in body or "%{" in body:
                raise Unresolved("iam:heredoc_interpolated")
            try:
                policy = json.loads(body)
            except ValueError:
                raise Unresolved("iam:heredoc_unparsed")
        elif stripped.startswith("{"):
            if "${" in stripped:
                raise Unresolved("iam:json_interpolated")
            try:
                policy = json.loads(stripped)
            except ValueError:
                raise Unresolved("iam:json_unparsed")
    if not isinstance(policy, dict):
        raise Unresolved("iam:policy_not_inline")
    policy = module.resolve(policy)
    statements = policy.get("Statement")
    statements = [statements] if isinstance(statements, dict) else (statements or [])
    out = []
    for st in statements:
        if not isinstance(st, dict):
            raise Unresolved("iam:statement_unparsed")
        if "NotAction" in st or "NotResource" in st:
            raise Unresolved("iam:not_action_or_resource")
        effect = module.string(st.get("Effect", "Allow"), "iam:effect_unresolved")
        actions = _string_list(module, st.get("Action"), "iam:action_unresolved")
        resources = _string_list(module, st.get("Resource"), "iam:resource_unresolved")
        out.append(_statement_record(module, resource, effect, actions, resources))
    return out


def _doc_statements(module, relpath, name, body):
    resource = _Resource(relpath, IAM_DOC, name, body)
    if "dynamic" in body:
        raise Unresolved("iam:dynamic_statement")
    out = []
    for st in _blocks(body, "statement"):
        if "not_actions" in st or "not_resources" in st:
            raise Unresolved("iam:not_action_or_resource")
        effect = module.string(st.get("effect", "Allow"), "iam:effect_unresolved")
        actions = _string_list(module, st.get("actions"), "iam:action_unresolved")
        resources = _string_list(module, st.get("resources"), "iam:resource_unresolved")
        out.append(_statement_record(module, resource, effect, actions, resources))
    return out


# ---------------------------------------------------------------------------------------------
# Module and repository level
# ---------------------------------------------------------------------------------------------

def normalise_module(parsed_files):
    """parsed_files: list of (relative path, parsed dict) for the .tf files of ONE directory.
    Returns (records, skips, seen). skips and seen are Counters: skip reasons and resources seen by TF type."""
    module = _Module(parsed_files)
    records, skips, seen = [], Counter(), Counter()
    companions = {t: [r for r in module.resources if r.rtype == t] for t in S3_COMPANIONS}

    def attempt(rtype, build):
        seen[rtype] += 1
        try:
            result = build()
        except Unresolved as exc:
            skips[exc.reason] += 1
            return
        records.extend(result if isinstance(result, list) else [result])

    for res in module.resources:
        if res.rtype == S3_BUCKET:
            attempt(res.rtype, lambda r=res: _s3_record(module, r, companions))
        elif res.rtype in SG_TYPES:
            attempt(res.rtype, lambda r=res: _sg_records(module, r, skips))
        elif res.rtype in RDS_TYPES:
            attempt(res.rtype, lambda r=res: _rds_record(module, r))
        elif res.rtype in IAM_POLICY_TYPES:
            policy = res.body.get("policy")
            if isinstance(policy, str) and _POLICY_DOC_REF_RE.match(policy):
                continue  # covered by the data "aws_iam_policy_document" block itself
            attempt(res.rtype, lambda r=res, p=policy: _json_statements(module, r, p))
    for relpath, name, body in module.docs:
        attempt(IAM_DOC, lambda f=relpath, n=name, b=body: _doc_statements(module, f, n, b))
    return records, skips, seen


def normalise_repo(files):
    """files: {relative posix path: text of a .tf file}. Groups files by directory (a Terraform module is a
    directory), parses them, and returns a dict:
        records, skips (Counter), seen (Counter), files_parsed, parse_errors
    """
    by_dir = {}
    parse_errors = 0
    parsed_count = 0
    for relpath in sorted(files):
        try:
            parsed = parse_text(files[relpath])
        except Exception:
            parse_errors += 1
            continue
        parsed_count += 1
        by_dir.setdefault(posixpath.dirname(relpath), []).append((relpath, parsed))
    records, skips, seen = [], Counter(), Counter()
    for directory in sorted(by_dir):
        r, s, n = normalise_module(by_dir[directory])
        records.extend(r)
        skips.update(s)
        seen.update(n)
    return {"records": records, "skips": skips, "seen": seen,
            "files_parsed": parsed_count, "parse_errors": parse_errors}
