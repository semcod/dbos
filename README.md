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
- **api-gateway** — generic `/api/entities/:id` that joins `entities` with the correct content table at runtime
- **command-bus** — persists every command, routes to a worker by `schemas.target_runtime`
- **worker-python** / **worker-php** — execute business logic
- **gen-jinja** (Python), **gen-twig** (PHP), **gen-handlebars** (Node) — three website generators, each reading the same tables, each declaring what it can render in `schemas.renderers[]`
- **ui-runtime** — schema-driven frontend
- **nginx-cdn** — reverse proxy with preview caching
- **vfs-webdav** — WebDAV skin over the same tables (mount from anywhere)
- **vfs-fuse** — real Linux FUSE mount

## Layout

```
platform/
├─ docker-compose.yml
├─ .env.example
├─ postgres/init/                 5 SQL files run on first boot
│  ├─ 01_core.sql                 extensions, users, ACL, audit_log
│  ├─ 02_registry.sql             schemas, mime_types, schema_paths, filesystem_map
│  ├─ 03_content_tables.sql       entities + content_json/yaml/xml/html/markdown/binary
│  ├─ 04_schemas_seed.sql         JSON Schemas + renderer declarations
│  └─ 05_demo_data.sql            first rows in every content table
├─ sync-engine/                   filesystem -> DB, MIME-routed
├─ api-gateway/                   REST + ACL + schema validation
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
├─ data/                          watched by sync-engine
│  ├─ articles/*.md
│  ├─ devices/*.json
│  ├─ pages/*.html
│  ├─ scenarios/*.yaml
│  └─ protocols/*.xml
└─ scripts/
   ├─ demo.sh                     end-to-end walkthrough
   └─ export-service.sh           extract one service + its tables for reuse
```

## Quickstart

```bash
cp .env.example .env
docker compose up --build
```

What happens on first boot:

1. Postgres runs the 5 init SQL files (schemas, demo data)
2. `sync-engine` picks up every file in `./data/` and writes it to the matching content table
3. All three generators wake up and publish `/capabilities` from `schemas.renderers[]`
4. UI at <http://localhost:5173> (login `admin@platform.local` / `demo1234`)
5. CDN at <http://localhost:8080>, WebDAV at `http://localhost:8090`

Then from a second terminal:

```bash
./scripts/demo.sh
```

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
           +-------------+        WebDAV          FUSE
           | UI / Client |         |               |
           +------+------+         |               |
                  |                v               v
                  |         +--------------+  +----------+
                  v         |  vfs-webdav  |  | vfs-fuse |
           +-------------+  +------+-------+  +----+-----+
           |  api-gateway|         |               |
           +------+------+         |               |
                  |                v               v
                  |         +-----------------------------+
                  |         |         PostgreSQL          |
                  v         |  entities + content_json    |
           +-------------+  |        + content_yaml       |
           | command-bus |->|        + content_xml        |
           +------+------+  |        + content_html       |
                  |         |        + content_markdown   |
    +-------------+---+     |        + content_binary     |
    v             v   v     |  schemas, mime_types        |
 worker-       gen-*    +-->|  audit_log, commands        |
 python/php                 +-----------------------------+
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
| List entities                     | `GET /api/entities?entity_type=device`                              |
| Fetch entity + content            | `GET /api/entities/:external_id`                                    |
| View rendered HTML                | `GET /api/entities/:external_id/html`                               |
| Inspect routing                   | `GET /mime-types`  and  `GET /schemas`                              |
| Who renders schema X?             | `SELECT renderers FROM schemas WHERE id = 'article_v1';`            |
| Run a command                     | `POST /commands/create_device  {...}`                               |
| Audit                             | `GET /audit` (admin only)                                           |
| Mount as filesystem               | `mount -t davfs http://localhost:8090 /mnt/vfs`                     |
| Export one service                | `./scripts/export-service.sh gen-jinja`                             |

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
