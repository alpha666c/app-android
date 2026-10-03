#!/usr/bin/env bash
# Run paper Viktor screen with an unlisted /p/<slug> URL (no password for Viktor).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/src"
export TRADING_MODE="${TRADING_MODE:-paper}"
export POLYSCOPE_HOST="${POLYSCOPE_HOST:-0.0.0.0}"
export POLYSCOPE_PORT="${POLYSCOPE_PORT:-8080}"
export POLYSCOPE_DB_PATH="${POLYSCOPE_DB_PATH:-${ROOT}/data/viktor-public.db}"
if [[ -z "${DASHBOARD_PASSWORD:-}" ]]; then
  echo "Set DASHBOARD_PASSWORD for operator dashboard (Viktor uses VIKTOR_PUBLIC_SLUG only)." >&2
  exit 1
fi
if [[ -z "${VIKTOR_PUBLIC_SLUG:-}" ]]; then
  echo "Set VIKTOR_PUBLIC_SLUG to a long random string (unlisted URL secret)." >&2
  exit 1
fi
mkdir -p "$(dirname "$POLYSCOPE_DB_PATH")"
exec python3 -m uvicorn polyscope.api.main:create_app --factory --host "$POLYSCOPE_HOST" --port "$POLYSCOPE_PORT"
