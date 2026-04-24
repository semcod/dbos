#!/usr/bin/env bash
# Write via HTTP, read via every protocol — proves uniformity of gateways.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/../_lib.sh"

EXTERNAL_ID="examples-hello"
BODY_SENTINEL="platform-os-example-$(date +%s)"

say "Login"
require_api
pass "got admin token"

say "Create entity via HTTP"
CREATE_PAYLOAD=$(cat <<JSON
{"external_id":"$EXTERNAL_ID","entity_type":"article","schema_id":"article_v1",
 "content":{"title":"Example Hello","body":"# hello\n\n$BODY_SENTINEL\n","front_matter":{"title":"Example Hello"}}}
JSON
)
# If it already exists from a previous run, delete first (ignore errors).
api_del "/api/entity?external_id=$(urlencode "$EXTERNAL_ID")" >/dev/null 2>&1 || true
RESP=$(api_post "/api/entities" "$CREATE_PAYLOAD")
if echo "$RESP" | grep -q '"id"'; then pass "POST /api/entities"; else fail "POST /api/entities: $RESP"; fi

say "Read via HTTP"
RESP=$(api_get "/api/entity?external_id=$(urlencode "$EXTERNAL_ID")")
if echo "$RESP" | grep -q "$BODY_SENTINEL"; then pass "GET /api/entity returns body"; else fail "GET /api/entity: $RESP"; fi

say "Read via WebDAV"
if curl -sS -u "$WEBDAV_USER:$WEBDAV_PASS" "$WEBDAV_URL/articles/examples-hello.md" | grep -q "$BODY_SENTINEL"; then
  pass "WebDAV GET body"
else
  warn "WebDAV did not return body (service not started or not seeded)"
fi

say "Read via FTP"
if require_port "FTP" "$FTP_HOST" "$FTP_PORT"; then
  if curl -sS -u "$FTP_USER:$FTP_PASS" "ftp://$FTP_HOST:$FTP_PORT/article/examples-hello.md" | grep -q "$BODY_SENTINEL"; then
    pass "FTP RETR body"
  else
    fail "FTP did not return body"
  fi
fi

say "Read via IMAP"
if require_port "IMAP" "$IMAP_HOST" "$IMAP_PORT"; then
  OUT=$(printf 'a1 LOGIN %s %s\r\na2 SELECT article\r\na3 FETCH 1:* (BODY[])\r\na4 LOGOUT\r\n' \
          "$IMAP_USER" "$IMAP_PASS" | nc -q 2 "$IMAP_HOST" "$IMAP_PORT" 2>/dev/null || true)
  if echo "$OUT" | grep -q "$BODY_SENTINEL"; then
    pass "IMAP FETCH body"
  else
    fail "IMAP did not deliver body"
  fi
fi

say "Read via POP3"
if require_port "POP3" "$POP3_HOST" "$POP3_PORT"; then
  OUT=$(printf 'USER %s\r\nPASS %s\r\nLIST\r\nQUIT\r\n' "$POP3_USER" "$POP3_PASS" \
          | nc -q 2 "$POP3_HOST" "$POP3_PORT" 2>/dev/null || true)
  COUNT=$(echo "$OUT" | grep -cE '^[0-9]+ [0-9]+' || true)
  HIT=0
  for i in $(seq 1 "${COUNT:-0}"); do
    OUT=$(printf 'USER %s\r\nPASS %s\r\nRETR %d\r\nQUIT\r\n' "$POP3_USER" "$POP3_PASS" "$i" \
            | nc -q 2 "$POP3_HOST" "$POP3_PORT" 2>/dev/null || true)
    if echo "$OUT" | grep -q "$BODY_SENTINEL"; then
      HIT=1
      break
    fi
  done
  if [[ "$HIT" -eq 1 ]]; then
    pass "POP3 RETR found the created message"
  else
    fail "POP3 never returned the created message"
  fi
fi

finish
