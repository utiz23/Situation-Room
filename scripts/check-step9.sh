#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[step9] ensuring services are up"
docker compose --profile app up -d db redis api workers >/dev/null

echo "[step9] health check"
curl -fsS http://localhost:8080/api/health >/dev/null

echo "[step9] checking satellites API row count"
SAT_ROWS=$(curl -fsS http://localhost:8080/api/satellites/tles | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else -1)')

if [[ "$SAT_ROWS" -le 0 ]]; then
  echo "[step9] FAIL: /api/satellites/tles returned 0 rows"
  echo "[step9] recent satellite worker logs:"
  docker compose logs --tail=120 workers | sed -n '/satellites/Ip'
  echo "[step9] DB rows:"
  docker compose exec -T db psql -U situationroom -d situationroom -c "select count(*) as tle_rows, max(fetched_at) as latest from satellite_tles;" || true
  exit 1
fi

echo "[step9] PASS: satellite rows=$SAT_ROWS"
