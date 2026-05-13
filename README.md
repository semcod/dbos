# Platform OS

A schema-driven runtime for data and applications. Not a backend, not an app.
PostgreSQL holds meaning, MIME-typed content tables hold payloads, and a set
of small services consume them through a published contract.

## What this actually is

Everything — devices, articles, scenarios, images, HTML pages, protocols —
lives as an `entities` row plus exactly one row in a `content_*` table
chosen by MIME. There's one content table per MIME type, which means any
service that cares about one MIME doesn't have to know about the others,
and you can `pg_dump -t content_markdown` to take your articles to a
different project without dragging along the rest of the database.

On top of the data there are:

- **sync-engine** — watches `./data/`, parses files by extension, routes each to the right `content_*` table
- **api-gateway** — generic `/api/entities/:id` that joins `entities` with the correct content table at runtime; plus CRUD for `storage_backends`, `protocol_gateways`, `inbound_sources`
- **command-bus** — persists every command, routes to a worker by `schemas.target_runtime`
- **worker-python** / **worker-php** — execute business logic
- **gen-jinja** (Python), **gen-twig** (PHP), **gen-handlebars** (Node) — three website generators, each reading the same tables, each declaring what it can render in `schemas.renderers[]`
- **ui-runtime** — schema-driven frontend
- **nginx-cdn** — reverse proxy with preview caching
- **vfs-webdav** — WebDAV skin over the same tables (mount from anywhere)
- **vfs-fuse** — real Linux FUSE mount
- **vfs-ftp** — FTP server (`:2121`) with passive mode support
- **vfs-imap** — IMAP4rev1 server (`:1143`) exposing entities as mailboxes/messages
- **vfs-pop3** — POP3 server (`:1110`) with UIDL/RETR/DELE
- **vfs-smtp** — SMTP gateway (`:2525`) ingesting mail as `mail/*` entities
- **storage-mirror** — tails `audit_log` and replays writes into SQLite / MySQL mirrors
- **sync-outbound** — reads `service_mappings` and pushes matching entities to filesystem targets (e.g. `./email/*.eml`)
- **connectors** — inbound pollers (filesystem, IMAP-pull, FTP-pull, SQL-mirror)

## Layout

```
platform/
├─ docker-compose.yml
├─ Makefile                       stack lifecycle, tests, runnable examples
├─ .env.example
├─ postgres/init/                 7 SQL files run on first boot
│  ├─ 01_core.sql                 extensions, users, ACL, audit_log
│  ├─ 02_registry.sql             schemas, mime_types, schema_paths, filesystem_map
│  ├─ 03_content_tables.sql       entities + content_json/yaml/xml/html/markdown/binary
│  ├─ 04_schemas_seed.sql         JSON Schemas + renderer declarations
│  ├─ 05_demo_data.sql            first rows in every content table
│  ├─ 06_connectors.sql           storage_backends, protocol_gateways, inbound_sources
│  └─ 07_mail_schema.sql          mail schema + schema_paths seed for SMTP/IMAP/POP3
├─ scripts/
│  ├─ demo.sh                     end-to-end walkthrough
│  ├─ export-service.sh           extract one service + its tables for reuse
│  └─ db-upgrade-protocols.sh     apply registry + mail schema to existing Postgres volumes
├─ libs/platform_storage/         shared storage contract + adapters (Pg, SQLite, MySQL)
├─ sync-engine/                   filesystem -> DB, MIME-routed
├─ api-gateway/                   REST + ACL + schema validation + registry CRUD
├─ command-bus/                   routes commands to workers by target_runtime
├─ workers/
│  ├─ python/                     FastAPI; handles create_device, etc.
│  └─ php/                        PHP CLI server; handles render_page
├─ generators/                    website generators (same contract, 3 techs)
│  ├─ gen-jinja/                  Python + FastAPI + Jinja2 + markdown
│  ├─ gen-twig/                   PHP + Twig
│  └─ gen-handlebars/             Node + Express + Handlebars
├─ ui-runtime/                    vanilla JS schema-driven UI
├─ cdn/nginx.conf                 reverse proxy
├─ vfs-webdav/                    WebDAV frontend over content_* tables
├─ vfs-fuse/                      FUSE frontend over content_* tables
├─ vfs-ftp/                       FTP gateway (passive mode, masquerade support)
├─ vfs-imap/                      IMAP4rev1 gateway
├─ vfs-pop3/                      POP3 gateway
├─ vfs-smtp/                      SMTP ingest gateway
├─ storage-mirror/                audit_log tailer -> SQLite/MySQL mirrors
├─ sync-outbound/                   service_mappings -> filesystem export
├─ connectors/                    inbound poller daemons
├─ sdk/                           Python / JS / PHP clients
├─ examples/                      runnable integration scenarios
│  ├─ 01-write-http-read-protocols/
│  ├─ 02-smtp-to-platform/
│  ├─ 03-sqlite-mirror/
│  ├─ 04-connectors-registry/
│  └─ 05-everything/
├─ data/                          watched by sync-engine (nested dirs supported)
│  ├─ articles/*.md
│  ├─ devices/*.json
│  ├─ pages/*.html
│  ├─ pages/page2/*.html         nested directory example
│  ├─ scenarios/*.yaml
│  └─ protocols/*.xml
├─ logs/                          info.txt, warnings.txt, error.txt
└─ mirror-data/                   SQLite mirror default path
```

