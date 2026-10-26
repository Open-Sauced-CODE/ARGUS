"""
ARGUS Phase 4 - structure-preserving tokenization.

    tokenize(record)   -> (tokenized_record, vault_refs)
    rehydrate(obj, vault_refs) -> obj with tokens replaced by the real values

Real identifiers (bucket names, ARNs, role names, account ids, IPs, emails, KMS key ids ...)
become typed, consistent tokens such as BUCKET_1, ROLE_2, ACCOUNT_1, CIDR_PRIV_1.
Tokens match the Patch-IR resource_ref pattern ^[A-Z_]+_[0-9]+$.

Structure is preserved: arn:aws:s3:::my-bucket  ->  arn:aws:s3:::BUCKET_1
Public constants pass through unchanged: 0.0.0.0/0, ::/0 and AWS-managed policy ARNs.
Numbering restarts at 1 for every record; the vault_refs returned by tokenize() are what make
a token unambiguous (token -> random vault reference -> encrypted real value).
"""

import ipaddress
import re
from collections import OrderedDict

from privacy.vault.vault import get_default_vault

_ARN_RE = re.compile(r"""arn:aws[a-z\-]*:[a-z0-9\-]+:[a-z0-9\-]*:(?:\d{12}|aws|):[^\s"'<>,;]+""")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}\b")
_RESID_RE = re.compile(r"\b(sg|vpc|subnet|igw|rtb|acl|eni|vol|snap|i)-[0-9a-f]{8,17}\b")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b")
_ACCOUNT_RE = re.compile(r"(?<![0-9A-Za-z])\d{12}(?![0-9A-Za-z])")
_ARN_TYPE_RE = re.compile(r"^([A-Za-z\-]+)([/:])(.+)$")

_RESID_KINDS = {
    "sg": "SG", "vpc": "VPC", "subnet": "SUBNET", "igw": "IGW", "rtb": "RTB",
    "acl": "ACL", "eni": "ENI", "vol": "VOLUME", "snap": "SNAPSHOT", "i": "INSTANCE",
}
_ARN_TYPE_KINDS = {
    "role": "ROLE", "user": "USER", "policy": "POLICY", "group": "GROUP", "key": "KMSKEY",
    "alias": "ALIAS", "instance-profile": "PROFILE", "security-group": "SG", "vpc": "VPC",
    "subnet": "SUBNET", "instance": "INSTANCE", "volume": "VOLUME", "snapshot": "SNAPSHOT",
    "db": "DB", "cluster": "CLUSTER", "secret": "SECRET", "function": "FUNCTION",
    "table": "TABLE",
}
# What a bare "name" / "resource_id" value is, by Cartography resource type.
_NAME_KIND_BY_TYPE = {
    "AWSS3Bucket": "BUCKET", "AWSRole": "ROLE", "AWSUser": "USER", "AWSPolicy": "POLICY",
    "AWSEC2SecurityGroup": "SG", "AWSVpc": "VPC", "AWSRDSInstance": "DB",
    "AWSEC2Subnet": "SUBNET",
}
# Field names whose whole value is an identifier of a known kind.
_IDENTIFIER_FIELDS = {
    "bucket": "BUCKET", "bucket_name": "BUCKET", "role_name": "ROLE", "user_name": "USER",
    "policy_name": "POLICY", "group_name": "GROUP", "account_id": "ACCOUNT",
    "kms_key_id": "KMSKEY", "key_id": "KMSKEY", "vpc_id": "VPC", "group_id": "SG",
    "subnet_id": "SUBNET",
}


