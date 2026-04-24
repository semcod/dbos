"""MySQL mirror adapter — same flat layout as SqliteStore, keyed on external_id.
Activated when `storage_backends.driver = 'mysql'`.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from .base import EntityStore, EntityRef, MIME_IO


class MysqlStore(EntityStore):
    def __init__(self, dsn: Optional[str] = None):
        try:
            import pymysql  # type: ignore
        except ImportError as e:
            raise RuntimeError("mysql adapter requires `pymysql`") from e
        self._pymysql = pymysql
        self.dsn = dsn or os.environ["MYSQL_DSN"]  # user:pw@host:port/db
        self._ensure()

    # tiny DSN parser
    def _connect(self):
        dsn = self.dsn.replace("mysql://", "")
        creds, rest = dsn.split("@", 1)
        user, pw = creds.split(":", 1)
        hostport, db = rest.split("/", 1)
        host, port = (hostport.split(":", 1) + ["3306"])[:2]
        return self._pymysql.connect(host=host, port=int(port), user=user,
                                     password=pw, database=db, charset="utf8mb4")

    def _ensure(self):
        with self._connect() as c:
            with c.cursor() as cur:
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS entities (
                        external_id VARCHAR(255) PRIMARY KEY,
                        entity_type VARCHAR(64) NOT NULL,
                        mime VARCHAR(128) NOT NULL,
                        body LONGBLOB NOT NULL,
                        updated_at DATETIME NOT NULL
                    ) ENGINE=InnoDB"""
                )
            c.commit()

    def list_types(self):
        with self._connect() as c:
            with c.cursor() as cur:
                cur.execute("SELECT DISTINCT entity_type, mime FROM entities")
                for etype, mime in cur.fetchall():
                    yield etype, mime, MIME_IO.get(mime, (".bin",))[0]

    def list_entities(self, entity_type):
        with self._connect() as c:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT external_id, entity_type, mime, updated_at, OCTET_LENGTH(body) "
                    "FROM entities WHERE entity_type=%s ORDER BY external_id",
                    (entity_type,),
                )
                for eid, etype, mime, updated, size in cur.fetchall():
                    yield EntityRef(external_id=eid, entity_type=etype, mime=mime,
                                    updated_at=updated, size=size or 0)

    def read(self, external_id):
        with self._connect() as c:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT body, mime, updated_at FROM entities WHERE external_id=%s",
                    (external_id,),
                )
                r = cur.fetchone()
        if not r:
            return None
        body, mime, updated = r
        return bytes(body), mime, updated

    def write(self, external_id, entity_type, mime, body, source="gateway"):
        with self._connect() as c:
            with c.cursor() as cur:
                cur.execute(
                    """INSERT INTO entities (external_id, entity_type, mime, body, updated_at)
                       VALUES (%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE entity_type=VALUES(entity_type),
                         mime=VALUES(mime), body=VALUES(body), updated_at=VALUES(updated_at)""",
                    (external_id, entity_type, mime, body, datetime.utcnow()),
                )
            c.commit()

    def delete(self, external_id):
        with self._connect() as c:
            with c.cursor() as cur:
                cur.execute("DELETE FROM entities WHERE external_id=%s", (external_id,))
            c.commit()
