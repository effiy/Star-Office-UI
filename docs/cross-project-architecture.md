# Star-Office-UI 跨项目数据打通架构方案

> **日期**: 2026-11-07  
> **负责**: SU·后端·铸舰  
> **状态**: 📋 方案阶段

---

## 一、三系统全景

### 1.1 系统清单

| 系统 | 角色 | 技术栈 | 端口 | 数据存储 |
|------|------|--------|:---:|------|
| **DSH** | Bot 运行时 | DeepSeek Harness | — | `~/.dsh/bot/state.json` + `inflight.json` |
| **YiAi** | 后端 API + 知识管理 | FastAPI + MongoDB | :10086 | MongoDB `ruiyi` |
| **YiVad** | 前端管理面板 | Vue3 + Vite + Phaser | dev :5173 | — |
| **Star-Office-UI** | 像素办公室可视化 | FastAPI + Redis | :19000 | Redis `star:*` + JSON |

### 1.2 当前数据流（痛点多桥并行）

```
                        DSH (state.json + inflight.json)
                         │
          ┌──────────────┼──────────────────┐
          ▼              ▼                  ▼
   launchd bridge   dsh_server         ws_server
   (30s tick)       (3s poll)          (500ms poll)
        │              │                  │
        ▼              ▼                  ▼
  .ds-bot-states.json  app.py :19000   WebSocket :19002
        │              │                  │
        ▼              ▼                  ▼
  YiAi /read-file   agents-state      StarOffice
        │            .json             frontend
        ▼
  YiVad botStatusService
```

**痛点**：
- 3 个独立轮询器竞争同一组文件
- DSH 数据 3 份副本（.ds-bot-states.json / agents-state.json / ws 内存），格式不一致
- YiVad 和 StarOffice 互不知对方存在
- YiAi 的角色/知识/仪表盘数据 StarOffice 完全消费不到

---

## 二、目标架构：单一真相源

### 2.1 数据主权分配

```
DSH 权威:  Bot 实时状态 (executing/writing/idle)
YiAi 权威: Bot 角色定义、知识库、项目指标
StarOffice 权威: 像素办公室可视化状态（位置/动画/交互）
```

### 2.2 统一数据流

```
DSH (state.json/inflight.json)
        │
        ▼
┌─ StarOffice dsh_server (:19003) — 3s 轮询 ──────────────┐
│                                                          │
│  state_reader.py → agent_mapper.py → state_pusher.py    │
│                                                          │
│  单一路径、统一数据模型 (Pydantic dsh_models.py)         │
└────────────────────────┬─────────────────────────────────┘
                         │ POST /agent-push
                         ▼
┌─ StarOffice app.py (:19000) FastAPI ─────────────────────┐
│                                                          │
│  Redis (star:* ns): agents, states, assets, config       │
│                                                          │
│  开放 API:                                               │
│  GET  /api/v2/bot-states   → YiVad/YiAi 统一 bot 状态   │
│  GET  /api/v2/office/view  → 办公室可视化数据            │
│  GET  /api/v2/yi-ai/roles  → 从 YiAi 拉取角色元数据      │
│  GET  /api/v2/yi-ai/metrics → 从 YiAi 拉取仪表盘指标     │
│  GET  /health               → 含跨系统连通性             │
└──────────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
    WebSocket            HTTP API
    (:19002)        YiAi ← YiVad (统一数据契约)
    StarOffice
    frontend
```

### 2.3 关键改进

