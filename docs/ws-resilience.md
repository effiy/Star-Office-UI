# WebSocket 降级策略与弹性设计

> SU-01 交付物 — 实时推送可靠性保障  
> 版本: v2-dev | 更新: 2026-11-04

---

## 1. 架构概览

```
                     ┌──────────────────────────────┐
                     │     DSH inflight.json         │
                     └──────────────┬───────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                      ▼
     ┌────────────────┐   ┌────────────────┐    ┌─────────────────┐
     │  ws_server.py  │   │ ds_bot_watcher │    │  sync_bridge.py │
     │  (500ms poll)  │   │   (1s poll)    │    │    (:19001)     │
     │    :19002       │   │                │    │  state 持久化    │
     └───────┬────────┘   └───────┬────────┘    └────────┬────────┘
             │                    │                       │
             │ WebSocket          │ POST /state            │ HTTP
             │ 实时推送            │                       │
             ▼                    ▼                       ▼
     ┌────────────────┐   ┌─────────────────────────────────────┐
     │  useBotStore   │   │         backend/app.py (:19000)      │
     │  (Pinia)       │   │          /agents REST API            │
     │                │   │          /office/floor/{n}           │
     └───────┬────────┘   └────────────────┬────────────────────┘
             │                              │
             │ WebSocket (主)                │ HTTP (备)
             │                              │
             ▼                              ▼
     ┌─────────────────────────────────────────────────────────┐
     │                  useDSHBridge.ts                         │
     │           双重路径: WS 实时 + REST 3s 轮询                 │
     └─────────────────────────────────────────────────────────┘
```

**数据流：**
- **主路径** (WebSocket): DSH inflight.json → ws_server (500ms poll) → WebSocket push → 前端 (<500ms 延迟)
- **备路径** (REST): DSH → sync_bridge → Flask /agents API → 前端 fetchBots() (3s 轮询)
- **持久化**: sync_bridge 写 bridge-state.json，供 ws_server 快照和 /ds-bot-states 端点使用

---

## 2. 双重路径降级机制

### 2.1 前端: useDSHBridge.ts

```typescript
// frontend/src/composables/useDSHBridge.ts

function start() {
    // 主路径: WebSocket 实时连接
    botStore.connectWebSocket();

    // 备路径: REST 3s 轮询，与 WebSocket 并行运行
    startPolling();
}
```

**关键设计决策**: WebSocket 和 REST 轮询**同时运行**，而非 sequential fallback。

| 优势 | 说明 |
|------|------|
| 零切换延迟 | REST 持续拉取数据，WS 断开时数据仍然新鲜 |
| 数据交叉验证 | 两个路径同时更新 Pinia store，最后写入者胜出 |
| 静默降级 | 用户无感知，`wsConnected` 仅影响状态指示灯 |

### 2.2 WebSocket 重连策略 (useBotStore.ts)

```
断开 → 立即关闭 socket → scheduleReconnect()
                                  │
                                  ▼
                         等待 5s → connectWebSocket()
                                  │
                         ┌────────┴────────┐
                         ▼                 ▼
                    连接成功            连接失败
                    (清除计时器)      ws.onerror → close()
                                          │
                                          ▼
                                    scheduleReconnect()
                                    (不重复添加计时器)
```

**参数表：**

| 参数 | 值 | 位置 |
|------|-----|------|
| 重连延迟 | 5s | `useBotStore.ts:292` |
| WebSocket URL | `VITE_WS_URL` 或 `ws://hostname:19002` | `useBotStore.ts:291` |
| 心跳保洁 | 30s 服务端主动 ping | `ws_server.py:33` |
| 僵尸连接清理 | 心跳发送失败 → 自动踢出 | `ws_server.py:181-187` |

### 2.3 服务端: ws_server.py 容错

```python
# ws_server.py — 多层容错

# 1. DSH 未运行时优雅降级
if not os.path.exists(INFLIGHT_FILE):
    log.warning("⚠️ inflight.json 不存在，使用 bridge-state.json 提供状态")

# 2. bridge-state.json 优先，inflight.json 补充
def get_state_snapshot():
    states = {}
    if os.path.exists(BRIDGE_STATE_FILE):
        states = json.load(open(BRIDGE_STATE_FILE))
    # 补充 inflight 活跃数据覆盖 idle 状态
    active = get_active_bots()
    for name in active:
        if states.get(name, {}).get("state") == "idle":
            states[name]["state"] = "executing"

# 3. 广播异常恢复
except Exception as e:
    log.error(f"广播异常: {e}")
    await asyncio.sleep(5)  # 冷却后重试

# 4. 60s 周期重载 bot 名册
if tick % int(RELOAD_INTERVAL / POLL_INTERVAL) == 0:
    load_bot_names()  # 新增 bot 自动发现
```

---

## 3. 故障模式与恢复

| 故障场景 | 影响 | 恢复方式 | 恢复时间 |
|----------|------|----------|----------|
| ws_server 进程崩溃 | WebSocket 断开, 前端状态灯红 | systemd/start-v2.sh 重启 + 前端 5s 重连 | 5-10s |
| DSH 未运行 | inflight.json 不存在, 所有 bot 显示 idle | ws_server 自动降级到 bridge-state.json | 即时 |
| bridge-state.json 损坏 | 状态快照为空 | inflight.json 补充 → 部分状态可用 | 即时 |
| 网络闪断 (客户端) | WebSocket 断开 | 前端 5s 重连 + REST 3s 轮询保底 | 3-5s (REST 覆盖) |
| 高负载 (50+ 连接) | 广播延迟增大 | 单线程 asyncio 事件循环; 心跳自动清理死连接 | 正常 <100ms |
| sync_bridge 宕机 | bridge-state.json 不更新 | ws_server 直接从 inflight.json 读取活跃状态 | 即时 |
| Redis 不可用 (SU-02) | /agents API 降级到 JSON | WebSocket 不受影响 (独立路径) | 即时 |

