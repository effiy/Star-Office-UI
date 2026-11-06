# Star-Office-UI ↔ YiAi ↔ DSH 数据打通规范 v1.0

> 作者：AI专家·铁甲（aier）· 2026-11-07 · 状态：已评审可执行
> 用户指令：「数据打通 YiAi DSH，需要更专业」

## 1. 现状审计（代码取证，非推测）

### 1.1 现存数据通道（三条并行，互不知情）

| # | 通道 | 载体 | 端口 | 机制 | 问题 |
|---|------|------|------|------|------|
| A | DSH 文件桥 | `backend/state_reader.py` + `dsh_server.py` | :19003 | Flask，3s 轮询 `~/.dsh/bot/{state,inflight}.json` → push :19000 | Flask 残留（SU-02 已 FastAPI 化）；轮询延迟 0–3s |
| B | HTTP 回调桥 | `sync_bridge.py` | :19001 | stdlib http.server，bot 主动 POST /state → :19000 | 第三个常驻服务；依赖 bot 自觉回调 |
| C | WS 广播 | `ws_server.py` | — | 读 `bridge-state.json` + **自带一份 floor registry** | floor 逻辑与 app.py、前端三处重复 |

### 1.2 数据源盘点

| 源 | 位置 | 内容 | 权威性 |
|----|------|------|--------|
| DSH 实时状态 | `~/.dsh/bot/state.json` + `inflight.json` | bot id/name/role/color/avatar(base64) + 活跃 turn | **实时状态唯一真源** |
| YiAi 角色卡 | Mongo `ruiyi.knowledge_roles`（315 docs） | title/icon/color/redLines 原文/quickRefs/onboarding/subdirs | **角色元数据唯一真源** |
| Bot 卡片镜像 | `YiKnowledge/roles/*/BOT.md`（45 个）frontmatter | `bot_id`（= DSH session id）、bot_name、model、skills | **bot↔role 连接键唯一真源** |
| 前端硬编码 | `useBotStore.ts` L62 `"YiAi·核心": "2F"` | floor 映射 | ❌ 反模式，应删除 |

### 1.3 反模式清单（「不专业」的七个证据）

1. 三条摄取通道并存，无单一事实源；`bridge-state.json`（文件）+ `_latest_states`（内存）双写
2. floor 映射三处维护：`ws_server.py` / `useBotStore.ts` / `app.py`
3. bot↔agent 按**显示名** join（`agent_mapper.py`），名字一改全断；稳定键 `bot_id` 就在 BOT.md 里没人用
4. avatar base64（数十 KB/bot）随每次 WS 广播全量流转
5. 数据形状无版本化契约，每个消费者各自猜字段
6. 无新鲜度指标：状态过期无人知晓
7. YiAi 315 张角色卡零暴露：`roles.py` 只有 POST /roles-sync，没有任何 GET

## 2. 目标架构（单管线 + 双源 join）

```
[实时源] ~/.dsh/bot/*.json ──watchdog 文件监听──▶ ┌────────────────────────────────┐
                                                  │ Collector（FastAPI :19000 内     │
[元数据源] YiAi GET /roles ──60s TTL + 熔断────▶  │ lifespan 后台任务，唯一摄取点）  │
              (X-Token 服务间鉴权)                 │ 按 bot_id join → BotState v1    │
                                                  └───────────────┬────────────────┘
                                                                  ▼
                                       Redis star:bot:{id} + star:meta:floor（SU-02 已就位）
                                       bridge-state.json 降级为 Redis 故障 fallback
                                                                  │ pub/sub
                                                  ┌───────────────▼───────────────┐
                                                  │ WS 广播（瘦身：avatar 走 URL） │──▶ 前端 Pinia（typed）
                                                  └───────────────────────────────┘
```

