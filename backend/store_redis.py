#!/usr/bin/env python3
"""Redis-backed storage with JSON-file fallback for Star Office backend.

All persistence goes through Redis first; JSON files serve as durable backup
and development fallback when Redis is unavailable.

Redis key namespace: "star:<entity>"
File paths are passed explicitly so this module stays framework-agnostic.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

import redis
from redis.exceptions import RedisError

logger = logging.getLogger("star-office.store")

# ── Redis client (lazy init) ────────────────────────────────
_redis_client: Optional[redis.Redis] = None
_redis_probe_done: bool = False
_redis_available: bool = False


def _get_redis_url() -> str:
    """Build Redis URL from environment or defaults."""
    return os.getenv("STAR_REDIS_URL", "redis://127.0.0.1:6379/0")


def _init_fakeredis() -> Optional[redis.Redis]:
    """Try to create a fakeredis in-memory client for dev/testing."""
    try:
        import fakeredis  # type: ignore

        cli = fakeredis.FakeRedis(decode_responses=True)
        cli.ping()
        logger.info("Redis (fakeredis): in-memory dev mode")
        return cli
    except ImportError:
        return None


def init_redis() -> bool:
    """Initialize Redis connection. Returns True if Redis is available."""
    global _redis_client, _redis_probe_done, _redis_available

    if _redis_probe_done:
        return _redis_available

    _redis_probe_done = True

    # Dev mode: use fakeredis in-memory store (set STAR_USE_FAKEREDIS=1)
    if os.getenv("STAR_USE_FAKEREDIS", "").strip() == "1":
        cli = _init_fakeredis()
        if cli is not None:
            _redis_client = cli
            _redis_available = True
            return True

    url = _get_redis_url()
    try:
        _redis_client = redis.Redis.from_url(
            url,
            socket_connect_timeout=2,
            socket_timeout=3,
            decode_responses=True,
        )
        _redis_client.ping()
        _redis_available = True
        logger.info("Redis connected: %s", url)
        return True
    except RedisError as e:
        _redis_available = False
        _redis_client = None
        logger.warning("Redis unavailable (%s), using JSON file fallback", e)
        return False


def get_redis() -> Optional[redis.Redis]:
    """Return Redis client or None if unavailable."""
    if not _redis_probe_done:
        init_redis()
    return _redis_client


def redis_enabled() -> bool:
    """Return True if Redis is available."""
    if not _redis_probe_done:
        return init_redis()
    return _redis_available


# ── Key namespace helpers ──────────────────────────────────
KEY_PREFIX = "star"

KEYS = {
    "state": f"{KEY_PREFIX}:state",
    "agents": f"{KEY_PREFIX}:agents",
    "join_keys": f"{KEY_PREFIX}:join_keys",
    "asset_positions": f"{KEY_PREFIX}:asset_positions",
    "asset_defaults": f"{KEY_PREFIX}:asset_defaults",
    "runtime_config": f"{KEY_PREFIX}:runtime_config",
}


# ── Core load/save with fallback ───────────────────────────
def _load_json_file(path: str) -> Optional[Any]:
    """Load a JSON file; return None if missing or invalid."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_json_file(path: str, data: Any) -> None:
    """Save data as JSON file with atomic write (write-tmp + rename)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        # fallback: direct write
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _redis_get_json(r: redis.Redis, key: str) -> Optional[Any]:
    """Get JSON value from Redis; return None if missing."""
    raw = r.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _redis_set_json(r: redis.Redis, key: str, data: Any) -> None:
    """Set JSON value in Redis."""
    r.set(key, json.dumps(data, ensure_ascii=False))


def load_or_default(
    redis_key: str,
    file_path: str,
    default_value: Any,
) -> Any:
    """Load data: Redis first → JSON file → default.
    
    On a cache miss, the value is warmed into Redis.
    """
    r = get_redis()
    if r is not None:
        try:
            val = _redis_get_json(r, redis_key)
            if val is not None:
                return val
        except RedisError:
            pass

    # Fall back to file
    val = _load_json_file(file_path)
    if val is not None:
        # Warm Redis
        if r is not None:
            try:
                _redis_set_json(r, redis_key, val)
            except RedisError:
                pass
        return val

    return default_value


def save_both(
    redis_key: str,
    file_path: str,
    data: Any,
) -> None:
    """Save data to both Redis and JSON file."""
    # File first (durable ground truth)
    _save_json_file(file_path, data)

    # Then Redis
    r = get_redis()
    if r is not None:
        try:
            _redis_set_json(r, redis_key, data)
        except RedisError:
            pass


# ── Domain-specific load/save ──────────────────────────────

def load_state(state_file: str, default_state: dict) -> dict:
    """Load main state dict."""
    data = load_or_default(KEYS["state"], state_file, None)
    if not isinstance(data, dict):
        return dict(default_state)
    return data


def save_state(state_file: str, data: dict) -> None:
    """Persist main state."""
    save_both(KEYS["state"], state_file, data)


def load_agents_state(agents_file: str, default_agents: list) -> list:
    """Load agents list."""
    data = load_or_default(KEYS["agents"], agents_file, None)
    if not isinstance(data, list):
        return list(default_agents)
    return data


def save_agents_state(agents_file: str, agents: list) -> None:
    """Persist agents list."""
    save_both(KEYS["agents"], agents_file, agents)


def load_asset_positions(pos_file: str) -> dict:
    """Load asset positions map."""
    data = load_or_default(KEYS["asset_positions"], pos_file, {})
    return data if isinstance(data, dict) else {}


def save_asset_positions(pos_file: str, data: dict) -> None:
    """Persist asset positions."""
    save_both(KEYS["asset_positions"], pos_file, data)


def load_asset_defaults(def_file: str) -> dict:
    """Load asset defaults map."""
    data = load_or_default(KEYS["asset_defaults"], def_file, {})
    return data if isinstance(data, dict) else {}


def save_asset_defaults(def_file: str, data: dict) -> None:
    """Persist asset defaults."""
    save_both(KEYS["asset_defaults"], def_file, data)


def load_runtime_config(cfg_file: str) -> dict:
    """Load runtime config (with env var overrides)."""
    base = {
        "gemini_api_key": os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "",
        "gemini_model": _normalize_user_model(os.getenv("GEMINI_MODEL") or "nanobanana-pro"),
    }
    data = load_or_default(KEYS["runtime_config"], cfg_file, None)
    if isinstance(data, dict):
        base.update({k: data.get(k, base.get(k)) for k in ["gemini_api_key", "gemini_model"]})
        base["gemini_model"] = _normalize_user_model(base.get("gemini_model") or "nanobanana-pro")
    return base


def save_runtime_config(cfg_file: str, data: dict) -> None:
    """Merge and persist runtime config."""
    cfg = load_runtime_config(cfg_file)
    cfg.update(data or {})
    save_both(KEYS["runtime_config"], cfg_file, cfg)


def load_join_keys(keys_file: str) -> dict:
    """Load join keys structure."""
    data = load_or_default(KEYS["join_keys"], keys_file, None)
    if isinstance(data, dict) and isinstance(data.get("keys"), list):
        return data
    return {"keys": []}


def save_join_keys(keys_file: str, data: dict) -> None:
    """Persist join keys."""
    save_both(KEYS["join_keys"], keys_file, data)


def _normalize_user_model(model_name: str) -> str:
    """Map provider model names to canonical user-facing options."""
    m = (model_name or "").strip().lower()
    if m in {"nanobanana-pro", "nanobanana-2"}:
        return m
    if m in {"nano-banana-pro-preview", "gemini-3-pro-image-preview"}:
        return "nanobanana-pro"
    if m in {"gemini-2.5-flash-image", "gemini-2.0-flash-exp-image-generation"}:
        return "nanobanana-2"
    return "nanobanana-pro"