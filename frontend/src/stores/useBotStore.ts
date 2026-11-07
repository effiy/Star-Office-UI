import { defineStore } from "pinia";
import { ref, computed } from "vue";

/* ═══════════════════════════════════════════════════════════════
   Bot types — 6 状态，floor 由像素办公室 WebSocket 直接提供
   ═══════════════════════════════════════════════════════════════ */

export type BotState =
  | "idle"
  | "writing"
  | "researching"
  | "executing"
  | "syncing"
  | "error";

export interface Bot {
  id: string;
  name: string;
  role: string;
  avatar: string;
  state: BotState;
  detail: string;
  /** 归属楼层（1F/2F/3F，由像素办公室分配，固定不变） */
  floor: string;
  /** 当前所在区域（breakroom/writing/executing/...） */
  area: string;
  /** 像素坐标 */
  deskX: number;
  deskY: number;
  updatedAt: string | null;
  /** YiAi 角色卡：职位名称（如"首席协调官"） */
  roleTitle?: string;
  /** YiAi 角色卡：icon emoji */
  roleIcon?: string;
  /** YiAi 角色卡：红线规则（≤5条） */
  roleRedlines?: string[];
  /** WS 标记：超过 10s 未更新视为 stale */
  stale?: boolean;
}

/* ═══════════════════════════════════════════════════════════════
   Floor config — 像素办公室权威分配
   ═══════════════════════════════════════════════════════════════ */

export const FLOOR_CONFIG = {
  "1F": { label: "1F 管理决策层", order: 1, yRange: [40, 240] },
  "2F": { label: "2F 工程执行层", order: 2, yRange: [260, 480] },
  "3F": { label: "3F 创意内容层", order: 3, yRange: [500, 696] },
} as const;

export type FloorId = keyof typeof FLOOR_CONFIG;
export const FLOOR_IDS: FloorId[] = ["1F", "2F", "3F"];

/* ═══════════════════════════════════════════════════════════════
   Bot → 归属楼层映射 — 从 floor-registry.json 动态加载
   启动时 fetch，hash 兜底保证同名始终同层
   ═══════════════════════════════════════════════════════════════ */

/** Static fallback for SSR / pre-fetch window (kept in sync with floor-registry.json) */
const STATIC_FLOOR_FALLBACK: Record<string, string> = {
  Chief: "1F", "管理顾问": "1F", "技术负责人": "1F", "产品经理": "1F", "Readme管家": "1F",
  "mac·企鹅": "1F", "mac·古天乐": "1F", "技术管家·哲思": "1F", bob: "1F",
  "设计品味": "1F", "OKR管家": "1F", "UX负责人": "1F", "测试负责人": "1F",
  "运营负责人": "1F", "安全负责人": "1F",
  "软件工程师": "2F", "AI工程师": "2F", "SRE工程师": "2F", "Git管家": "2F",
  "UB模式": "2F", "Vue3专家": "2F", "SU·实时·闪电": "2F", "SU·后端·铸舰": "2F",
  "SU·架构·筑桥": "2F", "Cpolar管家": "2F", "数据工程师": "2F",
  "DevOps工程师": "2F", "QA工程师": "2F", "安全工程师": "2F",
  "后端工程师": "2F", "前端工程师": "2F", "全栈工程师": "2F", "ML工程师": "2F",
  "YiAi·核心": "2F", "YiAi·接口": "2F",
  "Remotion大师": "3F", "排版管家": "3F", "知识管理者": "3F", "像素办公室": "3F",
  "形象大师": "3F", "内容创作者": "3F", "动画师": "3F", "插画师": "3F",
  "视频编辑": "3F", "文案策划": "3F", "社交媒体": "3F",
  "YiVad·设计": "3F", "YiVad·动效": "3F", "YiKnowledge·索引": "3F", "YiKnowledge·检索": "3F",
};

let _dynamicFloorMap: Record<string, string> | null = null;

function getHomeFloor(name: string): string {
  // Prefer dynamically loaded registry, fallback to static
  const map = _dynamicFloorMap ?? STATIC_FLOOR_FALLBACK;
  const known = map[name];
  if (known) return known;
  // 同名 hash 兜底（与 Python 一致：abs(hash(name)) % 3 + 1）
  let h = 0;
  for (let i = 0; i < name.length; i++) {
    h = ((h << 5) - h) + name.charCodeAt(i);
    h |= 0;
  }
  const floor = Math.abs(h) % 3 + 1;
  return `${floor}F`;
}

/** Normalize floor from backend (integer 1, "1", or "1F") → "1F"/"2F"/"3F" */
function normalizeFloor(raw: any, fallback: string): string {
  if (raw === null || raw === undefined) return fallback;
  const s = String(raw).trim();
  if (/^[123]F$/i.test(s)) return s.toUpperCase();
  if (/^[123]$/.test(s)) return `${s}F`;
  return fallback;
}

/* ═══════════════════════════════════════════════════════════════
   Store
   ═══════════════════════════════════════════════════════════════ */

