"""
ws_server 纯函数单元测试

测试范围: load_floor_registry / get_floor / get_floor_num /
         compute_floor_summary / get_state_snapshot / load_bot_names / get_active_bots
不启动 WebSocket 服务，全部通过 mock 文件路径覆盖。
"""

import json
import os
import sys
from pathlib import Path

import ws_server


# ═════════════════════════════════════════════════════════════
# load_floor_registry
# ═════════════════════════════════════════════════════════════

class TestLoadFloorRegistry:
    """load_floor_registry() 单元测试"""

    def test_loads_all_floors(self, monkeypatch, floor_registry_json):
        """正常加载楼层注册表"""
        monkeypatch.setattr(ws_server, "FLOOR_REGISTRY_FILE", str(floor_registry_json))
        ws_server.load_floor_registry()

        assert ws_server.BOT_FLOOR["Chief"] == 1
        assert ws_server.BOT_FLOOR["SU·测试·星验"] == 2
        assert ws_server.BOT_FLOOR["SU·UI·星绘"] == 3
        assert ws_server.MAX_AGENTS == 50
        assert len(ws_server.BOT_FLOOR) == 5

    def test_missing_file_no_crash(self, monkeypatch, data_dir):
        """floor-registry.json 不存在时不崩溃"""
        missing = str(data_dir / "no-such-file.json")
        monkeypatch.setattr(ws_server, "FLOOR_REGISTRY_FILE", missing)

        # 不应抛出异常
        ws_server.load_floor_registry()

    def test_corrupted_json_no_crash(self, monkeypatch, data_dir):
        """损坏的 JSON 不崩溃"""
        bad = data_dir / "bad-registry.json"
        bad.write_text("not valid {{{")
        monkeypatch.setattr(ws_server, "FLOOR_REGISTRY_FILE", str(bad))

        ws_server.load_floor_registry()

    def test_empty_registry(self, monkeypatch, data_dir):
        """空注册表（无楼层数据）"""
        p = data_dir / "empty-registry.json"
        p.write_text(json.dumps({"_meta": {"max_agents": 30}}))
        monkeypatch.setattr(ws_server, "FLOOR_REGISTRY_FILE", str(p))

        ws_server.load_floor_registry()
        assert ws_server.MAX_AGENTS == 30


# ═════════════════════════════════════════════════════════════
# get_floor / get_floor_num
# ═════════════════════════════════════════════════════════════

class TestGetFloor:
    """get_floor() 楼层分配测试"""

    def test_registered_bot_returns_correct_floor(self, monkeypatch, floor_registry_json):
        """已在注册表中的 bot 返回正确楼层"""
        monkeypatch.setattr(ws_server, "FLOOR_REGISTRY_FILE", str(floor_registry_json))
        ws_server.load_floor_registry()

        assert ws_server.get_floor("Chief") == "1F"
        assert ws_server.get_floor("SU·测试·星验") == "2F"
        assert ws_server.get_floor("SU·UI·星绘") == "3F"

    def test_unknown_bot_hash_fallback(self, monkeypatch, floor_registry_json):
        """未注册 bot 用 hash 兜底，同一 bot 始终同层"""
        monkeypatch.setattr(ws_server, "FLOOR_REGISTRY_FILE", str(floor_registry_json))
        ws_server.load_floor_registry()

        f1 = ws_server.get_floor("UnknownBot-X")
        f2 = ws_server.get_floor("UnknownBot-X")
        assert f1 == f2, "同一 bot 两次调用应返回相同楼层"
        assert f1 in ("1F", "2F", "3F")

    def test_unknown_bot_hash_saves_to_floor_dict(self, monkeypatch, floor_registry_json):
        """hash 兜底后写入 BOT_FLOOR，后续直接命中"""
        monkeypatch.setattr(ws_server, "FLOOR_REGISTRY_FILE", str(floor_registry_json))
        ws_server.load_floor_registry()

        ws_server.get_floor("NewBot99")
        assert "NewBot99" in ws_server.BOT_FLOOR


