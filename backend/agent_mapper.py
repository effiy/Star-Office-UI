"""
DSH bot name → Pixel Office agent ID mapping.

Extracted from dsh_bridge.py per UB-mode Stage 1 (瘦身).

Provides a module-level cache that is populated once at startup
and can be refreshed on demand.
"""
import logging
from state_pusher import fetch_agent_map

logger = logging.getLogger(__name__)

# Module-level cache: bot display name → pixel office agentId
_cache: dict[str, str] | None = None


def load_agent_mappings() -> dict[str, str]:
    """Fetch and cache agent name → agentId mappings from pixel office.

    Call once at startup.  Returns the populated mapping dict.
    """
    global _cache
    _cache = fetch_agent_map()
    return _cache


def get_agent_id(name: str) -> str | None:
    """Look up the pixel office agentId for a given bot display name.

    Returns None when the cache is empty (not yet loaded) or the
    name has no registered agent in the pixel office.
    """
    if _cache is None:
        logger.warning("agent map not loaded — call load_agent_mappings() first")
        return None
    return _cache.get(name)


def refresh_mappings() -> dict[str, str]:
    """Force-refresh the agent mapping cache (e.g. after a bot join/leave)."""
    logger.info("refreshing agent mappings")
    return load_agent_mappings()