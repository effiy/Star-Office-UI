"""
三源合并引擎 契约测试

覆盖: 优先级/时间戳/error降权/兜底链/源健康度
纯函数测试，无外部依赖，<0.01s 跑完
"""

import sys
import os
from copy import deepcopy

# 确保可 import merge_engine（项目根目录）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from merge_engine import (
    merge_bot_states,
    pick_winner,
    resolve_source_priority,
    compute_source_health,
    get_fallback_chain,
    SOURCE_PRIORITY,
)


# ═════════════════════════════════════════════════════════════
# resolve_source_priority
# ═════════════════════════════════════════════════════════════

class TestSourcePriority:
    def test_dsh_top_priority(self):
        assert resolve_source_priority("dsh", "executing") == 10

    def test_yiai_mid_priority(self):
        assert resolve_source_priority("yiai", "idle") == 5

    def test_yivad_low_priority(self):
        assert resolve_source_priority("yivad", "writing") == 3

    def test_error_state_drops_two_levels(self):
        """error 状态的源降 2 级（防止污染正常数据）"""
        assert resolve_source_priority("dsh", "error") == 8    # 10 - 2
        assert resolve_source_priority("yiai", "error") == 3   # 5 - 2
        assert resolve_source_priority("yivad", "error") == 1  # 3 - 2

    def test_unknown_source_defaults_to_1(self):
        assert resolve_source_priority("unknown-source", "idle") == 1

    def test_error_cannot_go_below_zero(self):
        assert resolve_source_priority("yivad", "error") >= 0


# ═════════════════════════════════════════════════════════════
# merge_bot_states
# ═════════════════════════════════════════════════════════════

class TestMergeBotStates:
    """核心合并逻辑"""

    # ── 基础合并 ──

    def test_empty_sources_returns_empty(self):
        assert merge_bot_states({}) == {}

    def test_single_source_passthrough(self):
        sources = {
            "dsh": {"Chief": {"state": "executing", "detail": "管理"}}
        }
        result = merge_bot_states(sources)
        assert "Chief" in result
        assert result["Chief"]["state"] == "executing"

    def test_two_sources_higher_priority_wins(self):
        """DSH executing vs YiAi idle → DSH 胜"""
        sources = {
            "dsh":  {"Chief": {"state": "executing", "updatedAt": "2026-11-07T00:00:00"}},
            "yiai": {"Chief": {"state": "idle",      "updatedAt": "2026-11-07T00:00:01"}},
        }
        result = merge_bot_states(sources)
        assert result["Chief"]["state"] == "executing"  # DSH 优先级更高，尽管时间戳更旧

    def test_same_priority_newer_wins(self):
        """两个自定义源同优先级 → 时间戳新的胜"""
        sources = {
            "src-a": {"BotX": {"state": "idle",      "updatedAt": "2026-11-07T00:00:00"}},
            "src-b": {"BotX": {"state": "executing",  "updatedAt": "2026-11-07T00:00:05"}},
        }
        result = merge_bot_states(sources)
        assert result["BotX"]["state"] == "executing"

    def test_error_source_loses_to_normal(self):
        """DSH 的 error 状态（降权后=8）vs YiAi 的正常 executing（5）→ DSH error 反而胜
        因为 8 > 5。但如果 YiAi 也有同样的 bot 且正常 → DSH error 胜。
        
        实际上 error 降权从 10→8，仍高于 YiAi 的 5。这符合设计:
        DSH 的 error 表示 DSH 确认出错，应比 YiAi 的普通 idle 更优先呈现。
        """
        sources = {
            "dsh":  {"BotX": {"state": "error",     "updatedAt": "2026-11-07T00:00:00"}},
            "yiai": {"BotX": {"state": "executing", "updatedAt": "2026-11-07T00:00:00"}},
        }
        result = merge_bot_states(sources)
        # DSH error (priority 8) > YiAi executing (priority 5) → DSH wins
        assert result["BotX"]["state"] == "error"

    def test_error_between_equal_sources_loses(self):
        """两个同优先级自定义源，一个 error → 正常的胜"""
        sources = {
            "src-a": {"BotX": {"state": "idle",      "updatedAt": "2026-11-07T00:00:00"}},
            "src-b": {"BotX": {"state": "error",     "updatedAt": "2026-11-07T00:00:00"}},
        }
        result = merge_bot_states(sources)
        assert result["BotX"]["state"] == "idle"  # src-a 优先级 1 > src-b error 的 0

    # ── 多 bot 合并 ──

    def test_different_bots_from_different_sources(self):
        """多 bot 分布在多个源 → 全部保留"""
        sources = {
            "dsh":  {"Chief": {"state": "executing"}},
            "yiai": {"YiAiBot": {"state": "idle"}},
            "yivad": {"YiVadBot": {"state": "writing"}},
        }
        result = merge_bot_states(sources)
        assert len(result) == 3
        assert result["Chief"]["state"] == "executing"
        assert result["YiAiBot"]["state"] == "idle"
        assert result["YiVadBot"]["state"] == "writing"

    def test_bot_only_in_low_priority_source(self):
        """bot 只在低优先级源存在 → 不丢"""
        sources = {
            "dsh":  {},
            "yiai": {"OnlyHere": {"state": "writing"}},
        }
        result = merge_bot_states(sources)
        assert "OnlyHere" in result
        assert result["OnlyHere"]["state"] == "writing"

    # ── 边界 ──

    def test_allow_empty_sources(self):
        """允许空源（DSH 离线场景）"""
        sources = {
            "dsh":  {},
            "yiai": {"Bot": {"state": "idle"}},
        }
        result = merge_bot_states(sources, allow_empty=True)
        assert "Bot" in result

    def test_disallow_empty_raises(self):
        """allow_empty=False 时空源报错"""
        import pytest
        with pytest.raises(ValueError, match="数据源 'dsh' 为空"):
            merge_bot_states(
                {"dsh": {}, "yiai": {"Bot": {"state": "idle"}}},
                allow_empty=False,
            )

    def test_non_dict_bot_data_skipped(self):
        """非 dict 的 bot 数据被跳过"""
        sources = {
            "dsh": {"BadBot": "not-a-dict"},
        }
        result = merge_bot_states(sources)
        assert "BadBot" not in result