class TestGetFloorNum:
    """get_floor_num() 楼层编号测试"""

    def test_known_bot(self, monkeypatch, floor_registry_json):
        monkeypatch.setattr(ws_server, "FLOOR_REGISTRY_FILE", str(floor_registry_json))
        ws_server.load_floor_registry()

        assert ws_server.get_floor_num("Chief") == 1

    def test_unknown_bot(self, monkeypatch, floor_registry_json):
        monkeypatch.setattr(ws_server, "FLOOR_REGISTRY_FILE", str(floor_registry_json))
        ws_server.load_floor_registry()

        n = ws_server.get_floor_num("NobodyHere")
        assert n in (1, 2, 3)


# ═════════════════════════════════════════════════════════════
# compute_floor_summary
# ═════════════════════════════════════════════════════════════

class TestComputeFloorSummary:
    """compute_floor_summary() 楼层统计测试"""

    def test_empty_states(self, monkeypatch, floor_registry_json):
        monkeypatch.setattr(ws_server, "FLOOR_REGISTRY_FILE", str(floor_registry_json))
        ws_server.load_floor_registry()

        summary = ws_server.compute_floor_summary({})
        assert summary == {1: 0, 2: 0, 3: 0}

    def test_all_idle_counts_zero(self, monkeypatch, floor_registry_json):
        monkeypatch.setattr(ws_server, "FLOOR_REGISTRY_FILE", str(floor_registry_json))
        ws_server.load_floor_registry()

        states = {
            "Chief": {"state": "idle"},
            "SU·测试·星验": {"state": "idle"},
        }
        summary = ws_server.compute_floor_summary(states)
        assert summary[1] == 0
        assert summary[2] == 0

    def test_mixed_states(self, monkeypatch, floor_registry_json):
        monkeypatch.setattr(ws_server, "FLOOR_REGISTRY_FILE", str(floor_registry_json))
        ws_server.load_floor_registry()

        states = {
            "Chief": {"state": "executing"},     # 1F, active
            "SU·测试·星验": {"state": "executing"},  # 2F, active
            "SU·UI·星绘": {"state": "idle"},      # 3F, idle
        }
        summary = ws_server.compute_floor_summary(states)
        assert summary[1] == 1
        assert summary[2] == 1
        assert summary[3] == 0

    def test_inflight_overrides_idle_in_bridge(self, monkeypatch, floor_registry_json):
        """inflight 活跃的 bot 即使 bridge 里 idle，统计也算活跃"""
        monkeypatch.setattr(ws_server, "FLOOR_REGISTRY_FILE", str(floor_registry_json))
        ws_server.load_floor_registry()

        # 这种情况在 get_state_snapshot 合并后才会出现
        states = {
            "Chief": {"state": "executing"},
            "SU·测试·星验": {"state": "executing"},  # inflight 覆盖了 bridge 的 idle
        }
        summary = ws_server.compute_floor_summary(states)
        assert summary[1] + summary[2] + summary[3] == 2


# ═════════════════════════════════════════════════════════════
# load_bot_names
# ═════════════════════════════════════════════════════════════

class TestLoadBotNames:
    """load_bot_names() 名册加载测试"""

    def test_loads_session_to_name_map(self, monkeypatch, state_json):
        monkeypatch.setattr(ws_server, "STATE_FILE", str(state_json))
        ws_server.load_bot_names()

        assert ws_server.bot_map["s1"] == "Chief"
        assert ws_server.bot_map["s3"] == "SU·实时·闪电"
        assert len(ws_server.bot_map) == 5

    def test_missing_state_file_no_crash(self, monkeypatch, data_dir):
        monkeypatch.setattr(ws_server, "STATE_FILE", str(data_dir / "no-state.json"))
        ws_server.load_bot_names()


# ═════════════════════════════════════════════════════════════
# get_active_bots
# ═════════════════════════════════════════════════════════════

