"""Security-group mutator (Phase 5, Step 5).

The projected record shows only ip_range, protocol, fromport and toport, and the original (safe) CIDR is never
visible after the mutation (contracts decision D5). The reference fix is therefore always the same symbolic
operation: restrict_cidr to the placeholder INTERNAL_CIDR, which the Phase 7 compiler resolves from the
deployer's configuration. To keep the round trip exact, prepare() replaces the base CIDR by the placeholder.
"""

from ml.mutation_engine.mutators.base import Mutator

INTERNAL_CIDR = "INTERNAL_CIDR"
SENSITIVE_PORTS = (22, 3389, 3306, 5432, 1433, 27017, 6379)
_KINDS = {"ssh": ("tcp", 22, 22), "rdp": ("tcp", 3389, 3389), "mysql": ("tcp", 3306, 3306),
          "postgres": ("tcp", 5432, 5432), "all_traffic": ("-1", 0, 0), "wide": ("tcp", 0, 65535)}


def _exposes_sensitive(attrs):
    if attrs.get("protocol") == "-1":
        return True
    lo, hi = attrs.get("fromport"), attrs.get("toport")
    return isinstance(lo, int) and isinstance(hi, int) and any(lo <= p <= hi for p in SENSITIVE_PORTS)


class SgWorldOpen(Mutator):
    mutator_id = "m_sg_world_open"
    resource_types = ("AWSIpPermissionInbound",)
    variants = {"{}_{}".format(kind, fam): (3.0 if kind == "base" else 1.0)
                for kind in ("base",) + tuple(_KINDS) for fam in ("v4", "v6")}
    rules = ("dpdp.rule6_sg_open_ingress", "cis.sg_open_ingress")
    writes = frozenset({"ip_range", "protocol", "fromport", "toport"})

    def prepare(self, res, variant):
        if res.resource_type not in self.resource_types:
            return None
        kind = variant.rsplit("_", 1)[0]
        out = res.copy()
        if kind == "base":
            if not _exposes_sensitive(res.attrs):
                return None
        else:
            protocol, lo, hi = _KINDS[kind]
            out.attrs.update({"protocol": protocol, "fromport": lo, "toport": hi})
        out.attrs["ip_range"] = INTERNAL_CIDR
        return out

    def mutate(self, clean, variant):
        broken = clean.copy()
        broken.attrs["ip_range"] = "0.0.0.0/0" if variant.endswith("_v4") else "::/0"
        ops = [{"op": "restrict_cidr", "attr": "ip_range", "value": INTERNAL_CIDR}]
        return broken, self._mutation(variant, clean, broken, ["ip_range"], ops)