class _Session:
    """Token bookkeeping for ONE record."""

    def __init__(self):
        self.counters = {}
        self.by_real = OrderedDict()  # (kind, real) -> token

    def token_for(self, kind, real):
        key = (kind, real)
        if key not in self.by_real:
            self.counters[kind] = self.counters.get(kind, 0) + 1
            self.by_real[key] = "{}_{}".format(kind, self.counters[kind])
        return self.by_real[key]

    def items(self):
        return [(tok, kind, real) for (kind, real), tok in self.by_real.items()]

    # -- string-level (content-based) tokenization ---------------------------
    def tok_arn(self, arn):
        parts = arn.split(":", 5)
        if len(parts) < 6:
            return arn
        _, partition, service, region, account, resource = parts
        if account == "aws":  # AWS-managed policy: public constant
            return arn
        if account.isdigit():
            account = self.token_for("ACCOUNT", account)
        return ":".join(["arn", partition, service, region, account, self._arn_resource(service, resource)])

    def _arn_resource(self, service, resource):
        if resource in ("", "*"):
            return resource
        if service == "s3":
            bucket, sep, rest = resource.partition("/")
            out = bucket if bucket in ("", "*") else self.token_for("BUCKET", bucket)
            if sep:
                out += sep + (rest if rest in ("", "*") else self.token_for("PATH", rest))
            return out
        m = _ARN_TYPE_RE.match(resource)
        if m:
            rtype, sep, name = m.groups()
            if name == "*":
                return resource
            return rtype + sep + self.token_for(_ARN_TYPE_KINDS.get(rtype.lower(), "RESOURCE"), name)
        return self.token_for("RESOURCE", resource)

    def _ip(self, match):
        text = match.group(0)
        try:
            net = ipaddress.ip_network(text, strict=False)
        except ValueError:
            return text
        if net.prefixlen == 0:  # 0.0.0.0/0 is a public constant
            return text
        return self.token_for("CIDR_PRIV" if net.is_private else "CIDR_PUB", text)

    def tok_string(self, text):
        text = _ARN_RE.sub(lambda m: self.tok_arn(m.group(0)), text)
        text = _EMAIL_RE.sub(lambda m: self.token_for("EMAIL", m.group(0)), text)
        text = _RESID_RE.sub(lambda m: self.token_for(_RESID_KINDS[m.group(1)], m.group(0)), text)
        text = _UUID_RE.sub(lambda m: self.token_for("KMSKEY", m.group(0)), text)
        text = _IPV4_RE.sub(self._ip, text)
        text = _ACCOUNT_RE.sub(lambda m: self.token_for("ACCOUNT", m.group(0)), text)
        return text

    # -- record walk -----------------------------------------------------------
    def walk(self, node, key=None, rtype=None):
        if isinstance(node, dict):
            return {k: self.walk(v, key=k, rtype=rtype) for k, v in node.items()}
        if isinstance(node, (list, tuple)):
            return [self.walk(v, key=key, rtype=rtype) for v in node]
        if isinstance(node, str):
            kind = self._field_kind(key, rtype)
            if kind and node and node != "*":
                return self.token_for(kind, node)
            return self.tok_string(node)
        return node

    @staticmethod
    def _field_kind(key, rtype):
        if key == "name":
            return _NAME_KIND_BY_TYPE.get(rtype, "RESOURCE")
        return _IDENTIFIER_FIELDS.get(key)


def _record_type(record):
    rtype = record.get("resource_type")
    if rtype is None and isinstance(record.get("fields"), dict):
        rtype = record["fields"].get("resource_type")
    return rtype


def tokenize(record, vault=None):
    """Tokenize a projected record. Returns (tokenized_record, vault_refs)."""
    vault = vault or get_default_vault()
    sess = _Session()
    rtype = _record_type(record)
    out = {}
    for k, v in record.items():
        if k == "resource_id" and isinstance(v, str) and v:
            out[k] = sess.token_for(_NAME_KIND_BY_TYPE.get(rtype, "RESOURCE"), v)
        else:
            out[k] = sess.walk(v, key=k, rtype=rtype)
    if "resource_id" in out:
        out["resource_ref"] = out["resource_id"]  # Patch-IR resource_ref
    refs = vault.put_many(sess.items())
    return out, refs


def rehydrate(obj, vault_refs, vault=None):
    """Replace tokens in `obj` (any JSON-like structure) by their real values."""
    vault = vault or get_default_vault()
    if not vault_refs:
        return obj
    mapping = {tok: vault.get(ref) for tok, ref in vault_refs.items()}
    alternatives = "|".join(re.escape(t) for t in sorted(mapping, key=len, reverse=True))
    rx = re.compile(r"(?<![A-Za-z0-9_])(" + alternatives + r")(?![A-Za-z0-9_])")

    def sub(node):
        if isinstance(node, dict):
            return {k: sub(v) for k, v in node.items()}
        if isinstance(node, (list, tuple)):
            return [sub(v) for v in node]
        if isinstance(node, str):
            return rx.sub(lambda m: mapping[m.group(1)], node)
        return node

    return sub(obj)
