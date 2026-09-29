#!/usr/bin/env bash
# Post-startup smoke test: verifies the four services are up and that the
# copilot backend can see the MCP tool catalog. Run after `docker compose up`
# (or after starting all four services locally per the README "Option B").
#
# Usage: ./scripts/smoke_test.sh [base_host]
#   base_host defaults to "localhost".

set -euo pipefail

HOST="${1:-localhost}"
FAIL=0

check() {
  local name="$1" url="$2"
  if curl -fsS -o /dev/null -m 5 "$url"; then
    echo "OK   $name ($url)"
  else
    echo "FAIL $name ($url)"
    FAIL=1
  fi
}

echo "== Alarm Investigation Copilot smoke test =="
check "alarm-api simulator" "http://${HOST}:8000/health"
check "alarm-mcp server"    "http://${HOST}:9000/health"
check "copilot backend"     "http://${HOST}:8080/health"
check "streamlit frontend"  "http://${HOST}:8501/_stcore/health"

echo
echo "== MCP tool catalog (via copilot backend) =="
if curl -fsS -m 5 "http://${HOST}:8080/tools" | python3 -m json.tool 2>/dev/null; then
  echo "OK   /tools returned a catalog"
else
  echo "FAIL could not fetch /tools"
  FAIL=1
fi

if [ "$FAIL" -ne 0 ]; then
  echo
  echo "One or more checks failed. See docs/known-limitations.md if this is"
  echo "the first run after 'docker compose up --build' on a fresh machine."
  exit 1
fi

echo
echo "All services healthy."
