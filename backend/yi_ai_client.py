#!/usr/bin/env python3
"""
YiAi HTTP Client — StarOffice ← YiAi data bridge.

Reads YiAi APIs (roles, dashboard, health) and returns typed models.
Uses httpx or urllib (zero extra deps). All calls have 5s timeout
and degrade gracefully when YiAi is unreachable.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────

YIAI_BASE_URL = os.environ.get("YIAI_BASE_URL", "http://127.0.0.1:10086")
YIAI_TIMEOUT = int(os.environ.get("YIAI_TIMEOUT", "5"))


# ── Data Models ─────────────────────────────────────────────────────

@dataclass
class YiAiRole:
    """A bot role as returned by YiAi /roles-sync."""
    name: str = ""
    title: str = ""
    domain: str = ""
    description: str = ""
    status: str = "active"
    file_count: int = 0
    subdir_count: int = 0
    updated_at: str = ""


@dataclass
class YiAiHealth:
    """YiAi health status."""
    status: str = "unknown"
    mongodb: str = "unknown"
    uptime: float = 0
    version: str = ""


@dataclass
class YiAiLiveMetrics:
    """Dashboard live metrics from YiAi."""
    active_issues: int = 0
    open_bugs: int = 0
    today_done: int = 0
    today_created: int = 0
    overdue_count: int = 0
    blocked_count: int = 0
    total_issues: int = 0
    total_bugs: int = 0
    server_uptime: float = 0
    timestamp: float = 0


# ── HTTP Helpers ────────────────────────────────────────────────────

def _http_get(path: str) -> Optional[dict]:
    """GET YiAi endpoint → parsed JSON, or None on failure."""
    url = f"{YIAI_BASE_URL}{path}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=YIAI_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        logger.warning("YiAi GET %s failed: %s", url, e)
        return None


def _http_post(path: str, payload: Optional[dict] = None) -> Optional[dict]:
    """POST YiAi endpoint → parsed JSON, or None on failure."""
    url = f"{YIAI_BASE_URL}{path}"
    try:
        data = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=YIAI_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        logger.warning("YiAi POST %s failed: %s", url, e)
        return None


# ── Public API ──────────────────────────────────────────────────────

def fetch_roles() -> List[YiAiRole]:
    """
    Fetch all bot roles from YiAi /roles-sync.
    
    Returns empty list if YiAi is unreachable.
    """
    resp = _http_post("/roles-sync")
    if resp is None:
        return []

    roles: List[YiAiRole] = []
    data = resp.get("data", {})
    items = data.get("roles", data.get("items", []))
    if not isinstance(items, list):
        return roles

    for item in items:
        if not isinstance(item, dict):
            continue
        roles.append(YiAiRole(
            name=item.get("name", ""),
            title=item.get("title", item.get("displayName", "")),
            domain=item.get("domain", ""),
            description=item.get("description", ""),
            status=item.get("status", "active"),
            file_count=item.get("fileCount", item.get("file_count", 0)),
            subdir_count=item.get("subdirCount", item.get("subdir_count", 0)),
            updated_at=item.get("updatedAt", item.get("updated_at", "")),
        ))

    return roles


def fetch_health() -> YiAiHealth:
    """Check YiAi health status."""
    resp = _http_get("/health/live")
    if resp is None:
        return YiAiHealth(status="unreachable")

    data = resp.get("data", resp)
    return YiAiHealth(
        status=data.get("status", "unknown"),
        mongodb=data.get("mongodb", "unknown"),
        uptime=data.get("uptime", 0),
        version=data.get("version", ""),
    )


def fetch_live_metrics() -> Optional[YiAiLiveMetrics]:
    """Fetch dashboard live metrics from YiAi (SSE snapshot)."""
    resp = _http_get("/dashboard/live-snapshot")
    if resp is None:
        return None

    data = resp.get("data", resp)
    if not isinstance(data, dict):
        return None

    return YiAiLiveMetrics(
        active_issues=data.get("active_issues", 0),
        open_bugs=data.get("open_bugs", 0),
        today_done=data.get("today_done", 0),
        today_created=data.get("today_created", 0),
        overdue_count=data.get("overdue_count", 0),
        blocked_count=data.get("blocked_count", 0),
        total_issues=data.get("total_issues", 0),
        total_bugs=data.get("total_bugs", 0),
        server_uptime=data.get("server_uptime", 0),
        timestamp=data.get("timestamp", 0),
    )


def is_yiai_available() -> bool:
    """Quick check if YiAi is reachable."""
    h = fetch_health()
    return h.status != "unreachable"