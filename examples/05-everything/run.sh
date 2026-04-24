#!/usr/bin/env bash
# Full-stack sanity: run every other example + protocol smoke test.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/../_lib.sh"

FAIL=0

say "Registry dump (protocol_gateways / storage_backends / inbound_sources)"
require_api
echo "── protocol gateways ──"
api_get "/api/protocol-gateways" | python3 -m json.tool | head -40
echo "── storage backends ──"
api_get "/api/storage-backends" | python3 -m json.tool | head -20
echo "── inbound sources ──"
api_get "/api/inbound-sources" | python3 -m json.tool | head -20

say "scripts/test-protocols.sh"
if bash "$HERE/../../scripts/test-protocols.sh"; then pass "protocol smoke test"; else fail "protocol smoke test"; FAIL=1; fi

for ex in 01-write-http-read-protocols 02-smtp-to-platform 03-sqlite-mirror 04-connectors-registry; do
  say "Running examples/$ex"
  if bash "$HERE/../$ex/run.sh"; then
    pass "$ex"
  else
    fail "$ex"
    FAIL=1
  fi
done

if [[ $FAIL -eq 0 ]]; then
  printf "\n${C_OK}★ full-stack PASS ★${C_OFF}\n"
else
  printf "\n${C_FAIL}full-stack FAIL${C_OFF}\n"
  exit 1
fi
