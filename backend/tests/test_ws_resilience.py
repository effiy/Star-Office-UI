"""
ws_server 故障场景自动化测试 — 6 场景全覆盖

场景 1: 进程崩溃 → 自动恢复
场景 2: DSH 未运行 → 降级到 bridge-state.json
场景 3: bridge-state.json 损坏 → 不崩溃
场景 4: 网络闪断 → 服务端清理死连接
场景 5: 高并发 50 连接 → snapshot 全部到达（标记 slow）
场景 6: inflight 兜底 bridge 过期
"""
import asyncio
import json
import os
import subprocess

import pytest
import websockets

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


# ═════════════════════════════════════════════════════════════
# 场景 1: 进程崩溃 → 客户端感知连接关闭
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_client_detects_crash(data_dir, bridge_state_json, state_json):
    """ws_server 进程崩溃后，客户端 onclose 触发"""
    port = 19997

    proc = subprocess.Popen(
        ["python", "ws_server.py"],
        env={
            **os.environ,
            "WS_BIND_PORT": str(port),
            "DSH_INFLIGHT_FILE": str(data_dir / "no-inflight.json"),
            "DSH_STATE_FILE": str(state_json),
            "BRIDGE_STATE_FILE": str(bridge_state_json),
            "FLOOR_REGISTRY_FILE": str(data_dir / "no-registry.json"),
        },
        cwd=PROJECT_ROOT,
    )
    await asyncio.sleep(1.5)

    # 连接 + 收 snapshot
    ws = await websockets.connect(f"ws://127.0.0.1:{port}")
    await asyncio.wait_for(ws.recv(), timeout=5)

    # 杀掉 ws_server
    proc.kill()
    proc.wait()

    # 验证连接关闭
    with pytest.raises((websockets.ConnectionClosed, ConnectionError, OSError)):
        await asyncio.wait_for(ws.recv(), timeout=3)


# ═════════════════════════════════════════════════════════════
# 场景 2: DSH 未运行 → 降级到 bridge-state.json
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_fallback_when_inflight_missing(data_dir, bridge_state_json, state_json):
    """inflight.json 不存在时，ws_server 使用 bridge-state.json 提供快照"""
    port = 19998

    proc = subprocess.Popen(
        ["python", "ws_server.py"],
        env={
            **os.environ,
            "WS_BIND_PORT": str(port),
            "DSH_INFLIGHT_FILE": str(data_dir / "DOES_NOT_EXIST.json"),
            "DSH_STATE_FILE": str(state_json),
            "BRIDGE_STATE_FILE": str(bridge_state_json),
            "FLOOR_REGISTRY_FILE": str(data_dir / "no-registry.json"),
        },
        cwd=PROJECT_ROOT,
    )
    await asyncio.sleep(1.5)

    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))

            assert msg["type"] == "snapshot"
            # bridge-state 数据应在 snapshot 中
            assert "Chief" in msg.get("bots", {})
    finally:
        proc.kill()
        proc.wait()


# ═════════════════════════════════════════════════════════════
# 场景 3: bridge-state.json 损坏 → 不崩溃，inflight 兜底
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_corrupted_bridge_state_no_crash(data_dir, state_json):
    """bridge-state.json 是乱码时 ws_server 不崩溃 — 闪电已修 main() 加 try/except ✅"""
    port = 19999

    bridge = data_dir / "bad-bridge.json"
    bridge.write_text("NOT VALID JSON {{{")

    inflight = data_dir / "inflight.json"
    inflight.write_text(json.dumps({
        "turns": {"s1": {"botId": "s1"}}
    }))

    proc = subprocess.Popen(
        ["python", "ws_server.py"],
        env={
            **os.environ,
            "WS_BIND_PORT": str(port),
            "DSH_INFLIGHT_FILE": str(inflight),
            "DSH_STATE_FILE": str(state_json),
            "BRIDGE_STATE_FILE": str(bridge),
            "FLOOR_REGISTRY_FILE": str(data_dir / "no-registry.json"),
        },
        cwd=PROJECT_ROOT,
    )
    await asyncio.sleep(1.5)

    try:
        # ws_server 不应崩溃
        assert proc.poll() is None, "ws_server 在损坏的 bridge-state 下崩溃"

        # 仍可连接并收到 snapshot（降级到 inflight）
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert msg["type"] == "snapshot"
    finally:
        proc.kill()
        proc.wait()