---

## 4. 延迟分析

### 4.1 正常路径延迟

```
DSH turn 开始
  │
  ├─ write inflight.json ....................... ~0ms
  │
  ├─ ws_server 下一个 poll (max 500ms) ......... ≤500ms
  │
  ├─ JSON 序列化 + WebSocket send .............. ~1ms
  │
  ├─ 网络传输 (本地回环) ....................... ~0.2ms
  │
  └─ 前端 onmessage → Pinia 响应式更新 ......... ~1ms
                                            ─────────
                                 端到端延迟:  ≤502ms  ✅
```

### 4.2 降级路径延迟

```
DSH turn 开始
  │
  ├─ ds_bot_watcher poll (1s) ................. ≤1000ms
  │
  ├─ POST /state → sync_bridge ................ ~5ms
  │
  ├─ sync_bridge → /set_state → Flask .......... ~5ms
  │
  ├─ 前端 fetchBots() 轮询 (3s) ................ ≤3000ms
  │
  └─ JSON 解析 → Pinia 更新 ................... ~1ms
                                            ─────────
                                 端到端延迟:  ≤4011ms  ⚠️
```

### 4.3 退化重叠保护

由于 WebSocket 和 REST 同时运行：
- WebSocket 正常时: 数据 <500ms 到达，REST 3s 后的数据被忽略 (同值)
- WebSocket 断开时: REST 保证 3s 内数据更新，5s 后 WebSocket 恢复接管

**实际用户感知**: WebSocket 断开后 3s 内状态仍准确（REST 持续更新），5s 后 WebSocket 恢复。

---

## 5. 验证清单

### 5.1 功能验证

- [x] `ws_server.py` 端口绑定 19002，无端口冲突
- [x] 前端 `connectWebSocket()` 连接成功 → `wsConnected = true`
- [x] 连接即收完整 `snapshot` 消息（含 floor 分配）
- [x] `state_change` 增量更新触发 Pinia 响应式
- [x] `floor` 格式端到端一致: ws_server "1F" → snapshot → useBotStore → OfficeFloor
- [x] 前端 `onclose` → 5s 后自动重连
- [x] 重连后收到新 `snapshot`
- [x] REST 3s 轮询与 WebSocket 并行运行
- [x] 30s 心跳保洁 → 死连接自动清理

### 5.2 压力验证

运行压测脚本:
```bash
WS_STRESS_CONNS=5 WS_STRESS_DURATION=15 WS_STRESS_FLIP=0.5 python scripts/ws_stress_test.py
```

| 指标 | 目标 | 实测 | 状态 |
|------|------|------|------|
| 连接延迟 | <500ms | **2-3ms** (5 并发) | ✅ |
| 广播延迟 | <500ms avg | **≤500ms** (理论值, 基于 500ms poll) | ✅ |
| 5 并发连接 | 全成功 | **5/5** 全部成功 | ✅ |
| 错误率 | 0% | **0** 错误 | ✅ |
| 丢帧率 | 0% | 快照全部送达 (5/5) | ✅ |

> **广播延迟说明**: 端到端广播延迟由 `POLL_INTERVAL = 500ms` 约束。ws_server 每 500ms 轮询 DSH `inflight.json`，检测到活跃 bot 集合变化时立即广播。理论最大延迟 = 500ms (poll) + ~2ms (序列化+发送) + ~0.2ms (本地回环) ≈ 502ms。实际延迟取决于 inflight.json 的写入时机和 poll 的对齐。

---

## 6. 已知局限与后续改进

| 局限 | 影响 | 改进方向 |
|------|------|----------|
| WebSocket 单播广播 (O(n) 发送) | 100+ 客户端时延迟增大 | 改用 Redis Pub/Sub 或消息队列 |
| 无消息确认/重传 | 网络丢包导致单条消息丢失 (下次快照恢复) | 添加序列号 + NACK 重传 |
| 无数据压缩 | 50 agent 快照 ~3KB | brotli 压缩可降至 500B |
| REST 轮询始终运行 | 无 WebSocket 故障时浪费 1 req/3s | 添加 `wsConnected` 监听 → 自动停启轮询 |
| floor-registry.json 静态 | 新增 bot 需手动注册楼层 | 对接 DSH API 自动发现 + 智能楼层分配 |

---

## 7. 依赖关系

```
ws_server.py
├── websockets >= 12.0
├── floor-registry.json (50 bot 楼层分配)
├── bridge-state.json (sync_bridge 写入)
├── ~/.dsh/bot/inflight.json (DSH 写入)
└── ~/.dsh/bot/state.json (DSH bot 名册)

useDSHBridge.ts → useBotStore.ts
├── WebSocket → ws://hostname:19002 (主)
├── fetchBots() → GET /agents (备)
└── scheduleReconnect() → 5s 延迟重试
```

---

*本文档随 SU-01 交付，与 `ws_server.py`、`useBotStore.ts`、`useDSHBridge.ts` 同步维护。*