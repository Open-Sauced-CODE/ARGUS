"""LocalCartographySession: executes frozen risk.attack_graph Cypher queries in-memory without Neo4j."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from risk.attack_graph import (
    Q_BUCKET_TAGS,
    Q_BUCKETS,
    Q_KEYS,
    Q_NET,
    Q_PRINCIPALS,
    Q_SG_VPC,
    Q_STATEMENTS,
    Q_TRUST,
)


class _Record:
    """Minimal Neo4j Record shim providing .data() for risk.graph_loader.run()."""

    def __init__(self, row: Dict[str, Any]):
        self._row = row

    def data(self) -> Dict[str, Any]:
        return dict(self._row)


def _norm(cypher: str) -> str:
    return " ".join(cypher.split())


@dataclass
class LocalCartographySession:
    """In-memory drop-in replacement for a read-only Neo4j Session.

    Populated by local Terraform or AWS boto3 scanners and fed directly into
    the unmodified frozen `risk.attack_graph.build_attack_graph(session)`.
    """

    principals: List[Dict[str, Any]] = field(default_factory=list)
    keys: List[Dict[str, Any]] = field(default_factory=list)
    trusts: List[Dict[str, Any]] = field(default_factory=list)
    buckets: List[Dict[str, Any]] = field(default_factory=list)
    bucket_tags: List[Dict[str, Any]] = field(default_factory=list)
    statements: List[Dict[str, Any]] = field(default_factory=list)
    net_rules: List[Dict[str, Any]] = field(default_factory=list)
    sg_vpcs: List[Dict[str, Any]] = field(default_factory=list)

    def run(self, cypher: str, **params: Any) -> List[_Record]:
        key = _norm(cypher)
        mapping = {
            _norm(Q_PRINCIPALS): self.principals,
            _norm(Q_KEYS): self.keys,
            _norm(Q_TRUST): self.trusts,
            _norm(Q_BUCKETS): self.buckets,
            _norm(Q_BUCKET_TAGS): self.bucket_tags,
            _norm(Q_STATEMENTS): self.statements,
            _norm(Q_NET): self.net_rules,
            _norm(Q_SG_VPC): self.sg_vpcs,
        }
        rows = mapping.get(key)
        if rows is None:
            raise ValueError(f"Unsupported Cypher query in LocalCartographySession: {key[:120]}")
        return [_Record(r) for r in rows]