## Quickstart

```bash
cp .env.example .env
make up-all          # core + protocols + connectors + mirrors
```

What happens on first boot:

1. Postgres runs the 7 init SQL files (schemas, demo data, registry, mail schema)
2. `sync-engine` picks up every file in `./data/` and writes it to the matching content table
3. All three generators wake up and publish `/capabilities` from `schemas.renderers[]`
4. UI at <http://localhost:5173> (login `admin@platform.local` / `demo1234`)
   - File Browser: `#files` — tree, table, manager, grid views
   - Thumbnails: 64x64 PNG generated from file content (colors per MIME type)
   - Icon size control: 16px–64px, row height: compact/normal/spacious
   - Inline HTML preview + schema preview on entity pages
   - JSON syntax highlighting
5. CDN at <http://localhost:8081>, WebDAV at `http://localhost:8090`
6. Protocol gateways: FTP `:2121`, IMAP `:1143`, POP3 `:1110`, SMTP `:2525`
7. Logs in `./logs/` for debugging services

Then from a second terminal:

```bash
make examples        # run all 5 integration scenarios
./scripts/demo.sh    # end-to-end walkthrough
```

If you already have an old Postgres volume, run `make db-upgrade-protocols` before
starting the new services so registry tables and the mail schema exist.

## File Browser UI

The UI at `#files` provides 4 views for browsing entities:

| View      | URL hash                | Description                                    |
| --------- | ----------------------- | -----------------------------------------------|
| Tree      | `#files/tree`           | Hierarchical tree with expandable folders        |
| Table     | `#files/table`          | Columns: path, type, schema, MIME, updated, status |
| Manager   | `#files/manager`        | Two-column file manager with drag-and-drop move + edit/delete |
| Grid      | `#files/grid`           | Grouped by folder, thumbnail + filename cards  |

Controls:
- **Icon Size**: 16px / 24px / 32px / 48px / 64px — adjusts thumbnails everywhere
- **Row Height**: compact / normal / spacious — table and tree spacing

## Nested filesystem paths

Files in subdirectories are supported. `data/pages/page2/welcome.html` is stored with `external_id = pages/page2/welcome` (slash-separated). The UI displays paths as on disk.

```bash
# This entity exists at the nested path
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3000/api/entity?external_id=pages/page2/welcome"
```

## Thumbnails

Every file change triggers 64x64 PNG thumbnail generation via `sharp`:
- **Images**: resized actual image
- **Text/HTML/JSON/YAML/XML**: colored squares (color per MIME) with dot pattern indicating content length

Thumbnails are stored in the `thumbnails` table and served from `GET /api/thumbnail?external_id=...&size=64px`.

## Mount the platform as a filesystem

