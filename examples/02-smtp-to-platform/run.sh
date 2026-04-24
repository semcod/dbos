#!/usr/bin/env bash
# Send mail via SMTP, read it back via every other channel.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/../_lib.sh"

require_api

SUBJECT="example-$(date +%s)"
SENTINEL="platform-inbound-$SUBJECT"

say "Deliver via SMTP :$SMTP_PORT"
if ! require_port "SMTP" "$SMTP_HOST" "$SMTP_PORT"; then
  fail "SMTP not running — 'make up-all' first"
  finish
fi

OUT=$(printf 'HELO test\r\nMAIL FROM:<robot@ex.local>\r\nRCPT TO:<admin@local>\r\nDATA\r\nSubject: %s\r\n\r\n%s\r\n.\r\nQUIT\r\n' \
        "$SUBJECT" "$SENTINEL" | nc -q 2 "$SMTP_HOST" "$SMTP_PORT" 2>/dev/null || true)
echo "$OUT" | grep -q "250" && pass "SMTP accepted" || fail "SMTP did not 250: $OUT"

# Give the DB a moment to receive the INSERT
sleep 1

say "Entity present via HTTP"
RESP=$(api_get "/api/entities?entity_type=mail&limit=10")
if echo "$RESP" | grep -q "\"external_id\""; then pass "GET /api/entities?entity_type=mail"; else fail "no mail entities: $RESP"; fi

# Find the one containing the sentinel
MATCH_ID=$(echo "$RESP" | python3 -c '
import sys, json, urllib.parse
d = json.load(sys.stdin).get("data", [])
# Print ids; calling script will re-check body
for e in d: print(e["external_id"])
' | head -5)
FOUND=""
for eid in $MATCH_ID; do
  ENC=$(python3 -c "import urllib.parse;print(urllib.parse.quote('$eid',safe=''))")
  BODY=$(api_get "/api/entity?external_id=$ENC")
  if echo "$BODY" | grep -q "$SENTINEL"; then FOUND=$eid; break; fi
done
if [[ -n "$FOUND" ]]; then pass "HTTP finds message body: $FOUND"; else fail "no mail carried sentinel $SENTINEL"; fi

say "Same message via IMAP"
if require_port "IMAP" "$IMAP_HOST" "$IMAP_PORT"; then
  OUT=$(printf 'a1 LOGIN %s %s\r\na2 SELECT mail\r\na3 FETCH 1:* (BODY[])\r\na4 LOGOUT\r\n' \
          "$IMAP_USER" "$IMAP_PASS" | nc -q 2 "$IMAP_HOST" "$IMAP_PORT" 2>/dev/null || true)
  echo "$OUT" | grep -q "$SENTINEL" && pass "IMAP FETCH contains sentinel" || fail "IMAP missing sentinel"
fi

say "Same message via POP3"
if require_port "POP3" "$POP3_HOST" "$POP3_PORT"; then
  OUT=$(printf 'USER %s\r\nPASS %s\r\nRETR 1\r\nQUIT\r\n' "$POP3_USER" "$POP3_PASS" \
          | nc -q 2 "$POP3_HOST" "$POP3_PORT" 2>/dev/null || true)
  # Message 1 may be anything; scan all LIST then RETR each
  TOTAL=$(printf 'USER %s\r\nPASS %s\r\nLIST\r\nQUIT\r\n' "$POP3_USER" "$POP3_PASS" \
            | nc -q 2 "$POP3_HOST" "$POP3_PORT" 2>/dev/null | grep -cE '^[0-9]+ [0-9]+' || true)
  HIT=0
  for i in $(seq 1 "${TOTAL:-0}"); do
    OUT=$(printf 'USER %s\r\nPASS %s\r\nRETR %d\r\nQUIT\r\n' "$POP3_USER" "$POP3_PASS" "$i" \
            | nc -q 2 "$POP3_HOST" "$POP3_PORT" 2>/dev/null || true)
    if echo "$OUT" | grep -q "$SENTINEL"; then HIT=1; break; fi
  done
  [[ $HIT -eq 1 ]] && pass "POP3 RETR contains sentinel" || fail "POP3 never returned sentinel"
fi

finish
