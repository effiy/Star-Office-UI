#!/usr/bin/env bash
# Star-Office-UI v2 服务停止脚本
set -euo pipefail

PID_DIR="${PID_DIR:-/tmp/star-office-v2}"

echo "═══════════════════════════════════════════"
echo "  Star-Office-UI v2 服务停止"
echo "═══════════════════════════════════════════"

stop_svc() {
  local name="$1" pid_file="$2"
  if [ -f "$pid_file" ]; then
    local pid
    pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      echo "✓ $name (PID $pid) 已停止"
    else
      echo "  $name (PID $pid) 已不在运行"
    fi
    rm -f "$pid_file"
  else
    echo "  $name 未找到 PID 文件"
  fi
}

stop_svc "ws-server     (:19002)" "$PID_DIR/ws-server.pid"

# main-app (:19000) 前台运行，Ctrl+C 停止（collector 随 lifespan 自动停止）

# 主应用通常前台运行，Ctrl+C 停止
echo ""
echo "完成"