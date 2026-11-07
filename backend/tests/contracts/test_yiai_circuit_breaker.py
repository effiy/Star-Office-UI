"""
YiAi :10086 熔断 & 降级测试

模拟场景:
  1. YiAi 超时 → merge_engine 降级到 DSH 单源
  2. YiAi 鉴权失败 (code 1009) → 源标记 unhealthy，不崩
  3. YiAi 返回 500 → 熔断器打开，跳过 YiAi 数据
  4. 熔断器半开 → 探测请求成功 → 恢复
  5. 三源全崩 → 前端用 bridge-state.json 兜底

纯函数测试，mock HTTP 响应，无真实网络依赖。
"""

import os
import sys
import time
from typing import Any, Dict

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from merge_engine import merge_bot_states, compute_source_health


# ── 熔断器状态机 ────────────────────────────────────────────

class CircuitState:
    CLOSED = "closed"          # 正常
    OPEN = "open"              # 熔断
    HALF_OPEN = "half_open"    # 半开（探测中）


class CircuitBreaker:
    """简易熔断器：3 次连续失败 → OPEN → 30s 后 HALF_OPEN → 1 次成功 → CLOSED"""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self.threshold = failure_threshold
        self.recovery = recovery_timeout
        self.failures = 0
        self.last_failure = 0.0
        self.state = CircuitState.CLOSED

    def call(self, fn, *args, **kwargs) -> Any:
        """执行一次调用，自动管理熔断状态"""
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.last_failure >= self.recovery:
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitOpenError("熔断中，拒绝请求")

        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
        self.failures = 0

    def _on_failure(self):
        self.failures += 1
        self.last_failure = time.monotonic()
        if self.failures >= self.threshold:
            self.state = CircuitState.OPEN


class CircuitOpenError(Exception):
    pass


# ── Mock YiAi API ───────────────────────────────────────────

class MockYiAiAPI:
    """模拟 YiAi :10086 GET /roles 接口"""

    def __init__(self, roles_data: dict):
        self.data = roles_data
        self.should_timeout = False
        self.should_401 = False
        self.should_500 = False
        self.call_count = 0

    def get_roles(self) -> dict:
        self.call_count += 1
        if self.should_timeout:
            raise TimeoutError("YiAi :10086 超时 (3s)")
        if self.should_401:
            raise PermissionError("YiAi 鉴权失败 code=1009")
        if self.should_500:
            raise RuntimeError("YiAi 500 Internal Server Error")
        return dict(self.data)


# ═════════════════════════════════════════════════════════════
# 场景 1: YiAi 超时 → 降级
# ═════════════════════════════════════════════════════════════

class TestYiAiTimeout:
    def test_timeout_graceful_degradation(self):
        """YiAi 超时 → merge 只用 DSH 数据，不丢 Bot"""
        dsh_data = {
            "Chief": {"state": "executing", "updatedAt": "2026-11-07T00:00:00Z"},
        }

        api = MockYiAiAPI({"Chief": {"state": "idle"}})
        api.should_timeout = True

        # 尝试获取 YiAi 数据
        yiai_data = {}
        try:
            yiai_data = api.get_roles()
        except TimeoutError:
            yiai_data = {}  # 降级为空

        merged = merge_bot_states({"dsh": dsh_data, "yiai": yiai_data})
        assert "Chief" in merged
        assert merged["Chief"]["state"] == "executing"  # DSH 数据保住了

    def test_timeout_health_check_marks_unavailable(self):
        """超时后源健康度标记为不可用"""
        api = MockYiAiAPI({"Bot": {"state": "idle"}})
        api.should_timeout = True

        yiai_data = {}
        try:
            yiai_data = api.get_roles()
        except TimeoutError:
            pass

        health = compute_source_health({"dsh": {"Bot": {"state": "idle"}}, "yiai": yiai_data})
        assert not health["yiai"]["available"]
        assert health["dsh"]["available"]


# ═════════════════════════════════════════════════════════════
# 场景 2: YiAi 鉴权失败 → 不崩溃
# ═════════════════════════════════════════════════════════════

