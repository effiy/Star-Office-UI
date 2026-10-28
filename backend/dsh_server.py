#!/usr/bin/env python3
"""
DSH Bridge Microservice — Flask layer wrapping the modular bridge.

Adds HTTP endpoints (/health, /ds-bot-states) on top of the existing
state_reader / state_pusher / agent_mapper modules. Runs the DSH → Pixel
Office polling loop in a background thread.

Start:  python dsh_server.py
Port:   19002 (set BRIDGE_PORT env var to override)
"""

import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Dict

from flask import Flask, jsonify

# Reuse the extracted modules (no code duplication)
from agent_mapper import load_agent_mappings, get_agent_id
from state_reader import get_dsh_bot_states, is_chief_busy
from state_pusher import push_agent_state, push_chief_state, STATE_LABELS

# ── Config ──────────────────────────────────────────────────────────

BRIDGE_PORT = int(os.environ.get("BRIDGE_PORT", "19002"))
POLL_INTERVAL = 3  # seconds

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

# ── Flask App ────────────────────────────────────────────────────────

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


@app.route("/health", methods=["GET", "HEAD"])
def health():
    """Health check — returns JSON with uptime and cached bot count."""
    uptime = (datetime.now(timezone.utc) - _started_at).total_seconds()
    return jsonify({
        "status": "ok",
        "uptime": round(uptime),
        "uptime_human": _format_uptime(uptime),
        "started_at": _started_at.isoformat(),
        "cached_bots": len(_latest_states),
    })


@app.route("/ds-bot-states", methods=["GET"])
def ds_bot_states():
    """
    Return all current DSH bot states for YiVad consumption.

    Response:
      {
        "bots": { "软件工程师": {"state": "idle", "detail": "待命中", "updatedAt": "..."}, ... },
        "count": 17,
        "updated_at": "2026-10-28T14:00:00Z"
      }
    """
    with _lock:
        bots = dict(_latest_states)
    return jsonify({
        "bots": bots,
        "count": len(bots),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


# ── Background Poller ────────────────────────────────────────────────

def poll_loop():
    """Background thread: poll DSH state, push to pixel office, update cache."""
    log.info("Poller started (interval=%ds)", POLL_INTERVAL)

    # Load agent mappings once at startup
    load_agent_mappings()

    while not _shutdown.is_set():
        try:
            # Read DSH state
            raw_states = get_dsh_bot_states()
            now_iso = datetime.now(timezone.utc).isoformat()

            # Enrich with detail labels and timestamps for the API
            enriched: Dict[str, dict] = {}
            for name, state in raw_states.items():
                enriched[name] = {
                    "state": state,
                    "detail": STATE_LABELS.get(state, ""),
                    "updatedAt": now_iso,
                }

            # Update global cache
            with _lock:
                _latest_states.clear()
                _latest_states.update(enriched)

            # Push to pixel office
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


# ── Main ─────────────────────────────────────────────────────────────

def main():
    log.info("DSH Bridge Microservice starting on :%d", BRIDGE_PORT)

    # Start background polling thread
    poller = threading.Thread(target=poll_loop, daemon=True, name="dsh-poller")
    poller.start()

    # Graceful shutdown handlers
    def on_shutdown(signum, _frame):
        log.info("Signal %d received, shutting down…", signum)
        _shutdown.set()
        poller.join(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, on_shutdown)
    signal.signal(signal.SIGTERM, on_shutdown)

    try:
        app.run(
            host="127.0.0.1",
            port=BRIDGE_PORT,
            debug=False,
            use_reloader=False,
        )
    except KeyboardInterrupt:
        on_shutdown(signal.SIGINT, None)


if __name__ == "__main__":
    main()