"""
三源合并引擎 — DSH / YiAi / YiVad 统一状态聚合

核心规则:
  1. source_priority 高的源覆盖低的（DSH=10 > YiAi=5 > YiVad=3）
  2. 同优先级按 updated_at 取最新
  3. error 状态的源降 2 级（不污染正常数据）
  4. 未知 bot 直接透传，标记 source 来源
"""

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

# ── 源优先级常量 ────────────────────────────────────────────
SOURCE_PRIORITY = {
    "dsh": 10,
    "yiai": 5,
    "yivad": 3,
}
DEFAULT_PRIORITY = 1


def resolve_source_priority(source: str, state: str) -> int:
    """计算有效优先级：offline 降 3 级（派生状态，权威性最低），error 降 2 级"""
    base = SOURCE_PRIORITY.get(source.lower(), DEFAULT_PRIORITY)
    if state == "offline":
        return max(0, base - 3)
    if state == "error":
        return max(0, base - 2)
    return base


def parse_ts(ts: Optional[str]) -> datetime:
    """安全解析 ISO 时间戳，失败返回 epoch"""
    if not ts:
        return datetime.min
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.min


def pick_winner(
    existing: Optional[Tuple[Dict[str, Any], int, datetime]],
    candidate_name: str,
    candidate: Dict[str, Any],
    source: str,
) -> Tuple[Dict[str, Any], int, datetime]:
    """
    比较已有值与候选值，返回胜出的 (data, priority, timestamp)。
    
    规则: 先比优先级 → 再比时间戳 → 默认保留已有
    """
    state = candidate.get("state", "idle")
    priority = resolve_source_priority(source, state)
    ts = parse_ts(candidate.get("updatedAt") or candidate.get("updated_at"))

    if existing is None:
        return (candidate, priority, ts)

    existing_data, existing_priority, existing_ts = existing

    if priority > existing_priority:
        return (candidate, priority, ts)
    if priority == existing_priority and ts > existing_ts:
        return (candidate, priority, ts)
    return existing


def merge_bot_states(
    sources: Dict[str, Dict[str, Any]],
    *,
    allow_empty: bool = True,
    state_fields: tuple = ("state", "detail", "updatedAt", "updated_at"),
) -> Dict[str, Dict[str, Any]]:
    """
    合并多个数据源的 bot 状态。
    
    核心语义：
      - state_fields 中的字段按优先级竞胜（高优先级源覆盖低优先级）
      - 其他字段（如 roleTitle/icon/redlines）从所有源合并，补齐 winner 缺失的元数据

    Args:
        sources: {
            "dsh":   {"Chief": {"state":"executing","updatedAt":"..."}, ...},
            "yiai":  {"Chief": {"state":"idle","roleTitle":"首席","icon":"🐧"}, ...},
            "yivad": {},
        }
        allow_empty: 为 True 时，空源不报错
        state_fields: 竞胜字段（默认: state, detail, updatedAt），其余字段走合并

    Returns:
        {"Chief": {"state":"executing","roleTitle":"首席","icon":"🐧","source":"dsh"}, ...}

    Raises:
        ValueError: allow_empty=False 且某源为空
    """
    if not sources:
        return {}

    # allow_empty=False 校验
    if not allow_empty:
        for source, bots in sources.items():
            if not bots:
                raise ValueError(f"数据源 '{source}' 为空 (allow_empty=False)")

    # 按优先级排序源名（跳过空源）
    source_order = sorted(
        [s for s in sources if sources[s]],
        key=lambda s: SOURCE_PRIORITY.get(s.lower(), DEFAULT_PRIORITY),
        reverse=True,  # 高优先先处理
    )

    # Phase 1: 所有源按优先级顺序合并（低优先先写，高优先覆盖 state_fields）
    merged_raw: Dict[str, Dict[str, Any]] = {}

    for source in reversed(source_order):  # 低优先先写
        for name, data in sources[source].items():
            if not isinstance(data, dict):
                continue
            if name not in merged_raw:
                merged_raw[name] = {}
            merged_raw[name].update(data)

    # Phase 2: state_fields 按优先级竞胜
    for name in merged_raw:
        winner_data = None
        winner_priority = -1
        winner_ts = datetime.min

        for source in source_order:
            bots = sources[source]
            if name not in bots:
                continue
            data = bots[name]
            state = data.get("state", "idle")
            priority = resolve_source_priority(source, state)
            ts = parse_ts(data.get("updatedAt") or data.get("updated_at"))

            if (priority > winner_priority or
                (priority == winner_priority and ts > winner_ts)):
                winner_data = data
                winner_priority = priority
                winner_ts = ts

        if winner_data:
            for field in state_fields:
                if field in winner_data:
                    merged_raw[name][field] = winner_data[field]

    # Phase 3: 附加 source 元信息
    result: Dict[str, Dict[str, Any]] = {}
    for name, data in merged_raw.items():
        entry = dict(data)
        entry.setdefault("source", "merged")
        result[name] = entry

    return result


def compute_source_health(sources: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    计算各数据源健康度。

    Returns:
        {"dsh":  {"available": True,  "bot_count": 5, "error_bots": 0},
         "yiai": {"available": False, "bot_count": 0, "error_bots": 0}}
    """
    health = {}
    for source, bots in sources.items():
        bot_count = len(bots)
        error_count = sum(
            1 for b in bots.values()
            if isinstance(b, dict) and b.get("state") == "error"
        )
        health[source] = {
            "available": bot_count > 0,
            "bot_count": bot_count,
            "error_bots": error_count,
            "healthy": bot_count > 0 and error_count < bot_count * 0.5,
        }
    return health


def get_fallback_chain(
    sources: Dict[str, Dict[str, Any]],
    target_bot: str,
) -> list:
    """
    按优先级返回某 bot 的兜底链: [dsh数据, yiai数据, yivad数据, None]。
    前端可用此链依次尝试渲染，直到找到非 idle/error 状态。
    """
    chain = []
    for source in ("dsh", "yiai", "yivad"):
        bots = sources.get(source, {})
        if target_bot in bots:
            chain.append({"source": source, "data": bots[target_bot]})

    if not chain:
        chain.append(None)
    return chain