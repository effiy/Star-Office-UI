<template>
  <Transition name="floor-slide" mode="out-in">
    <OfficeLayout :key="botStore.currentFloor">
      <!-- Phaser game canvas -->
      <div id="game-container" ref="gameContainer" />

      <!-- Overlay UI (non-blocking, above canvas) -->
      <StatusPanel />

      <!-- Floor switcher -->
      <OfficeFloor
        :floors="botStore.floors"
        :current="botStore.currentFloor"
        @switch-floor="botStore.setFloor"
      />
    </OfficeLayout>
  </Transition>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useBotStore } from "./stores/useBotStore";
import { usePhaserGame } from "./composables/usePhaserGame";
import OfficeLayout from "./components/OfficeLayout.vue";
import OfficeFloor from "./components/OfficeFloor.vue";
import StatusPanel from "./components/StatusPanel.vue";

const botStore = useBotStore();
const gameContainer = ref<HTMLElement>();

onMounted(async () => {
  await botStore.fetchBots();
  if (gameContainer.value) {
    usePhaserGame(gameContainer);
  }
});
</script>
