"""Persistent SQLite workspace state store for local_agent mode."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, Optional

from local_engine.paths import get_state_db_path


class LocalStateStore:
    """Stores workspace snapshots (findings, graph, compliance, interdiction, receipts, tenant) in SQLite."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or get_state_db_path())
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(str(self.db_path))) as conn:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS workspace_state (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        updated_at TEXT NOT NULL,
                        source_mode TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scan_history (
                        scan_id TEXT PRIMARY KEY,
                        scanned_at TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        target TEXT NOT NULL,
                        findings_count INTEGER NOT NULL,
                        nodes_count INTEGER NOT NULL,
                        edges_count INTEGER NOT NULL
                    )
                    """
                )

    def load(self) -> Optional[Dict[str, Any]]:
        with closing(sqlite3.connect(str(self.db_path))) as conn:
            row = conn.execute(
                "SELECT source_mode, payload_json, updated_at FROM workspace_state WHERE id = 1"
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row[1])
            payload["_store_source_mode"] = row[0]
            payload["_store_updated_at"] = row[2]
            return payload
        except Exception:
            return None

    def save(self, payload: Dict[str, Any], source_mode: str = "demo_seed") -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        serialized = json.dumps(payload)
        with closing(sqlite3.connect(str(self.db_path))) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO workspace_state (id, updated_at, source_mode, payload_json)
                    VALUES (1, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        updated_at = excluded.updated_at,
                        source_mode = excluded.source_mode,
                        payload_json = excluded.payload_json
                    """,
                    (now, source_mode, serialized),
                )

    def record_scan(
        self,
        scan_id: str,
        source_type: str,
        target: str,
        findings_count: int,
        nodes_count: int,
        edges_count: int,
    ) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with closing(sqlite3.connect(str(self.db_path))) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO scan_history
                    (scan_id, scanned_at, source_type, target, findings_count, nodes_count, edges_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (scan_id, now, source_type, target, findings_count, nodes_count, edges_count),
                )

    def list_scans(self, limit: int = 10) -> list[Dict[str, Any]]:
        with closing(sqlite3.connect(str(self.db_path))) as conn:
            rows = conn.execute(
                """
                SELECT scan_id, scanned_at, source_type, target, findings_count, nodes_count, edges_count
                FROM scan_history ORDER BY scanned_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "scan_id": r[0],
                "scanned_at": r[1],
                "source_type": r[2],
                "target": r[3],
                "findings_count": r[4],
                "nodes_count": r[5],
                "edges_count": r[6],
            }
            for r in rows
        ]
