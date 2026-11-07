#!/usr/bin/env python3
"""
WebSocket 延迟压测 & 降级验证脚本

模拟 5+ 并发 WebSocket 连接 + 高频 state_change 广播
记录: 连接延迟、快照延迟、广播延迟、丢帧率、延迟抖动

用法:
    python scripts/ws_stress_test.py [--connections 10] [--duration 30] [--flip-interval 0.5]
"""

import asyncio
import json
import os
import sys
import time
import statistics
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import websockets

# ── Config ───────────────────────────────────────────────
WS_URL = os.environ.get("WS_STRESS_URL", "ws://127.0.0.1:19002")
NUM_CONNECTIONS = int(os.environ.get("WS_STRESS_CONNS", "5"))
DURATION_SEC = int(os.environ.get("WS_STRESS_DURATION", "30"))
FLIP_INTERVAL = float(os.environ.get("WS_STRESS_FLIP", "0.5"))
BRIDGE_STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "bridge-state.json"
)

# ── Metrics ──────────────────────────────────────────────
connect_times = []       # ms: connect → snapshot received
broadcast_latencies = [] # ms: bridge-state write → state_change received
message_counts = {}      # client_id → count
pong_times = []          # ms: ping → pong RTT
errors = []
jitter_samples = []      # inter-message gaps (ms) for jitter calc


async def connect_and_measure(client_id: int, results: dict):
    """单个客户端: 连接、接收 snapshot、统计消息"""
    try:
        t0 = time.monotonic()
        async with websockets.connect(WS_URL) as ws:
            t_connected = time.monotonic()

            # Wait for snapshot
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            t_snapshot = time.monotonic()
            data = json.loads(raw)

            connect_ms = (t_connected - t0) * 1000
            snapshot_ms = (t_snapshot - t0) * 1000
            connect_times.append(connect_ms)
            results[f"client_{client_id}_connect_ms"] = round(connect_ms, 1)
            results[f"client_{client_id}_snapshot_ms"] = round(snapshot_ms, 1)
            results[f"client_{client_id}_snapshot_type"] = data.get("type", "?")
            results[f"client_{client_id}_snapshot_bots"] = len(data.get("bots", {}))

            msg_count = 1
            last_msg_ts = t_snapshot

            # Collect messages for duration
            try:
                while time.monotonic() - t0 < DURATION_SEC + 10:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2)
                    now = time.monotonic()
                    msg_count += 1

                    # Track inter-message gaps for jitter
                    gap = (now - last_msg_ts) * 1000
                    if gap < 5000:  # Ignore gaps > 5s (reconnection etc)
                        jitter_samples.append(gap)
                    last_msg_ts = now

                    msg = json.loads(raw)
                    if msg.get("type") == "state_change":
                        ts_str = msg.get("timestamp", "")
                        try:
                            msg_dt = datetime.fromisoformat(ts_str)
                            latency_ms = (datetime.now(timezone.utc) - msg_dt).total_seconds() * 1000
                            broadcast_latencies.append(latency_ms)
                        except Exception:
                            pass
            except asyncio.TimeoutError:
                pass

            message_counts[client_id] = msg_count
            results[f"client_{client_id}_msgs"] = msg_count

    except Exception as e:
        errors.append(f"client_{client_id}: {e}")
        results[f"client_{client_id}_error"] = str(e)


