"""Postgres-backed EntityStore — the canonical implementation.

Every other adapter is a simplification or mirror of this one. The logic here
intentionally mirrors the write path in `vfs-webdav/app.py` so behaviour is
consistent across every protocol.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Iterable, Optional, Tuple

import psycopg

from .base import EntityStore, EntityRef, MIME_IO


class PgStore(EntityStore):
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.environ["DATABASE_URL"]

    # ------------------------------------------------------------------ util
    def _conn(self):
        return psycopg.connect(self.dsn)

    # ------------------------------------------------------------------ discovery
    def list_types(self):
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                """
                SELECT s.name, s.mime_type, sp.path_template
                  FROM schemas s
                  JOIN schema_paths sp ON sp.schema_id = s.id
                 WHERE sp.path_template IS NOT NULL
                """
            )
            for name, mime, tpl in cur.fetchall():
                ext = "." + tpl.rsplit(".", 1)[-1] if "." in tpl else ""
                yield name, mime, ext

    def list_entities(self, entity_type: str):
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                """
                SELECT e.external_id, e.entity_type, e.primary_mime,
                       vec.updated_at, vec.version
                  FROM entities e
                  LEFT JOIN v_entity_contents vec ON vec.entity_id = e.id
                 WHERE e.entity_type = %s
                 ORDER BY e.external_id
                """,
                (entity_type,),
            )
            for eid, etype, mime, updated, ver in cur.fetchall():
                yield EntityRef(external_id=eid, entity_type=etype, mime=mime,
                                updated_at=updated, version=ver or 0)

    # ------------------------------------------------------------------ read
    def read(self, external_id: str):
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT id, primary_mime FROM entities WHERE external_id = %s",
                (external_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            entity_id, mime = row
            if mime not in MIME_IO:
                return None
            _ext, table, col, kind = MIME_IO[mime]
            cur.execute(
                f"SELECT {col}, updated_at FROM {table} "
                f"WHERE entity_id = %s ORDER BY updated_at DESC LIMIT 1",
                (entity_id,),
            )
            r = cur.fetchone()
            if not r:
                return (b"", mime, None)
            raw, updated = r
            if kind == "json":
                body = json.dumps(raw, indent=2).encode("utf-8")
            elif kind == "bytes":
                body = bytes(raw) if raw else b""
            else:
                body = (raw or "").encode("utf-8")
            return body, mime, updated

    # ------------------------------------------------------------------ write
    def write(self, external_id, entity_type, mime, body, source="gateway"):
        if mime not in MIME_IO:
            raise ValueError(f"unsupported mime: {mime}")
        _ext, table, col, kind = MIME_IO[mime]
        checksum = hashlib.sha256(body).hexdigest()

        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                """
                INSERT INTO entities (external_id, entity_type, schema_id, primary_mime)
                VALUES (%s, %s,
                  (SELECT id FROM schemas WHERE mime_type=%s AND name=%s LIMIT 1),
                  %s)
                ON CONFLICT (external_id) DO UPDATE SET entity_type = EXCLUDED.entity_type
                RETURNING id
                """,
                (external_id, entity_type, mime, entity_type, mime),
            )
            entity_id = cur.fetchone()[0]

            if kind == "json":
                data = json.loads(body.decode("utf-8") or "{}")
                cur.execute(
                    f"""INSERT INTO {table} (entity_id, data, checksum, source)
                         VALUES (%s, %s::jsonb, %s, %s)
                         ON CONFLICT (entity_id) DO UPDATE
                           SET data=EXCLUDED.data, checksum=EXCLUDED.checksum, source=EXCLUDED.source""",
                    (entity_id, json.dumps(data), checksum, source),
                )
            elif kind == "bytes":
                cur.execute(
                    f"""INSERT INTO {table} (entity_id, mime, storage_mode, bytes, size_bytes, checksum, source)
                         VALUES (%s, %s, 'db', %s, %s, %s, %s)""",
                    (entity_id, mime, body, len(body), checksum, source),
                )
            else:
                text = body.decode("utf-8", errors="replace")
                if table == "content_yaml":
                    try:
                        import yaml as y
                        parsed = y.safe_load(text) or {}
                    except Exception:
                        parsed = {}
                    cur.execute(
                        f"""INSERT INTO {table} (entity_id, raw_text, parsed, checksum, source)
                             VALUES (%s, %s, %s::jsonb, %s, %s)
                             ON CONFLICT (entity_id) DO UPDATE
                               SET raw_text=EXCLUDED.raw_text, parsed=EXCLUDED.parsed,
                                   checksum=EXCLUDED.checksum, source=EXCLUDED.source""",
                        (entity_id, text, json.dumps(parsed), checksum, source),
                    )
                elif table == "content_xml":
                    cur.execute(
                        f"""INSERT INTO {table} (entity_id, raw_text, parsed, checksum, source)
                             VALUES (%s, %s, '{{}}'::jsonb, %s, %s)
                             ON CONFLICT (entity_id) DO UPDATE
                               SET raw_text=EXCLUDED.raw_text, checksum=EXCLUDED.checksum, source=EXCLUDED.source""",
                        (entity_id, text, checksum, source),
                    )
                elif table == "content_html":
                    cur.execute(
                        f"""INSERT INTO {table} (entity_id, body, is_template, checksum, source)
                             VALUES (%s, %s, %s, %s, %s)""",
                        (entity_id, text, ("{{" in text or "{%" in text), checksum, source),
                    )
                else:
                    cur.execute(
                        f"""INSERT INTO {table} (entity_id, body, checksum, source)
                             VALUES (%s, %s, %s, %s)
                             ON CONFLICT (entity_id) DO UPDATE
                               SET body=EXCLUDED.body, checksum=EXCLUDED.checksum, source=EXCLUDED.source""",
                        (entity_id, text, checksum, source),
                    )

            cur.execute(
                "INSERT INTO audit_log (content_table, entity_id, source, action) VALUES (%s, %s, %s, %s)",
                (table, entity_id, source, "write"),
            )
            c.commit()

    # ------------------------------------------------------------------ delete
    def delete(self, external_id):
        with self._conn() as c, c.cursor() as cur:
            cur.execute("DELETE FROM entities WHERE external_id = %s", (external_id,))
            c.commit()
