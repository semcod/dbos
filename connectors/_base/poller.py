"""Common skeleton for every inbound connector.

A connector is a long-running loop that:
  1. reads its config rows from `inbound_sources` (filtered by driver),
  2. for each row calls `pull_once(row, store)`,
  3. sleeps `poll_seconds`,
  4. records outcome in `inbound_sources.last_run_at / last_status`.

Connector modules implement `pull_once(row, store)`. Everything else lives
here so the four connectors share identical orchestration.
"""
from __future__ import annotations

import os
import time
import traceback
from typing import Callable, Iterable

import psycopg

from platform_storage import get_store


DATABASE_URL = os.environ["DATABASE_URL"]


def _load_sources(driver: str):
    with psycopg.connect(DATABASE_URL) as c, c.cursor() as cur:
        cur.execute(
            """SELECT id, driver, endpoint, credentials_ref, poll_seconds,
                      target_schema, target_mime, id_template, config
                 FROM inbound_sources
                WHERE driver = %s AND enabled""",
            (driver,),
        )
        cols = [d.name for d in cur.description]
        for row in cur.fetchall():
            yield dict(zip(cols, row))


def _mark(source_id: str, status: str):
    try:
        with psycopg.connect(DATABASE_URL) as c, c.cursor() as cur:
            cur.execute(
                "UPDATE inbound_sources SET last_run_at = now(), last_status = %s WHERE id = %s",
                (status, source_id),
            )
            c.commit()
    except Exception:
        pass


def run_forever(driver: str, pull_once: Callable[[dict, object], Iterable[str]]):
    # Wait for DB
    for _ in range(30):
        try:
            get_store().list_types()
            break
        except Exception:
            print(f"[{driver}-pull] waiting for DB…")
            time.sleep(2)

    store = get_store()
    print(f"[{driver}-pull] started")

    default_sleep = int(os.environ.get("DEFAULT_POLL_SECONDS", "60"))

    while True:
        try:
            sources = list(_load_sources(driver))
        except Exception as e:
            print(f"[{driver}-pull] waiting for inbound_sources registry: {e}")
            time.sleep(default_sleep)
            continue
        if not sources:
            time.sleep(default_sleep)
            continue

        sleep_for = default_sleep
        for src in sources:
            sleep_for = min(sleep_for, max(5, int(src.get("poll_seconds") or default_sleep)))
            try:
                written = list(pull_once(src, store))
                _mark(src["id"], f"ok:{len(written)}")
                if written:
                    print(f"[{driver}-pull] {src['id']}: wrote {len(written)} entities")
            except Exception as e:
                traceback.print_exc()
                _mark(src["id"], f"error:{e.__class__.__name__}:{str(e)[:120]}")

        time.sleep(sleep_for)
