"""
vfs-fuse  —  FUSE driver over the platform's content_* tables.

This mounts Postgres-backed entities as a real filesystem at MOUNT_POINT.
Inside the container you get:
    /mnt/vfs/articles/hello-platform.md
    /mnt/vfs/devices/device_001.json
    /mnt/vfs/images/pixel.png
    …

It speaks the exact same contract as vfs-webdav: layout comes from
`schema_paths`, payload comes from the `content_*` table that matches
`mime_types`. Writing a file upserts into the right table.

Run mode:
    docker compose up vfs-fuse
The container mounts at /mnt/vfs internally. Bind-mount that into your
host with `--mount type=bind` or export it over NFS/SSHFS for external
clients. (FUSE inside Docker needs --cap-add SYS_ADMIN + --device /dev/fuse.)
"""
import errno
import hashlib
import json
import os
import stat
import time
from threading import RLock

import psycopg
from fuse import FUSE, FuseOSError, Operations, LoggingMixIn

DATABASE_URL  = os.environ["DATABASE_URL"]
MOUNT_POINT   = os.environ.get("MOUNT_POINT", "/mnt/vfs")

MIME_IO = {
    "application/json":  (".json", "content_json",     "data",     "json"),
    "application/yaml":  (".yaml", "content_yaml",     "raw_text", "text"),
    "application/xml":   (".xml",  "content_xml",      "raw_text", "text"),
    "text/html":         (".html", "content_html",     "body",     "text"),
    "text/markdown":     (".md",   "content_markdown", "body",     "text"),
    "image/png":         (".png",  "content_binary",   "bytes",    "bytes"),
    "image/jpeg":        (".jpg",  "content_binary",   "bytes",    "bytes"),
    "application/pdf":   (".pdf",  "content_binary",   "bytes",    "bytes"),
}


def db():
    return psycopg.connect(DATABASE_URL)


