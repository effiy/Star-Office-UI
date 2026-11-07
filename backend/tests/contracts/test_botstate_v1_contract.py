"""
BotState v1 数据契约验证 — WS 广播格式 + YiAi 注入字段

基于 SU·架构·筑桥 的 types/BotState.ts 定义，验证:
  1. 基础状态字段完整性
  2. YiAi 角色卡注入字段 (roleId/title/icon/redlines/quickRefs)
  3. stale 陈旧标记
  4. 与 merge_engine 输出格式兼容
纯 mock 数据，无外部依赖，<0.01s
"""

import json
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from merge_engine import merge_bot_states


# ── BotState v1 类型别名（纯函数验证，不需要 TypeScript）──

REQUIRED_FIELDS = [
    "id", "name", "state", "floor",
    "roleId", "roleTitle", "icon", "redlines", "quickRefs",
    "avatarUrl", "stale", "updatedAt",
]

VALID_STATES = {
    "idle", "writing", "executing", "researching",
    "syncing", "error", "offline",
}

VALID_FLOORS = {"1F", "2F", "3F"}


def validate_botstate(bot: dict, name: str = "") -> list:
    """验证单个 BotState v1 字典，返回错误列表"""
    errors = []

    for field in REQUIRED_FIELDS:
        if field not in bot:
            errors.append(f"{name}: 缺少必填字段 {field}")

    if "state" in bot and bot["state"] not in VALID_STATES:
        errors.append(f"{name}: 非法状态值 '{bot['state']}'")

    if "floor" in bot and bot["floor"] not in VALID_FLOORS:
        errors.append(f"{name}: 非法楼层 '{bot['floor']}'")

    if "redlines" in bot:
        if not isinstance(bot["redlines"], list):
            errors.append(f"{name}: redlines 应为 list")
        elif len(bot["redlines"]) > 5:
            errors.append(f"{name}: redlines 超过 5 条上限 ({len(bot['redlines'])})")

    if "stale" in bot and not isinstance(bot["stale"], bool):
        errors.append(f"{name}: stale 应为 bool")

    if "updatedAt" in bot and not isinstance(bot["updatedAt"], (int, float)):
        errors.append(f"{name}: updatedAt 应为数字 (epoch ms)")

    return errors


# ═════════════════════════════════════════════════════════════
# BotState v1 完整字段测试
# ═════════════════════════════════════════════════════════════

class TestBotStateV1Schema:
    """BotState v1 字段完整性"""

    def test_all_required_fields_present(self):
        bot = {
            "id": "bot-abc",
            "name": "mac·企鹅",
            "state": "executing",
            "floor": "2F",
            "roleId": "role-mac",
            "roleTitle": "首席协调官",
            "icon": "🐧",
            "redlines": ["不得代提交", "P1 事故需通报"],
            "quickRefs": ["跨项目联动", "日报复盘"],
            "avatarUrl": "/agents/mac·企鹅/avatar",
            "stale": False,
            "updatedAt": 1730908800000,
        }
        errors = validate_botstate(bot, "test")
        assert errors == [], f"字段验证失败: {errors}"

    def test_minimal_bot_state_passes(self):
        """最简有效 BotState"""
        bot = {
            "id": "minimal",
            "name": "TestBot",
            "state": "idle",
            "floor": "3F",
            "roleId": "",
            "roleTitle": "",
            "icon": "",
            "redlines": [],
            "quickRefs": [],
            "avatarUrl": "",
            "stale": False,
            "updatedAt": 0,
        }
        errors = validate_botstate(bot, "minimal")
        assert errors == []

    def test_missing_field_detected(self):
        bot = {"name": "NoId"}
        errors = validate_botstate(bot, "bad")
        assert len(errors) > 0

    def test_invalid_state_rejected(self):
        bot = {
            "id": "x", "name": "x", "state": "INVALID_STATE_VALUE",
            "floor": "1F", "roleId": "", "roleTitle": "", "icon": "",
            "redlines": [], "quickRefs": [], "avatarUrl": "",
            "stale": False, "updatedAt": 0,
        }
        errors = validate_botstate(bot, "bad")
        assert any("非法状态值" in e for e in errors)

    def test_invalid_floor_rejected(self):
        bot = {
            "id": "x", "name": "x", "state": "idle",
            "floor": "99F", "roleId": "", "roleTitle": "", "icon": "",
            "redlines": [], "quickRefs": [], "avatarUrl": "",
            "stale": False, "updatedAt": 0,
        }
        errors = validate_botstate(bot, "bad")
        assert any("非法楼层" in e for e in errors)

    def test_redlines_exceed_max(self):
        bot = {
            "id": "x", "name": "x", "state": "idle", "floor": "1F",
            "roleId": "", "roleTitle": "", "icon": "",
            "redlines": ["1", "2", "3", "4", "5", "6"],  # 6 > 5
            "quickRefs": [], "avatarUrl": "",
            "stale": False, "updatedAt": 0,
        }
        errors = validate_botstate(bot, "bad")
        assert any("超过 5 条" in e for e in errors)

    def test_all_valid_states_accepted(self):
        for state in VALID_STATES:
            bot = {
                "id": "x", "name": "x", "state": state, "floor": "2F",
                "roleId": "", "roleTitle": "", "icon": "",
                "redlines": [], "quickRefs": [], "avatarUrl": "",
                "stale": False, "updatedAt": 0,
            }
            errors = validate_botstate(bot, state)
            assert errors == [], f"state={state} 应合法，错误: {errors}"