### WebDAV (easiest — works on Linux/Mac/Windows)

```bash
# Linux
sudo apt install davfs2
sudo mkdir -p /mnt/vfs
sudo mount -t davfs http://localhost:8090 /mnt/vfs
# user: admin  password: admin  (from .env)

ls /mnt/vfs
#   articles/  customers/  devices/  images/  pages/  protocols/  scenarios/

cat /mnt/vfs/articles/hello-platform.md      # streams content_markdown.body
echo "# new" > /mnt/vfs/articles/test.md     # upserts into content_markdown
```

macOS: Finder → *Go* → *Connect to Server* → `http://localhost:8090`
Windows: Explorer → *This PC* → *Map network drive* → `http://localhost:8090`

### FUSE (real Linux mount)

Only on a Linux host with `/dev/fuse`:

```bash
docker compose --profile fuse up -d vfs-fuse
ls ./vfs-mount/                              # shares the same folder with the container
```

Inside the container the mount is at `/mnt/vfs`, bind-mounted to
`./vfs-mount/` on the host so other processes see it too.

## The reusability recipe

Say you want `gen-jinja` in a completely different project next week:

```bash
./scripts/export-service.sh gen-jinja
# -> ./export/gen-jinja/
#       service/                source + Dockerfile
#       bundle.sql              schemas + mime_types + content_markdown + content_html
#       docker-compose.snippet  service block for the new project
```

Drop `bundle.sql` into the new project's DB, paste the compose snippet,
`docker compose up`. On first hit the service queries `mime_types` and
`schemas`, sees what it's registered for, starts handling requests. No code
change.

## Developing

### Watch a file go from disk to DB

```bash
cat > data/articles/my-post.md <<EOF
---
title: My first post
author: me
tags: [hello]
---
# Hi

This will end up in \`content_markdown\` within a second.
EOF

# ~1s later:
curl -s http://localhost:3000/api/entities/my-post \
  -H "Authorization: Bearer $TOKEN" | jq
```

### Render an article three different ways

```bash
# Python + Jinja2
curl -X POST http://localhost:6001/render/my-post

# Node + Handlebars (uses content_json, so pick a device)
curl -X POST http://localhost:6003/render/device_001

# PHP + Twig (uses a template + a data entity)
curl -X POST http://localhost:6002/render/landing \
  -H 'content-type: application/json' \
  -d '{"data_from":"device_001"}'
```

All three write their output to `content_html` rows tagged with
`source = 'generator'`. Fetch the latest via the API:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:3000/api/entities/my-post/html
```

### Add a new MIME type without changing code

```sql
-- tell the platform about a new MIME, e.g. application/toml
INSERT INTO mime_types (mime, category, content_table, storage_mode)
VALUES ('application/toml', 'structured', 'content_toml', 'db');

