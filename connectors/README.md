# Connectors

Inbound data pullers. Each connector reads from a remote system (IMAP mailbox,
FTP server, external SQL DB, webhook) and writes discovered items into the
platform via the shared `platform_storage.EntityStore` contract — the same
interface used by `vfs-webdav`, `vfs-ftp`, `vfs-imap`, etc.

Runtime configuration lives in the `inbound_sources` registry table. At
startup each connector queries the registry with its driver name (e.g.
`driver='imap'`) and reacts to every enabled row.

| Connector        | Driver       | What it does                                  |
| ---------------- | ------------ | --------------------------------------------- |
| `imap-pull`      | `imap`       | polls an external IMAP mailbox → entities     |
| `ftp-pull`       | `ftp`        | polls an external FTP directory → entities    |
| `sql-mirror`     | `sql`        | mirrors rows from external MySQL/SQLite tables|

All three are opt-in: `docker compose --profile connectors up`.
