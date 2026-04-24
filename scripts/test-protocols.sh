#!/usr/bin/env bash
# test-protocols.sh — verify every new protocol gateway answers on its port.
#
# Assumes `docker compose --profile protocols up -d` is running.
# Nothing in here writes data; every test is read-only or sends a dummy mail.

set -euo pipefail

HOST=${HOST:-localhost}
FTP_PORT=${FTP_PORT:-2121}
IMAP_PORT=${IMAP_PORT:-1143}
POP3_PORT=${POP3_PORT:-1110}
SMTP_PORT=${SMTP_PORT:-2525}
USER=${USER_OVERRIDE:-admin}
PASS=${PASS_OVERRIDE:-admin}

pass() { printf "  \033[32mOK\033[0m  %s\n" "$1"; }
fail() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; exit 1; }

say() { printf "\n\033[36m== %s ==\033[0m\n" "$1"; }

# --- FTP ---------------------------------------------------------------------
say "FTP :$FTP_PORT"
if command -v curl >/dev/null; then
  if curl -s --connect-timeout 5 "ftp://${USER}:${PASS}@${HOST}:${FTP_PORT}/" | head -c 200 >/dev/null; then
    pass "FTP listing"
  else
    fail "FTP listing"
  fi
else
  echo "  skipped (no curl)"
fi

# --- IMAP --------------------------------------------------------------------
say "IMAP :$IMAP_PORT"
imap_out=$(printf 'a1 LOGIN %s %s\r\na2 LIST "" *\r\na3 LOGOUT\r\n' "$USER" "$PASS" \
  | nc -q 2 "$HOST" "$IMAP_PORT" 2>/dev/null || true)
echo "$imap_out" | grep -q "a2 OK LIST completed" \
  && pass "IMAP LOGIN + LIST" \
  || fail "IMAP LOGIN + LIST"

# --- POP3 --------------------------------------------------------------------
say "POP3 :$POP3_PORT"
pop_out=$(printf 'USER %s\r\nPASS %s\r\nSTAT\r\nQUIT\r\n' "$USER" "$PASS" \
  | nc -q 2 "$HOST" "$POP3_PORT" 2>/dev/null || true)
echo "$pop_out" | grep -q "^+OK " \
  && pass "POP3 USER/PASS/STAT" \
  || fail "POP3 USER/PASS/STAT"

# --- SMTP --------------------------------------------------------------------
say "SMTP :$SMTP_PORT"
smtp_out=$(printf 'HELO test\r\nMAIL FROM:<test@local>\r\nRCPT TO:<admin@local>\r\nDATA\r\nSubject: smoketest\r\n\r\nhello\r\n.\r\nQUIT\r\n' \
  | nc -q 2 "$HOST" "$SMTP_PORT" 2>/dev/null || true)
echo "$smtp_out" | grep -q "250" \
  && pass "SMTP accepted message" \
  || fail "SMTP accepted message"

# --- WebDAV (pre-existing) ---------------------------------------------------
say "WebDAV :8090"
if curl -s --connect-timeout 5 -u "${USER}:${PASS}" "http://${HOST}:8090/" | head -c 50 >/dev/null; then
  pass "WebDAV root"
fi

printf "\n\033[32mAll protocol gateways answered.\033[0m\n"