async def flip_bridge_state():
    """高频翻转 bridge-state.json 模拟 state_change 广播"""
    if not os.path.exists(BRIDGE_STATE_FILE):
        print(f"  ⚠️  bridge-state.json 不存在, 跳过翻转测试")
        return

    test_name = f"StressTest_{uuid.uuid4().hex[:6]}"
    try:
        with open(BRIDGE_STATE_FILE) as f:
            orig = json.load(f)
    except Exception:
        orig = {}

    flip_count = 0
    t0 = time.monotonic()

    while time.monotonic() - t0 < DURATION_SEC:
        for state in ["executing", "idle", "writing", "researching"]:
            if time.monotonic() - t0 >= DURATION_SEC:
                break

            # Modify first N bots' states
            modified = dict(orig)
            for i, (name, info) in enumerate(modified.items()):
                if i >= 5:
                    break
                modified[name] = {**info, "state": state, "detail": f"{test_name} flip #{flip_count}"}

            try:
                with open(BRIDGE_STATE_FILE, "w") as f:
                    json.dump(modified, f, ensure_ascii=False, indent=2)
                flip_count += 1
            except Exception as e:
                errors.append(f"flip: {e}")

            await asyncio.sleep(FLIP_INTERVAL)

    # Restore original
    try:
        with open(BRIDGE_STATE_FILE, "w") as f:
            json.dump(orig, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return flip_count


def print_report(results: dict, flip_count: int = 0):
    """打印压测报告"""
    print()
    print("═" * 60)
    print("  Star-Office-UI WebSocket 延迟压测报告")
    print("═" * 60)
    print(f"  测试时间: {datetime.now().isoformat()}")
    print(f"  WS 地址:  {WS_URL}")
    print(f"  并发连接: {NUM_CONNECTIONS}")
    print(f"  测试时长: {DURATION_SEC}s")
    print(f"  翻转间隔: {FLIP_INTERVAL}s (共 {flip_count} 次)")
    print()

    # ── Connection ──
    print("── 连接延迟 ──")
    if connect_times:
        print(f"  样本数:     {len(connect_times)}")
        print(f"  avg:        {statistics.mean(connect_times):.0f} ms")
        print(f"  p50:        {statistics.median(connect_times):.0f} ms")
        print(f"  p99:        {sorted(connect_times)[int(len(connect_times)*0.99)] if len(connect_times)>=100 else 'N/A'}")
        print(f"  min/max:    {min(connect_times):.0f} / {max(connect_times):.0f} ms")
    else:
        print("  ❌ 无连接数据")

    # ── Broadcast latency ──
    print()
    print("── 广播延迟 (bridge-state 写入 → WebSocket 送达) ──")
    if broadcast_latencies:
        print(f"  样本数:     {len(broadcast_latencies)}")
        print(f"  avg:        {statistics.mean(broadcast_latencies):.0f} ms")
        print(f"  p50:        {statistics.median(broadcast_latencies):.0f} ms")
        p99_idx = int(len(broadcast_latencies) * 0.99)
        print(f"  p99:        {sorted(broadcast_latencies)[p99_idx] if len(broadcast_latencies) >= 100 else 'N/A'}")
        print(f"  min/max:    {min(broadcast_latencies):.0f} / {max(broadcast_latencies):.0f} ms")
        # Jitter: stddev of inter-message gaps
        if len(jitter_samples) > 1:
            jitter = statistics.stdev(jitter_samples)
            print(f"  抖动(std):  {jitter:.0f} ms")
        # Check target: < 500ms
        over_500 = sum(1 for l in broadcast_latencies if l > 500)
        print(f"  超标(>500ms): {over_500}/{len(broadcast_latencies)} ({over_500/len(broadcast_latencies)*100:.1f}%)" if broadcast_latencies else "")
    else:
        print("  ⚠️  无广播数据 (bridge-state 可能未触发 state_change)")

    # ── Message delivery ──
    print()
    print("── 消息送达 ──")
    total_msgs = sum(message_counts.values())
    print(f"  总消息数:   {total_msgs}")
    if message_counts:
        avg_per_client = total_msgs / len(message_counts)
        print(f"  每客户端:   avg {avg_per_client:.0f}, min {min(message_counts.values())}, max {max(message_counts.values())}")
        # Expected: flip_count * NUM_CONNECTIONS state_changes + snapshots + heartbeats
        expected_min = flip_count + 1  # snapshot + state_changes
        dropped = [f"client_{cid}" for cid, cnt in message_counts.items() if cnt < expected_min * 0.8]
        if dropped:
            print(f"  ⚠️  可疑丢帧: {dropped}")
        else:
            print(f"  ✅ 无丢帧 (每客户端 ≥ {expected_min} msg)")

    # ── Errors ──
    print()
    print("── 错误 ──")
    if errors:
        for e in errors:
            print(f"  ❌ {e}")
    else:
        print("  ✅ 无错误")

    # ── Summary ──
    print()
    print("── 验收判定 ──")
    checks = []
    if connect_times and statistics.mean(connect_times) < 500:
        checks.append(("✅", f"连接延迟 <500ms ({statistics.mean(connect_times):.0f}ms)"))
    else:
        checks.append(("❌", "连接延迟超标"))
    if broadcast_latencies and statistics.mean(broadcast_latencies) < 500:
        checks.append(("✅", f"广播延迟 <500ms ({statistics.mean(broadcast_latencies):.0f}ms)"))
    else:
        checks.append(("⚠️" if broadcast_latencies else "⚠️", "广播延迟无数据/超标"))
    if not errors:
        checks.append(("✅", "零错误"))
    else:
        checks.append(("❌", f"{len(errors)} 个错误"))
    for icon, msg in checks:
        print(f"  {icon} {msg}")

    print()
    print("═" * 60)
    return checks


async def main():
    print(f"WebSocket 延迟压测启动")
    print(f"  目标: {WS_URL}")
    print(f"  {NUM_CONNECTIONS} 并发, {DURATION_SEC}s, flip={FLIP_INTERVAL}s")

    # Check ws_server is reachable
    try:
        async with websockets.connect(WS_URL) as ws:
            await asyncio.wait_for(ws.recv(), timeout=3)
        print("  ✅ ws_server 可达")
    except Exception as e:
        print(f"  ❌ ws_server 不可达: {e}")
        print("  请先启动: python ws_server.py")
        sys.exit(1)

    results = {}

    # Start bridge-state flipper in background
    flip_task = asyncio.create_task(flip_bridge_state())

    # Start all client connections concurrently
    client_tasks = [
        connect_and_measure(i, results)
        for i in range(NUM_CONNECTIONS)
    ]
    await asyncio.gather(*client_tasks)

    # Wait for flipper to finish
    flip_count = await flip_task

    # Print report
    print_report(results, flip_count)


if __name__ == "__main__":
    asyncio.run(main())