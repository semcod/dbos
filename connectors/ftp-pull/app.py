"""ftp-pull — walk a remote FTP directory, ingest each file as an entity
using the same MIME → content_table mapping as every other gateway.

`inbound_sources` row example:
    id              = 'ftp-partner-drop'
    driver          = 'ftp'
    endpoint        = 'ftp://partner.example.com:21/outgoing'
    credentials_ref = 'PARTNER_FTP'            # env PARTNER_FTP_USER/_PASS
    target_schema   = null                     # inferred from extension
    config          = {"delete_after_fetch": false, "recursive": true}
"""
from __future__ import annotations

import ftplib
import io
import os
import posixpath
from urllib.parse import urlparse

from _base import run_forever
from platform_storage.base import EXT_TO_MIME, MIME_IO


def _connect(endpoint: str, cred_ref: str):
    u = urlparse(endpoint)
    host = u.hostname or "localhost"
    port = u.port or 21
    f = ftplib.FTP()
    f.connect(host, port, timeout=30)
    user = os.environ.get(f"{cred_ref}_USER") if cred_ref else None
    pw   = os.environ.get(f"{cred_ref}_PASS") if cred_ref else None
    f.login(user or "anonymous", pw or "anonymous@")
    if u.path:
        f.cwd(u.path)
    return f, u.path or "/"


def _walk(ftp: ftplib.FTP, root: str, recursive: bool):
    """Yield (remote_path, filename)."""
    try:
        entries = list(ftp.mlsd(root))
    except ftplib.error_perm:
        # server without MLSD — fall back to LIST parsing
        lines = []
        ftp.retrlines(f"LIST {root}", lines.append)
        entries = []
        for ln in lines:
            parts = ln.split(None, 8)
            if len(parts) < 9:
                continue
            name = parts[-1]
            kind = "dir" if ln.startswith("d") else "file"
            entries.append((name, {"type": kind}))

    for name, facts in entries:
        if name in (".", ".."):
            continue
        full = posixpath.join(root, name)
        if facts.get("type") == "dir":
            if recursive:
                yield from _walk(ftp, full, recursive)
        else:
            yield full, name


def pull_once(src, store):
    cfg = src.get("config") or {}
    drop = bool(cfg.get("delete_after_fetch", False))
    recursive = bool(cfg.get("recursive", False))

    ftp, root = _connect(src["endpoint"], src.get("credentials_ref"))
    try:
        for full, name in _walk(ftp, root, recursive):
            ext = os.path.splitext(name)[1].lower()
            mime = src.get("target_mime") or EXT_TO_MIME.get(ext)
            if not mime or mime not in MIME_IO:
                continue

            buf = io.BytesIO()
            ftp.retrbinary(f"RETR {full}", buf.write)
            body = buf.getvalue()

            rel = full.lstrip("/")
            if rel.endswith(ext):
                rel = rel[: -len(ext)]
            external_id = src["id_template"].format(
                source_id=src["id"], remote_id=rel)
            entity_type = rel.split("/", 1)[0] if "/" in rel else "file"

            store.write(external_id, entity_type, mime, body, source="ftp-pull")
            yield external_id

            if drop:
                try:
                    ftp.delete(full)
                except Exception:
                    pass
    finally:
        try:
            ftp.quit()
        except Exception:
            pass


if __name__ == "__main__":
    run_forever("ftp", pull_once)
