# Star-Office-UI v2 测试架构设计 — YiAi/YiVad/DSH 三线数据打通

> **日期**: 2026-11-07  
> **负责**: SU·测试·星验  
> **状态**: 🟢 提案中，等待 go-ahead  

---

## 一、现状与目标

### 现状数据流

```
DSH (~/.dsh/bot/*.json)           YiAi (:10086)          YiVad (另项目)
      │                                │                      │
      ▼                                ▼                      ▼
ws_server :19002               [鉴权中间件 1009]       [待调研]
dsh_server :19003
      │
      ▼
app.py :19000 ──► frontend (Vue3+Phaser)
```

**痛点**：
- DSH 有 4 个独立轮询循环（500ms/1s/3s/3s），无统一数据契约验证
- YiAi 接入面未定义，鉴权方式未知
- YiVad 数据通道不存在
- 三源合并时的冲突解决策略无测试覆盖
- 无跨系统端到端回归能力

### 目标架构

```
        ┌─────────────────────────────────────┐
        │        统一数据契约层 (Pydantic)       │
        │  BotState / ProjectMeta / ActivityLog │
        └────┬──────────┬──────────┬───────────┘
             │          │          │
    ┌────────▼──┐ ┌────▼────┐ ┌───▼────────┐
    │ DSH Source │ │YiAi Src │ │YiVad Source│
    │ :19002/03  │ │ :10086  │ │ 待定义      │
    └──────┬─────┘ └───┬─────┘ └──────┬─────┘
           │            │             │
           └────────────┬─────────────┘
                        ▼
              ┌──────────────────┐
              │  Merge Engine    │
              │  优先级: inflight│
              │  > bridge > YiAi │
              │  > YiVad         │
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │  app.py :19000   │
              │  useBotStore     │
              │  Phaser 渲染      │
              └──────────────────┘
```

---

## 二、测试金字塔 — 三层覆盖

### L1: 数据契约测试（~20 用例，<1s）

**目标**：每种数据源的 Schema 验证、边界值、冲突解决算法

```
tests/contracts/
├── test_dsh_contract.py    # DSH inflight/state/bridge 格式验证
├── test_yiai_contract.py   # YiAi API 响应格式验证（待铁甲调研）
├── test_yivad_contract.py  # YiVad 数据格式验证（待定义）
└── test_merge_engine.py    # 三源合并的去重+优先级算法
```

**关键场景**：
- 同一 bot 在 DSH=executing, YiAi=idle → DSH 胜出
- DSH 离线时 YiAi 数据兜底 → 降级不丢数据
- 时间戳冲突：取最新 `updatedAt`
- 未知来源标记 `stateSource: "unknown"` → 不崩溃

### L2: 集成测试 — 跨系统数据流（~15 用例，~30s）

**目标**：验证数据从源头到前端的完整链路

```
tests/integration/
├── test_dsh_to_frontend.py     # DSH → ws_server → useBotStore
├── test_yiai_to_frontend.py    # YiAi API → dsh_server → useBotStore
├── test_cross_source_merge.py  # DSH + YiAi + YiVad 同时在线 → merge 正确
└── test_source_failover.py     # 任一源宕机 → 其余源兜底
```

**Mock 策略**：
- 每源一个轻量 Mock HTTP/WS 服务器（aiohttp test server）
- 同时注入 DSH mock JSON + YiAi mock API + YiVad mock socket
- 验证 useBotStore 最终状态 = 三源合并预期值

### L3: E2E 回归（~8 场景，Playwright）

**目标**：真实浏览器中的完整用户旅程

```
tests/e2e/
├── test_office_floor_rendering.spec.ts  # 楼层渲染正确
├── test_bot_state_live_update.spec.ts   # WS 推送 → UI 实时更新
├── test_cross_project_visibility.spec.ts # YiAi/YiVad bot 在 Star-Office 可见
└── test_degraded_mode.spec.ts           # WS 断 → REST 兜底 → UI 降级提示
```

---

## 三、关键设计决策

### 3.1 统一数据契约 — `UnifiedBotState`

```python
class UnifiedBotState(BaseModel):
    name: str                          # "Chief"
    state: DshBotState                 # executing | idle | error | ...
    floor: int = 2                     # 1-3
    project: str = "dsh"               # "dsh" | "yiai" | "yivad"
    source_priority: int = 0           # 冲突时取最高
    updated_at: datetime
    metadata: dict = {}                # 源特有字段（不参与合并）
```

**合并规则**：
1. 按 `source_priority` 取最高（DSH=10 > YiAi=5 > YiVad=3）
2. 同优先级按 `updated_at` 取最新
3. state=error 的源降权（不覆盖正常数据）

### 3.2 Mock 基础设施 — 可复用的三源模拟器

```python
# tests/mock_servers/
# ├── mock_dsh.py      # 模拟 ~/.dsh/bot/*.json 文件变化
# ├── mock_yiai.py     # 模拟 :10086 API（含鉴权中间件）
# └── mock_yivad.py    # 模拟 YiVad 数据推送
```

每个模拟器支持：
- ✅ 正常数据注入
- ✅ 故障注入（超时/500/格式错误）
- ✅ 延迟模拟（慢网络）
- ✅ 数据变化触发（模拟实时更新）

### 3.3 可观测性 — 测试即监控

```python
# 每个测试自动收集:
@pytest.fixture(autouse=True)
def metrics_collector():
    """收集跨系统延迟、丢包率、合并冲突次数"""
    yield {
        "dsh_latency_ms": [],
        "yiai_latency_ms": [],
        "merge_conflicts": 0,
        "stale_data_events": 0,
    }
```

---

## 四、实施路线图

| 优先级 | 任务 | 预估工作量 | 依赖 |
|:---:|------|:---:|------|
| 🔴 P0 | `test_dsh_contract.py` + `test_merge_engine.py` | 2h | dsh_models.py 已完成 |
| 🔴 P0 | 三源 Mock 服务器（mock_dsh / mock_yiai / mock_yivad） | 3h | 铁甲 YiAi 调研 |
| 🟡 P1 | `test_cross_source_merge.py` 集成测试 | 2h | P0 完成 |
| 🟡 P1 | E2E Playwright 骨架 + 首个场景 | 4h | 筑桥前端收口 |
| 🟢 P2 | CI 流水线（GitHub Actions） | 2h | P1 稳定 |
| 🟢 P2 | 可观测性仪表盘 | 3h | metrics_collector |

---

## 五、立即可交付

以下不依赖 YiAi/YiVad 调研，现在就能写：

1. **`tests/contracts/test_dsh_contract.py`** — DSH 数据格式验证（已有 dsh_models.py）
2. **`tests/contracts/test_merge_engine.py`** — 合并算法测试（纯函数，无外部依赖）
3. **`tests/integration/test_cross_source_merge.py`** — 多源合并集成（mock DSH + mock YiAi + mock YiVad 三 server 同时跑）

---

*等待技术管家·哲思/用户 go-ahead。P0 三文件可在 2h 内全部交付并全绿。*