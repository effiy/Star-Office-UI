"""
共享 fixtures: 临时 mock 数据目录 & JSON 文件
用于 test_ws_unit / test_ws_integration / test_ws_resilience
"""
import json
import os
import sys

import pytest

# ws_server.py 在项目根目录，不在 backend/ 下
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


@pytest.fixture
def data_dir(tmp_path):
    """临时 mock 数据目录"""
    d = tmp_path / "dsh"
    d.mkdir()
    return d


@pytest.fixture
def mock_bots():
    """标准 5-bot mock 数据（含各楼层代表）"""
    return {
        "Chief":          {"state": "executing", "detail": "管理统筹"},
        "SU·测试·星验":   {"state": "idle",      "detail": "等待任务"},
        "SU·实时·闪电":   {"state": "executing", "detail": "实时推送"},
        "SU·UI·星绘":     {"state": "executing", "detail": "视觉绘制"},
        "mac·企鹅":       {"state": "error",     "detail": "连接异常"},
    }


@pytest.fixture
def bridge_state_json(data_dir, mock_bots):
    """bridge-state.json mock"""
    p = data_dir / "bridge-state.json"
    p.write_text(json.dumps(mock_bots, ensure_ascii=False))
    return p


@pytest.fixture
def inflight_json(data_dir):
    """inflight.json mock — Chief(s1) + 星验(s2) 活跃中
    ⚠️ get_active_bots() 把 turns 的 key 当作 session ID 查 bot_map"""
    p = data_dir / "inflight.json"
    p.write_text(json.dumps({
        "turns": {
            "s1": {"botId": "s1"},
            "s2": {"botId": "s2"},
        }
    }))
    return p


@pytest.fixture
def state_json(data_dir):
    """state.json mock — session → name 映射"""
    p = data_dir / "state.json"
    p.write_text(json.dumps({
        "bots": {
            "s1": {"name": "Chief"},
            "s2": {"name": "SU·测试·星验"},
            "s3": {"name": "SU·实时·闪电"},
            "s4": {"name": "SU·UI·星绘"},
            "s5": {"name": "mac·企鹅"},
        }
    }, ensure_ascii=False))
    return p


@pytest.fixture
def empty_inflight_json(data_dir):
    """空的 inflight.json"""
    p = data_dir / "inflight.json"
    p.write_text(json.dumps({"turns": {}}))
    return p


@pytest.fixture
def floor_registry_json(data_dir):
    """floor-registry.json mock"""
    p = data_dir / "floor-registry.json"
    p.write_text(json.dumps({
        "_meta": {"max_agents": 50, "default_floor": 2},
        "1F": ["Chief", "mac·企鹅"],
        "2F": ["SU·测试·星验", "SU·实时·闪电"],
        "3F": ["SU·UI·星绘"],
    }, ensure_ascii=False))
    return p