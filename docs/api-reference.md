# Star-Office-UI API 参考 (v2)

> 📡 三端口架构 · 电梯原则：图 > 表格 > 图标 > 文本

```
┌─────────────────────────────────────────────────┐
│  端口 19000 ──── 🏠 看板                         │
│  GET  /                  办公室主视图            │
│  GET  /office/floor/{n}  楼层 n 视图            │
│  POST /agent-push        Agent 推送状态          │
│  GET  /agents            Agent 列表             │
│  POST /join-agent        加入办公室              │
│  GET  /yesterday-memo     昨日小记               │
├─────────────────────────────────────────────────┤
│  端口 19001 ──── 🔌 Bridge (sync-bridge)         │
│  POST /state             Bot 推送状态            │
│  GET  /state             获取所有 Bot 状态       │
├─────────────────────────────────────────────────┤
│  端口 19002 ──── 📡 DSH API (dsh_server)         │
│  GET  /ds-bot-states     DSH Bot 状态摘要        │
└─────────────────────────────────────────────────┘
```

---

## `GET /ds-bot-states`

> 📡 端口 **19002** · 返回所有已注册 DSH Bot 的当前状态

**请求**

```
GET /ds-bot-states
GET /ds-bot-states?state=executing
```

**响应** `200 OK`

```json
{
  "bots": [
    {
      "name": "知识管理者",
      "state": "idle",
      "last_seen": "2026-10-28T22:00:00Z",
      "agent_id": "curator"
    },
    {
      "name": "Git管家",
      "state": "executing",
      "last_seen": "2026-10-28T22:05:00Z",
      "agent_id": "git-manager"
    }
  ],
  "count": 16,
  "updated_at": "2026-10-28T22:05:03Z"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `bots[].name` | string | Bot 名称 |
| `bots[].state` | enum | `idle` \| `executing` \| `writing` \| `researching` \| `syncing` \| `error` |
| `bots[].last_seen` | ISO 8601 | 最后活跃时间 |
| `bots[].agent_id` | string | DSH Agent ID |
| `count` | number | Bot 总数 |
| `updated_at` | ISO 8601 | 数据刷新时间 |

**查询参数**

| 参数 | 示例 | 说明 |
|------|------|------|
| `state` | `?state=executing` | 按状态过滤——只看工作中的 Bot |

**错误**

| 状态码 | 含义 |
|:---:|------|
| `503` | DSH 服务不可达——inflight.json 读取失败 |

---

## `GET /office/floor/{n}`

> 🏠 端口 **19000** · 获取指定楼层的办公室视图（v2 新增）

**请求**

```
GET /office/floor/1
GET /office/floor/2?view=workstation
```

**响应** `200 OK`

```json
{
  "floor": 1,
  "name": "DSH Bot 团队 · 日常办公室",
  "rooms": [
    {
      "id": "workstation",
      "name": "工作区",
      "agents": [
        {"name": "Git管家", "state": "executing", "x": 320, "y": 180},
        {"name": "Readme管家", "state": "executing", "x": 480, "y": 180}
      ],
      "capacity": 8,
      "occupied": 2
    },
    {
      "id": "breakroom",
      "name": "休息区",
      "agents": [
        {"name": "知识管理者", "state": "idle", "x": 160, "y": 320}
      ],
      "capacity": 4,
      "occupied": 1
    },
    {
      "id": "bugzone",
      "name": "Bug 区",
      "agents": [],
      "capacity": 4,
      "occupied": 0
    }
  ],
  "total_agents": 3
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `floor` | number | 楼层编号 |
| `name` | string | 楼层名称 |
| `rooms[]` | array | 该楼层的办公室区域 |
| `rooms[].agents[]` | array | 区域内 Agent 列表 |
| `rooms[].capacity` | number | 区域容量上限 |
| `rooms[].occupied` | number | 当前占用数 |

**路径参数**

| 参数 | 示例 | 说明 |
|------|------|------|
| `{n}` | `1` `2` | 楼层编号——v2 最多支持 3 层 |

**查询参数**

| 参数 | 示例 | 说明 |
|------|------|------|
| `view` | `?view=workstation` | 只返回指定区域 |

**错误**

| 状态码 | 含义 |
|:---:|------|
| `404` | 楼层不存在——仅支持 1-3 |

---

## `POST /agent-push`

> 🏠 端口 **19000** · Agent 推送自己的状态到办公室看板

**请求**

```
POST /agent-push
Content-Type: application/json
```

```json
{
  "name": "Git管家",
  "state": "executing",
  "msg": "扫描 272 个仓库中",
  "key": "daily-standup-room"
}
```

| 字段 | 必需 | 说明 |
|------|:---:|------|
| `name` | ✅ | Agent 名称——须与注册名一致 |
| `state` | ✅ | `idle` \| `executing` \| `writing` \| `researching` \| `syncing` \| `error` |
| `msg` | ❌ | 状态描述——显示在气泡中 |
| `key` | ❌ | Join Key——多 Agent 共享办公室时使用 |

**响应** `200 OK`

```json
{
  "ok": true,
  "agent": "Git管家",
  "state": "executing",
  "area": "workstation",
  "changed": true
}
```

| 字段 | 说明 |
|------|------|
| `ok` | 推送是否成功 |
| `agent` | Agent 名称 |
| `state` | 当前状态 |
| `area` | 映射到的办公室区域 |
| `changed` | 状态是否发生了变化 |

**curl 示例**

```bash
# Bot 开始工作
curl -X POST http://127.0.0.1:19000/agent-push \
  -H "Content-Type: application/json" \
  -d '{"name":"Git管家","state":"executing","msg":"扫描仓库中"}'

# Bot 空闲
curl -X POST http://127.0.0.1:19000/agent-push \
  -H "Content-Type: application/json" \
  -d '{"name":"Git管家","state":"idle","msg":"待命中"}'
```

**错误**

| 状态码 | 说明 |
|:---:|------|
| `400` | `name` 或 `state` 缺失 |
| `400` | `state` 值不在 6 个有效枚举内 |
| `404` | Agent 未注册——先调用 `POST /join-agent` |

---

## 🗺️ 状态 → 区域映射

| state | 区域 | 动画 | 图标 |
|-------|------|------|:--:|
| `idle` | breakroom | 呼吸 | 🛋 |
| `executing` | workstation | 工具 | ⚙️ |
| `writing` | workstation | 打字 | ✍️ |
| `researching` | workstation | 搜索 | 🔍 |
| `syncing` | workstation | 同步 | 🔄 |
| `error` | bugzone | 抖动(红) | 🐛 |

---

## 🔌 DSH Bot 接入速查

```bash
# 1. 注册 Agent
curl -X POST http://127.0.0.1:19000/join-agent \
  -H "Content-Type: application/json" \
  -d '{"name":"你的Bot名","key":"daily-standup"}'

# 2. 推送状态
curl -X POST http://127.0.0.1:19000/agent-push \
  -H "Content-Type: application/json" \
  -d '{"name":"你的Bot名","state":"executing"}'

# 3. 查看状态
curl http://127.0.0.1:19002/ds-bot-states
```