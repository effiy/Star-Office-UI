"""
DSH bot state reader — parses state.json and inflight.json.

Extracted from dsh_bridge.py per UB-mode Stage 1 (瘦身).

Usage:
    from state_reader import get_dsh_bot_states, is_chief_busy
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Set

DSH_STATE_FILE = Path.home() / ".dsh" / "bot" / "state.json"
DSH_INFLIGHT_FILE = Path.home() / ".dsh" / "bot" / "inflight.json"

# Chief's DSH session ID — used to detect when the Chief agent is busy.
CHIEF_SESSION_ID = "session-78a256cd-9f5a-4762-84bf-d661e0d1dd13"


def _read_json(path: Path) -> dict:
    """Read and parse a JSON file, returning {} on any failure."""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def get_inflight_bot_ids() -> Set[str]:
    """Return the set of bot IDs currently in-flight (active turns)."""
    inflight = _read_json(DSH_INFLIGHT_FILE)
    ids: Set[str] = set()
    for turn in inflight.get("turns", {}).values():
        bot_id = turn.get("botId", "")
        if bot_id:
            ids.add(bot_id)
    return ids


def is_chief_busy() -> bool:
    """Check whether the Chief agent has an active turn in inflight."""
    inflight = _read_json(DSH_INFLIGHT_FILE)
    for turn in inflight.get("turns", {}).values():
        if turn.get("botId") == CHIEF_SESSION_ID:
            return True
    return False


def get_dsh_bot_states() -> Dict[str, str]:
    """
    Read DSH state files and return {bot_name: state} dict.

    State priority: executing (in inflight) > writing (active segment) > idle.
    The Chief bot is excluded because its state is pushed separately via /set_state.
    """
    inflight_ids = get_inflight_bot_ids()
    states: Dict[str, str] = {}

    data = _read_json(DSH_STATE_FILE)
    for bid, bot in data.get("bots", {}).items():
        name = bot.get("name", "")
        if not name or name == "Chief":
            continue

        has_active_seg = False
        segs = bot.get("segments", [])
        if segs:
            last = segs[-1]
            if last.get("endedAt") is None or last.get("endedAt") == "active":
                has_active_seg = True

        if bid in inflight_ids:
            states[name] = "executing"
        elif has_active_seg:
            states[name] = "writing"
        else:
            states[name] = "idle"

    return states


# ── Legacy alias for backward compatibility ──────────────────
def read_dsh_state() -> Dict[str, str]:
    """Deprecated alias.  Use get_dsh_bot_states() instead."""
    return get_dsh_bot_states()