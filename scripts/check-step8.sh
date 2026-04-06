#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[step8] ensuring services are up"
docker compose --profile app up -d db redis api workers >/dev/null

echo "[step8] health check"
curl -fsS http://localhost:8080/api/health >/dev/null

echo "[step8] checking gpsjam API row count"
GPSJAM_ROWS=$(curl -fsS http://localhost:8080/api/gpsjam/current | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d))')

if [[ "$GPSJAM_ROWS" -le 0 ]]; then
  echo "[step8] FAIL: /api/gpsjam/current returned 0 rows"
  docker compose logs --tail=80 workers | sed -n '/gpsjam/Ip'
  exit 1
fi

echo "[step8] PASS: gpsjam rows=$GPSJAM_ROWS"
