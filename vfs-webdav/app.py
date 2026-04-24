"""
vfs-webdav  —  WebDAV frontend over the platform's content_* tables.

What you see when you mount this:
    /                          root
    /articles/
        hello-platform.md      <- content_markdown.body
        platform-os-architecture.md
    /devices/
        device_001.json        <- content_json.data
        device_002.json
    /scenarios/
        nightly-calibration.yaml   <- content_yaml.raw_text
    /protocols/
        cal-report-2026-q2.xml     <- content_xml.raw_text
    /pages/
        landing.html               <- content_html.body
    /images/
        pixel.png                  <- content_binary.bytes

All of that is synthesised at request time from Postgres. Nothing lives on
disk. Edit a .md file in your editor and we write back to content_markdown.

Reading `schema_paths` gives us the directory layout — it's data, not code.
Add a new schema with a new path_template and a new folder appears.
"""
import os
import hashlib
import json
from io import BytesIO

import psycopg
from wsgidav.wsgidav_app import WsgiDAVApp
from wsgidav.dav_provider import DAVProvider, DAVCollection, DAVNonCollection
from wsgidav.util import join_uri
from cheroot import wsgi

DATABASE_URL = os.environ["DATABASE_URL"]
WEBDAV_USER  = os.environ.get("WEBDAV_USER", "admin")
WEBDAV_PASS  = os.environ.get("WEBDAV_PASS", "admin")

# MIME -> (file extension, content table, column with raw bytes/text)
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
# Reverse: extension -> mime (first match wins on ties)
EXT_TO_MIME = {}
for mime, (ext, *_rest) in MIME_IO.items():
    EXT_TO_MIME.setdefault(ext, mime)


def db():
    return psycopg.connect(DATABASE_URL)


