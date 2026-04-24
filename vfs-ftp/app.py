"""vfs-ftp — FTP frontend over platform content_* tables.

Same logical layout as vfs-webdav:
    /articles/*.md
    /devices/*.json
    /pages/*.html
    …

Implemented as a minimal in-memory filesystem adapter on top of pyftpdlib.
Uses `platform_storage.get_store()` so behaviour matches every other gateway.
"""
from __future__ import annotations

import io
import os
import time
from stat import S_IFDIR, S_IFREG

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
from pyftpdlib.filesystems import AbstractedFS

from platform_storage import get_store
from platform_storage.base import EXT_TO_MIME, MIME_IO


FTP_USER = os.environ.get("FTP_USER", "admin")
FTP_PASS = os.environ.get("FTP_PASS", "admin")
FTP_PORT = int(os.environ.get("FTP_PORT", "2121"))
FTP_PUBLIC_HOST = os.environ.get("FTP_PUBLIC_HOST")
FTP_PASSIVE_START = int(os.environ.get("FTP_PASSIVE_START", "30000"))
FTP_PASSIVE_END = int(os.environ.get("FTP_PASSIVE_END", "30100"))


class PlatformFS(AbstractedFS):
    """Maps FTP paths to EntityStore operations."""

    def __init__(self, root, cmd_channel):
        super().__init__(root, cmd_channel)
        self.store = get_store()
        self._layout = {etype: (mime, ext) for etype, mime, ext in self.store.list_types()}

    # --- path helpers ---------------------------------------------------------
    @staticmethod
    def _split(ftppath: str):
        parts = [p for p in ftppath.strip("/").split("/") if p]
        return parts

    def _folder(self, name):
        return name in self._layout

    def _lookup_file(self, parts):
        if len(parts) != 2:
            return None
        folder, fname = parts
        if folder not in self._layout:
            return None
        mime, ext = self._layout[folder]
        external_id = fname[:-len(ext)] if ext and fname.endswith(ext) else fname
        return folder, external_id, mime, ext

    # --- required overrides ---------------------------------------------------
    def validpath(self, path):
        return True

    def isdir(self, path):
        parts = self._split(path)
        if len(parts) == 0:
            return True
        if len(parts) == 1 and self._folder(parts[0]):
            return True
        return False

    def isfile(self, path):
        parts = self._split(path)
        return self._lookup_file(parts) is not None

    def chdir(self, path):
        # Accept any directory we can see
        if not self.isdir(path):
            raise OSError(2, "No such directory", path)
        self._cwd = self.fs2ftp(path)

    def listdir(self, path):
        parts = self._split(path)
        if len(parts) == 0:
            return sorted(self._layout.keys())
        if len(parts) == 1 and self._folder(parts[0]):
            _mime, ext = self._layout[parts[0]]
            return [ref.external_id + ext for ref in self.store.list_entities(parts[0])]
        return []

    def getsize(self, path):
        parts = self._split(path)
        info = self._lookup_file(parts)
        if not info:
            return 0
        _, eid, _mime, _ext = info
        r = self.store.read(eid)
        return len(r[0]) if r else 0

    def getmtime(self, path):
        parts = self._split(path)
        info = self._lookup_file(parts)
        if info:
            r = self.store.read(info[1])
            if r and r[2]:
                return r[2].timestamp()
        return time.time()

    def lstat(self, path):
        return self.stat(path)

    def stat(self, path):
        parts = self._split(path)
        now = time.time()
        if len(parts) == 0 or (len(parts) == 1 and self._folder(parts[0])):
            return os.stat_result((S_IFDIR | 0o755, 0, 0, 1, 0, 0, 0, now, now, now))
        info = self._lookup_file(parts)
        if info:
            size = self.getsize(path)
            mtime = self.getmtime(path)
            return os.stat_result((S_IFREG | 0o644, 0, 0, 1, 0, 0, size, mtime, mtime, mtime))
        raise OSError(2, "No such file", path)

    # --- I/O -----------------------------------------------------------------
    def open(self, filename, mode):  # noqa: A003
        parts = self._split(filename)
        info = self._lookup_file(parts)
        if not info:
            # creation: derive mime from extension inside a known folder
            if len(parts) == 2 and self._folder(parts[0]):
                folder, fname = parts
                ext = os.path.splitext(fname)[1]
                mime = EXT_TO_MIME.get(ext)
                if not mime:
                    raise OSError(13, "Unknown extension", filename)
                external_id = fname[:-len(ext)] if ext else fname
                return _WriteHandle(self.store, folder, external_id, mime)
            raise OSError(2, "No such file", filename)
        folder, eid, mime, _ext = info
        if "r" in mode:
            data = self.store.read(eid)
            return _ReadHandle(data[0] if data else b"")
        return _WriteHandle(self.store, folder, eid, mime)

    def remove(self, path):
        parts = self._split(path)
        info = self._lookup_file(parts)
        if info:
            self.store.delete(info[1])

    def mkdir(self, path):
        raise OSError(13, "Directory layout is data-driven; edit schema_paths instead", path)

    def rmdir(self, path):
        raise OSError(13, "Directory layout is data-driven", path)


class _ReadHandle(io.BytesIO):
    name = "<platform>"

    def __init__(self, data: bytes):
        super().__init__(data)

    closed_already = False


class _WriteHandle(io.BytesIO):
    name = "<platform>"

    def __init__(self, store, folder, external_id, mime):
        super().__init__()
        self._store = store
        self._folder = folder
        self._external_id = external_id
        self._mime = mime

    def close(self):
        body = self.getvalue()
        if body:
            self._store.write(self._external_id, self._folder, self._mime, body, source="ftp")
        super().close()


def main():
    auth = DummyAuthorizer()
    auth.add_user(FTP_USER, FTP_PASS, "/", perm="elradfmw")

    handler = FTPHandler
    handler.authorizer = auth
    handler.abstracted_fs = PlatformFS
    handler.banner = "Platform OS FTP gateway"
    handler.passive_ports = range(FTP_PASSIVE_START, FTP_PASSIVE_END + 1)
    if FTP_PUBLIC_HOST:
        handler.masquerade_address = FTP_PUBLIC_HOST

    # Wait for DB so the first list_types() succeeds
    for _ in range(30):
        try:
            get_store().list_types()
            break
        except Exception:
            print("[vfs-ftp] waiting for DB…")
            time.sleep(2)

    server = FTPServer(("0.0.0.0", FTP_PORT), handler)
    print(f"[vfs-ftp] FTP listening on :{FTP_PORT}  (user: {FTP_USER})")
    server.serve_forever()


if __name__ == "__main__":
    main()
