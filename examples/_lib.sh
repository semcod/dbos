#!/usr/bin/env bash
# Shared helpers for examples/*/run.sh
# Sourced via:  source "$(dirname "$0")/../_lib.sh"

set -uo pipefail

: "${API_URL:=http://localhost:3000}"
: "${ADMIN_EMAIL:=admin@platform.local}"
: "${ADMIN_PASSWORD:=demo1234}"
: "${FTP_HOST:=localhost}"
: "${FTP_PORT:=2121}"
: "${FTP_USER:=admin}"
: "${FTP_PASS:=admin}"
: "${IMAP_HOST:=localhost}"
: "${IMAP_PORT:=1143}"
: "${IMAP_USER:=admin}"
: "${IMAP_PASS:=admin}"
: "${POP3_HOST:=localhost}"
: "${POP3_PORT:=1110}"
: "${POP3_USER:=admin}"
: "${POP3_PASS:=admin}"
: "${SMTP_HOST:=localhost}"
: "${SMTP_PORT:=2525}"
: "${WEBDAV_URL:=http://localhost:8090}"
: "${WEBDAV_USER:=admin}"
: "${WEBDAV_PASS:=admin}"

C_OK='\033[32m'; C_FAIL='\033[31m'; C_HEAD='\033[36m'; C_MUTED='\033[90m'; C_OFF='\033[0m'

say()  { printf "\n${C_HEAD}» %s${C_OFF}\n" "$*"; }
pass() { printf "  ${C_OK}OK${C_OFF}   %s\n" "$*"; }
fail() { printf "  ${C_FAIL}FAIL${C_OFF} %s\n" "$*"; EXAMPLE_FAIL=1; }
warn() { printf "  ${C_MUTED}skip${C_OFF} %s\n" "$*"; }
info() { printf "  ${C_MUTED}%s${C_OFF}\n" "$*"; }

: "${EXAMPLE_FAIL:=0}"

# --- token management --------------------------------------------------------
get_token() {
  local t
  t=$(curl -s -X POST "$API_URL/auth/login" \
       -H 'content-type: application/json' \
       -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
       | python3 -c 'import sys,json;print(json.load(sys.stdin).get("token",""))' 2>/dev/null)
  echo "$t"
}

require_api() {
  ADMIN_TOKEN=$(get_token)
  if [[ -z "$ADMIN_TOKEN" ]]; then
    fail "API not reachable at $API_URL (did you run 'make up'?)"
    exit 1
  fi
  export ADMIN_TOKEN
}

# --- port probing ------------------------------------------------------------
port_open() {
  local host=$1 port=$2
  (exec 3<>/dev/tcp/"$host"/"$port") 2>/dev/null && return 0 || return 1
}

require_port() {
  local name=$1 host=$2 port=$3
  if ! port_open "$host" "$port"; then
    warn "$name :$port not reachable — start with 'make up-all'"
    return 1
  fi
  return 0
}

urlencode() {
  python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"
}

compose_service_running() {
  local svc=$1
  docker compose ps --status running --services 2>/dev/null | grep -qx "$svc"
}

# --- API helpers -------------------------------------------------------------
api_get()   { curl -sS -H "Authorization: Bearer $ADMIN_TOKEN" "$API_URL$1"; }
api_post()  { curl -sS -H "Authorization: Bearer $ADMIN_TOKEN" -H 'content-type: application/json' -d "$2" "$API_URL$1"; }
api_patch() { curl -sS -X PATCH -H "Authorization: Bearer $ADMIN_TOKEN" -H 'content-type: application/json' -d "$2" "$API_URL$1"; }
api_del()   { curl -sS -X DELETE -H "Authorization: Bearer $ADMIN_TOKEN" "$API_URL$1"; }

# --- final verdict -----------------------------------------------------------
finish() {
  if [[ "$EXAMPLE_FAIL" -eq 0 ]]; then
    printf "\n${C_OK}[example PASSED]${C_OFF}\n"
    exit 0
  else
    printf "\n${C_FAIL}[example FAILED]${C_OFF}\n"
    exit 1
  fi
}
