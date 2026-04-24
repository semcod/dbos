"""sql-mirror — project rows from an external SQL database into platform
entities. Supports MySQL and SQLite as sources. Each row becomes a JSON
entity keyed by a configurable column.

`inbound_sources` row example:
    id              = 'legacy-crm-customers'
    driver          = 'sql'
    endpoint        = 'mysql://reader@legacy-db:3306/crm'
    credentials_ref = 'LEGACY_CRM'             # env LEGACY_CRM_USER/_PASS
    target_schema   = 'customer_v1'
    target_mime     = 'application/json'
    config          = {
        "query":     "SELECT id, name, email, updated_at FROM customers",
        "key_column": "id",
        "entity_type": "customer"
    }
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlparse

from _base import run_forever


def _rows(endpoint: str, cred_ref: str, query: str):
    u = urlparse(endpoint)
    user = os.environ.get(f"{cred_ref}_USER") if cred_ref else None
    pw   = os.environ.get(f"{cred_ref}_PASS") if cred_ref else None

    if u.scheme == "mysql":
        import pymysql
        conn = pymysql.connect(
            host=u.hostname, port=u.port or 3306,
            user=user or u.username or "root",
            password=pw or u.password or "",
            database=(u.path or "/").lstrip("/"),
            charset="utf8mb4",
        )
        try:
            with conn.cursor() as cur:
                cur.execute(query)
                cols = [d[0] for d in cur.description]
                for r in cur.fetchall():
                    yield dict(zip(cols, r))
        finally:
            conn.close()

    elif u.scheme in ("sqlite", "sqlite3"):
        import sqlite3
        path = u.path or ":memory:"
        con = sqlite3.connect(path)
        try:
            con.row_factory = sqlite3.Row
            for r in con.execute(query):
                yield {k: r[k] for k in r.keys()}
        finally:
            con.close()

    elif u.scheme == "postgres" or u.scheme == "postgresql":
        import psycopg
        dsn = endpoint
        if cred_ref and user and pw:
            dsn = f"{u.scheme}://{user}:{pw}@{u.hostname}:{u.port or 5432}{u.path}"
        with psycopg.connect(dsn) as c, c.cursor() as cur:
            cur.execute(query)
            cols = [d.name for d in cur.description]
            for r in cur.fetchall():
                yield dict(zip(cols, r))
    else:
        raise ValueError(f"unsupported sql scheme: {u.scheme}")


def pull_once(src, store):
    cfg = src.get("config") or {}
    query = cfg.get("query")
    if not query:
        return
    key = cfg.get("key_column", "id")
    entity_type = cfg.get("entity_type") or src.get("target_schema") or "row"
    target_mime = src.get("target_mime") or "application/json"

    for row in _rows(src["endpoint"], src.get("credentials_ref"), query):
        remote_id = str(row.get(key))
        if remote_id is None:
            continue
        external_id = src["id_template"].format(
            source_id=src["id"], remote_id=remote_id)

        # Make row JSON-safe: stringify dates etc.
        safe = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}
        body = json.dumps(safe, default=str).encode("utf-8")

        store.write(external_id, entity_type, target_mime, body, source="sql-mirror")
        yield external_id


if __name__ == "__main__":
    run_forever("sql", pull_once)
