# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Protocol gateways** — `vfs-ftp` (port 2121, passive mode), `vfs-imap` (1143), `vfs-pop3` (1110), `vfs-smtp` (2525)
- **Shared storage contract** — `libs/platform_storage/` with `EntityStore` base + Postgres, SQLite, MySQL adapters
- **Storage mirror daemon** — `storage-mirror` tails `audit_log` and replays writes to secondary backends (SQLite / MySQL)
- **Inbound connectors** — `connectors/` with `_base/poller.py` for IMAP-pull, FTP-pull, SQL-mirror
- **Registry tables** — `storage_backends`, `protocol_gateways`, `inbound_sources` seeded via `06_connectors.sql`
- **Mail schema** — `07_mail_schema.sql` for SMTP/IMAP/POP3 mail entities (`mail_v1`)
- **API Gateway registry CRUD** — `GET|POST|PATCH|DELETE /api/storage-backends`, `/protocol-gateways`, `/inbound-sources`
- **Audit logging on entity creation** — `audit_log` inserts from `POST /api/entities` so mirrors stay in sync
- **Database upgrade script** — `scripts/db-upgrade-protocols.sh` applies new schema to existing Postgres volumes
- **Makefile** — `up`, `up-all`, `down`, `db-upgrade-protocols`, `examples`, `test`, `lint`, `clean`, `help`
- **Development tooling** — `taskfile` + `testql` Python packages integrated; `Taskfile.yml` + `requirements-dev.txt` + Makefile targets (`install-dev`, `taskfile`, `testql`)
- **Service mappings** — `service_mappings` table for dynamic source→target data routing (e.g. DB → `./email/*.eml`)
- **Outbound sync** — `sync-outbound` daemon reads `service_mappings` + `audit_log` and exports entities to filesystem targets
- **SDK** — Python (`sdk/python/dbos_client.py`), JavaScript (`sdk/js/dbos_client.js`), PHP (`sdk/php/DBOSClient.php`) clients with full entity + registry + config CRUD
  - `01-write-http-read-protocols` — write via HTTP, read via FTP/IMAP/POP3/WebDAV
  - `02-smtp-to-platform` — deliver via SMTP, read back via HTTP/IMAP/POP3
  - `03-sqlite-mirror` — declare mirror backend, verify replication
  - `04-connectors-registry` — CRUD all three registry tables via API
  - `05-everything` — full-stack smoke test of protocols + registry + examples

### Fixed
- **POP3** — `RETR` correctly returns synthesized RFC-5322 message with body content
- **SMTP** — `handle_DATA` stores mail as `mail/*` entities with YAML front-matter headers
- **Storage-mirror** — graceful retry when `storage_backends` table is missing on cold boot
- **Connectors** — poller sleeps and retries instead of crashing when `inbound_sources` is absent
- **API Gateway** — registry endpoints return `503` instead of crashing on missing tables
- **FTP passive mode** — configurable port range (30000–30100) and masquerade address via env vars

- feat(docs): code analysis engine
- feat(docs): configuration management system
- feat: add more services
- docs: add examples

## [0.0.2] - 2026-04-24

### Docs
- Update README.md
- Update SUMD.md
- Update SUMR.md
- Update project/README.md
- Update project/context.md

### Test
- Update test-gui.sh
- Update testql-scenarios/generated-api-smoke.testql.toon.yaml

### Other
- Update .gitignore
- Update api-gateway/src/index.js
- Update app.doql.less
- Update command-bus/src/index.js
- Update generators/gen-handlebars/src/index.js
- Update generators/gen-jinja/app.py
- Update generators/gen-twig/index.php
- Update postgres/init/03_content_tables.sql
- Update project.sh
- Update project/analysis.toon.yaml
- ... and 19 more files

## [0.0.1] - 2026-04-24

### Docs
- Update README.md
- Update data/articles/platform-os-architecture.md
- Update data/articles/reusing-services.md

### Other
- Update .env.example
- Update .gitignore
- Update api-gateway/Dockerfile
- Update api-gateway/package.json
- Update api-gateway/src/index.js
- Update cdn/nginx.conf
- Update command-bus/Dockerfile
- Update command-bus/package.json
- Update command-bus/src/index.js
- Update data/devices/device_005.json
- ... and 37 more files

