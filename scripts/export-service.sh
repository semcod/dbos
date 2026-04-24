#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# export-service.sh — rip one service + its schema + its content tables into
# a portable bundle that can be dropped into another project's DB + compose.
#
# Usage:
#   ./scripts/export-service.sh gen-jinja
#
# Produces:  ./export/<service>/
#   bundle.sql              — CREATE TABLE + data for tables this service touches
#   docker-compose.snippet  — service block ready to paste
#   README.md               — what was exported
# -----------------------------------------------------------------------------
set -euo pipefail

SERVICE="${1:-}"
[ -z "$SERVICE" ] && { echo "usage: $0 <service-name>"; exit 1; }

# What each service needs. Extend this map when you add new services.
case "$SERVICE" in
  gen-jinja)
    TABLES=(schemas mime_types content_markdown content_html)
    SERVICE_DIR="generators/gen-jinja"
    ;;
  gen-twig)
    TABLES=(schemas mime_types content_html content_json content_markdown)
    SERVICE_DIR="generators/gen-twig"
    ;;
  gen-handlebars)
    TABLES=(schemas mime_types content_json content_html)
    SERVICE_DIR="generators/gen-handlebars"
    ;;
  sync-engine)
    TABLES=(schemas mime_types schema_paths entities \
            content_json content_yaml content_xml content_html \
            content_markdown content_binary audit_log)
    SERVICE_DIR="sync-engine"
    ;;
  *)
    echo "unknown service: $SERVICE"; exit 1 ;;
esac

OUT="export/$SERVICE"
mkdir -p "$OUT"

echo "▸ exporting $SERVICE"
echo "  tables: ${TABLES[*]}"

# Pull schema+data for those tables only.
TABLE_ARGS=""
for t in "${TABLES[@]}"; do TABLE_ARGS+=" -t $t"; done

docker exec platform-postgres pg_dump -U platform \
  $TABLE_ARGS \
  --data-only=false --schema-only=false \
  --no-owner --no-privileges \
  platform > "$OUT/bundle.sql"

# Copy the service source
cp -r "$SERVICE_DIR" "$OUT/service/"

# Grab the docker-compose stanza for this service
awk "/^  $SERVICE:/,/^  [a-zA-Z-]+:/{if (/^  [a-zA-Z-]+:/ && !/^  $SERVICE:/) exit; print}" \
  docker-compose.yml > "$OUT/docker-compose.snippet.yml"

cat > "$OUT/README.md" <<EOF
# $SERVICE — portable bundle

## What's inside

- \`service/\` — source + Dockerfile
- \`bundle.sql\` — schema + data for: ${TABLES[*]}
- \`docker-compose.snippet.yml\` — the service block

## Drop into a new project

\`\`\`bash
# 1. load the tables into the new project's DB
psql \$DATABASE_URL < bundle.sql

# 2. paste docker-compose.snippet.yml into your compose file

# 3. build and run
docker compose up --build $SERVICE
\`\`\`

The service will self-bootstrap: on first request it queries \`mime_types\`
and \`schemas\` and starts handling the MIMEs it's registered for. No code
changes needed.
EOF

echo "✓ written to $OUT/"
ls -la "$OUT"
