"""vfs-imap — minimal IMAP4 server exposing platform entities as mail.

Mapping
-------
    Mailbox "INBOX"                 = all entities
    Mailbox "<entity_type>"         = entities of that type (articles, pages, …)
    Message body                    = content_* payload, wrapped with
                                      RFC-5322 headers built from metadata

Implements enough of RFC 3501 to let a typical IMAP client:
    LOGIN, CAPABILITY, LIST, SELECT, SEARCH ALL, FETCH, LOGOUT

Write-back is not supported (APPEND returns NO). Use FTP/WebDAV for uploads.
Anyone needing full IMAP semantics should plug in a real IMAP implementation
behind the same `EntityStore` contract — protocol is the only thing to change.
"""
from __future__ import annotations

import asyncio
import email.utils
import os
import time
from datetime import datetime
from typing import Dict, List

from platform_storage import get_store
from platform_storage.base import EntityRef


IMAP_USER = os.environ.get("IMAP_USER", "admin")
IMAP_PASS = os.environ.get("IMAP_PASS", "admin")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "1143"))
HOSTNAME  = os.environ.get("IMAP_HOST", "platform.local")


# ---------------------------------------------------------------------------
# Message synthesis
# ---------------------------------------------------------------------------
def ref_to_rfc822(ref: EntityRef, body: bytes, mime: str) -> bytes:
    ts = ref.updated_at or datetime.utcnow()
    date_hdr = email.utils.format_datetime(ts)
    subject  = ref.external_id
    headers = [
        f"From: platform <noreply@{HOSTNAME}>",
        f"To: {IMAP_USER}@{HOSTNAME}",
        f"Subject: {subject}",
        f"Date: {date_hdr}",
        f"Message-ID: <{ref.external_id}@{HOSTNAME}>",
        f"X-Entity-Type: {ref.entity_type}",
        f"X-Entity-Mime: {mime}",
        f"Content-Type: {mime}; charset=utf-8",
        "MIME-Version: 1.0",
        "",
    ]
    blob = ("\r\n".join(headers)).encode("utf-8") + body
    return blob


