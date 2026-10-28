import { defineStore } from "pinia";
import { ref, computed } from "vue";

export interface Bot {
  id: string;
  name: string;
  role: string;
  avatar: string;
  state: "idle" | "executing" | "writing" | "offline";
  detail: string;
  floor: string;
  deskX: number;
  deskY: number;
  updatedAt: string | null;
}

export const FLOORS = ["1F 大厅", "2F 研发区", "3F 休息室", "B1 机房"] as const;
export type FloorId = (typeof FLOORS)[number];

export const useBotStore = defineStore("bot", () => {
  // ── State ──
  const bots = ref<Bot[]>([]);
  const currentFloor = ref<FloorId>("1F 大厅");
  const selectedBotId = ref<string | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const drawerOpen = ref(false);
  const isAnimating = ref(false);

  // ── Getters ──
  const floors = computed(() => [...FLOORS]);
  const botsOnCurrentFloor = computed(() =>
    bots.value.filter((b) => b.floor === currentFloor.value)
  );
  const selectedBot = computed(() =>
    bots.value.find((b) => b.id === selectedBotId.value) ?? null
  );
  const onlineCount = computed(() =>
    bots.value.filter((b) => b.state !== "offline").length
  );
  const executingCount = computed(() =>
    bots.value.filter((b) => b.state === "executing" || b.state === "writing").length
  );

  // ── Actions ──
  async function fetchBots() {
    loading.value = true;
    error.value = null;
    try {
      const resp = await fetch("/agents");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const agents = await resp.json();
      bots.value = agents.map((a: any) => ({
        id: a.agentId ?? a.name,
        name: a.name,
        role: a.area ?? "",
        avatar: a.avatar ?? "",
        state: normaliseState(a.state),
        detail: a.detail ?? "",
        floor: a.floor ?? "1F 大厅",
        deskX: a.deskX ?? 0,
        deskY: a.deskY ?? 0,
        updatedAt: a.updated_at ?? null,
      }));
    } catch (e: any) {
      error.value = e.message ?? "Failed to fetch bots";
    } finally {
      loading.value = false;
    }
  }

  function setFloor(floor: FloorId) {
    isAnimating.value = true;
    currentFloor.value = floor;
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

  function normaliseState(raw: string): Bot["state"] {
    switch (raw) {
      case "executing": return "executing";
      case "writing": return "writing";
      case "idle": return "idle";
      default: return "offline";
    }
  }

  return {
    bots, currentFloor, selectedBotId, loading, error, drawerOpen, isAnimating,
    floors, botsOnCurrentFloor, selectedBot, onlineCount, executingCount,
    fetchBots, setFloor, selectBot, closeDrawer,
  };
});
