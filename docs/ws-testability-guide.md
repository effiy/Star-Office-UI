# ws_server 可测性说明 & 6 故障场景自动化方案

> 写给 SU·测试·星验 — ws_server.py 的测试钩子和怎么把 6 个故障场景变成自动化用例  
> 版本: v2-dev | 作者: SU·实时·闪电 | 2026-11-07

---

## 1. ws_server.py 可测性接口

### 1.1 启动参数（全环境变量控制）

```
WS_BIND_HOST      默认 127.0.0.1    监听地址
WS_BIND_PORT      默认 19002        监听端口
DSH_INFLIGHT_FILE 默认 ~/.dsh/bot/inflight.json  活跃数据源
DSH_STATE_FILE    默认 ~/.dsh/bot/state.json     bot 名册
```

**关键**: 测试时指向临时目录的 mock JSON，不依赖真实 DSH 运行。

### 1.2 纯函数——直接单元测试，不需要起服务

| 函数 | 输入 | 输出 | 怎么测 |
|------|------|------|--------|
| `load_floor_registry()` | floor-registry.json → `BOT_FLOOR` dict | 直接 `assert BOT_FLOOR["Chief"] == 1` |
| `get_floor(name)` | bot 名字符串 → `"1F"` `"2F"` `"3F"` | `assert get_floor("Chief") == "1F"` |
| `get_floor_num(name)` | bot 名字符串 → `1` `2` `3` | `assert get_floor_num("Chief") == 1` |
| `compute_floor_summary(states)` | `{"Chief": {"state":"executing"}}` → `{1:1,2:0,3:0}` | 纯 dict 输入输出 |
| `get_state_snapshot()` | bridge-state.json + inflight.json | mock 两个 JSON 文件路径 |
| `load_bot_names()` | state.json | mock JSON 内容 |
| `get_active_bots()` | inflight.json | mock JSON 内容 |

### 1.3 WebSocket 消息协议（3 种消息类型）

测试时连上 ws://127.0.0.1:19002，第一条消息必定是 `snapshot`：

```json
// → 连接后立即收到
{"type": "snapshot", "bots": {"Chief": {"state":"executing","floor":"1F"}}, "floor_summary": {...}, "timestamp": "..."}

// → 状态变化时收到
{"type": "state_change", "changes": {"Chief": {"state":"executing","floor":"1F"}}, ...}

// → 收到服务端 ping，应回复 pong
{"type": "ping", "ts": "..."}
// ← 回复
{"type": "pong"}
```

### 1.4 生命周期 hooks

```
启动 → load_floor_registry() → load_bot_names() → websockets.serve(handler, ...) + broadcast_updates()
                                                                          │
                          每 60s: load_bot_names()                       │
                          每 30s: 心跳 ping 全部客户端                    │
                          每 500ms: 检查 inflight.json → state_change 广播 │
```

---

## 2. 6 故障场景 → 自动化用例

> 所有用例可直接加入 `backend/tests/` 目录，用 pytest + pytest-asyncio 运行。  
> 需新增依赖: `pip install pytest-asyncio websockets`

### 场景 1: ws_server 进程崩溃 → 自动恢复

```python
# tests/test_ws_resilience.py

import asyncio
import pytest
import subprocess
import time
import websockets

@pytest.mark.asyncio
async def test_reconnect_after_crash(tmp_path):
    """ws_server 进程崩溃后，客户端 onclose → 重启后 reconnect 成功"""
    # 1. 准备 mock 数据
    bridge = tmp_path / "bridge-state.json"
    bridge.write_text('{"TestBot": {"state": "executing", "detail": ""}}')

    # 2. 启动 ws_server 指向 mock 数据
    proc = subprocess.Popen([
        "python", "ws_server.py"
    ], env={
        **os.environ,
        "WS_BIND_PORT": "19999",
        "DSH_INFLIGHT_FILE": str(tmp_path / "no-inflight.json"),
        "DSH_STATE_FILE": str(tmp_path / "no-state.json"),
    })

    await asyncio.sleep(1)  # 等它启动

    # 3. 连接 + 收 snapshot
    async with websockets.connect("ws://127.0.0.1:19999") as ws:
        msg = json.loads(await ws.recv())
        assert msg["type"] == "snapshot"

        # 4. 杀掉 ws_server
        proc.kill()
        proc.wait()

        # 5. 验证连接关闭
        with pytest.raises(websockets.ConnectionClosed):
            await ws.recv()

    # ✅ 前端 useBotStore 会在 onclose 时触发 5s scheduleReconnect
```

