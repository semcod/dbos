# Connectors registry CRUD

Exercises the three registry tables through the API:
`storage_backends`, `protocol_gateways`, `inbound_sources`. Every UI action,
every compose service, every connector reads these — so CRUD on them is
effectively the platform's "settings panel".

Runs a full create / read / patch / delete cycle against each table and
confirms the operations took effect.

## Run

```bash
make up          # core is enough for this example
make example-04-connectors-registry
```