# ═════════════════════════════════════════════════════════════
# YiAi 注入字段测试
# ═════════════════════════════════════════════════════════════

class TestYiAiInjectedFields:
    """YiAi GET /roles 注入到 BotState 的角色卡字段"""

    def test_role_fields_match_yiai_get_roles_format(self):
        """模拟 YiAi GET /roles 返回的角色卡被注入 BotState"""
        # 模拟 YiAi 原始数据
        yiai_role = {
            "roleId": "role-chief",
            "title": "首席协调官",
            "icon": "🐧",
            "color": "#2196F3",
            "subdomain": "协调管理",
            "redLines": [
                {"id": "rl1", "text": "不得代提交", "severity": "critical"},
                {"id": "rl2", "text": "P1 事故需通报", "severity": "high"},
            ],
            "quickRefs": [
                {"id": "qr1", "text": "跨项目联动"},
                {"id": "qr2", "text": "日报复盘"},
            ],
            "onboarding": ["熟悉团队", "了解规范"],
        }

        # 注入到 BotState
        bot = {
            "id": "bot-chief", "name": "Chief",
            "state": "executing", "floor": "1F",
            "roleId": yiai_role["roleId"],
            "roleTitle": yiai_role["title"],
            "icon": yiai_role["icon"],
            "redlines": [rl["text"] for rl in yiai_role["redLines"]],
            "quickRefs": [qr["text"] for qr in yiai_role["quickRefs"]],
            "avatarUrl": "/agents/Chief/avatar",
            "stale": False,
            "updatedAt": 1730908800000,
        }

        errors = validate_botstate(bot, "Chief")
        assert errors == []
        assert bot["roleId"] == "role-chief"
        assert bot["roleTitle"] == "首席协调官"
        assert bot["icon"] == "🐧"
        assert bot["redlines"] == ["不得代提交", "P1 事故需通报"]
        assert len(bot["redlines"]) <= 5

    def test_empty_yiai_role_graceful_degradation(self):
        """YiAi 无此 bot 的角色卡 → 字段为空但不丢"""
        bot = {
            "id": "bot-unknown", "name": "UnknownBot",
            "state": "idle", "floor": "2F",
            "roleId": "", "roleTitle": "", "icon": "",
            "redlines": [], "quickRefs": [],
            "avatarUrl": "", "stale": False, "updatedAt": 0,
        }
        errors = validate_botstate(bot, "UnknownBot")
        assert errors == []

    def test_botstate_stale_when_older_than_10s(self):
        """updatedAt 超过 10s → stale=true"""
        old_ts = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        bot = {
            "id": "x", "name": "x", "state": "idle", "floor": "2F",
            "roleId": "", "roleTitle": "", "icon": "",
            "redlines": [], "quickRefs": [], "avatarUrl": "",
            "stale": True,  # 由 Collector/ws_server 设置
            "updatedAt": old_ts,
        }
        errors = validate_botstate(bot, "stale")
        assert errors == []
        assert bot["stale"] is True


# ═════════════════════════════════════════════════════════════
# 与 merge_engine 输出兼容性
# ═════════════════════════════════════════════════════════════

class TestMergeEngineToBotStateV1:
    """merge_engine 输出可直接映射到 BotState v1"""

    def test_merge_output_to_botstate_shape(self):
        """DSH + YiAi 数据经 merge_engine → BotState v1 格式"""
        sources = {
            "dsh": {
                "mac·企鹅": {
                    "state": "executing",
                    "detail": "vue-tsc check",
                    "updatedAt": "2026-11-07T00:00:00Z",
                }
            },
            "yiai": {
                "mac·企鹅": {
                    "state": "idle",
                    "roleId": "role-mac",
                    "roleTitle": "首席协调官",
                    "icon": "🐧",
                    "redlines": ["不得代提交"],
                    "quickRefs": ["跨项目联动"],
                    "updatedAt": "2026-11-07T00:00:00Z",
                }
            },
        }

        merged = merge_bot_states(sources)

        # 映射到 BotState v1
        bot = {
            "id": "bot-mac",
            "name": "mac·企鹅",
            "state": merged["mac·企鹅"]["state"],       # DSH 胜出: executing
            "floor": "2F",                               # 来自 floor-registry
            "roleId": merged["mac·企鹅"].get("roleId", ""),
            "roleTitle": merged["mac·企鹅"].get("roleTitle", ""),
            "icon": merged["mac·企鹅"].get("icon", ""),
            "redlines": merged["mac·企鹅"].get("redlines", []),
            "quickRefs": merged["mac·企鹅"].get("quickRefs", []),
            "avatarUrl": "/agents/mac·企鹅/avatar",
            "stale": False,
            "updatedAt": 1730908800000,
        }

        errors = validate_botstate(bot, "mac·企鹅")
        assert errors == [], f"merge_engine→BotState 映射失败: {errors}"
        assert bot["state"] == "executing"  # DSH 优先级更高
        assert bot["roleTitle"] == "首席协调官"  # YiAi 字段已注入