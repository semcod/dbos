"""Runtime config manager — env vars as defaults, SQLite overrides.

UI panel (and any service) can mutate values at runtime; the SQLite table
shadows the environment.  All protocol gateways, connectors and workers should
read their settings through `get_config()` rather than `os.environ` directly so
that live changes from the admin panel take effect without a restart.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Optional


DEFAULT_PATH = os.environ.get("CONFIG_DB", "/config-data/platform-config.sqlite")


class ConfigManager:
    """Two-tier config: 1) SQLite override, 2) env var fallback."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or DEFAULT_PATH
        self._ensure()

    def _ensure(self):
        parent = os.path.dirname(self.path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with sqlite3.connect(self.path) as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            c.commit()

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with sqlite3.connect(self.path) as c:
            row = c.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
            if row:
                return row[0]
        return os.environ.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        val = self.get(key)
        if val is None:
            return default
        try:
            return int(val)
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        val = self.get(key)
        if val is None:
            return default
        return val.lower() in ("1", "true", "yes", "on")

    def set(self, key: str, value: str) -> None:
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.path) as c:
            c.execute(
                """INSERT INTO settings (key, value, updated_at)
                     VALUES (?, ?, ?)
                     ON CONFLICT(key) DO UPDATE SET
                       value=excluded.value,
                       updated_at=excluded.updated_at""",
                (key, value, now),
            )
            c.commit()

    def delete(self, key: str) -> None:
        with sqlite3.connect(self.path) as c:
            c.execute("DELETE FROM settings WHERE key=?", (key,))
            c.commit()

    def all(self) -> dict:
        """Return every env var that looks like a platform setting plus SQLite overrides."""
        out = {}
        # Start with env vars that match known prefixes
        prefixes = (
            "POSTGRES_", "API_", "BUS_", "UI_", "CDN_", "WEBDAV_",
            "JWT_", "SYNC_", "MERGE_", "FTP_", "IMAP_", "POP3_", "SMTP_",
            "STORAGE_", "COMMAND_BUS_", "MIRROR_", "SQLITE_", "MYSQL_",
            "VFS_", "CONFIG_",
        )
        for k, v in os.environ.items():
            if any(k.startswith(p) for p in prefixes):
                out[k] = {"value": v, "source": "env"}
        # SQLite overrides shadow env
        with sqlite3.connect(self.path) as c:
            for k, v, ts in c.execute(
                "SELECT key, value, updated_at FROM settings ORDER BY key"
            ).fetchall():
                out[k] = {"value": v, "source": "sqlite", "updated_at": ts}
        return out

    def protocol_settings(self) -> dict:
        """Convenience: all protocol-related keys as a flat dict."""
        keys = [
            "FTP_PORT", "FTP_HOST", "FTP_USER", "FTP_PASS",
            "FTP_PASV_MIN", "FTP_PASV_MAX",
            "IMAP_PORT", "IMAP_HOST", "IMAP_USER", "IMAP_PASS",
            "POP3_PORT", "POP3_HOST", "POP3_USER", "POP3_PASS",
            "SMTP_PORT", "SMTP_HOST",
        ]
        return {k: self.get(k) for k in keys}


# Singleton instance used by the whole Python side of the platform
_cfg: Optional[ConfigManager] = None


def get_config(path: Optional[str] = None) -> ConfigManager:
    global _cfg
    if _cfg is None:
        _cfg = ConfigManager(path)
    return _cfg


def reload_config(path: Optional[str] = None) -> ConfigManager:
    global _cfg
    _cfg = ConfigManager(path)
    return _cfg


if __name__ == "__main__":
    cm = get_config()
    print("protocol_settings:", cm.protocol_settings())
    print("all:", cm.all())
