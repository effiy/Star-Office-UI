#!/usr/bin/env python3
"""
Star-Office-UI WebSocket 实时推送服务器

监听 DSH inflight.json 变化，通过 WebSocket 主动推送 bot 状态到所有连接的前端。

端口: 19002
协议: ws://127.0.0.1:19002

推送格式:
  {"type": "state_update", "bots": {"Chief": {"state":"executing",...}, ...}, "timestamp":"..."}
"""

import asyncio
import json
import os
import sys
import time
import signal
import logging
from datetime import datetime

import websockets

# ── 配置 ──────────────────────────────────────────────
BIND_HOST = "127.0.0.1"
BIND_PORT = 19002
INFLIGHT_FILE = os.path.expanduser("~/.dsh/bot/inflight.json")
STATE_FILE = os.path.expanduser("~/.dsh/bot/state.json")
BRIDGE_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bridge-state.json")
POLL_INTERVAL = 0.5  # 500ms 轮询间隔

# ── 日志 ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  WS  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ws-server")

# ── 全局状态 ──────────────────────────────────────────
connected_clients = set()
last_inflight_mtime = 0
bot_map = {}  # sessionId → name
prev_active = set()


def load_bot_names():
    global bot_map
    try:
        if not os.path.exists(STATE_FILE):
            return
        with open(STATE_FILE) as f:
            data = json.load(f)
        bot_map = {}
        for sid, info in data.get("bots", {}).items():
            name = info.get("name", sid[:8])
            bot_map[sid] = name
    except Exception as e:
        log.error(f"加载 state.json 失败: {e}")


def get_active_bots():
    """从 inflight.json 读取活跃 bot"""
    try:
        if not os.path.exists(INFLIGHT_FILE):
            return set()
        with open(INFLIGHT_FILE) as f:
            data = json.load(f)
        turns = data.get("turns", {})
        active = set()
        for sid in turns:
            name = bot_map.get(sid)
            if name:
                active.add(name)
        return active
    except Exception:
        return set()


def get_state_snapshot():
    """获取完整状态快照（bridge-state.json 优先）"""
    states = {}
    # bridge 数据最实时
    if os.path.exists(BRIDGE_STATE_FILE):
        try:
            with open(BRIDGE_STATE_FILE) as f:
                states = json.load(f)
        except Exception:
            pass

    # 补充 inflight 数据
    active = get_active_bots()
    for name in active:
        if name not in states:
            states[name] = {"state": "executing", "detail": ""}
        elif states[name].get("state") == "idle":
            states[name]["state"] = "executing"

    return states


async def handler(websocket):
    """WebSocket 连接处理"""
    connected_clients.add(websocket)
    remote = websocket.remote_address
    log.info(f"客户端连接: {remote} (共 {len(connected_clients)} 个)")

    try:
        # 发送当前状态快照
        snapshot = get_state_snapshot()
        await websocket.send(json.dumps({
            "type": "snapshot",
            "bots": snapshot,
            "timestamp": datetime.now().isoformat(),
        }, ensure_ascii=False))

        # 保持连接，等待客户端消息
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("type") == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))
            except Exception:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)
        log.info(f"客户端断开: {remote} (剩 {len(connected_clients)} 个)")


async def broadcast_updates():
    """轮询 inflight.json 并广播状态变化"""
    global prev_active, last_inflight_mtime

    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL)

            current = get_active_bots()
            if current == prev_active:
                continue  # 无变化

            # 构建变化通知
            changed = {}
            for name in current - prev_active:
                changed[name] = "executing"
            for name in prev_active - current:
                changed[name] = "idle"

            if not changed:
                continue

            message = json.dumps({
                "type": "state_change",
                "changes": changed,
                "timestamp": datetime.now().isoformat(),
            }, ensure_ascii=False)

            # 广播到所有客户端
            if connected_clients:
                disconnected = set()
                for ws in connected_clients:
                    try:
                        await ws.send(message)
                    except Exception:
                        disconnected.add(ws)
                connected_clients.difference_update(disconnected)

            prev_active = current
        except Exception as e:
            log.error(f"广播异常: {e}")
            await asyncio.sleep(5)


async def main():
    load_bot_names()
    log.info(f"═══ WebSocket 实时推送服务 :{BIND_PORT} ═══")
    log.info(f"监控: {INFLIGHT_FILE}")
    log.info(f"轮询: {POLL_INTERVAL}s")

    # 并行运行: WebSocket 服务器 + 广播循环
    async with websockets.serve(handler, BIND_HOST, BIND_PORT):
        await broadcast_updates()


if __name__ == "__main__":
    asyncio.run(main())