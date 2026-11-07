#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Auto-load project env file when present.
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

exec "$ROOT_DIR/.venv/bin/python" -m uvicorn backend.app:app --host 0.0.0.0 --port "${STAR_BACKEND_PORT:-19000}" --log-level info