class TestGetActiveBots:
    """get_active_bots() 活跃 bot 检测测试"""

    def test_returns_active_bot_names(self, monkeypatch, inflight_json, state_json):
        monkeypatch.setattr(ws_server, "STATE_FILE", str(state_json))
        monkeypatch.setattr(ws_server, "INFLIGHT_FILE", str(inflight_json))

        ws_server.load_bot_names()
        active = ws_server.get_active_bots()

        assert "Chief" in active
        assert "SU·测试·星验" in active
        assert "SU·实时·闪电" not in active  # 不在 inflight 中

    def test_empty_inflight_returns_empty_set(self, monkeypatch, empty_inflight_json, state_json):
        monkeypatch.setattr(ws_server, "STATE_FILE", str(state_json))
        monkeypatch.setattr(ws_server, "INFLIGHT_FILE", str(empty_inflight_json))

        ws_server.load_bot_names()
        active = ws_server.get_active_bots()
        assert active == set()

    def test_missing_inflight_returns_empty_set(self, monkeypatch, data_dir, state_json):
        monkeypatch.setattr(ws_server, "STATE_FILE", str(state_json))
        monkeypatch.setattr(ws_server, "INFLIGHT_FILE", str(data_dir / "no-inflight.json"))

        ws_server.load_bot_names()
        active = ws_server.get_active_bots()
        assert active == set()

    def test_corrupted_inflight_returns_empty_set(self, monkeypatch, data_dir, state_json):
        monkeypatch.setattr(ws_server, "STATE_FILE", str(state_json))
        bad = data_dir / "bad-inflight.json"
        bad.write_text("not json {{{")
        monkeypatch.setattr(ws_server, "INFLIGHT_FILE", str(bad))

        ws_server.load_bot_names()
        active = ws_server.get_active_bots()
        assert active == set()


# ═════════════════════════════════════════════════════════════
# get_state_snapshot
# ═════════════════════════════════════════════════════════════

class TestGetStateSnapshot:
    """get_state_snapshot() 状态快照合并测试"""

    def test_bridge_only(self, monkeypatch, bridge_state_json, data_dir):
        """只有 bridge-state.json，无 inflight"""
        monkeypatch.setattr(ws_server, "BRIDGE_STATE_FILE", str(bridge_state_json))
        monkeypatch.setattr(ws_server, "INFLIGHT_FILE", str(data_dir / "no-inflight.json"))
        monkeypatch.setattr(ws_server, "STATE_FILE", str(data_dir / "no-state.json"))

        snapshot = ws_server.get_state_snapshot()
        assert snapshot["Chief"]["state"] == "executing"
        assert "SU·测试·星验" in snapshot

    def test_inflight_overrides_idle_in_bridge(self, monkeypatch, bridge_state_json, inflight_json, state_json):
        """inflight 活跃的 bot 覆盖 bridge 的 idle 状态"""
        monkeypatch.setattr(ws_server, "BRIDGE_STATE_FILE", str(bridge_state_json))
        monkeypatch.setattr(ws_server, "INFLIGHT_FILE", str(inflight_json))
        monkeypatch.setattr(ws_server, "STATE_FILE", str(state_json))

        ws_server.load_bot_names()
        snapshot = ws_server.get_state_snapshot()

        # SU·测试·星验 在 bridge 里是 idle，但在 inflight 里活跃 → 应变为 executing
        assert snapshot["SU·测试·星验"]["state"] == "executing"

    def test_missing_bridge_no_crash(self, monkeypatch, data_dir, empty_inflight_json, state_json):
        """bridge-state.json 不存在时不崩溃"""
        monkeypatch.setattr(ws_server, "BRIDGE_STATE_FILE", str(data_dir / "no-bridge.json"))
        monkeypatch.setattr(ws_server, "INFLIGHT_FILE", str(empty_inflight_json))
        monkeypatch.setattr(ws_server, "STATE_FILE", str(state_json))

        snapshot = ws_server.get_state_snapshot()
        assert isinstance(snapshot, dict)

    def test_corrupted_bridge_no_crash(self, monkeypatch, data_dir, empty_inflight_json, state_json):
        """损坏的 bridge-state.json 不崩溃"""
        bad = data_dir / "bad-bridge.json"
        bad.write_text("{{{ bad json")
        monkeypatch.setattr(ws_server, "BRIDGE_STATE_FILE", str(bad))
        monkeypatch.setattr(ws_server, "INFLIGHT_FILE", str(empty_inflight_json))
        monkeypatch.setattr(ws_server, "STATE_FILE", str(state_json))

        snapshot = ws_server.get_state_snapshot()
        assert isinstance(snapshot, dict)