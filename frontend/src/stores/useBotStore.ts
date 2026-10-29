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
   Bot → 归属楼层映射（像素办公室权威分配，作为 API 不可用时的 fallback）
   ═══════════════════════════════════════════════════════════════ */

const BOT_HOME_FLOOR: Record<string, string> = {
  Chief: "1F", "管理顾问": "1F", "技术负责人": "1F", "产品经理": "1F", "Readme管家": "1F",
  "软件工程师": "2F", "AI工程师": "2F", "SRE工程师": "2F", "Git管家": "2F", "UB模式": "2F", "Vue3专家": "2F",
  "Remotion大师": "3F", "排版管家": "3F", "设计品味": "3F", "知识管理者": "3F", "像素办公室": "3F",
};

function getHomeFloor(name: string): string {
  return BOT_HOME_FLOOR[name] || "2F";
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
          floor: String(info.floor ?? floor.slice(0, 1)),
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
      const floor = String(a.floor ?? getHomeFloor(name));
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
      const floor = String(info.floor ?? getHomeFloor(name));
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
      const floor = String(info.floor ?? getHomeFloor(name));
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
    const url = `${protocol}//${location.hostname}:19002`;

    try { ws = new WebSocket(url); }
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

  return {
    bots, currentFloor, selectedBotId, loading, error, drawerOpen, isAnimating, wsConnected, lastSnapshot,
    floors, botsOnCurrentFloor, selectedBot, onlineCount, workingCount, floorStats,
    fetchBots, fetchFloor, setFloor, selectBot, closeDrawer,
    connectWebSocket, disconnectWebSocket,
  };
});