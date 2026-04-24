#!/usr/bin/env bash
# Exercise every endpoint of the connectors registry.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/../_lib.sh"

require_api

STAMP=$(date +%s)
crud_cycle() {
  local kind=$1 id=$2 create_payload=$3 patch_payload=$4 expect_patched=$5

  say "$kind: LIST"
  RESP=$(api_get "/api/$kind")
  echo "$RESP" | grep -q '"data"' && pass "LIST returns data" || fail "LIST: $RESP"

  say "$kind: CREATE $id"
  api_del "/api/$kind/$id" >/dev/null 2>&1 || true   # idempotent
  RESP=$(api_post "/api/$kind" "$create_payload")
  echo "$RESP" | grep -q "\"$id\"" && pass "POST created" || { fail "POST: $RESP"; return 1; }

  say "$kind: GET $id"
  RESP=$(api_get "/api/$kind/$id")
  echo "$RESP" | grep -q "\"$id\"" && pass "GET found" || fail "GET: $RESP"

  say "$kind: PATCH $id"
  RESP=$(api_patch "/api/$kind/$id" "$patch_payload")
  echo "$RESP" | grep -q "$expect_patched" && pass "PATCH took" || fail "PATCH: $RESP"

  say "$kind: DELETE $id"
  RESP=$(api_del "/api/$kind/$id")
  echo "$RESP" | grep -q '"deleted":true' && pass "DELETE took" || fail "DELETE: $RESP"

  # Confirm deletion
  CODE=$(curl -sS -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $ADMIN_TOKEN" "$API_URL/api/$kind/$id")
  [[ "$CODE" == "404" ]] && pass "confirmed 404 after delete" || fail "after-delete code $CODE"
}

crud_cycle "storage-backends" "demo-sqlite-$STAMP" \
  "{\"id\":\"demo-sqlite-$STAMP\",\"driver\":\"sqlite\",\"role\":\"mirror\",\"dsn\":\"sqlite:///tmp/x.db\",\"enabled\":true}" \
  '{"enabled":false}' \
  '"enabled":false'

crud_cycle "protocol-gateways" "demo-gw-$STAMP" \
  "{\"id\":\"demo-gw-$STAMP\",\"protocol\":\"http\",\"service_name\":\"fake\",\"endpoint\":\"tcp://0.0.0.0:9999\",\"storage_backend\":\"pg-primary\",\"enabled\":true}" \
  '{"read_enabled":false}' \
  '"read_enabled":false'

crud_cycle "inbound-sources" "demo-src-$STAMP" \
  "{\"id\":\"demo-src-$STAMP\",\"driver\":\"imap\",\"endpoint\":\"imaps://nowhere\",\"poll_seconds\":60,\"enabled\":false,\"id_template\":\"{source_id}/{remote_id}\"}" \
  '{"poll_seconds":300}' \
  '"poll_seconds":300'

finish
