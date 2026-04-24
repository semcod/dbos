# Full-stack sanity

Umbrella example. Calls every other example in sequence, plus `test-protocols.sh`,
plus a registry dump. Useful as a single `PASS/FAIL` gate before committing.

## Run

```bash
make up-all
make example-05-everything
```
