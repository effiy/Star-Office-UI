"""
DSH 数据契约验证 — 基于 dsh_models.py 的 Pydantic Schema

验证 DSH 原始数据 (state.json / inflight.json) 格式合规性，
以及 Bridge 输出格式 (DsBotStatesResponse / MergedBotState) 校验。
"""

import json
import os
import sys
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dsh_models import (
    DshBotState,
    DshSegment,
    DshBotEntry,
    DshStateFile,
    DshTurn,
    DshInflightFile,
    DsBotStatesResponse,
    BotStateDetail,
    MergedBotState,
    STATE_PRIORITY,
    AgentPushRequest,
    BridgeHealthResponse,
)


# ═════════════════════════════════════════════════════════════
# DSH State Enums & Priority
# ═════════════════════════════════════════════════════════════

class TestDshStateEnum:
    def test_state_priority_order(self):
        """executing > writing > researching > syncing > error > idle"""
        priorities = list(STATE_PRIORITY.values())
        assert priorities == sorted(priorities, reverse=True), \
            "STATE_PRIORITY 应按降序排列"

    def test_all_states_have_priority(self):
        for state in DshBotState:
            assert state.value in STATE_PRIORITY, \
                f"{state.value} 缺少优先级定义"


# ═════════════════════════════════════════════════════════════
# DSH Raw File Schemas
# ═════════════════════════════════════════════════════════════

class TestDshStateFile:
    """~/.dsh/bot/state.json 格式验证"""

    def test_valid_state_file(self):
        data = {
            "bots": {
                "bot-1": {
                    "name": "Chief",
                    "segments": [
                        {"segmentId": "seg-1", "startedAt": "2026-11-07T00:00:00Z",
                         "endedAt": "active", "kind": "chat"}
                    ]
                }
            }
        }
        parsed = DshStateFile(**data)
        assert "bot-1" in parsed.bots
        assert parsed.bots["bot-1"].name == "Chief"
        assert parsed.bots["bot-1"].segments[0].kind == "chat"

    def test_empty_state_file(self):
        parsed = DshStateFile()
        assert parsed.bots == {}

    def test_bot_without_segments(self):
        data = {"bots": {"bot-1": {"name": "MinimalBot"}}}
        parsed = DshStateFile(**data)
        assert parsed.bots["bot-1"].segments == []

    def test_missing_name_defaults_to_empty(self):
        data = {"bots": {"bot-1": {"segments": []}}}
        parsed = DshStateFile(**data)
        assert parsed.bots["bot-1"].name == ""

    def test_segment_active_when_endedAt_is_None(self):
        """endedAt=None → 分段仍在进行中"""
        seg = DshSegment(startedAt="2026-01-01T00:00:00Z", endedAt=None)
        assert seg.endedAt is None


class TestDshInflightFile:
    """~/.dsh/bot/inflight.json 格式验证"""

    def test_valid_inflight(self):
        data = {
            "turns": {
                "t1": {"botId": "bot-chief", "botName": "Chief",
                       "startedAt": "2026-11-07T00:00:00Z", "status": "running"}
            }
        }
        parsed = DshInflightFile(**data)
        assert "t1" in parsed.turns
        assert parsed.turns["t1"].botId == "bot-chief"
        assert parsed.turns["t1"].botName == "Chief"

    def test_empty_inflight(self):
        parsed = DshInflightFile()
        assert parsed.turns == {}

    def test_invalid_turn_missing_botId(self):
        """botId 为必需字段且默认空字符串，不抛异常"""
        parsed = DshInflightFile(turns={"tx": {}})
        assert parsed.turns["tx"].botId == ""


# ═════════════════════════════════════════════════════════════
# Bridge Output Schemas
# ═════════════════════════════════════════════════════════════

class TestDsBotStatesResponse:
    """GET /ds-bot-states 响应格式验证"""

    def test_valid_response(self):
        data = {
            "bots": {
                "Chief": {"state": "executing", "detail": "工作中", "updatedAt": "2026-11-07T00:00:00Z"}
            },
            "count": 1,
            "updated_at": "2026-11-07T00:00:00Z",
            "source": "bridge",
        }
        parsed = DsBotStatesResponse(**data)
        assert parsed.bots["Chief"].state == DshBotState.EXECUTING
        assert parsed.count == 1
        assert parsed.source == "bridge"

    def test_default_source_is_bridge(self):
        parsed = DsBotStatesResponse()
        assert parsed.source == "bridge"

    def test_count_auto_computed(self):
        """count 当前不从 bots 自动计算——由调用方设置"""
        parsed = DsBotStatesResponse(bots={"a": {}, "b": {}}, count=2)
        assert parsed.count == 2

    def test_bot_state_accepts_all_enum_values(self):
        for state in DshBotState:
            parsed = BotStateDetail(state=state, detail="test")
            assert parsed.state == state


class TestMergedBotState:
    """app.py GET /ds-bot-states 合并后的响应格式"""

    def test_merged_state_sources(self):
        for src in ("local", "bridge", "merged"):
            parsed = MergedBotState(state="idle", stateSource=src)
            assert parsed.stateSource == src

    def test_default_state_source(self):
        parsed = MergedBotState()
        assert parsed.stateSource == "local"

    def test_updated_at_set(self):
        ts = datetime.now(timezone.utc).isoformat()
        parsed = MergedBotState(state="idle", updatedAt=ts)
        assert parsed.updatedAt == ts


# ═════════════════════════════════════════════════════════════
# Agent Push / Chief State
# ═════════════════════════════════════════════════════════════

class TestAgentPushRequest:
    def test_valid_push(self):
        req = AgentPushRequest(
            agentId="agent-1", joinKey="jk", state="executing",
            detail="工作中", name="TestBot"
        )
        assert req.agentId == "agent-1"
        assert req.state == "executing"

    def test_minimal_push(self):
        req = AgentPushRequest(agentId="a1", joinKey="k1", state="idle")
        assert req.detail == ""
        assert req.name == ""


class TestBridgeHealthResponse:
    def test_default_health(self):
        resp = BridgeHealthResponse()
        assert resp.status == "ok"
        assert resp.uptime == 0
        assert resp.cached_bots == 0
        assert resp.poll_interval == 3


# ═════════════════════════════════════════════════════════════
# 版本兼容性 — 确保所有 model 向后兼容
# ═════════════════════════════════════════════════════════════

def test_all_models_accept_extra_fields():
    """所有 Schema 应容忍未知字段（向前兼容）"""
    extra = {"bots": {"x": {}}, "count": 0, "extra_field": "should_be_ignored"}
    parsed = DsBotStatesResponse(**extra)
    assert parsed.count == 0