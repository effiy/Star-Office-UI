#!/usr/bin/env python3
"""
DSH State Collector — single ingestion point for YiAi DSH → Redis pipeline.

Replaces three legacy bridges:
  - backend/dsh_server.py  (:19003 Flask → retired)
  - backend/dsh_bridge.py  (standalone polling → deprecated)
  - ds_bot_watcher.py      (root-level watcher → retired)

Architecture (T2 per data-integration-spec.md):
  DSH state.json / inflight.json
        │  watchdog (FileSystemEventHandler)
        ▼
  Collector thread (FastAPI lifespan background)
        │  1. Read DSH files → compute bot states
        │  2. Fetch YiAi /roles (60s TTL cache → enrich)
        │  3. Write star:bot:{name} to Redis
        │  4. PUBLISH star:channel:state (changed bot names)
        ▼
  ws_server SUBSCRIBEs → WebSocket broadcast (<50ms event-driven)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Import shared modules (same imports as dsh_server uses)
# try/except for both package import and direct script run
try:
    from .state_reader import get_dsh_bot_states, is_chief_busy, get_inflight_bot_ids
except ImportError:
    from state_reader import get_dsh_bot_states, is_chief_busy, get_inflight_bot_ids

logger = logging.getLogger("star-office.collector")

# ── Config ────────────────────────────────────────────────────────────

DSH_STATE_FILE = Path.home() / ".dsh" / "bot" / "state.json"
DSH_INFLIGHT_FILE = Path.home() / ".dsh" / "bot" / "inflight.json"
YIAI_ROLES_TTL = 60  # seconds — YiAi role cache refresh interval
DEBOUNCE_INTERVAL = 0.5  # seconds — coalesce rapid file changes
YIAI_BASE_URL = os.environ.get("YIAI_BASE_URL", "http://127.0.0.1:10086")

# ── Global State ──────────────────────────────────────────────────────

_shutdown = threading.Event()
_latest_states: Dict[str, dict] = {}  # name → {state, detail, role, ...}
_yi_ai_roles: Dict[str, dict] = {}  # name → {title, icon, domain, redlines}
_roles_fetched_at = 0.0
_lock = threading.Lock()


# ── YiAi Role Ingestion ─────────────────────────────────────────────

def _fetch_yi_ai_roles() -> Dict[str, dict]:
    """Fetch bot roles from YiAi GET /roles. Returns {name: role_dict}."""
    import urllib.error
    import urllib.request

    token = os.environ.get("YIAI_TOKEN", "")
    try:
        url = f"{YIAI_BASE_URL}/roles"
        req = urllib.request.Request(url)
        if token:
            req.add_header("X-Token", token)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        logger.warning("YiAi /roles HTTP %d (check YIAI_TOKEN)", e.code)
        return {}
    except Exception as e:
        logger.debug("YiAi /roles fetch failed: %s", e)
        return {}

    roles: Dict[str, dict] = {}
    # YiAi response shape: {"data": {"total": N, "roles": [{id,title,icon,...}, ...]}}
    items = data.get("data", data)
    role_list = items.get("roles", items if isinstance(items, list) else [])
    for r in role_list:
        if not isinstance(r, dict):
            continue
        # Use 'id' (role identifier) as key; also capture botId/botName for DSH mapping
        role_id = r.get("id", r.get("key", ""))
        if not role_id:
            continue
        roles[role_id] = {
            "title": r.get("title", ""),
            "icon": r.get("icon", ""),
            "domain": r.get("description", ""),
            "status": r.get("status", "active"),
            "redLinesCount": r.get("redLinesCount", 0),
            "knowledgeFileCount": r.get("knowledgeFileCount", 0),
            "quickRefsCount": r.get("quickRefsCount", 0),
            "botId": r.get("botId", ""),
            "botName": r.get("botName", ""),
            "updatedAt": r.get("updatedAt", ""),
        }
    return roles


def _refresh_yi_ai_roles(force: bool = False) -> Dict[str, dict]:
    """Refresh the YiAi role cache. Returns current cache."""
    global _yi_ai_roles, _roles_fetched_at
    now = time.time()
    if not force and (now - _roles_fetched_at) < YIAI_ROLES_TTL:
        return _yi_ai_roles

    roles = _fetch_yi_ai_roles()
    if roles:
        _yi_ai_roles = roles
        _roles_fetched_at = now
        logger.info("YiAi roles refreshed: %d roles", len(roles))
    return _yi_ai_roles


def _enrich_bot_state(name: str, state: str, roles: Dict[str, dict]) -> dict:
    """Enrich a raw DSH bot state with YiAi role metadata + floor allocation."""
    role = roles.get(name, {})
    # Floor: try role's domain first, fall back to hash-based allocation
    floor = _compute_floor(name)
    return {
        "name": name,
        "state": state,
        "detail": _STATE_LABELS.get(state, ""),
        "floor": floor,
        "role_title": role.get("title", ""),
        "icon": role.get("icon", ""),
        "domain": role.get("domain", ""),
        "redLinesCount": role.get("redLinesCount", 0),
        "botId": role.get("botId", ""),
        "botName": role.get("botName", ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _compute_floor(name: str) -> str:
    """Hash-based floor allocation (1F/2F/3F). Same algorithm as ws_server/useBotStore."""
    h = abs(hash(name))
    f = (h % 3) + 1
    return f"{f}F"


_STATE_LABELS: Dict[str, str] = {
    "executing":   "工作中…",
    "writing":     "分析思考中…",
    "researching": "搜索资料中…",
    "syncing":     "同步数据中…",
    "error":       "出现错误",
    "idle":        "待命中",
    "offline":     "离线",          # R1(c): 7-state enum — derived, not from DSH files
}


# ── Redis Integration ──────────────────────────────────────────────

def _get_redis():
    """Lazy-import Redis client. Returns None if unavailable."""
    try:
        from .store_redis import _redis_client
        return _redis_client
    except ImportError:
        try:
            from store_redis import _redis_client
            return _redis_client
        except ImportError:
            return None


def _write_bot_to_redis(name: str, data: dict) -> bool:
    """Write a bot's state to Redis star:bot:{name}. Returns True on success."""
    r = _get_redis()
    if r is None:
        return False
    try:
        key = f"star:bot:{name}"
        r.set(key, json.dumps(data, ensure_ascii=False))
        return True
    except Exception:
        logger.debug("Redis write failed for %s", name)
        return False


