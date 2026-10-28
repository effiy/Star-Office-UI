#!/usr/bin/env python3
"""
DSH Bot → Pixel Office state bridge — main orchestration loop.

Reads DSH bot state from ~/.dsh/bot/state.json and inflight.json,
maps to pixel office agent IDs, and pushes states every 3 seconds.

Architecture (UB-mode Stage 1 — 瘦身):
    bridge.py          ← main loop (this file)
    state_reader.py    ← DSH state file parsing
    state_pusher.py    ← Pixel Office HTTP client
    agent_mapper.py    ← bot name → agentId cache

Usage:
    python backend/dsh_bridge.py
"""
import logging
import signal
import sys
import time
from typing import Dict

from agent_mapper import load_agent_mappings, get_agent_id
from state_reader import get_dsh_bot_states, is_chief_busy
from state_pusher import push_agent_state, push_chief_state

POLL_INTERVAL = 3   # seconds between polling cycles

# ── Graceful shutdown ────────────────────────────────────────

_shutdown = False


def _handle_signal(_signum: int, _frame: object) -> None:
    global _shutdown
    _shutdown = True


# ── Main loop ────────────────────────────────────────────────

def main() -> None:
    """Run the DSH → Pixel Office bridge polling loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="[bridge] %(message)s",
    )
    logger = logging.getLogger(__name__)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("DSH → Pixel Office state bridge starting...")

    # Load agent name → pixel office agentId mappings once at startup.
    count = len(load_agent_mappings())
    logger.info("loaded %d agent mappings, polling every %ds", count, POLL_INTERVAL)

    while not _shutdown:
        try:
            # ── Push per-agent states ──
            states = get_dsh_bot_states()
            pushed = 0
            for name, state in states.items():
                agent_id = get_agent_id(name)
                if agent_id is None:
                    continue
                if push_agent_state(name, agent_id, state):
                    pushed += 1

            # ── Push Chief (star) state ──
            chief_state = "executing" if is_chief_busy() else "idle"
            push_chief_state(chief_state)

            if pushed > 0:
                logger.debug("pushed %d agent state(s) + chief", pushed)

        except Exception:
            logger.exception("loop error — retrying in %ds", POLL_INTERVAL)

        time.sleep(POLL_INTERVAL)

    logger.info("bridge stopped")


if __name__ == "__main__":
    main()
