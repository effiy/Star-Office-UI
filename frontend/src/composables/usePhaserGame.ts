/**
 * usePhaserGame — Pinia ↔ Phaser Bridge (SU-03)
 *
 * Replaces the old game.js polling approach with reactive data flow:
 *   Pinia store (bots, currentFloor) → Phaser scene (AgentPool, culling)
 *
 * Usage (in App.vue):
 *   const { bridgeReady, setupBridge, getStats } = usePhaserGame();
 *   <PhaserCanvas ref="phaserRef" @ready="setupBridge" />
 */

import { ref, watch, nextTick, type ShallowRef } from "vue";
import { useBotStore, type FloorId } from "../stores/useBotStore";
import type { SceneManagerAPI } from "../game/OfficeScene";

export interface PhaserStats {
  activeAgents: number;
  poolSize: number;
  fps: number;
}

export function usePhaserGame() {
  const botStore = useBotStore();

  // ── State ──
  const bridgeReady = ref(false);
  const stats = ref<PhaserStats>({ activeAgents: 0, poolSize: 0, fps: 0 });

  let manager: SceneManagerAPI | null = null;
  let syncTimer: ReturnType<typeof setTimeout> | null = null;
  let statsTimer: ReturnType<typeof setInterval> | null = null;

  // ── Debounced sync: batches rapid store changes ──
  function scheduleSync() {
    if (syncTimer) clearTimeout(syncTimer);
    syncTimer = setTimeout(() => {
      if (manager) {
        manager.syncAgents(botStore.bots);
      }
    }, 16); // ~60fps debounce — batches within a single frame
  }

  // ── Setup bridge (called from parent on @ready) ──
  function setupBridge(mgr: SceneManagerAPI) {
    manager = mgr;
    bridgeReady.value = true;

    // Initial sync
    manager.syncAgents(botStore.bots);

    // Watch bot state changes → update Phaser sprites
    watch(
      () => botStore.bots,
      () => {
        scheduleSync();
      },
      { deep: true }
    );

    // Watch floor changes → cull agents on other floors
    watch(
      () => botStore.currentFloor,
      (floor: FloorId) => {
        manager?.setFloor(floor);
        nextTick(() => {
          manager?.syncAgents(botStore.bots);
        });
      }
    );

    // Periodic stats polling
    statsTimer = setInterval(() => {
      if (manager) {
        stats.value = manager.getStats();
      }
    }, 2000);
  }

  // ── Teardown ———─
  function teardown() {
    if (syncTimer) clearTimeout(syncTimer);
    if (statsTimer) clearInterval(statsTimer);
    manager = null;
    bridgeReady.value = false;
  }

  // ── Public API ──
  function getManager(): SceneManagerAPI | null {
    return manager;
  }

  function forceSync() {
    if (manager) {
      manager.syncAgents(botStore.bots);
    }
  }

  return {
    /** Whether the Pinia↔Phaser bridge is active */
    bridgeReady,
    /** Real-time stats: active agents, pool size, FPS */
    stats,
    /** Call from PhaserCanvas @ready event to establish the bridge */
    setupBridge,
    /** Tear down the bridge (called on unmount or error) */
    teardown,
    /** Get the raw SceneManagerAPI */
    getManager,
    /** Force immediate agent re-sync (for debugging) */
    forceSync,
  };
}