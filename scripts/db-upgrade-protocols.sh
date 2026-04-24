#!/usr/bin/env bash
set -euo pipefail

# Apply protocol/connector registry and mail schema additions to an already-
# initialized Postgres volume. Fresh databases get these from init scripts;
# this helper upgrades long-lived local dev volumes.

COMPOSE=${COMPOSE:-docker compose}
PSQL=( $COMPOSE exec -T postgres psql -U "${POSTGRES_USER:-platform}" -d "${POSTGRES_DB:-platform}" -v ON_ERROR_STOP=1 )

printf '== wait for postgres ==\n'
until $COMPOSE exec -T postgres pg_isready -U "${POSTGRES_USER:-platform}" -d "${POSTGRES_DB:-platform}" >/dev/null 2>&1; do
  sleep 1
done

has_table() {
  "${PSQL[@]}" -tAc "SELECT to_regclass('public.$1') IS NOT NULL" | tr -d '[:space:]'
}

printf '== upgrade connectors registry ==\n'
if [[ "$(has_table storage_backends)" != "t" ]]; then
  "${PSQL[@]}" -f /docker-entrypoint-initdb.d/06_connectors.sql
  echo 'applied 06_connectors.sql'
else
  echo 'storage_backends already present; skipping 06_connectors.sql'
fi

printf '== upgrade mail schema ==\n'
"${PSQL[@]}" -f /docker-entrypoint-initdb.d/07_mail_schema.sql

echo 'protocol upgrade complete'
