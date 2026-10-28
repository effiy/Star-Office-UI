#!/usr/bin/env python3
"""
DS Bot 实时状态监控守护进程

直接从 DSH 的 inflight.json 读取正在运行的 bot turn，
实时推送到像素办公室 sync-bridge。

原理:
  /Users/yi/.dsh/bot/inflight.json  → turns 字段列出所有活跃 session
  /Users/yi/.dsh/bot/state.json     → bot 名称映射

每秒轮询 inflight.json，检测 bot 状态变化 → 立即推送。

架构:
  DSH inflight.json ──▶ ds_bot_watcher ──▶ sync-bridge (:19001) ──▶ Star-Office (:19000)
"""

import os, sys, time, json, signal, logging, atexit
from datetime import datetime
import requests

# ── 配置 ──────────────────────────────────────────────
DSH_DIR = os.path.expanduser("~/.dsh/bot")
INFLIGHT_FILE = os.path.join(DSH_DIR, "inflight.json")
STATE_FILE = os.path.join(DSH_DIR, "state.json")
BRIDGE_URL = "http://127.0.0.1:19001/state"
PID_FILE = "/tmp/ds-bot-watcher.pid"
LOG_FILE = "/tmp/ds-bot-watcher.log"

POLL_INTERVAL = 1.0  # 轮询间隔（秒）

# ── 日志 ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("watcher")

# ── Bot 映射表 ────────────────────────────────────────
bot_map = {}        # sessionId → name
prev_active = set() # 上一轮活跃的 bot 名


def load_bot_names():
    """从 state.json 加载 sessionId → bot name 映射"""
    global bot_map
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        bots = data.get("bots", {})
        bot_map = {}
        for sid, info in bots.items():
            name = info.get("name", sid[:8])
            bot_map[sid] = name
        log.info("📋 加载 %d 个 Bot 映射", len(bot_map))
    except Exception as e:
        log.error("加载 state.json 失败: %s", e)


def get_active_bots():
    """从 inflight.json 读取当前活跃的 bot（只返回已注册的）"""
    try:
        if not os.path.exists(INFLIGHT_FILE):
            return set()
        with open(INFLIGHT_FILE) as f:
            data = json.load(f)
        turns = data.get("turns", {})
        active = set()
        for session_id in turns:
            name = bot_map.get(session_id)
            if name:  # 只保留已映射的 bot，忽略未知 session
                active.add(name)
        return active
    except Exception as e:
        log.error("读取 inflight.json 失败: %s", e)
        return prev_active


def push_state(bot_name: str, state: str):
    """推送状态到 sync-bridge"""
    try:
        r = requests.post(BRIDGE_URL, json={"bot": bot_name, "state": state}, timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def cleanup():
    try: os.remove(PID_FILE)
    except: pass


def main():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(cleanup)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    load_bot_names()
    
    log.info("═══ DS Bot 实时状态监控 v1 ═══")
    log.info("监控文件: %s", INFLIGHT_FILE)
    log.info("推送目标: %s", BRIDGE_URL)
    log.info("轮询间隔: %.1fs", POLL_INTERVAL)

    global prev_active
    prev_active = set()
    heartbeat_counter = 0

    # 初始推送：所有 bot idle
    for name in set(bot_map.values()):
        push_state(name, "idle")
    log.info("初始状态: 全部 idle")

    while True:
        try:
            time.sleep(POLL_INTERVAL)
            heartbeat_counter += 1
            current = get_active_bots()

            # 新激活的 → executing
            for name in current - prev_active:
                if push_state(name, "executing"):
                    log.info("🔧 %s → executing", name)

            # 刚空闲的 → idle
            for name in prev_active - current:
                if push_state(name, "idle"):
                    log.info("🛋 %s → idle", name)

            # 每 15 秒心跳：重推所有活跃 bot 的状态，防止 bridge 离线误判
            if heartbeat_counter >= 15:
                heartbeat_counter = 0
                for name in current:
                    push_state(name, "executing")

            prev_active = current
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error("异常: %s", e)
            time.sleep(5)

    log.info("服务已停止")


if __name__ == "__main__":
    main()