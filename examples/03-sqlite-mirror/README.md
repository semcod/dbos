# Mirror all writes to SQLite

Declares a secondary storage backend with `driver='sqlite'` and `role='mirror'`.
The `storage-mirror` daemon tails `audit_log` and replays every write through
`SqliteStore.write()` — the exact same `EntityStore` method a protocol gateway
uses.

Demonstrates **storage plurality**: the Postgres source of truth stays untouched,
but a SQLite file on disk receives a byte-for-byte copy, queryable offline.

## Requirements

- `make up-all` (needs the `mirrors` profile)
- `python3` on host (used to open the sqlite file for verification)

## Run

```bash
make example-03-sqlite-mirror
```
