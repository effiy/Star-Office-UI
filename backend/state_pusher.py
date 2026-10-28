"""
Pixel Office state pusher — HTTP client for /agents, /agent-push, /set_state.

Extracted from dsh_bridge.py per UB-mode Stage 1 (瘦身).

Uses stdlib urllib (no extra dependencies) instead of shelling out to curl.
"""
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Optional

logger = logging.getLogger(__name__)

PIXEL_API = "http://127.0.0.1:19000"
JOIN_KEY = "ocj_example_team_01"
CHIEF_AGENT_ID = "star"
REQUEST_TIMEOUT = 5  # seconds

# ── State → human-readable label ────────────────────────────

STATE_LABELS: Dict[str, str] = {
    "executing":   "工作中…",
    "writing":     "分析思考中…",
    "researching": "搜索资料中…",
    "syncing":     "同步数据中…",
    "error":       "出现错误",
    "idle":        "待命中",
}


def get_detail(state: str) -> str:
    """Return a human-readable label for an agent state, or empty string."""
    return STATE_LABELS.get(state, "")


# ── Shared HTTP helpers (eliminates duplicate curl subprocess calls) ──

def _http_get(url: str) -> Optional[dict]:
    """HTTP GET → parsed JSON, or None on failure."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        logger.warning("GET %s failed: %s", url, e)
        return None


def _http_post(url: str, payload: dict) -> Optional[dict]:
    """HTTP POST with JSON body → parsed JSON response, or None on failure."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        logger.warning("POST %s failed: %s", url, e)
        return None


# ── Agent state push ─────────────────────────────────────────

def fetch_agent_map() -> Dict[str, str]:
    """
    Fetch the pixel office agent IDs for all registered bots.

    Returns a dict mapping bot display name → pixel office agentId.
    Non-main agents only; main agents share the singleton pixel office.
    """
    agents = _http_get(f"{PIXEL_API}/agents")
    if agents is None:
        logger.warning("failed to fetch agent map from pixel office")
        return {}

    mapping: Dict[str, str] = {}
    for a in agents:
        if isinstance(a, dict) and not a.get("isMain"):
            name = a.get("name")
            agent_id = a.get("agentId")
            if name and agent_id:
                mapping[name] = agent_id

    logger.info("loaded %d agent mappings", len(mapping))
    return mapping


def push_agent_state(
    name: str,
    agent_id: str,
    state: str,
    detail: str = "",
) -> bool:
    """
    Push one agent's state to the pixel office /agent-push endpoint.

    Returns True on success, False on failure.
    """
    payload = {
        "agentId": agent_id,
        "joinKey": JOIN_KEY,
        "state": state,
        "detail": detail or get_detail(state),
        "name": name,
    }
    resp = _http_post(f"{PIXEL_API}/agent-push", payload)
    if resp is None:
        logger.warning("%s: push failed (no response)", name)
        return False
    if not resp.get("ok"):
        logger.warning("%s: push rejected — %s", name, resp.get("msg", "unknown"))
        return False
    return True


def push_chief_state(state: str) -> bool:
    """
    Push the Chief agent's (star) state via /set_state.

    Returns True on success, False on failure.
    """
    payload = {"state": state, "detail": get_detail(state)}
    resp = _http_post(f"{PIXEL_API}/set_state", payload)
    if resp is None:
        logger.debug("chief state push failed (no response)")
        return False
    return resp.get("ok", False)