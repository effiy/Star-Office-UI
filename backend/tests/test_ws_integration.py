"""
ws_server 集成测试 — 完整生命周期

启动临时 ws_server 进程 → 连接 → snapshot → state_change → ping/pong → 断开
"""
import asyncio
import json
import os
import subprocess
import time

import pytest
import websockets

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.mark.asyncio
async def test_connect_receives_snapshot(data_dir, bridge_state_json, state_json):
    """连接后立即收到 snapshot 消息"""
    port = 19991

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
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw)

            assert msg["type"] == "snapshot"
            assert "Chief" in msg["bots"]
            assert "floor_summary" in msg
            assert "timestamp" in msg

            # 每个 bot 都有 floor 字段
            for name, info in msg["bots"].items():
                assert "floor" in info, f"{name} 缺少 floor 字段"
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.asyncio
async def test_ping_pong_protocol(data_dir, bridge_state_json, state_json):
    """客户端发 ping → 服务端回 pong"""
    port = 19992

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
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            # 收 snapshot
            await asyncio.wait_for(ws.recv(), timeout=5)

            # 发 ping
            await ws.send(json.dumps({"type": "ping"}))
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw)

            assert msg["type"] == "pong"
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.asyncio
async def test_multiple_clients_all_receive_snapshot(data_dir, bridge_state_json, state_json):
    """多个客户端同时连接，都收到 snapshot"""
    port = 19993

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
        async def connect_and_check(client_id):
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                msg = json.loads(raw)
                assert msg["type"] == "snapshot", f"client {client_id} 未收到 snapshot"
                return True

        results = await asyncio.gather(
            connect_and_check(1),
            connect_and_check(2),
            connect_and_check(3),
        )
        assert all(results), "部分客户端未收到 snapshot"
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.asyncio
async def test_state_change_on_inflight_update(data_dir, bridge_state_json, state_json):
    """inflight.json 变化时广播 state_change"""
    port = 19994

    inflight = data_dir / "inflight.json"
    inflight.write_text(json.dumps({"turns": {}}))

    proc = subprocess.Popen(
        ["python", "ws_server.py"],
        env={
            **os.environ,
            "WS_BIND_PORT": str(port),
            "DSH_INFLIGHT_FILE": str(inflight),
            "DSH_STATE_FILE": str(state_json),
            "BRIDGE_STATE_FILE": str(bridge_state_json),
            "FLOOR_REGISTRY_FILE": str(data_dir / "no-registry.json"),
        },
        cwd=PROJECT_ROOT,
    )
    await asyncio.sleep(1.5)

    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            # 收 snapshot
            await asyncio.wait_for(ws.recv(), timeout=5)

            # 模拟 inflight 变化: 新 bot 活跃
            await asyncio.sleep(0.2)
            inflight.write_text(json.dumps({
                "turns": {
                    "s3": {"botId": "s3"},  # SU·实时·闪电 变活跃
                }
            }))

            # 等待 500ms 轮询
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw)

            # 可能是 ping 或 state_change，收几次
            while msg["type"] == "ping":
                # 回复 pong
                await ws.send(json.dumps({"type": "pong"}))
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                msg = json.loads(raw)

            assert msg["type"] == "state_change", f"期望 state_change，收到 {msg['type']}"
            assert "changes" in msg
            assert len(msg["changes"]) > 0
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.asyncio
async def test_client_disconnect_cleanup(data_dir, bridge_state_json, state_json):
    """客户端断开后 ws_server 正常清理"""
    port = 19995

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
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=5)
        # 连接正常关闭后，ws_server 应仍在运行
        assert proc.poll() is None, "ws_server 在客户端断开后异常退出"
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.asyncio
async def test_invalid_message_does_not_crash(data_dir, bridge_state_json, state_json):
    """客户端发送非法 JSON 不导致服务端崩溃"""
    port = 19996

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
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=5)

            # 发送非法 JSON
            await ws.send("not json at all {{{")
            await asyncio.sleep(0.5)

            # 服务端应存活，且仍能响应 ping
            await ws.send(json.dumps({"type": "ping"}))
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw)
            assert msg["type"] == "pong"

            assert proc.poll() is None
    finally:
        proc.kill()
        proc.wait()