class TestYiAiAuthFailure:
    def test_401_graceful_degradation(self):
        """鉴权失败 → 降级为空源，不影响其他源"""
        dsh_data = {"Chief": {"state": "executing"}}

        api = MockYiAiAPI({"Chief": {"state": "idle"}})
        api.should_401 = True

        yiai_data = {}
        try:
            yiai_data = api.get_roles()
        except PermissionError:
            yiai_data = {}

        merged = merge_bot_states({"dsh": dsh_data, "yiai": yiai_data})
        assert "Chief" in merged
        assert merged["Chief"]["state"] == "executing"

    def test_401_does_not_crash_pipeline(self):
        """鉴权失败不导致整体崩溃，管道继续"""
        api = MockYiAiAPI({})
        api.should_401 = True

        try:
            api.get_roles()
        except PermissionError:
            pass

        # 管道不受影响
        result = merge_bot_states({"dsh": {"Bot": {"state": "idle"}}})
        assert len(result) == 1


# ═════════════════════════════════════════════════════════════
# 场景 3: 熔断器 → 自动打开/半开/恢复
# ═════════════════════════════════════════════════════════════

class TestCircuitBreakerLifecycle:
    def test_trips_after_consecutive_failures(self):
        """3 次连续失败 → 熔断打开"""
        cb = CircuitBreaker(failure_threshold=3)
        api = MockYiAiAPI({})
        api.should_500 = True

        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(api.get_roles)

        assert cb.state == CircuitState.OPEN
        assert cb.failures == 3

    def test_open_rejects_requests(self):
        """熔断打开后拒绝请求"""
        cb = CircuitBreaker(failure_threshold=1)
        api = MockYiAiAPI({})
        api.should_500 = True

        # 触发熔断
        with pytest.raises(RuntimeError):
            cb.call(api.get_roles)

        assert cb.state == CircuitState.OPEN

        # 新请求被拒绝
        with pytest.raises(CircuitOpenError):
            cb.call(api.get_roles)

    def test_half_open_and_recovery(self):
        """半开探测成功 → 恢复"""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)  # 立即恢复

        api = MockYiAiAPI({})
        api.should_500 = True
        with pytest.raises(RuntimeError):
            cb.call(api.get_roles)

        assert cb.state == CircuitState.OPEN

        # recovery_timeout=0，下一次调用应该进入 HALF_OPEN 并成功
        api.should_500 = False
        result = cb.call(api.get_roles)
        assert cb.state == CircuitState.CLOSED
        assert result is not None

    def test_merge_engine_with_circuit_breaker(self):
        """熔断器包装 YiAi 源 → merge_engine 仍正常工作"""
        cb = CircuitBreaker(failure_threshold=2)
        api = MockYiAiAPI({
            "BotA": {"state": "idle", "roleTitle": "测试", "icon": "🧪"},
        })

        # 正常调用
        yiai = cb.call(api.get_roles)
        merged = merge_bot_states({
            "dsh": {"BotA": {"state": "executing"}},
            "yiai": yiai,
        })
        assert merged["BotA"]["state"] == "executing"  # DSH 胜出
        assert merged["BotA"]["roleTitle"] == "测试"   # YiAi 注入成功


# ═════════════════════════════════════════════════════════════
# 场景 4: 三源全崩 → bridge-state.json 兜底
# ═════════════════════════════════════════════════════════════

class TestAllSourcesDown:
    def test_empty_sources_graceful_merge(self):
        """所有源都返回空 → merge 不报错，返回 {}"""
        result = merge_bot_states({})
        assert result == {}

    def test_bridge_fallback_only_source(self):
        """只有 bridge-state.json 数据 → 作为唯一源可用"""
        bridge = {"Chief": {"state": "idle", "detail": "离线中"}}
        merged = merge_bot_states({"bridge": bridge})
        assert merged["Chief"]["state"] == "idle"


# ═════════════════════════════════════════════════════════════
# 场景 5: 混合故障 — DSH 在线，YiAi+Yivad 都崩
# ═════════════════════════════════════════════════════════════

class TestMixedFailure:
    def test_dsh_healthy_others_dead(self):
        """DSH 正常但 YiAi/YiVad 全崩 → DSH 数据不受影响"""
        sources = {
            "dsh": {
                "Chief": {"state": "executing"},
                "Worker": {"state": "writing"},
            },
            "yiai": {},   # 熔断
            "yivad": {},  # 宕机
        }
        merged = merge_bot_states(sources)
        assert len(merged) == 2
        assert merged["Chief"]["state"] == "executing"

    def test_health_report_shows_partial_outage(self):
        sources = {
            "dsh": {"Bot1": {"state": "idle"}, "Bot2": {"state": "executing"}},
            "yiai": {},
            "yivad": {},
        }
        health = compute_source_health(sources)
        assert health["dsh"]["available"]
        assert not health["yiai"]["available"]
        assert not health["yivad"]["available"]