"""Factory: pick the adapter by name, looking it up in `storage_backends`.

Services do:
    store = get_store()                       # backend from $STORAGE_BACKEND
or
    store = get_store('sqlite-mirror')        # explicit

If the registry can't be read (early boot), the factory falls back to the
driver given by $STORAGE_DRIVER (default 'postgres') and $DATABASE_URL.
"""
from __future__ import annotations

import os
from typing import Optional

from .base import EntityStore


def _resolve_dsn(raw: Optional[str]) -> Optional[str]:
    """Expand ${VAR} occurrences in a DSN."""
    if not raw:
        return raw
    return os.path.expandvars(raw)


def _instantiate(driver: str, dsn: Optional[str]) -> EntityStore:
    driver = (driver or "postgres").lower()
    if driver == "postgres":
        from .pg_adapter import PgStore
        return PgStore(dsn=_resolve_dsn(dsn))
    if driver == "sqlite":
        from .sqlite_adapter import SqliteStore
        return SqliteStore(dsn=_resolve_dsn(dsn))
    if driver == "mysql":
        from .mysql_adapter import MysqlStore
        return MysqlStore(dsn=_resolve_dsn(dsn))
    raise ValueError(f"unknown storage driver: {driver}")


def get_store(backend_id: Optional[str] = None) -> EntityStore:
    backend_id = backend_id or os.environ.get("STORAGE_BACKEND", "pg-primary")

    # Try to read the registry through whatever Postgres URL we've got.
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        try:
            import psycopg
            with psycopg.connect(db_url) as c, c.cursor() as cur:
                cur.execute(
                    "SELECT driver, dsn FROM storage_backends WHERE id = %s AND enabled",
                    (backend_id,),
                )
                row = cur.fetchone()
                if row:
                    return _instantiate(row[0], row[1])
        except Exception:
            pass  # fall through to env-based bootstrap

    driver = os.environ.get("STORAGE_DRIVER", "postgres")
    dsn    = os.environ.get("STORAGE_DSN") or os.environ.get("DATABASE_URL")
    return _instantiate(driver, dsn)
