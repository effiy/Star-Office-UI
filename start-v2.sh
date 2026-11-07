#!/usr/bin/env bash
# Star-Office-UI v2 服务启动脚本
# T2 architecture: 2 processes instead of 4
#   ws-server (WebSocket, :19002) + main-app (FastAPI + collector, :19000)
# Legacy :19001 (sync_bridge) + :19003 (dsh_server) retired — merged into collector.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Auto-load project env file when present.
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  source "$ROOT_DIR/.env"
  set +a
fi

VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
PID_DIR="${PID_DIR:-/tmp/star-office-v2}"
mkdir -p "$PID_DIR"

echo "═══════════════════════════════════════════"
echo "  Star-Office-UI v2 服务启动"
echo "═══════════════════════════════════════════"

# ── 1. WebSocket 实时推送 (port 19002) ──
echo ""
echo "▶ ws-server (:19002) [SU-01 WebSocket]"
if [ -f "$PID_DIR/ws-server.pid" ] && kill -0 "$(cat "$PID_DIR/ws-server.pid")" 2>/dev/null; then
  echo "  已在运行 (PID $(cat "$PID_DIR/ws-server.pid"))"
else
  nohup "$VENV_PYTHON" "$ROOT_DIR/ws_server.py" > /tmp/star-ws-server.log 2>&1 &
  echo $! > "$PID_DIR/ws-server.pid"
  echo "  已启动 (PID $!)"
fi

# ── 2. 主应用 (port 19000) + Collector (DSH watchdog) ──
echo ""
echo "▶ main-app (:19000) [FastAPI + DSH Collector]"
echo "   Collector: watchdog DSH → Redis PUBLISH (replaces :19001/:19003)"
"$VENV_PYTHON" "$ROOT_DIR/backend/app.py"
# 主应用前台运行，Ctrl+C 后执行清理