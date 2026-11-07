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
BIND_HOST = os.environ.get("WS_BIND_HOST", "127.0.0.1")
BIND_PORT = int(os.environ.get("WS_BIND_PORT", "19002"))
INFLIGHT_FILE = os.path.expanduser(os.environ.get("DSH_INFLIGHT_FILE", "~/.dsh/bot/inflight.json"))
STATE_FILE = os.path.expanduser(os.environ.get("DSH_STATE_FILE", "~/.dsh/bot/state.json"))
BRIDGE_STATE_FILE = os.environ.get("BRIDGE_STATE_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "bridge-state.json"))
FLOOR_REGISTRY_FILE = os.environ.get("FLOOR_REGISTRY_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "floor-registry.json"))
POLL_INTERVAL = 0.5  # 500ms 轮询间隔
RELOAD_INTERVAL = 60  # 每 60s 重载 bot 名册
HEARTBEAT_INTERVAL = 30  # 每 30s 对所有客户端发 ping
DEFAULT_FLOOR = 2  # 未知 bot 默认楼层

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

# ── 楼层分配（从 floor-registry.json 加载，未知 bot 用 hash 兜底）──
FLOOR_NAMES = {1: "管理决策层", 2: "工程执行层", 3: "创意内容层"}
BOT_FLOOR = {}  # bot name → floor (1/2/3)
MAX_AGENTS = 50


def load_floor_registry():
    """从 floor-registry.json 加载楼层分配，未知 bot 用 hash 兜底"""
    global BOT_FLOOR, MAX_AGENTS
    try:
        if os.path.exists(FLOOR_REGISTRY_FILE):
            with open(FLOOR_REGISTRY_FILE) as f:
                registry = json.load(f)
            meta = registry.get("_meta", {})
            MAX_AGENTS = meta.get("max_agents", 50)
            DEFAULT_FLOOR_CAPTURED = meta.get("default_floor", 2)

            BOT_FLOOR = {}
            for floor_key, names in registry.items():
                if floor_key.startswith("_"):
                    continue
                try:
                    floor_num = int(floor_key[0])  # "1F" → 1
                except ValueError:
                    continue
                for name in names:
                    BOT_FLOOR[name] = floor_num
            log.info(f"📋 楼层注册表: {len(BOT_FLOOR)} 个 bot, 上限 {MAX_AGENTS}")
        else:
            log.warning(f"⚠️  floor-registry.json 不存在, 所有 bot 分配至 {DEFAULT_FLOOR}F")
    except Exception as e:
        log.error(f"加载 floor-registry.json 失败: {e}")


def get_floor(name: str) -> str:
    """获取 bot 楼层标签: 注册表优先 → 同名 hash 兜底 → 默认 2F"""
    global BOT_FLOOR
    num = BOT_FLOOR.get(name)
    if num is not None:
        return f"{num}F"
    # 用 bot 名 hash 分配楼层 (1-3)，保证同一 bot 始终同层
    h = abs(hash(name)) % 3 + 1
    BOT_FLOOR[name] = h
    return f"{h}F"


def get_floor_num(name: str) -> int:
    """获取楼层编号（用于统计分组）"""
    label = get_floor(name)
    try:
        return int(label[0])
    except (ValueError, IndexError):
        return 2


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


def compute_floor_summary(states):
    """统计各楼层活跃数"""
    summary = {1: 0, 2: 0, 3: 0}
    for name, info in states.items():
        f = get_floor_num(name)
        if f and info.get("state") != "idle":
            summary[f] = summary.get(f, 0) + 1
    return summary


async def handler(websocket):
    """WebSocket 连接处理"""
    connected_clients.add(websocket)
    remote = websocket.remote_address
    log.info(f"客户端连接: {remote} (共 {len(connected_clients)} 个)")

    try:
        # 发送当前状态快照（含楼层）
        snapshot = get_state_snapshot()
        # 加 floor 信息
        for name in snapshot:
            snapshot[name]["floor"] = get_floor(name)
        await websocket.send(json.dumps({
            "type": "snapshot",
            "bots": snapshot,
            "floor_summary": compute_floor_summary(snapshot),
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
    global prev_active, last_inflight_mtime, bot_map

    tick = 0

    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL)
            tick += 1

            # ── 周期重载 bot 名册（新增 bot 自动发现）──
            if tick % int(RELOAD_INTERVAL / POLL_INTERVAL) == 0:
                load_bot_names()

            # ── 周期心跳 ──
            if connected_clients and tick % int(HEARTBEAT_INTERVAL / POLL_INTERVAL) == 0:
                log.debug(f"心跳: {len(connected_clients)} 个客户端, {len(bot_map)} 个 bot")
                disconnected = set()
                for ws in connected_clients:
                    try:
                        await ws.send(json.dumps({"type": "ping", "ts": datetime.now().isoformat()}))
                    except Exception:
                        disconnected.add(ws)
                connected_clients.difference_update(disconnected)

            current = get_active_bots()
            if current == prev_active:
                continue  # 无变化

            # 构建变化通知（含楼层信息）
            changed = {}
            for name in current - prev_active:
                floor = get_floor(name)
                changed[name] = {"state": "executing", "floor": floor}
            for name in prev_active - current:
                floor = get_floor(name)
                changed[name] = {"state": "idle", "floor": floor}

            if not changed:
                continue

            # 统计各楼层活跃数
            all_states = get_state_snapshot()
            floor_active = compute_floor_summary(all_states)

            log.info(f"状态变化: {len(changed)} 个 bot — " +
                     ", ".join(f"{n}→{i['state']}" for n, i in changed.items()))

            message = json.dumps({
                "type": "state_change",
                "changes": changed,
                "floor_summary": floor_active,
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
    load_floor_registry()
    load_bot_names()
    log.info(f"═══ WebSocket 实时推送服务 :{BIND_PORT} ═══")
    log.info(f"绑定: {BIND_HOST}:{BIND_PORT}")
    log.info(f"监控: {INFLIGHT_FILE}")
    log.info(f"轮询: {POLL_INTERVAL}s | 重载: {RELOAD_INTERVAL}s | 心跳: {HEARTBEAT_INTERVAL}s")

    if not os.path.exists(INFLIGHT_FILE):
        log.warning(f"⚠️  inflight.json 不存在 ({INFLIGHT_FILE})，DSH 可能未运行")
        log.warning("   WebSocket 服务将继续运行，使用 bridge-state.json 提供状态")

    if os.path.exists(BRIDGE_STATE_FILE):
        try:
            with open(BRIDGE_STATE_FILE) as f:
                bridge_bots = list(json.load(f).keys())
            log.info(f"📋 bridge-state 中已注册: {bridge_bots}")
        except Exception as e:
            log.warning(f"⚠️  bridge-state.json 读取失败: {e}")

    # 优雅退出: SIGTERM/SIGINT → 关闭 WebSocket 服务
    shutdown_event = asyncio.Event()

    def _signal_handler():
        log.info("收到终止信号，正在关闭...")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass  # Windows 不支持 add_signal_handler

    # 并行运行: WebSocket 服务器 + 广播循环
    async with websockets.serve(handler, BIND_HOST, BIND_PORT):
        broadcast_task = asyncio.create_task(broadcast_updates())
        await shutdown_event.wait()
        broadcast_task.cancel()
        try:
            await broadcast_task
        except asyncio.CancelledError:
            pass
        log.info(f"WebSocket 服务已关闭 ({len(connected_clients)} 个客户端断开)")


if __name__ == "__main__":
    asyncio.run(main())