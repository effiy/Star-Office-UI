#!/usr/bin/env python3
"""DSH Bot → Pixel Office state bridge.

Reads DSH bot state from ~/.dsh/bot/state.json and inflight.json,
maps to pixel office agent IDs, and pushes states every 3 seconds.
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone

DSH_STATE_FILE = os.path.expanduser("~/.dsh/bot/state.json")
DSH_INFLIGHT_FILE = os.path.expanduser("~/.dsh/bot/inflight.json")
PIXEL_API = "http://127.0.0.1:19000"
JOIN_KEY = "ocj_example_team_01"

# DSH bot name → pixel office agentId mapping (fetched from /agents on startup)
AGENT_MAP = {}
CHIEF_AGENT_ID = "star"


def fetch_agent_map():
    """Fetch the pixel office agent IDs for all registered bots."""
    try:
        result = subprocess.run(
            ["curl", "-s", f"{PIXEL_API}/agents"],
            capture_output=True, text=True, timeout=5
        )
        agents = json.loads(result.stdout)
        for a in agents:
            if not a.get("isMain"):
                AGENT_MAP[a["name"]] = a["agentId"]
        print(f"[bridge] loaded {len(AGENT_MAP)} agent mappings")
    except Exception as e:
        print(f"[bridge] failed to load agent map: {e}")


def get_dsh_bot_states():
    """Read DSH state files and return {bot_name: state} dict.
    
    States: executing (in inflight) > writing (active segment) > idle.
    """
    states = {}
    now = datetime.now(timezone.utc)
    
    # Check inflight (actively running bots)
    inflight_bots = set()
    try:
        if os.path.exists(DSH_INFLIGHT_FILE):
            with open(DSH_INFLIGHT_FILE) as f:
                inflight = json.load(f)
            for sid, turn in inflight.get("turns", {}).items():
                bot_id = turn.get("botId", "")
                inflight_bots.add(bot_id)
    except Exception:
        pass
    
    # Read bot state
    try:
        if os.path.exists(DSH_STATE_FILE):
            with open(DSH_STATE_FILE) as f:
                data = json.load(f)
            for bid, bot in data.get("bots", {}).items():
                name = bot.get("name", "")
                if not name or name == "Chief":
                    continue
                
                segs = bot.get("segments", [])
                is_active = (bid in inflight_bots)
                has_active_seg = False
                
                if segs:
                    last = segs[-1]
                    if last.get("endedAt") is None or last.get("endedAt") == "active":
                        has_active_seg = True
                
                if is_active:
                    states[name] = "executing"
                elif has_active_seg:
                    states[name] = "writing"
                else:
                    states[name] = "idle"
    except Exception as e:
        print(f"[bridge] read DSH state error: {e}")
    
    return states


def push_agent_state(name: str, agent_id: str, state: str, detail: str = ""):
    """Push one agent's state to pixel office."""
    try:
        payload = json.dumps({
            "agentId": agent_id,
            "joinKey": JOIN_KEY,
            "state": state,
            "detail": detail or get_detail(state),
            "name": name,
        })
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", f"{PIXEL_API}/agent-push",
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=5
        )
        resp = json.loads(result.stdout)
        if not resp.get("ok"):
            print(f"  {name}: push failed - {resp.get('msg', 'unknown')}")
    except Exception as e:
        print(f"  {name}: push error - {e}")


def push_chief_state(state: str):
    """Push Chief's (star) state via /set_state."""
    try:
        subprocess.run(
            ["curl", "-s", "-X", "POST", f"{PIXEL_API}/set_state",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"state": state, "detail": get_detail(state)})],
            capture_output=True, timeout=5
        )
    except Exception:
        pass


def get_detail(state: str) -> str:
    return {
        "executing": "工作中…",
        "writing": "分析思考中…",
        "researching": "搜索资料中…",
        "syncing": "同步数据中…",
        "error": "出现错误",
        "idle": "待命中",
    }.get(state, "")


def main():
    print("[bridge] DSH → Pixel Office state bridge starting...")
    fetch_agent_map()
    
    print("[bridge] polling every 3s, Ctrl+C to stop")
    while True:
        try:
            states = get_dsh_bot_states()
            pushed = 0
            for name, state in states.items():
                agent_id = AGENT_MAP.get(name)
                if not agent_id:
                    continue
                push_agent_state(name, agent_id, state)
                pushed += 1
            
            # Also push Chief state based on inflight
            chief_busy = False
            try:
                if os.path.exists(DSH_INFLIGHT_FILE):
                    with open(DSH_INFLIGHT_FILE) as f:
                        inflight = json.load(f)
                    for sid, turn in inflight.get("turns", {}).items():
                        if turn.get("botId") == "session-78a256cd-9f5a-4762-84bf-d661e0d1dd13":
                            chief_busy = True
                            break
            except Exception:
                pass
            push_chief_state("executing" if chief_busy else "idle")
            
        except Exception as e:
            print(f"[bridge] loop error: {e}")
        
        time.sleep(3)


if __name__ == "__main__":
    main()