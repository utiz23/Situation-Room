#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TARGET="${1:-all}"

echo "[prepush] target=$TARGET"

# Safety: secrets must never be tracked.
if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  echo "[prepush] FAIL: .env is tracked in git"
  exit 1
fi

if git diff --cached --name-only | grep -qx '.env'; then
  echo "[prepush] FAIL: .env is staged"
  exit 1
fi

case "$TARGET" in
  step8)
    scripts/check-step8.sh
    ;;
  step9)
    scripts/check-step9.sh
    ;;
  all)
    scripts/check-step8.sh
    scripts/check-step9.sh
    ;;
  *)
    echo "[prepush] FAIL: unknown target '$TARGET' (use: step8 | step9 | all)"
    exit 1
    ;;
esac

echo "[prepush] PASS"
