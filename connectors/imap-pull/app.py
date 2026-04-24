"""imap-pull — poll an external IMAP mailbox, ingest each message as an
entity. External form is identical to what vfs-smtp produces, so a message
written via SMTP and one fetched via IMAP end up in the same shape.

`inbound_sources` row example:
    id            = 'imap-support-mailbox'
    driver        = 'imap'
    endpoint      = 'imaps://mail.example.com:993'
    credentials_ref = 'SUPPORT_IMAP'           # expects env SUPPORT_IMAP_USER/_PASS
    target_mime   = 'text/markdown'
    config        = {"mailbox":"INBOX","delete_after_fetch":false,"limit":50}
"""
from __future__ import annotations

import email
import email.policy
import hashlib
import imaplib
import os
import re
from urllib.parse import urlparse

from _base import run_forever


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s).strip("-").lower()
    return s[:60] or "untitled"


def _connect(endpoint: str, cred_ref: str):
    u = urlparse(endpoint)
    host = u.hostname or "localhost"
    port = u.port or (993 if u.scheme == "imaps" else 143)
    cls  = imaplib.IMAP4_SSL if u.scheme == "imaps" else imaplib.IMAP4
    m = cls(host, port)

    user = os.environ.get(f"{cred_ref}_USER") if cred_ref else None
    pw   = os.environ.get(f"{cred_ref}_PASS") if cred_ref else None
    if user and pw:
        m.login(user, pw)
    return m


def pull_once(src, store):
    cfg = src.get("config") or {}
    mailbox = cfg.get("mailbox", "INBOX")
    limit   = int(cfg.get("limit", 50))
    drop    = bool(cfg.get("delete_after_fetch", False))
    target_mime = src.get("target_mime") or "text/markdown"

    m = _connect(src["endpoint"], src.get("credentials_ref"))
    try:
        m.select(mailbox, readonly=not drop)
        typ, data = m.search(None, "ALL")
        if typ != "OK":
            return
        ids = data[0].split()[-limit:]
        for num in ids:
            typ, fetched = m.fetch(num, "(RFC822)")
            if typ != "OK":
                continue
            raw = fetched[0][1]
            msg = email.message_from_bytes(raw, policy=email.policy.default)
            subject = msg.get("Subject", "(no subject)")
            mid     = msg.get("Message-ID") or hashlib.sha256(raw).hexdigest()[:16]
            slug    = _slugify(subject) or hashlib.sha256(mid.encode()).hexdigest()[:12]
            external_id = src["id_template"].format(
                source_id=src["id"], remote_id=slug)

            body_part = msg.get_body(preferencelist=("plain", "html"))
            body_text = body_part.get_content() if body_part else ""

            doc = (
                "---\n"
                f"from: {msg.get('From','')}\n"
                f"subject: \"{subject}\"\n"
                f"message_id: \"{mid}\"\n"
                f"date: {msg.get('Date','')}\n"
                f"source: imap-pull/{src['id']}\n"
                "---\n"
                f"{body_text}\n"
            )
            store.write(external_id, "mail", target_mime, doc.encode("utf-8"),
                        source="imap-pull")
            yield external_id

            if drop:
                m.store(num, "+FLAGS", "\\Deleted")
        if drop:
            m.expunge()
    finally:
        try:
            m.logout()
        except Exception:
            pass


if __name__ == "__main__":
    run_forever("imap", pull_once)