# ---------------------------------------------------------------------------
# Path discovery  — turn `schemas.fs_path_template` ('articles/{external_id}.md')
# into a directory and (entity_type, extension).
# ---------------------------------------------------------------------------
def load_directory_layout():
    """Return {folder_name: (entity_type, schema_id, mime, ext)}."""
    out = {}
    with db() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT s.id, s.name, s.mime_type, sp.path_template
              FROM schemas s
              JOIN schema_paths sp ON sp.schema_id = s.id
             WHERE sp.path_template IS NOT NULL
            """
        )
        for schema_id, entity_type, mime, tpl in cur.fetchall():
            # 'articles/{external_id}.md'  ->  folder='articles', ext='.md'
            folder = tpl.split("/", 1)[0]
            ext    = "." + tpl.rsplit(".", 1)[-1] if "." in tpl else ""
            out[folder] = (entity_type, schema_id, mime, ext)
    return out


# ---------------------------------------------------------------------------
# WebDAV resources
# ---------------------------------------------------------------------------
class EntityFile(DAVNonCollection):
    """One row in a content_* table, exposed as a single file."""

    def __init__(self, path, environ, entity_type, external_id, mime):
        super().__init__(path, environ)
        self.entity_type = entity_type
        self.external_id = external_id
        self.mime        = mime
        self._cached     = None

    # --- lazy load from DB on demand ---
    def _load(self):
        if self._cached is not None:
            return self._cached
        _, table, col, kind = MIME_IO[self.mime]
        with db() as c, c.cursor() as cur:
            cur.execute(
                f"""
                SELECT ct.{col}, ct.updated_at, ct.version
                  FROM entities e
                  JOIN {table} ct ON ct.entity_id = e.id
                 WHERE e.external_id = %s
                 ORDER BY ct.updated_at DESC LIMIT 1
                """,
                (self.external_id,),
            )
            row = cur.fetchone()
        if not row:
            self._cached = (b"", None, 0)
            return self._cached
        raw, updated, version = row
        if kind == "json":
            body = json.dumps(raw, indent=2).encode("utf-8")
        elif kind == "bytes":
            body = bytes(raw) if raw else b""
        else:
            body = (raw or "").encode("utf-8")
        self._cached = (body, updated, version)
        return self._cached

    def get_content_length(self):
        return len(self._load()[0])

    def get_content_type(self):
        return self.mime

    def get_display_name(self):
        return self.external_id + MIME_IO[self.mime][0]

    def get_etag(self):
        body = self._load()[0]
        return '"' + hashlib.md5(body).hexdigest() + '"'

    def support_etag(self):
        return True

    def get_last_modified(self):
        _, updated, _ = self._load()
        return updated.timestamp() if updated else 0

    def support_ranges(self):
        return False

    def get_content(self):
        return BytesIO(self._load()[0])

    # --- write path: PUT replaces content_* row ---
    def begin_write(self, content_type=None):
        self._upload_buffer = BytesIO()
        return self._upload_buffer

    def end_write(self, with_errors):
        if with_errors:
            return
        body = self._upload_buffer.getvalue()
        self._persist(body)
        self._cached = None   # force re-read on next access

    def _persist(self, body: bytes):
        _, table, col, kind = MIME_IO[self.mime]
        checksum = hashlib.sha256(body).hexdigest()

        with db() as c, c.cursor() as cur:
            # Ensure entity exists; upsert by external_id
            cur.execute(
                """
                INSERT INTO entities (external_id, entity_type, schema_id, primary_mime)
                VALUES (%s, %s,
                  (SELECT id FROM schemas WHERE mime_type=%s AND name=%s LIMIT 1),
                  %s)
                ON CONFLICT (external_id) DO UPDATE
                  SET entity_type = EXCLUDED.entity_type
                RETURNING id
                """,
                (self.external_id, self.entity_type, self.mime, self.entity_type, self.mime),
            )
            entity_id = cur.fetchone()[0]

            # Write into the right content_* table
            if kind == "json":
                data = json.loads(body.decode("utf-8") or "{}")
                cur.execute(
                    f"""
                    INSERT INTO {table} (entity_id, data, checksum, source)
                    VALUES (%s, %s::jsonb, %s, 'filesystem')
                    ON CONFLICT (entity_id) DO UPDATE
                      SET data=EXCLUDED.data, checksum=EXCLUDED.checksum, source='filesystem'
                    """,
                    (entity_id, json.dumps(data), checksum),
                )
            elif kind == "bytes":
                cur.execute(
                    f"""
                    INSERT INTO {table} (entity_id, mime, storage_mode, bytes, size_bytes, checksum, source)
                    VALUES (%s, %s, 'db', %s, %s, %s, 'filesystem')
                    """,
                    (entity_id, self.mime, body, len(body), checksum),
                )
            else:  # text
                text = body.decode("utf-8", errors="replace")
                if table == "content_yaml":
                    import yaml as y
                    parsed = y.safe_load(text) or {}
                    cur.execute(
                        f"""
                        INSERT INTO {table} (entity_id, raw_text, parsed, checksum, source)
                        VALUES (%s, %s, %s::jsonb, %s, 'filesystem')
                        ON CONFLICT (entity_id) DO UPDATE
                          SET raw_text=EXCLUDED.raw_text, parsed=EXCLUDED.parsed,
                              checksum=EXCLUDED.checksum, source='filesystem'
                        """,
                        (entity_id, text, json.dumps(parsed), checksum),
                    )
                elif table == "content_xml":
                    cur.execute(
                        f"""
                        INSERT INTO {table} (entity_id, raw_text, parsed, checksum, source)
                        VALUES (%s, %s, '{{}}'::jsonb, %s, 'filesystem')
                        ON CONFLICT (entity_id) DO UPDATE
                          SET raw_text=EXCLUDED.raw_text, checksum=EXCLUDED.checksum, source='filesystem'
                        """,
                        (entity_id, text, checksum),
                    )
                elif table == "content_html":
                    cur.execute(
                        f"""
                        INSERT INTO {table} (entity_id, body, is_template, checksum, source)
                        VALUES (%s, %s, %s, %s, 'filesystem')
                        """,
                        (entity_id, text, ("{{" in text or "{%" in text), checksum),
                    )
                else:  # content_markdown
                    cur.execute(
                        f"""
                        INSERT INTO {table} (entity_id, body, checksum, source)
                        VALUES (%s, %s, %s, 'filesystem')
                        ON CONFLICT (entity_id) DO UPDATE
                          SET body=EXCLUDED.body, checksum=EXCLUDED.checksum, source='filesystem'
                        """,
                        (entity_id, text, checksum),
                    )

            cur.execute(
                """
                INSERT INTO audit_log (content_table, entity_id, source, action)
                VALUES (%s, %s, 'filesystem', 'webdav-put')
                """,
                (table, entity_id),
            )
            c.commit()

    def delete(self):
        _, table, _col, _kind = MIME_IO[self.mime]
        with db() as c, c.cursor() as cur:
            cur.execute(
                f"""DELETE FROM {table} WHERE entity_id IN
                      (SELECT id FROM entities WHERE external_id=%s)""",
                (self.external_id,),
            )
            c.commit()


class EntityFolder(DAVCollection):
    """A directory that lists all entities of one entity_type as files."""

    def __init__(self, path, environ, entity_type, schema_id, mime, ext):
        super().__init__(path, environ)
        self.entity_type = entity_type
        self.schema_id   = schema_id
        self.mime        = mime
        self.ext         = ext

    def get_member_names(self):
        with db() as c, c.cursor() as cur:
            cur.execute(
                "SELECT external_id FROM entities WHERE entity_type=%s ORDER BY external_id",
                (self.entity_type,),
            )
            return [r[0] + self.ext for r in cur.fetchall()]

    def get_member(self, name):
        ext = os.path.splitext(name)[1]
        external_id = name[: -len(ext)] if ext else name
        return EntityFile(
            join_uri(self.path, name), self.environ,
            self.entity_type, external_id, self.mime,
        )

    def support_recursive_delete(self):
        return False


class RootCollection(DAVCollection):
    """Top-level collection: one subfolder per schema_paths row."""

    def __init__(self, path, environ):
        super().__init__(path, environ)
        self.layout = load_directory_layout()

    def get_member_names(self):
        return list(self.layout.keys())

    def get_member(self, name):
        if name not in self.layout:
            return None
        entity_type, schema_id, mime, ext = self.layout[name]
        return EntityFolder(
            join_uri(self.path, name), self.environ,
            entity_type, schema_id, mime, ext,
        )


class PlatformProvider(DAVProvider):
    """wsgidav hook — all paths resolve through here."""

    def get_resource_inst(self, path, environ):
        self._count_get_resource_inst += 1
        parts = [p for p in path.split("/") if p]

        if len(parts) == 0:
            return RootCollection("/", environ)

        root = RootCollection("/", environ)
        folder = root.get_member(parts[0])
        if folder is None or len(parts) == 1:
            return folder

        return folder.get_member(parts[1])


# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------
def build_app():
    config = {
        "host": "0.0.0.0",
        "port": 8090,
        "provider_mapping": {"/": PlatformProvider()},
        "http_authenticator": {
            "domain_controller": None,   # simple dict-based auth below
            "accept_basic": True,
            "accept_digest": False,
            "default_to_digest": False,
        },
        "simple_dc": {
            "user_mapping": {
                "*": {
                    WEBDAV_USER: {"password": WEBDAV_PASS},
                },
            },
        },
        "verbose": 2,
        "logging": {"enable_loggers": []},
        "property_manager": True,
        "lock_storage": True,
    }
    return WsgiDAVApp(config)


if __name__ == "__main__":
    # Wait for Postgres init to finish
    import time
    for _ in range(30):
        try:
            with db() as c, c.cursor() as cur:
                cur.execute("SELECT 1 FROM schemas LIMIT 1")
                break
        except Exception:
            print("[vfs-webdav] waiting for DB…")
            time.sleep(2)

    app = build_app()
    server = wsgi.Server(("0.0.0.0", 8090), app)
    print("[vfs-webdav] WebDAV serving on :8090  (user: %s)" % WEBDAV_USER)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
