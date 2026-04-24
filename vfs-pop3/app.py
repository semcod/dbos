"""vfs-pop3 — minimal POP3 server exposing platform entities as mail.

Same message synthesis as vfs-imap (RFC-5322 headers + payload body). Shares
the `EntityStore` contract, so flipping between POP3/IMAP/FTP is a protocol
swap only.

Commands implemented: USER, PASS, STAT, LIST, UIDL, RETR, DELE, NOOP, RSET,
QUIT, CAPA. DELE is accepted and mapped to `store.delete()`.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import List

from platform_storage import get_store
from platform_storage.base import EntityRef

# Re-use message synthesis from the IMAP server when available, else inline.
from datetime import datetime
import email.utils


POP3_USER = os.environ.get("POP3_USER", "admin")
POP3_PASS = os.environ.get("POP3_PASS", "admin")
POP3_PORT = int(os.environ.get("POP3_PORT", "1110"))
HOSTNAME  = os.environ.get("POP3_HOST", "platform.local")


def synth(ref: EntityRef, body: bytes, mime: str) -> bytes:
    ts = ref.updated_at or datetime.utcnow()
    hdr = [
        f"From: platform <noreply@{HOSTNAME}>",
        f"To: {POP3_USER}@{HOSTNAME}",
        f"Subject: {ref.external_id}",
        f"Date: {email.utils.format_datetime(ts)}",
        f"Message-ID: <{ref.external_id}@{HOSTNAME}>",
        f"X-Entity-Type: {ref.entity_type}",
        f"Content-Type: {mime}; charset=utf-8",
        "MIME-Version: 1.0",
        "",
    ]
    return ("\r\n".join(hdr)).encode("utf-8") + body


class Session:
    def __init__(self, reader, writer, store):
        self.r, self.w, self.store = reader, writer, store
        self.user = None
        self.authed = False
        self.msgs: List[EntityRef] = []
        self.deleted = set()

    async def send(self, line: str):
        self.w.write((line + "\r\n").encode("utf-8"))
        await self.w.drain()

    def _load(self):
        out = []
        for etype, _mime, _ext in self.store.list_types():
            out.extend(self.store.list_entities(etype))
        self.msgs = out

    async def run(self):
        await self.send("+OK Platform POP3 ready")
        while True:
            line = await self.r.readline()
            if not line:
                return
            cmd = line.decode("utf-8", errors="replace").strip()
            if not cmd:
                continue
            upper = cmd.upper()
            verb, _, arg = cmd.partition(" ")
            verb = verb.upper()

            if verb == "CAPA":
                await self.send("+OK")
                for c in ("USER", "UIDL", "TOP", "RESP-CODES"):
                    await self.send(c)
                await self.send(".")
            elif verb == "USER":
                self.user = arg.strip()
                await self.send("+OK user accepted")
            elif verb == "PASS":
                if self.user == POP3_USER and arg.strip() == POP3_PASS:
                    self.authed = True
                    self._load()
                    await self.send(f"+OK {len(self.msgs)} messages")
                else:
                    await self.send("-ERR auth failed")
            elif not self.authed:
                await self.send("-ERR not authenticated")
            elif verb == "STAT":
                total = sum(self._size(i) for i in range(len(self.msgs)) if i not in self.deleted)
                count = sum(1 for i in range(len(self.msgs)) if i not in self.deleted)
                await self.send(f"+OK {count} {total}")
            elif verb == "LIST":
                await self.send(f"+OK {len(self.msgs)} messages")
                for i, _ref in enumerate(self.msgs):
                    if i in self.deleted:
                        continue
                    await self.send(f"{i+1} {self._size(i)}")
                await self.send(".")
            elif verb == "UIDL":
                await self.send("+OK")
                for i, ref in enumerate(self.msgs):
                    if i in self.deleted:
                        continue
                    await self.send(f"{i+1} {ref.external_id}")
                await self.send(".")
            elif verb == "RETR":
                idx = int(arg) - 1
                if 0 <= idx < len(self.msgs) and idx not in self.deleted:
                    blob = self._blob(idx)
                    await self.send(f"+OK {len(blob)} octets")
                    self.w.write(blob)
                    if not blob.endswith(b"\r\n"):
                        self.w.write(b"\r\n")
                    self.w.write(b".\r\n")
                    await self.w.drain()
                else:
                    await self.send("-ERR no such message")
            elif verb == "DELE":
                idx = int(arg) - 1
                if 0 <= idx < len(self.msgs):
                    self.deleted.add(idx)
                    await self.send("+OK marked for deletion")
                else:
                    await self.send("-ERR no such message")
            elif verb == "RSET":
                self.deleted.clear()
                await self.send("+OK")
            elif verb == "NOOP":
                await self.send("+OK")
            elif verb == "QUIT":
                # Apply deletes now
                for idx in self.deleted:
                    self.store.delete(self.msgs[idx].external_id)
                await self.send("+OK bye")
                self.w.close()
                return
            else:
                await self.send(f"-ERR unknown command: {verb}")

    def _blob(self, idx: int) -> bytes:
        ref = self.msgs[idx]
        got = self.store.read(ref.external_id)
        if not got:
            return b""
        body, mime, _ = got
        return synth(ref, body, mime)

    def _size(self, idx: int) -> int:
        return len(self._blob(idx))


async def handle(reader, writer):
    store = get_store()
    try:
        await Session(reader, writer, store).run()
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def main():
    for _ in range(30):
        try:
            get_store().list_types()
            break
        except Exception:
            print("[vfs-pop3] waiting for DB…")
            time.sleep(2)

    server = await asyncio.start_server(handle, "0.0.0.0", POP3_PORT)
    print(f"[vfs-pop3] POP3 listening on :{POP3_PORT}  (user: {POP3_USER})")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