# ---------------------------------------------------------------------------
# IMAP connection handler
# ---------------------------------------------------------------------------
class Session:
    def __init__(self, reader, writer, store):
        self.r = reader
        self.w = writer
        self.store = store
        self.authed = False
        self.selected = None              # mailbox name
        self.messages: List[EntityRef] = []

    # low-level send
    async def send(self, line: str):
        self.w.write((line + "\r\n").encode("utf-8"))
        await self.w.drain()

    # ------------------------------------------------------------------ helpers
    def _mailboxes(self) -> Dict[str, List[EntityRef]]:
        boxes: Dict[str, List[EntityRef]] = {"INBOX": []}
        for etype, _mime, _ext in self.store.list_types():
            boxes.setdefault(etype, [])
            for ref in self.store.list_entities(etype):
                boxes[etype].append(ref)
                boxes["INBOX"].append(ref)
        return boxes

    def _select(self, mbox: str):
        boxes = self._mailboxes()
        if mbox not in boxes:
            return False
        self.selected = mbox
        self.messages = boxes[mbox]
        return True

    # ------------------------------------------------------------------ run
    async def run(self):
        await self.send(f"* OK [CAPABILITY IMAP4rev1 AUTH=PLAIN LOGINDISABLED] Platform IMAP ready")
        # Simple: allow LOGIN anyway
        while True:
            line = await self.r.readline()
            if not line:
                return
            try:
                cmd = line.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if not cmd:
                continue
            try:
                await self.dispatch(cmd)
            except Exception as e:
                await self.send(f"* BAD internal error: {e}")

    async def dispatch(self, line: str):
        parts = line.split(" ", 2)
        if len(parts) < 2:
            return
        tag, verb = parts[0], parts[1].upper()
        rest = parts[2] if len(parts) > 2 else ""

        if verb == "CAPABILITY":
            await self.send("* CAPABILITY IMAP4rev1 AUTH=PLAIN")
            await self.send(f"{tag} OK CAPABILITY completed")
        elif verb == "NOOP":
            await self.send(f"{tag} OK NOOP completed")
        elif verb == "LOGIN":
            user, _, pw = rest.partition(" ")
            user = user.strip('"')
            pw   = pw.strip('"')
            if user == IMAP_USER and pw == IMAP_PASS:
                self.authed = True
                await self.send(f"{tag} OK LOGIN completed")
            else:
                await self.send(f"{tag} NO LOGIN failed")
        elif verb == "LOGOUT":
            await self.send("* BYE Platform IMAP signing off")
            await self.send(f"{tag} OK LOGOUT completed")
            self.w.close()
        elif verb == "LIST":
            if not self.authed:
                await self.send(f"{tag} NO not authenticated")
                return
            for name in self._mailboxes().keys():
                await self.send(f'* LIST (\\HasNoChildren) "/" "{name}"')
            await self.send(f"{tag} OK LIST completed")
        elif verb == "LSUB":
            await self.send(f"{tag} OK LSUB completed")
        elif verb == "SELECT" or verb == "EXAMINE":
            if not self.authed:
                await self.send(f"{tag} NO not authenticated")
                return
            mbox = rest.strip().strip('"')
            if not self._select(mbox):
                await self.send(f"{tag} NO [NONEXISTENT] mailbox")
                return
            n = len(self.messages)
            await self.send(f"* {n} EXISTS")
            await self.send("* 0 RECENT")
            await self.send("* FLAGS (\\Seen)")
            await self.send(f"* OK [UIDVALIDITY 1] UIDs valid")
            await self.send(f"{tag} OK [READ-ONLY] {verb} completed")
        elif verb == "SEARCH":
            ids = " ".join(str(i + 1) for i in range(len(self.messages)))
            await self.send(f"* SEARCH {ids}".rstrip())
            await self.send(f"{tag} OK SEARCH completed")
        elif verb == "FETCH":
            await self._fetch(tag, rest)
        elif verb == "APPEND":
            await self.send(f"{tag} NO APPEND not supported (use FTP/WebDAV)")
        elif verb == "CLOSE":
            self.selected = None
            await self.send(f"{tag} OK CLOSE completed")
        else:
            await self.send(f"{tag} BAD unknown command: {verb}")

    async def _fetch(self, tag: str, rest: str):
        # rest like:  1:* (RFC822)      or     1 (BODY[])
        try:
            seq, _, what = rest.partition(" ")
        except Exception:
            await self.send(f"{tag} BAD bad FETCH")
            return
        if not self.messages:
            await self.send(f"{tag} OK FETCH completed (empty)")
            return

        # expand sequence
        if seq == "1:*":
            idxs = list(range(1, len(self.messages) + 1))
        else:
            idxs = []
            for chunk in seq.split(","):
                if ":" in chunk:
                    a, b = chunk.split(":", 1)
                    b = len(self.messages) if b == "*" else int(b)
                    idxs.extend(range(int(a), b + 1))
                else:
                    idxs.append(int(chunk))

        for idx in idxs:
            if idx < 1 or idx > len(self.messages):
                continue
            ref = self.messages[idx - 1]
            got = self.store.read(ref.external_id)
            if not got:
                continue
            body, mime, _ = got
            blob = ref_to_rfc822(ref, body, mime)
            size = len(blob)
            await self.send(f"* {idx} FETCH (RFC822.SIZE {size} UID {idx} BODY[] {{{size}}}")
            self.w.write(blob)
            self.w.write(b")\r\n")
            await self.w.drain()
        await self.send(f"{tag} OK FETCH completed")


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
async def handle_client(reader, writer):
    store = get_store()
    session = Session(reader, writer, store)
    try:
        await session.run()
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def main():
    # Wait for DB
    for _ in range(30):
        try:
            get_store().list_types()
            break
        except Exception:
            print("[vfs-imap] waiting for DB…")
            time.sleep(2)

    server = await asyncio.start_server(handle_client, "0.0.0.0", IMAP_PORT)
    print(f"[vfs-imap] IMAP listening on :{IMAP_PORT}  (user: {IMAP_USER})")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