**原则**
- 单摄取：退役 `dsh_server.py`(:19003) 与 `sync_bridge.py`(:19001)，并入 FastAPI lifespan
- 单真源：Redis；文件桥仅作降级路径
- 单契约：Pydantic `BotState` = 权威 schema，前端 TS 类型由 schema 生成，禁止手写漂移
- 稳定 join：`bot_id`（DSH session id）贯穿 DSH→YiAi→Star-Office，显示名仅做展示
- 元数据归 YiAi，办公室语义（floor/sprite/position）归 Star-Office，各管一段

## 3. 数据契约 BotState v1

```python
class BotState(BaseModel):
    version: int = 1
    id: str                    # DSH session id（bot_id，稳定 join 键）
    name: str                  # 显示名，如 mac·企鹅
    state: Literal["idle","writing","executing","researching","syncing","error","offline"]
    detail: str = ""
    floor: str                 # "1F"，来自 Star-Office floor registry（Redis star:meta:floor）
    role_id: str = ""          # YiAi 角色目录名，如 aier
    role_title: str = ""       # YiAi 角色卡 title
    icon: str = ""             # YiAi 角色卡 icon
    redlines: list[str] = []   # YiAi 红线 label 摘要（tooltip 用，≤5 条）
    avatar_url: str            # GET /agents/{id}/avatar + ETag；WS 禁止 base64
    updated_at: int            # epoch ms
    stale: bool                # updated_at > 10s → true，前端置灰
```

YiAi 侧新 API（本轮已实现，见 §5-T1）：
- `GET /roles` → 全部角色卡摘要 + bot 绑定（botId/botName）
- `GET /roles/{role_id}` → 单卡全量（redLines/quickRefs/onboarding 原文）
- 鉴权：`X-Token`（服务间静态 token，Star-Office .env 配 `YIAI_TOKEN`，不进 git）

## 4. 新鲜度 SLO 与可观测

| 指标 | 目标 | 暴露点 |
|------|------|--------|
| DSH 变化 → 前端可见 | P95 < 1s（事件驱动） | `/health`: collector_lag_ms |
| YiAi 角色卡缓存 | TTL 60s；不可用时熔断降级（用旧缓存/默认值，不阻塞实时线） | `/health`: yiai_ok, yiai_cache_age_s |
| Redis 健康 | 写失败 → bridge-state.json fallback + 告警日志 | `/health`: redis_ok |
| WS 首包 | < 500ms（现状 2-3ms，勿回退） | 压测脚本回归 |
| 状态过期 | stale 标记 10s 阈值 | BotState.stale |

## 5. 分工与验收

| # | 负责人 | 任务 | 验收标准 |
|---|--------|------|----------|
| T1 | AI专家·铁甲 | YiAi `GET /roles` + `GET /roles/{id}` + roles-sync 索引 BOT.md（botId 连接键） | curl 带 X-Token 返回全量卡片含 botId；契约字段与 BotState v1 对齐 ✅ 本轮交付 |
| T2 | SU·后端·铸舰 | Collector 并入 FastAPI：watchdog 监听 DSH 文件、按 bot_id join YiAi（60s 缓存+熔断）、写 Redis、avatar URL 端点、退役 :19001/:19003 | `ss -tlnp` 只剩 :19000；/ds-bot-states 走 Redis；/health 含四指标 |
| T3 | SU·实时·闪电 | ws_server 改订 Redis pub/sub；广播瘦身（无 base64）；stale 推送 | 广播体积 ↓≥60%；6 故障场景回归全过；首包不回退 |
| T4 | SU·架构·筑桥 | 契约工程化：Pydantic→TS schema 生成流；floor registry 单源方案；组件树消费 BotState 方式 | docs/architecture-audit.md 含契约章节 + 硬编码清除清单 |
| T5 | SU·测试·星验 | 契约测试：BotState 在 DSH→Collector→WS 三点 schema 校验；SLO 测试；YiAi 熔断测试 | pytest 契约套件绿；CI 拦截 schema 不匹配 |
| T6 | SU·UI·星绘 | 前端：删 useBotStore floor 硬编码；角色卡 tooltip（子域/红线/快速参考）；stale 视觉态 | 前端 grep 无 floor 硬编码；tooltip 展示 YiAi 卡片数据 |

