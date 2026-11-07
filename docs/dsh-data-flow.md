# DSH ↔ Star-Office 数据打通架构

> **日期**: 2026-11-07  
> **负责**: SU·后端·铸舰  
> **状态**: ✅ 核心已完成，持续优化

---

## 一、数据流全景

```
┌─────────────────────────────────────────────────────────────────┐
│                        YiAi DSH 系统                            │
│                                                                 │
│  ~/.dsh/bot/state.json     ← 全量 Bot 状态（名称、分段）       │
│  ~/.dsh/bot/inflight.json  ← 当前活跃 turn（执行中）            │
└───────────────┬─────────────────────────┬───────────────────────┘
                │ 读文件                   │ 读文件
                ▼                          ▼
┌───────────────────────┐   ┌─────────────────────────────────────┐
│  ws_server.py (:19002)│   │  backend/dsh_server.py (:19003)      │
│                       │   │                                     │
│  500ms 轮询            │   │  3s 轮询                            │
│  ► 读 inflight.json   │   │  ► state_reader 模块                │
│  ► 广播 WebSocket     │   │  ► agent_mapper 映射                │
│  ► 心跳 30s           │   │  ► state_pusher → :19000            │
└───────────────────────┘   └──────────────┬──────────────────────┘
                                           │ HTTP POST /agent-push
                                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  backend/app.py (:19000) — FastAPI 主应用                        │
│                                                                  │
│  POST /agent-push   ← 接收 DSH bridge 推送的 bot 状态            │
│  POST /set_state    ← 接收 Chief 状态推送                        │
│  GET /ds-bot-states ← 合并 agents-state.json + bridge-state.json │
│                                                                  │
│  存储: backend/store_redis.py                                    │
│  ┌─ Redis (star:* 命名空间)                                      │
│  ├─ FakeRedis (STAR_USE_FAKEREDIS=1 开发模式)                    │
│  └─ JSON 文件 (自动降级)                                         │
└──────────────────────────────────────────────────────────────────┘
```

## 二、组件清单

| 组件 | 路径 | 端口 | 框架 | 职责 | 状态 |
|------|------|:---:|------|------|:---:|
| 主应用 | `backend/app.py` | :19000 | FastAPI | 45 路由，状态管理，资产管理 | ✅ v2 |
| DSH Bridge | `backend/dsh_server.py` | :19003 | FastAPI | 轮询 DSH → 推送主应用 | ✅ v2 |
| WebSocket | `ws_server.py` | :19002 | aiohttp/websockets | 实时 bot 状态广播 | ✅ v1 |
| Sync Bridge | `sync_bridge.py` | :19001 | Flask | 旧版桥接（由 ds_bot_watcher 驱动） | ⚠️ 待收敛 |
| Bot Watcher | `ds_bot_watcher.py` | — | 守护进程 | 1s 轮询 inflight → sync-bridge | ⚠️ 待收敛 |
| 独立桥接 | `backend/dsh_bridge.py` | — | 独立进程 | 3s 轮询 DSH → :19000 | ⚠️ 已废弃 |

### 收敛计划

| 组件 | 操作 | 原因 |
|------|------|------|
| `backend/dsh_bridge.py` | 🗑 标记废弃 | 与 dsh_server 功能重叠，单进程轮询无 HTTP API |
| `ds_bot_watcher.py` | 🗑 待评估 | 功能可由 ws_server 的 inflight monitoring 替代 |
| `sync_bridge.py` | 🗑 待评估 | ds_bot_watcher 的接收端，watcher 废弃后随之废弃 |
| `backend/dsh_server.py` | ⭐ 唯一桥接 | FastAPI + 可配置轮询间隔 + HTTP API |

## 三、数据模型

### DSH 原始数据

**state.json** — bot 名称和分段信息：
```json
{
  "bots": {
    "bot-abc": {
      "name": "软件工程师",
      "segments": [{"startedAt": "...", "endedAt": "active", "kind": "..."}]
    }
  }
}
```

**inflight.json** — 正在执行的 turn：
```json
{
  "turns": {
    "turn-1": {"botId": "bot-abc", "botName": "软件工程师", "status": "running"}
  }
}
```

### 状态推断规则（state_reader.py）

| inflight.json 中有 active turn? | state.json segments 最后一项未结束? | 推断状态 |
|:---:|:---:|------|
| ✅ | — | `executing` |
| ❌ | ✅ | `writing` |
| ❌ | ❌ | `idle` |

### 桥接输出（dsh_server → app.py）

```json
POST /agent-push
{
  "agentId": "agent-uuid",
  "joinKey": "...",
  "state": "executing",
  "detail": "工作中…",
  "name": "软件工程师"
}
```

### 合并输出（app.py /ds-bot-states）

app.py 的 `/ds-bot-states` 合并两个数据源：
1. `agents-state.json` — 本地注册的 agent 信息
2. `bridge-state.json` — DSH bridge 推送的最新状态（优先级更高）

```json
GET /ds-bot-states
{
  "bots": {
    "软件工程师": {"state": "executing", "detail": "工作中…", "updatedAt": "..."}
  },
  "count": 17,
  "updated_at": "2026-11-07T00:30:00Z"
}
```

## 四、环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BRIDGE_PORT` | `19003` | DSH Bridge 监听端口 |
| `DSH_POLL_INTERVAL` | `3` | 轮询间隔（秒） |
| `DSH_STATE_FILE` | `~/.dsh/bot/state.json` | DSH 状态文件路径 |
| `DSH_INFLIGHT_FILE` | `~/.dsh/bot/inflight.json` | DSH inflight 文件路径 |

## 五、启动命令

```bash
# 主应用
STAR_USE_FAKEREDIS=1 python -m uvicorn backend.app:app --host 0.0.0.0 --port 19000

# DSH Bridge  
python -m uvicorn backend.dsh_server:app --host 127.0.0.1 --port 19003

# WebSocket
python ws_server.py  # 默认 :19002
```

## 六、专业度提升要点

| 维度 | 现状 | 改进 |
|------|------|------|
| 框架统一 | app.py FastAPI, dsh_server.py 刚转 FastAPI | ✅ 统一 FastAPI |
| 数据模型 | 字典直传，无类型约束 | ✅ Pydantic models (`dsh_models.py`) |
| 轮询收敛 | 4 个独立轮询循环 | 🔄 计划收敛到 2 个（ws_server + dsh_server） |
| 错误处理 | try/except + log.exception | ✅ 已有，可加 Sentry/钉钉告警 |
| 可观测性 | 日志 | 📋 待加 Prometheus metrics |
| WebSocket | 500ms 轮询 inflight | ✅ 已是推送，但数据源仍是文件轮询 |
| 文档 | 零 | ✅ 本文档 + 代码注释 |

## 七、风险清单

| 风险 | 等级 | 缓解 |
|------|:---:|------|
| DSH 文件不存在 | 🟡 中 | 优雅降级，日志警告，继续轮询 |
| state.json 格式变化 | 🟡 中 | `_read_json` 容错返回 `{}`；Pydantic 模型可验证 |
| Bridge 进程崩溃 | 🟢 低 | systemd/launchd 自动重启 |
| 多轮询重复推送 | 🟢 低 | `/agent-push` 幂等（同一状态不触发变更） |
| Redis 不可用 | 🟢 低 | 三级降级（Redis→FakeRedis→JSON） |

---

*本文档随架构演进持续更新。最后更新: 2026-11-07*