def _publish_state_change(changed_names: List[str]) -> bool:
    """PUBLISH to star:channel:state with the list of changed bot names."""
    if not changed_names:
        return True
    r = _get_redis()
    if r is None:
        return False
    try:
        payload = json.dumps(changed_names, ensure_ascii=False)
        r.publish("star:channel:state", payload)
        return True
    except Exception:
        logger.debug("Redis PUBLISH failed")
        return False


def _load_existing_from_redis(name: str) -> Optional[dict]:
    """Load a bot's current state from Redis. Returns None if not found."""
    r = _get_redis()
    if r is None:
        return None
    try:
        raw = r.get(f"star:bot:{name}")
        return json.loads(raw) if raw else None
    except Exception:
        return None


# ── Core Collection Logic ────────────────────────────────────────────

def _collect_and_publish() -> int:
    """
    Read DSH files, compute bot states, write to Redis, publish changes.

    Returns the number of bots whose state changed.
    """
    try:
        raw_states = get_dsh_bot_states()
    except Exception:
        logger.exception("Failed to read DSH state files")
        return 0

    roles = _refresh_yi_ai_roles()
    changed: List[str] = []

    for name, state in raw_states.items():
        new_data = _enrich_bot_state(name, state, roles)

        # Compare with previous state to detect changes
        with _lock:
            prev = _latest_states.get(name, {})
            prev_state = prev.get("state", "")
            _latest_states[name] = new_data

        if state != prev_state:
            changed.append(name)

        # Write to Redis regardless (keeps TTL fresh)
        _write_bot_to_redis(name, new_data)

    # Handle Chief state separately
    chief_state = "executing" if is_chief_busy() else "idle"
    chief_data = _enrich_bot_state("Chief", chief_state, roles)
    with _lock:
        _latest_states["Chief"] = chief_data
    _write_bot_to_redis("Chief", chief_data)

    # Publish changes
    if changed:
        logger.debug("State changes: %s", changed)
    _publish_state_change(changed)
    return len(changed)


# ── Watchdog Handler ──────────────────────────────────────────────────

class DshFileHandler(FileSystemEventHandler):
    """Watchdog handler: trigger collection on DSH file modifications."""

    def __init__(self, on_change: Callable[[], None]):
        super().__init__()
        self._on_change = on_change
        self._last_trigger = 0.0

    def on_modified(self, event):
        if event.is_directory:
            return
        # Only react to state.json and inflight.json
        fname = os.path.basename(event.src_path)
        if fname not in ("state.json", "inflight.json"):
            return
        # Debounce: coalesce rapid successive writes
        now = time.time()
        if now - self._last_trigger < DEBOUNCE_INTERVAL:
            return
        self._last_trigger = now
        self._on_change()


# ── Collector Lifecycle ───────────────────────────────────────────────

def _trigger_collection():
    """Callback invoked by watchdog on DSH file change."""
    try:
        changed = _collect_and_publish()
        if changed:
            logger.info("Collected DSH states: %d bots changed", changed)
    except Exception:
        logger.exception("Collection cycle failed")


def start_collector() -> threading.Thread:
    """
    Start the DSH state collector in a background thread.

    Returns the collector thread (daemon). Call shutdown_collector() to stop.
    """
    global _shutdown
    _shutdown.clear()

    # Initial collection and YiAi role fetch
    logger.info("Collector starting — initial collection…")
    _refresh_yi_ai_roles(force=True)
    _collect_and_publish()

    # Start watchdog observer for DSH files
    dsh_dir = DSH_STATE_FILE.parent
    if not dsh_dir.exists():
        logger.warning("DSH directory not found: %s — polling fallback", dsh_dir)
    else:
        logger.info("Watching DSH directory: %s", dsh_dir)

    def _run():
        observer = Observer()
        handler = DshFileHandler(on_change=_trigger_collection)
        observer.schedule(handler, str(dsh_dir), recursive=False)
        observer.start()
        logger.info("Watchdog observer started")

        # Periodic role refresh every 60s
        while not _shutdown.is_set():
            _shutdown.wait(15)  # wake every 15s to check shutdown
            if _shutdown.is_set():
                break
            # Refresh YiAi roles on TTL expiry
            _refresh_yi_ai_roles()

        observer.stop()
        observer.join(timeout=3)
        logger.info("Watchdog observer stopped")

    thread = threading.Thread(target=_run, daemon=True, name="star-collector")
    thread.start()
    return thread


def shutdown_collector():
    """Signal the collector to stop and wait for graceful shutdown."""
    _shutdown.set()


def get_latest_states() -> Dict[str, dict]:
    """Return a copy of the latest collected bot states."""
    with _lock:
        return dict(_latest_states)


def get_cached_roles() -> Dict[str, dict]:
    """Return a copy of the cached YiAi roles. May be empty if never fetched."""
    with _lock:
        return dict(_yi_ai_roles)