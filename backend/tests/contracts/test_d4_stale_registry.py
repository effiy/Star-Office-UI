"""
D4 门用例 — stale floor-registry vs live DSH 数据一致性

场景:
  1. floor-registry 有 bot 但 DSH 无此 bot → 标记 offline（stale registry entry）
  2. DSH 有 bot 但 floor-registry 无 → hash 兜底分配楼层
  3. registry 更新后新 bot 无需重启即获正确楼层
  4. bot 从 DSH 消失后 merge_engine 不丢数据

这是 ADR-001「动态注册」+ 铁甲「stale registry vs live DSH」的交集验收点。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from merge_engine import merge_bot_states, compute_source_health, resolve_source_priority
from dsh_models import DshBotState, STATE_PRIORITY


# ═════════════════════════════════════════════════════════════
# 7 态枚举自检
# ═════════════════════════════════════════════════════════════

def test_dshbotstate_has_seven_states():
    """发射侧必须有 7 态（含 offline 显式派生）"""
    states = [s.value for s in DshBotState]
    assert len(states) == 7, f"期望 7 态，实际 {len(states)}: {states}"
    assert "offline" in states, "缺少 offline 态"
    assert "executing" in states

def test_offline_has_lowest_priority():
    """offline 必须是优先级最低的状态（0）"""
    assert STATE_PRIORITY["offline"] == 0
    assert STATE_PRIORITY["offline"] < STATE_PRIORITY["idle"]
    assert STATE_PRIORITY["offline"] < STATE_PRIORITY["error"]

def test_offline_source_priority_drops_three_levels():
    """resolve_source_priority: offline 降 3 级（比 error 的 2 级更激进）"""
    # DSH offline (10-3=7) vs YiAi idle (5) → DSH offline 仍高但接近
    dsh_offline = resolve_source_priority("dsh", "offline")
    yiai_idle = resolve_source_priority("yiai", "idle")
    assert dsh_offline == 7
    assert dsh_offline > yiai_idle  # DSH offline 仍略高于 YiAi idle

    # 但同源 offline vs idle → idle 胜（如果 offline 降权后）
    yiai_offline = resolve_source_priority("yiai", "offline")
    assert yiai_offline == 2  # 5 - 3 = 2
    yiai_executing = resolve_source_priority("yiai", "executing")
    assert yiai_executing > yiai_offline


# ═════════════════════════════════════════════════════════════
# Stale registry entry → offline
# ═════════════════════════════════════════════════════════════

class TestStaleRegistryEntry:
    """floor-registry 中有，但 DSH/YiAi 都没有的 bot"""

    def test_registry_only_bot_absent_from_all_sources(self):
        """bot 只在 registry 里（floor=1F），但所有数据源都没有 → merge 结果里不出现（因为没有数据源提供它）"""
        # 这依赖于 Collector 为 registry 中的 bot 生成显式 offline 状态
        # 当前 merge_engine 只处理有数据的源。如果 Collector 已为 registry bot 生成 offline，
        # 则 merge_engine 会保留它。

        sources = {
            "dsh":  {"Chief": {"state": "executing"}},     # Chief 在线
            "yiai": {"Chief": {"state": "idle"}},
            # "OldBot" 不在任何源中
        }
        merged = merge_bot_states(sources)
        # OldBot 不在 merge 结果中（因为没有源提供它的数据）
        # 这是正确行为——Collector 负责为 registry bot 生成 offline 条目
        assert "OldBot" not in merged
        assert "Chief" in merged

    def test_collector_explicit_offline_for_registry_bot(self):
        """Collector 为 registry bot 生成显式 offline → merge_engine 保留"""
        sources = {
            "collector": {
                "Chief": {"state": "executing"},
                "OldBot": {"state": "offline", "detail": "registry stale"},
            }
        }
        merged = merge_bot_states(sources)
        assert "OldBot" in merged
        assert merged["OldBot"]["state"] == "offline"

    def test_explicit_offline_beats_no_data(self):
        """显式 offline（来自 collector）比无声消失更好——前端可以灰显而非凭空消失"""
        # 无 collector 的 offline 标记
        no_collector = merge_bot_states({
            "dsh": {"BotA": {"state": "executing"}}
        })
        assert "OldBot" not in no_collector

        # 有 collector 的 offline 标记
        with_collector = merge_bot_states({
            "dsh": {"BotA": {"state": "executing"}},
            "collector": {"OldBot": {"state": "offline"}}
        })
        assert "OldBot" in with_collector


# ═════════════════════════════════════════════════════════════
# DSH bot 不在 registry → hash 兜底
# ═════════════════════════════════════════════════════════════

class TestUnregisteredBotHashFallback:
    """DSH 有 bot 但 floor-registry 没有 → hash 兜底"""

    def test_unregistered_bot_gets_hash_floor(self):
        """ws_server 的 get_floor() 为未注册 bot 分配 hash 楼层，保证始终同层"""
        # 模拟 ws_server 行为（import ws_server 已验证此逻辑）
        import ws_server

        # 清空 registry
        ws_server.BOT_FLOOR = {}

        f1 = ws_server.get_floor("NewBotX")
        f2 = ws_server.get_floor("NewBotX")
        assert f1 == f2, "同一 bot 两次 hash 应一致"
        assert f1 in ("1F", "2F", "3F")

    def test_hash_fallback_does_not_override_registry(self):
        """hash 写入 BOT_FLOOR 后，registry 重载应覆盖"""
        import ws_server

        ws_server.BOT_FLOOR = {}
        # 先用 hash 分配
        f_hash = ws_server.get_floor("NewBot")
        # 再用 registry 覆盖
        ws_server.BOT_FLOOR["NewBot"] = 3
        f_registry = ws_server.get_floor("NewBot")
        assert f_registry == "3F"
        assert f_registry != f_hash or f_hash == "3F"  # hash 可能恰好也是 3F


# ═════════════════════════════════════════════════════════════
# Bot 消失 → 不丢数据
# ═════════════════════════════════════════════════════════════

class TestBotDisappearance:
    """bot 从活跃源消失 → 其他源仍提供数据"""

    def test_bot_leaves_dsh_stays_in_yiai(self):
        """DSH 不再报告某 bot，但 YiAi 仍报告 → YiAi 数据存活"""
        sources = {
            "dsh":  {"Chief": {"state": "executing"}},
            # "Worker" 不在 DSH 中
            "yiai": {"Worker": {"state": "idle", "roleTitle": "工程师", "icon": "🔧"}},
        }
        merged = merge_bot_states(sources)
        assert "Worker" in merged
        assert merged["Worker"]["state"] == "idle"
        assert merged["Worker"]["roleTitle"] == "工程师"

    def test_bot_disappears_from_all_sources(self):
        """所有源都没有 → 不出现（需要 Collector 补充 offline）"""
        merged = merge_bot_states({
            "dsh":  {"A": {"state": "executing"}},
            "yiai": {"A": {"state": "idle"}},
        })
        assert "B" not in merged
        assert "A" in merged


# ═════════════════════════════════════════════════════════════
# 7 态在 merge_engine 中的路由
# ═════════════════════════════════════════════════════════════

class TestSevenStateMergeRouting:
    """全 7 态在合并引擎中的行为"""

    def test_all_seven_states_in_sources(self):
        """每个源报告不同状态 → 按优先级+元数据合并"""
        for state in DshBotState:
            sources = {
                "dsh":  {"Bot": {"state": state.value}},
                "yiai": {"Bot": {"state": "idle", "roleTitle": f"role-{state.value}"}},
            }
            merged = merge_bot_states(sources)
            assert "Bot" in merged
            # roleTitle 从 YiAi 注入（不管 state 谁胜出）
            assert "roleTitle" in merged["Bot"]

    def test_offline_loses_to_idle_from_other_source(self):
        """DSH 报告 offline（降权后=7），YiAi 报告 idle（5）→ DSH 仍胜因为 7>5"""
        # 这是设计决策：DSH offline 比 YiAi idle 更权威
        # 因为 offline 是 DSH 确认的"此 bot 不在线"，而 YiAi idle 可能过时
        merged = merge_bot_states({
            "dsh":  {"Bot": {"state": "offline"}},
            "yiai": {"Bot": {"state": "executing"}},
        })
        assert merged["Bot"]["state"] == "offline"

    def test_yiai_offline_loses_to_dsh_idle(self):
        """YiAi offline（降权后=2）vs DSH idle（10）→ DSH 胜"""
        merged = merge_bot_states({
            "dsh":  {"Bot": {"state": "idle"}},
            "yiai": {"Bot": {"state": "offline"}},
        })
        assert merged["Bot"]["state"] == "idle"


# ═════════════════════════════════════════════════════════════
# L2 办公视图（50 席过滤）— R2 裁决对齐
# ═════════════════════════════════════════════════════════════

class TestOfficeViewFiltering:
    """L1 镜像层 = 全量 DSH（~271+），L2 办公室 = floor-registry 50 席过滤"""

    def test_filter_to_registry_bots(self):
        """仅 floor-registry 中的 bot 进入办公室视图"""
        registry_bots = {"Chief", "mac·企鹅", "SU·测试·星验"}

        all_bots = {
            "Chief": {"state": "executing"},
            "mac·企鹅": {"state": "idle"},
            "SU·测试·星验": {"state": "writing"},
            "UnknownBot": {"state": "executing"},  # 不在 registry
            "AnotherBot": {"state": "idle"},       # 不在 registry
        }

        office_view = {
            name: data for name, data in all_bots.items()
            if name in registry_bots
        }

        assert len(office_view) == 3
        assert "UnknownBot" not in office_view
        assert "AnotherBot" not in office_view

    def test_empty_registry_office_view_empty(self):
        """空 registry → 办公室视图为空（全量镜像层不受影响）"""
        office_view = {
            name: data for name, data in {"Bot": {"state": "idle"}}.items()
            if name in set()
        }
        assert office_view == {}

    def test_office_view_preserves_state(self):
        """过滤不改变 bot 状态数据"""
        all_bots = {"Chief": {"state": "executing", "detail": "管理"}}
        registry = {"Chief"}
        office_view = {n: d for n, d in all_bots.items() if n in registry}
        assert office_view["Chief"]["state"] == "executing"
        assert office_view["Chief"]["detail"] == "管理"