class PlatformFS(LoggingMixIn, Operations):
    """
    Virtual filesystem where:
      /                                  root
      /{folder}/                          from schemas.fs_path_template
      /{folder}/{external_id}.{ext}       one row in a content_* table
    """

    def __init__(self):
        self.lock   = RLock()
        self._fh    = 0
        self._open  = {}          # fh -> {buffer:bytes, dirty:bool, path:str}
        self._layout = None        # lazy

    # ------------------------------------------------------------------
    # Directory layout cache — refreshes when any new schema is added.
    # ------------------------------------------------------------------
    def layout(self):
        with self.lock:
            if self._layout is None or time.time() - self._layout[0] > 30:
                out = {}
                with db() as c, c.cursor() as cur:
                    cur.execute(
                        """SELECT s.id, s.name, s.mime_type, sp.path_template
                             FROM schemas s
                             JOIN schema_paths sp ON sp.schema_id = s.id
                            WHERE sp.path_template IS NOT NULL"""
                    )
                    for schema_id, entity_type, mime, tpl in cur.fetchall():
                        folder = tpl.split("/", 1)[0]
                        ext    = "." + tpl.rsplit(".", 1)[-1] if "." in tpl else ""
                        out[folder] = (entity_type, schema_id, mime, ext)
                self._layout = (time.time(), out)
            return self._layout[1]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _split(self, path):
        """/articles/hello.md -> ('articles', 'hello', '.md')"""
        parts = [p for p in path.split("/") if p]
        if len(parts) == 0:
            return ("", "", "")
        if len(parts) == 1:
            return (parts[0], "", "")
        base, ext = os.path.splitext(parts[1])
        return (parts[0], base, ext)

    def _load_payload(self, folder, external_id, mime):
        _, table, col, kind = MIME_IO[mime]
        with db() as c, c.cursor() as cur:
            cur.execute(
                f"""
                SELECT ct.{col}, ct.updated_at
                  FROM entities e
                  JOIN {table} ct ON ct.entity_id = e.id
                 WHERE e.external_id = %s
                 ORDER BY ct.updated_at DESC LIMIT 1
                """,
                (external_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        raw, updated = row
        if kind == "json":
            body = json.dumps(raw, indent=2).encode("utf-8")
        elif kind == "bytes":
            body = bytes(raw) if raw else b""
        else:
            body = (raw or "").encode("utf-8")
        return body, updated

    def _list_dir(self, folder):
        layout = self.layout()
        if folder not in layout:
            return None
        entity_type, _schema_id, _mime, ext = layout[folder]
        with db() as c, c.cursor() as cur:
            cur.execute(
                "SELECT external_id FROM entities WHERE entity_type=%s ORDER BY external_id",
                (entity_type,),
            )
            return [r[0] + ext for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # FUSE operations
    # ------------------------------------------------------------------
    def getattr(self, path, fh=None):
        now = time.time()
        base = dict(st_atime=now, st_mtime=now, st_ctime=now, st_uid=os.getuid(), st_gid=os.getgid())
        if path == "/":
            return {**base, "st_mode": stat.S_IFDIR | 0o755, "st_nlink": 2}

        folder, ext_id, ext = self._split(path)
        layout = self.layout()

        # Top-level folder
        if folder in layout and not ext_id:
            return {**base, "st_mode": stat.S_IFDIR | 0o755, "st_nlink": 2}

        # Regular file
        if folder in layout and ext_id:
            _, _, mime, want_ext = layout[folder]
            if ext and ext != want_ext:
                raise FuseOSError(errno.ENOENT)
            data = self._load_payload(folder, ext_id, mime)
            if not data:
                raise FuseOSError(errno.ENOENT)
            body, updated = data
            mtime = updated.timestamp() if updated else now
            return {**base, "st_mode": stat.S_IFREG | 0o644,
                    "st_nlink": 1, "st_size": len(body),
                    "st_atime": mtime, "st_mtime": mtime, "st_ctime": mtime}

        raise FuseOSError(errno.ENOENT)

    def readdir(self, path, fh):
        if path == "/":
            return [".", ".."] + list(self.layout().keys())
        folder = path.strip("/").split("/")[0]
        entries = self._list_dir(folder)
        if entries is None:
            raise FuseOSError(errno.ENOENT)
        return [".", ".."] + entries

    def open(self, path, flags):
        with self.lock:
            self._fh += 1
            folder, ext_id, _ext = self._split(path)
            layout = self.layout()
            _, _, mime, _ = layout[folder]
            data = self._load_payload(folder, ext_id, mime) or (b"", None)
            self._open[self._fh] = {"path": path, "buffer": bytearray(data[0]), "dirty": False}
            return self._fh

    def create(self, path, mode, fi=None):
        with self.lock:
            self._fh += 1
            self._open[self._fh] = {"path": path, "buffer": bytearray(), "dirty": True}
            return self._fh

    def read(self, path, size, offset, fh):
        state = self._open.get(fh)
        if not state:
            raise FuseOSError(errno.EBADF)
        return bytes(state["buffer"][offset:offset + size])

    def write(self, path, data, offset, fh):
        state = self._open.get(fh)
        if not state:
            raise FuseOSError(errno.EBADF)
        buf = state["buffer"]
        # Extend if needed
        if offset + len(data) > len(buf):
            buf.extend(b"\x00" * (offset + len(data) - len(buf)))
        buf[offset:offset + len(data)] = data
        state["dirty"] = True
        return len(data)

    def truncate(self, path, length, fh=None):
        if fh and fh in self._open:
            buf = self._open[fh]["buffer"]
            if length < len(buf):
                del buf[length:]
            else:
                buf.extend(b"\x00" * (length - len(buf)))
            self._open[fh]["dirty"] = True

    def flush(self, path, fh):
        state = self._open.get(fh)
        if not state or not state["dirty"]:
            return 0
        self._persist(path, bytes(state["buffer"]))
        state["dirty"] = False
        return 0

    def release(self, path, fh):
        state = self._open.pop(fh, None)
        if state and state["dirty"]:
            self._persist(path, bytes(state["buffer"]))
        return 0

    def unlink(self, path):
        folder, ext_id, _ = self._split(path)
        layout = self.layout()
        if folder not in layout:
            raise FuseOSError(errno.ENOENT)
        _entity_type, _sid, mime, _ = layout[folder]
        _, table, _col, _kind = MIME_IO[mime]
        with db() as c, c.cursor() as cur:
            cur.execute(
                f"""DELETE FROM {table} WHERE entity_id IN
                      (SELECT id FROM entities WHERE external_id=%s)""",
                (ext_id,),
            )
            c.commit()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _persist(self, path, body: bytes):
        folder, ext_id, _ = self._split(path)
        layout = self.layout()
        if folder not in layout:
            raise FuseOSError(errno.ENOENT)
        entity_type, _schema_id, mime, _ext = layout[folder]
        _, table, _col, kind = MIME_IO[mime]

        checksum = hashlib.sha256(body).hexdigest()

        with db() as c, c.cursor() as cur:
            cur.execute(
                """
                INSERT INTO entities (external_id, entity_type, schema_id, primary_mime)
                VALUES (%s, %s,
                  (SELECT id FROM schemas WHERE mime_type=%s AND name=%s LIMIT 1),
                  %s)
                ON CONFLICT (external_id) DO UPDATE
                  SET entity_type=EXCLUDED.entity_type
                RETURNING id
                """,
                (ext_id, entity_type, mime, entity_type, mime),
            )
            entity_id = cur.fetchone()[0]

            if kind == "json":
                try:
                    data = json.loads(body.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    raise FuseOSError(errno.EINVAL)
                cur.execute(
                    f"""INSERT INTO {table} (entity_id, data, checksum, source)
                        VALUES (%s, %s::jsonb, %s, 'filesystem')
                        ON CONFLICT (entity_id) DO UPDATE
                          SET data=EXCLUDED.data, checksum=EXCLUDED.checksum,
                              source='filesystem'""",
                    (entity_id, json.dumps(data), checksum),
                )
            elif kind == "bytes":
                cur.execute(
                    f"""INSERT INTO {table}
                          (entity_id, mime, storage_mode, bytes, size_bytes, checksum, source)
                        VALUES (%s, %s, 'db', %s, %s, %s, 'filesystem')""",
                    (entity_id, mime, body, len(body), checksum),
                )
            else:
                text = body.decode("utf-8", errors="replace")
                if table == "content_yaml":
                    import yaml as y
                    parsed = y.safe_load(text) or {}
                    cur.execute(
                        f"""INSERT INTO {table}
                              (entity_id, raw_text, parsed, checksum, source)
                            VALUES (%s, %s, %s::jsonb, %s, 'filesystem')
                            ON CONFLICT (entity_id) DO UPDATE
                              SET raw_text=EXCLUDED.raw_text, parsed=EXCLUDED.parsed,
                                  checksum=EXCLUDED.checksum, source='filesystem'""",
                        (entity_id, text, json.dumps(parsed), checksum),
                    )
                elif table == "content_xml":
                    cur.execute(
                        f"""INSERT INTO {table}
                              (entity_id, raw_text, parsed, checksum, source)
                            VALUES (%s, %s, '{{}}'::jsonb, %s, 'filesystem')
                            ON CONFLICT (entity_id) DO UPDATE
                              SET raw_text=EXCLUDED.raw_text, checksum=EXCLUDED.checksum,
                                  source='filesystem'""",
                        (entity_id, text, checksum),
                    )
                elif table == "content_html":
                    cur.execute(
                        f"""INSERT INTO {table}
                              (entity_id, body, is_template, checksum, source)
                            VALUES (%s, %s, %s, %s, 'filesystem')""",
                        (entity_id, text, ("{{" in text or "{%" in text), checksum),
                    )
                else:  # markdown
                    cur.execute(
                        f"""INSERT INTO {table}
                              (entity_id, body, checksum, source)
                            VALUES (%s, %s, %s, 'filesystem')
                            ON CONFLICT (entity_id) DO UPDATE
                              SET body=EXCLUDED.body, checksum=EXCLUDED.checksum,
                                  source='filesystem'""",
                        (entity_id, text, checksum),
                    )

            cur.execute(
                """INSERT INTO audit_log (content_table, entity_id, source, action)
                   VALUES (%s, %s, 'filesystem', 'fuse-write')""",
                (table, entity_id),
            )
            c.commit()


def main():
    # Wait for DB init
    for _ in range(30):
        try:
            with db() as c, c.cursor() as cur:
                cur.execute("SELECT 1 FROM schemas LIMIT 1")
                break
        except Exception:
            print("[vfs-fuse] waiting for DB…")
            time.sleep(2)

    os.makedirs(MOUNT_POINT, exist_ok=True)
    print(f"[vfs-fuse] mounting at {MOUNT_POINT}")
    FUSE(PlatformFS(), MOUNT_POINT, nothreads=False, foreground=True,
         allow_other=True, default_permissions=True)


if __name__ == "__main__":
    main()
