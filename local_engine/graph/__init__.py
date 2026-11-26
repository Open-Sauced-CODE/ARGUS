"""In-memory Cartography session adapter for running risk.attack_graph without Docker/Neo4j."""

from .inmemory_session import LocalCartographySession

__all__ = ["LocalCartographySession"]
