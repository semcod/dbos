#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# demo.sh — end-to-end walkthrough of the platform.
#
# Prereq:  docker compose up --build   (let it settle ~20s)
# Usage:   ./scripts/demo.sh
# -----------------------------------------------------------------------------
set -euo pipefail

API="${API:-http://localhost:3000}"
CDN="${CDN:-http://localhost:8080}"
JINJA="${JINJA:-http://localhost:6001}"
TWIG="${TWIG:-http://localhost:6002}"
HBS="${HBS:-http://localhost:6003}"

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
dim()   { printf "\033[2m%s\033[0m\n" "$*"; }
step()  { printf "\n\033[36m▸ %s\033[0m\n" "$*"; }

need() { command -v "$1" >/dev/null || { echo "install $1"; exit 1; }; }
need curl
need jq

# -----------------------------------------------------------------------------
step "1. Check health of every service"
for url in "$API/health" "$JINJA/health" "$TWIG/health" "$HBS/health" "$CDN/health"; do
  printf "  %-40s " "$url"
  curl -sf "$url" | jq -c . || echo "DOWN"
done

# -----------------------------------------------------------------------------
step "2. Log in as admin"
TOKEN=$(curl -sf -X POST "$API/auth/login" \
  -H 'content-type: application/json' \
  -d '{"email":"admin@platform.local","password":"demo1234"}' | jq -r .token)
echo "token: ${TOKEN:0:40}…"
AUTH="Authorization: Bearer $TOKEN"

# -----------------------------------------------------------------------------
step "3. Inspect the MIME-routing registry"
dim "   (services read this at startup to know where payloads live)"
curl -sf "$API/mime-types" | jq -r '.[] | "  \(.mime)  →  \(.content_table)   (\(.category))"'

# -----------------------------------------------------------------------------
step "4. Inspect schemas and which generators advertise support"
curl -sf "$API/schemas" | jq -r '.[] | "  \(.id)  kind=\(.kind)  renderers=\(.renderers | join(","))"'

# -----------------------------------------------------------------------------
step "5. List entities seeded by docker-entrypoint"
curl -sf -H "$AUTH" "$API/api/entities?limit=20" \
  | jq -r '.data[] | "  \(.external_id)  \(.entity_type)  \(.primary_mime)  v\(.version)"'

# -----------------------------------------------------------------------------
step "6. Fetch a markdown article (shows entity + content_markdown join)"
curl -sf -H "$AUTH" "$API/api/entities/hello-platform" \
  | jq '{entity: .entity | {external_id, entity_type, primary_mime},
         content_table, word_count: .content.word_count,
         front_matter: .content.front_matter}'

# -----------------------------------------------------------------------------
step "7. Render the same article through all three generators"
dim "   each reads content_markdown or content_json and writes content_html"

echo "  → gen-jinja (Python + Jinja2):"
curl -sf -X POST "$JINJA/render/hello-platform" | jq -c .

echo "  → gen-handlebars (Node + Handlebars) — needs a JSON entity:"
curl -sf -X POST "$HBS/render/device_001" | jq -c .

echo "  → gen-twig (PHP + Twig) — needs template + data:"
curl -sf -X POST "$TWIG/render/landing" \
  -H 'content-type: application/json' \
  -d '{"data_from":"device_001"}' | jq -c .

# -----------------------------------------------------------------------------
step "8. Check /capabilities — generators self-report"
for g in "$JINJA" "$HBS"; do
  printf "  %s → " "$g"
  curl -sf "$g/capabilities" | jq -c .
done
printf "  %s → " "$TWIG"; curl -sf "$TWIG/capabilities" | jq -c .

# -----------------------------------------------------------------------------
step "9. View the rendered HTML (first 300 chars)"
curl -sf -H "$AUTH" "$API/api/entities/hello-platform/html" | head -c 300
echo "…"

# -----------------------------------------------------------------------------
step "10. Drop a new markdown file into data/ — sync-engine picks it up"
NEW="data/articles/demo-$(date +%s).md"
cat > "$NEW" <<EOF
---
title: Live-synced article
author: demo.sh
tags: [live]
slug: demo-live
---

# Live-synced

This file was written by demo.sh and is now in \`content_markdown\`.
EOF
dim "  created $NEW — waiting 3s for watcher"
sleep 3
ls -l "$NEW"
BASENAME=$(basename "$NEW" .md)
curl -sf -H "$AUTH" "$API/api/entities/$BASENAME" \
  | jq '{entity: .entity.external_id, via: .content.source, words: .content.word_count}'

# -----------------------------------------------------------------------------
step "11. Execute a command through the bus (create a new device via worker-python)"
curl -sf -H "$AUTH" -H 'content-type: application/json' \
  -X POST "$API/commands/create_device" \
  -d '{"name":"DemoDevice-9000","device_type":"controller","external_id":"device_demo_9000"}' \
  | jq .

# -----------------------------------------------------------------------------
step "12. Tail the audit log"
curl -sf -H "$AUTH" "$API/audit" \
  | jq -r '.[0:12][] | "  \(.created_at)  \(.source | .[0:2])  \(.action)  \(.content_table)"'

# -----------------------------------------------------------------------------
bold "done. browse the UI at http://localhost:5173"
