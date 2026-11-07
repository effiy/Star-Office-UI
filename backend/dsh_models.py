"""
DSH State Data Models — Pydantic schemas for YiAi DSH ↔ Star-Office data flow.

Shared by dsh_server, state_reader, and ws_server for consistent data contracts.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ── DSH State Enums ─────────────────────────────────────────────────

class DshBotState(str, Enum):
    """DSH bot execution states, ordered by priority (highest first).
    
    ⚠️ 契约对齐：内部解析 6 态 (executing~idle)，发射侧 7 态 (含 offline)。
    offline 是显式派生状态——bot 从活跃监控中消失时由 Collector 计算，不直接从 DSH 文件解析。
    """
    EXECUTING = "executing"      # Active turn in inflight.json
    WRITING = "writing"           # Active segment in state.json
    RESEARCHING = "researching"   # Agent正在搜索
    SYNCING = "syncing"           # Agent正在同步
    ERROR = "error"               # Agent出错
    IDLE = "idle"                 # 待命中
    OFFLINE = "offline"           # 离线（显式派生，非 DSH 文件原生）


# State priority for conflict resolution: higher index = higher priority
STATE_PRIORITY: Dict[str, int] = {
    "executing": 6,
    "writing": 5,
    "researching": 4,
    "syncing": 3,
    "error": 2,
    "idle": 1,
    "offline": 0,
}


# ── DSH Raw File Schemas ────────────────────────────────────────────

class DshSegment(BaseModel):
    """A segment (turn part) from DSH state.json bots[*].segments[*]."""
    segmentId: str = ""
    startedAt: Optional[str] = None
    endedAt: Optional[str] = None  # "active" means still running
    kind: str = ""


class DshBotEntry(BaseModel):
    """A bot entry from DSH state.json bots dict."""
    name: str = ""
    segments: List[DshSegment] = Field(default_factory=list)
    status: str = ""


class DshStateFile(BaseModel):
    """Top-level structure of ~/.dsh/bot/state.json."""
    bots: Dict[str, DshBotEntry] = Field(default_factory=dict)
    updated_at: Optional[str] = None


class DshTurn(BaseModel):
    """A single turn from inflight.json turns dict."""
    botId: str = ""
    botName: str = ""
    startedAt: Optional[str] = None
    status: str = ""


class DshInflightFile(BaseModel):
    """Top-level structure of ~/.dsh/bot/inflight.json."""
    turns: Dict[str, DshTurn] = Field(default_factory=dict)
    updated_at: Optional[str] = None


# ── Bridge Output Schemas ───────────────────────────────────────────

class BotStateDetail(BaseModel):
    """Single bot state in the bridge API response."""
    state: DshBotState = DshBotState.IDLE
    detail: str = ""  # Human-readable label (e.g. "工作中…")
    updatedAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DsBotStatesResponse(BaseModel):
    """Response for GET /ds-bot-states from the bridge."""
    bots: Dict[str, BotStateDetail] = Field(default_factory=dict)
    count: int = 0
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "bridge"  # "bridge" | "file-fallback"


class BridgeHealthResponse(BaseModel):
    """Response for GET /health from the bridge."""
    status: str = "ok"
    uptime: int = 0
    uptime_human: str = ""
    started_at: str = ""
    cached_bots: int = 0
    poll_interval: int = 3


# ── State Push Schemas ──────────────────────────────────────────────

class AgentPushRequest(BaseModel):
    """Request body for POST /agent-push to main app."""
    agentId: str
    joinKey: str
    state: str
    detail: str = ""
    name: str = ""


class AgentPushResponse(BaseModel):
    """Response from POST /agent-push."""
    ok: bool
    msg: str = ""


class ChiefStateRequest(BaseModel):
    """Request body for POST /set_state (Chief)."""
    state: str
    detail: str = ""


# ── Merged State Schema (for app.py /ds-bot-states) ─────────────────

class MergedBotState(BaseModel):
    """Bot state merged from agents-state.json + bridge-state.json."""
    state: str = "idle"
    detail: str = ""
    updatedAt: str = ""
    stateSource: str = "local"  # "local" | "bridge" | "merged"


class MergedStatesResponse(BaseModel):
    """Response for GET /ds-bot-states from the main app."""
    bots: Dict[str, MergedBotState] = Field(default_factory=dict)
    count: int = 0
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())