"""sync-outbound — export platform entities to filesystem / external targets.

Reads `service_mappings` to discover active pipelines, then tails `audit_log`
and pushes matching entities to their declared targets (filesystem, SMTP,
webhook, etc.).  Adding a row to `service_mappings` creates a new pipeline
without code change.
"""
from __future__ import annotations

import json
import os
import re
import time
import traceback
from datetime import datetime
from typing import Any

import psycopg
import yaml

DATABASE_URL = os.environ["DATABASE_URL"]
DEFAULT_POLL = int(os.environ.get("OUTBOUND_POLL_SECONDS", "3"))


def _conn():
    return psycopg.connect(DATABASE_URL)


def _load_mappings():
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """SELECT id, source_service, target_service, filter, transform, enabled
                 FROM service_mappings WHERE enabled"""
        )
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetch_changes(last_id: int, limit: int = 50):
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """SELECT a.id, a.entity_id, a.content_table, a.action, a.source,
                      e.external_id, e.entity_type, e.schema_id, e.primary_mime
                 FROM audit_log a
                 JOIN entities e ON e.id = a.entity_id
                WHERE a.id > %s AND a.action IN ('create','update')
                ORDER BY a.id LIMIT %s""",
            (last_id, limit),
        )
        cols = [d.name for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    return rows


def _read_body(entity_id, content_table):
    with _conn() as c, c.cursor() as cur:
        if content_table == "content_markdown":
            cur.execute(
                "SELECT body, front_matter FROM content_markdown WHERE entity_id=%s",
                (entity_id,),
            )
        elif content_table == "content_json":
            cur.execute("SELECT data FROM content_json WHERE entity_id=%s", (entity_id,))
        elif content_table == "content_html":
            cur.execute("SELECT body FROM content_html WHERE entity_id=%s", (entity_id,))
        elif content_table == "content_yaml":
            cur.execute("SELECT raw_text FROM content_yaml WHERE entity_id=%s", (entity_id,))
        elif content_table == "content_xml":
            cur.execute("SELECT raw_text FROM content_xml WHERE entity_id=%s", (entity_id,))
        else:
            return None, {}
        row = cur.fetchone()
        if not row:
            return None, {}
        if content_table == "content_markdown":
            body, fm = row[0], row[1] or {}
            # Reconstruct front-matter as YAML header
            if fm:
                header = yaml.safe_dump(fm, default_flow_style=False, allow_unicode=True)
                full = "---\n" + header + "---\n\n" + body
            else:
                full = body
            return full.encode("utf-8"), fm
        return (row[0].encode("utf-8") if isinstance(row[0], str) else row[0]), {}
    return None, {}


def _match_filter(entity, filter_json: dict) -> bool:
    if not filter_json:
        return True
    for k, v in filter_json.items():
        if entity.get(k) != v:
            return False
    return True


def _to_rfc5322(external_id: str, body: bytes, front_matter: dict) -> bytes:
    """Convert markdown-with-front-matter to RFC-5322 message."""
    text = body.decode("utf-8", "replace")
    subject = front_matter.get("subject", external_id.split("/")[-1])
    sender = front_matter.get("from", "platform <noreply@platform.local>")
    msg_id = front_matter.get("message_id", f"<{external_id}@platform.local>")
    date = front_matter.get("date", datetime.utcnow().isoformat())

    hdr = [
        f"From: {sender}",
        f"To: admin@platform.local",
        f"Subject: {subject}",
        f"Date: {date}",
        f"Message-ID: {msg_id}",
        f"X-Entity-ID: {external_id}",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "",
    ]
    return ("\r\n".join(hdr)).encode("utf-8") + b"\r\n" + text.encode("utf-8")


def _write_filesystem(entity, body: bytes, fm: dict, transform: dict, target_service: str):
    target = target_service
    fmt = transform.get("format", "raw")
    ext = transform.get("extension", ".txt")
    out_dir = os.environ.get("OUTBOUND_DIR", "/data")

    # target_service like 'filesystem-email' -> subdir 'email'
    subdir = target.split("-")[-1] if "-" in target else target
    folder = os.path.join(out_dir, subdir)
    os.makedirs(folder, exist_ok=True)

    eid = entity["external_id"].replace("/", "_")
    path = os.path.join(folder, f"{eid}{ext}")

    if fmt == "rfc5322" and entity.get("primary_mime") == "text/markdown":
        payload = _to_rfc5322(entity["external_id"], body, fm)
    else:
        payload = body

    with open(path, "wb") as f:
        f.write(payload)
    return path


def _mark(mapping_id: str, status: str):
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute(
                "UPDATE service_mappings SET last_run_at=now(), last_status=%s WHERE id=%s",
                (status, mapping_id),
            )
            c.commit()
    except Exception:
        pass


def main():
    last_id = 0
    for _ in range(30):
        try:
            with _conn() as c:
                c.execute("SELECT 1")
            break
        except Exception:
            print("[outbound] waiting for DB…")
            time.sleep(2)

    print(f"[outbound] started, poll={DEFAULT_POLL}s")

    while True:
        mappings = _load_mappings()
        if not mappings:
            time.sleep(DEFAULT_POLL)
            continue

        rows = _fetch_changes(last_id)
        if not rows:
            time.sleep(DEFAULT_POLL)
            continue

        for row in rows:
            last_id = max(last_id, row["id"])
            body, fm = _read_body(row["entity_id"], row["content_table"])
            if body is None:
                continue

            for m in mappings:
                filt = m.get("filter") or {}
                if isinstance(filt, str):
                    filt = json.loads(filt)
                if not _match_filter(row, filt):
                    continue

                transform = m.get("transform") or {}
                if isinstance(transform, str):
                    transform = json.loads(transform)

                try:
                    if m["target_service"].startswith("filesystem"):
                        path = _write_filesystem(row, body, fm, transform, m["target_service"])
                        print(f"[outbound] {m['id']}: wrote {path}")
                        _mark(m["id"], f"ok:{path}")
                    else:
                        _mark(m["id"], f"skipped:{m['target_service']}")
                except Exception as e:
                    traceback.print_exc()
                    _mark(m["id"], f"error:{e.__class__.__name__}:{str(e)[:120]}")

        time.sleep(DEFAULT_POLL)


if __name__ == "__main__":
    main()
