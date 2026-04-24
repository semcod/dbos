# Write via HTTP, read via every protocol

Creates one markdown entity through the HTTP API, then reads it back through
each protocol gateway in turn. Proves the core uniformity claim:

> The same entity is visible through WebDAV, FTP, IMAP, POP3 and HTTP —
> with no per-protocol replication code.

## What it tests

1. `POST /api/entities` — create `articles/examples-hello` (text/markdown)
2. `GET /api/entities/articles/examples-hello` — read via HTTP
3. `GET http://localhost:8090/articles/examples-hello.md` — read via WebDAV
4. `LIST articles/` over FTP — entity listed with correct filename
5. `LOGIN + SELECT articles + FETCH` over IMAP — body wrapped as RFC-5322
6. `USER / PASS / LIST` over POP3 — message count ≥ 1

Missing protocols (when not started) are reported as skipped, not failed.

## Run

```bash
make up-all          # needs the protocols profile
make example-01-write-http-read-protocols
```
