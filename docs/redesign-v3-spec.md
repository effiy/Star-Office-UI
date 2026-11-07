# Star-Office-UI v3 重设计规格：YiAi × YiVad × DSH 三线数据打通

- 状态：**伞形架构 + 第二波权威**（第一波 Hub 实施以 `data-integration-spec.md` 为准，见 ADR-002 合一裁决）
- 日期：2026-11-07
- 作者：技术管家·哲思（TL）
- 触发：用户指令「按照你的理解重新设计下这个项目，需要打通 YiAi YiVad DSH 的数据及效果」
- 关联：ADR-001（DSH 数据直连）、docs/dsh-data-flow.md（铸舰）、SU-01~04 交付

---

## 1. 现状诊断：三系统数据面

### 1.1 已探明的事实

| 系统 | 角色 | 数据面 | 现有集成 |
|------|------|--------|----------|
| **DSH** (`~/.dsh/`) | Bot 运行时 | `bot/inflight.json`（活跃状态）、`sessions/`、`profiles/` | Star-Office ws_server 500ms 轮询；YiVad 桥接脚本写 `.ds-bot-states.json` |
| **YiAi** (:10086) | AI 后端 | FastAPI：auth/files/metrics/execution/knowledge/users 路由；MongoDB；SSE；RAG | YiVad 经 `yiAiProxyMiddleware` 代理；`/read-file` 承载桥接文件 |
| **YiVad** (Vue3) | 管理后台 | 41 个 API service 模块（okr/bug/issue/project/todo/dashboard…） | **已有** `botStatusService` + `groupBridgeService` 消费 DSH 状态 |
| **Star-Office** | 像素办公室 | ws_server(:19002) + dsh_server(:19003) + app(:19000)，Redis 存储 | 仅消费 DSH inflight.json——**与 YiAi/YiVad 零集成** |

### 1.2 核心问题

1. **双管道割裂**：同一份 DSH bot 状态，Star-Office 走 WebSocket 推送（500ms 级），YiVad 走桥接文件→YiAi→轮询（分钟级）。数据同源、链路两套、时效两级，无统一契约。
2. **契约未固化**：五态枚举 `executing/writing/idle/error/offline` 在 YiVad 和 Star-Office 恰好一致，纯属巧合，没有 schema 约束——任何一侧改动即静默漂移。
3. **Star-Office 信息贫瘠**：办公室只显示「谁在动」，不显示「在干什么」（YiAi 活动）和「干出了什么」（YiVad 成果）。
4. **轮询冗余**（铸舰已发现）：Star-Office 内部 4 个独立 DSH 轮询循环。

### 1.3 机会

- YiVad 的降级契约（stale 标记 + offline 兜底）和字段权威模型（DSH authoritative / local override wins）是成熟设计，**直接上升为全域标准**。
- Star-Office 的 ws_server 是现成的 WebSocket 基建，**升级为三源事件总线**成本最低。
- 铸舰的 `dsh_models.py`（Pydantic）是契约固化的种子。

---

## 2. 目标架构：统一事件总线 + 三环模型

```
┌─────────────────────────────────────────────────────────────┐
│                        数据源环 (Sources)                     │
│                                                             │
│  DSH ~/.dsh          YiAi :10086           YiVad API        │
│  inflight.json       /metrics /sse         okr/bug/todo     │
│  (谁在动·权威)        (在干什么)             (干出了什么)       │
└──────┬──────────────────┬──────────────────────┬────────────┘
       │ watch 500ms      │ poll/SSE (auth)      │ poll 30-60s
       ▼                  ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│              集成环 (Hub) — Star-Office Backend              │
│                                                             │
│   connectors/           OfficeEvent 规范契约                  │
│   ├─ dsh_connector      { source, type, botId?,             │
│   ├─ yiai_connector       payload, ts }                     │
│   └─ yivad_connector    Pydantic 校验 → Redis 状态快照        │
│                              ↓                              │
│              ws_server :19002 事件总线广播                    │
│         (state_change / activity / achievement / effect)     │
└──────┬──────────────────────────────────────────┬───────────┘
       │ WebSocket                                │ REST
       ▼                                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      效果环 (Effects)                        │
│                                                             │
│  Star-Office 前端                 YiVad 反向集成              │
│  ├─ 精灵状态动画 (DSH, 已有)       ├─ /office 路由嵌入办公室    │
│  ├─ 气泡打字动效 (YiAi 活动)       ├─ Bot 徽章深链跳转          │
│  ├─ 成果板 (YiVad OKR/bug 计数)    └─ 状态五态徽章(契约共享)     │
│  └─ 事件特效 (bug关闭→庆祝粒子)                                │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 规范契约：OfficeEvent

```python
class OfficeEvent(BaseModel):
    source: Literal["dsh", "yiai", "yivad", "office"]
    type: str          # state_change | activity | achievement | effect | system
    bot_id: str | None # 关联 bot（可空：全局事件）
    payload: dict      # source-specific，schema 由各 connector 文档化
    ts: datetime       # 事件时间（UTC）
    seq: int           # 总线单调序号，前端去重排序用
