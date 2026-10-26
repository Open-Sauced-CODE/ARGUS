"""
ARGUS Phase 4 - local token vault.

Maps tokens (BUCKET_3, ROLE_7, ...) to the real values they replaced. Real values are
encrypted with Fernet (AES-128-CBC + HMAC, from the `cryptography` package) before they are
written to a local SQLite file, so the database alone reveals nothing.

Key lookup order:
  1. the `key=` argument,
  2. environment variable ARGUS_VAULT_KEY,
  3. a key file (env ARGUS_VAULT_KEY_FILE, else privacy/vault/.vault.key) - created on first use.
Database path: `db_path=` argument, else env ARGUS_VAULT_PATH, else privacy/vault/vault.db.
"""

import os
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_VAULT_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = _VAULT_DIR / "vault.db"
DEFAULT_KEY_PATH = _VAULT_DIR / ".vault.key"


class VaultError(Exception):
    """Raised when the vault cannot find or decrypt a value."""


class TokenVault:
    def __init__(self, db_path=None, key=None, key_path=None):
        self.db_path = Path(db_path or os.environ.get("ARGUS_VAULT_PATH") or DEFAULT_DB_PATH)
        try:
            self._fernet = Fernet(self._resolve_key(key, key_path))
        except ValueError as exc:
            raise VaultError("Invalid vault key (must be a Fernet key): {}".format(exc)) from exc
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS tokens ("
                    "ref TEXT PRIMARY KEY, token TEXT NOT NULL, kind TEXT NOT NULL, "
                    "enc_value BLOB NOT NULL, created_at TEXT NOT NULL)"
                )

    # -- key handling -------------------------------------------------------
    @staticmethod
    def _resolve_key(key, key_path):
        if key:
            return key
        env_key = os.environ.get("ARGUS_VAULT_KEY")
        if env_key:
            return env_key.encode("utf-8")
        path = Path(key_path or os.environ.get("ARGUS_VAULT_KEY_FILE") or DEFAULT_KEY_PATH)
        if path.exists() and path.read_bytes().strip():
            return path.read_bytes().strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        new_key = Fernet.generate_key()
        path.write_bytes(new_key)
        return new_key

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    # -- storage ------------------------------------------------------------
    def put_many(self, items):
        """items: iterable of (token, kind, real_value). Returns {token: vault_ref}."""
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        refs = {}
        for token, kind, real in items:
            ref = secrets.token_hex(8)
            refs[token] = ref
            rows.append((ref, token, kind, self._fernet.encrypt(real.encode("utf-8")), now))
        if rows:
            with closing(self._connect()) as conn:
                with conn:
                    conn.executemany("INSERT INTO tokens VALUES (?, ?, ?, ?, ?)", rows)
        return refs

    def get(self, ref):
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT enc_value FROM tokens WHERE ref = ?", (ref,)).fetchone()
        if row is None:
            raise VaultError("Unknown vault reference")
        try:
            return self._fernet.decrypt(row[0]).decode("utf-8")
        except InvalidToken as exc:
            raise VaultError("Vault value could not be decrypted (wrong key?)") from exc

    def values_for(self, refs):
        """Real values for an iterable of vault refs (used by the leak-check)."""
        return [self.get(r) for r in refs]


_DEFAULT = {"vault": None}


def get_default_vault():
    if _DEFAULT["vault"] is None:
        _DEFAULT["vault"] = TokenVault()
    return _DEFAULT["vault"]
