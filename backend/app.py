#!/usr/bin/env python3
"""Star Office UI - Backend State Service (FastAPI + Redis)"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# ── Auto-load .env file (R4 — persists env across bridge-watchdog restarts) ──
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if _ENV_FILE.exists():
    with open(_ENV_FILE, "r") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _key, _, _val = _line.partition("=")
            _key = _key.strip()
            _val = _val.strip().strip('"').strip("'")
            if _key and _key not in os.environ:  # don't override existing env
                os.environ[_key] = _val
    del _key, _val, _line, _f

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.middleware.sessions import SessionMiddleware

# Use absolute backend.xxx imports when running as a package (uvicorn),
# fall back to bare module imports when running directly (python backend/app.py).
try:
    from .memo_utils import extract_memo_from_file, get_yesterday_date_str, sanitize_content
    from .security_utils import is_production_mode, is_strong_drawer_pass, is_strong_secret
    from .store_redis import (
        init_redis,
        load_agents_state,
        load_asset_defaults,
        load_asset_positions,
        load_join_keys,
        load_runtime_config,
        load_state,
        redis_enabled,
        save_agents_state,
        save_asset_defaults,
        save_asset_positions,
        save_join_keys,
        save_runtime_config,
        save_state,
    )
except ImportError:
    from memo_utils import extract_memo_from_file, get_yesterday_date_str, sanitize_content  # type: ignore
    from security_utils import is_production_mode, is_strong_drawer_pass, is_strong_secret  # type: ignore
    from store_redis import (  # type: ignore
        init_redis,
        load_agents_state,
        load_asset_defaults,
        load_asset_positions,
        load_join_keys,
        load_runtime_config,
        load_state,
        redis_enabled,
        save_agents_state,
        save_asset_defaults,
        save_asset_positions,
        save_join_keys,
        save_runtime_config,
        save_state,
    )

# YiAi cross-project client (graceful degradation when YiAi is unreachable)
try:
    from .yi_ai_client import fetch_health as _yi_ai_health, fetch_roles as _yi_ai_roles
except ImportError:
    from yi_ai_client import fetch_health as _yi_ai_health, fetch_roles as _yi_ai_roles  # type: ignore

# DSH state collector — watchdog-based, single ingestion point (T2)
try:
    from .collector import start_collector as _start_collector, shutdown_collector as _shutdown_collector, get_latest_states as _get_latest_states, get_cached_roles as _get_cached_roles
except ImportError:
    from collector import start_collector as _start_collector, shutdown_collector as _shutdown_collector, get_latest_states as _get_latest_states, get_cached_roles as _get_cached_roles  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-5s %(name)s  %(message)s")
logger = logging.getLogger("star-office")

try:
    from PIL import Image
except Exception:
    Image = None

# ═══════════════════════════════════════════════════════════
#  Paths (project-relative)
# ═══════════════════════════════════════════════════════════
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_DIR = os.path.join(os.path.dirname(ROOT_DIR), "memory")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
FRONTEND_DIST_DIR = os.path.join(FRONTEND_DIR, "dist")  # Vite build output
FRONTEND_INDEX_FILE = os.path.join(FRONTEND_DIR, "index.html")
FRONTEND_DIST_INDEX_FILE = os.path.join(FRONTEND_DIST_DIR, "index.html")
# Prefer Vite build output when available; fall back to source for dev
_INDEX_HTML_PATH = FRONTEND_DIST_INDEX_FILE if os.path.exists(FRONTEND_DIST_INDEX_FILE) else FRONTEND_INDEX_FILE
FRONTEND_ELECTRON_STANDALONE_FILE = os.path.join(FRONTEND_DIR, "electron-standalone.html")
STATE_FILE = os.path.join(ROOT_DIR, "state.json")
AGENTS_STATE_FILE = os.path.join(ROOT_DIR, "agents-state.json")
JOIN_KEYS_FILE = os.path.join(ROOT_DIR, "join-keys.json")
# Use dist/ as the primary static root (Vite build), with source dir as fallback
_STATIC_ROOTS = [d for d in (FRONTEND_DIST_DIR, FRONTEND_DIR) if os.path.isdir(d)]
FRONTEND_PATH = Path(FRONTEND_DIR)
ASSET_ALLOWED_EXTS = {".png", ".webp", ".jpg", ".jpeg", ".gif", ".svg", ".avif"}
ASSET_TEMPLATE_ZIP = os.path.join(ROOT_DIR, "assets-replace-template.zip")
WORKSPACE_DIR = os.path.dirname(ROOT_DIR)
OPENCLAW_WORKSPACE = os.environ.get("OPENCLAW_WORKSPACE") or os.path.join(os.path.expanduser("~"), ".openclaw", "workspace")
IDENTITY_FILE = os.path.join(OPENCLAW_WORKSPACE, "IDENTITY.md")
GEMINI_SCRIPT = os.path.join(WORKSPACE_DIR, "skills", "gemini-image-generate", "scripts", "gemini_image_generate.py")
GEMINI_PYTHON = os.path.join(WORKSPACE_DIR, "skills", "gemini-image-generate", ".venv", "bin", "python")
ROOM_REFERENCE_IMAGE = (
    os.path.join(ROOT_DIR, "assets", "room-reference.webp")
    if os.path.exists(os.path.join(ROOT_DIR, "assets", "room-reference.webp"))
    else os.path.join(ROOT_DIR, "assets", "room-reference.png")
)
BG_HISTORY_DIR = os.path.join(ROOT_DIR, "assets", "bg-history")
HOME_FAVORITES_DIR = os.path.join(ROOT_DIR, "assets", "home-favorites")
HOME_FAVORITES_INDEX_FILE = os.path.join(HOME_FAVORITES_DIR, "index.json")
HOME_FAVORITES_MAX = 30
ASSET_POSITIONS_FILE = os.path.join(ROOT_DIR, "asset-positions.json")
ASSET_DEFAULTS_FILE = os.path.join(ROOT_DIR, "asset-defaults.json")
RUNTIME_CONFIG_FILE = os.path.join(ROOT_DIR, "runtime-config.json")

# ═══════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════
AUTO_ROTATE_HOME_ON_PAGE_OPEN = (os.getenv("AUTO_ROTATE_HOME_ON_PAGE_OPEN", "0").strip().lower() in {"1", "true", "yes", "on"})
AUTO_ROTATE_MIN_INTERVAL_SECONDS = int(os.getenv("AUTO_ROTATE_MIN_INTERVAL_SECONDS", "60"))
_last_home_rotate_at: float = 0.0

VALID_AGENT_STATES = frozenset({"idle", "writing", "researching", "executing", "syncing", "error"})
WORKING_STATES = frozenset({"writing", "researching", "executing"})
STATE_TO_AREA_MAP = {
    "idle": "breakroom",
    "writing": "writing",
    "researching": "writing",
    "executing": "writing",
    "syncing": "writing",
    "error": "error",
}

START_TIME = time.time()

client_metrics: dict = {
    "fps": 0,
    "usedJSHeapSize": 0,
    "totalJSHeapSize": 0,
    "jsHeapSizeLimit": 0,
    "last_report_at": 0.0,
}

join_lock = threading.Lock()

_bg_tasks: dict = {}
_bg_tasks_lock = threading.Lock()

VERSION_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
ASSET_DRAWER_PASS_DEFAULT = os.getenv("ASSET_DRAWER_PASS", "1234")

USER_MODEL_TO_PROVIDER_MODELS = {
    "nanobanana-pro": ["nano-banana-pro-preview"],
    "nanobanana-2": ["gemini-2.5-flash-image"],
}
PROVIDER_MODEL_TO_USER_MODEL = {
    provider: user
    for user, providers in USER_MODEL_TO_PROVIDER_MODELS.items()
    for provider in providers
}

DEFAULT_STATE: dict = {
    "state": "idle",
    "detail": "等待任务中...",
    "progress": 0,
    "updated_at": datetime.now().isoformat(),
}

DEFAULT_AGENTS = [
    {
        "agentId": "star",
        "name": "Star",
        "isMain": True,
        "state": "idle",
        "detail": "待命中，随时准备为你服务",
        "updated_at": datetime.now().isoformat(),
        "area": "breakroom",
        "source": "local",
        "joinKey": None,
        "authStatus": "approved",
        "authExpiresAt": None,
        "lastPushAt": None,
    }
]

# ═══════════════════════════════════════════════════════════
#  FastAPI App
# ═══════════════════════════════════════════════════════════
app = FastAPI(
    title="Star Office UI",
    version="2.0.0",
    docs_url="/docs" if not is_production_mode() else None,
    redoc_url=None,
)

SECRET_KEY = os.getenv("STAR_OFFICE_SECRET") or os.getenv("FLASK_SECRET_KEY") or "star-office-dev-secret-change-me"
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="star_office_session",
    https_only=is_production_mode(),
    same_site="lax",
    max_age=43200,  # 12 hours
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════
#  Middleware: no-cache headers
# ═══════════════════════════════════════════════════════════
@app.middleware("http")
async def cache_control_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path or ""
    if path.startswith("/static/") or path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        # MutableHeaders doesn't support .pop(); use __delitem__
        for _hdr in ("Pragma", "Expires"):
            if _hdr in response.headers:
                del response.headers[_hdr]
    else:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ═══════════════════════════════════════════════════════════
#  Startup / Shutdown
# ═══════════════════════════════════════════════════════════
@app.on_event("startup")
def startup():
    """Initialize Redis and ensure state files exist."""
    init_redis()
    if redis_enabled():
        logger.info("Redis session storage: available ✓")
    else:
        logger.warning("Redis not available — using JSON file fallback")

    if not os.path.exists(STATE_FILE):
        save_state(STATE_FILE, DEFAULT_STATE)
    if not os.path.exists(AGENTS_STATE_FILE):
        save_agents_state(AGENTS_STATE_FILE, DEFAULT_AGENTS)
    if not os.path.exists(JOIN_KEYS_FILE):
        sample_path = os.path.join(ROOT_DIR, "join-keys.sample.json")
        if os.path.exists(sample_path):
            try:
                with open(sample_path, "r", encoding="utf-8") as sf:
                    sample = json.load(sf)
                save_join_keys(JOIN_KEYS_FILE, sample if isinstance(sample, dict) else {"keys": []})
            except Exception:
                save_join_keys(JOIN_KEYS_FILE, {"keys": []})
        else:
            save_join_keys(JOIN_KEYS_FILE, {"keys": []})

    # Secure runtime-config file perms
    if os.path.exists(RUNTIME_CONFIG_FILE):
        try:
            os.chmod(RUNTIME_CONFIG_FILE, 0o600)
        except Exception:
            pass

    # Electron standalone snapshot
    if not os.path.exists(FRONTEND_ELECTRON_STANDALONE_FILE):
        try:
            shutil.copy2(_INDEX_HTML_PATH, FRONTEND_ELECTRON_STANDALONE_FILE)
            logger.info("[standalone] created: %s", FRONTEND_ELECTRON_STANDALONE_FILE)
        except Exception as e:
            logger.warning("[standalone] create failed: %s", e)

    # Security hardening
    if is_production_mode():
        hardening_errors = []
        if not is_strong_secret(str(SECRET_KEY)):
            hardening_errors.append("STAR_OFFICE_SECRET / FLASK_SECRET_KEY is weak (need >=24 chars, non-default)")
        if not is_strong_drawer_pass(ASSET_DRAWER_PASS_DEFAULT):
            hardening_errors.append("ASSET_DRAWER_PASS is weak (do not use default 1234; recommend >=8 chars)")
        if hardening_errors:
            raise RuntimeError("Security hardening check failed in production mode: " + "; ".join(hardening_errors))

    logger.info("Star Office backend ready (FastAPI + %s)", "Redis" if redis_enabled() else "JSON files")

    # T2: Start DSH state collector (watchdog → Redis → PUBLISH)
    # Replaces legacy dsh_server (:19003) and ds_bot_watcher processes.
    try:
        _start_collector()
        logger.info("DSH state collector started (watchdog)")
    except Exception as e:
        logger.warning("DSH collector failed to start (non-fatal): %s", e)


@app.on_event("shutdown")
def shutdown():
    """Gracefully stop background services."""
    try:
        _shutdown_collector()
        logger.info("DSH state collector stopped")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════
_INDEX_HTML_CACHE: Optional[str] = None


def _is_asset_editor_authed(request: Request) -> bool:
    return bool(request.session.get("asset_editor_authed"))


def _require_asset_editor_auth(request: Request) -> Optional[JSONResponse]:
    if _is_asset_editor_authed(request):
        return None
    return JSONResponse(
        status_code=401,
        content={"ok": False, "code": "UNAUTHORIZED", "msg": "Asset editor auth required"},
    )


def normalize_agent_state(s: Optional[str]) -> str:
    if not s:
        return "idle"
    s_lower = s.lower().strip()
    if s_lower in {"working", "busy", "write"}:
        return "writing"
    if s_lower in {"run", "running", "execute", "exec"}:
        return "executing"
    if s_lower in {"sync"}:
        return "syncing"
    if s_lower in {"research", "search"}:
        return "researching"
    if s_lower in VALID_AGENT_STATES:
        return s_lower
    return "idle"


def state_to_area(state: str) -> str:
    return STATE_TO_AREA_MAP.get(state, "breakroom")


def _normalize_user_model(model_name: str) -> str:
    m = (model_name or "").strip()
    if not m:
        return "nanobanana-pro"
    low = m.lower()
    if low in USER_MODEL_TO_PROVIDER_MODELS:
        return low
    if low in PROVIDER_MODEL_TO_USER_MODEL:
        return PROVIDER_MODEL_TO_USER_MODEL[low]
    return "nanobanana-pro"


def _provider_model_candidates(user_model: str) -> list:
    normalized = _normalize_user_model(user_model)
    return list(USER_MODEL_TO_PROVIDER_MODELS.get(normalized, USER_MODEL_TO_PROVIDER_MODELS["nanobanana-pro"]))


def get_office_name_from_identity() -> Optional[str]:
    if not os.path.isfile(IDENTITY_FILE):
        return None
    try:
        with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"-\s*\*\*Name:\*\*\s*(.+)", content)
        if m:
            name = m.group(1).strip().replace("\r", "").split("\n")[0].strip()
            return f"{name}的办公室" if name else None
    except Exception:
        pass
    return None


# ── Store delegation wrappers ──────────────────────────────
def _load_state() -> dict:
    state = load_state(STATE_FILE, DEFAULT_STATE)
    if not isinstance(state, dict):
        state = dict(DEFAULT_STATE)
    # Auto-idle
    try:
        ttl = int(state.get("ttl_seconds", 300))
        updated_at = state.get("updated_at")
        s = state.get("state", "idle")
        if updated_at and s in WORKING_STATES:
            dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if dt.tzinfo:
                age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
            else:
                age = (datetime.now() - dt).total_seconds()
            if age > ttl:
                state["state"] = "idle"
                state["detail"] = "待命中（自动回到休息区）"
                state["progress"] = 0
                state["updated_at"] = datetime.now().isoformat()
                try:
                    save_state(STATE_FILE, state)
                except Exception:
                    pass
    except Exception:
        pass
    return state


def _save_state(state: dict) -> None:
    save_state(STATE_FILE, state)


def _load_agents_state() -> list:
    return load_agents_state(AGENTS_STATE_FILE, DEFAULT_AGENTS)


def _save_agents_state(agents: list) -> None:
    save_agents_state(AGENTS_STATE_FILE, agents)


def _load_asset_positions() -> dict:
    return load_asset_positions(ASSET_POSITIONS_FILE)


def _save_asset_positions(data: dict) -> None:
    save_asset_positions(ASSET_POSITIONS_FILE, data)


def _load_asset_defaults() -> dict:
    return load_asset_defaults(ASSET_DEFAULTS_FILE)


def _save_asset_defaults(data: dict) -> None:
    save_asset_defaults(ASSET_DEFAULTS_FILE, data)


def _load_runtime_config() -> dict:
    return load_runtime_config(RUNTIME_CONFIG_FILE)


def _save_runtime_config(data: dict) -> None:
    save_runtime_config(RUNTIME_CONFIG_FILE, data)


def _load_join_keys() -> dict:
    return load_join_keys(JOIN_KEYS_FILE)


def _save_join_keys(data: dict) -> None:
    save_join_keys(JOIN_KEYS_FILE, data)


def _load_floor_registry() -> dict:
    """加载楼层分配注册表（floor-registry.json），不存在时回退到硬编码默认值"""
    registry_file = os.path.join(ROOT_DIR, "floor-registry.json")
    try:
        if os.path.exists(registry_file):
            with open(registry_file, "r") as f:
                registry = json.load(f)
            floor_map = {}
            for key, names in registry.items():
                if key.startswith("_"):
                    continue
                try:
                    floor_num = int(key[0])
                except ValueError:
                    continue
                floor_map[floor_num] = names
            if floor_map:
                return floor_map
    except Exception:
        pass
    # 默认回退：16 bot 硬编码
    return {
        1: ["Chief", "管理顾问", "技术负责人", "产品经理", "Readme管家"],
        2: ["软件工程师", "AI工程师", "SRE工程师", "Git管家", "UB模式", "Vue3专家"],
        3: ["Remotion大师", "排版管家", "设计品味", "知识管理者", "像素办公室"],
    }


# ── Home favorites ─────────────────────────────────────────
def _ensure_home_favorites_index():
    os.makedirs(HOME_FAVORITES_DIR, exist_ok=True)
    if not os.path.exists(HOME_FAVORITES_INDEX_FILE):
        with open(HOME_FAVORITES_INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump({"items": []}, f, ensure_ascii=False, indent=2)


def _load_home_favorites_index():
    _ensure_home_favorites_index()
    try:
        with open(HOME_FAVORITES_INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data
    except Exception:
        pass
    return {"items": []}


def _save_home_favorites_index(data):
    _ensure_home_favorites_index()
    with open(HOME_FAVORITES_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _maybe_apply_random_home_favorite():
    global _last_home_rotate_at
    if not AUTO_ROTATE_HOME_ON_PAGE_OPEN:
        return False, "disabled"
    try:
        now_ts = datetime.now().timestamp()
        if _last_home_rotate_at and (now_ts - _last_home_rotate_at) < AUTO_ROTATE_MIN_INTERVAL_SECONDS:
            return False, "throttled"
        idx = _load_home_favorites_index()
        items = idx.get("items") or []
        candidates = []
        for it in items:
            rel = (it.get("path") or "").strip()
            if not rel:
                continue
            abs_path = os.path.join(ROOT_DIR, rel)
            if os.path.exists(abs_path):
                candidates.append((rel, abs_path))
        if not candidates:
            return False, "no-favorites"
        rel, src = random.choice(candidates)
        target = FRONTEND_PATH / "office_bg_small.webp"
        if not target.exists():
            return False, "missing-office-bg"
        shutil.copy2(src, str(target))
        _last_home_rotate_at = now_ts
        return True, rel
    except Exception as e:
        return False, str(e)


# ── Image/animation utilities ──────────────────────────────
def _ensure_magick_or_ffmpeg_available():
    if shutil.which("magick"):
        return "magick"
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    return None


def _probe_animated_frame_size(upload_path: str):
    if Image is not None:
        try:
            with Image.open(upload_path) as im:
                w, h = im.size
                return int(w), int(h)
        except Exception:
            pass
    if shutil.which("ffprobe"):
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x",
                upload_path,
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=5).decode().strip()
            if "x" in out:
                w, h = out.split("x", 1)
                return int(w), int(h)
        except Exception:
            pass
    return None, None


def _animated_to_spritesheet(
    upload_path: str,
    frame_w: int,
    frame_h: int,
    out_ext: str = ".webp",
    preserve_original: bool = True,
    pixel_art: bool = True,
    cols: Optional[int] = None,
    rows: Optional[int] = None,
):
    backend = _ensure_magick_or_ffmpeg_available()
    if not backend:
        raise RuntimeError("未检测到 ImageMagick/ffmpeg，无法自动转换动图")

    ext = (out_ext or ".webp").lower()
    if ext not in {".webp", ".png"}:
        ext = ".webp"

    out_fd, out_path = tempfile.mkstemp(suffix=ext)
    os.close(out_fd)

    with tempfile.TemporaryDirectory() as td:
        frames = 0
        out_fw, out_fh = int(frame_w), int(frame_h)
        if Image is not None:
            try:
                with Image.open(upload_path) as im:
                    n = getattr(im, "n_frames", 1)
                    if preserve_original:
                        out_fw, out_fh = im.size
                    for i in range(n):
                        im.seek(i)
                        fr = im.convert("RGBA")
                        if not preserve_original and (fr.size != (out_fw, out_fh)):
                            resample = Image.Resampling.NEAREST if pixel_art else Image.Resampling.LANCZOS
                            fr = fr.resize((out_fw, out_fh), resample)
                        fr.save(os.path.join(td, f"f_{i:04d}.png"), "PNG")
                    frames = n
            except Exception:
                frames = 0

        if frames <= 0:
            cmd1 = f"ffmpeg -y -i '{upload_path}' '{td}/f_%04d.png' >/dev/null 2>&1"
            if os.system(cmd1) != 0:
                raise RuntimeError("动图抽帧失败（Pillow/ffmpeg 都失败）")
            files = sorted([x for x in os.listdir(td) if x.startswith("f_") and x.endswith(".png")])
            frames = len(files)
            if frames <= 0:
                raise RuntimeError("动图无有效帧")

        if backend == "magick":
            quality_flag = "-define webp:lossless=true -define webp:method=6 -quality 100" if ext == ".webp" else ""
            if cols is None or cols <= 0:
                cols_eff = frames
            else:
                cols_eff = max(1, int(cols))
            rows_eff = max(1, int(rows)) if (rows is not None and rows > 0) else max(1, math.ceil(frames / cols_eff))

            prep = ""
            if not preserve_original:
                magick_filter = "-filter point" if pixel_art else ""
                prep = f" {magick_filter} -resize {out_fw}x{out_fh}^ -gravity center -background none -extent {out_fw}x{out_fh}"

            cmd = (
                f"magick '{td}/f_*.png'{prep} "
                f"-tile {cols_eff}x{rows_eff} -background none -geometry +0+0 {quality_flag} '{out_path}'"
            )
            rc = os.system(cmd)
            if rc != 0:
                raise RuntimeError("ImageMagick 拼图失败")
            return out_path, cols_eff, rows_eff, frames, out_fw, out_fh

        ffmpeg_quality = "-lossless 1 -compression_level 6 -q:v 100" if ext == ".webp" else ""
        cols_eff = max(1, int(cols)) if (cols is not None and cols > 0) else frames
        rows_eff = max(1, int(rows)) if (rows is not None and rows > 0) else max(1, math.ceil(frames / cols_eff))
        if preserve_original:
            vf = f"tile={cols_eff}x{rows_eff}"
        else:
            scale_algo = "neighbor" if pixel_art else "lanczos"
            vf = (
                f"scale={out_fw}:{out_fh}:force_original_aspect_ratio=decrease:flags={scale_algo},"
                f"pad={out_fw}:{out_fh}:(ow-iw)/2:(oh-ih)/2:color=0x00000000,"
                f"tile={cols_eff}x{rows_eff}"
            )
        cmd2 = (
            f"ffmpeg -y -pattern_type glob -i '{td}/f_*.png' "
            f"-vf '{vf}' "
            f"{ffmpeg_quality} '{out_path}' >/dev/null 2>&1"
        )
        if os.system(cmd2) != 0:
            raise RuntimeError("ffmpeg 拼图失败")
        return out_path, frames, 1, frames, out_fw, out_fh


def _generate_rpg_background_to_webp(
    out_webp_path: str,
    width: int = 1280,
    height: int = 720,
    custom_prompt: str = "",
    speed_mode: str = "fast",
):
    runtime_cfg = _load_runtime_config()
    api_key = (runtime_cfg.get("gemini_api_key") or "").strip()
    if not api_key:
        raise RuntimeError("MISSING_API_KEY")
    themes = [
        "8-bit dungeon guild room",
        "8-bit stardew-valley inspired cozy farm tavern",
        "8-bit nordic fantasy tavern",
        "8-bit magitech workshop",
        "8-bit elven forest inn",
        "8-bit pixel cyber tavern",
        "8-bit desert caravan inn",
        "8-bit snow mountain lodge",
    ]
    theme = random.choice(themes)

    if not (os.path.exists(GEMINI_PYTHON) and os.path.exists(GEMINI_SCRIPT)):
        raise RuntimeError("生图脚本环境缺失：gemini-image-generate 未安装")

    style_hint = (custom_prompt or "").strip()
    if not style_hint:
        style_hint = theme

    mode = (speed_mode or "quality").strip().lower()
    if mode not in {"fast", "quality"}:
        mode = "quality"

    configured_user_model = _normalize_user_model(runtime_cfg.get("gemini_model") or "nanobanana-pro")
    if mode == "fast":
        preferred_user_model = "nanobanana-2"
        gen_width, gen_height = 1152, 648
        ref_width, ref_height = 1152, 648
    else:
        preferred_user_model = configured_user_model
        gen_width, gen_height = width, height
        ref_width, ref_height = width, height

    allow_aspect_ratio = (preferred_user_model == "nanobanana-2")

    prompt = (
        "Use a top-down pixel room composition compatible with an office game scene. "
        "STRICTLY preserve the same room geometry, camera angle, wall/floor boundaries and major object placement as the provided reference image. "
        "Keep region layout stable (left work area, center lounge, right error area). "
        "Only change visual style/theme/material/lighting according to: " + style_hint + ". "
        "Do not add text or watermark. Retro 8-bit RPG style."
    )

    tmp_dir = tempfile.mkdtemp(prefix="rpg-bg-")
    cmd = [
        GEMINI_PYTHON,
        GEMINI_SCRIPT,
        "--prompt", prompt,
        "--model", configured_user_model,
        "--out-dir", tmp_dir,
        "--cleanup",
    ]
    if allow_aspect_ratio:
        cmd.extend(["--aspect-ratio", "16:9"])

    ref_for_call = None
    if os.path.exists(ROOM_REFERENCE_IMAGE):
        ref_for_call = ROOM_REFERENCE_IMAGE
        if mode == "fast" and Image is not None:
            try:
                ref_fast = os.path.join(tmp_dir, "room-reference-fast.webp")
                with Image.open(ROOM_REFERENCE_IMAGE) as rim:
                    rim = rim.convert("RGBA").resize((ref_width, ref_height), Image.Resampling.LANCZOS)
                    rim.save(ref_fast, "WEBP", quality=85, method=4)
                ref_for_call = ref_fast
            except Exception:
                ref_for_call = ROOM_REFERENCE_IMAGE

    if ref_for_call:
        cmd.extend(["--reference-image", ref_for_call])

    env = os.environ.copy()
    env.pop("GOOGLE_API_KEY", None)
    env["GEMINI_API_KEY"] = api_key

    def _run_cmd(cmd_args):
        return subprocess.run(cmd_args, capture_output=True, text=True, env=env, timeout=240)

    def _is_model_unavailable_error(text: str) -> bool:
        low = (text or "").strip().lower()
        return (
            ("not found" in low and "models/" in low)
            or ("model_not_available" in low)
            or ("model is not available" in low)
            or ("configured model is not available" in low)
            or ("this model is not available" in low)
            or ("not supported for generatecontent" in low)
        )

    def _with_model(cmd_args, model_name: str):
        m = cmd_args[:]
        if "--model" in m:
            idx = m.index("--model")
            if idx + 1 < len(m):
                m[idx + 1] = model_name
        else:
            m.extend(["--model", model_name])
        return m

    user_model_order = [preferred_user_model, configured_user_model]
    user_model_order = [m for i, m in enumerate(user_model_order) if m and m not in user_model_order[:i]]

    model_candidates = []
    for um in user_model_order:
        model_candidates.extend(_provider_model_candidates(um))
    model_candidates = [m for i, m in enumerate(model_candidates) if m and m not in model_candidates[:i]]

    proc = None
    last_err_text = ""
    model_unavailable_count = 0

    for mname in model_candidates:
        env["GEMINI_MODEL"] = mname
        try_cmd = _with_model(cmd, mname)
        proc = _run_cmd(try_cmd)
        if proc.returncode == 0:
            break

        err_text = (proc.stderr or proc.stdout or "").strip()
        last_err_text = err_text

        low = err_text.lower()
        if "your api key was reported as leaked" in low or "permission_denied" in low:
            raise RuntimeError("API_KEY_REVOKED_OR_LEAKED")

        if _is_model_unavailable_error(err_text):
            model_unavailable_count += 1
            continue

        raise RuntimeError(f"生图失败: {err_text}")

    if proc is None or proc.returncode != 0:
        err_text = (last_err_text or "").strip()
        if model_unavailable_count >= len(model_candidates) or _is_model_unavailable_error(err_text):
            brief = (err_text or "").replace("\n", " ")[:240]
            raise RuntimeError(f"MODEL_NOT_AVAILABLE::{brief}")
        raise RuntimeError(f"生图失败: {err_text}")

    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        raise RuntimeError("生图结果解析失败")

    files = result.get("files") or []
    if not files:
        raise RuntimeError("生图未返回文件")

    gen_path = files[0]
    if not os.path.exists(gen_path):
        raise RuntimeError("生图文件不存在")

    if Image is None:
        raise RuntimeError("Pillow 不可用，无法做尺寸标准化")

    with Image.open(gen_path) as im:
        im = im.convert("RGBA")
        if mode == "fast":
            im = im.resize((gen_width, gen_height), Image.Resampling.LANCZOS)
            if (gen_width, gen_height) != (width, height):
                im = im.resize((width, height), Image.Resampling.LANCZOS)
            im.save(out_webp_path, "WEBP", quality=96, method=6)
        else:
            if im.size != (width, height):
                im = im.resize((width, height), Image.Resampling.LANCZOS)
            im.save(out_webp_path, "WEBP", lossless=True, quality=100, method=6)


# ═══════════════════════════════════════════════════════════
#  Routes — Pages
# ═══════════════════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
def index():
    _maybe_apply_random_home_favorite()
    global _INDEX_HTML_CACHE
    if _INDEX_HTML_CACHE is None:
        with open(_INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            raw_html = f.read()
        _INDEX_HTML_CACHE = raw_html.replace("{{VERSION_TIMESTAMP}}", VERSION_TIMESTAMP)
    return HTMLResponse(content=_INDEX_HTML_CACHE)


@app.get("/electron-standalone", response_class=HTMLResponse)
def electron_standalone_page():
    target = FRONTEND_ELECTRON_STANDALONE_FILE
    if not os.path.exists(target):
        target = FRONTEND_INDEX_FILE
    with open(target, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("{{VERSION_TIMESTAMP}}", VERSION_TIMESTAMP)
    return HTMLResponse(content=html)


@app.get("/join", response_class=HTMLResponse)
def join_page():
    with open(os.path.join(FRONTEND_DIR, "join.html"), "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(content=html)


@app.get("/invite", response_class=HTMLResponse)
def invite_page():
    with open(os.path.join(FRONTEND_DIR, "invite.html"), "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(content=html)


# ═══════════════════════════════════════════════════════════
#  Routes — Agents
# ═══════════════════════════════════════════════════════════
@app.get("/agents")
def get_agents():
    agents = _load_agents_state()
    now = datetime.now()
    cleaned_agents = []
    keys_data = _load_join_keys()

    for a in agents:
        if a.get("isMain"):
            cleaned_agents.append(a)
            continue

        auth_expires_at_str = a.get("authExpiresAt")
        auth_status = a.get("authStatus", "pending")

        if auth_status == "pending" and auth_expires_at_str:
            try:
                auth_expires_at = datetime.fromisoformat(auth_expires_at_str)
                if now > auth_expires_at:
                    key = a.get("joinKey")
                    if key:
                        key_item = next((k for k in keys_data.get("keys", []) if k.get("key") == key), None)
                        if key_item:
                            key_item["used"] = False
                            key_item["usedBy"] = None
                            key_item["usedByAgentId"] = None
                            key_item["usedAt"] = None
                    continue
            except Exception:
                pass

        last_push_at_str = a.get("lastPushAt")
        if auth_status == "approved" and last_push_at_str:
            try:
                last_push_at = datetime.fromisoformat(last_push_at_str)
                age = (now - last_push_at).total_seconds()
                if age > 300:
                    a["authStatus"] = "offline"
            except Exception:
                pass

        cleaned_agents.append(a)

    _save_agents_state(cleaned_agents)
    _save_join_keys(keys_data)
    return cleaned_agents


@app.post("/agent-approve")
def agent_approve(data: dict):
    try:
        agent_id = (data.get("agentId") or "").strip()
        if not agent_id:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 agentId"})

        agents = _load_agents_state()
        target = next((a for a in agents if a.get("agentId") == agent_id and not a.get("isMain")), None)
        if not target:
            return JSONResponse(status_code=404, content={"ok": False, "msg": "未找到 agent"})

        target["authStatus"] = "approved"
        target["authApprovedAt"] = datetime.now().isoformat()
        target["authExpiresAt"] = (datetime.now() + timedelta(hours=24)).isoformat()

        _save_agents_state(agents)
        return {"ok": True, "agentId": agent_id, "authStatus": "approved"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.post("/agent-reject")
def agent_reject(data: dict):
    try:
        agent_id = (data.get("agentId") or "").strip()
        if not agent_id:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 agentId"})

        agents = _load_agents_state()
        target = next((a for a in agents if a.get("agentId") == agent_id and not a.get("isMain")), None)
        if not target:
            return JSONResponse(status_code=404, content={"ok": False, "msg": "未找到 agent"})

        target["authStatus"] = "rejected"
        target["authRejectedAt"] = datetime.now().isoformat()

        join_key = target.get("joinKey")
        keys_data = _load_join_keys()
        if join_key:
            key_item = next((k for k in keys_data.get("keys", []) if k.get("key") == join_key), None)
            if key_item:
                key_item["used"] = False
                key_item["usedBy"] = None
                key_item["usedByAgentId"] = None
                key_item["usedAt"] = None

        agents = [a for a in agents if a.get("agentId") != agent_id or a.get("isMain")]
        _save_agents_state(agents)
        _save_join_keys(keys_data)
        return {"ok": True, "agentId": agent_id, "authStatus": "rejected"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.post("/join-agent")
def join_agent(data: dict):
    try:
        if not isinstance(data, dict) or not data.get("name"):
            return JSONResponse(status_code=400, content={"ok": False, "msg": "请提供名字"})

        name = data["name"].strip()
        state = data.get("state", "idle")
        detail = data.get("detail", "")
        join_key = data.get("joinKey", "").strip()

        state = normalize_agent_state(state)

        if not join_key:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "请提供接入密钥"})

        keys_data = _load_join_keys()
        key_item = next((k for k in keys_data.get("keys", []) if k.get("key") == join_key), None)
        if not key_item:
            return JSONResponse(status_code=403, content={"ok": False, "msg": "接入密钥无效"})

        with join_lock:
            keys_data = _load_join_keys()
            key_item = next((k for k in keys_data.get("keys", []) if k.get("key") == join_key), None)
            if not key_item:
                return JSONResponse(status_code=403, content={"ok": False, "msg": "接入密钥无效"})

            key_expires_at_str = key_item.get("expiresAt")
            if key_expires_at_str:
                try:
                    key_expires_at = datetime.fromisoformat(key_expires_at_str)
                    if datetime.now() > key_expires_at:
                        return JSONResponse(status_code=403, content={"ok": False, "msg": "该接入密钥已过期，活动已结束 🎉"})
                except Exception:
                    pass

            agents = _load_agents_state()
            now = datetime.now()

            def _age_seconds(dt_str):
                if not dt_str:
                    return None
                try:
                    dt = datetime.fromisoformat(dt_str)
                    return (now - dt).total_seconds()
                except Exception:
                    return None

            existing = next((a for a in agents if a.get("name") == name and not a.get("isMain")), None)
            existing_id = existing.get("agentId") if existing else None

            for a in agents:
                if a.get("isMain"):
                    continue
                if a.get("authStatus") != "approved":
                    continue
                age = _age_seconds(a.get("lastPushAt"))
                if age is None:
                    age = _age_seconds(a.get("updated_at"))
                if age is not None and age > 300:
                    a["authStatus"] = "offline"

            max_concurrent = int(key_item.get("maxConcurrent", 3))
            active_count = 0
            for a in agents:
                if a.get("isMain"):
                    continue
                if a.get("agentId") == existing_id:
                    continue
                if a.get("joinKey") != join_key:
                    continue
                if a.get("authStatus") != "approved":
                    continue
                age = _age_seconds(a.get("lastPushAt"))
                if age is None:
                    age = _age_seconds(a.get("updated_at"))
                if age is None or age <= 300:
                    active_count += 1

            if active_count >= max_concurrent:
                _save_agents_state(agents)
                return JSONResponse(status_code=429, content={"ok": False, "msg": f"该接入密钥当前并发已达上限（{max_concurrent}），请稍后或换另一个 key"})

            import string as _string

            if existing:
                existing["state"] = state
                existing["detail"] = detail
                existing["updated_at"] = datetime.now().isoformat()
                existing["area"] = state_to_area(state)
                existing["source"] = "remote-openclaw"
                existing["joinKey"] = join_key
                existing["authStatus"] = "approved"
                existing["authApprovedAt"] = datetime.now().isoformat()
                existing["authExpiresAt"] = (datetime.now() + timedelta(hours=24)).isoformat()
                existing["lastPushAt"] = datetime.now().isoformat()
                if not existing.get("avatar"):
                    existing["avatar"] = random.choice(["guest_role_1", "guest_role_2", "guest_role_3", "guest_role_4", "guest_role_5", "guest_role_6"])
                agent_id = existing.get("agentId")
            else:
                agent_id = "agent_" + str(int(datetime.now().timestamp() * 1000)) + "_" + "".join(random.choices(_string.ascii_lowercase + _string.digits, k=4))
                agents.append({
                    "agentId": agent_id,
                    "name": name,
                    "isMain": False,
                    "state": state,
                    "detail": detail,
                    "updated_at": datetime.now().isoformat(),
                    "area": state_to_area(state),
                    "source": "remote-openclaw",
                    "joinKey": join_key,
                    "authStatus": "approved",
                    "authApprovedAt": datetime.now().isoformat(),
                    "authExpiresAt": (datetime.now() + timedelta(hours=24)).isoformat(),
                    "lastPushAt": datetime.now().isoformat(),
                    "avatar": random.choice(["guest_role_1", "guest_role_2", "guest_role_3", "guest_role_4", "guest_role_5", "guest_role_6"]),
                })

            key_item["used"] = True
            key_item["usedBy"] = name
            key_item["usedByAgentId"] = agent_id
            key_item["usedAt"] = datetime.now().isoformat()
            key_item["reusable"] = True

            _save_agents_state(agents)
            _save_join_keys(keys_data)

        return {"ok": True, "agentId": agent_id, "authStatus": "approved", "nextStep": "已自动批准，立即开始推送状态"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.post("/leave-agent")
def leave_agent(data: dict):
    try:
        if not isinstance(data, dict):
            return JSONResponse(status_code=400, content={"ok": False, "msg": "invalid json"})

        agent_id = (data.get("agentId") or "").strip()
        name = (data.get("name") or "").strip()
        if not agent_id and not name:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "请提供 agentId 或名字"})

        agents = _load_agents_state()
        target = None
        if agent_id:
            target = next((a for a in agents if a.get("agentId") == agent_id and not a.get("isMain")), None)
        if (not target) and name:
            target = next((a for a in agents if a.get("name") == name and not a.get("isMain")), None)

        if not target:
            return JSONResponse(status_code=404, content={"ok": False, "msg": "没有找到要离开的 agent"})

        join_key = target.get("joinKey")
        new_agents = [a for a in agents if a.get("isMain") or a.get("agentId") != target.get("agentId")]

        keys_data = _load_join_keys()
        if join_key:
            key_item = next((k for k in keys_data.get("keys", []) if k.get("key") == join_key), None)
            if key_item:
                key_item["used"] = False
                key_item["usedBy"] = None
                key_item["usedByAgentId"] = None
                key_item["usedAt"] = None

        _save_agents_state(new_agents)
        _save_join_keys(keys_data)
        return {"ok": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


# ═══════════════════════════════════════════════════════════
#  Routes — State
# ═══════════════════════════════════════════════════════════
@app.get("/status")
def get_status():
    state = _load_state()
    office_name = get_office_name_from_identity()
    if office_name:
        state["officeName"] = office_name
    return state


@app.post("/agent-push")
def agent_push(data: dict):
    try:
        if not isinstance(data, dict):
            return JSONResponse(status_code=400, content={"ok": False, "msg": "invalid json"})

        agent_id = (data.get("agentId") or "").strip()
        join_key = (data.get("joinKey") or "").strip()
        state = (data.get("state") or "").strip()
        detail = (data.get("detail") or "").strip()
        name = (data.get("name") or "").strip()

        if not agent_id or not join_key or not state:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 agentId/joinKey/state"})

        state = normalize_agent_state(state)

        keys_data = _load_join_keys()
        key_item = next((k for k in keys_data.get("keys", []) if k.get("key") == join_key), None)
        if not key_item:
            return JSONResponse(status_code=403, content={"ok": False, "msg": "joinKey 无效"})

        key_expires_at_str = key_item.get("expiresAt")
        if key_expires_at_str:
            try:
                key_expires_at = datetime.fromisoformat(key_expires_at_str)
                if datetime.now() > key_expires_at:
                    return JSONResponse(status_code=403, content={"ok": False, "msg": "该接入密钥已过期，活动已结束 🎉"})
            except Exception:
                pass

        agents = _load_agents_state()
        target = next((a for a in agents if a.get("agentId") == agent_id and not a.get("isMain")), None)
        if not target:
            return JSONResponse(status_code=404, content={"ok": False, "msg": "agent 未注册，请先 join"})

        auth_status = target.get("authStatus", "pending")
        if auth_status not in {"approved", "offline"}:
            return JSONResponse(status_code=403, content={"ok": False, "msg": "agent 未获授权，请等待主人批准"})
        if auth_status == "offline":
            target["authStatus"] = "approved"
            target["authApprovedAt"] = datetime.now().isoformat()
            target["authExpiresAt"] = (datetime.now() + timedelta(hours=24)).isoformat()

        if target.get("joinKey") != join_key:
            return JSONResponse(status_code=403, content={"ok": False, "msg": "joinKey 不匹配"})

        target["state"] = state
        target["detail"] = detail
        if name:
            target["name"] = name
        avatar = (data.get("avatar") or "").strip()
        if avatar:
            target["avatar"] = avatar
        target["updated_at"] = datetime.now().isoformat()
        target["area"] = state_to_area(state)
        target["source"] = "remote-openclaw"
        target["lastPushAt"] = datetime.now().isoformat()

        _save_agents_state(agents)
        return {"ok": True, "agentId": agent_id, "area": target.get("area")}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.post("/set-agent-avatar")
def set_agent_avatar(data: dict):
    try:
        if not isinstance(data, dict):
            return JSONResponse(status_code=400, content={"ok": False, "msg": "invalid json"})

        agent_id = (data.get("agentId") or "").strip()
        avatar = (data.get("avatar") or "").strip()

        if not agent_id:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 agentId"})
        if not avatar:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 avatar"})

        agents = _load_agents_state()
        target = next((a for a in agents if a.get("agentId") == agent_id), None)
        if not target:
            return JSONResponse(status_code=404, content={"ok": False, "msg": "agent 未找到"})

        target["avatar"] = avatar
        target["updated_at"] = datetime.now().isoformat()
        _save_agents_state(agents)

        return {"ok": True, "agentId": agent_id, "name": target.get("name", ""), "avatar": avatar}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.post("/set_state")
def set_state_endpoint(data: dict):
    try:
        if not isinstance(data, dict):
            return JSONResponse(status_code=400, content={"status": "error", "msg": "invalid json"})
        state = _load_state()
        if "state" in data:
            s = data["state"]
            if s in VALID_AGENT_STATES:
                state["state"] = s
        if "detail" in data:
            state["detail"] = data["detail"]
        state["updated_at"] = datetime.now().isoformat()
        _save_state(state)
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "msg": str(e)})


# ═══════════════════════════════════════════════════════════
#  Routes — Health / Metrics / Bot States
# ═══════════════════════════════════════════════════════════

def _build_yi_ai_status() -> dict:
    """Report collector cache freshness (not blind HTTP health scan).

    Previously checked YiAi /health/live (bypasses auth → false positive).
    Now reports: are roles cached? how many? when was last fetch?
    """
    try:
        roles = _get_cached_roles()
        return {
            "available": len(roles) > 0,
            "roles_cached": len(roles),
            "source": "collector-cache",
        }
    except Exception:
        return {"available": False, "roles_cached": 0, "source": "error"}


@app.get("/health")
def health():
    uptime = time.time() - START_TIME
    bridge_ok = False
    bridge_age = 0.0
    bridge_file = os.path.join(ROOT_DIR, "bridge-state.json")
    if os.path.exists(bridge_file):
        try:
            bridge_age = time.time() - os.path.getmtime(bridge_file)
            bridge_ok = bridge_age < 30
        except OSError:
            pass

    bot_count = 0
    try:
        agents = _load_agents_state()
        bot_count = len(agents)
    except Exception:
        pass

    return {
        "status": "ok",
        "service": "star-office-ui",
        "uptime_seconds": round(uptime, 1),
        "uptime_human": f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s",
        "bridge": {
            "connected": bridge_ok,
            "last_seen_sec": round(bridge_age, 1) if bridge_age else None,
        },
        "bot_count": bot_count,
        "yi_ai": _build_yi_ai_status(),
        "frontend": {
            "fps": client_metrics.get("fps", 0),
            "memory_mb": {
                "used": round(client_metrics.get("usedJSHeapSize", 0) / 1048576, 1),
                "total": round(client_metrics.get("totalJSHeapSize", 0) / 1048576, 1),
                "limit": round(client_metrics.get("jsHeapSizeLimit", 0) / 1048576, 1),
            },
            "last_report_sec": round(time.time() - client_metrics.get("last_report_at", 0), 1) if client_metrics.get("last_report_at") else None,
        },
        "storage": "redis" if redis_enabled() else "json-files",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/client-metrics")
def client_metrics_route(data: dict):
    global client_metrics
    try:
        client_metrics["fps"] = data.get("fps", 0)
        client_metrics["usedJSHeapSize"] = data.get("usedJSHeapSize", 0)
        client_metrics["totalJSHeapSize"] = data.get("totalJSHeapSize", 0)
        client_metrics["jsHeapSizeLimit"] = data.get("jsHeapSizeLimit", 0)
        client_metrics["last_report_at"] = time.time()
    except Exception:
        pass
    return {"ok": True}


@app.get("/ds-bot-states")
def ds_bot_states():
    try:
        agents = _load_agents_state()
        bridge_states = {}
        bridge_file = os.path.join(ROOT_DIR, "bridge-state.json")
        if os.path.exists(bridge_file):
            try:
                with open(bridge_file, "r") as f:
                    bridge_states = json.load(f)
            except Exception:
                pass

        bots = {}
        now_iso = datetime.now().isoformat()
        for a in agents:
            name = a.get("name", "")
            state = a.get("state", "idle")
            detail = a.get("detail", "")
            updated = a.get("updated_at", now_iso)
            if name in bridge_states:
                state = bridge_states[name].get("state", state)
                detail = bridge_states[name].get("detail", detail)
            bots[name] = {"state": state, "detail": detail, "updatedAt": updated}

        return {"bots": bots, "count": len(bots), "updated_at": now_iso}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.get("/office/floor/{n}")
def office_floor(n: int):
    floor_map = _load_floor_registry()
    floor_names = {1: "管理决策层", 2: "工程执行层", 3: "创意内容层"}

    if n not in floor_map:
        return JSONResponse(status_code=404, content={"ok": False, "msg": f"楼层 {n} 不存在 (1-3)"})

    floor_bots = floor_map[n]
    try:
        agents = _load_agents_state()
        bridge_states = {}
        bridge_file = os.path.join(ROOT_DIR, "bridge-state.json")
        if os.path.exists(bridge_file):
            try:
                with open(bridge_file, "r") as f:
                    bridge_states = json.load(f)
            except Exception:
                pass

        bots = {}
        now_iso = datetime.now().isoformat()
        for a in agents:
            name = a.get("name", "")
            if name not in floor_bots:
                continue
            state = a.get("state", "idle")
            detail = a.get("detail", "")
            updated = a.get("updated_at", now_iso)
            if name in bridge_states:
                state = bridge_states[name].get("state", state)
                detail = bridge_states[name].get("detail", detail)
            bots[name] = {"state": state, "detail": detail, "updatedAt": updated}

        active = sum(1 for b in bots.values() if b["state"] != "idle")
        return {"floor": n, "name": floor_names[n], "bots": bots, "count": len(bots), "active": active, "updated_at": now_iso}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.get("/yesterday-memo")
def get_yesterday_memo():
    try:
        yesterday_str = get_yesterday_date_str()
        yesterday_file = os.path.join(MEMORY_DIR, f"{yesterday_str}.md")
        target_file = None
        target_date = yesterday_str

        if os.path.exists(yesterday_file):
            target_file = yesterday_file
        else:
            if os.path.exists(MEMORY_DIR):
                files = [f for f in os.listdir(MEMORY_DIR) if f.endswith(".md") and re.match(r"\d{4}-\d{2}-\d{2}\.md", f)]
                if files:
                    files.sort(reverse=True)
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    for f in files:
                        if f != f"{today_str}.md":
                            target_file = os.path.join(MEMORY_DIR, f)
                            target_date = f.replace(".md", "")
                            break

        if target_file and os.path.exists(target_file):
            memo_content = extract_memo_from_file(target_file)
            return {"success": True, "date": target_date, "memo": memo_content}
        else:
            return {"success": False, "msg": "没有找到昨日日记"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "msg": str(e)})


# ═══════════════════════════════════════════════════════════
#  Routes — Assets
# ═══════════════════════════════════════════════════════════
@app.get("/assets/template.zip")
def assets_template_download():
    if not os.path.exists(ASSET_TEMPLATE_ZIP):
        return JSONResponse(status_code=404, content={"ok": False, "msg": "模板包不存在，请先生成"})
    return FileResponse(ASSET_TEMPLATE_ZIP, filename="assets-replace-template.zip")


@app.get("/assets/list")
def assets_list():
    items = []
    seen = set()
    # Scan dist/ first (production build), then source
    for scan_root in _STATIC_ROOTS:
        for p in Path(scan_root).rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(scan_root).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            if rel.startswith("fonts/"):
                continue
            if p.suffix.lower() not in ASSET_ALLOWED_EXTS:
                continue
            st = p.stat()
            width = None
            height = None
            if Image is not None:
                try:
                    with Image.open(p) as im:
                        width, height = im.size
                except Exception:
                    pass
            items.append({
                "path": rel,
                "size": st.st_size,
                "ext": p.suffix.lower(),
                "width": width,
                "height": height,
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
            })
    items.sort(key=lambda x: x["path"])
    return {"ok": True, "count": len(items), "items": items}


def _bg_generate_worker(task_id: str, custom_prompt: str, speed_mode: str):
    try:
        target = FRONTEND_PATH / "office_bg_small.webp"
        bak = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, bak)

        _generate_rpg_background_to_webp(str(target), width=1280, height=720, custom_prompt=custom_prompt, speed_mode=speed_mode)

        os.makedirs(BG_HISTORY_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        hist_file = os.path.join(BG_HISTORY_DIR, f"office_bg_small-{ts}.webp")
        shutil.copy2(target, hist_file)

        st = target.stat()
        with _bg_tasks_lock:
            _bg_tasks[task_id] = {
                "status": "done",
                "result": {
                    "ok": True,
                    "path": "office_bg_small.webp",
                    "size": st.st_size,
                    "history": os.path.relpath(hist_file, ROOT_DIR),
                    "speed_mode": speed_mode,
                    "msg": "已生成并替换 RPG 房间底图（已自动归档）",
                },
            }
    except Exception as e:
        msg = str(e)
        error_result = {"ok": False, "msg": msg}
        if msg == "MISSING_API_KEY":
            error_result["code"] = "MISSING_API_KEY"
            error_result["msg"] = "Missing GEMINI_API_KEY or GOOGLE_API_KEY"
        elif msg == "API_KEY_REVOKED_OR_LEAKED":
            error_result["code"] = "API_KEY_REVOKED_OR_LEAKED"
            error_result["msg"] = "API key is revoked or flagged as leaked. Please rotate to a new key."
        elif msg.startswith("MODEL_NOT_AVAILABLE"):
            error_result["code"] = "MODEL_NOT_AVAILABLE"
            error_result["msg"] = "Configured model is not available for this API key/channel."
            if "::" in msg:
                error_result["detail"] = msg.split("::", 1)[1]
        with _bg_tasks_lock:
            _bg_tasks[task_id] = {"status": "error", "result": error_result}


@app.post("/assets/generate-rpg-background")
def assets_generate_rpg_background(request: Request, data: dict = {}):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        custom_prompt = (data.get("prompt") or "").strip() if isinstance(data, dict) else ""
        speed_mode = (data.get("speed_mode") or "quality").strip().lower() if isinstance(data, dict) else "quality"
        if speed_mode not in {"fast", "quality"}:
            speed_mode = "fast"

        target = FRONTEND_PATH / "office_bg_small.webp"
        if not target.exists():
            return JSONResponse(status_code=404, content={"ok": False, "msg": "office_bg_small.webp 不存在"})

        runtime_cfg = _load_runtime_config()
        api_key = (runtime_cfg.get("gemini_api_key") or "").strip()
        if not api_key:
            return JSONResponse(status_code=400, content={"ok": False, "code": "MISSING_API_KEY", "msg": "Missing GEMINI_API_KEY or GOOGLE_API_KEY"})
        if not (os.path.exists(GEMINI_PYTHON) and os.path.exists(GEMINI_SCRIPT)):
            return JSONResponse(status_code=500, content={"ok": False, "msg": "生图脚本环境缺失：gemini-image-generate 未安装"})

        with _bg_tasks_lock:
            for tid, task in _bg_tasks.items():
                if task.get("status") == "pending":
                    return {"ok": True, "async": True, "task_id": tid, "msg": "已有生图任务进行中，请等待完成"}

        import string as _string
        task_id = "gen_" + str(int(datetime.now().timestamp() * 1000)) + "_" + "".join(random.choices(_string.ascii_lowercase + _string.digits, k=4))
        with _bg_tasks_lock:
            _bg_tasks[task_id] = {"status": "pending", "created_at": datetime.now().isoformat()}

        t = threading.Thread(target=_bg_generate_worker, args=(task_id, custom_prompt, speed_mode), daemon=True)
        t.start()

        return {"ok": True, "async": True, "task_id": task_id, "msg": "生图任务已启动，请通过 task_id 轮询结果"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.get("/assets/generate-rpg-background/poll")
def assets_generate_rpg_background_poll(request: Request, task_id: str = Query(...)):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    if not task_id:
        return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 task_id"})
    with _bg_tasks_lock:
        task = _bg_tasks.get(task_id)
    if not task:
        return JSONResponse(status_code=404, content={"ok": False, "msg": "任务不存在"})
    status = task.get("status", "pending")
    if status == "pending":
        return {"ok": True, "status": "pending", "msg": "生图进行中..."}
    elif status == "done":
        with _bg_tasks_lock:
            _bg_tasks.pop(task_id, None)
        return {"ok": True, "status": "done", **task.get("result", {})}
    else:
        with _bg_tasks_lock:
            _bg_tasks.pop(task_id, None)
        result = task.get("result", {})
        code = 400 if result.get("code") else 500
        return JSONResponse(status_code=code, content={"ok": False, "status": "error", **result})


@app.post("/assets/restore-reference-background")
def assets_restore_reference_background(request: Request):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        target = FRONTEND_PATH / "office_bg_small.webp"
        if not target.exists():
            return JSONResponse(status_code=404, content={"ok": False, "msg": "office_bg_small.webp 不存在"})
        if not os.path.exists(ROOM_REFERENCE_IMAGE):
            return JSONResponse(status_code=404, content={"ok": False, "msg": "参考图不存在"})

        bak = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, bak)

        ref_ext = os.path.splitext(ROOM_REFERENCE_IMAGE)[1].lower()
        fast_copied = False
        if ref_ext == '.webp':
            try:
                with Image.open(ROOM_REFERENCE_IMAGE) as rim:
                    if rim.size == (1280, 720):
                        shutil.copy2(ROOM_REFERENCE_IMAGE, target)
                        fast_copied = True
            except Exception:
                fast_copied = False

        if not fast_copied:
            if Image is None:
                return JSONResponse(status_code=500, content={"ok": False, "msg": "Pillow 不可用"})
            with Image.open(ROOM_REFERENCE_IMAGE) as im:
                im = im.convert("RGBA").resize((1280, 720), Image.Resampling.LANCZOS)
                im.save(target, "WEBP", quality=92, method=6)

        st = target.stat()
        return {"ok": True, "path": "office_bg_small.webp", "size": st.st_size, "msg": "已恢复初始底图"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.post("/assets/restore-last-generated-background")
def assets_restore_last_generated_background(request: Request):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        target = FRONTEND_PATH / "office_bg_small.webp"
        if not target.exists():
            return JSONResponse(status_code=404, content={"ok": False, "msg": "office_bg_small.webp 不存在"})

        if not os.path.isdir(BG_HISTORY_DIR):
            return JSONResponse(status_code=404, content={"ok": False, "msg": "暂无历史底图"})

        files = [
            os.path.join(BG_HISTORY_DIR, x)
            for x in os.listdir(BG_HISTORY_DIR)
            if x.startswith("office_bg_small-") and x.endswith(".webp")
        ]
        if not files:
            return JSONResponse(status_code=404, content={"ok": False, "msg": "暂无历史底图"})

        latest = max(files, key=lambda p: os.path.getmtime(p))
        bak = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, bak)
        shutil.copy2(latest, target)

        st = target.stat()
        return {"ok": True, "path": "office_bg_small.webp", "size": st.st_size, "from": os.path.relpath(latest, ROOT_DIR), "msg": "已回退到最近一次生成底图"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


# ═══════════════════════════════════════════════════════════
#  Routes — Home Favorites
# ═══════════════════════════════════════════════════════════
@app.get("/assets/home-favorites/list")
def assets_home_favorites_list(request: Request):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        data = _load_home_favorites_index()
        items = data.get("items") or []
        out = []
        for it in items:
            rel = (it.get("path") or "").strip()
            if not rel:
                continue
            abs_path = os.path.join(ROOT_DIR, rel)
            if not os.path.exists(abs_path):
                continue
            fn = os.path.basename(rel)
            out.append({
                "id": it.get("id"),
                "path": rel,
                "url": f"/assets/home-favorites/file/{fn}",
                "thumb_url": f"/assets/home-favorites/file/{fn}",
                "created_at": it.get("created_at") or "",
            })
        out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return {"ok": True, "items": out}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.get("/assets/home-favorites/file/{filename}")
def assets_home_favorites_file(request: Request, filename: str):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    return FileResponse(os.path.join(HOME_FAVORITES_DIR, filename))


@app.post("/assets/home-favorites/save-current")
def assets_home_favorites_save_current(request: Request):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        src = FRONTEND_PATH / "office_bg_small.webp"
        if not src.exists():
            return JSONResponse(status_code=404, content={"ok": False, "msg": "office_bg_small.webp 不存在"})

        _ensure_home_favorites_index()
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        item_id = f"home-{ts}"
        fn = f"{item_id}.webp"
        dst = os.path.join(HOME_FAVORITES_DIR, fn)
        shutil.copy2(str(src), dst)

        idx = _load_home_favorites_index()
        items = idx.get("items") or []
        items.insert(0, {"id": item_id, "path": os.path.relpath(dst, ROOT_DIR), "created_at": datetime.now().isoformat(timespec="seconds")})

        if len(items) > HOME_FAVORITES_MAX:
            extra = items[HOME_FAVORITES_MAX:]
            items = items[:HOME_FAVORITES_MAX]
            for it in extra:
                try:
                    p = os.path.join(ROOT_DIR, it.get("path") or "")
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass

        idx["items"] = items
        _save_home_favorites_index(idx)
        return {"ok": True, "id": item_id, "path": os.path.relpath(dst, ROOT_DIR), "msg": "已收藏当前地图"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.post("/assets/home-favorites/delete")
def assets_home_favorites_delete(request: Request, data: dict):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        item_id = (data.get("id") or "").strip()
        if not item_id:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 id"})

        idx = _load_home_favorites_index()
        items = idx.get("items") or []
        hit = next((x for x in items if (x.get("id") or "") == item_id), None)
        if not hit:
            return JSONResponse(status_code=404, content={"ok": False, "msg": "收藏项不存在"})

        rel = hit.get("path") or ""
        abs_path = os.path.join(ROOT_DIR, rel)
        if os.path.exists(abs_path):
            try:
                os.remove(abs_path)
            except Exception:
                pass

        idx["items"] = [x for x in items if (x.get("id") or "") != item_id]
        _save_home_favorites_index(idx)
        return {"ok": True, "id": item_id, "msg": "已删除收藏"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.post("/assets/home-favorites/apply")
def assets_home_favorites_apply(request: Request, data: dict):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        item_id = (data.get("id") or "").strip()
        if not item_id:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 id"})

        idx = _load_home_favorites_index()
        items = idx.get("items") or []
        hit = next((x for x in items if (x.get("id") or "") == item_id), None)
        if not hit:
            return JSONResponse(status_code=404, content={"ok": False, "msg": "收藏项不存在"})

        src = os.path.join(ROOT_DIR, hit.get("path") or "")
        if not os.path.exists(src):
            return JSONResponse(status_code=404, content={"ok": False, "msg": "收藏文件不存在"})

        target = FRONTEND_PATH / "office_bg_small.webp"
        if not target.exists():
            return JSONResponse(status_code=404, content={"ok": False, "msg": "office_bg_small.webp 不存在"})

        bak = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(str(target), str(bak))
        shutil.copy2(src, str(target))

        st = target.stat()
        return {"ok": True, "path": "office_bg_small.webp", "size": st.st_size, "from": hit.get("path"), "msg": "已应用收藏地图"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


# ═══════════════════════════════════════════════════════════
#  Routes — Asset Auth
# ═══════════════════════════════════════════════════════════
@app.post("/assets/auth")
def assets_auth(request: Request, data: dict):
    try:
        pwd = (data.get("password") or "").strip()
        if pwd and pwd == ASSET_DRAWER_PASS_DEFAULT:
            request.session["asset_editor_authed"] = True
            return {"ok": True, "msg": "认证成功"}
        return JSONResponse(status_code=401, content={"ok": False, "msg": "验证码错误"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.get("/assets/auth/status")
def assets_auth_status(request: Request):
    return {
        "ok": True,
        "authed": _is_asset_editor_authed(request),
        "drawer_default_pass": ASSET_DRAWER_PASS_DEFAULT == "1234",
    }


# ═══════════════════════════════════════════════════════════
#  Routes — Asset Positions / Defaults
# ═══════════════════════════════════════════════════════════
@app.get("/assets/positions")
def assets_positions_get(request: Request):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        return {"ok": True, "items": _load_asset_positions()}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.post("/assets/positions")
def assets_positions_set(request: Request, data: dict):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        key = (data.get("key") or "").strip()
        x = data.get("x")
        y = data.get("y")
        scale = data.get("scale")
        if not key:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 key"})
        if x is None or y is None:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 x/y"})
        x = float(x)
        y = float(y)
        if scale is None:
            scale = 1.0
        scale = float(scale)

        all_pos = _load_asset_positions()
        all_pos[key] = {"x": x, "y": y, "scale": scale, "updated_at": datetime.now().isoformat()}
        _save_asset_positions(all_pos)
        return {"ok": True, "key": key, "x": x, "y": y, "scale": scale}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.get("/assets/defaults")
def assets_defaults_get(request: Request):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        return {"ok": True, "items": _load_asset_defaults()}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.post("/assets/defaults")
def assets_defaults_set(request: Request, data: dict):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        key = (data.get("key") or "").strip()
        x = data.get("x")
        y = data.get("y")
        scale = data.get("scale")
        if not key:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 key"})
        if x is None or y is None:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 x/y"})
        x = float(x)
        y = float(y)
        if scale is None:
            scale = 1.0
        scale = float(scale)

        all_defaults = _load_asset_defaults()
        all_defaults[key] = {"x": x, "y": y, "scale": scale, "updated_at": datetime.now().isoformat()}
        _save_asset_defaults(all_defaults)
        return {"ok": True, "key": key, "x": x, "y": y, "scale": scale}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


# ═══════════════════════════════════════════════════════════
#  Routes — Config / Restore
# ═══════════════════════════════════════════════════════════
@app.get("/config/gemini")
def gemini_config_get(request: Request):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        cfg = _load_runtime_config()
        key = (cfg.get("gemini_api_key") or "").strip()
        masked = ("*" * max(0, len(key) - 4)) + key[-4:] if key else ""
        return {
            "ok": True,
            "has_api_key": bool(key),
            "api_key_masked": masked,
            "gemini_model": _normalize_user_model(cfg.get("gemini_model") or "nanobanana-pro"),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.post("/config/gemini")
def gemini_config_set(request: Request, data: dict):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        api_key = (data.get("api_key") or "").strip()
        model = _normalize_user_model((data.get("model") or "").strip() or "nanobanana-pro")
        payload = {"gemini_model": model}
        if api_key:
            payload["gemini_api_key"] = api_key
        _save_runtime_config(payload)
        return {"ok": True, "msg": "Gemini 配置已保存"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.post("/assets/restore-default")
def assets_restore_default(request: Request, data: dict):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        rel_path = (data.get("path") or "").strip().lstrip("/")
        if not rel_path:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 path"})

        target = (FRONTEND_PATH / rel_path).resolve()
        try:
            target.relative_to(FRONTEND_PATH.resolve())
        except Exception:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "非法 path"})

        if not target.exists():
            return JSONResponse(status_code=404, content={"ok": False, "msg": "目标文件不存在"})

        root, ext = os.path.splitext(str(target))
        default_path = root + ext + ".default"
        if not os.path.exists(default_path):
            return JSONResponse(status_code=404, content={"ok": False, "msg": "未找到默认资产快照"})

        bak = str(target) + ".bak"
        if os.path.exists(str(target)):
            shutil.copy2(str(target), bak)

        shutil.copy2(default_path, str(target))
        st = os.stat(str(target))
        return {"ok": True, "path": rel_path, "size": st.st_size, "msg": "已重置为默认资产"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.post("/assets/restore-prev")
def assets_restore_prev(request: Request, data: dict):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        rel_path = (data.get("path") or "").strip().lstrip("/")
        if not rel_path:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 path"})

        target = (FRONTEND_PATH / rel_path).resolve()
        try:
            target.relative_to(FRONTEND_PATH.resolve())
        except Exception:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "非法 path"})

        bak = str(target) + ".bak"
        if not os.path.exists(bak):
            return JSONResponse(status_code=404, content={"ok": False, "msg": "未找到上一版备份"})

        shutil.copy2(str(target), bak + ".tmp") if os.path.exists(str(target)) else None
        shutil.copy2(bak, str(target))
        st = os.stat(str(target))
        return {"ok": True, "path": rel_path, "size": st.st_size, "msg": "已回退到上一版"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


@app.post("/assets/upload")
def assets_upload(
    request: Request,
    path: str = Form(..., description="Relative path for the target asset"),
    file: UploadFile = File(..., description="Asset file to upload"),
    backup: str = Form("1"),
    auto_spritesheet: str = Form("0"),
    frame_w: str = Form("0"),
    frame_h: str = Form("0"),
    cols: str = Form("0"),
    rows: str = Form("0"),
    preserve_original: str = Form("1"),
    pixel_art: str = Form("1"),
):
    guard = _require_asset_editor_auth(request)
    if guard:
        return guard
    try:
        rel_path = path.lstrip("/")
        do_backup = backup.strip() != "0"
        if not rel_path or file is None:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "缺少 path 或 file"})

        target = (FRONTEND_PATH / rel_path).resolve()
        try:
            target.relative_to(FRONTEND_PATH.resolve())
        except Exception:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "非法 path"})

        if target.suffix.lower() not in ASSET_ALLOWED_EXTS:
            return JSONResponse(status_code=400, content={"ok": False, "msg": "仅允许上传图片/美术资源类型"})

        if not target.exists():
            return JSONResponse(status_code=404, content={"ok": False, "msg": "目标文件不存在，请先从 /assets/list 选择 path"})

        target.parent.mkdir(parents=True, exist_ok=True)

        # Create default snapshot
        default_snap = Path(str(target) + ".default")
        if not default_snap.exists():
            try:
                shutil.copy2(target, default_snap)
            except Exception:
                pass

        if do_backup:
            bak = target.with_suffix(target.suffix + ".bak")
            shutil.copy2(target, bak)

        auto_sheet = auto_spritesheet.strip() == "1"
        ext_name = (file.filename or "").lower()

        if auto_sheet and target.suffix.lower() in {".webp", ".png"}:
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(ext_name)[1] or ".gif", delete=False) as tf:
                src_path = tf.name
                tf.write(file.file.read())
            try:
                in_w, in_h = _probe_animated_frame_size(src_path)
                frame_w_int = int(frame_w or (in_w or 64))
                frame_h_int = int(frame_h or (in_h or 64))

                # Static image uploaded to spritesheet target — slice by grid
                if not (ext_name.endswith(".gif") or ext_name.endswith(".webp")) and Image is not None:
                    try:
                        with Image.open(src_path) as sim:
                            sim = sim.convert("RGBA")
                            sw, sh = sim.size
                            if frame_w_int <= 0 or frame_h_int <= 0:
                                frame_w_int, frame_h_int = sw, sh
                            grid_cols = max(1, sw // frame_w_int)
                            grid_rows = max(1, sh // frame_h_int)
                            sheet_w = grid_cols * frame_w_int
                            sheet_h = grid_rows * frame_h_int
                            if sheet_w <= 0 or sheet_h <= 0:
                                raise RuntimeError("静态图尺寸与帧规格不匹配")

                            cropped = sim.crop((0, 0, sheet_w, sheet_h))
                            if target.suffix.lower() == ".webp":
                                cropped.save(str(target), "WEBP", lossless=True, quality=100, method=6)
                            else:
                                cropped.save(str(target), "PNG")

                            st = target.stat()
                            return {
                                "ok": True,
                                "path": rel_path,
                                "size": st.st_size,
                                "backup": do_backup,
                                "converted": {
                                    "from": ext_name.split(".")[-1] if "." in ext_name else "image",
                                    "to": "webp_spritesheet" if target.suffix.lower() == ".webp" else "png_spritesheet",
                                    "frame_w": frame_w_int,
                                    "frame_h": frame_h_int,
                                    "columns": grid_cols,
                                    "rows": grid_rows,
                                    "frames": grid_cols * grid_rows,
                                    "preserve_original": False,
                                    "pixel_art": True,
                                },
                            }
                    finally:
                        pass

                preserve_original_bool = preserve_original.strip() == "1"
                pixel_art_bool = pixel_art.strip() == "1"
                req_cols = int(cols or 0)
                req_rows = int(rows or 0)
                sheet_path, out_cols, out_rows, frames, out_fw, out_fh = _animated_to_spritesheet(
                    src_path,
                    frame_w_int,
                    frame_h_int,
                    out_ext=target.suffix.lower(),
                    preserve_original=preserve_original_bool,
                    pixel_art=pixel_art_bool,
                    cols=(req_cols if req_cols > 0 else None),
                    rows=(req_rows if req_rows > 0 else None),
                )
                shutil.move(sheet_path, str(target))
                st = target.stat()
                from_type = "gif" if ext_name.endswith(".gif") else "webp"
                to_type = "webp_spritesheet" if target.suffix.lower() == ".webp" else "png_spritesheet"
                return {
                    "ok": True,
                    "path": rel_path,
                    "size": st.st_size,
                    "backup": do_backup,
                    "converted": {
                        "from": from_type,
                        "to": to_type,
                        "frame_w": out_fw,
                        "frame_h": out_fh,
                        "columns": out_cols,
                        "rows": out_rows,
                        "frames": frames,
                        "preserve_original": preserve_original_bool,
                        "pixel_art": pixel_art_bool,
                    },
                }
            finally:
                try:
                    os.remove(src_path)
                except Exception:
                    pass

        # Simple upload — just save the file
        with open(str(target), "wb") as dst:
            file.file.seek(0)
            shutil.copyfileobj(file.file, dst)

        st = target.stat()
        return {"ok": True, "path": rel_path, "size": st.st_size, "backup": do_backup}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


# ═══════════════════════════════════════════════════════════
#  Static file serving (must be last)
# ═══════════════════════════════════════════════════════════
# Vite build outputs: dist/assets/ (JS/CSS), dist/static/ (images/sprites)
# Source files at frontend/ root (legacy).
# URL prefix /static/ → look under dist/static/ first, then dist/, then frontend/

def _find_static_file(url_prefix: str, path: str) -> Optional[str]:
    """Try to find a static file. `url_prefix` is the URL segment (e.g. 'static' or 'assets')."""
    # Try with the URL prefix under each root first (matches dist/ structure)
    prefixed = f"{url_prefix}/{path}"
    for root in _STATIC_ROOTS:
        full_path = os.path.join(root, prefixed)
        if os.path.isfile(full_path):
            return full_path
    # Then try bare path under each root (matches flat source layout)
    for root in _STATIC_ROOTS:
        full_path = os.path.join(root, path)
        if os.path.isfile(full_path):
            return full_path
    return None


@app.get("/static/{path:path}")
def static_files(path: str):
    """Serve static image/spritesheet assets."""
    full_path = _find_static_file("static", path)
    if full_path is None:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full_path)


@app.get("/assets/{path:path}")
def assets_files(path: str):
    """Serve Vite-bundled JS/CSS assets."""
    full_path = _find_static_file("assets", path)
    if full_path is None:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full_path)


# ═══════════════════════════════════════════════════════════
#  Main entry point
# ═══════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════
#  Cross-Project API v2 — YiAi / YiVad integration
# ═══════════════════════════════════════════════════════════

@app.get("/api/v2/yi-ai/roles")
def api_v2_yi_ai_roles():
    """Proxy YiAi roles from the collector's in-memory cache (60s TTL).

    Output format aligned with data-integration-spec §7.1:
      id, title, botId, botName, icon, status, updatedAt,
      knowledgeFileCount, redLinesCount, quickRefsCount
    """
    try:
        roles = _get_cached_roles()
        result = []
        for role_id, r in roles.items():
            entry = {
                "id": role_id,
                "title": r.get("title", ""),
                "botId": r.get("botId", ""),
                "botName": r.get("botName", ""),
                "icon": r.get("icon", ""),
                "domain": r.get("domain", ""),
                "status": r.get("status", "active"),
                "updatedAt": r.get("updatedAt", ""),
                "knowledgeFileCount": r.get("knowledgeFileCount", 0),
                "redLinesCount": r.get("redLinesCount", 0),
                "quickRefsCount": r.get("quickRefsCount", 0),
            }
            result.append(entry)
        return {
            "roles": result,
            "count": len(result),
            "botIdCount": sum(1 for r in result if r.get("botId")),
            "source": "collector-cache (YiAi GET /roles, 60s TTL)",
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.warning("Failed to read YiAi roles from collector cache: %s", e)
        return {
            "roles": [],
            "count": 0,
            "botIdCount": 0,
            "source": "collector-cache (unavailable)",
            "error": str(e),
            "updated_at": datetime.now().isoformat(),
        }


@app.get("/api/v2/bot-states")
def api_v2_bot_states():
    """Unified DSH bot states — single source for YiVad/YiAi consumption (R1).

    Sources (priority order):
      1. collector _latest_states      ← DSH live states (watchdog, <1s lag)
      2. collector _get_cached_roles   ← YiAi role metadata (60s TTL)
      3. floor-registry.json           ← floor allocation map
      4. agents-state.json             ← agentId lookup (legacy, for IDs)
    """
    now_iso = datetime.now().isoformat()
    try:
        # ── Get live DSH states from collector ──
        live_states = _get_latest_states()
        roles = _get_cached_roles()

        # ── Floor registry ──
        floor_map: dict = {}
        floor_file = os.path.join(ROOT_DIR, "floor-registry.json")
        if os.path.exists(floor_file):
            try:
                with open(floor_file, "r") as f:
                    floor_data = json.load(f)
                for fname, fbots in floor_data.items():
                    if fname.startswith("_meta"):
                        continue
                    for b in fbots:
                        floor_map[b] = fname
            except Exception:
                pass

        # ── Agent ID lookup from legacy agents-state.json ──
        agent_id_map: dict = {}
        try:
            for a in _load_agents_state():
                n = a.get("name", "")
                aid = a.get("agentId", "")
                if n and aid:
                    agent_id_map[n] = aid
        except Exception:
            pass

        # ── Merge: collector states + roles + floor + agentId ──
        bots: dict = {}

        # Build botName → botId reverse index from roles cache (keyed by id, not name)
        _bot_name_to_id: dict = {}
        for _r in roles.values():
            bn = _r.get("botName", "").strip()
            bd = _r.get("botId", "").strip()
            if bn and bd:
                _bot_name_to_id[bn] = bd

        for name, sdata in live_states.items():
            if name == "Chief":
                continue  # Chief handled separately

            state = sdata.get("state", "idle")
            detail = sdata.get("detail", "")

            # Inject YiAi role metadata
            role = roles.get(name, {})
            role_title = sdata.get("role_title", "") or role.get("title", "")
            icon = sdata.get("icon", "") or role.get("icon", "")
            bot_id = role.get("botId", "") or sdata.get("botId", "") or _bot_name_to_id.get(name, "")

            # Floor: collector data first → floor-registry → hash fallback
            floor = sdata.get("floor", "") or floor_map.get(name, "")
            if not floor:
                h = abs(hash(name))
                floor = f"{(h % 3) + 1}F"

            bots[name] = {
                "agentId": agent_id_map.get(name, ""),
                "botId": bot_id,
                "name": name,
                "state": state,
                "detail": detail,
                "floor": floor,
                "roleTitle": role_title,
                "icon": icon,
                "updatedAt": sdata.get("updated_at", now_iso),
            }

        return {
            "bots": bots,
            "count": len(bots),
            "source": "collector (DSH watchdog + YiAi roles)",
            "rolesCached": len(roles),
            "yiAiAvailable": len(roles) > 0,
            "updated_at": now_iso,
        }
    except Exception as e:
        logger.exception("api_v2_bot_states failed")
        return JSONResponse(status_code=500, content={"ok": False, "msg": str(e)})


if __name__ == "__main__":
    import uvicorn

    raw_port = os.environ.get("STAR_BACKEND_PORT", "19000")
    try:
        backend_port = int(raw_port)
    except ValueError:
        backend_port = 19000
    if backend_port <= 0:
        backend_port = 19000

    mode = "production" if is_production_mode() else "development"
    print("=" * 50)
    print("Star Office UI - Backend State Service (FastAPI + Redis)")
    print("=" * 50)
    print(f"State file: {STATE_FILE}")
    print(f"Listening on: http://0.0.0.0:{backend_port}")
    print(f"Mode: {mode}")
    if is_production_mode():
        print("Security hardening: ENABLED (strict checks)")
    else:
        weak_flags = []
        if not is_strong_secret(str(SECRET_KEY)):
            weak_flags.append("weak STAR_OFFICE_SECRET/FLASK_SECRET_KEY")
        if not is_strong_drawer_pass(ASSET_DRAWER_PASS_DEFAULT):
            weak_flags.append("weak ASSET_DRAWER_PASS")
        if weak_flags:
            print("Security hardening: WARNING (dev mode) -> " + ", ".join(weak_flags))
        else:
            print("Security hardening: OK")
    print("=" * 50)

    uvicorn.run(app, host="0.0.0.0", port=backend_port, log_level="info")