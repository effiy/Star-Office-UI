#!/usr/bin/env python3
"""
多 Agent 状态同步桥接服务 v2

架构:
  任意 DS Bot ──POST /state──▶ sync-bridge (:19001) ──▶ Star-Office-UI (:19000)
                  {"bot":"Git管家",            /set_state (Chief)
                   "state":"executing"}        /agent-push (其他 bot)

功能:
  - HTTP 回调: POST /state {"bot":"...", "state":"..."}
  - 自动发现: 从 /agents API 获取所有 bot 的 agentId/joinKey
  - 离线检测: 单 bot 超时未回调 → 标记 idle
  - 健康检查: GET /health 列出所有 bot 状态
  - PID 管理: /tmp/chief-sync-bridge.pid
"""

import os, sys, time, json, signal, logging, atexit
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# ── 配置 ──────────────────────────────────────────────
BIND_HOST, BIND_PORT = "127.0.0.1", 19001
STAR_OFFICE_URL = "http://127.0.0.1:19000"
JOIN_KEY = "ocj_example_team_01"
BRIDGE_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bridge-state.json")
PID_FILE = "/tmp/chief-sync-bridge.pid"
LOG_FILE = "/tmp/chief-sync-bridge.log"
OFFLINE_TIMEOUT = 30
POLL_INTERVAL = 3
DISCOVERY_INTERVAL = 60  # 每 60s 重新发现 agent

STATE_MAP = {
    "idle": "idle", "writing": "writing", "executing": "executing",
    "researching": "researching", "syncing": "syncing", "error": "error",
}

# ── 日志 ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-5s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("sync-bridge")

# ── Bot 注册表 ────────────────────────────────────────
bot_registry = {}     # name → {agentId, joinKey, lastState, lastCallback}
last_discovery = 0


def discover_agents():
    """从 Star-Office-UI /agents API 发现所有 bot"""
    global bot_registry, last_discovery
    try:
        r = requests.get(f"{STAR_OFFICE_URL}/agents", timeout=3)
        agents = r.json()
        for a in agents:
            name = a["name"]
            entry = bot_registry.get(name, {})
            entry["agentId"] = a["agentId"]
            entry["joinKey"] = a.get("joinKey") or JOIN_KEY
            entry["isMain"] = a.get("isMain", False)
            entry.setdefault("lastState", "idle")
            entry.setdefault("lastCallback", 0)
            bot_registry[name] = entry
        last_discovery = time.time()
        log.info("🔍 发现 %d 个 Agent", len(bot_registry))
    except Exception as e:
        log.error("Agent 发现失败: %s", e)


def push_agent_state(name: str, state: str, detail: str = "", source: str = "unknown"):
    """推送单个 Agent 状态到 Star-Office-UI"""
    entry = bot_registry.get(name)
    if not entry:
        log.warning("未知 Bot: %s", name)
        return False

    state = STATE_MAP.get(state, "idle")
    # 心跳：callback 收到就刷新时间，防止离线误判
    if source == "callback":
        entry["lastCallback"] = time.time()
    if state == entry.get("lastState"):
        return False

    try:
        if entry.get("isMain"):
            # 主 Agent: 使用 /set_state
            r = requests.post(f"{STAR_OFFICE_URL}/set_state",
                json={"state": state, "detail": detail or name}, timeout=3)
        else:
            # 访客 Agent: 使用 /agent-push
            r = requests.post(f"{STAR_OFFICE_URL}/agent-push",
                json={
                    "agentId": entry["agentId"],
                    "joinKey": entry["joinKey"],
                    "state": state,
                    "detail": detail or "",
                    "name": name,
                }, timeout=3)

        if r.status_code == 200:
            emoji = {"idle":"🛋","writing":"💻","executing":"🔧","error":"🐛"}.get(state,"❓")
            log.info("%s %-12s → %-10s (via %s)", emoji, name, state, source)
            entry["lastState"] = state
            entry["lastDetail"] = detail or ""
            if source == "callback":
                entry["lastCallback"] = time.time()
            save_bridge_state()
            return True
    except Exception as e:
        log.error("%s 推送失败: %s", name, e)
    return False


def save_bridge_state():
    """保存当前所有 bot 状态到共享文件，供 Flask /ds-bot-states 读取"""
    try:
        snapshot = {}
        for name, entry in bot_registry.items():
            snapshot[name] = {
                "state": entry.get("lastState", "idle"),
                "detail": entry.get("lastDetail", ""),
            }
        with open(BRIDGE_STATE_FILE, "w") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("保存 bridge-state.json 失败: %s", e)


def check_offline_all():
    """检测所有 Bot 是否离线"""
    now = time.time()
    for name, entry in bot_registry.items():
        if entry["lastCallback"] == 0:
            continue
        age = now - entry["lastCallback"]
        if age > OFFLINE_TIMEOUT and entry.get("lastState") != "idle":
            log.warning("⚠️  %s 离线 %.0fs，回退 idle", name, age)
            entry["lastState"] = None  # force push
            push_agent_state(name, "idle", f"离线 {int(age)}s", source="offline")


# ── HTTP ──────────────────────────────────────────────
class StateHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/state":
            self.send_error(404); return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
        except Exception:
            self.send_error(400, "Invalid JSON"); return

        bot = (data.get("bot") or data.get("name") or "Chief").strip()
        state = (data.get("state") or "idle").strip().lower()

        if state not in STATE_MAP:
            self.send_error(400, f"Invalid state: {state}"); return

        changed = push_agent_state(bot, state, source="callback")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "bot": bot, "state": state, "changed": changed}).encode())

    def do_GET(self):
        if self.path == "/health":
            bots = []
            for name, e in bot_registry.items():
                age = time.time() - e["lastCallback"] if e["lastCallback"] else 0
                bots.append({"name": name, "state": e.get("lastState","?"), "lastSeenSec": round(age,1)})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "bots": bots, "total": len(bots)}).encode())
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        log.debug("HTTP %s", format % args)


# ── 生命周期 ──────────────────────────────────────────
def cleanup():
    try: os.remove(PID_FILE)
    except: pass

def main():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(cleanup)

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    discover_agents()

    server = HTTPServer((BIND_HOST, BIND_PORT), StateHandler)
    log.info("═══ 多 Agent 状态同步桥接 v2 ═══")
    log.info("HTTP: http://%s:%d/state (POST)", BIND_HOST, BIND_PORT)
    log.info("发现 %d 个 Agent", len(bot_registry))

    import threading
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        while True:
            time.sleep(POLL_INTERVAL)
            check_offline_all()
            if time.time() - last_discovery > DISCOVERY_INTERVAL:
                discover_agents()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        log.info("服务已停止")

if __name__ == "__main__":
    main()