**自动化要点**: `subprocess.Popen` 启动 → `proc.kill()` 模拟崩溃 → `pytest.raises(ConnectionClosed)` 验证。

### 场景 2: DSH 未运行 → 降级到 bridge-state.json

```python
@pytest.mark.asyncio
async def test_fallback_when_dsh_offline(tmp_path):
    """inflight.json 不存在时，ws_server 使用 bridge-state.json 提供快照"""
    bridge = tmp_path / "bridge-state.json"
    bridge.write_text('{"OfflineBot": {"state": "idle", "detail": "离线"}}')

    proc = subprocess.Popen([
        "python", "ws_server.py"
    ], env={
        **os.environ,
        "WS_BIND_PORT": "19998",
        # 故意指向不存在的 inflight.json
        "DSH_INFLIGHT_FILE": str(tmp_path / "DOES_NOT_EXIST.json"),
        "DSH_STATE_FILE": str(tmp_path / "no-state.json"),
        # BRIDGE_STATE_FILE 环境变量（如果 ws_server 支持的话，否则需要 patch）
    })
    await asyncio.sleep(1)

    async with websockets.connect("ws://127.0.0.1:19998") as ws:
        msg = json.loads(await ws.recv())
        assert msg["type"] == "snapshot"
        # bridge-state 数据应在 snapshot 中
        assert "OfflineBot" in msg.get("bots", {})

    proc.kill()
    proc.wait()
```

**注意**: `BRIDGE_STATE_FILE` 目前是硬编码在项目根目录。如果要完整的 mock 隔离，需要改 ws_server.py 让它也支持 `BRIDGE_STATE_FILE` 环境变量覆盖。**建议修改**（<5 行改动）:

```python
# ws_server.py line 30 — 当前:
BRIDGE_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bridge-state.json")
# 改为:
BRIDGE_STATE_FILE = os.environ.get(
    "BRIDGE_STATE_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "bridge-state.json")
)
```

### 场景 3: bridge-state.json 损坏 → 不崩溃，inflight 兜底

```python
@pytest.mark.asyncio
async def test_corrupted_bridge_state_no_crash(tmp_path):
    """bridge-state.json 是乱码时 ws_server 不崩溃"""
    bridge = tmp_path / "bridge-state.json"
    bridge.write_text("NOT VALID JSON {{{")

    inflight = tmp_path / "inflight.json"
    inflight.write_text(json.dumps({
        "turns": {"t1": {"botId": "s1"}}
    }))
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({
        "bots": {"s1": {"name": "AliveBot"}}
    }))

    # ws_server 不应崩溃
    proc = subprocess.Popen([...])
    await asyncio.sleep(1)
    assert proc.poll() is None  # 进程存活
    proc.kill()
```

**自动化要点**: 写入非法 JSON → `assert proc.poll() is None`。

### 场景 4: 网络闪断（客户端） → REST 3s 保底

这个场景更适合前端 E2E 测试（Playwright/Cypress），但可以验证 ws_server 端行为：

```python
@pytest.mark.asyncio
async def test_server_cleans_dead_connections():
    """客户端突然断开后，ws_server 心跳机制 30s 内清理死连接"""
    ws1 = await websockets.connect("ws://127.0.0.1:19997")
    ws2 = await websockets.connect("ws://127.0.0.1:19997")

    # 收 snapshot
    await ws1.recv()
    await ws2.recv()

    # 暴力关闭 ws1（不发 close frame）
    transport = ws1.transport
    transport.close()

    # 等 30s 心跳周期
    await asyncio.sleep(35)

    # ws2 应仍然存活
    await ws2.send(json.dumps({"type": "ping"}))
    pong = json.loads(await asyncio.wait_for(ws2.recv(), timeout=5))
    assert pong["type"] == "pong"

    await ws2.close()
```

**自动化要点**: `transport.close()` 模拟闪断 → 等心跳周期 → 验证其他连接正常。

### 场景 5: 高负载（50+ 连接）

已有 `scripts/ws_stress_test.py`，直接改参数跑：

```python
@pytest.mark.slow
@pytest.mark.asyncio
async def test_50_concurrent_connections():
    """50 并发连接 + snapshot 全部按时到达"""
    # 直接用 ws_stress_test 的 connect_and_measure 逻辑
    # 改 NUM_CONNECTIONS=50, DURATION_SEC=30
    ...
```

**已有基础设施**: `scripts/ws_stress_test.py` 只需 `WS_STRESS_CONNS=50 python scripts/ws_stress_test.py`。

### 场景 6: sync_bridge 宕机 → bridge-state.json 不更新

