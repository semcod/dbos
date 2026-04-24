#!/usr/bin/env bash
# Declare a sqlite mirror backend, write an entity, verify it lands in the .sqlite file.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/../_lib.sh"

SQLITE_FILE="${SQLITE_FILE:-mirror-data/platform.sqlite}"
BACKEND_ID="sqlite-mirror-demo"
EXTERNAL_ID="sqlite-mirror-$(date +%s)"
SENTINEL="mirror-works-$(date +%s)"

require_api

say "Declare sqlite mirror backend via API"
api_del "/api/storage-backends/$BACKEND_ID" >/dev/null 2>&1 || true
PAYLOAD=$(cat <<JSON
{"id":"$BACKEND_ID","driver":"sqlite","role":"mirror",
 "dsn":"sqlite:///mirror-data/platform.sqlite","enabled":true,"config":{}}
JSON
)
RESP=$(api_post "/api/storage-backends" "$PAYLOAD")
if echo "$RESP" | grep -q "\"id\""; then
  pass "created $BACKEND_ID"
else
  fail "could not create backend: $RESP"; finish
fi

say "Ensure storage-mirror is running and reloads the new backend"
if docker compose --profile mirrors up -d storage-mirror >/dev/null 2>&1; then
  docker compose restart storage-mirror >/dev/null 2>&1 || true
  pass "storage-mirror restarted"
else
  fail "could not start storage-mirror via docker compose"
  finish
fi

say "Create entity via HTTP"
CREATE_PAYLOAD=$(cat <<JSON
{"external_id":"$EXTERNAL_ID","entity_type":"article","schema_id":"article_v1",
 "content":{"title":"SQLite Mirror Example","body":"$SENTINEL\n","front_matter":{"title":"SQLite Mirror Example"}}}
JSON
)
RESP=$(api_post "/api/entities" "$CREATE_PAYLOAD")
echo "$RESP" | grep -q '"id"' && pass "entity created" || { fail "create: $RESP"; finish; }

say "Wait for mirror to catch up"
for i in $(seq 1 10); do
  sleep 1
  if [[ -f "$SQLITE_FILE" ]] && python3 - "$SQLITE_FILE" "$EXTERNAL_ID" <<'PY' >/dev/null 2>&1
import sqlite3, sys
path, eid = sys.argv[1], sys.argv[2]
c = sqlite3.connect(path)
row = c.execute("SELECT body FROM entities WHERE external_id=?", (eid,)).fetchone()
sys.exit(0 if row and row[0] else 1)
PY
  then
    pass "entity replicated to $SQLITE_FILE"
    break
  fi
  [[ $i -eq 10 ]] && fail "entity never appeared in sqlite mirror after 10s"
done

if [[ -f "$SQLITE_FILE" ]]; then
  say "Verify body content in sqlite mirror"
  BODY=$(python3 - "$SQLITE_FILE" "$EXTERNAL_ID" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
row = c.execute("SELECT body FROM entities WHERE external_id=?", (sys.argv[2],)).fetchone()
print(row[0].decode("utf-8","replace") if row else "")
PY
)
  if echo "$BODY" | grep -q "$SENTINEL"; then
    pass "sqlite holds identical body"
  else
    fail "sqlite body mismatch: '$BODY'"
  fi
fi

finish
