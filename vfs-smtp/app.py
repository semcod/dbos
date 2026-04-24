"""vfs-smtp — SMTP gateway that ingests incoming mail as platform entities.

Each accepted message is stored as a text/markdown entity under
`mail/<slug>` where slug = first 60 chars of the subject (or the Message-ID
hash). The body is the message body; headers are preserved as YAML front
matter at the top so round-trip via vfs-imap gets them back.
"""
from __future__ import annotations

import asyncio
import email
import email.policy
import hashlib
import os
import re
import time

from aiosmtpd.controller import Controller

from platform_storage import get_store


SMTP_PORT = int(os.environ.get("SMTP_PORT", "2525"))


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s).strip("-").lower()
    return s[:60] or "untitled"


class MailHandler:
    def __init__(self):
        self.store = get_store()

    async def handle_DATA(self, server, session, envelope):
        msg = email.message_from_bytes(envelope.content, policy=email.policy.default)
        subject = msg.get("Subject", "(no subject)")
        sender  = msg.get("From", "")
        mid     = msg.get("Message-ID") or hashlib.sha256(envelope.content).hexdigest()[:16]

        slug = slugify(subject) or hashlib.sha256(mid.encode()).hexdigest()[:12]
        external_id = f"mail/{slug}"

        # prefer plain-text body
        body_part = msg.get_body(preferencelist=("plain", "html"))
        body_text = body_part.get_content() if body_part else msg.get_payload(decode=True).decode("utf-8", "replace")

        doc = (
            "---\n"
            f"from: {sender}\n"
            f"subject: \"{subject}\"\n"
            f"message_id: \"{mid}\"\n"
            f"date: {msg.get('Date','')}\n"
            "source: smtp\n"
            "---\n"
            f"{body_text}\n"
        )

        self.store.write(external_id, "mail", "text/markdown", doc.encode("utf-8"), source="smtp")
        print(f"[vfs-smtp] accepted → {external_id} ({len(doc)} bytes)")
        return "250 OK"


def main():
    # Wait for DB
    for _ in range(30):
        try:
            get_store().list_types()
            break
        except Exception:
            print("[vfs-smtp] waiting for DB…")
            time.sleep(2)

    controller = Controller(MailHandler(), hostname="0.0.0.0", port=SMTP_PORT)
    controller.start()
    print(f"[vfs-smtp] SMTP listening on :{SMTP_PORT}")
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        controller.stop()


if __name__ == "__main__":
    main()