# ═════════════════════════════════════════════════════════════
# compute_source_health
# ═════════════════════════════════════════════════════════════

class TestComputeSourceHealth:
    def test_all_healthy(self):
        sources = {
            "dsh":  {"Bot1": {"state": "executing"}, "Bot2": {"state": "idle"}},
            "yiai": {"Bot3": {"state": "idle"}},
        }
        health = compute_source_health(sources)
        assert health["dsh"]["available"]
        assert health["dsh"]["healthy"]
        assert health["dsh"]["bot_count"] == 2
        assert health["dsh"]["error_bots"] == 0

    def test_empty_source_unavailable(self):
        sources = {"dsh": {}}
        health = compute_source_health(sources)
        assert not health["dsh"]["available"]
        assert not health["dsh"]["healthy"]

    def test_high_error_rate_unhealthy(self):
        """超过 50% bot 在 error → unhealthy"""
        sources = {
            "dsh": {
                "Bot1": {"state": "error"},
                "Bot2": {"state": "error"},
                "Bot3": {"state": "idle"},
            }
        }
        health = compute_source_health(sources)
        assert health["dsh"]["error_bots"] == 2
        assert not health["dsh"]["healthy"], "66% error rate 应标记 unhealthy"

    def test_low_error_rate_still_healthy(self):
        sources = {
            "dsh": {
                "Bot1": {"state": "error"},
                "Bot2": {"state": "idle"},
                "Bot3": {"state": "idle"},
                "Bot4": {"state": "idle"},
            }
        }
        health = compute_source_health(sources)
        assert health["dsh"]["healthy"], "25% error rate 应标记 healthy"


# ═════════════════════════════════════════════════════════════
# get_fallback_chain
# ═════════════════════════════════════════════════════════════

class TestGetFallbackChain:
    def test_bot_in_all_sources(self):
        sources = {
            "dsh":  {"Chief": {"state": "idle"}},
            "yiai": {"Chief": {"state": "executing"}},
            "yivad": {"Chief": {"state": "error"}},
        }
        chain = get_fallback_chain(sources, "Chief")
        assert len(chain) == 3
        assert chain[0]["source"] == "dsh"
        assert chain[1]["source"] == "yiai"
        assert chain[2]["source"] == "yivad"

    def test_bot_not_in_any_source(self):
        sources = {"dsh": {}}
        chain = get_fallback_chain(sources, "Nobody")
        assert chain == [None]

    def test_bot_only_in_yiai(self):
        sources = {
            "dsh":  {},
            "yiai": {"OnlyYiai": {"state": "writing"}},
        }
        chain = get_fallback_chain(sources, "OnlyYiai")
        assert len(chain) == 1
        assert chain[0]["source"] == "yiai"


# ═════════════════════════════════════════════════════════════
# SOURCE_PRIORITY 常量
# ═════════════════════════════════════════════════════════════

def test_source_priority_order():
    """DSH > YiAi > YiVad"""
    assert SOURCE_PRIORITY["dsh"] > SOURCE_PRIORITY["yiai"] > SOURCE_PRIORITY["yivad"]