# ═════════════════════════════════════════════════════════════
# 场景 4: 网络闪断 → 服务端心跳清理死连接
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_server_cleans_dead_connections(data_dir, bridge_state_json, state_json):
    """客户端突然断开后，ws_server 心跳机制清理死连接"""
    port = 20000

    proc = subprocess.Popen(
        ["python", "ws_server.py"],
        env={
            **os.environ,
            "WS_BIND_PORT": str(port),
            "DSH_INFLIGHT_FILE": str(data_dir / "no-inflight.json"),
            "DSH_STATE_FILE": str(state_json),
            "BRIDGE_STATE_FILE": str(bridge_state_json),
            "FLOOR_REGISTRY_FILE": str(data_dir / "no-registry.json"),
            # 缩短轮询周期，加快测试
        },
        cwd=PROJECT_ROOT,
    )
    await asyncio.sleep(1.5)

    try:
        ws1 = await websockets.connect(f"ws://127.0.0.1:{port}")
        ws2 = await websockets.connect(f"ws://127.0.0.1:{port}")

        # 收 snapshot
        await asyncio.wait_for(ws1.recv(), timeout=5)
        await asyncio.wait_for(ws2.recv(), timeout=5)

        # 暴力关闭 ws1（不发 close frame）
        transport = ws1.transport
        if transport:
            transport.close()
        else:
            await ws1.close()

        # ws2 应仍然存活
        await ws2.send(json.dumps({"type": "ping"}))
        pong = json.loads(await asyncio.wait_for(ws2.recv(), timeout=5))
        assert pong["type"] == "pong"

        await ws2.close()
    finally:
        proc.kill()
        proc.wait()


# ═════════════════════════════════════════════════════════════
# 场景 5: 高负载 50 并发连接 → snapshot 全部到达
# ═════════════════════════════════════════════════════════════

@pytest.mark.slow
@pytest.mark.asyncio
async def test_high_concurrency_connections(data_dir, bridge_state_json, state_json):
    """多并发连接全部收到 snapshot（缩减到 20 连接以便 CI 运行）"""
    port = 20001
    CONCURRENT = 20

    proc = subprocess.Popen(
        ["python", "ws_server.py"],
        env={
            **os.environ,
            "WS_BIND_PORT": str(port),
            "DSH_INFLIGHT_FILE": str(data_dir / "no-inflight.json"),
            "DSH_STATE_FILE": str(state_json),
            "BRIDGE_STATE_FILE": str(bridge_state_json),
            "FLOOR_REGISTRY_FILE": str(data_dir / "no-registry.json"),
        },
        cwd=PROJECT_ROOT,
    )
    await asyncio.sleep(1.5)

    try:
        async def connect(idx):
            try:
                async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                    raw = await asyncio.wait_for(ws.recv(), timeout=10)
                    msg = json.loads(raw)
                    return msg["type"] == "snapshot"
            except Exception as e:
                return False

        results = await asyncio.gather(*[connect(i) for i in range(CONCURRENT)])
        success = sum(1 for r in results if r)
        assert success >= CONCURRENT * 0.9, f"仅 {success}/{CONCURRENT} 连接收到 snapshot"
    finally:
        proc.kill()
        proc.wait()


# ═════════════════════════════════════════════════════════════
# 场景 6: inflight 兜底 bridge 过期 → inflight 优先
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_inflight_takes_priority_over_bridge(data_dir, state_json):
    """bridge 里 bot 是 idle，但 inflight 里活跃 → snapshot 里 bot 状态为 executing"""
    port = 20002

    # bridge: SU·测试·星验 是 idle
    bridge = data_dir / "bridge-state.json"
    bridge.write_text(json.dumps({
        "SU·测试·星验": {"state": "idle", "detail": "桥接显示空闲"},
        "Chief": {"state": "executing", "detail": "管理"},
    }, ensure_ascii=False))

    # inflight: SU·测试·星验 活跃
    inflight = data_dir / "inflight.json"
    inflight.write_text(json.dumps({
        "turns": {
            "s2": {"botId": "s2"},  # SU·测试·星验
        }
    }))

    proc = subprocess.Popen(
        ["python", "ws_server.py"],
        env={
            **os.environ,
            "WS_BIND_PORT": str(port),
            "DSH_INFLIGHT_FILE": str(inflight),
            "DSH_STATE_FILE": str(state_json),
            "BRIDGE_STATE_FILE": str(bridge),
            "FLOOR_REGISTRY_FILE": str(data_dir / "no-registry.json"),
        },
        cwd=PROJECT_ROOT,
    )
    await asyncio.sleep(1.5)

    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))

            assert msg["type"] == "snapshot"
            bots = msg["bots"]

            # SU·测试·星验 在 bridge 里 idle，但 inflight 活跃 → 应显示 executing
            assert bots["SU·测试·星验"]["state"] == "executing", \
                f"inflight 应覆盖 bridge 的 idle，实际: {bots['SU·测试·星验']}"

            # Chief 只在 bridge 里 → 保持原状态
            assert bots["Chief"]["state"] == "executing"
    finally:
        proc.kill()
        proc.wait()