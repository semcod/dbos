"""storage-mirror — tail `audit_log` and replay writes into every
`storage_backends` row whose role = 'mirror'. Keeps alternative databases
(SQLite, MySQL, …) byte-for-byte in sync with Postgres.

Because every mirror target implements the same `EntityStore` contract, the
daemon doesn't care which backend it's talking to — it just calls
`mirror.write(external_id, entity_type, mime, body)`.
"""
from __future__ import annotations

import os
import time

import psycopg

from platform_storage import get_store


DATABASE_URL = os.environ["DATABASE_URL"]
POLL_SECONDS = int(os.environ.get("MIRROR_POLL_SECONDS", "3"))


def _load_mirrors():
    with psycopg.connect(DATABASE_URL) as c, c.cursor() as cur:
        cur.execute(
            "SELECT id, mime_filter FROM storage_backends WHERE role='mirror' AND enabled"
        )
        return [(mid, set(mimes or [])) for mid, mimes in cur.fetchall()]


def _fetch_changes(since_id: int, limit: int = 500):
    with psycopg.connect(DATABASE_URL) as c, c.cursor() as cur:
        cur.execute(
            """SELECT a.id, a.content_table, a.entity_id, e.external_id, e.entity_type,
                      e.primary_mime
                 FROM audit_log a
                 JOIN entities e ON e.id = a.entity_id
                WHERE a.id > %s
                ORDER BY a.id ASC
                LIMIT %s""",
            (since_id, limit),
        )
        return cur.fetchall()


def _read_body(primary, external_id):
    return primary.read(external_id)


def main():
    # Boot guard
    for _ in range(30):
        try:
            get_store("pg-primary").list_types()
            break
        except Exception:
            print("[mirror] waiting for DB…")
            time.sleep(2)

    primary = get_store("pg-primary")

    last_id = 0
    while True:
        try:
            mirrors = {}
            try:
                for mid, mime_filter in _load_mirrors():
                    try:
                        mirrors[mid] = (get_store(mid), mime_filter)
                    except Exception as e:
                        print(f"[mirror] cannot init {mid}: {e}")
                if not mirrors:
                    print("[mirror] no mirror backends declared; idling")
            except Exception as e:
                print(f"[mirror] waiting for storage_backends registry: {e}")
                time.sleep(POLL_SECONDS)
                continue

            rows = _fetch_changes(last_id)
            for aid, _table, _eid, external_id, entity_type, mime in rows:
                last_id = aid
                got = _read_body(primary, external_id)
                if not got:
                    continue
                body, actual_mime, _ = got
                for mid, (adapter, mime_filter) in mirrors.items():
                    if mime_filter and actual_mime not in mime_filter:
                        continue
                    try:
                        adapter.write(external_id, entity_type, actual_mime, body,
                                      source="mirror")
                    except Exception as e:
                        print(f"[mirror] {mid} write failed for {external_id}: {e}")
        except Exception as e:
            print(f"[mirror] loop error: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
