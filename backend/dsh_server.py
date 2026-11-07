"""
🗑 RETIRED — Replaced by backend/collector.py (FastAPI lifespan).

This Flask → FastAPI bridge microservice on :19003 has been superseded
by the unified DSH state collector that runs inside the main FastAPI app's
lifespan. The collector uses watchdog for event-driven file monitoring
(no polling) and publishes state changes via Redis PUBLISH for ws_server.

Retired: 2026-11-07
Replaced by: backend/collector.py (watchdog DSH → Redis PUBLISH)
Port freed: :19003

See docs/cross-project-architecture.md §2.2 for the unified data flow.
"""

import logging
import os
import signal
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel

# Reuse the extracted modules (shared with dsh_bridge.py)
from state_reader import get_dsh_bot_states, is_chief_busy
from agent_mapper import load_agent_mappings, get_agent_id
from state_pusher import push_agent_state, push_chief_state, STATE_LABELS

# ── Config ──────────────────────────────────────────────────────────

BRIDGE_PORT = int(os.environ.get("BRIDGE_PORT", "19003"))
POLL_INTERVAL = int(os.environ.get("DSH_POLL_INTERVAL", "3"))  # seconds

# ── Logging ─────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [dsh-server] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("dsh_server")

# ── Global State ────────────────────────────────────────────────────

_latest_states: Dict[str, dict] = {}  # botName → {state, detail, updatedAt}
_lock = threading.Lock()
_started_at = datetime.now(timezone.utc)
_shutdown = threading.Event()

# ── Pydantic Models ─────────────────────────────────────────────────

class BotStateDetail(BaseModel):
    """Single bot state entry in the /ds-bot-states response."""
    state: str  # idle | writing | executing | researching | syncing | error
    detail: str = ""  # human-readable label
    updatedAt: str  # ISO 8601 timestamp


class DsBotStatesResponse(BaseModel):
    """Response for GET /ds-bot-states."""
    bots: Dict[str, BotStateDetail]
    count: int
    updated_at: str  # ISO 8601


class HealthResponse(BaseModel):
    """Response for GET /health."""
    status: str
    uptime: int
    uptime_human: str
    started_at: str  # ISO 8601
    cached_bots: int


# ── Helpers ──────────────────────────────────────────────────────────

def _format_uptime(seconds: float) -> str:
    s = int(seconds)
    h, m = s // 3600, (s % 3600) // 60
    sec = s % 60
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    parts.append(f"{sec}s")
    return " ".join(parts)


# ── Background Poller ────────────────────────────────────────────────

def poll_loop():
    """Background thread: poll DSH state, push to pixel office, update cache."""
    log.info("Poller started (interval=%ds)", POLL_INTERVAL)

    # Load agent mappings once at startup
    load_agent_mappings()

    while not _shutdown.is_set():
        try:
            # ── Read DSH state ──
            raw_states = get_dsh_bot_states()
            now_iso = datetime.now(timezone.utc).isoformat()

            # ── Enrich with detail labels and timestamps ──
            enriched: Dict[str, dict] = {}
            for name, state in raw_states.items():
                enriched[name] = {
                    "state": state,
                    "detail": STATE_LABELS.get(state, ""),
                    "updatedAt": now_iso,
                }

            # ── Update global cache ──
            with _lock:
                _latest_states.clear()
                _latest_states.update(enriched)

            # ── Push to pixel office ──
            pushed = 0
            for name, state in raw_states.items():
                agent_id = get_agent_id(name)
                if agent_id is None:
                    continue
                if push_agent_state(name, agent_id, state):
                    pushed += 1

            # Push Chief state
            chief_state = "executing" if is_chief_busy() else "idle"
            push_chief_state(chief_state)

            if pushed > 0:
                log.debug("Pushed %d agent state(s) + chief", pushed)

        except Exception:
            log.exception("Poll loop error — retrying in %ds", POLL_INTERVAL)

        _shutdown.wait(POLL_INTERVAL)

    log.info("Poller stopped")


# ── FastAPI App ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background poller on app startup, signal shutdown on teardown."""
    global _started_at
    _started_at = datetime.now(timezone.utc)

    poller = threading.Thread(target=poll_loop, daemon=True, name="dsh-poller")
    poller.start()

    yield  # app runs here

    _shutdown.set()
    poller.join(timeout=5)
    log.info("DSH Bridge Microservice stopped")


app = FastAPI(
    title="DSH Bridge Microservice",
    description="DSH Bot → Pixel Office state bridge with HTTP API",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
def health():
    """Health check — returns JSON with uptime and cached bot count."""
    uptime = (datetime.now(timezone.utc) - _started_at).total_seconds()
    with _lock:
        cached = len(_latest_states)
    return HealthResponse(
        status="ok",
        uptime=round(uptime),
        uptime_human=_format_uptime(uptime),
        started_at=_started_at.isoformat(),
        cached_bots=cached,
    )


@app.get("/ds-bot-states", response_model=DsBotStatesResponse)
def ds_bot_states():
    """Return all current DSH bot states for YiVad / YiAi consumption."""
    with _lock:
        bots_raw = dict(_latest_states)

    bots = {
        name: BotStateDetail(
            state=info["state"],
            detail=info.get("detail", ""),
            updatedAt=info.get("updatedAt", datetime.now(timezone.utc).isoformat()),
        )
        for name, info in bots_raw.items()
    }

    return DsBotStatesResponse(
        bots=bots,
        count=len(bots),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    log.info("DSH Bridge Microservice starting on :%d", BRIDGE_PORT)
    uvicorn.run(
        "backend.dsh_server:app",
        host="127.0.0.1",
        port=BRIDGE_PORT,
        log_level="info",
    )