export const useBotStore = defineStore("bot", () => {
  // ── State ──
  const bots = ref<Bot[]>([]);
  const currentFloor = ref<FloorId>("1F");
  const selectedBotId = ref<string | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const drawerOpen = ref(false);
  const isAnimating = ref(false);
  const wsConnected = ref(false);
  const lastSnapshot = ref<string | null>(null);

  // ── WebSocket ref ──
  let ws: WebSocket | null = null;
  let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null;

  // ── Getters ──
  const floors = computed(() =>
    FLOOR_IDS.map((id) => ({ id, ...FLOOR_CONFIG[id] }))
  );

  const botsOnCurrentFloor = computed(() =>
    bots.value.filter((b) => b.floor === currentFloor.value)
  );

  const selectedBot = computed(() =>
    bots.value.find((b) => b.id === selectedBotId.value) ?? null
  );

  const onlineCount = computed(() => bots.value.length);

  const workingCount = computed(() =>
    bots.value.filter(
      (b) => b.state !== "idle"
    ).length
  );

  const floorStats = computed(() => {
    const stats: Record<string, { total: number; working: number }> = {};
    for (const fid of FLOOR_IDS) {
      const onFloor = bots.value.filter((b) => b.floor === fid);
      stats[fid] = {
        total: onFloor.length,
        working: onFloor.filter((b) => b.state !== "idle").length,
      };
    }
    return stats;
  });

  /** Bots whose updatedAt is > 10 seconds ago (stale gray-out) */
  const staleBotIds = computed(() => {
    const threshold = Date.now() - 10_000; // 10s stale window
    const ids = new Set<string>();
    for (const b of bots.value) {
      if (!b.updatedAt) { ids.add(b.id); continue; }
      const ts = new Date(b.updatedAt).getTime();
      if (isNaN(ts) || ts < threshold) ids.add(b.id);
    }
    return ids;
  });

  // ── Actions ──

  /** 全量拉取（REST API fallback） */
  async function fetchBots() {
    loading.value = true;
    error.value = null;
    try {
      const resp = await fetch("/agents");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const agents = await resp.json();
      ingestAgents(agents);
    } catch (e: any) {
      error.value = e.message ?? "Failed to fetch bots";
    } finally {
      loading.value = false;
    }
  }

  /** 按楼层拉取 */
  async function fetchFloor(floor: FloorId) {
    loading.value = true;
    error.value = null;
    try {
      const resp = await fetch(`/office/floor/${floor.slice(0, 1)}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      if (data.bots) {
        const agents = Object.entries(data.bots).map(([name, info]: [string, any]) => ({
          agentId: name,
          name,
          state: info.state ?? "idle",
          detail: info.detail ?? "",
          floor: normalizeFloor(info.floor, floor),
          area: info.area ?? "",
          avatar: info.avatar ?? "",
          updated_at: data.timestamp ?? null,
        }));
        ingestAgents(agents);
      }
    } catch (e: any) {
      error.value = e.message ?? `Failed to fetch floor ${floor}`;
    } finally {
      loading.value = false;
    }
  }

  /** 统一处理 agent 列表（REST API 格式：array of agents） */
  function ingestAgents(agents: any[]) {
    if (!Array.isArray(agents)) return;
    bots.value = agents.map((a: any) => {
      const name = a.name ?? "";
      const state = normaliseState(a.state);
      const floor = normalizeFloor(a.floor, getHomeFloor(name));
      return {
        id: a.agentId ?? name,
        name,
        role: a.area ?? "",
        avatar: a.avatar ?? "",
        state,
        detail: a.detail ?? "",
        floor,
        area: a.area ?? "",
        deskX: a.deskX ?? 0,
        deskY: a.deskY ?? 0,
        updatedAt: a.updated_at ?? a.lastPushAt ?? a.timestamp ?? null,
      };
    });
  }

  /** 处理 WebSocket snapshot 消息 */
  function ingestSnapshot(snapshot: Record<string, any>, timestamp: string) {
    const incoming = new Map<string, any>();
    for (const [name, info] of Object.entries(snapshot)) {
      incoming.set(name, info);
    }

    bots.value = Array.from(incoming.entries()).map(([name, info]: [string, any]) => {
      const state = normaliseState(info.state);
      const floor = normalizeFloor(info.floor, getHomeFloor(name));
      return {
        id: name,
        name,
        role: info.area ?? "",
        avatar: info.avatar ?? "",
        state,
        detail: info.detail ?? "",
        floor,
        area: info.area ?? "",
        deskX: info.deskX ?? 0,
        deskY: info.deskY ?? 0,
        updatedAt: timestamp,
      };
    });
    lastSnapshot.value = timestamp;
  }

  /** 处理 WebSocket state_change 消息（增量更新） */
  function ingestChanges(changes: Record<string, any>, timestamp: string) {
    for (const [name, info] of Object.entries(changes)) {
      const state = normaliseState(info.state);
      const floor = normalizeFloor(info.floor, getHomeFloor(name));
      const idx = bots.value.findIndex((b) => b.id === name);
      const bot: Bot = {
        id: name,
        name,
        role: info.area ?? "",
        avatar: info.avatar ?? "",
        state,
        detail: info.detail ?? "",
        floor,
        area: info.area ?? "",
        deskX: info.deskX ?? 0,
        deskY: info.deskY ?? 0,
        updatedAt: timestamp,
      };
      if (idx >= 0) {
        bots.value[idx] = bot;
      } else {
        bots.value.push(bot);
      }
    }
  }

  function setFloor(floor: FloorId) {
    isAnimating.value = true;
    currentFloor.value = floor;
    if (typeof window !== "undefined") {
      (window as any).__soSetFloor?.(floor);
    }
    setTimeout(() => { isAnimating.value = false; }, 350);
  }

  function selectBot(id: string | null) {
    selectedBotId.value = id;
    if (id) drawerOpen.value = true;
  }

  function closeDrawer() {
    drawerOpen.value = false;
    selectedBotId.value = null;
  }

  /** Connect WebSocket for real-time updates */
  function connectWebSocket() {
    if (ws && ws.readyState === WebSocket.OPEN) return;
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = (import.meta as any).env?.VITE_WS_URL || `${protocol}//${location.hostname}:19002`;

    try { ws = new WebSocket(wsUrl); }
    catch { scheduleReconnect(); return; }

    ws.onopen = () => {
      wsConnected.value = true;
      if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const ts = data.timestamp ?? new Date().toISOString();
        if (data.type === "snapshot" && data.bots) {
          ingestSnapshot(data.bots, ts);
        } else if (data.type === "state_change" && data.changes) {
          ingestChanges(data.changes, ts);
        }
      } catch { /* ignore malformed */ }
    };

    ws.onclose = () => { wsConnected.value = false; ws = null; scheduleReconnect(); };
    ws.onerror = () => { ws?.close(); };
  }

  function disconnectWebSocket() {
    if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
    ws?.close(); ws = null; wsConnected.value = false;
  }

  function scheduleReconnect() {
    if (wsReconnectTimer) return;
    wsReconnectTimer = setTimeout(() => { wsReconnectTimer = null; connectWebSocket(); }, 5000);
  }

  function normaliseState(raw: string): BotState {
    switch (raw?.toLowerCase()) {
      case "writing": return "writing";
      case "researching": case "research": return "researching";
      case "executing": case "exec": case "run": case "running": return "executing";
      case "syncing": case "sync": return "syncing";
      case "error": case "fail": case "failed": return "error";
      case "idle": default: return "idle";
    }
  }

  /** Load floor registry from JSON (replaces hardcoded BOT_HOME_FLOOR) */
  async function fetchFloorRegistry() {
    try {
      const resp = await fetch("/floor-registry.json");
      if (!resp.ok) return;
      const data = await resp.json();
      const map: Record<string, string> = {};
      for (const floor of ["1F", "2F", "3F"]) {
        const names: string[] = data[floor] ?? [];
        for (const name of names) {
          map[name] = floor;
        }
      }
      _dynamicFloorMap = map;
    } catch {
      // Keep STATIC_FLOOR_FALLBACK
    }
  }

  /** Consume DSH bridge bot states (from /api/v2/bot-states, main app :19000) */
  function ingestDSHStates(dshData: { bots: Record<string, any> }) {
    if (!dshData?.bots) return;
    for (const [name, info] of Object.entries(dshData.bots)) {
      const stableId = info.agentId ?? name;
      const state = normaliseState(info.state);
      const floor = normalizeFloor(info.floor, getHomeFloor(name));
      const idx = bots.value.findIndex((b) => b.id === stableId);
      const bot: Bot = {
        id: stableId,
        name: info.name ?? name,
        role: info.role ?? info.area ?? "",
        avatar: info.avatar ?? "",
        state,
        detail: info.detail ?? "",
        floor,
        area: info.area ?? "",
        deskX: info.deskX ?? 0,
        deskY: info.deskY ?? 0,
        updatedAt: info.updatedAt ?? null,
      };
      if (idx >= 0) {
        bots.value[idx] = bot;
      } else {
        bots.value.push(bot);
      }
    }
  }

  /** Cache YiAi role metadata (from /api/v2/yi-ai/roles, 60s refresh) */
  const yiAiRoles = ref<Record<string, any>[]>([]);

  function ingestYiAiRoles(roles: Record<string, any>[]) {
    yiAiRoles.value = roles;
  }

  return {
    bots, currentFloor, selectedBotId, loading, error, drawerOpen, isAnimating, wsConnected, lastSnapshot,
    yiAiRoles,
    floors, botsOnCurrentFloor, selectedBot, onlineCount, workingCount, floorStats, staleBotIds,
    fetchBots, fetchFloor, setFloor, selectBot, closeDrawer,
    connectWebSocket, disconnectWebSocket,
    fetchFloorRegistry, ingestDSHStates, ingestYiAiRoles,
  };
});