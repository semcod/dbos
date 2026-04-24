# SMTP becomes a platform entity

Sends a plain SMTP message to `vfs-smtp`, then verifies that a new `mail/*`
entity exists via the HTTP API, and that the same message can be retrieved via
IMAP/POP3.

Demonstrates that **inbound protocols write through the same `EntityStore`
contract as outbound ones** — there is no mail-specific code path in storage.

## Run

```bash
make up-all
make example-02-smtp-to-platform
```
