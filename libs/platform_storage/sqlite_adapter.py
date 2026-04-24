"""SQLite mirror adapter — writes every entity into a local sqlite file so
the same data can live in an embedded DB without touching the Postgres
source of truth. Read path re-hydrates rows as if they were in Postgres.

This is a *mirror-oriented* implementation. Single logical table `entities`
with (external_id, entity_type, mime, body, updated_at).
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Optional

from .base import EntityStore, EntityRef, MIME_IO


class SqliteStore(EntityStore):
    def __init__(self, dsn: Optional[str] = None):
        path = dsn or os.environ.get("SQLITE_PATH", "/tmp/platform.sqlite")
        self.path = path.replace("sqlite://", "")
        self._ensure()

    def _ensure(self):
        with sqlite3.connect(self.path) as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS entities (
                    external_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    mime TEXT NOT NULL,
                    body BLOB NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            c.commit()

    def list_types(self):
        with sqlite3.connect(self.path) as c:
            rows = c.execute(
                "SELECT DISTINCT entity_type, mime FROM entities"
            ).fetchall()
        for etype, mime in rows:
            ext = MIME_IO.get(mime, (".bin",))[0]
            yield etype, mime, ext

    def list_entities(self, entity_type):
        with sqlite3.connect(self.path) as c:
            rows = c.execute(
                "SELECT external_id, entity_type, mime, updated_at, length(body) "
                "FROM entities WHERE entity_type=? ORDER BY external_id",
                (entity_type,),
            ).fetchall()
        for eid, etype, mime, updated, size in rows:
            yield EntityRef(external_id=eid, entity_type=etype, mime=mime,
                            updated_at=datetime.fromisoformat(updated) if updated else None,
                            size=size or 0)

    def read(self, external_id):
        with sqlite3.connect(self.path) as c:
            r = c.execute(
                "SELECT body, mime, updated_at FROM entities WHERE external_id=?",
                (external_id,),
            ).fetchone()
        if not r:
            return None
        body, mime, updated = r
        return bytes(body), mime, datetime.fromisoformat(updated) if updated else None

    def write(self, external_id, entity_type, mime, body, source="gateway"):
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.path) as c:
            c.execute(
                """INSERT INTO entities (external_id, entity_type, mime, body, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(external_id) DO UPDATE SET
                     entity_type=excluded.entity_type,
                     mime=excluded.mime, body=excluded.body, updated_at=excluded.updated_at""",
                (external_id, entity_type, mime, body, now),
            )
            c.commit()

    def delete(self, external_id):
        with sqlite3.connect(self.path) as c:
            c.execute("DELETE FROM entities WHERE external_id=?", (external_id,))
            c.commit()