| 维度 | 现状 | 目标 |
|------|------|------|
| DSH 桥接 | 3 个独立轮询器 | 1 个 dsh_server，统一数据模型 |
| 数据契约 | 无类型，格式分散 | Pydantic 模型 (`dsh_models.py`) |
| YiAi 集成 | ❌ 零集成 | 消费 /roles，/dashboard/live |
| YiVad 集成 | ❌ 零集成 | 暴露 /api/v2/bot-states（替代 .ds-bot-states.json 桥接） |
| 跨系统健康 | 各自健康 | StarOffice /health 聚合 DSH+YiAi 连通性 |
| 会话互通 | ❌ 不互通 | YiAi /bridge/* token 机制复用 |

---

## 三、API 契约

### 3.1 StarOffice → YiVad/YiAi 暴露的新端点

#### `GET /api/v2/bot-states`

```json
{
  "bots": {
    "Chief": {
      "botId": "session-78a256cd-...",
      "name": "Chief",
      "state": "idle",
      "detail": "待命中",
      "floor": "1F",
      "role": {"name": "Chief", "domain": "管理决策", "status": "active"},
      "updatedAt": "2026-11-07T00:30:00Z"
    }
  },
  "count": 50,
  "source": "dsh-bridge+redis",
  "yiAiAvailable": true,
  "updated_at": "2026-11-07T00:30:00Z"
}
```

> 替代当前 YiVad botStatusService 读取 `.ds-bot-states.json` 的路径。  
> botStatusService 只需改 `BRIDGE_FILE` → `fetch(":19000/api/v2/bot-states")`。

#### `GET /api/v2/yi-ai/roles`

```json
{
  "roles": [
    {"name": "SU·后端·铸舰", "domain": "后端迁移", "status": "active", "file_count": 4}
  ],
  "count": 28,
  "source": "yi-ai /roles-sync"
}
```

#### `GET /api/v2/yi-ai/metrics`

```json
{
  "active_issues": 12, "open_bugs": 3, "today_done": 5,
  "blocked_count": 1, "overdue_count": 2
}
```

### 3.2 StarOffice ← YiAi 消费

| YiAi 端点 | 用途 | StarOffice 消费位置 |
|------|------|------|
| `POST /roles-sync` | Bot 角色元数据 | agent 卡片展示角色名/领域/状态 |
| `GET /dashboard/live-snapshot` | 实时指标 | 办公室大屏数据面板 |
| `GET /health/live` | 健康检查 | `/health` 聚合跨系统连通性 |
| `POST /bridge/create-token` | 会话转移 | 从 YiVad 跳转到 StarOffice 时带 token |

---

## 四、实施路线

### Phase 1: 基础打通（本轮）

| 任务 | 交付物 | 状态 |
|------|------|:---:|
| YiAi HTTP Client | `backend/yi_ai_client.py` | ✅ |
| 跨项目数据模型 | `backend/dsh_models.py`（已扩展） | ✅ |
| 架构方案文档 | `docs/cross-project-architecture.md` | ✅ 本文档 |
| dsh_server Flask→FastAPI | `backend/dsh_server.py` | ✅ |
| /health 聚合 YiAi 连通性 | app.py 修改 | 📋 待实施 |

### Phase 2: API 统一（下轮）

| 任务 | 说明 |
|------|------|
| `GET /api/v2/bot-states` | 统一 DSH bot 状态输出，替代 .ds-bot-states.json |
| `GET /api/v2/yi-ai/roles` | 代理 YiAi 角色数据，含缓存 |
| `GET /api/v2/yi-ai/metrics` | 代理 YiAi 仪表盘指标 |

### Phase 3: 深度集成（远期）

| 任务 | 说明 |
|------|------|
| DSH 桥接收敛 | ds_bot_watcher + dsh_bridge → 仅 dsh_server |
| YiVad botStatusService 切换 | 从 .ds-bot-states.json 改为调用 StarOffice API |
| 会话互通 | YiAi /bridge/* token → 跨项目导航 |
| 统一 WebSocket | StarOffice ws_server 同时服务 YiVad 和 StarOffice 前端 |

---

## 五、数据模型对齐

### 5.1 Bot 状态（三系统共享）

| 字段 | DSH | StarOffice | YiVad (期望) |
|------|-----|------------|-------------|
| `botId` | session id | agentId | botId |
| `name` | bot.name | name | name |
| `state` | executing/writing/idle | same | same |
| `detail` | — | STATE_LABELS | detail |
| `floor` | — | `"1F"/"2F"/"3F"` | floor |
| `role.domain` | — | from YiAi | role |

### 5.2 对齐要点

- **YiVad `DshBotStatus.botId`** = **StarOffice `agent.agentId`** = **DSH `bot.botId`**
- **状态枚举**: 三系统统一用 `executing | writing | idle | error | offline`（YiVad 已有 5 态 Badge）
- **时间戳**: ISO 8601 UTC (`2026-11-07T00:30:00Z`)

---

## 六、风险与缓解

| 风险 | 等级 | 缓解 |
|------|:---:|------|
| YiAi 不可达 | 🟡 | 优雅降级，StarOffice 本地角色缓存 |
| DSH 文件格式变化 | 🟡 | Pydantic 容错解析 + 日志告警 |
| 多系统时钟偏差 | 🟢 | 统一 `updatedAt` 来源 |
| API 兼容性 | 🟢 | v2 端点独立于 v1，零破坏 |

---

*本文档随实施进展持续更新。最后更新: 2026-11-07*