**依赖链**：T1 → T2 → T3；T4/T5/T6 在 T2 契约冻结后并行。T1 已完成，T2 可立即开工。

## 6. 迁移与回滚

- 分步：T2 上线时 :19001/:19003 先停写不停进程（观察 24h）→ 确认 Redis 路径稳定后删进程
- 回滚：bridge-state.json fallback 常驻，Redis 或 YiAi 全挂时系统退化为现状（文件桥），不黑屏
- 红线：部署/重启脚本永不代 commit 工作树；v2-dev 各自收口各自 commit

## 7. YiAi 接入鉴权细则（Collector 凭证配置，ADR-002 D5 配套）

- **Base URL**：`http://127.0.0.1:10086`（本机直连；macapi 公网隧道已纪律令 disable，勿依赖）
- **鉴权**：请求头 `X-Token: <API_X_TOKEN>`。取值源：`~/Library/LaunchAgents/com.yivad.yiai.plist` 的 API_X_TOKEN；配置到 `Star-Office-UI/.env` 的 `YIAI_TOKEN`（.env 已 gitignore）。**永不进 git、永不进前端代码**
- **Token 红线**：X-Token 只存在于服务端 Collector。浏览器不得持有 token → 前端要角色卡详情一律经 Collector(:19000) 代理一跳，不直连 YiAi（也规避 CORS）
- **端点**：`GET /roles`（列表，`?bot_id=` join 过滤 / `?status=` 过滤，轻投影）；`GET /roles/{id}`（全量卡含 redLines/quickRefs 原文）
- **缓存**：YiAi 响应已带 `Cache-Control: public, max-age=60` + ETag；Collector 侧另建自有 60s TTL 缓存（独立于 HTTP 缓存，专供熔断降级）
- **熔断降级**：连续 3 次失败 → 熔断打开 → 供旧缓存（标 stale）→ 无缓存则 BotState 角色字段留空默认值；**永不阻塞 DSH 实时主线**。`/health` 暴露 `yiai_ok` / `yiai_cache_age_s`
- **Join 语义**：DSH state.json 的 bot id = `knowledge_roles.botId`（11-07 00:52 起由 roles-sync 每分钟自动刷新，当前 43/316 已绑定）。未绑定 bot：角色字段空，前端正常渲染、无角色卡 tooltip
- **变更单**：11-07 00:56 已发跨项目联动枢纽（含销项证据：live 200/401/join 1-hit）；待 mac·企鹅 会签（ADR-002 D5）。入库：YiAi 747e1ec（签蟹）

## 8. 第二波预研：YiAi 活动流调研结论（yiai_connector 选型，11-07 01:05 实测 Mongo ruiyi 库）

| 候选源 | 数据形态 | 判定 |
|--------|----------|------|
| `knowledge_files` roles/ 子树（524 文件已索引，含 path/updatedAt） | 各 bot 知识目录的最近写入 = 其工作痕迹 | ✅ **主信号**：30–60s delta 轮询，role 目录名 → knowledge_roles.botId join |
| `knowledge_roles.updatedAt`（roles-sync 每分钟刷新） | 卡片级活动 | ✅ 次信号，与主信号同库顺手取 |
| `audit_logs`（1754 条，actor/operation/timestamp） | API 级操作流水 | ❌ actor 仅 admin/anonymous，**无 bot 身份**——如需 per-API 活动，第二波立项 `X-Bot-Id` 请求头方案（触及鉴权面 = 红线级变更单 + 盾卫评审） |
| `dashboard/live` SSE（5s KPI 推送） | 全局指标 | 🟡 可做办公室全局氛围层（非 per-bot 气泡） |
| `agent_sessions` / `chat_records` | YiAi 自身 AI 会话 | ❌ 与 DSH bot 无关，排除 |

**结论**：第二波 yiai_connector 以 knowledge_files delta 轮询为「在干什么」信号源，气泡内容 = 最近 N 条知识写入（文件名+时间）；v3 风险表「YiAi 鉴权未明(1009)」已解除——1009 = X-Token 中间件，细则见 §7。
