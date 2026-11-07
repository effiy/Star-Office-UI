/**
 * useDSHBridge — Unified DSH ↔ Star-Office Bridge (SU-03 P1)
 *
 * Three data sources, merged into the Pinia store:
 *   1. WebSocket (primary)       — ws_server :19002, <500ms latency
 *   2. DSH Bridge (secondary)    — dsh_server :19003 /ds-bot-states, 3s poll
 *   3. REST /agents (fallback)   — main app :19000, 3s poll when (1) fails
 *
 * Usage (in App.vue):
 *   const bridge = useDSHBridge();
 *   onMounted(() => bridge.start());
 *   onBeforeUnmount(() => bridge.stop());
 *
 * This composable OWNS the boot sequence — App.vue no longer
 * manually calls fetchBots / connectWebSocket.
 */

import { ref, type Ref } from "vue";
import { useBotStore } from "../stores/useBotStore";

export interface BridgeStatus {
  /** WebSocket connected */
  ws: boolean;
  /** DSH bridge responding */
  dsh: boolean;
  /** REST polling active */
  polling: boolean;
}

export function useDSHBridge() {
  const botStore = useBotStore();

  // ── Status ──
  const status = ref<BridgeStatus>({ ws: false, dsh: false, polling: false });

  // ── Timers ──
  let dshTimer: ReturnType<typeof setInterval> | null = null;
  let restTimer: ReturnType<typeof setInterval> | null = null;
  let rolesTimer: ReturnType<typeof setInterval> | null = null;
  let started = false;

  // ── DSH Bridge poll (3s, secondary data source) ──

  async function pollDSHBridge() {
    try {
      const resp = await fetch("/api/v2/bot-states");
      if (!resp.ok) {
        status.value.dsh = false;
        return;
      }
      const data = await resp.json();
      botStore.ingestDSHStates(data);
      status.value.dsh = true;
    } catch {
      status.value.dsh = false;
    }
  }

  // ── YiAi roles poll (60s, metadata — low frequency) ──

  async function pollYiAiRoles() {
    try {
      const resp = await fetch("/api/v2/yi-ai/roles");
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.roles?.length > 0) {
        botStore.ingestYiAiRoles(data.roles);
      }
    } catch {
      // Silent — roles are metadata, not critical for real-time
    }
  }

  // ── REST fallback poll (3s, only when WS is down) ──

  async function pollREST() {
    if (botStore.wsConnected) return; // WebSocket is alive, skip REST
    status.value.polling = true;
    try {
      await botStore.fetchBots();
    } catch {
      // Silent — WebSocket will recover
    }
  }

  // ── Lifecycle ──

  async function start() {
    if (started) return;
    started = true;

    // 1. Load floor registry (replaces hardcoded BOT_HOME_FLOOR)
    await botStore.fetchFloorRegistry();

    // 2. Initial data: REST /agents + DSH /api/v2/bot-states + YiAi roles
    await Promise.allSettled([
      botStore.fetchBots(),
      pollDSHBridge(),
      pollYiAiRoles(),
    ]);

    // 3. WebSocket (primary real-time)
    botStore.connectWebSocket();

    // 4. DSH bridge periodic poll (3s)
    dshTimer = setInterval(pollDSHBridge, 3000);

    // 5. REST fallback when WS is disconnected (3s)
    restTimer = setInterval(pollREST, 3000);

    // 6. YiAi roles metadata refresh (60s, low priority)
    rolesTimer = setInterval(pollYiAiRoles, 60000);

    // Monitor WS connection state
    setInterval(() => {
      status.value.ws = botStore.wsConnected;
    }, 1000);
  }

  function stop() {
    started = false;
    if (dshTimer) { clearInterval(dshTimer); dshTimer = null; }
    if (restTimer) { clearInterval(restTimer); restTimer = null; }
    if (rolesTimer) { clearInterval(rolesTimer); rolesTimer = null; }
    botStore.disconnectWebSocket();
    status.value = { ws: false, dsh: false, polling: false };
  }

  /** Force immediate DSH re-poll (for debugging) */
  function forceDSHPoll() {
    pollDSHBridge();
  }

  return {
    /** Bridge connection status: ws, dsh, polling */
    status,
    /** Start all bridge channels (call once from App.vue onMounted) */
    start,
    /** Stop all bridge channels (call from App.vue onBeforeUnmount) */
    stop,
    /** Force immediate DSH re-poll */
    forceDSHPoll,
  };
}