-- create the table (mirror content_yaml shape)
CREATE TABLE content_toml (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  raw_text text NOT NULL,
  parsed jsonb NOT NULL,
  checksum text NOT NULL,
  version int NOT NULL DEFAULT 1,
  source change_source NOT NULL DEFAULT 'system',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(entity_id)
);
```

That's it from Postgres' side. `sync-engine` needs a one-line addition to its
`EXT_TO_MIME` map to route `.toml` files, but anyone who only reads the
registry (generators, VFS, API) picks up the new routing automatically.

## Architecture

```
           +-------------+   WebDAV   FUSE   FTP   IMAP   POP3
           | UI / Client |     |       |      |      |      |
           +------+------+     |       |      |      |      |
                  |            v       v      v      v      v
                  |    +----------+ +------+ +------+ +------+ +------+
                  |    |vfs-webdav| |fuse  | |ftp   | |imap  | |pop3  |
                  |    +----+-----+ +---+--+ +---+--+ +--+---+ +--+---+
                  |         |          |        |        |        |
           +-------------+  |          |        |        |        |
           |  api-gateway|  |          |        |        |        |
           +------+------+  |          |        |        |        |
                  |         v          v        v        v        v
                  |    +------------------------------------------------+
                  |    |               PostgreSQL (primary)               |
                  v    |  entities + content_* tables + schemas + audit_log |
           +-------------+ |  storage_backends + protocol_gateways      |
           | command-bus | |  inbound_sources                               |
           +------+------+ +-----------------------+------------------------+
                  |                                ^
    +-------------+---+                            |
    v             v   v                    +--------------------+
 worker-       gen-*    +----------------> |  storage-mirror    |
 python/php                               |  SQLite / MySQL    |
                                          +--------------------+
                                       ^
                                       |
                           +---------------------+
                           |     sync-engine     |
                           +----------+----------+
                                      |
                                   ./data/*
```

## Cheat sheet

| What                              | How                                                                 |
| --------------------------------- | ------------------------------------------------------------------- |
| Log in                            | `POST /auth/login  {email, password}` → JWT                         |
| List entities                     | `GET /api/entities?entity_type=device&limit=200`                    |
| Fetch entity + content            | `GET /api/entities/:external_id`  or `GET /api/entity?external_id=` |
| View rendered HTML                | `GET /api/entities/:external_id/html`                               |
| Thumbnail (64x64 PNG)             | `GET /api/thumbnail?external_id=pages/page2/welcome&size=64px`      |
| Update entity (move/edit)         | `PATCH /api/entity?external_id=... {external_id, content}`          |
| Delete entity                     | `DELETE /api/entity?external_id=...`                                |
| File Browser views                | `#files/tree`, `#files/table`, `#files/manager`, `#files/grid`      |
| Inspect routing                   | `GET /mime-types`  and  `GET /schemas`                              |
| Who renders schema X?             | `SELECT renderers FROM schemas WHERE id = 'article_v1';`            |
| Run a command                     | `POST /commands/create_device  {...}`                               |
| Audit                             | `GET /audit` (admin only)                                           |
| Registry CRUD (backends/gateways/sources) | `GET|POST|PATCH|DELETE /api/storage-backends` / `protocol-gateways` / `inbound-sources` |
| Mount as filesystem               | `mount -t davfs http://localhost:8090 /mnt/vfs`                     |
| Export one service                | `./scripts/export-service.sh gen-jinja`                             |
| View logs                         | `cat ./logs/info.txt`  `./logs/warnings.txt`  `./logs/error.txt`    |
| Run all examples                  | `make examples`                                                     |
| Upgrade existing DB               | `make db-upgrade-protocols`                                         |
| Install dev tools                 | `make install-dev`  (taskfile + testql)                             |
| List taskfile tasks               | `taskfile list`                                                     |
| Run TestQL smoke tests            | `testql run testql-scenarios/*.testql.toon.yaml`                    |

## Conventions that make this work

1. **Every entity declares a MIME.** `entities.primary_mime` points at
   `mime_types` which points at a content table. No service hardcodes
   which table holds what — they read the registry.
2. **Schemas carry `renderers[]`.** Generators advertise compatibility via
   data, not a central registry file.
3. **Filesystem layout is `schemas.fs_path_template`.** Change the
   template, the WebDAV/FUSE/sync-engine layouts all update together.
4. **Sources are always tracked.** Every row has `source ∈
   {filesystem, api, command, generator, system}`, and so does every
   `audit_log` entry. You always know who wrote what.

## Uniform protocols & storage plug-ins

Every protocol surface (WebDAV, FUSE, FTP, IMAP, POP3, SMTP) and every
inbound connector (filesystem, IMAP-pull, FTP-pull, SQL-mirror) implements
the same `EntityStore` contract from `libs/platform_storage/`. Add a new
protocol by writing a thin wrapper over that class — the data contract,
MIME routing and audit trail stay identical.

### Four registry tables

| Table               | What lives there                                      |
| ------------------- | ----------------------------------------------------- |
| `storage_backends`  | Databases/object-stores: postgres, sqlite, mysql, …   |
| `protocol_gateways` | Outbound surfaces: webdav, ftp, imap, pop3, smtp, …   |
| `inbound_sources`   | Pullers: filesystem, IMAP mailboxes, FTP dirs, SQL    |
| `service_mappings`  | Data-flow routing: source → target (DB → filesystem)    |

Seeded on first boot (`06_connectors.sql` + `08_service_mappings.sql`); add rows at runtime via UI or API.

### SDK (Python / JavaScript / PHP)

Programmatic access to entities, registry, and config:

```python
from dbos_client import DBOSClient
db = DBOSClient('http://localhost:3000')
db.login('admin@platform.local', 'demo1234')
db.create_entity('mail/hello', 'mail', 'mail_v1', {'title':'Hello','body':'World'})
db.create_service_mapping('imap-to-email', 'pg-primary', 'filesystem-email',
                          filter={'entity_type':'mail'},
                          transform={'format':'rfc5322','extension':'.eml'})
```

See `sdk/python/dbos_client.py`, `sdk/js/dbos_client.js`, `sdk/php/DBOSClient.php`.

### Start the extra protocols

```bash
docker compose --profile protocols up -d
#   vfs-ftp   :2121     (FTP, user/pass from FTP_USER/FTP_PASS)
#   vfs-imap  :1143     (IMAP4rev1)
#   vfs-pop3  :1110     (POP3)
#   vfs-smtp  :2525     (accepts incoming mail → entities)

docker compose --profile outbound up -d
#   sync-outbound       (exports DB entities → ./email/*.eml via service_mappings)
```

Example — read articles over IMAP with a mail client or `openssl`:

```bash
# Any IMAP client works. Account = localhost:1143, user 'admin', pass 'admin'.
# Mailbox "articles" lists every markdown entity; each message body IS the
# markdown, with entity metadata in RFC-5322 headers.
```

Example — upload a file via FTP, see it in the same DB:

```bash
lftp -u admin,admin localhost:2121
cd articles
put my-post.md      # -> content_markdown via platform_storage, source='ftp'
```

### Start the inbound pullers

```bash
docker compose --profile connectors up -d
```

Then register a remote source at runtime:

```sql
INSERT INTO inbound_sources (id, driver, endpoint, credentials_ref,
                             target_mime, id_template, config) VALUES
('support-mail', 'imap', 'imaps://mail.example.com:993', 'SUPPORT',
 'text/markdown', 'mail/{remote_id}',
 '{"mailbox":"INBOX","limit":50}');
```

Put `SUPPORT_USER`/`SUPPORT_PASS` in the env and the `connector-imap-pull`
daemon will begin polling it every minute, writing messages as `mail/*`
entities via the same `EntityStore.write()` used by `vfs-smtp`.

### Mirror to a different database

Declare a secondary backend and start the mirror daemon:

```sql
INSERT INTO storage_backends (id, driver, role, dsn) VALUES
('sqlite-mirror', 'sqlite', 'mirror', 'sqlite:///mirror-data/platform.sqlite');
```

```bash
docker compose --profile mirrors up -d storage-mirror
```

The daemon tails `audit_log` and replays every write into each mirror.
Both MySQL (`driver='mysql'`) and SQLite (`driver='sqlite'`) are
implemented; adding Mongo/Redis is one adapter class.

## What's deliberately not here

This is a usable dev scaffold, not a production stack. Things a production
deployment would add:

- Redis / Kafka for real async queues (commands currently execute inline)
- Object store (MinIO/S3) for `content_binary` when `storage_mode='object_store'`
- Observability (OTel traces, metrics, structured logs)
- Proper secrets management for JWT + DB credentials
- Connection pooling beyond what the Node/Python drivers provide by default
- Kubernetes manifests mirroring the compose topology


## License

Licensed under Apache-2.0.

<!-- taskill:status:start -->

## Status

_Last updated by [taskill](https://github.com/oqlos/taskill) at 2026-04-25 13:37 UTC_

| Metric | Value |
|---|---|
| HEAD | `d28c580` |
| Coverage | — |
| Failing tests | — |
| Commits in last cycle | 5 |

> Added documentation for a code analysis engine and a configuration management system; also introduced example files and additional service components.

<!-- taskill:status:end -->