```

状态枚举全域统一（与 YiVad `DshBotState` 对齐）：
`executing | writing | researching | syncing | idle | error | offline`

### 2.2 关键决策（ADR-002 摘要）

| # | 决策 | 理由 | 否决的替代 |
|---|------|------|-----------|
| D1 | Hub 落在 Star-Office backend，不新建服务 | ws_server/Redis/降级链已生产就绪，增量最小 | 独立事件服务（运维成本+1） |
| D2 | Connector 模式接入三源，各自独立降级 | 单源故障不拖垮总线；沿用 YiVad stale 契约 | 大一统轮询器（耦合） |
| D3 | 五态枚举 + OfficeEvent 写入 Pydantic 契约包，YiVad/YiAi/Star-Office 三方引用 | 消灭「巧合一致」 | 各写各的（现状，已漂移风险） |
| D4 | YiVad 桥接文件链路保留为降级路径，主路径切 WebSocket | 不动 YiVad 现有可用性设计 | 强拆桥接（破坏 YiVad 降级） |
| D5 | 效果环只做「读」，不反向写三系统 | 办公室是仪表盘不是控制器，写路径风险不对称 | 双向控制（越权） |
| D6 | 4 个内部轮询收敛为 connector 内 2 个（dsh watch + dsh_server persist） | 铸舰技术债清单第 1 项 | 维持现状（I/O 竞争） |

### 2.3 数据流时效目标

| 链路 | 现状 | v3 目标 |
|------|------|---------|
| DSH 状态 → 办公室 | <500ms ✅ | 保持 |
| DSH 状态 → YiVad 徽章 | 分钟级（文件桥） | <2s（WS 订阅，文件桥降级） |
| YiAi 活动 → 办公室气泡 | 无 | <3s |
| YiVad 成果 → 办公室成果板 | 无 | <60s |

---

## 3. 分期实施计划

### Phase 0（在途，不打断）
筑桥 P1-P3 / 铸舰 dsh_server 迁移 / 星验测试基线 / 铁甲 YiAi 鉴权调研——**全部是 v3 的地基，照常收口**。

### Phase 1：契约固化 + Hub 骨架（今夜）
1. `dsh_models.py` → `contracts/` 包：OfficeEvent + 五态枚举 + BotStatus（对齐 YiVad 接口）
2. ws_server 增加多源 ingest 接口（`ingest_event(source, event)`），广播消息类型扩展
3. `docs/office-event-contract.md` 契约文档——YiVad/YiAi 侧评审入口

### Phase 2：三源 Connector（明夜）
1. `dsh_connector`：现 ws_server watch 逻辑抽离（闪电）
2. `yiai_connector`：/metrics + 活动流消费，**依赖铁甲鉴权结论**
3. `yivad_connector`：okr/bug/todo 计数轮询（30-60s，读 YiVad API 或其 MongoDB 只读副本）

### Phase 3：效果环（Phase 2 后）
1. 气泡打字动效（YiAi activity → BotBubble）
2. 成果板组件（YiVad achievement → OfficeOverlay，星绘）
3. 事件特效（bug 关闭→庆祝粒子、OKR 里程碑→楼层横幅，筑桥）

### Phase 4：反向集成（收尾）
1. YiVad `/office` 路由嵌入（协调 YiVad 页面管理群）
2. YiVad 徽章深链 → 办公室楼层定位
3. YiVad botStatusService 主路径切 WS（文件桥保留降级）

### 验证标准（每 Phase 出口）
- [ ] P1：契约包零循环依赖，ws_server 广播 OfficeEvent，星验契约测试全绿
- [ ] P2：三 connector 独立降级演练通过（拔任一源，总线存活 + stale 标记）
- [ ] P3：端到端演示——DSH 跑任务→精灵动画→气泡出 YiAi 活动→成果板计数+1
- [ ] P4：YiVad /office 路由可打开，徽章状态与办公室一致率 100%
- 回溯：任一 Phase 失败，revert 该 Phase commits，退回上一 Phase 稳定态

---

## 4. 分工（按领地，不跨线）

| 人 | Phase 1 | Phase 2+ |
|----|---------|----------|
| 铸舰 | contracts/ 包 + OfficeEvent（他的 dsh_models 升级） | yivad_connector |
| 闪电 | ws_server ingest 接口扩展 | dsh_connector 抽离 + 总线压测 |
| 筑桥 | 收口 P1-P3 后待命 | 前端效果：气泡动效 + 事件特效 |
| 星绘 | Token/SoToast 收口 | 成果板组件 + OfficeOverlay |
| 星验 | 现有 35 用例收口 | 契约测试 + connector 降级演练 |
| 铁甲 | YiAi 鉴权结论（1009） | yiai_connector 协作 |
| mac·企鹅 | — | Phase 4 跨群协调（YiVad 页面管理群） |

红线不变：跨人文件勿动、各自 commit、部署脚本永不代 commit、报告写 `/Users/yi/YrY/YiKnowledge/` 不写项目内。

---

## 5. 风险清单

| 风险 | 等级 | 缓解 |
|------|------|------|
| YiAi 鉴权未明（code 1009） | 🔴 阻塞 P2 | 铁甲调研中；不通则 yiai_connector 降级为只读公开端点或延后 |
| YiVad API 无对外契约文档 | 🟡 | 41 模块已探明入口，P2 前由铸舰出只读端点清单 |
| ws_server 单点（总线化后更关键） | 🟡 | 闪电的 6 故障场景文档 + 星验 resilience 测试覆盖 |
| 三方契约评审周期 | 🟡 | Phase 1 出文档即送 YiVad/YiAi 群评审，不阻塞 Hub 骨架开发 |
| 效果环范围蔓延 | 🟢 | D5 只读红线 + 每 Phase 验证标准封顶 |
