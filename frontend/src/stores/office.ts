/**
 * Office store — manages office-level state
 * Floor layout, area mappings, asset positions
 */

import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { FLOOR_CONFIG, FLOOR_IDS, type FloorId } from "./useBotStore";

export type AreaId = "breakroom" | "writing" | "researching" | "error" | "syncing";

export interface AreaInfo {
  id: AreaId;
  label: string;
  x: number;
  y: number;
  icon: string;
}

export const AREA_MAP: Record<AreaId, AreaInfo> = {
  breakroom: { id: "breakroom", label: "休息区", x: 640, y: 360, icon: "☕" },
  writing: { id: "writing", label: "写作区", x: 320, y: 360, icon: "✍️" },
  researching: { id: "researching", label: "研究区", x: 320, y: 360, icon: "🔍" },
  error: { id: "error", label: "报错区", x: 1066, y: 180, icon: "🐛" },
  syncing: { id: "syncing", label: "同步区", x: 1157, y: 592, icon: "🔄" },
};

export const useOfficeStore = defineStore("office", () => {
  // ── State ──
  const currentFloor = ref<FloorId>("1F");

  /** Dynamic asset positions loaded from server */
  const assetPositions = ref<Record<string, { x: number; y: number }>>({});

  /** Asset defaults (scale, depth) */
  const assetDefaults = ref<Record<string, any>>({});

  /** Runtime config */
  const runtimeConfig = ref<Record<string, any>>({});

  // ── Getters ──

  const floors = computed(() =>
    FLOOR_IDS.map((id) => ({ id, ...FLOOR_CONFIG[id] }))
  );

  const currentFloorConfig = computed(() => FLOOR_CONFIG[currentFloor.value]);

  const areas = computed(() => Object.values(AREA_MAP));

  const floorStats = computed(() => {
    // Delegate to bot store — computed in useBotStore
    return {} as Record<string, { total: number; working: number }>;
  });

  // ── Actions ──

  function setFloor(floor: FloorId) {
    currentFloor.value = floor;
  }

  async function fetchAssetConfig() {
    try {
      const [posRes, defRes] = await Promise.all([
        fetch("/asset-positions").then((r) => r.json()),
        fetch("/asset-defaults").then((r) => r.json()),
      ]);
      assetPositions.value = posRes;
      assetDefaults.value = defRes;
    } catch {
      // Use defaults from layout.ts
    }
  }

  async function fetchRuntimeConfig() {
    try {
      const res = await fetch("/runtime-config");
      if (res.ok) runtimeConfig.value = await res.json();
    } catch {
      // Use built-in defaults
    }
  }

  return {
    currentFloor,
    assetPositions,
    assetDefaults,
    runtimeConfig,
    floors,
    currentFloorConfig,
    areas,
    floorStats,
    setFloor,
    fetchAssetConfig,
    fetchRuntimeConfig,
  };
});