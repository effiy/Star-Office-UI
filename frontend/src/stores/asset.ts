/**
 * Asset store — manages game asset loading state
 * Tracks which spritesheets, images, and fonts are loaded
 */

import { defineStore } from "pinia";
import { ref, computed } from "vue";

export interface AssetEntry {
  key: string;
  type: "image" | "spritesheet" | "font" | "audio";
  url: string;
  loaded: boolean;
  progress: number; // 0–100
}

export const useAssetStore = defineStore("asset", () => {
  // ── State ──
  const assets = ref<Map<string, AssetEntry>>(new Map());
  const loading = ref(false);
  const totalCount = ref(0);
  const loadedCount = ref(0);
  const error = ref<string | null>(null);

  // ── Getters ──

  const progress = computed(() =>
    totalCount.value > 0 ? Math.round((loadedCount.value / totalCount.value) * 100) : 0
  );

  const isReady = computed(() => loadedCount.value >= totalCount.value && totalCount.value > 0);

  const failedAssets = computed(() =>
    Array.from(assets.value.values()).filter((a) => !a.loaded && a.progress < 0)
  );

  // ── Actions ──

  function registerAsset(entry: Omit<AssetEntry, "loaded" | "progress">) {
    assets.value.set(entry.key, { ...entry, loaded: false, progress: 0 });
    totalCount.value = assets.value.size;
  }

  function markLoaded(key: string) {
    const entry = assets.value.get(key);
    if (entry) {
      entry.loaded = true;
      entry.progress = 100;
      loadedCount.value++;
    }
  }

  function markProgress(key: string, pct: number) {
    const entry = assets.value.get(key);
    if (entry) entry.progress = Math.min(100, Math.max(0, pct));
  }

  function markFailed(key: string) {
    const entry = assets.value.get(key);
    if (entry) entry.progress = -1; // negative = failed
  }

  function reset() {
    assets.value.clear();
    totalCount.value = 0;
    loadedCount.value = 0;
    error.value = null;
    loading.value = false;
  }

  return {
    assets,
    loading,
    totalCount,
    loadedCount,
    error,
    progress,
    isReady,
    failedAssets,
    registerAsset,
    markLoaded,
    markProgress,
    markFailed,
    reset,
  };
});