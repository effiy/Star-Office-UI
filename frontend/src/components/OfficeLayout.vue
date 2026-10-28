<template>
  <div class="sol" :class="{ 'is-drawer-open': botStore.drawerOpen }">
    <!-- Loading overlay -->
    <div v-if="botStore.loading" class="sol-loading">
      <div class="sol-loading__text">Loading Star's pixel office...</div>
      <div class="sol-loading__bar"><div class="sol-loading__fill" /></div>
    </div>

    <!-- Game stage -->
    <div class="sol-stage">
      <slot />
    </div>

    <!-- Bottom panels -->
    <div class="sol-panels">
      <slot name="panels" />
    </div>

    <!-- Guest agent drawer -->
    <Transition name="drawer-slide">
      <aside v-if="botStore.drawerOpen" class="sol-drawer">
        <StatusPanel :compact="false" />
        <BotInfoCard
          v-if="botStore.selectedBot"
          :bot="botStore.selectedBot"
          @close="botStore.closeDrawer"
        />
      </aside>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { useBotStore } from "../stores/useBotStore";
import StatusPanel from "./StatusPanel.vue";
import BotInfoCard from "./BotInfoCard.vue";

const botStore = useBotStore();
</script>

<style scoped>
.sol {
  display: flex; flex-direction: column; min-height: 100vh; position: relative;
  background: var(--so-bg);
}
.sol-stage { flex: 1; min-height: 0; position: relative; }
.sol-panels { display: flex; gap: var(--so-gap-lg); padding: 20px; }
.sol-drawer {
  position: fixed; right: 0; top: 0; bottom: 0;
  width: max(320px, 30vw); padding: var(--so-padding-lg);
  background: var(--so-panel-bg); backdrop-filter: var(--so-glass-blur);
  border-left: 1px solid var(--so-panel-border); z-index: 100;
  overflow-y: auto; display: flex; flex-direction: column; gap: var(--so-gap);
}

/* Loading */
.sol-loading {
  position: fixed; inset: 0; z-index: 999;
  background: var(--so-bg); display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: var(--so-gap);
}
.sol-loading__text { font-size: var(--so-font-size-lg); color: var(--so-ink-muted); }
.sol-loading__bar { width: 200px; height: 4px; background: var(--so-accent); border-radius: 2px; overflow: hidden; }
.sol-loading__fill { height: 100%; width: 40%; background: var(--so-ink); border-radius: 2px; animation: sol-load 1.2s ease infinite; }
@keyframes sol-load { 0% { transform: translateX(-100%); } 100% { transform: translateX(350%); } }

/* Drawer */
.drawer-slide-enter-active, .drawer-slide-leave-active { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.drawer-slide-enter-from, .drawer-slide-leave-to { transform: translateX(100%); opacity: 0; }

@media (max-width: 768px) {
  .sol-drawer { width: 100%; }
  .sol-panels { flex-direction: column; gap: var(--so-gap); padding: 10px; }
}
</style>