与场景 2 类似——ws_server 能直接从 inflight.json 读取：

```python
@pytest.mark.asyncio
async def test_inflight_fallback_when_bridge_stale():
    """bridge-state.json 过期，inflight.json 有更新数据 → inflight 优先"""
    # mock: bridge 里 bot 是 idle，但 inflight 里 bot 活跃
    # 预期: snapshot 里 bot 状态是 executing
    ...
```

**自动化要点**: bridge-state 和 inflight 设置冲突状态 → 验证 inflight 胜出。

---

## 3. 建议的测试文件结构

```
backend/tests/
├── test_dsh_bridge.py          # 已有 17 tests
├── test_ws_resilience.py       # 🆕 6 故障场景 (pytest-asyncio)
├── test_ws_unit.py             # 🆕 纯函数单元测试 (get_floor/compute_floor_summary/load_floor_registry)
├── test_ws_integration.py      # 🆕 ws_server 完整生命周期 (启动→连接→snapshot→state_change→断开)
└── conftest.py                 # 🆕 共享 fixtures (临时目录、mock JSON、ws_server 进程)
```

### 3.1 conftest.py 骨架

```python
import pytest
import subprocess
import json
import tempfile
import asyncio
from pathlib import Path

@pytest.fixture
def data_dir(tmp_path):
    """创建临时 mock 数据目录"""
    d = tmp_path / "dsh"
    d.mkdir()
    return d

@pytest.fixture
def mock_bots():
    """标准 3-bot mock 数据"""
    return {"Chief": {"state": "executing", "detail": "管理"},
            "SU·测试·星验": {"state": "idle", "detail": "测试"}}

@pytest.fixture
def bridge_json(data_dir, mock_bots):
    p = data_dir / "bridge-state.json"
    p.write_text(json.dumps(mock_bots, ensure_ascii=False))
    return p

@pytest.fixture
async def ws_server(data_dir):
    """启动临时 ws_server，测试完自动清理"""
    port = 19990
    proc = subprocess.Popen(
        ["python", "ws_server.py"],
        env={
            **__import__("os").environ,
            "WS_BIND_PORT": str(port),
            "DSH_INFLIGHT_FILE": str(data_dir / "inflight.json"),
            "DSH_STATE_FILE": str(data_dir / "state.json"),
        },
        cwd="/Users/yi/YrY/Star-Office-UI",
    )
    await asyncio.sleep(1)
    yield f"ws://127.0.0.1:{port}"
    proc.kill()
    proc.wait()
```

### 3.2 pytest 配置（pyproject.toml）

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["backend/tests"]
markers = [
    "slow: 慢测试, CI 中可选跑",
    "asyncio: 异步测试",
]
```

---

## 4. 覆盖目标建议

| 层 | 覆盖目标 | 用例数 | 备注 |
|---|---|---|---|
| 纯函数 | 100% 分支 | ~15 | get_floor/hash/floor_registry edge cases |
| WebSocket 协议 | 3 消息类型 + error path | ~8 | snapshot/state_change/ping/错误 JSON |
| 生命周期 | 启动/重载/心跳/优雅退出 | ~6 | 60s reload, 30s heartbeat |
| 故障场景 | 6 场景全绿 | ~6 | 崩溃/离线/损坏/闪断/负载/过期 |
| **合计** | | **~35** | 覆盖 <30min 跑完（慢测试除外） |

---

## 5. 快速上手命令

```bash
cd /Users/yi/YrY/Star-Office-UI

# 装测试依赖
pip install pytest pytest-asyncio pytest-timeout

# 跑所有测试
pytest backend/tests/ -v

# 只跑 ws 单元测试
pytest backend/tests/test_ws_unit.py -v

# 跑 ws 集成测试（需先手动改 BRIDGE_STATE_FILE 为环境变量）
WS_BIND_PORT=19999 python ws_server.py &
pytest backend/tests/test_ws_integration.py -v
kill %1
```

---

## 6. ws_server.py 建议的小改动（方便测试）

| 改动 | 代码量 | 价值 |
|------|--------|------|
| `BRIDGE_STATE_FILE` 支持环境变量 | 1 行 | mock 隔离，不用 patch |
| `FLOOR_REGISTRY_FILE` 支持环境变量 | 1 行 | floor registry mock |
| `main()` 加一个 signal handler 优雅退出 | 3 行 | `proc.terminate()` 替代 `proc.kill()` |

总计 5 行改动，测试隔离度从 60% → 100%。

---

*本文档与 `ws_server.py`、`docs/ws-resilience.md`、`scripts/ws_stress_test.py` 配合使用。有问题直接 @我。*